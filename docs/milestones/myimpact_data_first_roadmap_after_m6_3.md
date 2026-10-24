# MyImpact --- Data-First Roadmap After M6.3

**Status:** Working roadmap; M6.3 and M6.4 validated\
**Starting point:** M6.3 (Goals & Expectations) is at its completion
checkpoint\
**Product principle:** Collect first, organize second, analyze later.

> **M6.5 scope decision (23 October 2026):** The current agreed delivery
> direction is to let users choose whether to attach evidence directly
> to a goal or specifically to one of its milestones. Impact analysis is
> out of scope for M6.5 and remains deferred. This replaces the proposed
> M6.5–M6.7 contribution collection sequence below for the current M6
> delivery plan. See
> [M6.5-README.md](./M6.5-README.md) for the canonical scope. External
> source integrations remain separate future work unless explicitly
> added to scope.

------------------------------------------------------------------------

## 1. Executive summary

MyImpact should help JL4/JL5 employees understand and eventually
demonstrate progress against their Workday goals. Before analyzing
performance, the system needs a trustworthy collection of goals,
contributions, and user-provided work evidence.

The next phase should focus on:

1.  Importing and managing goals.
2.  Collecting source records from engineering and collaboration
    systems.
3.  Accepting user-owned documents and manually recorded work.
4.  Organizing collected data and linking it to goals.
5.  Providing a transparent way to inspect the collected data.

**Defer assessment, impact scoring, gap analysis, and AI-generated
next-step recommendations until the data foundation is reliable.**

This roadmap proposes milestone boundaries. Before implementation,
reconcile them with the existing M6 plan, repository READMEs, API
contracts, database schema, and completed work. Do not renumber
milestones automatically.

## 2. Product objective

A user should be able to open MyImpact and find:

-   Their goals, preserving the original wording and source.
-   Documents uploaded or used to create goals.
-   Contributions collected from connected systems.
-   User-recorded work, accomplishments, and outcomes.
-   Links to original Jira issues, GitHub pull requests, Confluence
    pages, and documents where available.
-   The collection and synchronization status of source data.
-   The ability to add, inspect, and correct goal associations.

The initial experience is a **data collection and organization tool**,
not a performance judge.

## 3. Guiding principles

-   **Goal-centric:** Goals are the main user-facing object.
-   **Data before analysis:** Store and display source facts before
    making performance claims.
-   **Reuse existing capabilities:** Build on the M3 document ingestion,
    embedding storage, and semantic retrieval pipeline where
    appropriate.
-   **Provenance:** Preserve source type, external ID, original link,
    timestamps, and relevant metadata.
-   **Idempotency:** Reprocessing the same source record must not create
    duplicates.
-   **User control:** Extracted goals are drafts until explicitly
    reviewed and approved.
-   **Transparency:** Distinguish imported source facts from
    user-provided statements and AI-generated extraction.
-   **Privacy:** Enforce ownership, source-system permissions, and
    user-level data isolation.
-   **Minimal model:** Add tables or endpoints only where existing
    contracts demonstrably cannot support the requirement.

## 4. Proposed milestone plan (historical proposal; see the M6.5 scope decision above)

These milestones are a suggested structure, not confirmation of the
current repository state.

### M6.3 --- Goals & Expectations: stabilize and close

**Outcome:** Existing goal lifecycle and expectations contracts are
stable enough for subsequent data collection work.

**Current status:** Complete. The lifecycle, assessment, import,
authorization, upload validation, and duplicate-handling checks were
validated on 23 October 2026.

Tasks: - Verify goal creation, editing, approval, and lifecycle
transitions. - Confirm that lifecycle status and achievement status are
separate concepts. - Verify goal ownership and authorization. - Review
existing goal APIs, database models, migrations, and seed data. - Run
backend tests, frontend tests, database checks, and a production
build. - Document existing contracts and known gaps.

**Exit criteria:** - Goal flows work end to end. - Draft goals require
explicit approval before becoming active. - Status values and valid
transitions are documented. - Seed data covers goals with no activity
and varying amounts of associated data. - No known failing tests or
unexplained schema inconsistencies remain.

### M6.4 --- Goal and document ingestion

**Outcome:** Users can create goals manually or import goals from
supported Workday PDF/DOCX documents.

**Current status:** Complete. The upload-to-extraction-to-draft-review
flow was validated on 23 October 2026. The API integration test uses
real DOCX parsing and persistence with deterministic goal extraction;
it verifies provenance, dates and scope, repeat-import idempotency,
user correction, explicit approval, and activation. Existing tests
cover unsupported, empty, oversized, and failed uploads. Live-provider
goal extraction is separately smoke-tested as recorded in the M6
delivery plan. The new test in
`tests/integration/api/test_goal_document_ingestion.py`, the 44 focused
backend tests, and all 3 fixture-based goal-flow Playwright tests passed.
The live-stack Playwright test in
`myimpact-web/e2e/m64-goal-document-ingestion.spec.ts` also passed against
the auth API, AI API, document storage, and configured LLM provider. Run
it with `cd myimpact-web && npm run test:e2e:m64`; it requires the local
database and service environment files to be configured.

