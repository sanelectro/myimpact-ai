# MyImpact M7 – Database Changes Specification

**Milestone:** M7 – Impact Analysis  
**Workstream:** M7.1 – Database Design  
**Target repository:** `myimpact-db`  
**Document version:** 0.1  
**Status:** Proposed design – review required before migration implementation  
**Repository baseline inspected:** Latest uploaded ZIPs dated 8 November 2026  

---

## 1. Purpose

This document defines the proposed PostgreSQL changes required to support M7 Impact Analysis.

M7 must let an employee understand:

- The impact they believe they created from submitted evidence.
- The impact that has been assessed or validated by their manager.
- Which evidence items are pending, approved, need more information, or were rejected.
- The measurements, contribution and role expectations associated with each impact statement.
- How impact changes over a performance period.

The database must preserve separate employee, AI and manager perspectives. It must not convert an employee claim or AI suggestion into a manager-approved outcome automatically.

This is a database design specification, not an executable Flyway migration. Names and DDL below are proposed and must be reconciled with the current ORM and API contracts before implementation.

## 2. Repository findings – existing schema

The latest `myimpact-db` migrations and corresponding `myimpact-ai` SQLAlchemy models were inspected.

### 2.1 Existing tables to reuse

| Existing table | Current responsibility | M7 treatment |
|---|---|---|
| `users` | Employee identity, organization, team and `reporting_manager_id` | Reuse for employee and manager references |
| `goals` | Employee-owned goals, dates, lifecycle and organization | Reuse as the goal anchor |
| `milestones` | Goal milestones and progress checkpoints | Reuse as an optional link; do not assume every milestone is an achievement |
| `evidence` | Submitted evidence | Reuse; do not duplicate |
| `evidence_versions` | Versioned evidence content | Reuse for source-version traceability |
| `evidence_mappings` | Evidence-to-goal and optional milestone relationship | Reuse as the authoritative evidence relationship |
| `evidence_approvals` | Current manager decision for an evidence mapping | Reuse; do not create a second evidence approval table |
| `notification_history` | Records notification and evidence-review-related events | Reuse for existing event history where applicable |
| `impact_assessments` | Existing evidence-and-goal-level AI impact assessment | Preserve and extend only if required; do not repurpose as employee/manager assessment records |
| `goal_criteria`, `goal_criterion_versions` | Goal success criteria and versioned definitions | Reuse for criterion-level context |
| `goal_assessment_runs`, `goal_criterion_assessments`, `goal_criterion_assessment_evidence` | Goal criterion assessment results and their evidence links | Reuse for goal assessment context and provenance |
| `organization_roles` | Organization-scoped role catalogue | Reuse as role context |
| `organization_role_responsibilities` | Role responsibility statements | Reuse as role expectation references |
| `organization_role_competencies` | Role competencies and expected levels | Reuse as role expectation references |
| `organizations`, `teams` | Organization and team structure | Reuse for scope and authorization |
| `reports` | Existing generated reports | Do not use as the authoritative M7 impact data store |

### 2.2 Important gaps confirmed in the current schema

1. There is **no dedicated `achievements` table** in the current migrations. Goals, milestones, evidence mappings and AI impact assessments exist. M7 must not silently treat a milestone as an achievement. This proposal uses an `impact_statement` as the M7-owned employee-visible outcome/claim, linked to a goal and supporting evidence mappings. A separate achievement domain can be introduced later only if product requirements establish it.
2. There is **no performance-period entity** in the current schema. M7 will initially store a start and end date on the employee's impact-analysis record. A shared performance-cycle table can be introduced later if other modules need centrally managed cycles, names, states and deadlines.
3. `users.role` is currently a text value. The organization role catalogue is not directly assigned to a user through a normalized role-assignment table. This proposal links statements to role responsibility/competency catalogue rows but does not invent a user-role assignment model.
4. `evidence_approvals` stores one current row per `evidence_mappings` row. The current status values are `PENDING`, `APPROVED`, `REJECTED`, and `NEEDS_INFORMATION`.
5. Evidence review decision and resubmission events are represented in `notification_history` metadata by the existing application flow. The approval row itself is reset to `PENDING` on resubmission. M7 must not treat the current approval row as a complete immutable record of every prior decision.
6. `impact_assessments` is currently tied directly to `evidence_id` and `goal_id`, with `impact_type`, `impact_summary`, `impact_score`, `confidence`, and `assessment_version`. This is an AI/evidence-level assessment, not a performance-period employee/manager assessment aggregate.

