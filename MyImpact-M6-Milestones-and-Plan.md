# MyImpact — M6 Milestones and Delivery Plan

**Document status:** Working plan; current M6.1–M6.5 validation passed on 24 October; expanded identity and admin scope is included; M7 release readiness remains open
**Last known checkpoint:** 24 October 2026  
**Purpose:** Capture M6 scope, last known implementation state, remaining work, and validation needed before milestones are considered complete.

> **Status caveat:** Current M6.1–M6.5 build, browser, backend, and migration checks passed on 24 October 2026. M6.4 is complete for goal/document ingestion; evidence association is covered by M6.5. M6.6 implementation is in progress and unvalidated for release; M6.7–M6.8 and M6.10 remain planned or unvalidated. M6.9 implementation is present, but its integrated admin/organization flows are not validated. M7 release readiness is open.

## 1. M6 overview

| Milestone | Scope | Last known status | Remaining work |
|---|---|---|---|
| M6.1 | Frontend foundation and API integration | Validated on 24 October: production build, auth/browser flows, and live API integration through document ingestion | None for M6.1; integrated E2E validation remains M6.10 |
| M6.2 | Dashboard | Validated on 24 October: empty, partial-progress, capped progress, and API-error browser scenarios | None for M6.2; integrated E2E validation remains M6.10 |
| M6.3 | Goals and Expectations | Current backend suite and browser CRUD, scopes, lifecycle, assessment, and import checks passed on 24 October | Known limitation: lexical duplicate matching may miss semantic paraphrases |
| M6.4 | Goal/document ingestion | Live-stack DOCX upload, extraction, provenance, idempotency, correction, approval, and activation passed on 24 October | M6.4 is scoped to goal/document ingestion; evidence association is validated under M6.5 |
| M6.5 | Goal/milestone evidence association | Current API/browser checks and the association migration passed on 24 October | None for M6.5; M6.6 adds AI-generated goal criteria and evidence-based assessment |
| M6.6 | Goal criteria and evidence-based assessment | Product decisions finalized; implementation in progress; release acceptance not confirmed | Implement versioned criteria, evidence assessments, lifecycle/history, deterministic progress, shared UI, source freshness, and AI evaluation |
| M6.7 | Impact Analysis | Planning scope: analyze validated goal assessments and traceable evidence; implementation and acceptance criteria are not confirmed complete | Define reporting periods, aggregation, source traceability, privacy, and uncertainty; implement and validate the Impact Analysis experience |
| M6.8 | 1:1 and Career Reports | Planned; acceptance criteria and implementation are not confirmed complete | Define report periods, privacy/versioning/export; implement user-owned briefs and career reports using validated M6.6/M6.7 results |
| M6.9 | Admin Portal and Platform Access | Implementation, API, UI and migrations are present; integrated validation is not recorded | Validate authentication, organization/profile relationships, platform-admin access and admin workflows |
| M6.10 | End-to-End UX Validation | Not confirmed complete | Run integrated validation across all committed M6.1–M6.9 scope |
| M7 | Release Readiness | Not confirmed complete | Complete operational, deployment, documentation, and release go/no-go checks after M6.10 |

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

Keep calculated assessment state separate from goal lifecycle. The current M6.3 implementation uses counts of evidence with linked impact and a target of three to calculate assessment/progress. That is the legacy model, not the product definition going forward; revise its labels and calculation so evidence records are not presented as separate achievements. M6.6 replaces that model with AI-proposed, employee-approved goal criteria and source-grounded evidence-to-criterion assessments. AI assesses all submitted evidence, while the evidence review state remains visible and AI conclusions are never presented as manager-verified achievements. The backend owns deterministic progress and aggregate calculations; AI suggestions are not achievements and must not change goal lifecycle. M6.6 criterion types, progress formulas, confirmation behavior, and evidence-review distinctions are finalized in [M6.6-README.md](./docs/milestones/M6.6-README.md).

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
- The Admin Portal and Platform Access scope is tracked in M6.9. M6.10 is the integrated E2E milestone; M7 owns release readiness. AI Assistant is not in the current M6/M7 scope.

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
- [ ] In M6.6, replace legacy evidence-count guidance with AI-generated, employee-approved goal criteria and evidence-based criterion assessments; treat completed goals as achievements, not evidence records.
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

## 8. M6.6 — Goal Criteria Generation and Evidence-Based Assessment

**Intended outcome:** Put AI-assisted criteria generation and evidence assessment into the existing Goals workflow. M6.7 adds a separate Impact Analysis experience that can aggregate validated goal assessments and cross-goal patterns.

Implementation breakdown: [M6.6 Technical Plan](./docs/milestones/M6.6-TECHNICAL-PLAN.md).

### Current foundation and gap

