# MyImpact — M6 Milestones and Delivery Plan

**Document status:** Working plan; current M6.1–M6.5 validation passed on 24 October; expanded identity and admin scope is included; release readiness remains open
**Last known checkpoint:** 24 October 2026  
**Purpose:** Capture M6 scope, last known implementation state, remaining work, and validation needed before milestones are considered complete.

> **Status caveat:** Current M6.1–M6.5 build, browser, backend, and migration checks passed on 24 October 2026. M6.4 is considered complete for goal/document ingestion; evidence association is covered by M6.5. M6.6–M6.8 and the broader M6.9 admin/organization release flows remain unvalidated.

## 1. M6 overview

| Milestone | Scope | Last known status | Remaining work |
|---|---|---|---|
| M6.1 | Frontend foundation and API integration | Validated on 24 October: production build, auth/browser flows, and live API integration through document ingestion | None for M6.1; full release regression remains M6.8 |
| M6.2 | Dashboard | Validated on 24 October: empty, partial-progress, capped progress, and API-error browser scenarios | None for M6.2; full release regression remains M6.8 |
| M6.3 | Goals and Expectations | Current backend suite and browser CRUD, scopes, lifecycle, assessment, and import checks passed on 24 October | Known limitation: lexical duplicate matching may miss semantic paraphrases |
| M6.4 | Goal/document ingestion | Live-stack DOCX upload, extraction, provenance, idempotency, correction, approval, and activation passed on 24 October | M6.4 is scoped to goal/document ingestion; evidence association is validated under M6.5 |
| M6.5 | Goal/milestone evidence association | Current API/browser checks and the association migration passed on 24 October | None for M6.5; manager review and impact scoring remain M6.6/M6.9 scope |
| M6.6 | Impact Analysis, 1:1 and Career Report | Planned; acceptance criteria and implementation are not confirmed complete | Define manager evidence review and weighted scoring; implement monthly analysis, 1:1 preparation and career reports |
| M6.7 | AI Assistant | Not confirmed complete | Define use cases, grounding, usage tracking and validation |
| M6.8 | End-to-End UX Validation and Release Readiness | Not confirmed complete | Run final integrated acceptance tests across all committed M6 scope |
| M6.9 | Admin Portal and Platform Access | Implementation, API, UI and migrations are present; integrated validation is not recorded | Validate authentication, organization/profile relationships, platform-admin access and admin workflows; M6.8 remains the final release gate |

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

There is no separate Achievement entity in this plan: a goal with lifecycle status `COMPLETED` is itself an achievement. Linked evidence and demonstrated impact support and substantiate the goal outcome; they are not separate achievements.

Keep calculated assessment state separate from goal lifecycle. The current M6.3 implementation uses counts of evidence with linked impact and a target of three to calculate assessment/progress. That is the legacy model, not the product definition going forward; revise its labels and calculation so evidence records are not presented as separate achievements. M6.6 defines the replacement as evidence-based, weighted goal criteria: only employee-submitted evidence accepted by the reporting manager can contribute; AI may propose criterion progress with its supporting evidence and confidence, and the employee confirms a proposed partial value. Milestone and goal scores must follow the same evidence eligibility rule.

### Goal UX requirements
- Present the completed goal as the achievement, with its supporting evidence and demonstrated impact together.
- Explain the assessment state and why the goal is at that state.
- Avoid duplicate progress bars, repeated percentages and duplicate impact summaries.
- Assessment colors: Above Expectations = green; Met Expectations = blue; In Progress = purple; Not Started = gray.
- Do not require a next step after a goal is already Above Expectations.
- Goal scopes: `PERSONAL`, `TEAM`, `ORGANIZATION`.
- Platform administrators are MyImpact operator accounts, distinct from customer-company administrators. Admin access to customer data must be explicitly authorized and covered by cross-organization access tests.

### Authentication, organization profiles and platform administration

