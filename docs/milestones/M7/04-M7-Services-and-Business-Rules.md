# M7.3–M7.4 – Services and Business Rules

**Target repository:** `myimpact-ai`

## 1. Existing service boundary

The inspected backend already has `app.services.impact_assessment.ImpactAssessmentService`, which persists the legacy `impact_assessments` records (one evidence/goal-level AI assessment). Do not repurpose or rename it as the employee/manager assessment service without a dedicated migration plan.

Use explicit M7 service names to avoid semantic collision.

## 2. Proposed services

| Service | Responsibility |
|---|---|
| `ImpactAnalysisService` | Create/read/update/finalize employee-period analysis; enforce analysis lifecycle and actor scope |
| `ImpactStatementService` | Create/update/archive statements; validate goal and milestone ownership |
| `ImpactStatementEvidenceService` | Link existing evidence mappings/versions; return evidence review context without owning approvals |
| `ImpactStatementAssessmentService` | Create/version employee and manager perspectives; enforce transitions and immutable history |
| `ImpactAIAssessmentService` | Orchestrate advisory AI assessment using existing intelligence/retrieval/evaluation components |
| `ImpactEvidenceEligibilityService` | Determine whether linked evidence is eligible for a given decision and explain exclusions |
| `ImpactMeasurementService` | Validate and persist sourced baseline/target/actual measurements |
| `ImpactAttributionService` | Validate contributor links and contribution records |
| `ImpactRoleCoverageService` | Link impact statements to existing role responsibilities/competencies and calculate coverage read models |
| `ImpactAggregationService` | Produce Overview, By Goals, Comparison and Trends read models without double counting |
| `ImpactAuthorizationService` | Centralize employee, manager, team and organization access checks |

Services may be combined where they are small, but do not combine all behavior into one oversized `ImpactService`.

## 3. Transaction and dependency rules

- Services coordinate repositories and own commit/rollback boundaries.
- Repositories do not commit independently.
- Inject dependencies where practical; follow the current `Depends`/service construction conventions.
- Keep pure policy functions separate from database access so they can be unit tested.
- Use existing M6 services for goal, evidence, evidence mapping, evidence approval, source versions, criteria and review context.
- Do not make M7 responsible for changing the state of M6 evidence approvals.

## 4. Core workflows

### 4.1 Employee creates an impact analysis

1. Resolve employee from authenticated actor.
2. Validate date range.
3. Find/create the employee-period analysis according to the idempotency decision.
4. Return analysis ID, date range and status.

### 4.2 Employee creates an impact statement

1. Load analysis and verify actor owns it and it is editable.
2. Load goal and verify goal belongs to analysis employee.
3. If milestone supplied, verify it belongs to that goal.
4. Create statement.
5. Add evidence and role links only through their dedicated validation paths.
6. Commit atomically.

### 4.3 Employee links evidence

1. Load statement and verify employee ownership.
2. Load evidence mapping from the existing M6 repository.
3. Verify mapping is for the same goal as the statement.
4. If a specific evidence version is supplied, verify it belongs to the evidence referenced by the mapping.
5. Persist relationship type (`PRIMARY`, `SUPPORTING`, `CONTEXT`).
6. Return current evidence approval state and available feedback/history as read-only context.

Do not create, approve, reject, or reset an `evidence_approvals` record in this workflow.

### 4.4 Employee submits self-assessment

1. Validate employee ownership and editable statement state.
2. Validate summary, rationale, measurement units/source and attribution structure.
3. Create a new `EMPLOYEE` assessment version and child records in one transaction.
4. Mark the version `SUBMITTED` and freeze it.
5. Preserve prior versions; do not update a submitted version in place.
6. Make the submitted version available to manager and AI workflows according to authorization.

### 4.5 AI generates an assessment

1. Build bounded context from the impact statement, linked goals/milestones, evidence mappings, source versions, evidence approval states, existing goal criterion assessments and legacy evidence-level AI impact assessments.
2. Include rejected and `NEEDS_INFORMATION` evidence as explicit context with its state and feedback. Do not treat it as approved proof.
3. Reuse existing retrieval/evaluation/intelligence services where relevant; do not duplicate M6 pipelines.
4. Generate an `AI` perspective version with model version, prompt version, cited evidence/source version IDs and rationale.
5. Persist `GENERATED` or `FAILED`; mark older AI version superseded only through a new version transition.
6. Never modify employee or manager assessment versions.
7. Do not produce a numeric impact score unless an approved, documented and versioned calculation methodology exists.

### 4.6 Manager validates impact

1. Resolve manager from authenticated actor.
2. Load statement and analysis; verify employee is within manager's authorized reporting scope.
3. Load latest employee submission and its source context.
4. Evaluate evidence eligibility and show all evidence states, including rejected/needs-information items and feedback.
5. Require manager rationale for `ACCEPTED`, `NEEDS_REVIEW` or `NOT_ACCEPTED` decisions as defined by product validation rules.
6. Create a new immutable `MANAGER` assessment version, recording reviewer identity.
7. Persist measurements and attribution for the manager perspective where supplied.
8. Do not update evidence approval state as a side effect.