## 3. Database design principles

1. **Reuse authoritative source tables.** Do not copy goals, milestones, evidence, evidence versions, evidence mappings, evidence approvals, or role catalogue records into M7 tables.
2. **Keep perspectives separate.** Employee, AI and manager assessments must be identifiable and independently versioned.
3. **Separate evidence approval from impact validation.** `evidence_approvals` continues to represent the manager's decision on evidence-to-goal mapping. M7 assessment records represent whether the manager accepts the impact interpretation/outcome.
4. **Preserve history.** New assessment versions are append-only. Do not overwrite prior employee or manager assessment versions.
5. **Trace every claim.** Impact statements should link to one or more existing evidence mappings and, where available, a specific evidence version.
6. **Do not fabricate measurements.** Quantitative fields are nullable and must include units and measurement context.
7. **Avoid double counting.** An impact statement may reference several evidence mappings, but those references must not cause the same underlying outcome to be summed repeatedly.
8. **Do not introduce an arbitrary universal impact score in the database.** Store underlying dimensions, outcomes, measurements, confidence and review decisions. Any later aggregate score must have a documented calculation version and methodology.
9. Follow the existing SQL-first, timestamped Flyway migration approach. Applied migrations are immutable.

## 4. Proposed M7-owned tables

The initial proposal introduces the following tables:

| Proposed table | Purpose | Priority |
|---|---|---|
| `impact_analyses` | One employee's impact workspace for a defined date range | Required |
| `impact_statements` | Employee-visible impact claim/outcome linked to a goal | Required |
| `impact_statement_evidence` | Links an impact statement to existing evidence mappings and optional evidence versions | Required |
| `impact_statement_assessments` | Versioned employee, AI and manager perspectives for a statement | Required |
| `impact_assessment_measurements` | Structured baseline/target/actual metrics for an assessment version | Required for quantitative impact |
| `impact_assessment_attributions` | Individual/team contribution records for an assessment version | Required for attribution |
| `impact_statement_role_expectations` | Links a statement to existing role responsibilities or competencies | Required for Role Impact page |

No new evidence approval table is proposed.

### 4.1 `impact_analyses`

Represents the employee's impact-analysis workspace for one performance period/date range.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key; follows existing identifier convention |
| `employee_user_id` | `VARCHAR(64)` | No | FK to `users.id` |
| `period_start` | `DATE` | No | Inclusive start date |
| `period_end` | `DATE` | No | Inclusive end date; must be >= start date |
| `status` | `VARCHAR(30)` | No | `DRAFT`, `IN_PROGRESS`, `FINALIZED` |
| `created_at` | `TIMESTAMPTZ` | No | Creation time |
| `updated_at` | `TIMESTAMPTZ` | No | Last update time |
| `finalized_at` | `TIMESTAMPTZ` | Yes | Set when finalized |

Constraints and indexes:

- PK on `id`.
- FK `employee_user_id` to `users(id)`; use `ON DELETE RESTRICT` to preserve performance history.
- CHECK `period_end >= period_start`.
- CHECK status is one of the supported values.
- Unique `(employee_user_id, period_start, period_end)` for the initial one-analysis-per-employee-and-period model.
- Index `(employee_user_id, period_start DESC, period_end)`.
- Index `(status, period_end)` for operational queries.

Design note: this is not a company-wide performance-cycle definition. If formal cycles become a shared concept, add a `performance_periods` table in a separate design decision and reference it from `impact_analyses`.

### 4.2 `impact_statements`