- The authentication issuer owns registration, password verification, access-token issuance, refresh-token rotation and logout. Product APIs validate issuer, audience, signature, expiry and required scope.
- Registration requires an organization name. A normalized organization match associates the user with the existing organization; otherwise, registration creates an organization record.
- Users can manage their company, engineering role and reporting manager in My Profile. Reporting-manager choices are organization-scoped and role-validated by the API.
- Organization-scoped goals are linked to the user's company and remain private to that user. Personal and team goals do not carry a company association.
- Platform administrators can review customer users' goals, impact and evidence across companies, invite users, and disable or reactivate accounts. Public registration must never grant platform-admin privileges.
- Before public production use, authentication still requires email verification and abuse protection such as rate limiting and bot controls. Production secrets, issuer URLs, CORS origins and secure-cookie settings must be configured for the deployment environment.
- The new Admin Portal and Platform Access scope is tracked in M6.9. M6.8 remains the final release-readiness gate and must run after the M6.9 flows are included.

### Milestones, Source Documents and Evidence

- Milestones are goal-owned checkpoints with their own `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED` or `BLOCKED` status; they do not change goal lifecycle or assessment.
- The initial milestone slice supports title, description, optional completion criteria and due date through goal-scoped APIs and the goal detail UI.
- The versioned database migration creates a separate `milestones` table with cascade deletion from its parent goal. Applying this migration is required before using the milestone API.
- Evidence uses existing evidence records and goal mappings, with an optional milestone association delivered in M6.5. Evidence is not duplicated; milestone completion does not infer impact or change goal assessment.
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

**Last known state:** M6.2 was reported complete. Earlier UX feedback asked that the dashboard emphasize the strength of completed goal outcomes and the user's role journey.

**Acceptance checks**
- [ ] Validate dashboard API calls against the current backend.
- [ ] Check empty/new-user and partially completed-goal states.
- [ ] Verify assessment/progress calculations against the rules above.
- [ ] Ensure the dashboard is not overloaded with goal-detail content.
- [ ] Confirm responsive layout and error states.
- [ ] Test aggregate calculations and API failure behavior.

## 5. M6.3 — Goals and Expectations

**Scope:** Create/edit/list/view goals; lifecycle and sub-status; goal outcomes supported by evidence and impact; calculated assessment/progress; document-based goal import; duplicate prevention across imports.

### Last known implementation

- Goal lifecycle and sub-status changes were implemented across backend, database migration and web UI.
- New goals default to `DRAFT`; a test expecting `ACTIVE` was corrected to expect `DRAFT`.
- The legacy goal assessment counts active evidence records and linked impact as qualifying achievement units. This behavior was validated, but must be revised to align with the product decision that a completed goal itself is an achievement.
- A generic **Add / Import Goal(s)** flow was designed rather than a PDF-only flow.
- The import flow reuses document ingestion/extraction, extracts multiple goals and inferred scope, creates goals as `DRAFT`, and supports review/edit and approval/activation.
- Goal records track `source_document_id`; re-importing the same source document is intended to be idempotent.
- Cross-document duplicate detection was added using deterministic text normalization/similarity and scope-sensitive comparison.
- The API response distinguishes `imported_goals` and `skipped_duplicates`; the UI reports skipped duplicates.

### Validation completed — 23 October 2026

