# MyImpact — Goal Validation Engine
## Design Document

**Document status:** Proposed design  
**Version:** 1.0  
**Target capability:** Goal Validation Engine  
**Roadmap context:** M7 foundation / subsequent implementation phase  
**Audience:** Product, Architecture, Engineering, QA and AI Evaluation teams

---

## 1. Executive Summary

The Goal Validation Engine evaluates the quality and readiness of a goal before it is approved, activated, and used as the basis for evidence collection and achievement assessment.

MyImpact must not simply accept a goal because it was manually entered or extracted from an uploaded document. It should help the employee and manager establish:

- What the goal means.
- What the employee is personally accountable for.
- Whether the goal is individual, team or organizational in scope.
- What successful completion looks like.
- How achievement can be assessed.
- Which outcomes and impacts are expected.
- Which measures, baselines, targets and timelines apply.
- Whether the goal is relevant to the employee's role and context.

The engine should identify ambiguity and missing information, explain why it matters, and suggest improvements. It must not invent commitments, targets, ownership or responsibilities on behalf of the employee.

Goal validation is distinct from goal approval. The engine provides validation findings and a readiness recommendation; the employee and, where required, the manager remain responsible for confirming the goal.

The design also includes a dedicated benchmark capability so the Goal Validation Engine can be evaluated against human-reviewed reference cases before being trusted in production.

## 2. Problem Statement

Goals can arrive through manual entry, uploaded documents or extracted content. These inputs may be incomplete, ambiguous or mix several different expectations.

Examples identified during benchmark case analysis:

### 2.1 Shared contribution

**Original goal:** Reduce deployment failures by 30%.

The employee may own one component of a larger team initiative rather than the entire 30% reduction. Without explicit accountability, a later assessment may incorrectly attribute the whole team result to the employee or fail to credit the employee's actual contribution.

The goal should identify the employee's deliverable and distinguish it from the broader team outcome.

### 2.2 Delivery without demonstrated impact

**Original goal:** Reduce support effort through an automated reporting feature.

The employee may be accountable for delivering the feature, while adoption and reduction in support effort depend on other teams or organizational factors.

The goal should distinguish:
- The employee's delivery commitment.
- The intended outcome.
- The measurable business impact, if the employee is accountable for it.

A delivery commitment must not later be assessed as incomplete solely because a broader business impact has not been demonstrated, unless that impact was explicitly part of the agreed accountability.

## 3. Goals and Non-Goals

### 3.1 Goals

The Goal Validation Engine will:

1. Validate goal clarity and structure.
2. Identify individual ownership and accountability.
3. Identify goal scope (Personal, Team or Organization).
4. Check whether success criteria are explicit and assessable.
5. Evaluate measurability where applicable.
6. Separate deliverables, outcomes and impacts.
7. Check timeline and feasibility using available context.
8. Assess role alignment when reliable role expectations are available.
9. Identify missing, ambiguous or conflicting information.
10. Suggest improvements while preserving the employee's intent.
11. Produce structured, explainable and versioned validation results.
12. Support human correction, revalidation and approval workflows.
13. Be evaluated through a dedicated benchmark suite.

### 3.2 Non-goals

The initial capability will not:

- Automatically approve or activate goals.
- Decide employee performance ratings.
- Guarantee that a goal will be achieved.
- Invent missing targets, baselines, deadlines or responsibilities.
- Treat every goal as requiring a numerical target.
- Require every employee to own a business-level impact.
- Replace manager judgment or organizational goal-setting policy.
- Assess submitted evidence or calculate achievement. Those belong to downstream assessment capabilities.
- Use autonomous agents to make unapproved changes to goals.

## 4. Core Design Principles

