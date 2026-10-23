# MyImpact — M6 Milestones and Delivery Plan

**Document status:** Working plan; M6.3 automated and browser acceptance checks complete
**Last known checkpoint:** 22 October 2026  
**Purpose:** Capture M6 scope, last known implementation state, remaining work, and validation needed before milestones are considered complete.

> **Status caveat:** M6.3 was revalidated against the current local working copies on 22 October 2026. Other milestone statuses remain historical and have not been freshly validated.

## 1. M6 overview

| Milestone | Scope | Last known status | Remaining work |
|---|---|---|---|
| M6.1 | Frontend foundation and API integration | Reported complete | Re-run frontend build and verify API/CORS integration |
| M6.2 | Dashboard | Reported complete | Validate dashboard against current APIs, data and UX requirements |
| M6.3 | Goals and Expectations | Automated and browser checks complete | Real document extraction with configured LLM; disposable-database migration run; textual duplicate false-positive review |
| M6.4 | Source Documents and Evidence | Pending validation | Confirm document ingestion, evidence linking, review and tests |
| M6.5 | Impact and Career Insights | Not confirmed complete | Define acceptance criteria, implement and validate |
| M6.6 | 1:1 and Career Report | Not confirmed complete | Define acceptance criteria, implement and validate |
| M6.7 | AI Assistant | Not confirmed complete | Define use cases, grounding, usage tracking and validation |
| M6.8 | End-to-End UX Validation | Not confirmed complete | Run integrated acceptance tests and document release readiness |

## 2. Product decisions to preserve

### Goal lifecycle

Use one lifecycle `status`:

`DRAFT → APPROVED → ACTIVE → COMPLETED → ARCHIVED`

Use separate operational `sub_status` values:

- `DRAFT`: `NEEDS_REVIEW`, `READY_FOR_APPROVAL`
- `APPROVED`: `NOT_STARTED`
- `ACTIVE`: `ON_TRACK`, `AT_RISK`, `OFF_TRACK`
- `COMPLETED`: `COMPLETED`
- `ARCHIVED`: `NONE`

Keep calculated assessment state separate from lifecycle and sub-status:

- `NOT_STARTED`
- `IN_PROGRESS`
- `MET_EXPECTATIONS`
- `ABOVE_EXPECTATIONS`

### Assessment and progress rules

A qualifying achievement requires **Achievement + Supporting Evidence + Demonstrated Impact**.

- 0 qualifying achievements → `NOT_STARTED`
- 1–2 → `IN_PROGRESS`
- 3 → `MET_EXPECTATIONS`
- 4+ → `ABOVE_EXPECTATIONS`

Progress = qualifying achievements / 3 × 100. The displayed percentage may exceed 100%; cap the visual progress bar at 100%. Aggregate dashboard progress may be capped at 100%.

### Goal UX requirements
- Keep Achievement → Evidence → Impact together.
- Explain the assessment state and why the goal is at that state.
- Avoid duplicate progress bars, repeated percentages and duplicate impact summaries.
- Assessment colors: Above Expectations = green; Met Expectations = blue; In Progress = purple; Not Started = gray.
- Do not require a next step after a goal is already Above Expectations.
- Goal scopes: `PERSONAL`, `TEAM`, `ORGANIZATION`.
- Admin-managed global/role-based goals are future backlog, not current committed scope.

### Milestones and Source Documents

- Milestones are goal-owned checkpoints with their own `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED` or `BLOCKED` status; they do not change goal lifecycle or assessment.
- The initial milestone slice supports title, description, optional completion criteria and due date through goal-scoped APIs and the goal detail UI.
- The versioned database migration creates a separate `milestones` table with cascade deletion from its parent goal. Applying this migration is required before using the milestone API.
- Evidence continues to use existing evidence records and goal mappings. Direct evidence-to-milestone links are not part of this slice; evidence is not duplicated and milestone completion does not infer impact or meet a goal assessment.
- The navigation label and dashboard area now say **Milestones**. Document ingestion, extracted expectations, retrieval APIs and stored documents remain available; changing the product navigation does not delete those capabilities or their data.

## 3. M6.1 — Frontend Foundation and API Integration

**Scope:** Frontend structure and API client; API integration; API base URL and CORS; loading, empty, error and success states.

**Last known state:** The frontend was able to call the backend after fixing a Vite environment-variable issue and backend CORS configuration. M6.1 was reported complete.