Tasks: - Support document upload through existing or newly justified API
contracts. - Preserve the original document or a secure reference to
it. - Extract goal title, description, dates, and scope when
available. - Use Docling or the existing document processing pipeline
where appropriate. - Present extracted goals as editable drafts. - Allow
users to approve drafts explicitly before activation. - Track ingestion
status and actionable processing errors. - Avoid duplicate goal creation
when a document is processed again.

**Exit criteria:** - A supported document can be uploaded and
processed. - Extracted goals are shown for review, not activated
automatically. - Users can correct extraction errors before approval. -
Source provenance is retained. - Empty, malformed, unsupported, and
failed uploads are handled clearly. - Existing M3 ingestion capabilities
are reused where appropriate.

### M6.5 --- Contribution data collection (superseded proposal)

**Outcome:** The system can collect contribution records from an initial
connected source and retain traceable source information.

Candidate sources: - Jira issues and delivery records. - GitHub pull
requests, reviews, and repository activity. - Confluence pages and
technical documents. - Incident and monitoring records.

Tasks: - Inspect available connectors, permissions, and API readiness. -
Select the first source based on usefulness, access, data quality, and
implementation cost. - Define a common representation for source
records. - Store source type, external identifier, original URL,
timestamps, and relevant metadata. - Implement incremental
synchronization where supported. - Make synchronization idempotent. -
Track synchronization status and errors. - Respect source-system
permissions and access boundaries.

**Exit criteria:** - At least one source can be synchronized end to
end. - Each record has traceable provenance. - Repeated synchronization
does not create duplicates. - Failures can be retried and diagnosed. -
The frontend can browse the collected records through backend APIs.

**Scope guardrail:** Do not implement every integration in one
milestone. Validate one source end to end before expanding.

### M6.6 --- User-provided evidence and goal associations (superseded proposal)

**Outcome:** Users can contribute their own work records and documents
and associate them with relevant goals.

Tasks: - Support manual work/contribution entries. - Support user-owned
PDF/DOCX documents and secure file references. - Preserve document
metadata and processing status. - Allow source records and documents to
be associated with goals. - Allow users to inspect and correct
associations. - Preserve the distinction between a raw source record and
a user-entered claim about its significance. - Ensure users can still
provide data when external integrations are unavailable.

**Exit criteria:** - Users can add and inspect their own records. -
Documents and source records can be linked to goals. - Users can correct
associations where permitted. - Source facts, user statements, and
extracted text remain distinguishable. - Authorization and data
isolation are tested.

### M6.7 --- Unified data experience and data-quality validation (superseded proposal)

**Outcome:** Users can inspect all collected information for a goal in
one place.

Tasks: - Display the original goal and its source. - List associated
source records and user-provided documents. - Show dates, source names,
original links, and synchronization status where available. - Provide
useful filtering and chronological browsing. - Show empty, loading, and
error states. - Identify duplicate or unlinked records where
deterministic rules allow. - Provide a way to correct associations. -
Validate realistic data scenarios end to end.

**Exit criteria:** - A user can navigate from the goals list to a goal
and inspect its collected data. - Records retain source attribution. -
The experience works for goals with no associated records and goals with
substantial activity. - Duplicate handling and synchronization failures
are tested. - No performance assessment or impact score is implied by
raw activity counts.

### Later milestone --- Analysis and assessment (superseded deferral)

**Explicitly deferred until the data foundation is reliable.**

Potential future capabilities: - Goal and milestone progress analysis. -
Evidence sufficiency and coverage. - Outcome and impact
interpretation. - Gaps against goal criteria or role expectations. -
Recommended next milestones. - Career insights and assessment snapshots.

Before introducing these capabilities, validate that the collected data
is sufficiently complete, traceable, authorized, and useful.

## 5. Minimal logical data model

Reuse existing database entities if they already represent these
concepts.

  -----------------------------------------------------------------------
  Concept                             Responsibility
  ----------------------------------- -----------------------------------
  **Goal**                            Owner, original goal text, source
                                      reference, scope, period, lifecycle
                                      and achievement status

  **SourceRecord**                    Contribution or record collected
                                      from Jira, GitHub, Confluence, or
                                      another connected system

  **Document**                        Uploaded file or secure file
                                      reference, metadata, and ingestion
                                      status

  **GoalSourceLink**                  Associates a source record with a
                                      goal

  **GoalDocumentLink**                Associates a document with a goal
  -----------------------------------------------------------------------

This is a logical model, not a requirement to create five new tables.
Existing schema and relationship patterns take precedence unless a
verified gap requires change.

### Goal

Possible fields: - `id` - `user_id` - `title` - `description` -
`source_type` - `source_reference` - `scope` - `start_date` -
`target_date` - `lifecycle_status` - `achievement_status` -
`created_at` - `updated_at`

Keep lifecycle status (such as Draft or Active) separate from
achievement status (such as Not Started, In Progress, Achieved, or Not
Achieved). Confirm the final enums against M6.3's existing
implementation.

### SourceRecord

Possible fields: - `id` - `user_id` - `source_type` - `external_id` -
`source_url` - `title` - `description` - `occurred_at` - `metadata` -
`first_seen_at` - `last_synced_at`

