# MyImpact — Hierarchical Goals & Evidence Architecture

**Document status:** Proposed target architecture — requires current-repository assessment and explicit approval  
**Scope:** `myimpact-web`, `myimpact-api`, `myimpact-ai`, `myimpact-db`  
**Related capabilities:** Goal Management, Goal Validation, M6.6 Evidence Assessment, M7 Impact Analysis, M8 Reporting, M9 Agents/Dots

---

## 1. Executive Summary

This document proposes a unified architecture for managing goals across four **Goal Levels**:

- Annual Goal
- Quarterly Goal
- Monthly Goal
- Sprint Goal

All Goal Levels use one common Goal entity. A goal may exist independently or be connected to another goal through an optional parent relationship. Intermediate levels may be skipped, goals may be reparented or disconnected, and hierarchy depth must not be hardcoded to exactly four levels.

Evidence is an independent entity. Evidence can be attached to a goal at any Goal Level and made visible to relevant higher-level goals through relationship traversal. Evidence records must not be duplicated merely because they contribute to multiple goals.

The architecture separates execution completion, outcome achievement and demonstrated impact. Completing child goals does not automatically prove that a parent goal achieved its outcome or generated business impact.

Goal validation is progressive and stage-aware. It evaluates what is reasonably expected at the goal's current maturity and Goal Level rather than requiring every baseline, target or measurement to be available at the beginning.

**Important:** This is a proposed target architecture, not a claim about confirmed existing implementation. The implementation must begin with a repository-backed assessment and reuse existing capabilities wherever possible.

## 2. Goals and Non-Goals

### 2.1 Goals

1. Support Annual, Quarterly, Monthly and Sprint Goals through one common Goal model.
2. Allow standalone goals and optional parent-child relationships.
3. Support flexible hierarchy, skipped levels, reparenting and disconnection.
4. Preserve relationship history and auditability.
5. Validate goals progressively according to maturity and Goal Level.
6. Support explicitly deferred requirements.
7. Capture evidence at the level where work or results occur.
8. Reuse evidence across multiple goals through explicit relationships without duplicating evidence records.
9. Distinguish direct, contribution-linked and inherited/descendant evidence.
10. Separate execution, achievements, outcomes and impact.
11. Preserve existing M6.6 assessment and human-review capabilities.
12. Maintain compatibility with existing goals, evidence, APIs and reports.

### 2.2 Non-Goals

This proposal does not authorize:

- Automatically creating, approving, restructuring or reparenting goals using AI.
- Automatically assigning business impact based only on child completion.
- Inventing baselines, targets, owners, dates or organizational policy.
- Replacing existing evidence assessment or human-review workflows without assessment.
- Creating separate goal tables for each Goal Level.
- Rewriting historical evidence relationships when a goal is reparented.
- Introducing agent-driven workflows as a prerequisite for the hierarchy foundation.

## 3. Domain Concepts and Terminology

These concepts must remain independent.

| Concept | Meaning |
|---|---|
| Goal Level | The level/category of goal: Annual, Quarterly, Monthly or Sprint |
| Goal Type | The nature of the commitment: Delivery, Outcome, Impact or Development |
| Parent relationship | The goal's position in the primary hierarchy |
| Contribution relationship | How one goal contributes to another goal, independently of primary hierarchy |
| Validation status | Whether the goal is sufficiently defined for its current stage |
| Approval status | Whether the required person or authority has approved the goal |
| Lifecycle status | Whether the goal is draft, active, completed or in another lifecycle state |
| Evidence | A source or artifact supporting a claim about work, a result or an outcome |
| Achievement | A meaningful accomplishment supported by evidence |
| Outcome | The result the goal intended to achieve |
| Impact | The demonstrated value or effect, supported by appropriate evidence |

Do not collapse validation, approval and lifecycle into one status field.

### 3.1 Goal Levels

| Business label | Proposed technical value |
|---|---|
| Annual Goal | `ANNUAL` |
| Quarterly Goal | `QUARTERLY` |
| Monthly Goal | `MONTHLY` |
| Sprint Goal | `SPRINT` |