- Backend: **506 tests passed** across the complete unit, integration and end-to-end suite (`python -m pytest -q tests`); the run emitted 6 dependency deprecation warnings. The separate authentication-service suite passed all 6 tests.
- Frontend: **15 unit tests passed**, **3 Playwright acceptance tests passed**, and the TypeScript/Vite production build passed.
- Goal lifecycle browser flow covers create, view, edit, list, all three scopes, and the full lifecycle; matching CRUD, lifecycle, invalid transition, and owner-isolation assertions run against PostgreSQL.
- Goal assessment browser coverage checks dashboard/list/detail consistency, one progress bar, and goal/evidence/impact presentation; the existing threshold and qualifying-evidence tests cover the legacy model and must be updated with the revised assessment definition.
- Import browser coverage checks multiple returned draft goals, review/edit, duplicate feedback, all-duplicate and no-goal outcomes, and upload errors. These browser tests use deterministic API fixtures.
- New/changed backend test files passed Ruff and whitespace checks. Existing Ruff findings in older portions of the goal-import unit test module were not changed.
- The local Flyway history reports all migrations through `V20261022140000` successful; the `goals` and `milestones` tables are present with the expected goal lifecycle columns.
- PostgreSQL import integration verifies draft persistence, same-document idempotency, and duplicate skipping across PDF/DOCX source records using deterministic extraction output.
- All 13 SQL migrations were applied successfully to a newly created disposable PostgreSQL database; goal, evidence, and milestone schema was verified.
- Generic DOCX extraction through Docling and the Groq LLM service smoke test passed in the backend suite. A new live goal-import smoke test also passed on a small generated DOCX: `DocumentService` uploads and parses it with Docling, then `GoalImportService` uses the configured live provider and persists the extracted team goal as `DRAFT`. Classification is stubbed to isolate goal extraction; browser import tests still use deterministic API fixtures.
- Duplicate-matching review added regressions for conflicting numeric targets, substring collisions (`30` versus `300`), unrelated descriptions under a shared title, near-title matches, and matching descriptions with paraphrased titles. The matcher now avoids those observed false positives and catches the identical-description paraphrase case. Different synonym phrasing and descriptions can still be a false negative; matching remains lexical, not semantic.
- Upload validation now has coverage for PDF/DOCX extensions and media types, the exact 10 MiB boundary, over-limit rejection, empty/unsupported files, and evidence-file type/media combinations. All document upload routes read at most the configured limit plus one byte before rejecting oversized files.
- Authorization verification confirms protected goal access, 401 without a bearer token, 403 when the token's user does not match the requested user, and 404 when that user requests another owner's goal. The integration test uses a locally signed RSA token and a fake JWKS client; it verifies resource-server authorization without making a live HTTP call to the issuer.

### Remaining implementation and acceptance checks

- [x] Verify manual goal creation starts in `DRAFT`.
- [x] Test transitions `DRAFT → APPROVED → ACTIVE → COMPLETED → ARCHIVED`, including invalid transitions.
- [x] Verify every lifecycle/sub-status pair against the allowed matrix.
- [x] Record the legacy assessment thresholds at 0, 1, 2, 3 and 4+ evidence-and-impact units.
- [x] Record that active evidence without demonstrated impact does not qualify under the legacy assessment.
- [ ] In M6.6, replace the legacy evidence-count assessment with weighted goal criteria backed only by employee-submitted, manager-accepted evidence; treat completed goals as achievements, not evidence records.
- [ ] Update assessment API terminology, user-facing guidance and tests as part of M6.6; retain coverage that unreviewed, rejected or unsupported evidence does not strengthen a goal outcome.
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
- [x] Review duplicate-matching false positives/negatives, add regressions for observed collisions and document the remaining semantic-paraphrase limitation.
- [x] Verify generic DOCX parsing and extraction through Docling.
- [x] Verify the configured Groq LLM service with its smoke test.
- [x] Smoke-test upload, Docling parsing and live goal-specific extraction on a small supported DOCX; verify team scope and `DRAFT` persistence. Classification is stubbed.
- [x] Apply all migrations to a newly created disposable database and verify goal/evidence/milestone schema.
- [x] Run the complete backend unit, integration and end-to-end test suite.
- [x] Verify document/evidence upload type and size limits on the API routes, including the exact maximum and over-limit behavior.
- [x] Verify JWT-protected goal access and user-data isolation with signed tokens.

**M6.3 automated definition of done:** Goal lifecycle, sub-status matrix, CRUD, the revised goal-centered assessment rules, authenticated owner isolation, import persistence/idempotency/deduplication, browser UI states, frontend/backend regression checks, upload limits, and a service-level live extraction smoke test pass. The recorded assessment tests currently validate the legacy evidence-count model and need updating before this definition of done is satisfied. The remaining known limitation is that lexical matching may miss semantic paraphrases with different wording.

