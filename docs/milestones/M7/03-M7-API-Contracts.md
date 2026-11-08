# M7.3 – API Contracts

**Target repository:** `myimpact-ai`  
**API prefix:** `/api/v1`  
**Status:** Proposed contracts; endpoint naming and auth dependencies must be reconciled with the current auth implementation.

## 1. Existing API baseline

The inspected backend already has `app/api/v1/impact.py`, mounted in `app/api/v1/router.py`. It currently exposes goal-scoped legacy operations:

- `POST /api/v1/goals/{goal_id}/impact/analyze`
- `GET /api/v1/goals/{goal_id}/impact`

These operate on the existing evidence/goal-level AI impact assessments and the intelligence pipeline. Preserve their behavior for backward compatibility. M7 period/employee impact endpoints must be added separately rather than silently changing the response shape or meaning of the legacy endpoints.

`myimpact-api` is the authentication service in the inspected baseline; product APIs belong in `myimpact-ai`.

## 2. API schema module

Create `app/models/api_v1_impact_analysis.py` (or split into request/response modules if it becomes large). Use Pydantic v2 conventions already used in the repository:

- Request models validate user-editable fields and bounds.
- Response models expose stable API names and `from_attributes=True` only for simple ORM projections.
- Use explicit read models for aggregates; do not serialize ORM graphs directly.
- Use `Decimal` for measurements.
- Use typed enums from `app/domain/impact/enums.py`.
- Use cursor/page pagination consistent with the existing API conventions.

Suggested response families:

- `ImpactAnalysisCreateRequest`, `ImpactAnalysisUpdateRequest`, `ImpactAnalysisResponse`
- `ImpactStatementCreateRequest`, `ImpactStatementUpdateRequest`, `ImpactStatementResponse`
- `ImpactStatementEvidenceCreateRequest`, `ImpactStatementEvidenceResponse`
- `ImpactAssessmentCreateRequest`, `ImpactAssessmentResponse`, `ImpactAssessmentVersionResponse`
- `ImpactMeasurementInput`, `ImpactMeasurementResponse`
- `ImpactAttributionInput`, `ImpactAttributionResponse`
- `ImpactRoleExpectationInput`, `ImpactRoleExpectationResponse`
- `ImpactOverviewResponse`, `ImpactByGoalResponse`, `ImpactRoleImpactResponse`, `ImpactEvidenceReviewResponse`, `ImpactComparisonResponse`, `ImpactTrendResponse`

## 3. Proposed endpoints

