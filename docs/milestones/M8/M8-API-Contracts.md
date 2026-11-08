# M8 — API Contracts

**Target repository:** `myimpact-ai`  
**Proposed API prefix:** `/api/v1/reports`  
**Status:** Proposed; reconcile with current authentication and router conventions.

## 1. Compatibility

The existing goal-scoped `GET /api/v1/goals/{goal_id}/report` synthesizes a report from legacy goal-level impact assessments and career insight. Preserve its response and behavior during M8. Do not overload it with the new report lifecycle.

Inspect and restrict legacy generic report CRUD endpoints before exposing new M8 behavior. New endpoints derive actor identity from the authenticated principal; do not trust client-provided `user_id`, `created_by_user_id` or `published_by_user_id`.

## 2. Request/response conventions

- Pydantic v2 request/response schemas.
- Typed enums for report kind, audience, lifecycle and artifact format.
- Dates are ISO `YYYY-MM-DD`; end date must be on/after start date.
- Use explicit read models, not ORM graph serialization.
- Use stable pagination consistent with existing APIs.
- Use `Decimal` for any numeric source values; do not coerce null to zero.
- Return source references and validation findings in stable structured shapes.

## 3. Proposed endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/reports` | Request on-demand generation |
| `GET` | `/api/v1/reports` | List reports visible to actor, with filters |
| `GET` | `/api/v1/reports/{report_id}` | Report metadata and structured content |
| `GET` | `/api/v1/reports/{report_id}/preview` | Draft preview projection |
| `PATCH` | `/api/v1/reports/{report_id}/draft` | Edit allowed narrative content in a draft |
| `POST` | `/api/v1/reports/{report_id}/publish` | Publish an authorized draft |
| `POST` | `/api/v1/reports/{report_id}/regenerate` | Create a new version from fresh or explicitly selected context |
| `GET` | `/api/v1/reports/{report_id}/versions` | List version lineage |
| `GET` | `/api/v1/reports/{report_id}/validation` | Retrieve validation status/findings |
| `GET` | `/api/v1/reports/{report_id}/artifacts` | List available PDF/DOCX artifacts |
| `POST` | `/api/v1/reports/{report_id}/artifacts` | Request export in PDF or DOCX |
| `GET` | `/api/v1/reports/{report_id}/artifacts/{artifact_id}/download` | Authorized artifact download |
| `GET` | `/api/v1/reports/templates` | List templates available to actor |
| `GET` | `/api/v1/reports/{report_id}/context-summary` | Safe summary of snapshot sources/completeness; never expose unrestricted raw context |

Endpoint consolidation is acceptable if it follows existing project patterns. Do not create one route per report kind; use a validated `report_kind` request field.

## 4. Generate request

Example:

```json
{
  "report_kind": "EMPLOYEE_PERFORMANCE",
  "audience": "EMPLOYEE",
  "period_start": "2026-01-01",
  "period_end": "2026-12-31",
  "locale": "en-IN",
  "idempotency_key": "client-generated-key"
}
```

For manager requests, `subject_user_id` or `team_id` may be supplied as a target selector, but the server must verify the authenticated actor's relationship and scope. For employee audience, subject is the authenticated user and must not be overridden by client input.

Response should include:
- `report_id`
- `generation_status`
- `publication_status`
- `version`
- `created_at`
- optional status polling URL or report location.

If generation is asynchronous, return `202 Accepted`. Do not keep an HTTP request open for lengthy LLM/export work.

## 5. Core response shape

```json
{
  "id": "report-id",
  "report_kind": "EMPLOYEE_PERFORMANCE",
  "audience": "EMPLOYEE",
  "subject": {"user_id": "subject-id"},
  "period": {"start_date": "2026-01-01", "end_date": "2026-12-31"},
  "generation_status": "DRAFT_READY",
  "publication_status": "DRAFT",
  "freshness": "CURRENT",
  "version": 1,
  "content": {
    "schema_version": "1.0",
    "title": "Employee Performance Report",
    "sections": []
  },
  "validation": {"status": "PASSED_WITH_WARNINGS", "findings": []},
  "generated_at": "timestamp"
}
```

## 6. Authorization rules

- Employee may generate/list/read/edit draft/publish/export own reports.
- Manager may target only employees in authorized reporting scope and teams in authorized scope.
- Manager team summary must be computed from authorized members only.
- Actor identity comes from auth dependency, not request body/query.
- Validate authorization independently for preview, context summary, history, publish, regenerate, artifact listing and download.
- Return 404 for inaccessible resources if consistent with existing information-disclosure policy.
- Organization admin access is not implied; use explicit existing policy.

## 7. Error contract

Use existing API error conventions. Distinguish:
- `400`: invalid lifecycle operation or unsupported report-kind/audience combination.
- `401`: unauthenticated.
- `403` or masked `404`: unauthorized.
- `404`: missing/inaccessible resource.
- `409`: idempotency/version conflict, immutable report edit, duplicate publication.
- `422`: invalid date range, missing required source configuration, schema/business validation failure.
- `429`: rate/usage limit if configured.
- `503`: generation provider unavailable where retry is appropriate.

Errors must be actionable and must not expose another employee's data, raw prompts or sensitive source content.

## 8. API acceptance tests

- Employee cannot generate/read/download another employee's report.
- Manager can target only authorized direct reports/team scope.
- Forged actor IDs are ignored/rejected.
- Team aggregation excludes unauthorized members.
- Legacy goal report endpoint remains compatible.
- Generation is idempotent for repeated request key.
- Draft edit is allowed only before publication and only for editable fields.
- Published report cannot be mutated; regeneration creates a new version.
- Artifact download rechecks authorization.
- Missing source data and validation warnings are represented accurately.