## 6. M6.4 — Source Documents and Evidence

**Scope to confirm against current product:** Ingest supported source documents; extract useful expectations and content; link evidence directly to goals (and optionally milestones); let users review/correct extracted information; preserve provenance; make evidence usable by assessment and later insights.

**Last known state:** Earlier project work included document-ingestion pipelines and semantic retrieval, with historical test counts recorded during M3. The M6 import discussion proposed reusing Docling/parser infrastructure and separating generic document processing from goal-specific extraction. M6.4 completion was not confirmed.

**Acceptance checks**
- [ ] Inspect the current source-document/evidence implementation and list what already exists.
- [ ] Confirm supported file types, extraction behavior and failure handling.
- [ ] Validate parsing, normalized content and metadata persistence.
- [ ] Verify evidence can be linked to a goal (and optionally one of its milestones), without requiring a separate achievement record.
- [ ] Allow users to review extracted evidence before it affects assessment.
- [ ] Verify provenance: source document, extraction status and timestamps.
- [ ] Test duplicate/repeated ingestion, malformed files and empty extraction.
- [ ] Confirm authorization and user data isolation.
- [ ] Add integration tests using representative documents.
- [ ] Confirm only qualifying evidence contributes to assessment.

## 7. M6.5 — Goal/Milestone Evidence Association

**Intended outcome:** Let users choose whether evidence is attached directly to a goal or to one of that goal's milestones, and make the selected destination visible when listing goal evidence.

**Current state:** Users can attach evidence to a goal or one of its milestones. The association reuses evidence records, is returned by the API, and is protected against cross-goal, archived-milestone and ownership violations. Evidence remains goal-level if an archived milestone is deleted.

**Work and acceptance checks**
- [x] Let users choose direct goal attachment or a milestone belonging to that goal.
- [x] Enforce ownership and reject archived or cross-goal milestone associations.
- [x] Persist the optional milestone association and include it in API responses.
- [x] Reuse evidence records rather than duplicating them to represent milestone associations.
- [x] Preserve evidence as goal-level if its archived milestone is deleted.
- [x] Implement/extend API contracts and frontend views; cover both destination choices with integration and Playwright tests and invalid associations with API tests.
- [x] Keep impact analysis and assessment behavior unchanged; evidence attachment alone must not trigger analysis.

## 8. M6.6 — Impact Analysis, 1:1 and Career Report

**Intended outcome:** Give employees an evidence-grounded view of progress against their goals and expectations, help them identify useful next contributions, prepare for monthly manager 1:1 discussions, and create a reviewable career report. Analysis and reports are not an automatic manager feed.

### Current foundation and gap

- The AI service has a `Report` model with report types for monthly/quarterly impact, annual performance, goal progress, promotion evidence and 1:1; its persistence/API currently stores and retrieves report content.
- The web app exposes `/reports` as a placeholder. The end-to-end user workflow, source-data assembly, grounded generation, editing and export are not confirmed implemented.
- Reuse goals, their lifecycle status, linked evidence, impact assessments and reporting-period data. In this plan, a completed goal is itself an achievement; do not create a separate achievement entity. Do not treat report prose as new evidence or change goal assessment when a report is created or edited.

### Proposed first release

**Impact analysis**

1. Analyze goals monthly against explicit expectations available from the employee's goals, role/company context and manager; preserve the source for each expectation and flag missing or conflicting expectations.
2. Represent expectations as goal criteria with equal weights by default; allow employee/manager-adjusted weights where supported.
3. The employee submits evidence for a goal or milestone. The reporting manager accepts or rejects each submission; rejected or unreviewed evidence does not contribute to a score.
4. AI proposes evidence-to-criterion matches and evidence-based partial progress, with source links and confidence. The employee confirms or corrects a proposed partial value. Calculate the score from criterion weights and confirmed progress backed by manager-accepted evidence; never score an unsupported claim.
5. Explain the result, evidence coverage, gaps and uncertainty. Suggest concrete next contributions tied to unmet criteria, clearly distinguished from completed work.
6. Use the same evidence eligibility and scoring rules for goal and milestone scores. Monthly analysis is the initial period; quarterly and yearly analysis views can follow after the monthly model is validated.

