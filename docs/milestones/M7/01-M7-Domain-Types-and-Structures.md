# M7.2 – Domain Types and Structures

**Target repository:** `myimpact-ai`  
**Status:** Proposed; align enum values with the approved Flyway schema before implementation.

## 1. Current code conventions

The inspected backend uses:

- `app/models/` for Pydantic domain/API-facing models and enums.
- `app/db/models/` for SQLAlchemy ORM entities.
- `app/models/api_v1_*.py` for API request/response schemas.
- `app/services/` and `app/repositories/` for business logic and persistence.

M7 should follow these conventions. Avoid introducing a parallel generic framework or renaming the existing `ImpactAssessment` types, because those currently describe AI impact assessments attached to evidence and goals.

## 2. Proposed domain module layout

```text
app/
  domain/
    __init__.py
    impact/
      __init__.py
      enums.py
      types.py
      policies.py
  models/
    impact_analysis.py
    impact_statement.py
    impact_statement_assessment.py
    impact_measurement.py
    impact_attribution.py
    impact_role_expectation.py
    api_v1_impact_analysis.py
```

`app/domain/impact/` contains business vocabulary and pure domain structures. `app/models/` continues to contain Pydantic models, including API schemas. SQLAlchemy entities remain exclusively in `app/db/models/`.

## 3. Enums

Create string enums in `app/domain/impact/enums.py`. Enum values must exactly match the approved DB/API contract; do not allow free-form strings for controlled states.

| Enum | Proposed values | Meaning |
|---|---|---|
| `ImpactAnalysisStatus` | `DRAFT`, `IN_PROGRESS`, `FINALIZED` | Employee analysis workspace lifecycle |
| `ImpactStatementStatus` | `ACTIVE`, `ARCHIVED` | Whether a statement participates in current analysis |
| `ImpactDimension` | `BUSINESS`, `CUSTOMER`, `TECHNICAL`, `RELIABILITY`, `OPERATIONAL`, `PEOPLE`, `LEADERSHIP`, `INNOVATION`, `RISK`, `OTHER` | What kind of impact is claimed |
| `ImpactEvidenceRelationship` | `PRIMARY`, `SUPPORTING`, `CONTEXT` | How evidence supports a statement |
| `ImpactPerspective` | `EMPLOYEE`, `AI`, `MANAGER` | Who/what authored an assessment |
| `EmployeeAssessmentStatus` | `DRAFT`, `SUBMITTED`, `WITHDRAWN` | Employee perspective lifecycle |
| `AIAssessmentStatus` | `GENERATED`, `SUPERSEDED`, `FAILED` | AI perspective lifecycle |
| `ManagerAssessmentStatus` | `DRAFT`, `ACCEPTED`, `NEEDS_REVIEW`, `NOT_ACCEPTED` | Manager perspective lifecycle |
| `ContributionType` | `DIRECT`, `SHARED`, `LEADERSHIP`, `ENABLING`, `INDIRECT` | Nature of an individual's contribution |

Use perspective-specific status validation. Do not create one unrestricted status enum that permits invalid combinations such as an AI assessment with `ACCEPTED` status.

## 4. Domain structures / structs

Use Python `dataclass` or typed immutable structures for service-to-service values that are not persistence entities. Pydantic remains appropriate at API boundaries. Suggested structures:

```python
@dataclass(frozen=True)
class EvidenceEligibility:
    mapping_id: str
    evidence_id: str
    approval_status: str | None
    is_eligible_for_manager_validation: bool
    reason: str | None
    source_version_id: str | None

@dataclass(frozen=True)
class ImpactComparison:
    employee_assessment_id: str | None
    ai_assessment_id: str | None
    manager_assessment_id: str | None
    employee_status: str | None
    manager_status: str | None
    differences: tuple[str, ...]

@dataclass(frozen=True)
class RoleCoverage:
    responsibility_id: str | None
    competency_id: str | None
    linked_statement_count: int
    coverage_state: str

@dataclass(frozen=True)
class ImpactTrendPoint:
    period_start: date
    period_end: date
    statement_count: int
    accepted_count: int
    needs_review_count: int
    measurement_summaries: tuple[dict[str, object], ...]
```

These are illustrative contracts, not exact code to paste without review. Prefer typed fields and small named structures over untyped nested dictionaries. Do not put SQLAlchemy objects inside domain structures.

## 5. Core domain concepts

### 5.1 Impact analysis

One employee's impact workspace for one date range. The database proposal uses `impact_analyses` with employee, start/end date and lifecycle status. It is not a shared company performance-cycle definition.

### 5.2 Impact statement

The employee-visible claim/outcome within an analysis. It is linked to an existing goal and optionally a milestone. It is not a replacement for a goal, milestone, evidence item, or a future general-purpose achievement entity.

A statement should answer:

- What changed or was delivered?
- Which goal did it support?
- What outcome or value resulted?
- Which evidence supports, contextualizes or challenges the claim?
- What contribution did the employee make?

### 5.3 Assessment perspective

An assessment is versioned and belongs to exactly one statement and one perspective. Employee, AI and manager versions must not overwrite one another.

- Employee: submitted self-assessment.
- AI: advisory analysis with model and prompt provenance.
- Manager: review decision, summary and rationale.

### 5.4 Measurement

A measurement belongs to a specific assessment version. Baseline, target and actual are nullable; a number must never be invented to make a card or chart look complete. Every populated value must carry a unit and, where known, method/source and measurement period.

### 5.5 Attribution

Attribution records contributors and contribution type. Allocation percentage is optional and must not be fabricated or forced to total 100 unless a later business rule explicitly requires that behavior.

### 5.6 Role expectation

A statement can reference an existing organization role responsibility or competency. Exactly one of the responsibility or competency references is populated. The service validates that the referenced expectation belongs to the appropriate organization/role context.

## 6. Invariants to centralize in domain policy

- A statement's goal must belong to the employee who owns the impact analysis.
- An optional milestone must belong to the same goal.
- A linked evidence mapping must belong to the statement's goal.
- An optional evidence version must belong to the evidence referenced by the mapping.
- Employee, AI and manager assessments are independently versioned.
- An AI assessment cannot create or change a manager decision.
- Manager acceptance is impact validation, not evidence approval.
- Rejected and `NEEDS_INFORMATION` evidence remains visible with its state and review feedback; it is not eligible as approved support for manager acceptance unless a separately documented policy permits it.
- Historical assessments and their cited source versions remain inspectable after source updates.
- Do not calculate a universal score from dimension labels or raw evidence counts.

## 7. Compatibility with existing types

Keep these existing types and their meaning unchanged:

- `app.models.impact_assessment.ImpactType`
- `app.models.impact_assessment.ImpactAssessment`
- `app.models.impact_intelligence.*`
- Existing evidence approval and goal criterion types.

Where the legacy `ImpactType` overlaps with `ImpactDimension`, map explicitly in a conversion function. Do not alias one enum to the other without a reviewed mapping because their vocabularies and semantics differ.

## 8. Tests

Add unit tests for enum values, perspective/status combinations, measurement validation, attribution percentage bounds, role expectation exclusivity, evidence eligibility policy, and conversion from legacy AI impact types. These tests must not require a database unless testing ORM integration.