Represents an employee's impact claim or outcome statement within an impact analysis. It is the M7-owned object displayed and compared across the six Impact pages.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key |
| `impact_analysis_id` | `VARCHAR(64)` | No | FK to `impact_analyses.id` |
| `goal_id` | `VARCHAR(64)` | No | FK to `goals.id` |
| `milestone_id` | `VARCHAR(64)` | Yes | Optional milestone context; must belong to the same goal |
| `title` | `VARCHAR(300)` | No | Short impact headline |
| `description` | `TEXT` | No | What changed / what outcome was created |
| `impact_dimension` | `VARCHAR(40)` | No | Controlled dimension; see section 7 |
| `status` | `VARCHAR(20)` | No | `ACTIVE` or `ARCHIVED` |
| `created_by_user_id` | `VARCHAR(64)` | No | FK to `users.id` |
| `created_at` | `TIMESTAMPTZ` | No | Creation time |
| `updated_at` | `TIMESTAMPTZ` | No | Last update time |

Constraints and indexes:

- FK to `impact_analyses` and `goals` with `ON DELETE RESTRICT` to protect historical assessments.
- Optional composite FK `(milestone_id, goal_id)` to `milestones(id, goal_id)`; the existing migration defines the required unique key.
- FK `created_by_user_id` to `users(id)` with `ON DELETE RESTRICT`.
- CHECK dimension belongs to the controlled dimension list.
- CHECK status is `ACTIVE` or `ARCHIVED`.
- Index `(impact_analysis_id, status)`.
- Index `(goal_id)`.

Ownership rule: the application must verify that `impact_analysis.employee_user_id` matches `goals.user_id` and the authorized employee context. A database trigger is not proposed for this cross-table ownership rule in the first migration; enforce it in the service layer and test it.

### 4.3 `impact_statement_evidence`

Associates an impact statement with one or more authoritative evidence-to-goal mappings. This allows the employee to see exactly which submitted evidence supports a claim.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key |
| `impact_statement_id` | `VARCHAR(64)` | No | FK to `impact_statements.id` |
| `evidence_mapping_id` | `VARCHAR(64)` | No | FK to `evidence_mappings.id` |
| `evidence_version_id` | `VARCHAR(64)` | Yes | Optional FK to `evidence_versions.id` to pin the content version used |
| `relationship_type` | `VARCHAR(30)` | No | `PRIMARY`, `SUPPORTING`, `CONTEXT` |
| `created_by_user_id` | `VARCHAR(64)` | No | User who linked the evidence |
| `created_at` | `TIMESTAMPTZ` | No | Link creation time |

Constraints and indexes:

- FK to statement and mapping with `ON DELETE RESTRICT`.
- FK to evidence version with `ON DELETE RESTRICT`.
- FK to creator with `ON DELETE RESTRICT`.
- Unique `(impact_statement_id, evidence_mapping_id, evidence_version_id)`; because nullable uniqueness has PostgreSQL semantics, implementation must decide whether to use a partial unique index for null version rows or use a normalized non-null version strategy.
- Index `(evidence_mapping_id)` and `(impact_statement_id)`.
- CHECK `relationship_type` is one of the supported values.

Application validation must ensure that the evidence mapping belongs to the same goal as the impact statement, and that the optional evidence version belongs to the evidence referenced by that mapping. The current schema does not expose a composite FK for this full relationship; do not assume separate FKs prove the relationship is consistent.

### 4.4 `impact_statement_assessments`

Stores versioned perspectives on an impact statement. This is deliberately separate from the existing `impact_assessments` table.

Perspectives:

- `EMPLOYEE`: employee's self-assessment.
- `AI`: generated recommendation/interpretation.
- `MANAGER`: manager's assessment of the claimed outcome and contribution.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key |
| `impact_statement_id` | `VARCHAR(64)` | No | FK to `impact_statements.id` |
| `perspective` | `VARCHAR(20)` | No | `EMPLOYEE`, `AI`, `MANAGER` |
| `version` | `INTEGER` | No | Incrementing version per statement and perspective |
| `status` | `VARCHAR(30)` | No | Perspective-specific lifecycle value |
| `assessment_summary` | `TEXT` | No | Assessment of the outcome/impact |
| `rationale` | `TEXT` | Yes | Explanation and supporting reasoning |
| `reviewed_by_user_id` | `VARCHAR(64)` | Yes | Manager/reviewer identity for MANAGER; null for employee/AI |
| `model_version` | `VARCHAR(200)` | Yes | AI provenance when perspective is AI |
| `prompt_version` | `VARCHAR(100)` | Yes | AI provenance when perspective is AI |
| `supersedes_assessment_id` | `VARCHAR(64)` | Yes | Previous version, if any |
| `created_by_user_id` | `VARCHAR(64)` | No | Actor creating this version |
| `created_at` | `TIMESTAMPTZ` | No | Creation time |

Suggested status values:

| Perspective | Allowed statuses |
|---|---|
| EMPLOYEE | `DRAFT`, `SUBMITTED`, `WITHDRAWN` |
| AI | `GENERATED`, `SUPERSEDED`, `FAILED` |
| MANAGER | `DRAFT`, `ACCEPTED`, `NEEDS_REVIEW`, `NOT_ACCEPTED` |

Constraints and indexes:

- FK to statement with `ON DELETE RESTRICT`.
- FK `reviewed_by_user_id` and `created_by_user_id` to `users(id)` with `ON DELETE RESTRICT`.
- Self-FK `supersedes_assessment_id` to this table with `ON DELETE RESTRICT`.
- Unique `(impact_statement_id, perspective, version)`.
- CHECK `version > 0`.
- CHECK perspective is one of `EMPLOYEE`, `AI`, `MANAGER`.
- CHECK status belongs to the agreed status set; add a perspective/status consistency check in SQL or enforce it in the domain service.
- Index `(impact_statement_id, perspective, version DESC)`.
- Index `(perspective, status, created_at DESC)`.

Important business rules:

- The employee's submitted version is immutable. Editing creates a new version.
- AI output is advisory and must not set manager status.
- A manager assessment is separate from evidence approval. `ACCEPTED` here means the manager accepts the impact interpretation, not merely that the evidence item was approved.
- A manager assessment should not be treated as validated if its supporting evidence is not eligible under the agreed evidence policy. The service must evaluate the current evidence approval state and record the source context used.
- Manager authorization must be checked against `users.reporting_manager_id` and applicable organization access rules in the service layer.

### 4.5 `impact_assessment_measurements`

Stores structured metrics for one specific assessment version. This avoids placing multiple metric values into a single JSON field and allows the employee and manager to record different interpretations or measurements.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key |
| `impact_statement_assessment_id` | `VARCHAR(64)` | No | FK to `impact_statement_assessments.id` |
| `metric_name` | `VARCHAR(200)` | No | E.g. API response time |
| `baseline_value` | `NUMERIC(20,6)` | Yes | Baseline value |
| `target_value` | `NUMERIC(20,6)` | Yes | Target value |
| `actual_value` | `NUMERIC(20,6)` | Yes | Observed value |
| `unit` | `VARCHAR(50)` | No | E.g. ms, %, requests/sec, INR |
| `measurement_method` | `TEXT` | Yes | How the measurement was calculated |
| `measurement_source` | `VARCHAR(500)` | Yes | Source/report/system reference |
| `measurement_period_start` | `DATE` | Yes | Start of measurement window |
| `measurement_period_end` | `DATE` | Yes | End of measurement window |
| `created_at` | `TIMESTAMPTZ` | No | Creation time |

Constraints and indexes:

- FK to assessment with `ON DELETE RESTRICT`.
- CHECK at least one of baseline, target or actual is populated.
- CHECK period end is not before period start when both are populated.
- Index `(impact_statement_assessment_id)`.

Do not store a display string such as `40% reduction` as the only metric. Store numeric values and the unit separately. The direction and formula used to derive improvement must be represented in the measurement method or a later explicit metric-definition model; do not assume higher is always better.

### 4.6 `impact_assessment_attributions`