Goal Level describes the goal's planning/organizational level. It does **not** require a parent at the immediately preceding level.

Examples:
- An Annual Goal may have a Monthly Goal directly beneath it.
- A Quarterly Goal may be standalone.
- A Sprint Goal may be connected directly to an Annual Goal if the use case and policy permit it.

The allowed parent-child combinations should be configurable or governed by explicit product policy, not inferred from enum ordering.

### 3.2 Goal Types

Proposed initial values:

- `DELIVERY`
- `OUTCOME`
- `IMPACT`
- `DEVELOPMENT`

The repository assessment must inspect existing enums and stored values before proposing additions or mappings.

## 4. Goal Domain Model

### 4.1 Common Goal Entity

The logical Goal model should support the following attributes. These are conceptual requirements, not instructions to add every field if an equivalent already exists.

| Attribute | Purpose |
|---|---|
| `goal_id` | Stable goal identifier |
| `parent_goal_id` | Optional primary parent reference |
| `goal_level` | Annual, Quarterly, Monthly or Sprint |
| `goal_type` | Delivery, Outcome, Impact or Development |
| `title` | Goal title |
| `description` | Goal context and intent |
| `owner_id` | Accountable owner |
| `start_date` / `end_date` | Goal timeframe |
| `scope` | Personal, Team or Organization |
| `validation_status` | Stage-aware validation result |
| `approval_status` | Approval workflow state |
| `lifecycle_status` | Lifecycle state |

Inspect the current domain and physical database schema before changing names, types or relationships.

### 4.2 Primary Parent Relationship

A goal has zero or one primary parent and may have multiple children.

Rules:

1. A goal may be created without a parent.
2. A parent may be assigned after creation.
3. Intermediate Goal Levels may be skipped.
4. A goal may be reparented or disconnected, subject to authorization and policy.
5. A goal cannot be its own parent.
6. Circular relationships are prohibited.
7. Connecting a goal to a parent must not silently change its Goal Level, dates, type, scope, validation, approval or lifecycle.
8. Parent changes must be auditable.
9. A standalone goal remains valid.
10. Hierarchy depth must not be hardcoded to four.

A primary hierarchy relationship represents structural ownership or alignment. It should not be overloaded to represent every possible contribution.

### 4.3 Contribution Relationships

A separate contribution relationship may be needed when one goal contributes to multiple higher-level goals.

This relationship must be distinct from the primary parent relationship. It should include a description of the contribution and must not cause duplicate progress or evidence counting.

The repository assessment must determine whether an existing relationship model can support this use case before a new table or entity is proposed.

### 4.4 Reparenting and Disconnection

A parent change must preserve:

- Previous parent and new parent.
- Goal identifier.
- Actor who made the change.
- Timestamp.
- Reason or change note, where required by policy.

Reparenting must not rewrite historical evidence associations, prior assessments or completed review records. Parent-level visibility and derived views may be recalculated using the new hierarchy.

### 4.5 Authorization and Deletion

The design must define:

- Who may create, connect, reparent or disconnect goals.
- Whether a goal may be connected to a parent owned by another employee.
- How Team and Organization scope affect authorization.
- What happens when a parent with children is archived or deleted.

Deleting a parent must not orphan or silently delete child goals. Prefer controlled reassignment, disconnection or archival according to approved product policy.

## 5. Progressive Goal Validation

### 5.1 Core Principle

**Validate a goal for its current maturity and Goal Level, not against an expectation that every detail must be known on day one.**

An Annual Goal may be valid at the beginning of a year even when its baseline, target or measurement method has not yet been established, provided that:

- The goal's purpose and accountability are sufficiently clear.
- The missing information is legitimately expected to be defined later.
- The deferred work has an expected resolution stage or date.
- The deferral is visible and can be followed up.

For example, an Annual Goal titled “Reduce deployment failures” may be Ready for initial planning while baseline analysis and target-setting are explicitly planned through a later Quarterly Goal.