1. **Preserve accountability:** Never assign a responsibility that is not supported by the submitted goal or confirmed context.
2. **Separate delivery, outcome and impact:** These are related but distinct concepts.
3. **Clarify before judging:** Missing information should normally lead to a clarification request, not an unsupported negative conclusion.
4. **Context-sensitive validation:** Requirements depend on goal type, role, scope and available organizational context.
5. **Explain every finding:** The employee should understand what is unclear, why it matters and how to improve it.
6. **Human ownership:** AI suggestions are proposals. The employee confirms edits and the manager approves where required.
7. **Version everything material:** Preserve goal versions and validation runs so later assessments can be traced to the exact goal definition.
8. **Deterministic controls around AI:** Use deterministic rules for structural and policy checks; use LLM reasoning for semantic analysis and suggestions.
9. **Benchmark before release:** Quality claims and release thresholds must be based on human-reviewed reference data and repeatable evaluations.
10. **Agent-ready, not agent-driven:** Use controlled LLM and MCP integrations where appropriate; do not introduce autonomous agents into this capability by default.

## 5. Conceptual Goal Model

A goal should be represented as structured information rather than only a title and free-text description.

| Attribute | Description | Requirement |
|---|---|---|
| Goal title | Short, understandable statement of intent | Required |
| Goal description | Context and intended work | Required |
| Goal type | Delivery, Outcome, Impact, Development or another approved type | Required; controlled vocabulary |
| Employee accountability | What the employee is expected to own or deliver | Required |
| Goal scope | Personal, Team or Organization | Required |
| Success criteria | Conditions used to determine completion | Required |
| Deliverable | Tangible output, where applicable | Conditional |
| Expected outcome | Change expected from the deliverable or activity | Conditional |
| Expected impact | Broader value or measurable effect | Conditional |
| Measurement method | How a target or outcome will be measured | Conditional |
| Baseline | Starting measurement, where relevant | Conditional |
| Target value | Intended measurable target, where relevant | Conditional |
| Target date / timeframe | When completion or outcome is expected | Required according to policy |
| Dependencies | External teams, systems or approvals that affect delivery | Conditional |
| Role alignment | Relationship to role expectations | Required only when reliable role context is available |
| Source | Manual entry, uploaded document or imported system | Required |
| Owner | Employee responsible for the goal | Required |

The data model should support goals that are delivery-focused and do not have a numerical business-impact target. A numerical target must not be forced when it is not meaningful or within the employee's accountability.

## 6. Goal Types and Accountability

The initial design should support a controlled goal-type taxonomy. The exact taxonomy must be confirmed with Product and existing MyImpact domain models before implementation.

| Goal type | Primary accountability | Example |
|---|---|---|
| Delivery | Complete and obtain acceptance for a deliverable | Deliver an automated reporting feature |
| Outcome | Achieve a defined operational or user outcome | Increase automated reporting adoption to 80% |
| Impact | Demonstrate a measurable business or organizational effect | Reduce monthly support effort by 30% |
| Development | Build a skill or capability with observable evidence | Demonstrate solution architecture capability through an approved design |

A goal may contain more than one layer, but accountability must be explicit. For example, an employee may own delivery while a team owns adoption and business impact.

### 6.1 Delivery, outcome and impact

| Layer | Key question | Example evidence later in the lifecycle |
|---|---|---|
| Delivery | Did the employee complete the agreed work? | Accepted feature, implementation record, release |
| Outcome | Did the delivered work produce the intended change? | Adoption, reduced manual steps, improved quality |
| Impact | What measurable value resulted? | Hours saved, cost avoided, failure-rate reduction |

The validation engine must determine which layer or layers are part of the employee's commitment. It must not silently turn an intended impact into an individual delivery obligation.

## 7. Validation Dimensions

The engine should evaluate the following dimensions. Some checks are mandatory; others are conditional on goal type and available context.

