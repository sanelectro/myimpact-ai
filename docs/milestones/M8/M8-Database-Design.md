# M8 — Database Design

**Target repository:** `myimpact-db`  
**Status:** Proposed logical design; not executable DDL  
**Baseline:** 8 November 2026 uploaded repository snapshots.

## 1. Design goals

Extend the existing reporting foundation without replacing it. Persist structured report content, reproducible source context, generation/validation metadata, version history and PDF/DOCX artifact references.

## 2. Existing baseline to preserve

The inspected initial schema defines:
- `reports`: `id`, `user_id`, `report_type`, `period_start`, `period_end`, `content TEXT`, `version`, `status`, `generated_at`, `updated_at`.
- `report_type` enum values: `MONTHLY_IMPACT`, `QUARTERLY_IMPACT`, `ANNUAL_PERFORMANCE`, `GOAL_PROGRESS`, `PROMOTION_EVIDENCE`, `ONE_TO_ONE`.
- `report_status` enum values: `CURRENT`, `STALE`, `ARCHIVED`.
- Existing ORM, repository and service provide basic report CRUD/retrieval.

Do not edit an applied migration. Do not remove or rename existing enum values in the initial rollout. Preserve legacy report reads and map old records explicitly.

## 3. Proposed logical model

The following are logical entities. They may be implemented as separate tables or consolidated after query and lifecycle review.

### 3.1 `reports` (extend existing)
Keep existing columns for compatibility. Proposed additions:
- `audience` — `EMPLOYEE` or `MANAGER`.
- `target_user_id` — employee subject; nullable only for team-level reports if team scope is separately stored.
- `team_id` — optional authorized team scope.
- `generation_status` — e.g. `REQUESTED`, `CONTEXT_READY`, `GENERATING`, `VALIDATING`, `DRAFT_READY`, `FAILED`.
- `publication_status` — e.g. `DRAFT`, `PUBLISHED`, `WITHDRAWN`.
- `content_json JSONB` — canonical structured report content.
- `template_id`, `template_version`.
- `prompt_version`, `model_provider`, `model_name`, `model_version`.
- `context_snapshot_id`.
- `created_by_user_id` — authenticated actor.
- `published_at`, `published_by_user_id`.
- `supersedes_report_id` — previous version lineage.
- `idempotency_key` — optional request deduplication token.

Do not overload legacy `status` to represent generation or publication. Define explicit migration/backfill semantics for existing rows. Do not assume `user_id` means both subject and actor; clarify legacy meaning and preserve it until all consumers migrate.

### 3.2 `report_context_snapshots`
Proposed fields:
- `id`, `report_id`.
- `subject_user_id`, optional `team_id`.
- `period_start`, `period_end`.
- `snapshot_schema_version`.
- `source_manifest JSONB` containing source entity type, source ID, source version/revision, source timestamp and relationship role.
- `context_payload JSONB` containing only bounded, authorized data required for generation/reproducibility.
- `created_at`, optional `content_hash`.

Rules:
- Snapshot is immutable after generation begins.
- Prefer source references and version identifiers over duplicating full evidence/document content.
- If bounded source excerpts are stored, apply privacy, retention and access controls.
- Never snapshot unauthorized employee data.

### 3.3 `report_templates`
Proposed fields:
- `id`, `report_type`, `audience`.
- `template_key`, `version`, `status` (`DRAFT`, `ACTIVE`, `RETIRED`).
- `section_schema JSONB`, `formatting_config JSONB`.
- `prompt_key`, `prompt_version`.
- `created_at`, `updated_at`, `created_by_user_id`.

Rules:
- Unique `(template_key, version)`.
- A report references the exact template version used.
- Retired templates remain readable for historical reports.
- Template editing authorization is separate from report generation authorization.

### 3.4 `report_generation_runs`
Proposed fields:
- `id`, `report_id`, `attempt_number`.
- `status`, `started_at`, `completed_at`.
- `model_provider`, `model_name`, `model_version`.
- `prompt_key`, `prompt_version`.
- `input_token_count`, `output_token_count` where available.
- `error_code`, sanitized `error_summary`.
- `created_at`.

Rules:
- Preserve retries as separate attempts.
- Never store secrets or unrestricted prompt payloads in operational logs.
- A retry must use the same snapshot unless the user explicitly requests regeneration from refreshed data.

