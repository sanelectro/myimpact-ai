from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.exceptions import ImpactAssessmentEvaluationError
from app.models.api_v1_impact import ImpactAnalysisRequest, ImpactAnalysisResponse, ImpactAssessmentResponse
from app.models.goal import Goal
from app.models.document_expectation import DocumentExpectation
from app.services.document import DocumentService
from app.services.document_expectation_api import DocumentExpectationApiService
from app.services.goal import GoalService
from app.services.impact_assessment import ImpactAssessmentService
from app.services.knowledge.career_insight import CareerInsightService
from app.services.knowledge.evidence_discovery import EvidenceDiscoveryService
from app.services.knowledge.evidence_evaluation import EvidenceEvaluationService
from app.services.knowledge.evidence_persistence import EvidencePersistenceService
from app.services.knowledge.impact_assessment import ImpactAssessmentEvaluationService
from app.services.knowledge.impact_intelligence_pipeline import ImpactIntelligencePipelineService
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService
from app.services.embedding.factory import create_embedding_service
from app.services.llm.factory import create_llm_service
from app.repositories.document_chunk_embedding import DocumentChunkEmbeddingRepository
from app.api.v1.evidence import get_goal_service

router = APIRouter(prefix="/goals", tags=["goal-impact"])



def get_document_service(db: Annotated[Session, Depends(get_db)]) -> DocumentService:
    return DocumentService(db)


def get_expectation_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentExpectationApiService:
    return DocumentExpectationApiService(db)


def get_impact_assessment_service(
    db: Annotated[Session, Depends(get_db)],
) -> ImpactAssessmentService:
    return ImpactAssessmentService(db)


def get_pipeline(db: Annotated[Session, Depends(get_db)]) -> ImpactIntelligencePipelineService:
    llm_service = create_llm_service()
    retrieval = SemanticRetrievalService(
        repository=DocumentChunkEmbeddingRepository(db),
        embedding_service=create_embedding_service(),
    )
    return ImpactIntelligencePipelineService(
        discovery_service=EvidenceDiscoveryService(retrieval),
        evaluation_service=EvidenceEvaluationService(llm_service),
        persistence_service=EvidencePersistenceService(db),
        impact_evaluation_service=ImpactAssessmentEvaluationService(llm_service),
        impact_assessment_service=ImpactAssessmentService(db),
        career_insight_service=CareerInsightService(llm_service),
    )


def _require_goal(goal, user_id: str):
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.post("/{goal_id}/impact/analyze", response_model=ImpactAnalysisResponse)
async def analyze_goal_impact(
    goal_id: str,
    request: ImpactAnalysisRequest,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    expectation_service: Annotated[DocumentExpectationApiService, Depends(get_expectation_service)],
    pipeline: Annotated[ImpactIntelligencePipelineService, Depends(get_pipeline)],
) -> ImpactAnalysisResponse:
    goal_db = _require_goal(goal_service.get_goal_by_id(goal_id), user_id)

    expectations: list[DocumentExpectation] = []
    for document_id in request.document_ids:
        document = document_service.get_document_by_id(document_id)
        if document is None or document.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        expectations.extend(
            DocumentExpectation.model_validate(item, from_attributes=True)
            for item in expectation_service.get_by_document_id(document_id)
        )

    if not expectations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No expectations found for the supplied documents",
        )

    goal = Goal.model_validate(goal_db, from_attributes=True)
    try:
        result = await pipeline.run(
            goal,
            expectations,
            user_id=user_id,
            discovery_limit=request.discovery_limit,
        )
    except ImpactAssessmentEvaluationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ImpactAnalysisResponse(
        goal_id=goal.id,
        processed_expectations=result.processed_expectations,
        discovered_candidates=result.discovered_candidates,
        evaluated_candidates=result.evaluated_candidates,
        persisted_evidence_count=result.persisted_evidence_count,
        impact_assessment_count=result.impact_assessment_count,
        career_insight=result.career_insight,
    )


@router.get("/{goal_id}/impact", response_model=list[ImpactAssessmentResponse])
def get_goal_impact(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    impact_service: Annotated[ImpactAssessmentService, Depends(get_impact_assessment_service)],
) -> list[ImpactAssessmentResponse]:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    return [
        ImpactAssessmentResponse.model_validate(item, from_attributes=True)
        for item in impact_service.get_assessments_by_goal_id(goal_id)
    ]
