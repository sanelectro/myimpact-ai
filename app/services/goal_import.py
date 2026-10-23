import asyncio
import json
import re
import unicodedata
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.exceptions import DocumentExtractionError, LLMQuotaExceededError
from app.db.models.goal import GoalDB
from app.models.goal import GoalCreate, GoalScope, GoalStatus
from app.models.goal_import import GoalImportExtractionResult
from app.models.llm import LLMRequest
from app.repositories.document import DocumentRepository
from app.services.goal import GoalService
from app.services.llm.interface import ILLMService
from app.storage.interface import FileStorage

GOAL_EXTRACTION_MAX_RETRIES = 5
GOAL_EXTRACTION_RETRY_DELAY_SECONDS = 0.5


class GoalImportService:
    """Turn normalized document content into reviewable draft goals."""

    def __init__(
        self,
        session: Session,
        storage: FileStorage,
        llm_service: ILLMService,
    ) -> None:
        self.session = session
        self.storage = storage
        self.llm_service = llm_service
        self.document_repository = DocumentRepository(session)
        self.goal_service = GoalService(session)

    async def import_from_document(self, document_id: str, user_id: str):
        document = self.document_repository.get_by_id(document_id)
        if document is None or document.user_id != user_id:
            raise ValueError("Document not found")
        if not document.extracted_content_path:
            raise ValueError("Document has not been processed")

        existing = self.goal_service.repository.get_by_source_document_id(document_id)
        if existing:
            return {"imported_goals": existing, "skipped_duplicates": []}

        try:
            content = self.storage.read(document.extracted_content_path).decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise DocumentExtractionError("Extracted document content could not be read") from exc

        extraction = await self._extract(content)
        existing_goals = self.goal_service.get_goals_by_user_id(user_id)
        goals = []
        skipped_duplicates = []
        comparison_goals: list[GoalDB] = list(existing_goals)

        for candidate in extraction.goals:
            title = candidate.title.strip()
            duplicate = self._find_duplicate_goal(
                title=title,
                description=candidate.description,
                scope=candidate.scope,
                existing_goals=comparison_goals,
            )
            if duplicate is not None:
                skipped_duplicates.append({
                    "title": title,
                    "existing_goal_id": duplicate.id,
                })
                continue

            goal = self.goal_service.create_goal(
                GoalCreate(
                    user_id=user_id,
                    title=title,
                    description=candidate.description,
                    scope=candidate.scope,
                    start_date=candidate.start_date,
                    end_date=candidate.end_date,
                    status=GoalStatus.DRAFT,
                    source="file_import",
                    source_document_id=document_id,
                )
            )
            goals.append(goal)
            # Include newly-created goals so duplicate candidates in the same
            # document are also suppressed.
            comparison_goals.append(goal)
        return {"imported_goals": goals, "skipped_duplicates": skipped_duplicates}

    @classmethod
    def _find_duplicate_goal(
        cls,
        *,
        title: str,
        description: str | None,
        scope: GoalScope,
        existing_goals: list[GoalDB],
    ) -> GoalDB | None:
        """Return the existing goal when a candidate is materially duplicated.

        This deliberately uses deterministic local text similarity instead of an
        LLM call so importing the same goal from PDF/DOCX/XLSX does not create
        duplicates and does not add model cost.
        """
        candidate_title = cls._normalise_text(title)
        candidate_description = cls._normalise_text(description or "")
        if not candidate_title:
            return None

        for existing in existing_goals:
            # Scope is part of the duplicate identity. A personal goal and a
            # team goal with similar wording can legitimately coexist.
            if existing.scope != scope:
                continue

            existing_title = cls._normalise_text(existing.title)
            if not existing_title:
                continue

            # Strong exact/containment match handles format differences such as
            # "JL5 Roles.pdf" vs "JL5 Roles.docx" where extracted wording is
            # identical or one title has a small qualifier appended.
            if candidate_title == existing_title:
                return existing
            if (candidate_title in existing_title or existing_title in candidate_title) and min(
                len(candidate_title), len(existing_title)
            ) >= 18:
                return existing

            title_similarity = cls._text_similarity(candidate_title, existing_title)
            if title_similarity < 0.90:
                continue

            existing_description = cls._normalise_text(existing.description or "")
            if not candidate_description or not existing_description:
                if title_similarity >= 0.94:
                    return existing
                continue

            description_similarity = cls._text_similarity(
                candidate_description, existing_description
            )
            combined = (title_similarity * 0.70) + (description_similarity * 0.30)
            if combined >= 0.88 or title_similarity >= 0.96:
                return existing

        return None

    @staticmethod
    def _normalise_text(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).lower()
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _text_similarity(cls, left: str, right: str) -> float:
        sequence_score = SequenceMatcher(None, left, right).ratio()
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        if not left_tokens or not right_tokens:
            return sequence_score
        jaccard_score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        return (sequence_score * 0.65) + (jaccard_score * 0.35)

    async def _extract(self, content: str) -> GoalImportExtractionResult:
        prompt = (
            "Extract the meaningful employee goals stated in the document. "
            "Return only a JSON object with a goals array. Each goal must contain "
            "title, description, scope, start_date, end_date, and confidence. "
            "scope must be one of: personal, team, organization. Use personal only "
            "when the document does not clearly indicate team or organization scope. "
            "Dates must be ISO YYYY-MM-DD or null. Do not invent goals, dates, or scope. "
            "Ignore generic policies, responsibilities, and expectations that are not expressed as goals. "
            "If there are no clear goals, return an empty goals array.\n\n"
            f"DOCUMENT CONTENT:\n{content}"
        )
        request = LLMRequest(
            prompt=prompt,
            response_format={"type": "json_object"},
        )
        last_error: ValueError | None = None

        for attempt in range(GOAL_EXTRACTION_MAX_RETRIES + 1):
            try:
                response = await self.llm_service.generate(request)
            except Exception as exc:
                if self._is_quota_error(exc):
                    raise LLMQuotaExceededError(
                        "The LLM provider quota or token balance is exhausted. "
                        "Check provider usage and billing limits, then retry."
                    ) from exc

                status_code = getattr(exc, "status_code", None)
                if isinstance(status_code, int) and 400 <= status_code < 500 and status_code not in (408, 429):
                    raise ValueError("Goal extraction provider failed") from exc
                last_error = ValueError("Goal extraction provider failed")
            else:
                try:
                    return self._parse_extraction_response(response.content)
                except ValueError as exc:
                    last_error = exc

            if attempt < GOAL_EXTRACTION_MAX_RETRIES:
                await asyncio.sleep(GOAL_EXTRACTION_RETRY_DELAY_SECONDS)

        if last_error is not None:
            raise last_error
        raise ValueError("Goal extraction failed after all attempts")

    @staticmethod
    def _is_quota_error(error: Exception) -> bool:
        body = getattr(error, "body", None)
        error_details = " ".join(
            (
                str(error),
                str(getattr(error, "code", "")),
                json.dumps(body, default=str),
            )
        ).lower()
        quota_markers = (
            "insufficient_quota",
            "quota_exceeded",
            "quota exceeded",
            "quota exhausted",
            "out of tokens",
            "out of credits",
            "tokens exhausted",
            "billing_hard_limit",
            "billing hard limit",
        )
        return any(marker in error_details for marker in quota_markers)

    @staticmethod
    def _parse_extraction_response(content: str) -> GoalImportExtractionResult:
        raw = content.strip()
        if raw.startswith("```"):
            raw = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                raw,
                flags=re.IGNORECASE | re.DOTALL,
            ).strip()
        try:
            return GoalImportExtractionResult.model_validate_json(raw)
        except ValidationError:
            # Some providers occasionally return a JSON object wrapped in prose.
            try:
                payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
                return GoalImportExtractionResult.model_validate(payload)
            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                raise ValueError("Goal extraction returned an invalid response") from exc