The DB proposal suggests manager acceptance should require eligible/approved supporting evidence. The exact rule (all primary evidence approved vs at least one eligible primary item, and whether context evidence may remain non-approved) is an explicit product decision to finalize before implementation.

## 5. Evidence eligibility policy

Create one policy function/service that returns an explainable result, not a boolean alone.

| Existing evidence approval state | Display in Evidence & Reviews | Eligible as approved support for manager acceptance |
|---|---|---|
| `APPROVED` | Yes | Yes, subject to source/version validity |
| `PENDING` | Yes | No |
| `NEEDS_INFORMATION` | Yes, include feedback | No until resubmitted and approved |
| `REJECTED` | Yes, include rejection feedback | No |
| No approval record | Yes, show unreviewed state | No |

This table is the conservative default. A policy change must be explicit, versioned and tested. A rejected item must never disappear from the employee's traceability view merely because it cannot support acceptance.

The current `evidence_approvals` row represents current state, not a complete immutable event ledger. Use the existing notification/review history data where available and be transparent if older decision history is incomplete. Do not fabricate a complete review timeline from the current row.

## 6. Versioning rules

- Each statement has separate version sequences per perspective.
- Employee submission creates a new immutable employee version.
- AI regeneration creates a new AI version with model/prompt provenance.
- Manager decision/revision creates a new manager version.
- `supersedes_assessment_id` points to the previous version where applicable.
- Never mutate old measurement or attribution rows to rewrite what a prior reviewer saw.
- Source version references must remain attached to the assessment context so later source changes do not rewrite history.

## 7. Attribution rules

- Contributors must be valid users in the relevant organization scope.
- Contribution type is required.
- Description is recommended for shared, leadership, enabling and indirect contributions.
- Allocation percentage is optional and bounded 0–100.
- Do not assume all contribution percentages sum to 100; if a future allocation model requires it, enforce it at a defined scope (statement + assessment version) with explicit rounding rules.
- Do not infer that a contributor's presence means they co-own the goal.

## 8. Role coverage rules

- Link to existing `organization_role_responsibilities` or `organization_role_competencies`.
- Exactly one target reference per link.
- Validate the expectation belongs to the relevant organization and role context.
- Do not use free-text `users.role` as a foreign key or pretend the current schema has a normalized user-role assignment.
- A role coverage gap means no linked/assessed impact statement supports an expectation in the selected analysis context; it does not automatically mean the employee failed that responsibility.

## 9. Aggregation and six-page read models

### Overview

Counts and summaries: total statements, employee-submitted, AI-generated, manager-accepted, needs-review, not-accepted, evidence status breakdown and measurement highlights. Label perspectives explicitly.

### By Goals

Group statements under goals. Show goal status/progress separately from impact statement status and manager decision. Never equate goal completion with impact acceptance.

### Role Impact

Show responsibilities/competencies, linked statements, evidence coverage and gaps. Keep role catalogue coverage separate from inferred employee role assignment.

### Evidence & Reviews

Show all linked evidence and current approval state; feedback and review history where available; source/version provenance; explain why an item is or is not eligible for manager validation.

### Comparison

Compare employee, AI and manager perspectives side by side. Show missing perspectives as “Not yet assessed”, not zero. Surface differences and manager rationale; never average the three perspectives into one score.

### Trends

Trend by analysis/performance date range and measurement window. Use comparable metric names/units and preserve missing values. Do not chart incomparable units together or double-count one outcome linked to multiple evidence items.

## 10. Finalization and lifecycle

Finalizing an analysis must not erase or lock evidence review workflows. Define whether finalization freezes employee statements only, or also prevents additional manager assessment versions. Recommended behavior: freeze the employee's submitted snapshot for the period while allowing authorized manager review/versioning and explicitly recorded reopening/amendment workflows.

The exact reopening and post-finalization edit policy is an open decision and must be settled before endpoint implementation.

## 11. Observability and tests

Log actor ID, target employee ID, analysis/statement/assessment IDs, perspective, version and decision event. Do not log sensitive evidence contents or secrets.

Test at minimum:

- ownership and manager-scope authorization;
- goal/milestone/evidence mapping consistency;
- all evidence states and eligibility behavior;
- employee/AI/manager isolation;
- immutable versioning and supersedes links;
- atomic creation of parent/child rows;
- measurement decimal/unit/source validation;
- attribution contributor and percentage validation;
- role expectation scope and gaps;
- aggregation without duplicate counting;
- no side effects on M6 evidence approvals;
- no regression to legacy `impact_assessments` endpoints.