### 5.2 Requirement Classification

Each validation requirement should be evaluated as one of:

- `REQUIRED_NOW`
- `DEFERRED_ALLOWED`
- `NOT_APPLICABLE`

A missing value must not automatically mean validation failure.

A deferred requirement should carry sufficient information to manage it, such as:

- Requirement identifier or category.
- Reason for deferral.
- Expected resolution Goal Level or date.
- Current resolution state.
- Related child goal, if one exists.

The precise persistence model must be determined after inspecting the current validation schema.

### 5.3 Validation Outcomes

| Technical value | Display label | Meaning |
|---|---|---|
| `READY` | Ready | Sufficiently defined for the current stage and applicable approval workflow |
| `NEEDS_REFINEMENT` | Needs Refinement | A known, actionable gap the employee can usually address |
| `NEEDS_DISCUSSION` | Needs Discussion | A reliable decision requires manager, stakeholder or authoritative-context discussion |
| `INVALID` | Invalid | An explicit policy violation or fundamental issue not fixable through ordinary refinement |

### 5.4 Validation Context

Validation should consider, where relevant:

- Goal Level.
- Goal Type.
- Current maturity or planning stage.
- Purpose and clarity.
- Ownership and accountability.
- Scope.
- Success criteria.
- Measurability and target readiness.
- Outcome versus impact expectations.
- Timeframe and feasibility.
- Role alignment.
- Dependencies and conflicts.
- Parent and child context.
- Deferred requirements and their due state.
- Applicable organizational policy.

A Delivery Goal does not always require an explicit business impact target. Missing contribution detail is not, by itself, evidence of employee underperformance.

### 5.5 Parent and Child Validation

- A parent is not automatically valid merely because it has children.
- A child must have its own purpose and accountability.
- A parent must retain a meaningful commitment of its own.
- Child goals may clarify how a parent will be delivered, but must not silently replace the parent's intent.
- A Ready child does not imply that its parent is Ready.
- A Ready parent does not imply that every child is Ready.

### 5.6 Deferred Requirement Monitoring

Deferred requirements should become visible when their expected resolution date or stage approaches or passes.

The system should distinguish:

- Deferred and not yet due.
- Due for resolution.
- Overdue.
- Resolved.
- No longer applicable, with rationale.

An overdue deferred requirement may trigger refinement or discussion. It should not automatically invalidate the goal without applying the relevant validation policy.

## 6. Evidence Architecture

### 6.1 Core Principle

**Capture evidence at the lowest meaningful level where the work or result occurred, then make it visible to relevant higher-level goals through relationships and hierarchy traversal. Do not duplicate evidence.**

Evidence may be attached directly to any Goal Level:

- Sprint: pull requests, commits, CI results, demos.
- Monthly: deliverable documents, implementation results, operational changes.
- Quarterly: trend analysis, milestone completion, quarterly results.
- Annual: annual reliability reports, overall business metrics or customer impact reports.

These are examples, not restrictive evidence-type rules.

### 6.2 Logical Evidence Model

A logical Evidence entity may contain:

| Attribute | Purpose |
|---|---|
| `evidence_id` | Stable evidence identifier |
| `title` | Evidence title |
| `description` | What the evidence demonstrates |
| `evidence_type` | Type or category |
| `source_reference` | Link or reference to the source |
| `submitted_by` | Submitter |
| `submitted_at` | Submission timestamp |
| `verification_status` | Verification or assessment state |
| `metadata` | Source-specific metadata |

The repository assessment must identify and reuse the existing evidence entity and provenance model where possible.

### 6.3 Evidence-to-Goal Relationship

If the existing evidence-goal association cannot support the requirements, consider a relationship model with:

| Attribute | Purpose |
|---|---|
| `evidence_goal_link_id` | Relationship identifier |
| `evidence_id` | Evidence record |
| `goal_id` | Goal supported by the evidence |
| `relationship_type` | `PRIMARY` or `CONTRIBUTION` |
| `contribution_description` | How this evidence supports this goal |
| `created_by` | Actor creating the relationship |
| `created_at` | Relationship creation timestamp |