| Dimension | Validation questions | Example finding |
|---|---|---|
| Goal clarity | Is the goal specific, understandable and unambiguous? | “Improve performance” does not define what should improve. |
| Ownership and accountability | Is the employee's responsibility explicit and attributable? | The goal states a team target but not the employee's contribution. |
| Scope | Is the scope Personal, Team or Organization, and is the employee's relationship to it clear? | Organization-wide target with no individual responsibility described. |
| Success criteria | Can a reviewer determine whether the agreed commitment was completed? | No acceptance or completion conditions are stated. |
| Measurability | Is there a meaningful way to measure the goal where measurement is relevant? | A percentage target has no baseline or measurement method. |
| Outcome and impact | Are deliverable, outcome and impact distinguished? | Feature delivery is described as if it proves reduced support effort. |
| Timeline and feasibility | Is the timeframe clear and plausible given available information? | A large cross-team migration is expected in an unspecified short period. |
| Role alignment | Is the goal relevant to role expectations, based on reliable role context? | Goal appears unrelated to the supplied role expectations. |

### 7.1 Conditional validation

The engine must not treat all missing fields as defects.

Examples:
- A delivery goal may be assessable through acceptance criteria without a business-impact metric.
- An impact goal normally requires a measure, baseline or defensible measurement approach, target and timeframe.
- A team goal requires clarity about the employee's own contribution.
- Role alignment should be marked not evaluable if role expectations are unavailable or outdated.

## 8. Validation Outcomes and Finding Severity

The engine should return a validation status separately from findings and, where applicable, goal lifecycle status.

Proposed validation statuses:

| Status | Meaning |
|---|---|
| `READY` | Required goal information is sufficiently clear for submission to approval. |
| `NEEDS_IMPROVEMENT` | The goal is potentially valid but needs clarification or refinement before it is ready. |
| `NEEDS_REVIEW` | A human decision or missing external context is required. |
| `INVALID` | The goal violates a confirmed structural or policy rule and cannot proceed without correction. |

These statuses are proposed and must be reconciled with existing MyImpact status conventions.

Each finding should have:
- Dimension code.
- Severity (for example, BLOCKING, WARNING or INFORMATIONAL).
- Finding code.
- Explanation.
- Evidence or input text that triggered the finding.
- Missing information, if any.
- Suggested question or improvement.
- Whether the employee can resolve it.
- Whether manager or administrator review is required.

`READY` does not mean approved. Approval and activation remain separate workflow decisions.

### 8.1 Missing information versus failure

The engine must distinguish:
- A goal that is demonstrably incomplete or violates a confirmed rule.
- A goal that may be valid but lacks information needed to assess it.
- A goal that is complete for the employee's accountability but has an unproven broader impact.

Absence of a metric or evidence must not automatically mean the employee failed. It may mean that the relevant outcome is not part of the employee's commitment or that more information is needed.

## 9. End-to-End Workflow

1. **Goal intake:** Employee enters a goal manually or uploads/imports a document.
2. **Extraction:** For documents, extract candidate goal statements, ownership, scope, criteria, targets, dates and dependencies. Preserve source references and extraction confidence.
3. **Structuring:** Convert extracted or manually entered information into a structured draft. Do not silently fill missing values.
4. **Context resolution:** Retrieve relevant, authorized context such as employee role, role expectations, team objectives and organizational objectives, if available.
5. **Deterministic validation:** Check required fields, controlled values, date formats, target formats and confirmed policy rules.
6. **Semantic validation:** Use the LLM to assess ambiguity, accountability, scope, success criteria, delivery/outcome/impact separation, feasibility and role alignment.
7. **Findings aggregation:** Combine deterministic and semantic findings without hiding conflicts between them.
8. **Employee correction:** Present findings and suggested questions. Employee may edit the draft or provide missing information.
9. **Revalidation:** Create a new validation run against the updated goal version.
10. **Submission:** When the goal is `READY`, allow submission for approval according to configured policy.
11. **Manager review:** Manager approves, rejects or requests changes where required.
12. **Activation:** Activate only after the required approval and lifecycle checks.
13. **Evidence enablement:** Permit evidence submission against the active goal version, subject to product policy.

### 9.1 Revalidation