Stores how an employee or other internal contributor participated in the outcome, for a particular assessment perspective/version.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key |
| `impact_statement_assessment_id` | `VARCHAR(64)` | No | FK to assessment version |
| `contributor_user_id` | `VARCHAR(64)` | No | FK to `users.id` |
| `contribution_type` | `VARCHAR(30)` | No | `DIRECT`, `SHARED`, `LEADERSHIP`, `ENABLING`, `INDIRECT` |
| `contribution_description` | `TEXT` | Yes | Specific contribution description |
| `allocation_percentage` | `NUMERIC(5,2)` | Yes | Optional allocation; 0–100 only when defensible |
| `created_at` | `TIMESTAMPTZ` | No | Creation time |

Constraints and indexes:

- FK to assessment and contributor with `ON DELETE RESTRICT`.
- CHECK contribution type belongs to the controlled set.
- CHECK allocation is null or between 0 and 100.
- Unique `(impact_statement_assessment_id, contributor_user_id, contribution_type)`.
- Index `(contributor_user_id)`.

Allocation percentages are optional. The system must not require artificial percentages when the contribution cannot be defensibly quantified. If percentages are supplied for a shared outcome, service validation should ensure the chosen allocation policy is followed and prevent totals above 100% where the business rule requires it.

### 4.7 `impact_statement_role_expectations`

Links an impact statement to the existing organization role responsibility or competency it demonstrates. This powers the Role Impact view without copying role catalogue text into M7.

Proposed columns:

| Column | Type | Null | Notes |
|---|---|---:|---|
| `id` | `VARCHAR(64)` | No | Primary key |
| `impact_statement_id` | `VARCHAR(64)` | No | FK to `impact_statements.id` |
| `role_responsibility_id` | `VARCHAR(64)` | Yes | FK to `organization_role_responsibilities.id` |
| `role_competency_id` | `VARCHAR(64)` | Yes | FK to `organization_role_competencies.id` |
| `created_at` | `TIMESTAMPTZ` | No | Creation time |

Constraints and indexes:

- FK to statement and both role catalogue tables with `ON DELETE RESTRICT`.
- CHECK exactly one of `role_responsibility_id` or `role_competency_id` is populated.
- Unique statement/responsibility and statement/competency relationships (implemented as separate partial unique indexes).
- Index on each role reference.

The service must verify that the referenced role belongs to the employee's organization and applicable role assignment. The current schema has no normalized user-to-organization-role assignment; this proposal does not infer that `users.role` text is a stable FK.

## 5. Relationship overview

```text
users (employee)
  └── impact_analyses (one employee + date range)
        └── impact_statements
              ├── goals
              │     └── milestones (optional context)
              ├── impact_statement_evidence
              │     └── evidence_mappings
              │           ├── evidence
              │           ├── evidence_versions (optional pinned version)
              │           └── evidence_approvals (current manager evidence decision)
              ├── impact_statement_assessments
              │     ├── perspective: EMPLOYEE / AI / MANAGER
              │     ├── impact_assessment_measurements
              │     └── impact_assessment_attributions
              └── impact_statement_role_expectations
                    ├── organization_role_responsibilities
                    └── organization_role_competencies
```

Existing `impact_assessments` remains separate:

```text
evidence + goal
   └── impact_assessments (existing AI evidence-level analysis)

impact_statement
   └── impact_statement_assessments (new M7 employee / AI / manager versions)
```

## 6. Evidence approval and impact validation – separate data concepts

The current `evidence_approvals` table is authoritative for a manager's evidence-mapping decision.

| Evidence approval state | Employee-facing label | M7 treatment |
|---|---|---|
| `PENDING` | Pending | Visible; not manager-validated |
| `APPROVED` | Approved | Eligible to support manager-validated impact, subject to relevance and measurement checks |
| `NEEDS_INFORMATION` | Needs Review | Visible with manager comment; not manager-validated until resolved |
| `REJECTED` | Not Approved | Visible with manager comment; excluded from manager-validated impact |