Do not create this model blindly. Inspect the current database and API first.

### 6.4 Evidence Visibility

A goal view should distinguish:

1. **Direct evidence** — evidence explicitly linked to this goal.
2. **Contribution evidence** — evidence linked with an explicit contribution relationship.
3. **Descendant/inherited evidence** — evidence associated with a child or deeper descendant and surfaced through hierarchy traversal.

The UI must make the source goal and relationship type clear. Inherited evidence must not appear as if it were directly submitted against the parent.

### 6.5 Evidence Reuse and Counting

A single evidence record may support multiple goals, but:

- The evidence record is stored once.
- Each goal relationship describes its own contribution.
- One PR linked to four goals is still one evidence record, not four independent records.
- Evidence coverage and counts must avoid double-counting.
- Evidence relevance may differ by goal.
- Evidence verification and assessment remain independent of goal progress.

### 6.6 Reparenting and Evidence History

Evidence remains associated with its original goal when that goal is reparented.

After a parent change:

- Recalculate which ancestor views can discover the evidence.
- Preserve the original evidence-goal relationship.
- Preserve provenance and prior assessment.
- Do not silently rewrite evidence links to match the new parent.
- Make historical hierarchy context available where required for auditability.

## 7. Achievements, Outcomes and Impact

Keep these three concepts distinct.

| Dimension | Question |
|---|---|
| Execution completion | Was the planned work completed? |
| Outcome achievement | Did the intended result happen? |
| Demonstrated impact | What measurable value or effect was demonstrated? |

A possible assessment flow is:

`Evidence → Evidence Assessment → Achievement Identification → Goal Contribution Assessment → Outcome Assessment → Impact Analysis`

This is a conceptual flow. The implementation must map it to existing M6.6 and M7 services and avoid duplicating existing capabilities.

### 7.1 Parent Progress

Child completion must not automatically prove parent outcome or impact.

Do not calculate parent progress as a simple average of child completion percentages.

If weighted roll-up is introduced:

- Weights must be explicitly configured or agreed.
- The basis for the weights must be visible.
- Missing weights must not be silently invented.
- Execution, outcome and impact must remain separately reportable.

Recommended separate parent-level measures:

- Child execution progress.
- Outcome achievement.
- Demonstrated impact.
- Evidence coverage.

### 7.2 AI Contribution Reasoning

AI may suggest or infer a contribution chain for human review. It must:

- Cite the supporting evidence.
- Explain uncertainty and limitations.
- Distinguish correlation, contribution and causation.
- Avoid claiming causal business impact without appropriate evidence.
- Avoid silently changing goal relationships or status.

## 8. API Capability Requirements

These are capability requirements, not final endpoint names. Endpoint design must follow the current API conventions and compatibility constraints.

The API should support:

1. Create a standalone goal.
2. Create a goal with an optional parent, if permitted by workflow.
3. Retrieve a goal and its hierarchy context.
4. Retrieve children and ancestors.
5. Connect a goal to a parent.
6. Reparent a goal.
7. Disconnect a goal from its parent.
8. Retrieve relationship history.
9. Validate a goal using Goal Level, type and context.
10. Retrieve deferred requirements and their due state.
11. Add evidence to a goal at any Goal Level.
12. Link existing evidence to another goal.
13. Retrieve direct, contribution and descendant evidence.
14. Retrieve execution, outcome and impact measures separately.
15. Retrieve hierarchy-aware reporting data.

API changes must preserve existing contracts or provide a controlled, versioned compatibility strategy. Authorization must be enforced server-side; frontend visibility alone is not sufficient.

## 9. AI Capability Requirements

AI capabilities should be assistive and explainable.

Potential capabilities:

- Goal-Level-aware validation.
- Deferred requirement reasoning.
- Goal clarity and measurability suggestions.
- Hierarchy consistency checks.
- Suggested parent/child alignment.
- Evidence-to-goal contribution assessment.
- Achievement and outcome summarization.
- Impact analysis with source citations and uncertainty.

