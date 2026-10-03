# M4 — Impact Intelligence

## Overview

M4 introduces the **Impact Intelligence** layer of MyImpact AI.

The purpose of M4 is to move from stored knowledge and document expectations to **evidence-grounded impact understanding**:

```text
Document Expectations
        ↓
Evidence Discovery
        ↓
Evidence Evaluation
        ↓
Evidence Persistence
        ↓
Impact Assessment
        ↓
Career Insight
```

M4 builds on the semantic knowledge and retrieval capabilities established in M3. Semantic similarity is used to **discover relevant evidence**, but it is not treated as proof of impact or used directly as an impact score.

---

## M4 Architecture

```text
                         M3 Knowledge
                              │
                              ▼
                    DocumentExpectation
                              │
                              ▼
                     Evidence Discovery
                              │
                    Semantic Retrieval
                              │
                              ▼
                    Evidence Candidates
                              │
                              ▼
                    Evidence Evaluation
                              │
                              ▼
                    Evidence Persistence
                     ┌────────┼─────────┐
                     ▼        ▼         ▼
                  Evidence  Evidence  Evidence
                            Version
                     │
                     ▼
                 EvidenceMapping
                     │
                     ▼
                     Goal
                     │
                     ▼
              Impact Assessment
                     │
                     ▼
               Career Insight
```

---

# M4.1 — Impact Intelligence Contracts

## Purpose

Introduce the first transient contracts for M4 evidence intelligence without changing the database schema.

## Contracts

`app/models/impact_intelligence.py` contains the transient contracts used across M4:

- `EvidenceSupportLevel`
- `EvidenceCandidate`
- `EvidenceEvaluation`
- `ExpectationEvidenceResult`

Later M4 stages extend this contract set with:

- `ImpactAssessmentEvaluation`
- `CareerInsight`

The contracts are Pydantic models and are not persisted as separate database entities.

## Architecture

```text
DocumentExpectation
        ↓
Semantic Retrieval
        ↓
EvidenceCandidate
        ↓
EvidenceEvaluation
        ↓
Evidence
        ↓
EvidenceMapping
        ↓
ImpactAssessment
```

## Boundary

No database tables or migrations are introduced for these contracts.

---

# M4.2 — Evidence Discovery

## Purpose

Discover potentially relevant evidence for each document expectation using the existing semantic retrieval capability from M3.

## Flow

```text
DocumentExpectation
        ↓
EvidenceDiscoveryService
        ↓
Build deterministic query
        ↓
SemanticRetrievalService
        ↓
KnowledgeSearchResult[]
        ↓
EvidenceCandidate[]
```

## Design

- Reuses the existing `SemanticRetrievalService`.
- Builds a deterministic retrieval query from the expectation description and evidence hints.
- Restricts retrieval to the expectation's document where applicable.
- Preserves user isolation.
- Does not use an LLM.
- Does not persist an expectation-to-chunk relationship.

## Important boundary

Semantic similarity is a **discovery signal only**.

A high similarity score does not prove that an expectation was achieved and is not used as an impact score.

---

# M4.3 — Evidence Evaluation

## Purpose

Determine whether semantically retrieved evidence actually supports an expectation.

## Flow

```text
Expectation
     ↓
Evidence Candidates
     ↓
Evidence Evaluation
```

## Evaluation Contract

Each candidate is evaluated with:

```text
candidate_chunk_id
supports_expectation
support_level
confidence
rationale
```

`support_level` can be:

- `none`
- `weak`
- `moderate`
- `strong`

## Design

The existing LLM abstraction is used to evaluate evidence.

The evaluator must distinguish between:

- semantic relevance, and
- actual evidence supporting the expectation.

The LLM must not treat high semantic similarity as proof of achievement.

No database schema changes are introduced.

---

# M4.4 — Evidence Persistence & Mapping

## Purpose

Persist only evidence that has been evaluated as materially supporting an expectation, then map that evidence to a user-owned goal.

## Flow

```text
Expectation
    ↓
EvidenceCandidate
    ↓
EvidenceEvaluation
    ↓
EvidencePersistenceService
    ├── Evidence
    ├── EvidenceVersion
    └── EvidenceMapping → Goal
```

## Persistence Rules

| Evaluation | Persistence | Relevance |
|---|---|---|
| `strong` + supported | Yes | `HIGH` |
| `moderate` + supported | Yes | `MEDIUM` |
| `weak` | No | — |
| `none` | No | — |
| unsupported | No | — |

Additional rules:

- Unsupported evidence is never persisted, even if its support level is strong.
- Document chunk ID is used as the evidence source ID.
- Evidence content hash is deterministic SHA-256.
- The first persisted version is `EvidenceVersion.version = 1`.
- Existing evidence for the same document chunk and user is reused.
- Existing evidence-to-goal mapping is reused.
- Repeated persistence is therefore idempotent.
- Goal ownership is validated before persistence.

## Boundary

M4.4 reuses the existing:

- `Evidence`
- `EvidenceVersion`
- `EvidenceMapping`
- `Goal`

persistence models.

No new database tables or migrations are introduced.

---

# M4.5 — Impact Assessment

## Purpose