M7 manager impact assessment has its own lifecycle (`DRAFT`, `ACCEPTED`, `NEEDS_REVIEW`, `NOT_ACCEPTED`). These are not aliases for evidence approval statuses.

The existing `evidence_approvals` record is unique per mapping and can be reset to `PENDING` when an employee resubmits. `notification_history` captures decision/resubmission events. If M7 requires a formally immutable, queryable evidence-review audit independent of notifications, design a dedicated evidence approval event table as a separate cross-cutting schema change. Do not silently rely on the current mutable approval row as a complete historical ledger.

## 7. Impact dimensions and contribution types

### 7.1 Impact dimensions

Use a controlled `VARCHAR` plus CHECK constraint initially, to avoid creating an inflexible PostgreSQL enum while the product taxonomy is still being validated.

Proposed values:

- `FINANCIAL`
- `OPERATIONAL`
- `CUSTOMER`
- `QUALITY`
- `TECHNICAL`
- `STRATEGIC`
- `PEOPLE`
- `RISK`

Existing `impact_type` values in `impact_assessments` remain unchanged. A future mapping between legacy AI categories (`PERFORMANCE`, `AUTOMATION`, `LEADERSHIP`, `MENTORING`, etc.) and M7 dimensions should be explicit in application/domain logic or a governed mapping table, not silently assumed to be one-to-one.

### 7.2 Contribution types

- `DIRECT`
- `SHARED`
- `LEADERSHIP`
- `ENABLING`
- `INDIRECT`

## 8. Tables explicitly not proposed in this change

| Table/concept | Reason |
|---|---|
| New `evidence` table | Already exists; duplicating would split the source of truth |
| New `evidence_approvals` table | Existing manager evidence workflow is authoritative |
| New `achievements` table | No dedicated achievement entity exists today; M7 uses impact statements linked to goals/evidence until a separate achievement domain is agreed |
| New `performance_periods` table | No shared cycle entity exists today; use date range on `impact_analyses` initially |
| New `impact_assessments` table with the same name | Existing table already stores AI evidence-goal assessments; new perspective-specific records use `impact_statement_assessments` |
| New role catalogue tables | Existing organization role/responsibility/competency catalogue is reusable |
| New report storage for impact calculations | `reports` remains a presentation/output concern; normalized M7 data is the source of truth |

## 9. Migration implementation plan

Migrations must be added only after the design is approved. Do not edit existing migrations.

Suggested migration grouping:

1. `V<timestamp>__create_impact_analysis_core.sql`
   - Create `impact_analyses`.
   - Create `impact_statements`.
   - Create `impact_statement_evidence`.
   - Add required indexes, FKs and CHECK constraints.
2. `V<timestamp>__create_impact_statement_assessments.sql`
   - Create `impact_statement_assessments`.
   - Create `impact_assessment_measurements`.
   - Create `impact_assessment_attributions`.
3. `V<timestamp>__link_impact_statements_to_role_expectations.sql`
   - Create `impact_statement_role_expectations`.

The final migration split can be adjusted to match review and deployment needs. Use the repository helper:

```bash
./scripts/db/new_migration.sh "create impact analysis core"
```

Then validate and apply locally:

```bash
./scripts/db/validate.sh
./scripts/db/migrate.sh
./scripts/db/status.sh
```

Do not include `BEGIN`/`COMMIT` wrappers; Flyway manages migration transactions. Keep all SQL changes in `myimpact-db` and update the corresponding SQLAlchemy models in `myimpact-ai` in the coordinated implementation workstream.

## 10. Data integrity, authorization and audit requirements