**Acceptance checks**
- [ ] Run the production frontend build.
- [ ] Verify API base URL in local and intended deployment environments.
- [ ] Confirm CORS configuration is environment-safe.
- [ ] Verify authentication/authorization behavior where applicable.
- [ ] Check loading, empty, error and retry states on primary screens.

## 4. M6.2 — Dashboard

**Scope:** Show progress against goals and milestones; surface relevant evidence and impact indicators; support the role/career journey concept; avoid duplicating goal detail content.

**Last known state:** M6.2 was reported complete. Earlier UX feedback asked that the dashboard emphasize the strength of achievement against each goal and the user's role journey.

**Acceptance checks**
- [ ] Validate dashboard API calls against the current backend.
- [ ] Check empty/new-user and partially completed-goal states.
- [ ] Verify assessment/progress calculations against the rules above.
- [ ] Ensure the dashboard is not overloaded with goal-detail content.
- [ ] Confirm responsive layout and error states.
- [ ] Test aggregate calculations and API failure behavior.

## 5. M6.3 — Goals and Expectations

**Scope:** Create/edit/list/view goals; lifecycle and sub-status; achievements with evidence and impact; calculated assessment/progress; document-based goal import; duplicate prevention across imports.

### Last known implementation

- Goal lifecycle and sub-status changes were implemented across backend, database migration and web UI.
- New goals default to `DRAFT`; a test expecting `ACTIVE` was corrected to expect `DRAFT`.
- Goal assessment counts only active evidence and requires linked impact for an achievement to qualify.
- A generic **Add / Import Goal(s)** flow was designed rather than a PDF-only flow.
- The import flow reuses document ingestion/extraction, extracts multiple goals and inferred scope, creates goals as `DRAFT`, and supports review/edit and approval/activation.
- Goal records track `source_document_id`; re-importing the same source document is intended to be idempotent.
- Cross-document duplicate detection was added using deterministic text normalization/similarity and scope-sensitive comparison.
- The API response distinguishes `imported_goals` and `skipped_duplicates`; the UI reports skipped duplicates.

### Validation completed — 22 October 2026

- Backend: **466 tests passed** across the complete unit, integration and end-to-end suite (`python -m pytest -q tests`); the run emitted 6 dependency deprecation warnings. The initial full run exposed an evidence-mapping integration fixture that tried to attach evidence to a default-DRAFT goal; the fixture now activates the goal through the lifecycle API, and the full rerun passed.
- Frontend: **15 unit tests passed**, **3 Playwright acceptance tests passed**, and the TypeScript/Vite production build passed.
- Goal lifecycle browser flow covers create, view, edit, list, all three scopes, and the full lifecycle; matching CRUD, lifecycle, invalid transition, and owner-isolation assertions run against PostgreSQL.
- Goal assessment browser coverage checks dashboard/list/detail consistency, one progress bar, and achievement/evidence/impact presentation; threshold and qualifying-evidence rules are covered by backend unit tests.
- Import browser coverage checks multiple returned draft goals, review/edit, duplicate feedback, all-duplicate and no-goal outcomes, and upload errors. These browser tests use deterministic API fixtures.
- New/changed backend test files passed Ruff and whitespace checks. Existing Ruff findings in older portions of the goal-import unit test module were not changed.
- The local Flyway history reports all migrations through `V20261022140000` successful; the `goals` and `milestones` tables are present with the expected goal lifecycle columns.
- PostgreSQL import integration verifies draft persistence, same-document idempotency, and duplicate skipping across PDF/DOCX source records using deterministic extraction output.
- All 13 SQL migrations were applied successfully to a newly created disposable PostgreSQL database; goal, evidence, and milestone schema was verified.
- Actual document parsing and live external LLM goal extraction remain unverified. Browser upload tests use deterministic API fixtures.

### Remaining implementation and acceptance checks