Constraints:

- AI suggestions do not automatically create or approve goals.
- AI must not automatically restructure the hierarchy.
- AI must not invent missing facts.
- AI output must retain evidence references and provenance.
- Human review and adjudication must remain available where required.
- Reuse M6.6 evaluation and human-review infrastructure where suitable.
- Add hierarchy-specific evaluation cases rather than assuming the existing M6.6 dataset covers the new behavior.

## 10. Frontend and User Experience

### 10.1 Unified Goal Workspace

Provide a unified workspace with:

- Goal Level selection.
- Goal Type selection.
- Optional parent goal selection.
- Goal title, purpose and accountability.
- Stage-appropriate planning fields.
- Validation and approval status displayed separately.
- Lifecycle status displayed separately.

### 10.2 Hierarchy Navigation

Goal details should support:

- Parent and ancestor navigation.
- Child goal listing.
- Connect to Parent Goal action after creation.
- Reparent and disconnect actions subject to authorization.
- Clear indication of standalone goals.
- Relationship history where appropriate.

### 10.3 Progressive Validation Experience

- Ask for information appropriate to the current planning stage.
- Explain why a field is required now or can be deferred.
- Show deferred requirements and their expected resolution stage/date.
- Group related fields.
- Hide empty optional values by default.
- Distinguish Needs Refinement from Needs Discussion.
- Explain validation results with actionable reasons.

### 10.4 Evidence Experience

Show evidence with clear labels:

- Direct.
- Contribution-linked.
- Descendant/inherited.

Display the source goal, source reference, verification/assessment state and contribution description where available.

Do not make inherited evidence look like direct evidence.

### 10.5 Achievement and Impact Experience

Display execution completion, outcome achievement, evidence coverage and demonstrated impact separately. Explain how each measure is derived and avoid unsupported roll-up percentages.

### 10.6 Human Evaluation Experience

Preserve the blind-review principle: reviewers must not see AI suggestions before submitting their independent assessment when the workflow requires blind review.

Do not redesign or bypass M6.6 review behavior without an explicit, repository-backed decision.

## 11. Database and Migration Principles

The database design must be based on the actual current schema.

Potential changes to evaluate:

- Goal Level support.
- Optional primary parent reference.
- Hierarchy indexes and cycle-prevention strategy.
- Relationship history/audit events.
- Deferred validation requirements.
- Evidence-goal relationship enhancements, only if current schema is insufficient.
- Contribution relationships, if required and not already supported.

Migration constraints:

1. Use new Flyway migrations only.
2. Never modify an applied migration.
3. Preserve existing goal and evidence records.
4. Do not force legacy active goals into validation failure because a new field is missing.
5. Define a compatibility/backfill policy before making new fields mandatory.
6. Preserve existing evidence submission during rollout.
7. Avoid destructive changes.
8. Avoid introducing tables for every nested JSON structure without a demonstrated query, integrity or lifecycle requirement.
9. Define indexes and database constraints based on actual query patterns and supported database capabilities.
10. Test migration against representative existing data and recovery procedures.

## 12. Backward Compatibility and Data Integrity

The implementation must preserve:

- Existing goals and their meaning.
- Existing owners, dates, scope and statuses.
- Existing evidence and source references.
- Existing achievements and reviews.
- Existing M6.6 assessments and human-review records.
- Existing API consumers and frontend flows.
- Existing reporting behavior unless a deliberate, approved change is made.

Specific safeguards:

- Existing active goals must not become invalid merely because Goal Level is absent during migration.
- Existing evidence must not be deleted, duplicated or reassigned.
- Historical assessments must remain tied to the context in which they were produced.
- Parent changes must not rewrite historical evidence links.
- Existing evidence submission must continue during staged rollout.
- New validation gates must have a controlled legacy-goal policy.

## 13. Evaluation and Quality Strategy

### 13.1 Goal Validation Evaluation

Include cases covering:

- Early-stage Annual Goals with legitimately deferred measures.
- Quarterly goals establishing baselines and targets.
- Monthly and Sprint goals with more immediate delivery detail.
- Missing ownership or unclear accountability.
- Conflicting or incomplete information.
- Goals that need employee refinement.
- Goals that need manager discussion.
- Explicitly invalid goals.
- Overdue deferred requirements.
- Parent/child inconsistency.
- Standalone goals.

### 13.2 Hierarchy Evaluation

Evaluate:

- Valid skipped-level relationships.
- Standalone goals.
- Reparenting and disconnection.
- Self-link and cycle rejection.
- Cross-owner authorization.
- Parent/child consistency.
- Contribution relationships distinct from primary hierarchy.
- Preservation of evidence and history after reparenting.

### 13.3 Evidence Evaluation

Evaluate:

- Direct versus inherited evidence classification.
- Evidence linked to multiple goals.
- Contribution descriptions.
- Duplicate counting prevention.
- Provenance preservation.
- Relevance to different goal levels.
- Evidence visibility after reparenting.

### 13.4 Human and AI Evaluation

Reuse the existing M6.6 human-review infrastructure where possible. Keep AI output separate from independent human review until the reviewer submits their initial assessment.

A dataset is not approved ground truth merely because a batch is marked complete. Human review, adjudication, dataset versioning and explicit approval must be recorded before treating benchmark labels or numeric thresholds as approved.

## 14. Integrated Implementation Approach

Use a **single coordinated implementation initiative**, not an unnecessarily fragmented sequence of small phases. A capable coding model can reason across the repositories, but implementation must still be controlled by explicit checkpoints, dependency order and test gates.

### Step 1 — Inspect and Establish the Baseline

Inspect all four repositories:

- `myimpact-db`
- `myimpact-api`
- `myimpact-ai`
- `myimpact-web`

Produce:

1. Current architecture and domain inventory.
2. Current Goal schema and relationship map.
3. Current Evidence schema and relationship map.
4. Achievement, outcome and impact implementation map.
5. Validation, approval and lifecycle workflow map.
6. M6.6 and M7 integration map.
7. API and frontend contract inventory.
8. Migration, test and deployment inventory.
9. Gap analysis against this proposal.
10. Reuse-versus-change recommendations.
11. Backward-compatibility and rollout strategy.
12. An implementation plan with dependency order, acceptance criteria and test strategy.

**Inspection checkpoint:** No code, migration, API, prompt or frontend behavior changes during this step. Review the findings and approve the implementation plan before proceeding.

### Step 2 — Implement the End-to-End Architecture

After approval, implement the agreed changes across the four repositories as one coherent capability. The coding model should determine the appropriate internal task breakdown from the repository findings rather than being constrained to arbitrary milestone-sized phases.

Implementation must follow dependency order. At minimum:

- Establish compatible Goal Level and hierarchy domain/persistence behavior.
- Implement authorized hierarchy operations and history.
- Implement progressive validation and deferred requirements.
- Implement evidence relationships and hierarchy-aware evidence retrieval.
- Integrate achievement, outcome and impact views and services.
- Update API contracts and frontend workflows.
- Extend evaluation and reporting where required.

These are work areas, not independent release phases. Reuse existing structures and services wherever possible.

### Step 3 — Validate, Review and Deliver

Run and report integrated validation across all affected repositories:

- Database migration tests against representative existing data.
- Backend unit and integration tests.
- AI validation and evaluation tests.
- API contract and authorization tests.
- Frontend build and relevant UI tests.
- End-to-end hierarchy, evidence and goal lifecycle scenarios.
- M6.6 regression tests.
- M7 impact-analysis regression tests.
- Backward-compatibility checks.

Provide a final implementation report with:

- Files and migrations changed.
- Existing components reused.
- New components introduced and why.
- API and data-model changes.
- Test commands and actual results.
- Known limitations and unresolved decisions.
- Rollout and rollback considerations.

Do not claim tests passed unless they were actually run successfully.