Any material change to title, accountability, scope, success criteria, target, measurement method, outcome, impact or timeframe should create a new goal version and trigger a new validation run.

A change to non-material metadata may not require semantic revalidation, based on explicit policy.

## 10. Illustrative Validation Examples

### 10.1 Shared team contribution

**Input goal:** Reduce deployment failures by 30%.

**Context:** Employee is responsible for implementing automated deployment validation for assigned services. The 30% reduction is a team objective.

**Potential findings:**
- Individual accountability should be stated.
- Team-level target should be distinguished from employee-owned deliverable.
- Measurement source and timeframe for the team target should be clarified if it is retained in the goal.

**Suggested revision:**

“Implement automated deployment validation for assigned services, contributing to the team's objective of reducing deployment failures by 30%.”

The system must not claim the employee owns the entire 30% reduction unless that responsibility is explicitly confirmed.

### 10.2 Delivery without demonstrated impact

**Input goal:** Reduce support effort through an automated reporting feature.

**Potential findings:**
- Is the employee accountable for feature delivery only, or also for adoption and support-effort reduction?
- Define delivery acceptance criteria.
- If impact is part of the commitment, specify the measurement method, baseline, target and timeframe.

**Suggested delivery-focused revision:**

“Deliver an automated reporting feature that enables the support team to reduce manual reporting effort.”

If the employee is accountable for adoption or measurable effort reduction, those responsibilities must be explicitly added and agreed.

### 10.3 Vague goal

**Input goal:** Improve system performance.

**Potential findings:**
- System or service in scope is unclear.
- Performance dimension is unclear (latency, throughput, resource usage, availability, etc.).
- Success criteria and timeframe are missing.

**Expected behavior:** Ask clarifying questions rather than inventing a target.

## 11. User Experience

The goal creation experience should show validation as an integrated step, not as a hidden AI score.

Recommended experience:

1. Goal input and source.
2. Structured goal preview.
3. Validation summary.
4. Findings grouped by dimension and severity.
5. Suggested questions and editable improvements.
6. Revalidate action.
7. Submission for approval when ready.

The employee should be able to:
- See the original input and extracted content.
- Understand which content came from the source and which content is an AI suggestion.
- Accept, edit or reject suggestions.
- Answer clarification questions.
- View validation history.
- See why a goal is not ready.
- Submit the final version for approval.

The UI should not present a single opaque quality score as the only explanation. A score may be useful as a secondary summary only if its calculation and limitations are clear.

## 12. Proposed Architecture

The capability should be implemented as a controlled workflow across existing MyImpact repositories. This is a logical target architecture, not a claim about current code structure. Existing services and boundaries must be inspected before implementation.

### 12.1 Component responsibilities

| Repository | Proposed responsibility |
|---|---|
| `myimpact-web` | Goal intake, structured editor, validation findings, employee corrections, validation history and approval experience |
| `myimpact-api` | Authentication, authorization, orchestration, goal versioning, validation run lifecycle, API contracts and approval workflow |
| `myimpact-ai` | Semantic goal analysis, structured findings, clarification questions and improvement suggestions |
| `myimpact-db` | Goal versions, validation runs, findings, source references and approval records |

### 12.2 Logical processing pipeline

```text
Manual Entry / Uploaded Document
              |
              v
       Goal Intake API
              |
              v
     Extraction / Structuring
              |
              v
       Context Resolution
              |
              v
    Deterministic Validation
              |
              v
      Semantic Validation
       (Controlled LLM)
              |
              v
     Findings Aggregation
              |
              v
       Goal Validation API
              |
              v
       Employee Review UI
              |
       Edit / Clarify / Accept
              |
              v
        New Goal Version
              |
              v
           Revalidate
              |
              v
        Approval Workflow
              |
              v
          Active Goal
```

### 12.3 Separation of responsibilities