- `impact_analyses.employee_user_id` must be the authenticated employee for employee self-service operations.
- A manager can assess an employee only when authorized by the current reporting relationship and organization policy.
- The application must verify that a statement's goal belongs to the employee represented by its parent impact analysis.
- The application must verify evidence mapping/goal consistency and evidence-version/mapping consistency.
- The application must verify role expectation organization scope.
- Employee, AI and manager assessment versions must not be silently overwritten.
- Manager assessment records must identify the manager actor and timestamp.
- AI assessments must preserve model and prompt provenance when generated by an LLM.
- Source evidence versions used by an assessment must be pinned where the evidence content version is material to the conclusion.
- Evidence review status must be read from `evidence_approvals`; M7 must not maintain a second status column that can drift.
- Do not cascade-delete finalized analysis or assessment history when a user, goal or source record is removed. Align retention and anonymization policy before implementing destructive operations.
- Tenant and organization authorization must be enforced by the application. Foreign keys alone do not provide tenant isolation.

## 11. Query and index requirements

The schema should support these primary access patterns:

1. List impact analyses for an employee ordered by period.
2. Load an employee's impact analysis and statements for a period.
3. Load all evidence mappings and current approval statuses for an impact statement.
4. Load the latest employee, AI and manager assessment versions for a statement.
5. Load measurement and attribution rows for an assessment version.
6. Find impact statements associated with a role responsibility or competency.
7. Load manager's pending/accepted impact assessments for employees in the reporting hierarchy, subject to authorization.

At minimum, implement the indexes specified with each table. Add further indexes only after checking query plans and real access patterns; avoid indexing every status or timestamp column by default.

## 12. Rollback and migration safety

- Existing migrations are immutable; all M7 schema changes are additive.
- No existing rows should be rewritten as manager-validated impact during migration.
- Do not backfill employee/manager assessments from legacy `impact_assessments` automatically. Legacy records are AI/evidence-level outputs and do not prove an employee or manager made that assessment.
- If any backfill is later required, mark the origin explicitly as legacy/imported and preserve original identifiers and timestamps.
- Avoid destructive enum changes. Controlled text + CHECK constraints are preferred for new M7 classifications during initial rollout.
- Validate migrations against both a fresh database and an upgraded database containing representative demo data.
- Rollback strategy should prefer a forward corrective migration. Dropping new M7 tables is acceptable only before M7 data is persisted and after confirming no dependent application version is deployed.

## 13. Database acceptance criteria for M7.1

M7.1 database design is ready for implementation when:

1. Existing table reuse decisions in section 2 are confirmed against the latest schema.
2. Product owners approve the distinction between impact statements and achievements.
3. Product owners approve the initial date-range performance-period model.
4. Employee, AI and manager assessment perspectives and status lifecycles are agreed.
5. Evidence approval and impact validation remain separate.
6. Proposed tables, columns, constraints and indexes are reviewed.
7. Role expectation links are confirmed against the existing organization role catalogue.
8. The evidence-review history limitation is explicitly accepted or addressed by a separate design.
9. Migration naming and validation follow the `myimpact-db` repository conventions.
10. Coordinated SQLAlchemy model and repository changes are planned for `myimpact-ai`.

## 14. Open decisions before creating Flyway migrations

| Decision | Proposed default | Needs approval |
|---|---|---|
| Is `impact_statement` the M7 outcome/claim entity, or should a separate Achievement domain be designed first? | Use `impact_statement` now; do not equate it with milestone | Yes |
| How are performance periods named and governed? | Store employee-specific start/end dates in `impact_analyses` initially | Yes |
| Can a manager revise an accepted impact assessment? | Create a new manager assessment version and preserve the old one | Yes |
| Should manager impact acceptance require all supporting evidence to be `APPROVED`? | Yes for manager-validated impact; employee self-assessment remains visible regardless | Yes |
| Should evidence review history move from notification metadata to a dedicated immutable event table? | Keep current workflow for M7 initial integration; decide whether separate cross-cutting change is needed | Yes |
| How are employees assigned to organization role catalogue entries? | Do not infer from free-text `users.role`; define/confirm role assignment before strict role-coverage enforcement | Yes |
| Is quantitative impact scoring required in M7 initial release? | No universal score; persist metric facts and separate assessments | Yes |

---

**Document status:** Proposed M7 database design based on the uploaded 8 November 2026 repository snapshots. No database migration has been created or applied by this document. The next step is product/domain review of section 14, followed by a reviewed DDL implementation plan.