**1:1 preparation**

1. User selects a date range (default to the current month, with the previous preparation date available when useful) and starts a draft.
2. Present a concise employee-facing meeting brief: monthly expectations and progress, completed goals as achievements with source links, active goal/milestone progress, evidence awaiting manager review, blockers or risks, evidence gaps, suggested next contributions, and discussion topics or asks.
3. Let the user edit the brief and add private notes/questions; clearly distinguish user-authored notes and AI suggestions from linked MyImpact facts.
4. Save a user-owned draft/version. Sharing is a deliberate user action; merely generating or saving a brief does not notify or grant access to the manager.

**Career report**

1. User selects a reporting period and report type (initial focus: quarterly impact/career summary; promotion evidence can follow if the core workflow is validated).
2. Generate a structured draft from completed goals (the achievements), other in-period goal progress, linked evidence and impact assessments.
3. Include period boundaries, generation date, source dates and traceable links/references for factual claims.
4. Let the user review, correct, remove or add content before printing/exporting. Clearly flag gaps and omit unsupported claims rather than filling them in.

**Shared behavior and boundaries**

- Keep analysis and reports private to their owner by default. Add only the minimum reporting-manager access needed to review and accept/reject that employee's submitted evidence; this does not grant access to private 1:1 notes or reports. Do not add organization-wide reporting or automatic delivery.
- Keep generated content tied to its source snapshot and period; edits must not rewrite source evidence or assessments.
- Make stale/out-of-date content visible if its source goals or evidence change after generation; regeneration should create a reviewable version rather than silently overwriting user edits.
- Treat export/print as a user-initiated output. Decide whether editable drafts and exported files need separate retention behavior before implementation.
- Keep the first release to user-facing preparation and career summaries. Scheduling, manager collaboration, performance ratings, calibration and predictive promotion recommendations are out of scope unless explicitly added.

### Workstreams and acceptance checks

- [ ] Confirm first-release report types, sections, period defaults and whether an edited report can be regenerated while retaining prior versions.
- [ ] Define expectation sources and criterion creation, including how role/company and manager expectations are reconciled with employee goals.
- [ ] Define evidence-review states, manager authorization, rejection/resubmission behavior, and the audit trail for accepted evidence.
- [ ] Define score calculation, adjusted-weight rules, AI partial-progress proposals, employee confirmation, confidence display and migration from the legacy M6.3 assessment.
- [ ] Define the source-data query and inclusion rules, including completed goals as achievements, archived-goal handling, evidence dates and the user's selected period.
- [ ] Define report content as structured sections rather than relying only on an opaque text blob; preserve report type, period, version, status and generation timestamp.
- [ ] Define 1:1 draft behavior, private notes, manual edits and the user-controlled share/export boundary.
- [ ] Generate summaries from traceable goals, linked evidence and impact; describe completed goals as achievements without introducing a separate achievement record, and distinguish source facts, AI suggestions and user-authored text.
- [ ] Generate next-contribution recommendations from unmet criteria without presenting suggestions as completed work.
- [ ] Make reporting periods and source dates explicit, and identify missing, stale or out-of-period data.
- [ ] Handle empty or weakly supported periods without inventing accomplishments; explain when there is insufficient information.
- [ ] Enforce owner-scoped access for analysis and report flows, and reporting-manager-scoped access only for evidence review.
- [ ] Add a Reports UI for creating, reviewing, editing, saving and revisiting drafts; add print/export only after format and retention are decided.
- [ ] Add API/service tests for evidence approval, scoring, period filtering, source traceability, empty data, versions and access boundaries; add UI and end-to-end coverage for evidence review, analysis, 1:1 preparation and career reports.

### Product decisions to resolve before implementation