- Extraction identifies candidate content from source documents.
- Structuring maps candidate content to the goal model.
- Context resolution obtains authorized role and organizational context.
- Deterministic validation enforces structural and explicit policy rules.
- Semantic validation interprets meaning and identifies ambiguity.
- Findings aggregation produces a unified, traceable result.
- Approval workflow records human decisions.
- Evidence assessment is a downstream capability and must not be embedded in goal validation.

### 12.4 LLM output contract

The LLM should return structured data, not only free-form prose. A conceptual response:

```json
{
  "goal_version_id": "goal-version-id",
  "validation_dimensions": [
    {
      "dimension_code": "OWNERSHIP_ACCOUNTABILITY",
      "status": "NEEDS_IMPROVEMENT",
      "severity": "WARNING",
      "finding_code": "TEAM_OUTCOME_WITHOUT_INDIVIDUAL_ACCOUNTABILITY",
      "explanation": "The goal defines a team-level reduction target but does not state the employee's specific responsibility.",
      "missing_information": [
        "Employee-owned deliverable",
        "Contribution boundary"
      ],
      "suggested_questions": [
        "Which part of the deployment reliability initiative are you accountable for?"
      ],
      "suggested_revision": null
    }
  ],
  "overall_validation_status": "NEEDS_IMPROVEMENT",
  "requires_human_review": false
}
```

This is illustrative. Final enums, schema and API contracts must align with existing MyImpact conventions.

The API must validate the LLM response against a schema and apply deterministic policy checks before persisting or displaying it. The LLM must not directly update goal lifecycle status or approve a goal.

## 13. Data Model Considerations

The following are conceptual entities for architecture discussion. Do not create them before inspecting existing database models and migrations.

| Logical entity | Responsibility |
|---|---|
| Goal | Stable identity and ownership of a goal |
| Goal version | Immutable or versioned goal definition |
| Goal validation run | One validation execution against one exact goal version |
| Goal validation finding | One dimension-specific finding from a validation run |
| Goal source reference | Link to uploaded/imported source and extracted content |
| Goal approval | Human approval decision and rationale |

Recommended design rules:

1. Every validation run references an exact goal version.
2. Findings belong to a specific validation run.
3. Store validator version, prompt version, model reference and execution timestamp.
4. Preserve source references and extraction provenance.
5. Record whether a field was user-provided, source-extracted, context-derived or AI-suggested.
6. Do not overwrite approved goal versions when a material change is made.
7. Preserve approval history.
8. Use existing shared master data for users, roles and AI models where available.
9. Use foreign keys and existing database naming conventions.
10. Follow the established audit-column convention for mutable transaction tables: `created_at`, `created_by`, `updated_at`, `updated_by`. Immutable validation and audit records should not be silently overwritten; update columns may remain null or be omitted according to established schema conventions.

## 14. Benchmark Strategy for Goal Validation

The Goal Validation Engine must have its own benchmark suite. It should share reusable evaluation infrastructure with the M6.6 evidence-assessment benchmark where practical, but use separate datasets, reference outcomes, dimensions and engine-specific metrics.

### 14.1 Initial benchmark size

Proposed starter dataset: **30 cases**.

| Category | Cases | Coverage |
|---|---:|---|
| Goal clarity and structure | 5 | Vague, ambiguous, compound and poorly structured goals |
| Ownership and accountability | 5 | Individual versus team responsibility, shared contribution |
| Delivery versus outcome versus impact | 5 | Delivery-only, outcome and impact accountability |
| SMART and measurability | 5 | Missing targets, baselines, measurement methods and dates |
| Feasibility and role alignment | 5 | Unrealistic goals and role relevance with context |
| Conflicting and incomplete goals | 5 | Contradictions, missing context, dependencies and uncertainty |
| **Total** | **30** | |

The 30 cases are a proposed starting point, not an approved or exhaustive dataset.

### 14.2 Benchmark case schema

Each case should contain:

- Case ID and case version.
- Category.
- Primary and secondary validation dimensions.
- Polarity or scenario type where useful.
- Original goal input.
- Employee role and relevant context fixtures.
- Source type and source content where applicable.
- Expected findings by dimension.
- Expected missing information.
- Acceptable clarification questions.
- Acceptable improvement characteristics.
- Expected overall validation status.
- Reference rationale.
- Known ambiguity and evaluation notes.
- Human review and approval status.

### 14.3 Benchmark dimensions

The benchmark should evaluate:

1. Goal clarity detection.
2. Ownership and accountability detection.
3. Scope interpretation.
4. Success-criteria completeness.
5. Measurability checks.
6. Delivery/outcome/impact distinction.
7. Timeline and feasibility reasoning.
8. Role-alignment reasoning.
9. Missing-information recall.
10. Recommendation usefulness.
11. Accountability preservation.
12. Contradiction handling.
13. Uncertainty and abstention.
14. Repeatability and consistency.

### 14.4 Evaluation metrics

| Metric | Purpose |
|---|---|
| Dimension classification accuracy | Whether the correct goal-quality dimensions are identified |
| Finding precision | Proportion of reported findings that are valid |
| Finding recall | Proportion of required findings detected |
| Missing-information recall | Whether critical missing inputs are identified |
| False-positive rate | Whether valid goals are unnecessarily blocked or challenged |
| False-negative rate | Whether materially defective goals are incorrectly marked ready |
| Recommendation quality | Relevance, correctness and actionability of suggestions |
| Accountability preservation | Whether the engine avoids inventing employee responsibilities |
| Status classification accuracy | Whether overall readiness is correctly classified |
| Repeatability | Consistency across repeated runs |
| Structured-output validity | Compliance with the agreed response schema |

Metrics must be reported by dimension and case category, not only as one aggregate score. Release thresholds must be established through governance and human-reviewed evaluation; no numeric threshold is approved by this design document.

### 14.5 Human review and reference governance

- Use at least two independent reviewers for cases where dual review is required.
- Record reviewer rationale and disagreements.
- Adjudicate unresolved disagreements.
- Preserve reviewer identities, review dates and dataset versions according to access policy.
- Keep training/development cases separate from holdout evaluation cases.
- Do not treat AI-generated expected outcomes as approved ground truth.
- Record dataset approval and threshold approval separately from review-batch completion.

### 14.6 Example benchmark cases

| Case | Input | Expected behavior |
|---|---|---|
| GV01 | “Improve system performance” | Identify ambiguity and ask what performance measure and system are intended. |
| GV02 | “Reduce API latency by 30%” | Ask for baseline, measurement method, scope and timeframe if not supplied. |
| GV03 | “Deliver automated reporting feature” | Validate delivery ownership and acceptance criteria; do not require business impact unless part of accountability. |
| GV04 | “Reduce support effort by 30%” | Check ownership, baseline, measurement method, timeframe and dependencies. |
| GV05 | “Lead organization-wide cloud migration” | Check actual authority, scope and employee accountability using available context. |
| GV06 | “Improve team productivity” | Identify missing definition of productivity and employee contribution. |
| GV07 | “Complete assigned API integration by March” | Check scope, acceptance criteria and year/date context. |
| GV08 | “Increase revenue by 50% in one month” | Identify feasibility and context gaps; do not declare impossible without supporting context. |
| GV09 | “Improve technical leadership” | Ask for observable behaviors and success criteria. |
| GV10 | “Reduce deployment failures by 30%” | Clarify whether the target is individual or team-owned and define the employee's contribution. |

## 15. Security, Privacy and Trust Boundaries

- Only retrieve role, team and organizational context the requesting user is authorized to access.
- Treat uploaded documents and extracted text as untrusted input.
- Do not follow instructions embedded in source documents that attempt to override system or application policy.
- Preserve source provenance and distinguish source content from AI suggestions.
- Avoid exposing confidential role or manager context to unauthorized users.
- Apply existing MyImpact authentication, authorization and data-retention controls.
- Log validation activity without unnecessarily copying sensitive source content into audit events.
- Do not use AI-generated content as an authoritative source without human confirmation.

