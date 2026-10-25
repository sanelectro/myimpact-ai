import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field
from importlib.resources import files
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_approval import EvidenceApprovalDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.goal import GoalDB
from app.db.models.goal_source_retrieval import GoalSourceRetrievalDB
from app.db.models.goal_source_fetch_state import GoalSourceFetchStateDB
from app.db.models.goal_criterion import (
    GoalAssessmentRunDB,
    GoalCriterionAssessmentDB,
    GoalCriterionAssessmentEventDB,
    GoalCriterionAssessmentEvidenceDB,
    GoalCriterionDB,
    GoalCriterionVersionDB,
)
from app.exceptions import GoalCriterionAssessmentError
from app.models.evidence import EvidenceSourceType, EvidenceStatus
from app.models.evidence_approval import EvidenceApprovalStatus
from app.models.goal_criteria import (
    GoalAssessmentBatchResponse,
    GoalAssessmentLifecycle,
    GoalAssessmentRunResponse,
    GoalAssessmentRunStatus,
    GoalAssessmentSummaryResponse,
    GoalCriterionAssessmentEventResponse,
    GoalCriterionEvidenceResponse,
    GoalCriterionAssessmentProposal,
    GoalCriterionAssessmentResponse,
    GoalCriterionDefinition,
    GoalCriterionResult,
    GoalCriterionSummary,
    GoalCriterionType,
    GoalSourceRetrievalStatus,
    GoalSourceRetrievalResponse,
)
from app.models.evidence_mapping import EvidenceRelevance
from app.models.llm import LLMRequest
from app.repositories.goal_criterion import (
    GoalAssessmentRepository,
    GoalCriterionRepository,
)
from app.services.base import BaseService
from app.services.evidence_discovery import (
    CriterionSearchContext,
    discover_evidence_bounded,
)
from app.services.llm.interface import ILLMService
from app.services.source_connections import (
    SourceConnectionError,
    get_connection_status,
)

ASSESSMENT_PROMPT_VERSION = "m66-criterion-assessment-v1"
MAX_EVIDENCE_CHARS = 6000
MAX_SOURCE_CONTENT_CHARS = 20000
MAX_REANALYSIS_GITHUB_COMMITS = 10
MAX_REANALYSIS_GITHUB_PULL_REQUEST_LOOKUPS = 5
MAX_REANALYSIS_JIRA_RESULTS = 10
MAX_REANALYSIS_CANDIDATES = 20
SOURCE_DISPLAY_NAMES = {"github": "GitHub", "jira": "Jira"}
logger = logging.getLogger(__name__)


@dataclass
class SourceRefreshResult:
    source_refreshed: bool = False
    errors: list[str] = field(default_factory=list)
    discovered_mapping_ids: set[str] = field(default_factory=set)
    mapping_ids_by_criterion: dict[str, set[str]] = field(default_factory=dict)
    retrieval_sufficiency_by_criterion: dict[str, bool | None] = field(default_factory=dict)


