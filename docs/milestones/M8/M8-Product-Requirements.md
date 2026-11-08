# M8 — Product Requirements

**Status:** Proposed; requires product review  
**Scope:** On-demand reports for employee and manager audiences; PDF and DOCX.

## 1. Product objective

Enable employees and authorized managers to turn validated MyImpact information into clear, accurate, reviewable reports for performance reflection, 1:1 discussions and career development.

## 2. Users and permissions

### Employee
- Generate reports for their own profile and reporting period.
- Preview and edit permitted narrative sections in a draft.
- Review source references and validation findings.
- Publish/save and download PDF/DOCX.
- View their own report history.

### Manager
- Generate an individual report only for an employee within their authorized reporting scope.
- Generate a team summary only for teams within authorized scope.
- Review and download reports permitted by organizational policy.
- Cannot impersonate the employee or change source assessment decisions through report operations.

### Platform/organization administrator
- Manage templates only if existing admin authorization supports this capability.
- No broad access to employee report content is implied by template administration.

## 3. Report catalogue and requirements

### 3.1 Employee Performance Report
Required sections:
1. Employee, current role and reporting period.
2. Executive summary.
3. Goals and their existing assessment/progress state.
4. Key achievements or outcome statements from approved M6/M7 representations.
5. Supporting evidence and provenance.
6. Demonstrated impact, including measurements and attribution where present.
7. Incomplete goals, challenges and missing information.
8. Development opportunities, only where supported by existing career insights.

Requirements:
- Distinguish delivery, outcome and demonstrated impact.
- Show the assessment state supplied by M6; do not recompute it.
- Show employee, AI and manager perspectives separately where relevant.
- Every material factual claim must be traceable to source references.

### 3.2 Goal Progress Report
Required sections:
- Reporting period and goal scope.
- Goals grouped by lifecycle/assessment state.
- Progress and milestone information as provided by M6.
- Achievements and evidence coverage.
- Impact information when available from M7.
- Incomplete, at-risk or blocked work.
- Missing/partial data notice.

Requirements:
- Lifecycle status, operational sub-status and assessment state are separate concepts.
- A missing assessment is not equivalent to zero progress.
- Use existing M6 calculation outputs.

### 3.3 1:1 Meeting Brief
Required sections:
- Employee and manager identity as authorized.
- Meeting/reporting period.
- Recent goal progress and achievements.
- Impact highlights.
- Challenges, blockers and support needed.
- Employee-provided discussion topics if available.
- Suggested discussion questions, clearly labeled as AI suggestions.
- Existing follow-up actions only if a trusted source exists.

Requirements:
- Reuse the M6.6 preparation workflow/intelligence where implemented.
- Do not invent previous meeting decisions or action items.
- Keep suggested discussion prompts distinct from agreed actions.
- Allow review/edit before export.

### 3.4 Career Development Report
Required sections:
- Current role and role expectation source.
- Demonstrated strengths and evidence.
- Competency/responsibility coverage, if role mapping is configured.
- Development opportunities and evidence gaps.
- Existing learning/development goals.
- Suggested development priorities and learning actions.

Requirements:
- Reuse M6 career insight data where available.
- Distinguish a demonstrated gap from missing evidence.
- Recommendations are advisory; no automatic promotion-readiness verdict.
- If role assignment or competency catalogue data is unavailable, say so explicitly.

### 3.5 Manager Individual Report
Required sections:
- Employee and period.
- Goal progress and existing assessment state.
- Major achievements and supporting sources.
- M7 impact perspectives and manager validation state.
- Blockers and incomplete work.
- Development themes and discussion points.
- Data completeness and unresolved review items.

Requirements:
- Manager can access only authorized employees.
- Do not merge employee self-assessment, AI analysis and manager assessment into one voice.
- No employee ranking or unsupported performance rating.

### 3.6 Manager Team Summary
Required sections:
- Team and period scope.
- Team goal/progress overview using existing data.
- Employee-level concise summaries.
- Shared outcomes and contribution context.
- Common blockers and dependencies.
- Development themes.
- Coverage and completeness caveats.

Requirements:
- Avoid double-counting a shared impact statement across multiple people.
- Do not calculate an unapproved team score or rank employees.
- Exclude employees outside the manager's permitted scope.
- Use aggregate values only when the denominator and data coverage are clear.

## 4. Common report workflow

1. User opens Reports.
2. User selects report type.
3. User selects reporting period.
4. For manager reports, user selects an authorized employee/team.
5. System validates the request and access.
6. Context builder assembles an immutable generation snapshot.
7. Generation engine creates structured content.
8. Validation checks schema, factual references and completeness.
9. Report is saved as a draft.
10. User previews and edits allowed narrative text.
11. User publishes or saves according to product policy.
12. User downloads PDF or DOCX and can later retrieve history.

Generation is on demand only. No scheduled or background periodic generation is included in this release.

## 5. Functional requirements

- FR-01: Support the six report catalogue types defined in M8 README.
- FR-02: Support employee and manager audiences.
- FR-03: Derive actor identity from authenticated server-side context.
- FR-04: Enforce employee, manager and team authorization on every read/write/download.
- FR-05: Validate reporting period and target scope.
- FR-06: Build a source-bounded context from authorized M6/M7 data.
- FR-07: Preserve source IDs, versions and retrieval timestamps.
- FR-08: Generate schema-conformant structured report content.
- FR-09: Preserve missing, null, pending, rejected and conflicting states.
- FR-10: Validate material factual claims and source references.
- FR-11: Save drafts and preserve immutable published versions.
- FR-12: Support PDF and DOCX export.
- FR-13: Maintain report history and generation metadata.
- FR-14: Provide loading, partial, empty, error and retry UX.
- FR-15: Record audit events for generation, preview, publication and export as required by policy.

## 6. Non-functional requirements

- Security: no cross-user or cross-organization data leakage.
- Reliability: idempotent generation requests and safe retry behavior.
- Explainability: material claims trace to source records.
- Reproducibility: preserve source snapshot, template, prompt and model provenance.
- Performance: long-running generation must not hold an HTTP request open indefinitely; use the project's established background-job pattern if needed.
- Accessibility: report preview, status and charts/tables must be accessible.
- Maintainability: report-specific templates and renderers are pluggable.
- Privacy: avoid storing unnecessary raw source content in report snapshots; store IDs/versions and only the bounded content needed for reproducibility under retention policy.

## 7. UX states

- No report history: explain how to generate the first report.
- No eligible source data: explain why generation cannot proceed or generate a limited report with explicit caveats.
- Partial source data: generate only supported sections and mark missing sections.
- Generating: show progress/status and prevent duplicate clicks.
- Validation failed: show actionable findings; do not mark ready.
- Draft ready: preview and edit.
- Published: immutable version and download options.
- Stale: source data changed since snapshot; explain and offer a new generation.
- Failed: safe error and retry path.

## 8. Acceptance criteria

- Each report type has an approved section schema and template.
- Employee and manager journeys pass authorization tests.
- All material claims have resolvable source references or are clearly labeled as suggestions.
- Report output is honest when data is missing or conflicting.
- A draft can be previewed and edited without changing source goals/evidence/impact data.
- Published report versions cannot be silently overwritten.
- PDF and DOCX preserve section content, tables and source references.
- History shows type, period, audience, version, status, generated time and actor.