- Reuse goals, lifecycle status, linked evidence, impact assessments and reporting-period data. A completed goal is itself an achievement; do not create a separate achievement entity.

### Proposed first release

### Criteria and evidence assessment

1. When an employee creates a goal, AI proposes observable or measurable criteria. The employee can edit, add, remove, and approve them.
2. Reuse existing evidence records and supported ingestion/retrieval. External content is fetched only through authorized, supported APIs; unavailable sources must show their limitation.
3. AI proposes evidence-to-criterion matches and status/progress with rationale, source references, confidence, and uncertainty. Validate every criterion/evidence ID and user authorization before recording decisions.
4. AI assesses all submitted evidence regardless of manager-review state. Keep evidence attachment, AI assessment, optional employee confirmation, and manager review separate; attaching or accepting evidence does not itself mean a criterion is met.
5. Store provenance/version information so changes to criteria or evidence do not silently rewrite prior assessments. Show freshness and failures explicitly.
6. Use one backend assessment engine for Goal detail and the Goals page. The backend computes deterministic criterion progress and aggregate results using the finalized M6.6 criterion types and formulas, with equal criterion and milestone weights by default.
7. Keep the separate Impact Analysis experience in M6.7, where it may aggregate validated goal assessments and cross-goal patterns.

### M6.6 decisions and acceptance checks

- [x] AI assesses all submitted evidence, independently of manager-review state; AI assessment, employee confirmation, and manager review remain distinct.
- [x] Define criterion result states separately from `CURRENT`, `STALE`, and `OBSOLETE` assessment lifecycle states.
- [x] Make employee confirmation optional for routine assessments; retain AI proposals when employees correct or challenge them.
- [x] Define binary, milestone-based, and measurable-target criteria, with equal milestone/criterion weights by default and deterministic backend progress.
- [x] Version criteria; material edits obsolete prior assessments and trigger reassessment without overwriting history.
- [x] Define source freshness/access tracking, targeted invalidation, immutable history, and AI evaluation measures.
- [ ] Validate model-referenced criterion/evidence IDs and authorization; handle provider failures and invalid outputs explicitly.
- [ ] Implement API/service, UI, integration, and AI-evaluation tests for traceability, freshness, uncertainty, versioning, and access boundaries.

**M6.6 definition of done:** Employees can create a goal, approve AI-proposed criteria, attach supported evidence, and inspect source-linked AI assessments for each criterion. Goal detail and the Goals page reuse one assessment engine and deterministic progress/aggregation. Evidence review state, employee confirmation, manager review, uncertainty, stale/obsolete assessments, and history are explicit; access is enforced; and backend, UI, integration, and AI-evaluation tests validate the workflow against thresholds established from a human-reviewed dataset.

## 9. M6.7 — Impact Analysis

**Intended outcome:** Help employees understand progress and impact across their goals by analyzing validated M6.6 criterion assessments and their traceable evidence. Impact Analysis summarizes existing goal/evidence data; it does not create evidence or replace criterion-level decisions.

### Proposed scope

- Summarize goal and criterion progress for a user-selected reporting period, with source links to validated assessments and evidence.
- Make evidence gaps, uncertainty, stale assessments, and out-of-period sources explicit.
- Separate source facts, deterministic aggregation, and any generated narrative; do not invent achievements or imply performance ratings.
- Reuse M6.6 assessment and authorization rules; do not add a second evidence store or independent goal-scoring system.
- Keep the initial experience employee-scoped. Manager sharing, organization-wide analytics, and predictive performance decisions require separate approval.

### Decisions and acceptance checks

- [ ] Confirm reporting periods, analysis views, and whether narrative generation is in scope.
- [ ] Define how criterion assessments are aggregated across goals without introducing unapproved scoring or weights.
- [ ] Preserve source references, assessment versions, source dates, and access boundaries in every result.
- [ ] Handle empty periods, weak evidence, stale assessments, and analysis/provider failures explicitly.
- [ ] Add focused API/service/UI and end-to-end tests for traceability, authorization, period filtering, and uncertainty.

**M6.7 definition of done:** Users can view a period-based, source-linked analysis of validated goal assessments. It distinguishes evidence from generated explanation, surfaces gaps and uncertainty, respects owner access, and does not create or modify source records.

## 10. M6.8 — 1:1 and Career Reports

**Intended outcome:** Turn M6.6 goal assessments and M6.7 Impact Analysis into private, reviewable employee-facing 1:1 briefs and career reports. Reports are user-controlled summaries, not new evidence or automatic manager feeds.

See [M6.8-README.md](./docs/milestones/M6.8-README.md) for report scope and acceptance criteria.

**M6.8 definition of done:** Users can create, edit, save, and revisit private 1:1 briefs and career reports from selected periods and authorized source context. Sharing/export is deliberate, unsupported claims are omitted or flagged, source records remain unchanged, and backend/UI/end-to-end tests cover the workflows and privacy boundaries.