- Which expectations should be included in analysis? **Planning direction:** employee goals plus available role/company and manager expectations, with source attribution and explicit gaps where context is unavailable.
- How should the manager evidence review and employee confirmation steps work, including edits, rejection reasons and resubmission? Define before implementation.
- Is the initial career report primarily a quarterly review, an annual review, or a flexible user-selected report? **Planning default:** quarterly, with custom periods supported by the underlying model.
- Should career-report sharing be included now, and if so, what exact recipient/access and revocation behavior is required? **Planning default:** private draft plus explicit user-controlled export; manager access is limited to evidence review.
- Which content must persist as editable report state versus being regenerated from source data? **Planning default:** save a versioned user-reviewed snapshot and retain source references.
- Which export format is required for the first release? **Planning default:** browser print/PDF only if the edited preview is stable; defer integrations and automated delivery.

**M6.6 definition of done:** Goal and milestone scores use only employee-submitted, manager-accepted evidence and the agreed weighted-criteria rules; employees can review AI-proposed partial progress and see its sources and confidence. A user can create and revise a monthly impact analysis, a grounded 1:1 brief and a period-based career report, verify their source context, save/revisit drafts and deliberately produce an output. Unsupported claims are omitted or flagged, access is correctly scoped, and backend/UI/end-to-end tests cover evidence review and both user-facing workflows.

## 9. M6.7 — AI Assistant

**Intended outcome:** Help users understand goals, identify evidence gaps, and improve goal and evidence descriptions. Monthly impact analysis and 1:1/career report generation are covered by M6.6.

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

**Scope:** Validate the complete agreed M6 journey, including authentication, organization/profile relationships, goals and documents, evidence capture, assessment, platform administration, and any committed insight or career outputs.

**Acceptance checklist**
- [ ] Fresh setup and migrations work from documented instructions.
- [ ] Seed/demo data loads without enum or conflict errors.
- [ ] Backend tests pass in the full repository.
- [ ] Frontend build and tests pass.
- [ ] No known API contract mismatches or unresolved CORS issues.
- [ ] Registration, login, token refresh/rotation and logout work through the documented issuer flow.
- [ ] Protected AI/API routes validate the expected issuer, audience, scope and user identity.
- [ ] Organization registration/linking behaves correctly for new and normalized-matching company names.
- [ ] Profile company, role and reporting-manager changes enforce organization and role constraints at the API.
- [ ] Organization-scoped goals are associated with the correct company and remain private to the owning user.
- [ ] Platform-admin privileges cannot be self-assigned through public registration or ordinary user flows.
- [ ] Admin workflows cover authorized cross-company review, invitations, invitation expiry/resend, account disable/reactivation and refresh-session revocation.
- [ ] Non-admin users are denied platform-admin routes and APIs; customer data access is checked across organization boundaries.
- [ ] Deployment configuration documents secure cookies, signing-key handling, trusted origins and the remaining email-verification/abuse-protection requirements.
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

1. **Re-establish baseline:** record the current source revisions, working-tree state, service configuration and applied database migrations across `myimpact-ai`, `myimpact-api`, `myimpact-web` and `myimpact-db`.
2. **Validate M6.1/M6.2:** run builds/tests and smoke-test API integration and dashboard behavior.
3. **Confirm M6.3–M6.5:** retain the recorded results, reconcile M6.4's evidence scope, and include the latest goal/milestone evidence migration in the migration baseline.
4. **Validate M6.9:** test authentication, organization linking, reporting-manager rules, platform-admin authorization and admin workflows end to end.
5. **Define and implement M6.6:** manager-reviewed evidence, weighted impact analysis, monthly 1:1 preparation and career report.
6. **Define and implement M6.7:** grounded AI assistant and usage/error handling.
7. **Run M6.8 last:** execute end-to-end regression across the agreed scope, update documentation and record the release decision.

## 12. Immediate next actions