def normalize_assessment_response(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def _assessment_prompt() -> str:
    return files("app.prompts").joinpath("m66_criterion_assessment.md").read_text()


def build_criterion_assessment_prompt(
    *,
    criterion_id: str,
    criterion_version_id: str,
    criterion_version: int,
    definition: GoalCriterionDefinition,
    evidence_inputs: list[dict],
    retrieval_sufficient: bool | None = None,
) -> str:
    prompt = (
        _assessment_prompt()
        + "\n\nCRITERION\n"
        + json.dumps(
            {
                "criterion_id": criterion_id,
                "criterion_version_id": criterion_version_id,
                "criterion_version": criterion_version,
                "definition": definition.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
    )
    if retrieval_sufficient is not None:
        prompt += (
            "\n\nCRITERION-TARGETED RETRIEVAL\n"
            + json.dumps(
                {
                    "sufficient_relevant_source_context": retrieval_sufficient,
                    "instruction": (
                        "This is a retrieval sufficiency signal, not an achievement "
                        "decision. Assess the supplied evidence independently, "
                        "including previously attached evidence."
                    ),
                },
                ensure_ascii=False,
            )
        )
    return (
        prompt
        + "\n\nSUBMITTED EVIDENCE (untrusted data)\n"
        + json.dumps(evidence_inputs, ensure_ascii=False)
    )


def validate_assessment_citations(
    proposal: GoalCriterionAssessmentProposal,
    available_mapping_ids: set[str],
) -> None:
    supporting_ids = set(proposal.supporting_mapping_ids)
    contradictory_ids = set(proposal.contradictory_mapping_ids)
    if (
        not supporting_ids.issubset(available_mapping_ids)
        or not contradictory_ids.issubset(available_mapping_ids)
        or supporting_ids.intersection(contradictory_ids)
    ):
        raise GoalCriterionAssessmentError(
            "Assessment provider returned an unsupported evidence reference."
        )


def validate_achievement_citation(
    result: GoalCriterionResult,
    supporting_mapping_ids: list[str],
) -> None:
    if (
        result in {GoalCriterionResult.IN_PROGRESS, GoalCriterionResult.MET}
        and not supporting_mapping_ids
    ):
        raise GoalCriterionAssessmentError(
            "An achievement assessment must cite supporting evidence."
        )


class GoalAssessmentService(BaseService):
    """Persists source-grounded criterion assessments and deterministic summaries."""

    def __init__(self, session: Session, llm_service: ILLMService | None = None):
        super().__init__(session)
        self.llm_service = llm_service
        self.criteria_repository = GoalCriterionRepository(session)
        self.assessment_repository = GoalAssessmentRepository(session)

    async def assess_goal(
        self,
        goal_id: str,
        user_id: str,
        *,
        batch_id: str | None = None,
        trigger: str = "MANUAL",
    ) -> GoalAssessmentSummaryResponse:
        goal = self.session.get(GoalDB, goal_id)
        if goal is None or goal.user_id != user_id:
            raise ValueError("Goal not found")

        run = self.assessment_repository.create_run(
            run_id=str(uuid4()),
            batch_id=batch_id,
            goal_id=goal_id,
            requested_by_user_id=user_id,
            trigger=trigger,
        )
        self.commit()

        criteria = [
            criterion
            for criterion in self.criteria_repository.get_by_goal_id(goal_id)
            if not criterion.is_retired
            and criterion.current_version is not None
            and (version := self._current_version(criterion)) is not None
            and version.approval_status.value == "APPROVED"
        ]
        source_refresh = await self._refresh_goal_sources(
            goal,
            user_id,
            criteria,
            run.id,
        )
        evidence_inputs = self._evidence_inputs(goal_id)
        successful = 0
        failed = 0

        for criterion in criteria:
            version = self._current_version(criterion)
            if version is None or not evidence_inputs:
                continue
            criterion_mapping_ids = source_refresh.mapping_ids_by_criterion.get(
                criterion.id,
                set(),
            )
            criterion_evidence = [
                item
                for item in evidence_inputs
                if item["mapping_id"] not in source_refresh.discovered_mapping_ids
                or item["mapping_id"] in criterion_mapping_ids
            ]
            try:
                assessment = await self._assess_criterion(
                    run=run,
                    goal=goal,
                    criterion=criterion,
                    version=version,
                    evidence_inputs=criterion_evidence,
                    fingerprint_inputs=evidence_inputs,
                    retrieval_sufficient=source_refresh.retrieval_sufficiency_by_criterion.get(
                        criterion.id
                    ),
                )
                self.assessment_repository.create_assessment(assessment)
                self._record_event(
                    assessment.id,
                    "LIFECYCLE_CHANGED",
                    GoalAssessmentLifecycle.CURRENT,
                    None,
                    {"reason": "Initial assessment"},
                )
                successful += 1
            except GoalCriterionAssessmentError:
                failed += 1

        messages = source_refresh.errors
        if failed:
            messages.append(
                f"{failed} criterion assessment(s) failed validation or provider execution."
            )
        if messages and (successful or source_refresh.source_refreshed):
            run_status = GoalAssessmentRunStatus.PARTIAL
        elif messages:
            run_status = GoalAssessmentRunStatus.FAILED
        else:
            run_status = GoalAssessmentRunStatus.COMPLETED
        message = "; ".join(messages)[:2000] if messages else None
        self.assessment_repository.finish_run(run, run_status, message)
        self.commit()
        return self.get_summary(goal_id)

    async def _refresh_goal_sources(
        self,
        goal: GoalDB,
        user_id: str,
        criteria: list[GoalCriterionDB],
        run_id: str,
    ) -> SourceRefreshResult:
        result = SourceRefreshResult(
            mapping_ids_by_criterion={criterion.id: set() for criterion in criteria},
            retrieval_sufficiency_by_criterion={
                criterion.id: None for criterion in criteria
            },
        )
        criterion_contexts: list[CriterionSearchContext] = []
        for criterion in criteria:
            version = self._current_version(criterion)
            if version is None:
                continue
            definition = GoalCriterionDefinition.model_validate(version.definition)
            search_text = " ".join(
                text.strip()
                for text in [
                    definition.description,
                    definition.completion_conditions or "",
                    definition.unit or "",
                    *(milestone.title for milestone in definition.milestones),
                    *(milestone.completion_conditions for milestone in definition.milestones),
                    *definition.evidence_suggestions,
                ]
                if text.strip()
            )
            criterion_contexts.append(
                {
                    "criterion_id": criterion.id,
                    "definition": definition.model_dump(mode="json"),
                    "search_text": search_text,
                }
            )

        today = datetime.now(UTC).date()
        end_date = min(goal.end_date or today, today)
        start_date = goal.start_date or (end_date - timedelta(days=365))
        if start_date > end_date:
            return result
        if (end_date - start_date).days > 365:
            start_date = end_date - timedelta(days=365)

        mapped_source_types = {
            source_type.value
            for (source_type,) in (
                self.session.query(EvidenceDB.source_type)
                .join(EvidenceMappingDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
                .filter(
                    EvidenceMappingDB.goal_id == goal.id,
                    EvidenceDB.status == EvidenceStatus.ACTIVE,
                )
                .distinct()
                .all()
            )
        }
        snapshot_dates = self._source_snapshot_dates(goal.id)
        try:
            connections = get_connection_status(self.session, user_id)
        except SourceConnectionError as exc:
            logger.warning("Unable to check evidence connections for goal %s: %s", goal.id, exc)
            message = f"Could not check connected sources: {exc}"
            result.errors.append(message)
            for provider in ("github", "jira"):
                snapshot_date = snapshot_dates.get(provider)
                if provider in mapped_source_types:
                    self._record_source_retrieval(
                        goal.id,
                        run_id,
                        provider,
                        GoalSourceRetrievalStatus.FAILURE,
                        message,
                        snapshot_date,
                    )
            return result

        connected = {
            item["provider"]
            for item in connections
            if item.get("connected") and item.get("provider") in {"github", "jira"}
        }
        fetch_states = {
            state.provider: state
            for state in self.session.query(GoalSourceFetchStateDB)
            .filter(GoalSourceFetchStateDB.goal_id == goal.id)
            .all()
        }
        provider_sufficiency: list[dict[str, bool]] = []
        for provider in ("github", "jira"):
            if provider in mapped_source_types and provider not in connected:
                message = (
                    f"{SOURCE_DISPLAY_NAMES[provider]} is not connected; "
                    "assessment uses stored evidence snapshots."
                )
                result.errors.append(message)
                self._record_source_retrieval(
                    goal.id,
                    run_id,
                    provider,
                    GoalSourceRetrievalStatus.FAILURE,
                    message,
                    snapshot_dates.get(provider),
                )
        related_jira_keys: set[str] = set()
        for provider in ("github", "jira"):
            if provider not in connected:
                continue
            state = fetch_states.get(provider)
            provider_start_date = start_date
            after = None
            if state is not None:
                watermark = state.last_successful_fetch_at
                if watermark.tzinfo is None:
                    watermark = watermark.replace(tzinfo=UTC)
                else:
                    watermark = watermark.astimezone(UTC)
                after = watermark
                provider_start_date = max(
                    start_date,
                    watermark.date() - timedelta(days=1),
                )
            if provider_start_date > end_date:
                continue
            fetch_started_at = datetime.now(UTC)
            try:
                discovered = await discover_evidence_bounded(
                    self.session,
                    user_id,
                    goal.title,
                    goal.description,
                    None,
                    None,
                    provider_start_date,
                    end_date,
                    [provider],
                    jira_keys=related_jira_keys,
                    max_github_commits=MAX_REANALYSIS_GITHUB_COMMITS,
                    max_github_pull_request_lookups=MAX_REANALYSIS_GITHUB_PULL_REQUEST_LOOKUPS,
                    max_jira_results=MAX_REANALYSIS_JIRA_RESULTS,
                    max_candidates=MAX_REANALYSIS_CANDIDATES,
                    after=after,
                    criteria=criterion_contexts,
                )
            except SourceConnectionError as exc:
                message = f"{SOURCE_DISPLAY_NAMES[provider]} evidence refresh failed: {exc}"
                logger.warning("Evidence refresh failed for goal %s: %s", goal.id, message)
                result.errors.append(message)
                self._record_source_retrieval(
                    goal.id,
                    run_id,
                    provider,
                    GoalSourceRetrievalStatus.FAILURE,
                    message,
                    snapshot_dates.get(provider),
                )
                continue

            self._record_source_retrieval(
                goal.id,
                run_id,
                provider,
                GoalSourceRetrievalStatus.SUCCESS,
            )
            result.source_refreshed = True
            if criterion_contexts:
                provider_result = (
                    discovered[0].get("criterion_sufficiency")
                    if discovered
                    else {}
                )
                if not isinstance(provider_result, dict):
                    raise ValueError(
                        "Criterion retrieval must return sufficiency for each approved criterion."
                    )
                provider_sufficiency.append(
                    {
                        criterion["criterion_id"]: provider_result.get(
                            criterion["criterion_id"], False
                        )
                        is True
                        for criterion in criterion_contexts
                    }
                )
            for candidate in discovered:
                criterion_ids = candidate.get("criterion_ids", [])
                if criterion_contexts and (
                    not isinstance(criterion_ids, list)
                    or any(
                        criterion_id not in result.mapping_ids_by_criterion
                        for criterion_id in criterion_ids
                    )
                ):
                    raise ValueError(
                        "Discovered evidence referenced an unknown goal criterion."
                    )
                mapping_id = self._persist_discovered_evidence(goal, user_id, candidate)
                if mapping_id is not None and criterion_contexts:
                    result.discovered_mapping_ids.add(mapping_id)
                    for criterion_id in criterion_ids:
                        result.mapping_ids_by_criterion[criterion_id].add(mapping_id)
            if state is None:
                state = GoalSourceFetchStateDB(
                    goal_id=goal.id,
                    provider=provider,
                    last_successful_fetch_at=fetch_started_at,
                    updated_at=fetch_started_at,
                )
                self.session.add(state)
                fetch_states[provider] = state
            else:
                state.last_successful_fetch_at = fetch_started_at
                state.updated_at = fetch_started_at
            self.session.flush()
            if provider == "github":
                related_jira_keys = {
                    key
                    for candidate in discovered
                    for key in candidate.get("jira_keys", [])
                    if isinstance(key, str)
                }

        if provider_sufficiency and not result.errors:
            for criterion_id in result.retrieval_sufficiency_by_criterion:
                result.retrieval_sufficiency_by_criterion[criterion_id] = any(
                    provider[criterion_id] for provider in provider_sufficiency
                )
        return result

    def _source_snapshot_dates(self, goal_id: str) -> dict[str, datetime]:
        rows = (
            self.session.query(EvidenceDB.source_type, EvidenceDB.captured_at)
            .join(EvidenceMappingDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
            .filter(
                EvidenceMappingDB.goal_id == goal_id,
                EvidenceDB.status == EvidenceStatus.ACTIVE,
                EvidenceDB.source_type.in_(
                    [EvidenceSourceType.GITHUB, EvidenceSourceType.JIRA]
                ),
            )
            .order_by(EvidenceDB.captured_at.desc())
            .all()
        )
        snapshot_dates: dict[str, datetime] = {}
        for source_type, captured_at in rows:
            snapshot_dates.setdefault(source_type.value, captured_at)
        return snapshot_dates

    def _record_source_retrieval(
        self,
        goal_id: str,
        run_id: str,
        provider: str,
        status: GoalSourceRetrievalStatus,
        failure_reason: str | None = None,
        snapshot_captured_at: datetime | None = None,
    ) -> None:
        self.session.add(
            GoalSourceRetrievalDB(
                id=str(uuid4()),
                goal_id=goal_id,
                run_id=run_id,
                provider=provider,
                status=status.value,
                checked_at=datetime.now(UTC),
                failure_reason=failure_reason,
                used_snapshot=status == GoalSourceRetrievalStatus.FAILURE
                and snapshot_captured_at is not None,
                snapshot_captured_at=(
                    snapshot_captured_at
                    if status == GoalSourceRetrievalStatus.FAILURE
                    else None
                ),
            )
        )

    def _persist_discovered_evidence(
        self,
        goal: GoalDB,
        user_id: str,
        candidate: dict,
    ) -> str | None:
        source_id = candidate["source_id"]
        captured_at = candidate["captured_at"]
        source_updated_at = candidate.get("source_updated_at")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("Discovered evidence must have a source identifier.")
        if not isinstance(captured_at, datetime):
            raise ValueError("Discovered evidence must have a capture timestamp.")
        if source_updated_at is not None and not isinstance(source_updated_at, datetime):
            raise ValueError("Discovered evidence has an invalid source update timestamp.")

        source_type = EvidenceSourceType(candidate["source_type"])
        title = str(candidate["title"]).strip()[:500]
        summary = str(candidate["summary"]).strip()
        source_content = str(candidate.get("description") or summary)
        if not title or not summary:
            raise ValueError("Discovered evidence must have a title and summary.")
        source_url = candidate.get("source_url")
        if source_url is not None:
            source_url = str(source_url)[:2000]
        content_hash = hashlib.sha256(source_content.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)

        evidence = (
            self.session.query(EvidenceDB)
            .filter(
                EvidenceDB.user_id == user_id,
                EvidenceDB.source_type == source_type,
                EvidenceDB.source_id == source_id,
            )
            .order_by(EvidenceDB.created_at.desc())
            .first()
        )
        if evidence is not None and evidence.status != EvidenceStatus.ACTIVE:
            return None
        if evidence is None:
            evidence = EvidenceDB(
                id=str(uuid4()),
                user_id=user_id,
                source_type=source_type,
                source_id=source_id,
                title=title,
                description=summary,
                source_url=source_url,
                captured_at=captured_at,
                source_updated_at=source_updated_at,
                content_hash=content_hash,
                status=EvidenceStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            self.session.add(evidence)
            self.session.flush()
        else:
            evidence.title = title
            evidence.description = summary
            evidence.source_url = source_url
            evidence.captured_at = captured_at
            evidence.source_updated_at = source_updated_at
            evidence.content_hash = content_hash
            evidence.updated_at = now

        latest_version = (
            self.session.query(EvidenceVersionDB)
            .filter(EvidenceVersionDB.evidence_id == evidence.id)
            .order_by(EvidenceVersionDB.version.desc())
            .first()
        )
        if latest_version is None or latest_version.content_hash != content_hash:
            self.session.add(
                EvidenceVersionDB(
                    id=str(uuid4()),
                    evidence_id=evidence.id,
                    version=latest_version.version + 1 if latest_version else 1,
                    content=source_content[:MAX_SOURCE_CONTENT_CHARS],
                    content_hash=content_hash,
                    source_updated_at=source_updated_at,
                    captured_at=captured_at,
                    created_at=now,
                )
            )
            self.session.flush()

        mapping = (
            self.session.query(EvidenceMappingDB)
            .filter(
                EvidenceMappingDB.evidence_id == evidence.id,
                EvidenceMappingDB.goal_id == goal.id,
            )
            .first()
        )
        if mapping is None:
            mapping = EvidenceMappingDB(
                id=str(uuid4()),
                evidence_id=evidence.id,
                goal_id=goal.id,
                milestone_id=None,
                relevance=EvidenceRelevance(candidate["relevance"]),
                reason=f"Discovered from connected {source_type.value} source during reanalysis.",
                confidence=1.0,
                created_at=now,
                updated_at=now,
            )
            self.session.add(mapping)
            self.session.flush()
            self.session.add(
                EvidenceApprovalDB(
                    id=str(uuid4()),
                    mapping_id=mapping.id,
                    status=EvidenceApprovalStatus.PENDING,
                    created_at=now,
                )
            )
        return mapping.id

    async def assess_goals(
        self,
        goal_ids: list[str],
        user_id: str,
    ) -> GoalAssessmentBatchResponse:
        goals = [self.session.get(GoalDB, goal_id) for goal_id in goal_ids]
        if any(goal is None or goal.user_id != user_id for goal in goals):
            raise ValueError("One or more goals were not found")

        batch_id = str(uuid4())
        run_responses: list[GoalAssessmentRunResponse] = []
        for goal_id in goal_ids:
            await self.assess_goal(
                goal_id,
                user_id,
                batch_id=batch_id,
                trigger="ANALYZE_GOALS",
            )
            run = (
                self.session.query(GoalAssessmentRunDB)
                .filter(
                    GoalAssessmentRunDB.goal_id == goal_id,
                    GoalAssessmentRunDB.batch_id == batch_id,
                )
                .order_by(GoalAssessmentRunDB.created_at.desc())
                .first()
            )
            if run is not None:
                run_responses.append(GoalAssessmentRunResponse.model_validate(run, from_attributes=True))
        return GoalAssessmentBatchResponse(batch_id=batch_id, runs=run_responses)

    def get_summary(self, goal_id: str) -> GoalAssessmentSummaryResponse:
        criteria = [
            criterion
            for criterion in self.criteria_repository.get_by_goal_id(goal_id)
            if not criterion.is_retired
            and criterion.current_version is not None
            and (version := self._current_version(criterion)) is not None
            and version.approval_status.value == "APPROVED"
        ]
        goal = self.session.get(GoalDB, goal_id)
        evidence_inputs = self._evidence_inputs(goal_id)
        all_assessments = self.assessment_repository.get_assessments_by_goal_id(goal_id)
        assessment_by_criterion: dict[str, GoalCriterionAssessmentDB] = {}
        for assessment in all_assessments:
            criterion = next(
                (item for item in criteria if item.id == assessment.criterion_id),
                None,
            )
            version = self._current_version(criterion) if criterion is not None else None
            if version is None or assessment.criterion_version_id != version.id:
                continue
            if assessment.criterion_id not in assessment_by_criterion:
                assessment_by_criterion[assessment.criterion_id] = assessment

        summaries: list[GoalCriterionSummary] = []
        current_assessments: list[GoalCriterionAssessmentDB] = []
        covered_criteria = 0
        for criterion in criteria:
            version = self._current_version(criterion)
            assessment = assessment_by_criterion.get(criterion.id)
            if version is None:
                continue
            if assessment is not None:
                fingerprint = self._fingerprint(version, evidence_inputs, goal)
                if (
                    assessment.lifecycle_state == GoalAssessmentLifecycle.CURRENT
                    and assessment.input_fingerprint != fingerprint
                ):
                    self._change_lifecycle(
                        assessment,
                        GoalAssessmentLifecycle.STALE,
                        "Assessment inputs changed",
                    )
                if assessment.lifecycle_state == GoalAssessmentLifecycle.CURRENT:
                    current_assessments.append(assessment)
                    if any(
                        item.relationship_type in {"SUPPORTING", "CONTRADICTORY"}
                        for item in assessment.evidence
                    ):
                        covered_criteria += 1
                summaries.append(
                    GoalCriterionSummary(
                        criterion_id=criterion.id,
                        criterion_version=version.version,
                        result=assessment.result,
                        lifecycle_state=assessment.lifecycle_state,
                        progress_percentage=assessment.progress_percentage,
                        assessment=self._assessment_response(assessment),
                    )
                )
            else:
                summaries.append(
                    GoalCriterionSummary(
                        criterion_id=criterion.id,
                        criterion_version=version.version,
                        result=GoalCriterionResult.NOT_ASSESSED,
                        lifecycle_state=None,
                        progress_percentage=None,
                        assessment=None,
                    )
                )

        if self.session.new or self.session.dirty:
            self.commit()

        criterion_count = len(criteria)
        assessed_count = len(current_assessments)
        met_count = sum(
            assessment.result == GoalCriterionResult.MET
            for assessment in current_assessments
        )
        progress_values = [item.progress_percentage for item in current_assessments]
        goal_progress = (
            round(sum(value for value in progress_values if value is not None) / criterion_count)
            if criterion_count
            and assessed_count == criterion_count
            and all(value is not None for value in progress_values)
            else None
        )
        latest_run = self.assessment_repository.get_latest_run_by_goal_id(goal_id)
        retrieval_history = (
            self.session.query(GoalSourceRetrievalDB)
            .filter(GoalSourceRetrievalDB.goal_id == goal_id)
            .order_by(GoalSourceRetrievalDB.checked_at.desc())
            .limit(20)
            .all()
        )
        return GoalAssessmentSummaryResponse(
            goal_id=goal_id,
            run_id=latest_run.id if latest_run else None,
            run_status=latest_run.status if latest_run else None,
            run_error_message=latest_run.error_message if latest_run else None,
            criteria_count=criterion_count,
            assessed_criteria_count=assessed_count,
            criteria_met_count=met_count,
            criteria_met_percentage=round(met_count * 100 / criterion_count) if criterion_count else None,
            goal_progress_percentage=goal_progress,
            evidence_coverage_percentage=round(covered_criteria * 100 / criterion_count)
            if criterion_count
            else None,
            average_confidence=round(
                sum(item.confidence for item in current_assessments) / assessed_count,
                3,
            )
            if assessed_count
            else None,
            criteria=summaries,
            source_retrieval_history=[
                GoalSourceRetrievalResponse.model_validate(item, from_attributes=True)
                for item in retrieval_history
            ],
            updated_at=max(
                (item.created_at for item in current_assessments),
                default=None,
            ),
        )

    def add_feedback(
        self,
        goal_id: str,
        criterion_id: str,
        assessment_id: str,
        user_id: str,
        feedback_type,
        corrected_result: GoalCriterionResult | None,
        comment: str | None,
    ) -> GoalCriterionAssessmentDB:
        goal = self.session.get(GoalDB, goal_id)
        assessment = self.assessment_repository.get_assessment(assessment_id)
        if (
            goal is None
            or goal.user_id != user_id
            or assessment is None
            or assessment.criterion_id != criterion_id
            or assessment.criterion.goal_id != goal_id
        ):
            raise ValueError("Assessment not found")
        details = {"corrected_result": corrected_result.value if corrected_result else None}
        if comment:
            details["comment"] = comment.strip()
        self._record_event(
            assessment.id,
            feedback_type.value,
            None,
            user_id,
            details,
        )
        self.commit()
        return self.assessment_repository.get_assessment(assessment_id)

    async def _assess_criterion(
        self,
        *,
        run: GoalAssessmentRunDB,
        goal: GoalDB,
        criterion: GoalCriterionDB,
        version: GoalCriterionVersionDB,
        evidence_inputs: list[dict],
        fingerprint_inputs: list[dict] | None = None,
        retrieval_sufficient: bool | None = None,
    ) -> GoalCriterionAssessmentDB:
        if self.llm_service is None:
            raise GoalCriterionAssessmentError("Criterion assessment is not configured.")
        mapping_ids = {item["mapping_id"] for item in evidence_inputs}
        definition = GoalCriterionDefinition.model_validate(version.definition)
        prompt = build_criterion_assessment_prompt(
            criterion_id=criterion.id,
            criterion_version_id=version.id,
            criterion_version=version.version,
            definition=definition,
            evidence_inputs=evidence_inputs,
            retrieval_sufficient=retrieval_sufficient,
        )
        try:
            response = await self.llm_service.generate(
                LLMRequest(prompt=prompt, response_format={"type": "json_object"})
            )
        except Exception as exc:
            raise GoalCriterionAssessmentError("Assessment provider failed.") from exc
        try:
            proposal = GoalCriterionAssessmentProposal.model_validate_json(
                normalize_assessment_response(response.content)
            )
        except ValidationError as exc:
            raise GoalCriterionAssessmentError(
                "Assessment provider returned an invalid response."
            ) from exc

        validate_assessment_citations(proposal, mapping_ids)
        supporting_ids = set(proposal.supporting_mapping_ids)
        contradictory_ids = set(proposal.contradictory_mapping_ids)
        if proposal.result == GoalCriterionResult.MET and not supporting_ids:
            raise GoalCriterionAssessmentError(
                "A MET assessment must cite supporting evidence."
            )

        result, progress = self._calculate_progress(definition, proposal)
        validate_achievement_citation(result, proposal.supporting_mapping_ids)
        fingerprint = self._fingerprint(
            version,
            fingerprint_inputs if fingerprint_inputs is not None else evidence_inputs,
            goal,
        )
        self._obsolete_previous_assessments(criterion.id)
        assessment = GoalCriterionAssessmentDB(
            id=str(uuid4()),
            run_id=run.id,
            criterion_id=criterion.id,
            criterion_version_id=version.id,
            result=result,
            lifecycle_state=GoalAssessmentLifecycle.CURRENT,
            progress_percentage=progress,
            rationale=proposal.rationale,
            confidence=proposal.confidence,
            measured_value=proposal.measured_value,
            completed_milestone_ids=proposal.completed_milestone_ids,
            input_fingerprint=fingerprint,
            model_version=response.model,
            prompt_version=ASSESSMENT_PROMPT_VERSION,
            created_at=datetime.now(UTC),
        )
        self.session.flush()
        assessment.evidence = []
        for evidence in evidence_inputs:
            mapping_id = evidence["mapping_id"]
            relationship_type = (
                "SUPPORTING"
                if mapping_id in supporting_ids
                else "CONTRADICTORY"
                if mapping_id in contradictory_ids
                else "CONSIDERED"
            )
            assessment.evidence.append(
                GoalCriterionAssessmentEvidenceDB(
                    id=str(uuid4()),
                    evidence_mapping_id=mapping_id,
                    evidence_version_id=evidence["evidence_version_id"],
                    review_state=evidence["review_state"],
                    source_validity=evidence["source_validity"],
                    relationship_type=relationship_type,
                    title_snapshot=evidence["title"],
                    source_url_snapshot=evidence["source_url"],
                    captured_at_snapshot=datetime.fromisoformat(evidence["captured_at"]),
                    source_updated_at_snapshot=(
                        datetime.fromisoformat(evidence["source_updated_at"])
                        if evidence["source_updated_at"]
                        else None
                    ),
                    citation_excerpt=evidence["content"][:2000] or None,
                    created_at=datetime.now(UTC),
                )
            )
        return assessment

    @staticmethod
    def _calculate_progress(
        definition: GoalCriterionDefinition,
        proposal: GoalCriterionAssessmentProposal,
    ) -> tuple[GoalCriterionResult, int | None]:
        if proposal.result == GoalCriterionResult.NEEDS_REVIEW:
            return GoalCriterionResult.NEEDS_REVIEW, None
        if definition.criterion_type == GoalCriterionType.BINARY:
            return (
                proposal.result,
                100 if proposal.result == GoalCriterionResult.MET else 0,
            )
        if definition.criterion_type == GoalCriterionType.MILESTONE_BASED:
            expected = {milestone.id for milestone in definition.milestones}
            completed = set(proposal.completed_milestone_ids)
            if len(completed) != len(proposal.completed_milestone_ids) or not completed.issubset(expected):
                raise GoalCriterionAssessmentError(
                    "Assessment provider returned an unsupported milestone reference."
                )
            progress = round(len(completed) * 100 / len(expected))
            if progress == 100:
                return GoalCriterionResult.MET, progress
            if progress > 0:
                return GoalCriterionResult.IN_PROGRESS, progress
            if proposal.result == GoalCriterionResult.NOT_STARTED:
                return GoalCriterionResult.NOT_STARTED, 0
            return GoalCriterionResult.NEEDS_REVIEW, None
        if proposal.measured_value is None or proposal.measured_value < 0:
            if proposal.result == GoalCriterionResult.NEEDS_REVIEW:
                return GoalCriterionResult.NEEDS_REVIEW, None
            raise GoalCriterionAssessmentError(
                "A measurable-target assessment requires a cited measured value."
            )
        progress = min(
            100,
            round(proposal.measured_value * 100 / definition.target_value),
        )
        if progress == 100:
            return GoalCriterionResult.MET, progress
        if progress > 0:
            return GoalCriterionResult.IN_PROGRESS, progress
        if proposal.result == GoalCriterionResult.NOT_STARTED:
            return GoalCriterionResult.NOT_STARTED, 0
        return GoalCriterionResult.NEEDS_REVIEW, None

    def _evidence_inputs(self, goal_id: str) -> list[dict]:
        mappings = (
            self.session.query(EvidenceMappingDB)
            .options(
                joinedload(EvidenceMappingDB.evidence).selectinload(EvidenceDB.versions)
            )
            .join(EvidenceDB, EvidenceDB.id == EvidenceMappingDB.evidence_id)
            .filter(
                EvidenceMappingDB.goal_id == goal_id,
                EvidenceDB.status == EvidenceStatus.ACTIVE,
            )
            .all()
        )
        if not mappings:
            return []
        approvals = {
            approval.mapping_id: approval.status.value
            for approval in self.session.query(EvidenceApprovalDB)
            .filter(
                EvidenceApprovalDB.mapping_id.in_(
                    [mapping.id for mapping in mappings]
                )
            )
            .all()
        }
        result: list[dict] = []
        for mapping in mappings:
            evidence = mapping.evidence
            latest_version = max(evidence.versions, key=lambda item: item.version, default=None)
            content = (
                latest_version.content
                if latest_version is not None
                else evidence.description or mapping.reason or ""
            )
            content_hash = (
                latest_version.content_hash
                if latest_version is not None
                else evidence.content_hash
            ) or hashlib.sha256(content.encode("utf-8")).hexdigest()
            source_validity = (
                "STORED_SNAPSHOT"
                if content.strip()
                else "METADATA_ONLY"
            )
            result.append(
                {
                    "mapping_id": mapping.id,
                    "evidence_id": evidence.id,
                    "evidence_version_id": latest_version.id if latest_version else None,
                    "source_type": evidence.source_type.value,
                    "title": evidence.title,
                    "source_url": evidence.source_url,
                    "captured_at": evidence.captured_at.isoformat(),
                    "source_updated_at": (
                        evidence.source_updated_at.isoformat()
                        if evidence.source_updated_at
                        else None
                    ),
                    "content_hash": content_hash,
                    "review_state": approvals.get(mapping.id, "pending"),
                    "source_validity": source_validity,
                    "content": content[:MAX_EVIDENCE_CHARS],
                }
            )
        return result

    @staticmethod
    def _fingerprint(
        version: GoalCriterionVersionDB,
        evidence_inputs: list[dict],
        goal: GoalDB | None,
    ) -> str:
        data = {
            "goal": (
                {
                    "id": goal.id,
                    "title": goal.title,
                    "description": goal.description,
                    "scope": goal.scope.value,
                    "start_date": goal.start_date.isoformat() if goal.start_date else None,
                    "end_date": goal.end_date.isoformat() if goal.end_date else None,
                }
                if goal is not None
                else None
            ),
            "criterion_version_id": version.id,
            "definition": version.definition,
            "evidence": [
                {
                    "mapping_id": item["mapping_id"],
                    "version_id": item["evidence_version_id"],
                    "content_hash": item["content_hash"],
                    "source_updated_at": item["source_updated_at"],
                    "review_state": item["review_state"],
                    "source_validity": item["source_validity"],
                    "source_type": item["source_type"],
                    "source_url": item["source_url"],
                    "title": item["title"],
                }
                for item in sorted(evidence_inputs, key=lambda value: value["mapping_id"])
            ],
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _obsolete_previous_assessments(self, criterion_id: str) -> None:
        previous = (
            self.session.query(GoalCriterionAssessmentDB)
            .filter(
                GoalCriterionAssessmentDB.criterion_id == criterion_id,
                GoalCriterionAssessmentDB.lifecycle_state == GoalAssessmentLifecycle.CURRENT,
            )
            .all()
        )
        for item in previous:
            self._change_lifecycle(
                item,
                GoalAssessmentLifecycle.OBSOLETE,
                "Superseded by a newer assessment",
            )

    def _change_lifecycle(
        self,
        assessment: GoalCriterionAssessmentDB,
        lifecycle: GoalAssessmentLifecycle,
        reason: str,
    ) -> None:
        if assessment.lifecycle_state == lifecycle:
            return
        assessment.lifecycle_state = lifecycle
        assessment.invalidation_reason = reason
        self._record_event(
            assessment.id,
            "LIFECYCLE_CHANGED",
            lifecycle,
            None,
            {"reason": reason},
        )

    def _record_event(
        self,
        assessment_id: str,
        event_type: str,
        lifecycle_state: GoalAssessmentLifecycle | None,
        actor_user_id: str | None,
        details: dict,
    ) -> None:
        self.assessment_repository.add_event(
            GoalCriterionAssessmentEventDB(
                id=str(uuid4()),
                assessment_id=assessment_id,
                event_type=event_type,
                lifecycle_state=lifecycle_state,
                actor_user_id=actor_user_id,
                details=details,
                created_at=datetime.now(UTC),
            )
        )

    def _assessment_response(
        self,
        assessment: GoalCriterionAssessmentDB,
    ) -> GoalCriterionAssessmentResponse:
        evidence_responses = []
        for item in assessment.evidence:
            mapping = item.evidence_mapping
            evidence = mapping.evidence
            evidence_responses.append(
                GoalCriterionEvidenceResponse(
                    id=item.id,
                    evidence_mapping_id=mapping.id,
                    evidence_id=evidence.id,
                    title=item.title_snapshot,
                    source_url=item.source_url_snapshot,
                    captured_at=item.captured_at_snapshot,
                    source_updated_at=item.source_updated_at_snapshot,
                    review_state=item.review_state,
                    source_validity=item.source_validity,
                    relationship_type=item.relationship_type,
                    citation_excerpt=item.citation_excerpt,
                )
            )
        event_responses = [
            GoalCriterionAssessmentEventResponse.model_validate(event, from_attributes=True)
            for event in assessment.events
        ]
        return GoalCriterionAssessmentResponse(
            id=assessment.id,
            run_id=assessment.run_id,
            criterion_id=assessment.criterion_id,
            criterion_version_id=assessment.criterion_version_id,
            criterion_version=assessment.criterion_version.version,
            result=assessment.result,
            lifecycle_state=assessment.lifecycle_state,
            progress_percentage=assessment.progress_percentage,
            rationale=assessment.rationale,
            confidence=assessment.confidence,
            input_fingerprint=assessment.input_fingerprint,
            model_version=assessment.model_version,
            prompt_version=assessment.prompt_version,
            created_at=assessment.created_at,
            evidence=evidence_responses,
            events=event_responses,
        )

    @staticmethod
    def _current_version(criterion: GoalCriterionDB | None) -> GoalCriterionVersionDB | None:
        if criterion is None or criterion.current_version is None:
            return None
        return next(
            (item for item in criterion.versions if item.version == criterion.current_version),
            None,
        )