## 11. M6.9 — Admin Portal and Platform Access

**Status:** Implementation, API, UI, and migrations are present; integrated validation is not recorded.

Validate authentication, organization/profile relationships, reporting-manager rules, platform-admin access, and admin workflows. See [M6.9-README.md](./docs/milestones/M6.9-README.md) for acceptance criteria and deployment constraints.

## 12. M6.10 — End-to-End UX Validation

**Scope:** Validate the integrated, committed M6 journey across authentication, organization/profile relationships, goals and documents, M6.6 assessment, M6.7 Impact Analysis, M6.8 reports, and M6.9 admin workflows.

**Acceptance checklist**
- [ ] Run the agreed backend, frontend, integration, and browser suites against current source.
- [ ] Validate user journeys across goals, evidence, goal assessment, Impact Analysis, reports, and admin operations.
- [ ] Verify representative no-data, partial-data, error/retry, and authorization paths.
- [ ] Verify cross-user and cross-organization data isolation throughout the integrated journeys.
- [ ] Record environment, exact commands, scenarios, results, and unresolved integration defects.

## 13. M7 — Release Readiness

**Scope:** Make a release go/no-go decision after M6.10 integrated validation is complete.

**Release acceptance checklist**
- [ ] Fresh setup and database migrations work using documented instructions.
- [ ] Seed/demo data loads without enum, migration, or conflict errors.
- [ ] Full backend tests, frontend tests, type-check, and production build pass.
- [ ] API contracts, base URL configuration, CORS, and authentication issuer settings are verified.
- [ ] Production requirements for secrets, signing keys, HTTPS, secure cookies, trusted origins, email verification, and abuse protection are documented and satisfied.
- [ ] Deployment/rollback procedures, monitoring, diagnostics, and support runbooks are ready.
- [ ] Known limitations, deferred scope, and data/privacy boundaries are documented.
- [ ] Final regression evidence and an explicit release go/no-go decision are recorded.

## 14. Recommended execution order

1. **Re-establish baseline:** record the current source revisions, working-tree state, service configuration and applied database migrations across `myimpact-ai`, `myimpact-api`, `myimpact-web` and `myimpact-db`.
2. **Validate M6.1/M6.2:** run builds/tests and smoke-test API integration and dashboard behavior.
3. **Confirm M6.3–M6.5:** retain the recorded results, reconcile M6.4's evidence scope, and include the latest goal/milestone evidence migration in the migration baseline.
4. **Define and implement M6.6:** AI-generated goal criteria and evidence-based assessment in the Goals workflow.
5. **Define and implement M6.7:** source-linked Impact Analysis built on validated goal assessments.
6. **Define and implement M6.8:** private 1:1 preparation and career reports using M6.6/M6.7 results.
7. **Validate M6.9:** test authentication, organization linking, reporting-manager rules, platform-admin authorization and admin workflows end to end.
8. **Run M6.10:** execute integrated end-to-end validation across all committed M6.1–M6.9 scope and record results.
9. **Run M7 last:** complete deployment/operational readiness and record the release go/no-go decision.

## 15. Immediate next actions

- [x] Run the M6.3 small-DOCX upload/extraction smoke test with a configured LLM provider.
- [x] Validate migrations on a disposable test database.
- [x] Verify upload validation limits and JWT-protected authorization/user isolation.
- [x] Reconcile M6.4's goal/document-ingestion boundary with M6.5 evidence association; reserve manager evidence review for the appropriate later scope.
- [x] Revalidate M6.1 and M6.2 against current source.
- [ ] Validate M6.9 authentication, organization/reporting-manager and platform-admin flows, including latest migrations and cross-organization authorization.
- [ ] Implement and validate M6.6 using the finalized evidence, status, progress, versioning, freshness, and evaluation decisions in [M6.6-README.md](./docs/milestones/M6.6-README.md).
- [ ] Define M6.7 Impact Analysis periods, aggregation, source traceability, and uncertainty; then implement and validate.
- [ ] Resolve M6.8 report types, sharing, versioning and export decisions; then implement and validate the 1:1 and career-report workflows.
- [ ] Run M6.10 after all committed M6.6–M6.9 scope is ready for integrated validation.
- [ ] Run M7 release readiness only after M6.10 passes.

## 16. Completion tracking

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
| Full M6 end-to-end flow | Not run | M6.10 integrated validation remains, including M6.7 Impact Analysis, M6.8 reports, and M6.9 admin workflows |
| M7 release readiness | Not run | Release go/no-go checklist remains after M6.10 |

---

**Plan maintenance rule:** Mark a task complete only after it has been checked against the current source and the relevant test/build or acceptance flow has passed. Historical implementation notes are context, not proof of current completion.