- [x] Run the M6.3 small-DOCX upload/extraction smoke test with a configured LLM provider.
- [x] Validate migrations on a disposable test database.
- [x] Verify upload validation limits and JWT-protected authorization/user isolation.
- [x] Reconcile M6.4's goal/document-ingestion boundary with M6.5 evidence association; reserve manager evidence review for the appropriate later scope.
- [x] Revalidate M6.1 and M6.2 against current source.
- [ ] Validate the new M6.9 authentication, organization/reporting-manager and platform-admin flows, including latest migrations and cross-organization authorization.
- [ ] Resolve M6.6's evidence-review, scoring, report type, sharing, versioning and export decisions; then implement and validate the agreed MVP. Define and complete M6.7, or explicitly remove it from committed M6 scope.
- [ ] Run M6.8 only after all committed M6 scope, including M6.9, is ready for integrated validation.

## 13. Completion tracking

| Check | Result | Evidence / notes |
|---|---|---|
| Full backend test suite | Pass | `python -m pytest -q tests` — 538 passed; 9 deprecation warnings; run against a fresh disposable PostgreSQL database with all current migrations |
| DOCX and live goal extraction | Pass | `python -m pytest -q tests/integration/services/test_document_extraction.py` — 2 passed; generated DOCX parsed by Docling, then one team goal extracted by the configured provider and persisted as DRAFT; document classification stubbed |
| Goal API/service/import integrations | Pass | Selected PostgreSQL-backed goal integration tests — 5 passed |
| Playwright M6.1–M6.5 acceptance | Pass | `npm run test:e2e:m61-m65` — 11 passed, including the real-stack M6.4 upload/extraction journey |
| Frontend tests | Pass | `npm test` — 25 passed |
| Frontend production build | Pass | `npm run build` — TypeScript and Vite build passed |
| Database migration history/schema | Pass | All 22 current SQL migrations, through `20261024140000`, validated and applied to a fresh disposable PostgreSQL database; existing local database was not changed |
| Goal lifecycle/assessment | Pass | PostgreSQL-backed CRUD, ownership, full lifecycle, plus full sub-status matrix and threshold unit coverage |
| Same-document import idempotency | Pass | PostgreSQL-backed M6.3 goal import integration |
| Cross-document duplicate detection | Pass, reviewed lexical cases | PostgreSQL-backed PDF/DOCX records plus false-positive regressions; synonym paraphrases with different descriptions may be missed |
| Import UI results/errors | Pass, fixture-backed | Partial success, duplicate-only, empty extraction, upload error, draft review/edit |
| Generic DOCX parsing / extraction | Pass | Docling-backed service integration test passed |
| Generic Groq LLM smoke test | Pass | Included in the 538-test backend suite |
| Goal-specific live extraction from a document | Pass, smoke-test scope | Small generated DOCX through service-level upload, Docling and live goal extraction; broader documents and classifier behavior are not covered |
| Upload type and size validation | Pass | PDF/DOCX and evidence allowlists; exactly 10 MiB accepted, larger files rejected on document and evidence upload routes |
| JWT authorization and user isolation | Pass | Protected goal API integration and issuer tests passed within the 538 backend tests; M6.4 browser flow also exercised real registration and protected API access |
| Disposable-database migration run | Pass | Created an isolated validation database, applied all 22 SQL migrations in order, verified the recorded history, then dropped only that temporary database |
| M6.4 document provenance and M6.5 evidence association | Pass | Live-stack document import checks plus backend/API and browser coverage of goal- and milestone-level evidence |
| Authentication issuer registration and sign-in | Pass | Auth issuer tests passed; real-stack M6.4 registration and protected AI API journey passed |
| M6.9 organization/reporting-manager and platform-admin integrated flows | Not recorded | Current profile unit coverage passed, but cross-organization and admin browser journeys remain unvalidated |
| Latest M6.5/M6.9 database migrations | Pass | All 22 current migrations validated and applied on the fresh disposable database; milestone-evidence and organization/team schema are included |
| Full M6 end-to-end flow | Not run | M6.8 release validation remains, including M6.9 |

---

**Plan maintenance rule:** Mark a task complete only after it has been checked against the current source and the relevant test/build or acceptance flow has passed. Historical implementation notes are context, not proof of current completion.