Evaluate the impact represented by persisted evidence against a user goal using the existing LLM abstraction and existing `ImpactAssessment` persistence model.

## Flow

```text
Persisted Evidence
       +
      Goal
       ↓
ImpactAssessmentEvaluationService
       ↓
ImpactAssessmentEvaluation
       ↓
Existing ImpactAssessmentService
       ↓
ImpactAssessment
```

## Evaluation Contract

The transient evaluation contains:

- `impact_type`
- `impact_summary`
- `impact_score`
- `confidence`

Rules:

- `impact_type` uses the existing `ImpactType` enum.
- `impact_summary` is concise and evidence-grounded.
- `impact_score` is constrained to `0..1`.
- `confidence` is constrained to `0..1`.

## Guardrails

- The LLM receives only the relevant goal and persisted evidence.
- Semantic similarity is not used as an impact score.
- The evaluator must not invent outcomes or metrics absent from the evidence.
- Invalid provider output is rejected rather than persisted.
- Evidence without a description cannot be safely assessed.

## Boundary

M4.5 adds a transient evaluation contract and LLM-backed evaluation service, then uses the existing `ImpactAssessmentService` for persistence.

No new database tables or migrations are introduced.

---

# M4.6 — Career Insight

## Purpose

Synthesize multiple persisted impact assessments for a goal into one concise, evidence-grounded career insight.

## Flow

```text
Persisted ImpactAssessments
          +
         Goal
          ↓
CareerInsightService
          ↓
CareerInsight
```

## CareerInsight Contract

`CareerInsight` contains:

- `goal_id`
- `headline`
- `summary`
- `impact_types`
- `supporting_assessment_ids`
- `confidence`

## Guardrails

- At least one impact assessment is required.
- Every supplied assessment must belong to the supplied goal.
- The LLM receives only the goal and supplied impact assessments.
- The LLM must not invent outcomes, metrics, achievements, themes, or gaps.
- Supporting assessment IDs must refer only to supplied assessments.
- Returned goal ID must match the supplied goal.
- Invalid provider output is rejected.

## Boundary

`CareerInsight` is a transient synthesis result.

It does not replace the persisted `ImpactAssessment` model and does not introduce a separate persisted career-insight entity.

---

# M4.7 — End-to-End Impact Intelligence Pipeline

## Purpose

Orchestrate the existing M4 stages into one end-to-end flow without introducing a new persistence model.

## Flow

```text
DocumentExpectation
        ↓
Evidence Discovery
        ↓
Evidence Evaluation
        ↓
Evidence Persistence
        ↓
Impact Assessment Evaluation
        ↓
ImpactAssessment Persistence
        ↓
Career Insight
```

## Responsibilities

The pipeline:

- Validates goal ownership for the supplied user.
- Processes one or more document expectations.
- Reuses the existing M4.2–M4.6 services.
- Persists only evidence accepted by the M4.4 rules.
- Assesses each unique persisted evidence item once per goal during the run.
- Synthesizes the resulting impact assessments into `CareerInsight`.
- Returns pipeline counters for observability and testing.

## Pipeline Result

The transient pipeline result includes:

- career insight
- processed expectation count
- discovered candidate count
- evaluated candidate count
- persisted evidence count
- impact assessment count

## Boundaries

- No new database tables.
- No migrations.
- No new persisted career-insight entity.
- Semantic similarity remains evidence discovery only.
- Existing M4 services remain independently testable.
- The pipeline does not expose a new API route yet.

API exposure should follow after the orchestration contract is validated.

---

# Cross-Cutting M4 Guardrails

## Evidence Grounding

M4 keeps a strict distinction between:

```text
Semantic Similarity
        ≠
Evidence Support
        ≠
Impact Score
```

Semantic retrieval finds potentially relevant content.

Evidence evaluation determines whether that content supports an expectation.

Impact assessment evaluates the impact represented by persisted evidence.

## User Isolation

Goal ownership and evidence ownership are validated at the relevant persistence and orchestration boundaries.

## Idempotency

Evidence and evidence-to-goal mappings are reused where appropriate so repeated processing does not unnecessarily create duplicate persistence records.

## Persistence Discipline

M4 reuses the existing domain and persistence model.

No unnecessary:

- database tables
- migrations
- persisted career-insight entities
- expectation-to-chunk persistence relationships

are introduced.

---

# Validation

## Focused M4 Validation

The individual M4 stages were validated with focused unit tests throughout development.

The final M4.7 pipeline validation passed:

```text
8 passed
```

## Final M4 Regression Validation

The complete test suite passed:

```text
373 passed, 9 warnings
```

There were:

```text
0 failures
```

This represents the final M4 validation checkpoint.

---

# Final M4 Architecture

```text
                         KNOWLEDGE
                            │
                            ▼
                 Document Expectations
                            │
                            ▼
                  Evidence Discovery
                            │
                            ▼
                  Evidence Candidates
                            │
                            ▼
                  Evidence Evaluation
                            │
                            ▼
                 Evidence Persistence
                            │
                            ▼
                  Impact Assessment
                            │
                            ▼
                    Career Insight
```

M4 therefore establishes the complete **Impact Intelligence pipeline** from expectations and knowledge through evidence, impact assessment, and career-level insight.
