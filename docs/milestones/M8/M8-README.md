# MyImpact M8 — Reporting & Intelligence

**Document status:** Proposed product and engineering scope  
**Version:** 0.1  
**Baseline:** Repository snapshots uploaded 8 November 2026  
**Decision:** On-demand report generation; employee and manager audiences; PDF and DOCX exports.

## 1. Purpose

M8 turns validated, structured MyImpact information into useful, reviewable, traceable reports. It is a reporting and document-generation milestone, not a new goal-assessment, evidence-assessment, impact-assessment or employee-rating engine.

- M6 owns goals, goal assessment, evidence and the earlier 1:1/career insight capabilities.
- M7 owns impact analysis, impact statements, employee/AI/manager impact perspectives, measurements and attribution.
- M8 consumes authorized M6/M7 outputs, assembles a bounded report context, generates structured report content, validates it, and presents it as a draft for review and export.

## 2. Confirmed product decisions

| Decision | Selection |
|---|---|
| Formats | PDF and DOCX |
| Audiences | Employee and manager |
| Generation | On demand |
| Initial report review | Draft / preview before publication or download |
| Scheduling | Out of scope |
| Email distribution | Out of scope |

## 3. Report catalogue

1. Employee Performance Report — consolidated goals, achievements, evidence and demonstrated impact.
2. Goal Progress Report — committed goals, lifecycle/assessment state, progress and incomplete work.
3. 1:1 Meeting Brief — meeting preparation, achievements, blockers and discussion prompts; reuse existing M6.6 capability.
4. Career Development Report — strengths, evidence-backed competency coverage, development gaps and learning recommendations; reuse existing M6 career intelligence.
5. Manager Individual Report — an authorized manager's view of one employee's progress, contributions and discussion areas.
6. Manager Team Summary — authorized team-level roll-up, with careful aggregation and no unsupported ranking.

The first four are employee-oriented outputs; manager individual and team reports are manager-oriented. Audience-specific projections must be enforced in the context builder and API, not merely hidden in the UI.

## 4. Sub-phases

| Phase | Name | Main deliverable |
|---|---|---|
| M8.1 | Reporting Foundation & Context Builder | Domain contracts, authorization-aware context and source snapshots |
| M8.2 | AI Report Generation Engine | Versioned templates, structured generation and orchestration |
| M8.3 | Employee Performance Reports | Employee performance and goal progress report types |
| M8.4 | 1:1 Meeting Reports | Reviewable meeting brief and action/discussion section |
| M8.5 | Career Development Reports | Career development report and roadmap |
| M8.6 | Manager Summary Reports | Individual manager report and team summary |
| M8.7 | Report Validation & Traceability | Factual, schema, citation and completeness validation |
| M8.8 | Report History, Export & UI | Versioned report workspace, PDF and DOCX exports |

## 5. Key product and engineering principles

- Reports are generated only from data the requesting actor is authorized to access.
- Employee identity and actor identity are derived from authenticated server-side context; client-supplied user IDs are never trusted as authorization.
- Source systems remain authoritative. M8 does not recalculate M6 goal assessments or M7 impact decisions.
- Employee, AI and manager impact perspectives remain distinct.
- Evidence approval state remains distinct from manager impact validation.
- Missing, null, pending, rejected and conflicting information must not be converted to zero or silently omitted when material.
- AI may summarize and organize source facts but must not invent achievements, outcomes, measurements, decisions or citations.
- Every report generation records the source snapshot, template version, prompt version, model metadata and validation outcome.
- Drafts are reviewable. Publication/download must follow explicit access and product rules.
- Published versions are immutable; regeneration creates a new version.
- PDF/DOCX are presentation artifacts, not the canonical report content store.

## 6. Repository baseline and compatibility notes

The 8 November 2026 source snapshots show:

- `myimpact-ai/app/models/report.py` defines existing report types: `monthly_impact`, `quarterly_impact`, `annual_performance`, `goal_progress`, `promotion_evidence`, `one_to_one`; status values are `current`, `stale`, `archived`.
- `app/db/models/report.py`, `app/repositories/report.py` and `app/services/report.py` provide basic persistence and retrieval around the existing `reports` table.
- `app/api/v1/report.py` contains a goal-scoped report endpoint that synthesizes a goal report from existing impact assessments and career insight service.
- The frontend `/reports` page is currently a placeholder in the inspected snapshot.
- The initial database schema stores report content as `TEXT`; it does not yet represent the full structured report, generation run, context snapshot, validation findings or export artifact lifecycle.

These are baseline observations, not proof that every item remains unchanged in a later checkout. Revalidate current branches and tests before implementation.

### Compatibility rules

1. Preserve existing report enum values and legacy report retrieval behavior.
2. Do not silently repurpose `CURRENT/STALE/ARCHIVED` to mean generation or publication lifecycle.
3. Do not change the legacy `GET /api/v1/goals/{goal_id}/report` response semantics as part of M8.
4. Add a dedicated reporting API surface and migrate consumers deliberately.
5. Review existing generic report CRUD endpoints because they accept user-supplied identity/content in the current baseline; new M8 operations must derive actor identity from authentication.
6. Do not assume a dedicated `achievements` table exists. Resolve current M6 achievement representation through approved contracts.
7. Reuse M6.6 1:1/career work where it exists; do not duplicate its intelligence logic.

## 7. Recommended implementation order

1. M8.1 domain and data contracts, authorization, context builder and source snapshot.
2. M8.2 generation orchestration and structured output.
3. M8.3 employee performance and goal progress.
4. M8.4 1:1 report integration.
5. M8.5 career development report integration.
6. M8.6 manager individual and team reports.
7. M8.7 report validation and evaluation.
8. M8.8 persistence/versioning, exports and frontend completion. Some storage/export groundwork can proceed after contracts stabilize.

## 8. Definition of Done

- All agreed report types can be generated on demand.
- Employee and manager access boundaries are enforced server-side.
- Context snapshots and source references are preserved.
- Structured output conforms to report schemas.
- Factual and citation validation runs before a report is marked ready for review.
- Missing/partial/conflicting data is represented honestly.
- Reports can be previewed, reviewed and exported to PDF and DOCX.
- Report history and immutable published versions work.
- Backend unit/integration tests, frontend tests/build and end-to-end employee/manager flows pass.
- Fresh and upgraded database migration paths are validated.
- Operational logs and error states are useful and do not expose sensitive report content.

## 9. Out of scope

- New employee performance rating or scoring engine.
- Automatic promotion or talent decisions.
- Scheduled report generation.
- Email or external distribution.
- New goal, evidence or impact assessment logic.
- Organization-wide talent analytics beyond the authorized manager team summary.
- Unapproved composite scores or employee rankings.

## 10. Document set

- `M8-Product-Requirements.md`
- `M8-Database-Design.md`
- `M8-Domain-Models.md`
- `M8-API-Contracts.md`
- `M8-Services-and-Business-Rules.md`
- `M8-AI-Prompts-and-Templates.md`
- `M8-Frontend-Design.md`
- `M8-Test-Strategy.md`

**Planning rule:** This package is a proposed design baseline. Do not create or apply migrations, alter production contracts or mark a story complete until the relevant design is reviewed against the current repositories and its acceptance tests pass.
