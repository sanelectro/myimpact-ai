# M8 — Test Strategy

**Status:** Proposed test plan  
**Coverage:** Domain, services, APIs, database, AI evaluation, frontend, export and end-to-end workflows.

## 1. Testing principles

- Test business rules deterministically without LLM calls where possible.
- Mock provider boundaries for orchestration tests.
- Keep AI evaluation fixtures versioned and reviewable.
- Validate both fresh database setup and upgrade from existing report data.
- Treat authorization tests as release blockers.
- Do not approve arbitrary numerical AI quality thresholds without human review and documented rationale.

## 2. Domain/unit tests

### Report lifecycle
- Valid and invalid generation transitions.
- Publication requires draft-ready and validation gate.
- Published report immutability.
- Regeneration creates a new version.
- Stale state does not mutate snapshot.

### Request validation
- End date before start date rejected.
- Invalid report-kind/audience combinations rejected.
- Team target required only for team summary.
- Employee cannot override subject identity.

### Context and source references
- Source references contain entity/version identity.
- Null values remain null.
- Pending/rejected states preserved.
- Unauthorized sources excluded.
- Period boundary behavior deterministic.
- Snapshot canonicalization/hash stable.

### Legacy compatibility
- Existing report enum values still parse.
- Legacy report text can still be retrieved.
- Legacy goal-report response shape remains unchanged.

## 3. Service/integration tests

- Context builder aggregates M6 and M7 read models.
- M6 assessment values are consumed, not recomputed.
- M7 employee/AI/manager perspectives remain distinct.
- M6.6 1:1/career capabilities are reused where available.
- Context snapshot is immutable after generation starts.
- Template version selected and pinned.
- LLM timeout and malformed output handled.
- Retry creates separate generation run and does not duplicate report.
- Validation findings are persisted.
- PDF/DOCX artifact references are persisted.
- Storage failure does not publish report.

## 4. API and authorization tests

### Employee
- Can generate/read/list/edit draft/publish/export own report.
- Cannot target another employee by forging body/query ID.
- Cannot access another user's report, context summary, version history or artifact.

### Manager
- Can generate individual report only for authorized reports.
- Can generate team summary only for authorized team.
- Cannot access employees outside reporting scope.
- Team aggregation excludes unauthorized members.
- Manager actor identity is recorded from auth.

### Lifecycle and compatibility
- Cannot edit published report.
- Cannot publish validation-failed report.
- Regenerate creates new version.
- Idempotency key returns same request for same payload.
- Same key with changed payload returns conflict.
- Legacy goal report endpoint remains unchanged.
- Error status codes follow API contract.

## 5. Database tests

- Fresh migrations apply cleanly.
- Upgrade path preserves existing report records.
- Existing enum values remain valid.
- JSONB content schema version is persisted.
- Snapshot/generation/validation/artifact relationships enforce referential integrity.
- Published history is not cascade-deleted.
- Indexes support report list/history queries.
- Concurrent duplicate generation is handled safely.

## 6. AI report evaluation dataset

Start with a small, representative, human-reviewed fixture set for each report kind. Include:
1. Complete source context.
2. No completed goals.
3. Missing impact assessments.
4. Pending evidence.
5. Rejected evidence.
6. Conflicting measurements.
7. Shared contribution.
8. Missing role mapping.
9. Partial period data.
10. No prior 1:1 action items.
11. Team member outside manager scope.
12. Long context requiring bounded selection.

Evaluate:
- Schema validity.
- Factual support.
- Citation/source correctness.
- Completeness relative to available sources.
- Correct treatment of missing/null/conflicting data.
- Perspective separation.
- Neutrality and nonjudgmental language.
- No invented scores, promotion verdicts or unsupported metrics.

Use at least two reviewers for ground-truth adjudication where feasible. Record reviewer, date, rationale and dataset version. Treat automated scores as exploratory until thresholds are approved.

## 7. Export tests

### PDF
- Text is selectable/searchable where expected.
- Page breaks and headers/footers are correct.
- Long tables and sections do not clip.
- Unicode and Indian names render correctly.
- Page numbering and metadata are correct.
- Output checksum and storage metadata match.

### DOCX
- Document opens in supported Word-compatible editors.
- Heading hierarchy and styles are correct.
- Tables, bullets and page breaks are preserved.
- Unicode text is retained.
- Content matches canonical structured report.
- Re-export does not mutate report content.

## 8. Frontend tests

- Report type selection and period validation.
- Manager employee/team selector authorization.
- Loading, empty, error and partial states.
- Generation status and retry behavior.
- Preview section rendering.
- Validation warning display.
- Draft edit restrictions.
- Published report read-only behavior.
- Version history.
- PDF/DOCX download and failed export.
- Accessibility and responsive layout.

## 9. End-to-end scenarios

### Employee performance
1. Employee authenticates.
2. Selects period and Employee Performance.
3. Generation request accepted.
4. Context snapshot created from authorized M6/M7 sources.
5. Report generated and validated.
6. Employee previews and reviews draft.
7. Employee publishes if workflow requires it.
8. PDF and DOCX are downloaded.
9. History shows the correct version.

### Manager individual report
1. Manager authenticates.
2. Selects an authorized direct report.
3. Generates manager report.
4. Report includes only authorized employee data.
5. Manager previews and exports.
6. Attempts to access an out-of-scope employee are denied.

### Team summary
1. Manager selects an authorized team and period.
2. System resolves team membership at the defined snapshot time.
3. Aggregation avoids duplicate shared outcomes.
4. Incomplete source coverage is disclosed.
5. Manager exports summary.
6. Out-of-scope member data is absent.

### Regeneration and history
1. Generate and publish version 1.
2. Update source data.
3. Existing report remains unchanged and may become stale.
4. Regenerate from fresh context.
5. Version 2 links to version 1.
6. Both versions and artifacts remain retrievable subject to access policy.

## 10. Definition of test completion

- All critical authorization and lifecycle tests pass.
- Backend unit and integration tests pass.
- Frontend production build and tests pass.
- Database fresh/upgrade tests pass.
- AI evaluation results and human review notes are recorded.
- PDF/DOCX rendering tests pass.
- Employee, manager and team E2E scenarios pass.
- Known limitations and unapproved thresholds are documented.