- [x] Verify manual goal creation starts in `DRAFT`.
- [x] Test transitions `DRAFT → APPROVED → ACTIVE → COMPLETED → ARCHIVED`, including invalid transitions.
- [x] Verify every lifecycle/sub-status pair against the allowed matrix.
- [x] Test assessment thresholds at 0, 1, 2, 3 and 4+ qualifying achievements.
- [x] Verify achievements without active evidence or demonstrated impact do not qualify.
- [x] Verify dashboard, list and detail assessment presentation is consistent for an active goal.
- [x] Verify Personal, Team and Organization scopes through the goal form and list.
- [x] Verify imported goals are persisted as `DRAFT`.
- [x] Verify imported draft goals can be opened and edited.
- [x] Import the exact same document twice and verify no duplicate records are created.
- [x] Import equivalent goals from PDF and DOCX with different filenames and verify duplicates are skipped.
- [x] Test supported textual near-duplicates, unrelated goals and different scopes.
- [x] Verify UI behavior for partial success, all duplicates, no extracted goals and upload failure using browser API fixtures.
- [x] Confirm API response and frontend types agree on `imported_goals` and `skipped_duplicates`.
- [x] Verify goal owner isolation through PostgreSQL-backed API requests and document ownership through a service test.
- [ ] Review duplicate-matching false positives/negatives. Matching is textual similarity, not guaranteed semantic equivalence.
- [ ] Exercise actual document parsing and goal extraction with supported files and a configured LLM provider.
- [x] Apply all migrations to a newly created disposable database and verify goal/evidence/milestone schema.
- [x] Run the complete backend unit, integration and end-to-end test suite.
- [ ] Verify backend upload size/type limits and authorization beyond the current caller-supplied `user_id` boundary.

**M6.3 automated definition of done:** Goal lifecycle, sub-status matrix, CRUD, assessment thresholds, owner-isolation boundary, import persistence/idempotency/deduplication, browser UI states, and frontend/backend regression checks pass. Remaining release checks are real document/LLM extraction and duplicate-quality review; authorization/upload-limit verification is deferred.

## 6. M6.4 — Source Documents and Evidence

**Scope to confirm against current product:** Ingest supported source documents; extract useful expectations and content; link evidence to goals/achievements; let users review/correct extracted information; preserve provenance; make evidence usable by assessment and later insights.

**Last known state:** Earlier project work included document-ingestion pipelines and semantic retrieval, with historical test counts recorded during M3. The M6 import discussion proposed reusing Docling/parser infrastructure and separating generic document processing from goal-specific extraction. M6.4 completion was not confirmed.

**Acceptance checks**
- [ ] Inspect the current source-document/evidence implementation and list what already exists.
- [ ] Confirm supported file types, extraction behavior and failure handling.
- [ ] Validate parsing, normalized content and metadata persistence.
- [ ] Verify evidence can be linked to a goal and specific achievement.
- [ ] Allow users to review extracted evidence before it affects assessment.
- [ ] Verify provenance: source document, extraction status and timestamps.
- [ ] Test duplicate/repeated ingestion, malformed files and empty extraction.
- [ ] Confirm authorization and user data isolation.
- [ ] Add integration tests using representative documents.
- [ ] Confirm only qualifying evidence contributes to assessment.

## 7. M6.5 — Impact and Career Insights

**Intended outcome:** Turn validated goals, achievements, evidence and demonstrated impact into understandable insights about contribution and career progress.

**Work to define/complete**
- [ ] Agree on insight cards, metrics and explanations.
- [ ] Derive impact from evidence rather than unsupported AI assertions.
- [ ] Link every insight to source goals, achievements and evidence.
- [ ] Explain confidence, missing evidence and uncertainty.
- [ ] Avoid double-counting evidence across goals.
- [ ] Implement API contracts and frontend views.
- [ ] Test empty, partial and conflicting data.
- [ ] Verify consistency with goal assessment rules.

## 8. M6.6 — 1:1 and Career Report

**Intended outcome:** Help users prepare for manager 1:1 discussions and create a career report from validated MyImpact data.

**Work to define/complete**
- [ ] Define the 1:1 preparation workflow and editable output.
- [ ] Define report sections and intended audience.
- [ ] Generate summaries from traceable goals, achievements, evidence and impact.
- [ ] Allow review/edit before export or sharing.
- [ ] Make reporting periods and source dates explicit.
- [ ] Handle missing evidence without inventing accomplishments.
- [ ] Implement export/print if in scope.
- [ ] Add API, UI and end-to-end tests.

## 9. M6.7 — AI Assistant

**Intended outcome:** Help users understand goals, identify evidence gaps, improve achievement descriptions and prepare career conversations.

**Work to define/complete**
- [ ] Define supported use cases and boundaries.
- [ ] Ground answers in the user's authorized MyImpact data.
- [ ] Link answers to goals/evidence/documents where possible.
- [ ] Ask for clarification instead of inventing missing details.
- [ ] Add AI usage/token tracking if required.
- [ ] Confirm AI ON/OFF behavior if retained in scope.
- [ ] Handle timeouts, model errors, empty retrieval and low-confidence results.
- [ ] Test authorization and prevent cross-user data leakage.
- [ ] Add evaluations for factuality, relevance and safe failure behavior.

