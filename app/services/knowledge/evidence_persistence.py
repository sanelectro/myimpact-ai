from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.exceptions import EvidencePersistenceError
from app.models.evidence import EvidenceSourceType
from app.models.evidence_mapping import EvidenceRelevance
from app.models.document_expectation import DocumentExpectation
from app.models.impact_intelligence import EvidenceCandidate, EvidenceEvaluation, EvidenceSupportLevel
from app.repositories.evidence import EvidenceRepository
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.repositories.evidence_version import EvidenceVersionRepository
from app.repositories.goal import GoalRepository
from app.services.base import BaseService


class EvidencePersistenceService(BaseService):
    """Persist supported evaluated evidence and map it to a user goal."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.evidence_repository = EvidenceRepository(session)
        self.version_repository = EvidenceVersionRepository(session)
        self.mapping_repository = EvidenceMappingRepository(session)
        self.goal_repository = GoalRepository(session)

    @staticmethod
    def _relevance(support_level: EvidenceSupportLevel) -> EvidenceRelevance:
        if support_level == EvidenceSupportLevel.STRONG:
            return EvidenceRelevance.HIGH
        return EvidenceRelevance.MEDIUM

    @staticmethod
    def _content_hash(content: str) -> str:
        return sha256(content.encode("utf-8")).hexdigest()

    def persist_evaluation(
        self,
        expectation: DocumentExpectation,
        candidate: EvidenceCandidate,
        evaluation: EvidenceEvaluation,
        *,
        user_id: str,
        goal_id: str,
    ) -> tuple[EvidenceDB, EvidenceVersionDB, EvidenceMappingDB] | None:
        """Persist a supported candidate once and return its persisted records.

        Weak, none, or explicitly unsupported evaluations are intentionally not
        persisted. Re-running the same evaluation is idempotent for the evidence
        source and goal mapping.
        """
        if candidate.expectation_id != expectation.id:
            raise EvidencePersistenceError(
                "Evidence candidate does not belong to the supplied expectation."
            )

        if evaluation.candidate_chunk_id != candidate.search_result.chunk_id:
            raise EvidencePersistenceError(
                "Evidence evaluation does not belong to the supplied candidate."
            )

        if (
            not evaluation.supports_expectation
            or evaluation.support_level not in {
                EvidenceSupportLevel.MODERATE,
                EvidenceSupportLevel.STRONG,
            }
        ):
            return None

        goal = self.goal_repository.get_by_id(goal_id)
        if goal is None:
            raise EvidencePersistenceError("Goal was not found.")
        if goal.user_id != user_id:
            raise EvidencePersistenceError("Goal does not belong to the supplied user.")

        now = datetime.now(UTC)
        content = candidate.search_result.content.strip()
        content_hash = self._content_hash(content)
        source_id = candidate.search_result.chunk_id

        try:
            evidence = self.evidence_repository.get_by_source_for_user(
                EvidenceSourceType.DOCUMENT,
                source_id,
                user_id,
            )

            if evidence is None:
                evidence = self.evidence_repository.create(
                    evidence_id=str(uuid4()),
                    user_id=user_id,
                    source_type=EvidenceSourceType.DOCUMENT,
                    source_id=source_id,
                    title=expectation.description,
                    description=content,
                    captured_at=now,
                    content_hash=content_hash,
                )

            versions = self.version_repository.get_by_evidence_id(evidence.id)
            if versions:
                version = versions[-1]
            else:
                version = self.version_repository.create(
                    version_id=str(uuid4()),
                    evidence_id=evidence.id,
                    version=1,
                    content=content,
                    content_hash=content_hash,
                    captured_at=now,
                )

            mapping = self.mapping_repository.get_by_evidence_and_goal(
                evidence.id,
                goal_id,
            )
            if mapping is None:
                mapping = self.mapping_repository.create(
                    mapping_id=str(uuid4()),
                    evidence_id=evidence.id,
                    goal_id=goal_id,
                    relevance=self._relevance(evaluation.support_level),
                    confidence=evaluation.confidence,
                    reason=evaluation.rationale,
                )

            self.commit()
            return evidence, version, mapping
        except Exception:
            self.rollback()
            raise