### 3.5 `report_validation_results`
Proposed fields:
- `id`, `report_id`, optional `generation_run_id`.
- `validator_version`, `status` (`PASSED`, `PASSED_WITH_WARNINGS`, `FAILED`).
- `findings JSONB` with severity, rule, section/claim path, message and source references.
- `validated_at`.

Rules:
- Validation results are append-only per validation attempt.
- A failed validation blocks transition to ready/published unless a governed override policy exists.
- Overrides require actor, rationale and audit event; do not silently ignore findings.

### 3.6 `report_artifacts`
Proposed fields:
- `id`, `report_id`, `report_version`.
- `format` (`PDF`, `DOCX`).
- `storage_provider`, `storage_key`, `content_type`, `file_name`, `size_bytes`, `checksum`.
- `generated_at`, `generated_by_user_id`, `status`.
- Optional `renderer_version`.

Rules:
- Store artifact bytes in the existing approved file-storage abstraction, not PostgreSQL large objects unless architecture explicitly requires it.
- Download endpoint resolves storage key server-side after authorization.
- Regenerating an artifact creates a new artifact record or version; do not overwrite a published artifact silently.

### 3.7 `report_audit_events` (if existing audit framework is insufficient)
Proposed fields:
- `id`, `report_id`, `actor_user_id`, `event_type`, `event_at`.
- `details JSONB` with non-sensitive metadata.
- Events: requested, generated, validation failed/passed, draft edited, published, exported, archived, regenerated.

Reuse an existing audit facility if one already meets the requirement; do not create a duplicate audit system.

## 4. Relationships

```text
users (report subject)          users (requesting actor)
        |                                |
        +------------- reports ----------+
                         |
             +-----------+------------+
             |           |            |
       context snapshot  generation   validation
                         runs         results
             |
       source manifest
       (M6 + M7 refs)
                         |
                  report artifacts
                   (PDF / DOCX)

report_templates -- exact template/version --> reports
reports -- supersedes --> reports
```

## 5. Indexes and constraints

At minimum evaluate:
- `(target_user_id, report_type, period_start, period_end)`.
- `(created_by_user_id, created_at DESC)`.
- `(team_id, report_type, period_start, period_end)` where team reports are supported.
- `(generation_status, created_at)` for operational queues.
- `(report_id, attempt_number)` unique for generation runs.
- `(report_id, validated_at DESC)` for validation history.
- `(report_id, report_version, format)` for artifacts.
- Unique `(template_key, version)`.

Use FK delete behavior that preserves published report history. Avoid cascading deletion of report snapshots, generation runs, validation findings or artifacts. Align user deletion/anonymization and retention with privacy policy. Use CHECK constraints for date range, positive version, valid status/format and nonnegative artifact size.

## 6. Data migration and compatibility

1. Inspect all current report consumers and queries.
2. Add new nullable columns/tables in additive Flyway migrations.
3. Preserve existing enum values and `content TEXT`.
4. Define explicit mapping from legacy `ReportStatus` to new lifecycle fields.
5. Treat old text content as legacy content; do not pretend it conforms to new structured schemas.
6. Do not backfill fabricated prompt/model/source provenance for historical records.
7. New reports write structured content and maintain legacy compatibility only where required.
8. Validate fresh install and upgrade from a representative existing database.
9. Roll out backend and frontend compatibility in a coordinated sequence.

## 7. Open database decisions

| Decision | Proposed default |
|---|---|
| JSONB vs normalized report sections | JSONB canonical content; normalize only queried lifecycle/provenance fields |
| Snapshot payload | Source manifest plus minimum bounded context |
| Team summary subject | Explicit team ID and authorized scope |
| Artifact storage | Existing file storage abstraction |
| Audit table | Reuse existing audit framework if sufficient |
| Legacy status | Preserve; add explicit generation/publication statuses |
| Retention | Follow organization privacy/retention policy; do not invent duration |

## 8. Database acceptance criteria

- Existing reports remain readable.
- New structured reports can be persisted and retrieved.
- Context snapshots are immutable and versioned.
- Generation attempts and validation outcomes are auditable.
- PDF/DOCX artifacts are referenced securely.
- Published report versions are retained.
- Authorization is enforced by services, not assumed from FKs.
- Fresh and upgrade migrations pass.
- No existing applied migration is modified.