Use a dedicated router such as `app/api/v1/impact_analysis.py` with prefix `/impact-analyses`, and include it in `app/api/v1/router.py`. The route prefix is separate from the existing `/goals/{goal_id}/impact` legacy API.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/impact-analyses` | Create or get an employee analysis for a date range, subject to uniqueness policy |
| `GET` | `/impact-analyses` | List analyses visible to current actor; employee sees own, manager sees authorized reports |
| `GET` | `/impact-analyses/{analysis_id}` | Read analysis and high-level status |
| `PATCH` | `/impact-analyses/{analysis_id}` | Update permitted analysis metadata/status |
| `POST` | `/impact-analyses/{analysis_id}/finalize` | Finalize employee analysis subject to completeness policy |
| `GET` | `/impact-analyses/{analysis_id}/overview` | Overview counts and status summary |
| `GET` | `/impact-analyses/{analysis_id}/goals` | By Goals page data |
| `GET` | `/impact-analyses/{analysis_id}/role-impact` | Role Impact page data |
| `GET` | `/impact-analyses/{analysis_id}/evidence-reviews` | Evidence & Reviews page data |
| `GET` | `/impact-analyses/{analysis_id}/comparison` | Employee vs AI vs manager comparison |
| `GET` | `/impact-analyses/{analysis_id}/trends` | Trend read model |
| `POST` | `/impact-analyses/{analysis_id}/statements` | Create impact statement |
| `GET` | `/impact-statements/{statement_id}` | Read statement and bounded source context |
| `PATCH` | `/impact-statements/{statement_id}` | Edit statement content while editable |
| `POST` | `/impact-statements/{statement_id}/archive` | Archive statement without deleting history |
| `POST` | `/impact-statements/{statement_id}/evidence` | Link an existing evidence mapping/version |
| `DELETE` | `/impact-statements/{statement_id}/evidence/{link_id}` | Unlink where policy permits; retain audit/history |
| `POST` | `/impact-statements/{statement_id}/assessments/employee` | Create/submit a new employee perspective version |
| `POST` | `/impact-statements/{statement_id}/assessments/ai` | Trigger AI perspective generation; usually async if processing is long-running |
| `POST` | `/impact-statements/{statement_id}/assessments/manager` | Manager creates a new manager perspective version |
| `GET` | `/impact-statements/{statement_id}/assessments` | List version history by perspective |
| `POST` | `/impact-assessments/{assessment_id}/measurements` | Add structured measurements to a new/editable assessment version |
| `POST` | `/impact-assessments/{assessment_id}/attributions` | Add contribution records to a new/editable assessment version |
| `PUT` | `/impact-statements/{statement_id}/role-expectations` | Replace or update expectation links with validation |

The final route list may be consolidated after the API read models are implemented. Do not create a separate endpoint for every tiny field if an aggregate command is safer and clearer.

## 4. Authentication and authorization

Critical: current legacy impact routes accept a `user_id` query parameter. Do not copy this pattern into M7 as the trust boundary.

- Derive the actor from the authenticated principal/dependency already used by the app.
- Employee can create/update their own analysis and statements.
- Manager can read/report on direct or otherwise authorized reports only, using `reporting_manager_id` and organization policy.
- Manager assessment writes require manager relationship/role authorization and statement ownership checks.
- Organization admins have only the scope explicitly granted by existing authorization rules.
- Never accept `employee_user_id`, `reviewed_by_user_id`, or `created_by_user_id` from the client as authoritative identity. Derive actor identity server-side; accept a target employee only for manager-scoped routes and validate it.
- Return 404 for inaccessible resources where that matches existing information-disclosure policy.

## 5. Request/response behavior

### Create analysis

Request fields: `period_start`, `period_end`. Employee identity is derived from auth. Validate end date >= start date and enforce one analysis per employee/date range. Return existing analysis or conflict according to the chosen idempotency contract; document the choice and test it.

### Create impact statement

Request fields: `goal_id`, optional `milestone_id`, `title`, `description`, `impact_dimension`, optional evidence mapping IDs, optional role expectation links. Verify goal ownership and milestone-goal consistency. Evidence linking can be a separate command to keep validation and audit explicit.

### Employee assessment

Request fields: assessment summary, rationale, measurements and attributions. Create a new version. Submission freezes that version; later edits create another version. Employee must not set perspective or manager status.

### AI assessment

The server chooses the AI perspective, records model/prompt provenance and cited source versions, and cannot set manager status. The response must distinguish generated, failed and superseded states.

### Manager assessment

Request fields: decision/status, summary, rationale, measurements, attributions and optional feedback. The actor is the reviewer. The service validates the manager relationship and evidence eligibility. Manager assessment version is immutable after submission/decision; corrections create a new version.

## 6. Evidence status in API

Evidence & Reviews must surface existing evidence approval states:

- `PENDING`
- `APPROVED`
- `NEEDS_INFORMATION`
- `REJECTED`

Expose current approval state and available review feedback/history from existing sources. Do not collapse all non-approved states into `PENDING`, and do not hide rejected or needs-information evidence from employee-facing traceability.

Manager impact acceptance must be distinct from evidence approval. API fields should make the distinction explicit, e.g. `evidence_approval_status` vs `manager_impact_status`.

## 7. Error contract

Use the existing API error conventions. At minimum distinguish:

- `400` invalid state transition or malformed request.
- `401` unauthenticated.
- `403` authenticated but not authorized, if policy does not mask existence.
- `404` inaccessible/missing resource when using resource masking.
- `409` duplicate analysis or stale/conflicting version.
- `422` business validation failure (goal mismatch, invalid evidence mapping, manager not in scope, unsupported status/perspective combination).

Errors must be safe and actionable; never leak another employee's data.

## 8. API tests

- Contract/schema validation for all request/response models.
- Employee can access own analysis; cannot access another employee's analysis.
- Manager can access only authorized reports.
- Employee cannot submit manager assessment; manager cannot impersonate employee.
- AI endpoint cannot set or overwrite manager decision.
- All four evidence approval statuses are returned faithfully.
- Legacy `/goals/{goal_id}/impact` contract remains unchanged.
- Pagination, filtering, empty states and error codes are deterministic.