## 10. M6.8 — End-to-End UX Validation and Release Readiness

**Scope:** Validate the complete journey from current data through goal creation, evidence capture, assessment, insights and career outputs.

**Acceptance checklist**
- [ ] Fresh setup and migrations work from documented instructions.
- [ ] Seed/demo data loads without enum or conflict errors.
- [ ] Backend tests pass in the full repository.
- [ ] Frontend build and tests pass.
- [ ] No known API contract mismatches or unresolved CORS issues.
- [ ] Manual goal creation and document import work end to end.
- [ ] Duplicate-import scenarios pass.
- [ ] Goal lifecycle and assessment calculations pass.
- [ ] Evidence links and provenance are correct.
- [ ] Dashboard and goal detail pages agree on status/progress.
- [ ] Loading, empty, error and retry states are covered.
- [ ] Authentication and user-level data isolation are tested.
- [ ] Responsive layout/accessibility receive a basic review.
- [ ] Logs provide useful diagnostics without leaking sensitive content.
- [ ] README/runbook and known limitations are updated.
- [ ] Final regression results are recorded before M6 is marked complete.

## 11. Recommended execution order

1. **Re-establish baseline:** obtain latest `myimpact-ai`, `myimpact-web` and `myimpact-db`; record branches/commits and working-tree state; compare against the latest feature ZIP.
2. **Validate M6.1/M6.2:** run builds/tests and smoke-test API integration and dashboard.
3. **Finish M6.3:** validate lifecycle/assessment, generic import and cross-document duplicate detection.
4. **Complete M6.4:** verify source-document/evidence ingestion, linking, provenance and review.
5. **Define and implement M6.5:** traceable impact and career insights.
6. **Define and implement M6.6:** 1:1 preparation and career report.
7. **Define and implement M6.7:** grounded AI assistant and usage/error handling.
8. **Run M6.8:** end-to-end regression, documentation and release checklist.

## 12. Immediate next actions

- [ ] Run the M6.3 supported-file upload/extraction smoke test with a configured LLM provider.
- [x] Validate migrations on a disposable test database.
- [ ] Verify upload validation limits and authorization beyond the caller-supplied `user_id` boundary.
- [ ] Continue with M6.4 source-document/evidence validation.
- [ ] Revalidate M6.1, M6.2, and M6.4–M6.8 against current source before overall M6 completion.

## 13. Completion tracking

| Check | Result | Evidence / notes |
|---|---|---|
| Full backend test suite | Pass | `python -m pytest -q tests` — 466 passed across unit, integration and end-to-end tests; 6 deprecation warnings |
| Goal API/service/import integrations | Pass | Selected PostgreSQL-backed goal integration tests — 5 passed |
| Playwright goal acceptance | Pass | `npm run test:e2e` — 3 passed; deterministic API fixtures |
| Frontend tests | Pass | `npm test` — 15 passed |
| Frontend production build | Pass | `npm run build` — TypeScript and Vite build passed |
| Database migration history/schema | Pass | All 13 SQL migrations applied to a disposable PostgreSQL database; expected goal/evidence/milestone schema verified; local Flyway history also current |
| Goal lifecycle/assessment | Pass | PostgreSQL-backed CRUD, ownership, full lifecycle, plus full sub-status matrix and threshold unit coverage |
| Same-document import idempotency | Pass | PostgreSQL-backed M6.3 goal import integration |
| Cross-document duplicate detection | Pass, supported textual cases | PostgreSQL-backed PDF/DOCX records; no semantic-quality evaluation |
| Import UI results/errors | Pass, fixture-backed | Partial success, duplicate-only, empty extraction, upload error, draft review/edit |
| Real parsing / external LLM flow | Not run | Requires configured provider and supported document smoke test |
| Disposable-database migration run | Pass | Created a temporary PostgreSQL database, applied all 13 SQL files in order, verified schema, then dropped it |
| Evidence linking/provenance beyond goal display | Not fully re-verified | Wider M6.4 evidence acceptance remains |
| Full M6 end-to-end flow | Not run | M6.8 release validation remains |

---

**Plan maintenance rule:** Mark a task complete only after it has been checked against the current source and the relevant test/build or acceptance flow has passed. Historical implementation notes are context, not proof of current completion.