Use a stable uniqueness rule, such as source type plus external ID
within the correct account or tenant boundary, to prevent duplicates.
The precise key depends on connector and tenancy design.

### Document

Possible fields: - `id` - `user_id` - `filename` - `content_type` -
`storage_reference` - `source_type` - `ingestion_status` -
`uploaded_at` - `processed_at` - `metadata`

Store secure references to file content rather than embedding large file
contents in relational records. Follow the project's existing storage
and retention conventions.

### GoalSourceLink and GoalDocumentLink

These associations should: - Connect goals to relevant records or
documents. - Preserve who created or confirmed the association. -
Support correction or removal when allowed. - Avoid duplicate links. -
Enforce ownership and authorization across both sides of the
relationship.

If the current schema already supports generic associations safely,
reuse it instead of creating dedicated link tables.

## 6. Architecture and repository responsibilities

### `myimpact-web`

-   Goal list and goal detail views.
-   Goal creation, editing, and draft approval UI.
-   Document upload and processing status.
-   Browsing collected contributions and documents.
-   Goal association management.
-   Loading, empty, validation, and error states.

### `myimpact-ai`

-   Versioned `/api/v1` contracts.
-   Goal and document ingestion orchestration.
-   Source integration and synchronization.
-   Source-record normalization and deduplication.
-   Authorization and ownership checks.
-   Document extraction through existing processing capabilities.
-   APIs for browsing and linking records.

### `myimpact-db`

-   Persist goals, source records, documents, and associations where
    existing schema is insufficient.
-   Add migrations only for demonstrated gaps.
-   Enforce appropriate constraints and indexes.
-   Preserve existing data and migration history.

The frontend must not connect directly to PostgreSQL, external source
systems, vector stores, or internal processing components.

## 7. What to defer to avoid overengineering

Do not prioritize these in the data-foundation phase: - Impact scoring
or performance ratings. - AI-based goal completion judgments. -
Automatic assessment of JL4/JL5 expectations. - Gap analysis and
AI-generated next-step recommendations. - A separate primary navigation
module for "Knowledge" without a clear user need. - A separate
Achievement entity for every raw contribution. - A generic persisted
entity for every AI insight. - All integrations at once. - Duplicate
tables or endpoints that replicate existing capabilities.

Raw activity counts should not be presented as performance scores.

## 8. Testing strategy

Create deterministic test scenarios for: - Goal created manually. -
Goals extracted from a supported document and approved. - Extraction
errors and malformed documents. - Goal with no source records. - Goal
with several linked records from one source. - Same external record
imported multiple times. - User-provided document linked to a goal. -
Source integration temporarily unavailable. - Permission denied by the
source system. - Attempt to access another user's goal or records. -
Incorrect goal association corrected by the user. - Reprocessing an
uploaded document without creating duplicate goals. - Existing M3
ingestion and retrieval tests remaining green.

Use seeded data for repeatable frontend and integration testing.

## 9. Data quality and operational requirements

-   Preserve provenance and original source references.
-   Enforce user and tenant isolation.
-   Make synchronization observable and retryable.
-   Make ingestion errors understandable to users and diagnosable by
    developers.
-   Track ingestion and synchronization timestamps.
-   Make ingestion and sync operations idempotent.
-   Respect external source permissions and document access controls.
-   Provide a safe strategy for deleted or revoked external records.
-   Keep user-submitted statements distinct from automatically imported
    source facts.
-   Do not generate assessment conclusions during collection.

## 10. Product success measures for this phase

Measure data reliability and usability, not AI sophistication.

Suggested metrics: - Percentage of goals with complete source and period
metadata. - Percentage of collected records with traceable provenance. -
Duplicate rate after synchronization. - Synchronization success and
retry rates. - Document ingestion success rate. - Percentage of linked
records that users confirm as relevant. - Number of unlinked records and
time to resolve them. - User ability to find and inspect collected
information without manual reconstruction.

Do not optimize for the number of tables, entities, integrations,
prompts, or AI calls.

## 11. Immediate action plan

1.  Complete an M6.3 closure review and record the current known-good
    branch, tests, and API contracts.
2.  Inspect the current `myimpact-web`, `myimpact-ai`, and `myimpact-db`
    implementations.
3.  Map the existing goal, document, source-record, and association
    models to this plan.
4.  Create a short gap analysis: reuse, extend, or build.
5.  Implement M6.4 goal/document ingestion using existing capabilities
    wherever possible.
6.  Validate the complete upload → extraction → draft review → approval
    flow.
7.  Choose one practical source integration and implement M6.5 end to
    end.
8.  Add user-owned data and goal associations.
9.  Build the unified data browsing experience and validate data
    quality.
10. Revisit analysis only after the data foundation is demonstrably
    reliable.

## Final principle

**Collect first. Organize second. Analyze later.**

Goals define what matters. Connected systems and user-owned material
provide the raw information. Provenance and goal associations make it
trustworthy and useful. Only after that foundation is reliable should
MyImpact assess progress, impact, gaps, or recommended next steps.
