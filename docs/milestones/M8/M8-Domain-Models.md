# M8 — Domain Models, Types and Structures

**Target repository:** `myimpact-ai`  
**Status:** Proposed domain design.

## 1. Domain boundary

The Reporting domain owns report request, context snapshot, template selection, generation lifecycle, validation, publication, versioning and artifact metadata. It does not own goal, evidence, impact or role-assessment truth.

## 2. Core enums

Proposed values; reconcile naming with existing Python enum conventions before coding.

```python
class ReportAudience(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"

class ReportKind(str, Enum):
    EMPLOYEE_PERFORMANCE = "EMPLOYEE_PERFORMANCE"
    GOAL_PROGRESS = "GOAL_PROGRESS"
    ONE_TO_ONE_BRIEF = "ONE_TO_ONE_BRIEF"
    CAREER_DEVELOPMENT = "CAREER_DEVELOPMENT"
    MANAGER_INDIVIDUAL = "MANAGER_INDIVIDUAL"
    MANAGER_TEAM_SUMMARY = "MANAGER_TEAM_SUMMARY"

class ReportGenerationStatus(str, Enum):
    REQUESTED = "REQUESTED"
    CONTEXT_READY = "CONTEXT_READY"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    DRAFT_READY = "DRAFT_READY"
    FAILED = "FAILED"

class ReportPublicationStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"

class ReportFreshness(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"

class ReportValidationStatus(str, Enum):
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"

class ReportArtifactFormat(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"
```

Keep legacy `ReportType` and `ReportStatus` values unchanged. Use explicit adapters from legacy values to new `ReportKind` where a mapping is defensible. Do not silently map `PROMOTION_EVIDENCE` to a promotion decision report; it may be a legacy evidence compilation.

## 3. Core entities/value objects

### ReportRequest
- `report_kind`
- `audience`
- `period_start`, `period_end`
- optional `subject_user_id` (manager request only; validated against actor)
- optional `team_id` (team report only)
- optional `locale`
- optional `idempotency_key`

Actor identity is not a client-controlled field in the trusted domain command; pass authenticated actor context separately.

### Report
- `id`
- `report_kind`, `audience`
- `subject_user_id`, optional `team_id`
- `period`
- `generation_status`
- `publication_status`
- `freshness`
- `version`
- `content`
- `context_snapshot_id`
- `template_ref`
- `created_by`, timestamps
- optional `supersedes_report_id`

### ReportPeriod
- `start_date`
- `end_date`
- invariant: end date must not precede start date.

### ReportSection
- `section_key`
- `title`
- `content_blocks`
- `status` (`AVAILABLE`, `PARTIAL`, `UNAVAILABLE`)
- `source_references`
- optional `warnings`

### ReportClaim
Recommended structured representation for material factual claims:
- `claim_id`
- `text`
- `claim_type` (`SOURCE_FACT`, `SUMMARY`, `SUGGESTION`)
- `source_references`
- optional `qualifiers`
- optional `validation_state`

### ReportSourceReference
- `source_system` (`M6_GOAL`, `M6_EVIDENCE`, `M6_INSIGHT`, `M7_IMPACT`, `ROLE_CATALOGUE`, etc.)
- `entity_type`
- `entity_id`
- optional `version_id`
- `relationship`
- optional `source_updated_at`
- optional bounded locator/section reference.

Do not put raw secrets, unrestricted documents or unnecessary personal data in source references.

### ReportContextSnapshot
- `id`
- `subject/team scope`
- `period`
- `schema_version`
- `source_manifest`
- bounded `context_payload`
- `content_hash`
- `created_at`

### ReportTemplateRef
- `template_id`
- `template_key`
- `version`
- `report_kind`
- `audience`

### ReportGenerationRun
- `id`
- `report_id`
- `attempt_number`
- `status`
- model/provider/version and prompt/template versions
- timestamps and sanitized error details
- usage metadata when available.

### ReportValidationFinding
- `rule_id`
- `severity` (`ERROR`, `WARNING`, `INFO`)
- `message`
- optional `section_key` / `claim_id`
- source references
- remediation guidance.

### ReportArtifact
- `id`
- `report_id`
- `report_version`
- `format`
- `storage_reference`
- `file_name`, `content_type`, `size_bytes`, `checksum`
- renderer version and generated timestamp.

## 4. Report lifecycle invariants

Generation lifecycle and publication lifecycle are independent.

- A report can be `DRAFT` only after structured content has been persisted.
- `DRAFT_READY` requires schema validation and no blocking factual validation errors.
- Warnings may remain visible and must be reviewable.
- Publication is a separate user action and requires authorization.
- Published versions are immutable.
- Regeneration creates a new version linked by `supersedes_report_id`.
- A report may become stale when source data changes; stale does not rewrite the snapshot.
- Exporting an artifact does not publish a report unless product policy explicitly makes that action equivalent.
- Failed attempts remain visible in operational history without being mistaken for completed reports.

## 5. Report content schema

Use a versioned structured schema. Suggested top-level fields:

```json
{
  "schema_version": "1.0",
  "report_kind": "EMPLOYEE_PERFORMANCE",
  "title": "Employee Performance Report",
  "subject": {},
  "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "executive_summary": {},
  "sections": [],
  "data_completeness": {},
  "limitations": [],
  "source_manifest": []
}
```

Each section should contain a stable key, title, content blocks, availability state, source references and warnings. Store content as JSONB; validate with Pydantic models at the application boundary.

## 6. Domain policies

- `ReportAccessPolicy`: determines whether actor can generate/read/publish/export for subject/team.
- `ReportContextPolicy`: bounds sources by period, scope, authorization and supported source types.
- `ReportTemplatePolicy`: selects active template compatible with report kind and audience.
- `ReportGenerationPolicy`: retry, idempotency, timeout and duplicate-request behavior.
- `ReportValidationPolicy`: blocking vs warning rules.
- `ReportPublicationPolicy`: draft review and immutable publication.
- `ReportFreshnessPolicy`: compares current source versions to snapshot manifest without rewriting history.

## 7. Legacy adapters

- Preserve existing `ReportType` values.
- Preserve legacy report retrieval and goal report endpoint.
- Build adapters only for unambiguous mappings.
- Legacy text content remains legacy content unless explicitly migrated.
- Do not reinterpret existing `CURRENT`, `STALE`, `ARCHIVED` as new generation statuses.

## 8. Domain test requirements

Test enum compatibility, date invariants, report-kind/audience compatibility, immutable publication, version lineage, snapshot immutability, validation transition rules, null handling, and source-reference identity/version rules.