## 16. Failure Handling and Edge Cases

The design should explicitly handle:

- Document extraction failure.
- Multiple possible goals in one uploaded document.
- Conflicting goal statements across sources.
- Missing employee role context.
- Outdated or unavailable role expectations.
- Unsupported goal types or unknown fields.
- LLM timeout, provider failure or malformed structured output.
- Deterministic and semantic validation disagreement.
- Goal changed while a validation run is in progress.
- Revalidation of an older goal version.
- Employee rejection of AI suggestions.
- Manager override or exception, with rationale and audit trail.

A failed AI call must not be interpreted as a successful validation. The system should communicate that validation could not be completed and allow a safe retry or manual review.

## 17. Observability and Reporting

Capture enough information to explain and reproduce each validation run:

- Goal ID and exact goal version.
- Validation run ID and timestamp.
- Deterministic rule-set version.
- Prompt version.
- AI model reference and provider.
- Context references and versions used.
- Structured findings and overall status.
- Latency, token usage and provider errors where available.
- Employee actions on suggestions.
- Revalidation links.
- Approval decision and approver.

Operational dashboards should include run success, failure rates, latency, validation status distribution, common findings, revalidation rates and user correction patterns. These operational metrics must be distinguished from benchmark quality metrics.

## 18. Implementation Phases

### Phase 0 — Existing architecture inspection

- Inspect goal entities, lifecycle and approval workflow.
- Inspect existing document ingestion and extraction.
- Inspect role and organizational context sources.
- Inspect existing AI orchestration and structured-output patterns.
- Inspect database migrations, audit conventions and API contracts.
- Identify reusable validation, assessment and benchmark infrastructure.
- Produce a current-state and gap analysis.

**Exit:** Architecture and gap analysis reviewed. No implementation changes before approval.

### Phase 1 — Domain and validation contract

- Confirm goal types and structured goal model.
- Confirm validation dimensions and conditional rules.
- Define statuses, finding severity and response schema.
- Define source provenance and goal-version behavior.
- Agree approval and activation boundaries.

**Exit:** Product and architecture approval of domain and contracts.

### Phase 2 — Benchmark design and reference review

- Build the initial 30-case dataset.
- Include positive, negative and borderline scenarios.
- Define expected findings and acceptable recommendations.
- Obtain independent human review and adjudication.
- Establish a versioned holdout set.

**Exit:** Human-reviewed reference dataset and evaluation plan.

### Phase 3 — Validation engine implementation

- Implement deterministic validation.
- Implement controlled LLM semantic validation.
- Implement findings aggregation and schema validation.
- Add version and provenance tracking.
- Add safe retry and failure handling.

**Exit:** API-level and component tests pass.

### Phase 4 — Benchmark runner and quality evaluation

- Implement repeatable benchmark execution.
- Calculate dimension-specific metrics.
- Compare repeated runs.
- Evaluate false positives, false negatives and accountability preservation.
- Document known limitations and obtain release-threshold approval.

**Exit:** Approved evaluation report and release decision.

### Phase 5 — Employee and manager experience

- Build structured goal editor and validation findings UI.
- Support clarification, edits and revalidation.
- Integrate approval and activation.
- Preserve goal and validation history.

**Exit:** End-to-end workflow validated.

### Phase 6 — Integrated validation and rollout

- Validate backend, AI, frontend, API contracts and migrations together.
- Run security and authorization tests.
- Test document ingestion and manual entry.
- Run regression and benchmark holdout evaluation.
- Roll out with monitoring and a controlled feedback process.

**Exit:** Product, engineering and quality sign-off.

## 19. Acceptance Criteria

The capability is ready for controlled release when:

1. Manual and supported document-based goal intake produce a structured draft with source provenance.
2. The engine evaluates all applicable validation dimensions.
3. Conditional requirements are applied according to goal type and context.
4. Findings include explanations and actionable clarification questions.
5. AI suggestions never silently change employee accountability or goal commitments.
6. Delivery, outcome and impact are represented distinctly.
7. Missing information is not automatically treated as failure.
8. Validation results reference an exact goal version and validator configuration.
9. Employees can edit and revalidate goals.
10. Approval and activation remain separate from AI validation.
11. Role/context access is authorized and auditable.
12. Failure paths do not accidentally mark goals as ready.
13. The benchmark dataset has human-reviewed reference outcomes and documented limitations.
14. Benchmark results include dimension-specific metrics and repeatability analysis.
15. Release thresholds and release approval are explicitly recorded.
16. Integrated tests cover manual entry, document intake, revalidation, approval and activation.

## 20. Open Decisions

The following decisions require Product and Architecture confirmation:

1. Final goal-type taxonomy.
2. Whether every goal requires a target date, and how ongoing goals are represented.
3. Which validation findings are blocking versus advisory.
4. Which role and organizational context sources are authoritative.
5. Whether manager approval is mandatory for all goals or configurable by organization.
6. Whether a manager can override a validation status and what rationale is required.
7. Goal versioning and treatment of evidence linked to earlier versions.
8. Exact benchmark labels, case schema and dimension registry.
9. Human-review policy for benchmark reference approval.
10. Release thresholds and minimum holdout coverage.
11. Whether goal validation is a separate milestone or part of the M7 foundation.
12. Which existing AI evaluation and benchmark components can be reused.

## 21. Copilot / Engineering Execution Instructions

This document describes a proposed target design. It does not authorize immediate implementation.

Before making code or database changes, inspect all relevant repositories:

- `myimpact-web`
- `myimpact-api`
- `myimpact-ai`
- `myimpact-db`

Inspect existing goal models, lifecycle/status definitions, migrations, document ingestion, role-context integrations, AI orchestration, API contracts, tests and benchmark infrastructure.

Produce the following first:

1. Current-state architecture and flow.
2. Existing entities and relationships.
3. Gap analysis against this design.
4. Reuse opportunities and conflicts with existing implementation.
5. Proposed target architecture and data model.
6. API and frontend contract changes.
7. Migration and backward-compatibility plan.
8. Test and benchmark implementation plan.
9. Risks, dependencies and unresolved decisions.

**Stop after the inspection and proposal. Do not modify files, migrations, APIs, prompts or UI until the design and implementation plan are reviewed and explicitly approved.**

When implementation is approved, work incrementally, preserve existing behavior unless a change is approved, and validate each repository and the integrated workflow.

---

## Appendix A — Terminology

| Term | Meaning |
|---|---|
| Goal | The employee's agreed objective |
| Deliverable | Tangible work product or output |
| Outcome | Change resulting from work or deliverable |
| Impact | Broader measurable value or effect |
| Accountability | What the employee is responsible for |
| Validation | Assessment of goal quality and readiness |
| Finding | A specific issue or observation from validation |
| Validation run | One execution against an exact goal version |
| Approval | Human decision to accept a goal |
| Activation | Lifecycle transition that makes a goal active |
| Benchmark case | Controlled input used to evaluate engine behavior |
| Reference outcome | Human-reviewed expected behavior for a benchmark case |

## Appendix B — Status Separation

Do not conflate these independent concepts:

- **Validation status:** `READY`, `NEEDS_IMPROVEMENT`, `NEEDS_REVIEW`, `INVALID`.
- **Approval status:** Pending, approved, rejected or other existing domain values.
- **Lifecycle status:** Draft, approved, active, completed or other existing domain values.
- **Achievement outcome:** `MET`, `PARTIALLY_MET`, `NOT_MET` or other approved assessment labels.

Final enum values must be reconciled with existing MyImpact domain conventions before implementation.
