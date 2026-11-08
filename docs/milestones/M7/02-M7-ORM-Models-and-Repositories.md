# M7.2 – ORM Models and Repositories

**Target repository:** `myimpact-ai`  
**Database source:** `myimpact-db` M7 migration specification.

## 1. ORM model files

Create SQLAlchemy models under `app/db/models/` corresponding to the seven proposed M7 tables. Use existing `Mapped`, `mapped_column`, `relationship`, `Base` conventions.

| ORM class | Suggested file | Table |
|---|---|---|
| `ImpactAnalysisDB` | `impact_analysis.py` | `impact_analyses` |
| `ImpactStatementDB` | `impact_statement.py` | `impact_statements` |
| `ImpactStatementEvidenceDB` | `impact_statement_evidence.py` | `impact_statement_evidence` |
| `ImpactStatementAssessmentDB` | `impact_statement_assessment.py` | `impact_statement_assessments` |
| `ImpactAssessmentMeasurementDB` | `impact_assessment_measurement.py` | `impact_assessment_measurements` |
| `ImpactAssessmentAttributionDB` | `impact_assessment_attribution.py` | `impact_assessment_attributions` |
| `ImpactStatementRoleExpectationDB` | `impact_statement_role_expectation.py` | `impact_statement_role_expectations` |

Do not name a new ORM class simply `ImpactAssessmentDB`: that name is already used by the existing `impact_assessments` table. Keep the new names explicit.

## 2. Mapping rules

- Map column names and nullability exactly to the approved Flyway migration.
- Use `String(64)` identifiers to match the inspected repository convention unless the DB design is deliberately revised.
- Use timezone-aware timestamps consistently with current ORM conventions.
- Use `Numeric(20, 6)` for measurement values, not floating point, to preserve decimal precision.
- Use Python `Decimal` in Pydantic/domain/API representations for exact numeric measurements.
- Use database CHECK constraints and unique constraints in ORM metadata only where the repository's migration strategy expects metadata parity. Flyway remains the schema authority.
- Explicitly define `ondelete` behavior to match the SQL migration. New performance history should generally use restrictive deletion semantics, not cascade deletion.
- Avoid eager-loading large relationship graphs by default. Use explicit repository query methods or loader options for page-specific reads.

## 3. Relationships

Recommended relationships:

- `ImpactAnalysisDB` → employee (`UserDB`) and statements.
- `ImpactStatementDB` → analysis, goal, optional milestone, statement evidence, assessment versions and role expectation links.
- `ImpactStatementEvidenceDB` → statement, evidence mapping and optional evidence version.
- `ImpactStatementAssessmentDB` → statement, creator, optional reviewer, superseded assessment, measurements and attributions.
- `ImpactAssessmentMeasurementDB` → assessment version.
- `ImpactAssessmentAttributionDB` → assessment version and contributor (`UserDB`).
- `ImpactStatementRoleExpectationDB` → statement, optional organization role responsibility and optional competency.

Avoid bidirectional relationship declarations unless they are needed. If used, ensure `back_populates` names are symmetrical and tested.

## 4. Model registration

Update `app/db/models/__init__.py` to import/register all seven ORM models. Check how `Base.metadata` is loaded in the current app and test discovery. Missing model imports can cause migrations/tests to appear correct while runtime metadata is incomplete.

Do not edit existing `ImpactAssessmentDB` to make it represent an employee-period assessment. Do not change existing evidence approval model semantics.

## 5. Repository layout

Create focused repositories:

```text
app/repositories/
  impact_analysis.py
  impact_statement.py
  impact_statement_evidence.py
  impact_statement_assessment.py
  impact_assessment_measurement.py
  impact_assessment_attribution.py
  impact_statement_role_expectation.py
```

If CRUD for a child entity is always performed as part of its parent aggregate, a repository may expose aggregate operations rather than a public repository for every table. Keep persistence methods cohesive and avoid an over-engineered generic repository layer.

## 6. Required repository operations

### `ImpactAnalysisRepository`

- `get_by_id(analysis_id)`
- `get_for_employee_period(employee_user_id, period_start, period_end)`
- `list_for_employee(employee_user_id, filters, pagination)`
- `create(...)`
- `update_status(...)`
- `get_manager_team_period(manager_user_id, period_start, period_end, filters, pagination)` only if manager scope is validated by a service/query policy.

### `ImpactStatementRepository`

- `get_by_id(statement_id)`
- `list_by_analysis(analysis_id, filters, pagination)`
- `create(...)`
- `update_content(...)` for editable statement fields only
- `archive(...)`
- `get_with_source_context(statement_id)` for a bounded read model.

### `ImpactStatementEvidenceRepository`

- `list_by_statement(statement_id)`
- `add_link(...)`
- `remove_link(...)` only when allowed by history/retention policy
- `get_review_context(statement_id)` joining the existing evidence mapping and current evidence approval state.

Do not write to `evidence_approvals` through this repository.

### `ImpactStatementAssessmentRepository`

- `get_by_id(assessment_id)`
- `list_versions(statement_id, perspective)`
- `get_latest(statement_id, perspective)`
- `create_version(...)`
- `list_for_analysis(analysis_id, perspective/status filters)`

Never update a submitted employee version or prior manager decision in place. A new version supersedes the previous version.

### Measurement / attribution / role expectation repositories

Provide list/add/replace-version operations scoped to a single assessment or statement. Do not expose unscoped bulk updates that can cross employee or organization boundaries.

## 7. Transaction boundaries

The service layer owns transaction boundaries. Repositories should `add`/`flush` and return ORM entities; they should not independently commit. Follow the current `BaseService`/repository convention and ensure a multi-table operation is atomic:

- Create statement + evidence links.
- Submit employee assessment + child measurements + attribution.
- Create manager assessment + child measurements + attribution.
- Finalize analysis and associated state changes.

On failure, roll back the whole unit of work. Do not leave orphan child rows or partially submitted assessment versions.

## 8. Query design

- Overview: one bounded aggregate query for counts/statuses, not N+1 calls per goal.
- By Goals: group statements by goal and include goal title/status plus statement counts.
- Role Impact: join statement role links to role responsibilities/competencies and aggregate linked statement counts.
- Evidence & Reviews: join statement evidence links to existing evidence, mapping, evidence version and current approval state; include review feedback/history where the existing notification/audit model supports it.
- Comparison: fetch latest employee, AI and manager perspective versions side by side.
- Trends: aggregate by analysis period and measurement period; never sum duplicate evidence links as if each were a separate outcome.

Add pagination for statement and review lists. Avoid returning full evidence payloads or all historical assessment versions in summary endpoints.

## 9. Test requirements

- ORM metadata contains all seven tables and expected FK/unique/check constraints.
- Relationships load without mapper errors.
- Repository tests cover ownership scoping, latest-version selection, pagination, status filters, source-version links and transaction rollback.
- Verify no M7 repository mutates `evidence_approvals` or legacy `impact_assessments`.