## 15. Cross-Repository Responsibilities

Exact ownership must be confirmed during inspection.

| Repository | Areas to inspect and potentially change |
|---|---|
| `myimpact-db` | Flyway migrations, schema constraints, indexes, reference data |
| `myimpact-api` | Domain models, repositories, services, API contracts, authorization |
| `myimpact-ai` | Validation reasoning, contribution assessment, evidence/impact reasoning, evaluation |
| `myimpact-web` | Goal workspace, hierarchy navigation, validation UX, evidence views, reporting |

Identify shared contracts and duplicated domain definitions before implementation. Avoid independently redefining the same enum or relationship semantics across repositories.

## 16. Key Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Legacy goals fail new validation | Compatibility policy and controlled backfill |
| Circular hierarchy | Cycle prevention in service and appropriate persistence safeguards |
| Unauthorized cross-owner linking | Server-side authorization and explicit policy |
| Evidence duplication | One evidence record with multiple explicit relationships |
| Double-counted progress | Separate measures and explicit aggregation rules |
| Parent impact inferred from child completion | Independent outcome and impact assessment |
| Reparenting changes historical meaning | Immutable history and preserved evidence links |
| AI invents targets or relationships | Evidence-grounded suggestions and human approval |
| M6.6 regression | Regression tests and preserved review contracts |
| Overly complex schema | Inspect existing schema and add only justified structures |
| Disruptive rollout | Backward-compatible migrations, staged rollout and monitoring |

## 17. Decisions Requiring Explicit Approval

The following remain open until confirmed by repository assessment and product decisions:

1. Exact allowed Goal Level parent/child combinations.
2. Whether hierarchy depth has a configured maximum.
3. Cross-employee and cross-team parent-linking policy.
4. Who may connect, reparent and disconnect goals.
5. Parent deletion/archive behavior.
6. Whether contribution relationships are required in the first release.
7. Exact deferred-requirement persistence and reminder behavior.
8. Validation rules by Goal Level and Goal Type.
9. Whether and how parent execution progress is rolled up.
10. Any weighting model for progress aggregation.
11. Evidence verification requirements by evidence type.
12. Legacy-goal compatibility and evidence-gate rollout policy.
13. Which M6.6 evaluation components can be reused unchanged.
14. Dataset approval process and numeric release thresholds.

No implementation should silently decide these policy questions.

## 18. Acceptance Criteria

The architecture is acceptable when:

- All four Goal Levels use the common Goal model.
- Goals can exist independently.
- Parent relationships are optional and flexible.
- Skipped Goal Levels are supported.
- Self-links and cycles are rejected.
- Reparenting and disconnection are authorized and auditable.
- Parent changes do not silently alter goal attributes or historical evidence.
- Validation is stage-aware and supports explicit deferral.
- The four validation outcomes have distinct meanings.
- Evidence can be attached at any Goal Level.
- Evidence can be surfaced through hierarchy without duplication.
- Direct, contribution and descendant evidence are distinguishable.
- Execution, outcome and impact are separately represented.
- Parent progress does not imply parent impact.
- Existing M6.6 human review and evidence assessment remain functional.
- Existing data and API consumers remain compatible through the approved rollout.
- Automated tests cover hierarchy, validation, evidence and compatibility behavior.

## 19. Guiding Principles

1. One Goal entity; multiple Goal Levels.
2. Standalone goals are first-class.
3. Hierarchy is flexible, optional and auditable.
4. Validate maturity, not perfection.
5. Defer legitimately unknown details explicitly.
6. Capture evidence once, relate it meaningfully.
7. Preserve provenance and historical context.
8. Separate execution, outcome and impact.
9. AI recommends; authorized humans decide.
10. Inspect current repositories before changing them.
11. Preserve M6.6 and existing product behavior.
12. Prefer incremental, backward-compatible delivery.

---

**Document status:** Proposed target architecture.  
**Next action:** Complete the inspect-only baseline assessment, reconcile this proposal with the current implementation, and obtain explicit approval before implementation.
