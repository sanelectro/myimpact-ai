from sqlalchemy import String, cast, literal, select, text
from sqlalchemy.dialects.postgresql import ARRAY, array
from sqlalchemy.orm import Session, aliased

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_approval import EvidenceApprovalDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.goal import GoalDB
from app.models.evidence import EvidenceStatus
from app.services.goal_hierarchy import GoalHierarchyNotFound


MAX_CONTEXT_GOALS = 1000


class GoalEvidenceContextService:
    def __init__(self, session: Session):
        self.session = session

    def get_context(
        self, goal_id: str, user_id: str, *, limit: int, offset: int, max_depth: int
    ) -> dict:
        self.session.execute(text("SELECT pg_advisory_xact_lock(1296650324, 1)"))
        root = self.session.scalar(
            select(GoalDB.id).where(GoalDB.id == goal_id, GoalDB.user_id == user_id)
        )
        if root is None:
            raise GoalHierarchyNotFound("Goal not found")

        tree = select(
            GoalDB.id.label("goal_id"),
            cast(array([GoalDB.id], type_=String), ARRAY(String)).label("path"),
            literal(0).label("depth"),
        ).where(GoalDB.id == goal_id, GoalDB.user_id == user_id).cte("goal_tree", recursive=True)
        child = aliased(GoalDB)
        tree = tree.union_all(
            select(child.id, tree.c.path + array([child.id], type_=String), tree.c.depth + 1)
            .join(tree, child.parent_goal_id == tree.c.goal_id)
            .where(child.user_id == user_id, tree.c.depth < max_depth)
        )
        tree_rows = self.session.execute(
            select(tree.c.goal_id, tree.c.path, tree.c.depth).limit(MAX_CONTEXT_GOALS + 1)
        ).all()
        truncated = len(tree_rows) > MAX_CONTEXT_GOALS
        tree_rows = tree_rows[:MAX_CONTEXT_GOALS]
        paths = {row.goal_id: row.path for row in tree_rows}
        boundary_ids = [row.goal_id for row in tree_rows if row.depth == max_depth]
        if boundary_ids:
            truncated = truncated or bool(self.session.scalar(
                select(
                    select(GoalDB.id).where(
                        GoalDB.parent_goal_id.in_(boundary_ids),
                        GoalDB.user_id == user_id,
                    ).exists()
                )
            ))
        evidence_ids = list(self.session.scalars(
            select(EvidenceDB.id)
            .join(EvidenceMappingDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
            .where(
                EvidenceMappingDB.goal_id.in_(list(paths)),
                EvidenceDB.user_id == user_id,
                EvidenceDB.status == EvidenceStatus.ACTIVE,
            )
            .distinct()
            .order_by(EvidenceDB.id)
            .limit(limit + 1)
            .offset(offset)
        ))
        has_more = len(evidence_ids) > limit
        evidence_ids = evidence_ids[:limit]
        rows = self.session.execute(
            select(EvidenceDB, EvidenceMappingDB, EvidenceApprovalDB)
            .join(EvidenceMappingDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
            .outerjoin(EvidenceApprovalDB, EvidenceApprovalDB.mapping_id == EvidenceMappingDB.id)
            .where(
                EvidenceDB.id.in_(evidence_ids),
                EvidenceMappingDB.goal_id.in_(list(paths)),
                EvidenceDB.user_id == user_id,
                EvidenceDB.status == EvidenceStatus.ACTIVE,
            )
            .order_by(EvidenceDB.id, EvidenceMappingDB.goal_id, EvidenceMappingDB.id)
        )
        items = {}
        for evidence, mapping, approval in rows:
            item = items.setdefault(evidence.id, {
                "evidence_id": evidence.id,
                "title": evidence.title,
                "description": evidence.description,
                "source_type": evidence.source_type.value,
                "source_url": evidence.source_url,
                "captured_at": evidence.captured_at,
                "source_updated_at": evidence.source_updated_at,
                "origins": [],
            })
            item["origins"].append({
                "origin": "DIRECT" if mapping.goal_id == goal_id else "INHERITED",
                "source_goal_id": mapping.goal_id,
                "goal_path": paths[mapping.goal_id],
                "mapping_id": mapping.id,
                "mapping_kind": mapping.mapping_kind,
                "contribution_description": mapping.contribution_description,
                "relevance": mapping.relevance.value,
                "confidence": mapping.confidence,
                "approval_status": approval.status.value if approval else None,
            })

        return {
            "items": list(items.values()),
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
            "hierarchy_truncated": truncated,
        }
