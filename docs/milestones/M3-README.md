# MyImpact — M3 Document Intelligence & Knowledge

# 1. M3 Objective

M3 turns uploaded career information into **structured, searchable, and semantically retrievable knowledge**.

M3 answers:

> **Can MyImpact understand, structure, store, and retrieve the user's career knowledge?**

M4 will build on this foundation to answer:

> **What evidence demonstrates that expectations are being met, and what impact did that evidence create?**

The core principle remains:

> **Measure impact, not activity.**

M3 therefore focuses on building the reliable **knowledge foundation** required for future evidence and impact intelligence.

---

# 2. M3 Scope

M3 covers:

- Document upload
- PDF/DOCX processing
- Text extraction
- Document classification
- Structured expectation extraction
- Intelligent document chunking
- Embedding provider abstraction
- Embedding generation
- Embedding persistence
- PostgreSQL + pgvector semantic retrieval
- User/document isolation
- End-to-end knowledge pipeline validation

M3 does **not** attempt to determine:

- Whether an expectation was achieved
- Whether work created measurable impact
- Impact magnitude
- Performance ratings
- Career readiness
- Promotion readiness
- Evidence quality scoring
- Final career recommendations

Those belong to M4/M5.

---

# 3. M3 Status

| Area                                          | Status                     |
| --------------------------------------------- | -------------------------- |
| M3.1 Document Domain & Persistence            | ✅ Complete                |
| M3.2 PDF/DOCX Upload                          | ✅ Complete                |
| M3.3 Text Extraction                          | ✅ Complete                |
| M3.4 Document Classification                  | ✅ Complete                |
| M3.5 Structured Expectation Extraction        | ✅ Complete                |
| M3.6.1 Knowledge / Chunk Model                | ✅ Complete                |
| M3.6.2 Intelligent Document Chunking          | ✅ Complete                |
| M3.6.3 Chunk ↔ Expectation Enrichment        | ⏭️ Intentionally skipped |
| M3.6.4 Embedding Provider Abstraction         | ✅ Complete                |
| M3.6.5 Embedding Storage & Semantic Retrieval | ✅ Complete                |
| M3.7 Final Validation                         | ✅ Complete                |

### Final validation

```text
323 tests passed
9 warnings
```

The warnings are dependency/deprecation-related and are not test failures.

---

# 4. High-Level Architecture

```text
                    ┌──────────────────────┐
                    │     User Documents   │
                    │   PDF / DOCX / etc.  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Document Domain    │
                    │   & Persistence      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Text Extraction    │
                    │   PDF / DOCX         │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Classification     │
                    └──────────┬───────────┘
                               │
                               ├──────────────────────┐
                               │                      │
                               ▼                      ▼
                    ┌──────────────────┐   ┌────────────────────┐
                    │ Expectations     │   │ Document Knowledge │
                    │ Extraction       │   │ Chunking           │
                    └────────┬─────────┘   └──────────┬─────────┘
                             │                        │
                             ▼                        ▼
                    ┌──────────────────┐   ┌────────────────────┐
                    │ Structured       │   │ DocumentChunk      │
                    │ Expectations     │   │                    │
                    └────────┬─────────┘   └──────────┬─────────┘
                             │                        │
                             │                        ▼
                             │              ┌────────────────────┐
                             │              │ Embedding Provider │
                             │              └──────────┬─────────┘
                             │                         │
                             │                         ▼
                             │              ┌────────────────────┐
                             │              │ DocumentChunk      │
                             │              │ Embeddings         │
                             │              └──────────┬─────────┘
                             │                         │
                             │                         ▼
                             │              ┌────────────────────┐
                             │              │ PostgreSQL         │
                             │              │ + pgvector         │
                             │              └──────────┬─────────┘
                             │                         │
                             └──────────────┬──────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ M4 Impact Intelligence   │
                              │                          │
                              │ Expectations             │
                              │        ↓                 │
                              │ Semantic Retrieval       │
                              │        ↓                 │
                              │ Evidence Chunks          │
                              │        ↓                 │
                              │ Impact Evaluation        │
                              └──────────────────────────┘
```

---

# 5. Document Processing Flow

The completed M3 document pipeline is:

```text
PDF / DOCX
    ↓
Document
    ↓
Text Extraction
    ↓
Document Classification
    ↓
Expectation Extraction
    ↓
Structured Expectations
    ↓
Intelligent Chunking
    ↓
Document Chunks
    ↓
Embedding Generation
    ↓
Embedding Persistence
    ↓
PostgreSQL + pgvector
    ↓
Semantic Retrieval
```

A document does **not** need to produce expectations.

A document can still be valuable as source knowledge and evidence.

---

# 6. M3.1 — Document Domain & Persistence

M3 introduced the document domain required to represent uploaded career information.

Documents provide the canonical source from which subsequent processing is derived.

The document lifecycle is conceptually:

```text
Uploaded
   ↓
Processing
   ↓
Extracted
   ↓
Classified
   ↓
Structured
   ↓
Completed
```

The exact lifecycle implementation remains owned by the document-processing domain.

The important architectural principle is:

> Document content is the source of truth. All derived knowledge can be regenerated.

---

# 7. M3.2 — PDF/DOCX Upload

M3 supports ingestion of career-related PDF and DOCX documents.

Typical examples include:

- Performance reviews
- Role descriptions
- Job expectations
- Goal documents
- Feedback
- Career documents
- Project documents
- Other professional documentation

The uploaded document becomes the source artifact from which structured knowledge is derived.

---

# 8. M3.3 — Text Extraction

Documents are processed to extract usable textual content.

The extraction pipeline supports:

```text
PDF
 └── extracted text

DOCX
 └── extracted text
```

The extracted content becomes the input for:

- Classification
- Expectation extraction
- Intelligent chunking
- Embedding generation

The extraction layer should remain independent of downstream intelligence.

---

# 9. M3.4 — Document Classification

Documents are classified so that MyImpact can understand the nature of the source material.

Classification provides contextual information for subsequent processing.

Classification is metadata about the source.

It is not an assessment of the user's performance.

---

# 10. M3.5 — Structured Expectation Extraction

M3 extracts structured expectations from relevant documents.

Examples of expectations may include:

- Technical leadership
- Delivery ownership
- Architecture responsibility
- Team leadership
- Stakeholder management
- Quality improvement
- Operational excellence

The important distinction is:

```text
Document
   ↓
Potential expectations
   ↓
Structured expectations
```

An expectation is **not evidence**.

An expectation describes what is expected.

Evidence will later describe what actually happened.

---

# 11. M3.6.1 — Knowledge / DocumentChunk Model

`DocumentChunk` is the canonical source-knowledge representation used for semantic retrieval.

Conceptually:

```text
DocumentChunk
├── id
├── document_id
├── chunk_index
├── content
├── heading_path
├── document_type
├── scope_type
├── scope_id
├── metadata
├── created_at
└── updated_at
```

### Important principles

### `content`

The actual source text.

This remains the canonical knowledge content.

### `chunk_index`

Represents source order within the document.

### `heading_path`

Represents the hierarchical context of the chunk.

For example:

```text
["Performance", "Technical Leadership", "Architecture"]
```

The heading hierarchy is retained without persisting redundant heading/level/display-path fields.

### `metadata`

Stores additional contextual information without polluting the core model.

---

# 12. M3.6.2 — Intelligent Document Chunking

The chunking system converts extracted document text into meaningful knowledge units.

The chunking strategy supports:

- Heading hierarchy
- Multiple chunks under the same heading
- Large-section splitting
- Documents without headings
- Source-order preservation
- Heading context
- Safe replacement during reprocessing

Example:

```text
Document
│
├── Performance
│   │
│   ├── Technical Leadership
│   │   ├── Chunk 1
│   │   └── Chunk 2
│   │
│   └── Delivery
│       ├── Chunk 3
│       └── Chunk 4
│
└── Goals
    └── Chunk 5
```

The heading itself is represented through `heading_path` rather than being unnecessarily duplicated inside chunk content.

---

# 13. M3.6.3 — Chunk ↔ Expectation Mapping

A persistent direct relationship between:

```text
DocumentChunk ↔ Expectation
```

was intentionally **not introduced** in M3.

The reasoning is that semantic retrieval can dynamically connect expectations with relevant knowledge when needed.

The intended M4 flow is:

```text
Expectation
    ↓
Semantic Retrieval
    ↓
Relevant Document Chunks
    ↓
Evidence Evaluation
    ↓
Impact Analysis
```

This avoids creating a potentially stale or overly rigid mapping layer.

If future requirements demonstrate a persistent relationship is necessary, it can be introduced later.

---

# 14. M3.6.4 — Embedding Provider Abstraction

Embeddings are generated through a provider abstraction.

The application uses:

```text
IEmbeddingService
```

This keeps the core application independent of a specific embedding vendor.

Supported providers include:

```text
Mock
OpenAI
Azure OpenAI
```

Provider selection is configuration-driven.

---

# 15. Embedding Model

The embedding request/response model supports batched inputs.

Conceptually:

```text
EmbeddingRequest
├── inputs[]
└── optional provider configuration

EmbeddingResponse
├── embeddings[]
├── model
└── dimensions
```

The abstraction allows the application to:

- Generate multiple embeddings
- Change providers
- Change models
- Test without external API calls
- Keep vendor-specific details outside domain logic

---

# 16. Embedding Configuration

Default development configuration:

```text
EMBEDDING_PROVIDER=mock
```

Supported values:

```text
mock
openai
azure
```

### OpenAI

```text
OPENAI_API_KEY
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

### Azure OpenAI

```text
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_API_VERSION
AZURE_OPENAI_EMBEDDING_DEPLOYMENT
```

Secrets must not be committed to source control.

---

# 17. M3.6.5 — Embedding Storage

Embeddings are treated as **derived data**.

The conceptual model is:

```text
DocumentChunk
       │
       │ 1 : 1
       ▼
DocumentChunkEmbedding
```

Conceptually:

```text
DocumentChunkEmbedding
├── id
├── chunk_id
├── embedding
├── embedding_model
├── embedding_dimensions
├── created_at
└── updated_at
```

The embedding is derived from the canonical:

```text
DocumentChunk.content
```

Therefore embeddings can be regenerated if required.

---

# 18. PostgreSQL + pgvector

M3 uses:

```text
PostgreSQL 16
+
pgvector
```

Development environment:

```text
PostgreSQL container:
myimpact-postgres

Database:
myimpact

Host port:
5556

Container port:
5432
```

The pgvector-enabled image is:

```text
pgvector/pgvector:pg16
```

The development environment currently uses pgvector 0.8.7.

---

# 19. Semantic Retrieval

Semantic retrieval converts a natural-language query into an embedding and uses vector similarity to locate relevant document chunks.

Flow:

```text
Natural-language query
        ↓
Embedding Provider
        ↓
Query embedding
        ↓
pgvector similarity search
        ↓
Relevant DocumentChunk records
```

The `SemanticRetrievalService` is responsible for this orchestration.

Conceptually:

```python
results = await semantic_retrieval_service.retrieve(
    query="What did I do related to technical leadership?",
    limit=5,
    document_id=None,
    user_id=user_id,
)
```

The retrieval service:

1. Validates the query.
2. Generates a query embedding.
3. Validates the embedding response.
4. Uses the returned embedding model.
5. Searches the vector store.
6. Applies optional document/user scope.
7. Returns relevant knowledge chunks.

---

# 20. Semantic Retrieval Result

The service returns knowledge-oriented search results containing information such as:

```text
chunk_id
document_id
content
heading_path
document_type
scope_type
scope_id
metadata
similarity
```

The similarity value describes semantic relevance between the query and the stored chunk.

It is **not** an impact score.

---

# 21. Important Architectural Rule

## Vector Similarity ≠ Impact

This distinction is critical.

A high vector similarity means:

> "This content is semantically related to the query."

It does **not** mean:

> "This person had high impact."

Therefore M4 must not use raw vector similarity as an impact measurement.

Correct flow:

```text
Expectation
     ↓
Semantic Retrieval
     ↓
Relevant Evidence
     ↓
Evidence Evaluation
     ↓
Impact Analysis
```

---

# 22. User Isolation

Knowledge retrieval must respect user ownership.

A semantic query may optionally be scoped using:

```text
user_id
document_id
```

The repository layer is responsible for applying the appropriate filtering.

The system must never allow a user's retrieval query to return another user's private career knowledge.

User isolation has been explicitly validated through integration testing.

---

# 23. Product API Boundary

The intended product-facing retrieval boundary is:

```http
POST /knowledge/retrieve
```

The product API should accept a natural-language query and return useful knowledge.

Example conceptual request:

```json
{
  "query": "What evidence do I have for technical leadership?"
}
```

The internal implementation details should remain hidden from product consumers.

The product API should **not** expose internal concepts such as:

```text
/chunks/search
/documents/search
/vector/search
embedding_model
embedding_dimensions
vector similarity implementation
```

Internally, the service may use:

```text
limit
similarity thresholds
embedding model
embedding dimensions
document scope
user scope
```

These are implementation details.

> Note: `/knowledge/retrieve` is the intended product-facing boundary. M3's completed validation is centered on the semantic retrieval service and pipeline; the API boundary should be treated as the product integration contract unless an implementation is explicitly present in the API layer.

---

# 24. Knowledge Retrieval as a Platform Capability

Semantic retrieval is not itself the final user experience.

It is a reusable platform capability for future MyImpact intelligence.

Potential consumers include:

```text
M4 Impact Intelligence
M5 Career Assistant
1:1 Assistant
Career Review Assistant
Goal / Expectation Analysis
Evidence Discovery
```

The consumers should not need to know how embeddings or pgvector work.

---

# 25. Reprocessing Behaviour

Document processing must support safe regeneration.

The intended model is:

```text
Original Document
       │
       ├── Extracted Text
       ├── Classification
       ├── Expectations
       └── Document Chunks
                │
                └── Embeddings
```

Derived knowledge can be regenerated from the source document.

This avoids treating derived representations as the ultimate source of truth.

---

# 26. M3 Testing

M3 was validated at multiple levels.

### Unit tests

Provider abstractions, services, validation and edge cases.

### Integration tests

Repository and PostgreSQL/pgvector behaviour.

### Isolation tests

Verification that user-scoped retrieval does not leak knowledge across users.

### End-to-end pipeline test

Validated the complete knowledge flow:

```text
Document
   ↓
Text / Chunks
   ↓
Embedding
   ↓
Persistence
   ↓
Semantic Retrieval
```

### Final result

```text
323 passed
9 warnings
```

---

# 27. Semantic Retrieval Edge Cases

The semantic retrieval tests cover:

### Empty query

An empty or whitespace-only query is rejected.

### Invalid embedding response

The service validates that exactly one query embedding is returned.

### Missing embedding model

The service rejects responses without an embedding model.

### Zero embeddings

The system handles the absence of stored embeddings.

### Multiple embeddings

The repository can return multiple relevant chunks.

### Empty repository result

Semantic retrieval correctly returns an empty result when no matching knowledge exists.

### User isolation

Retrieval respects user boundaries.

---

# 28. End-to-End Knowledge Scenario

A representative M3 scenario is:

```text
1. User uploads performance review
             ↓
2. Document is persisted
             ↓
3. Text is extracted
             ↓
4. Document is classified
             ↓
5. Expectations are extracted where applicable
             ↓
6. Document is intelligently chunked
             ↓
7. Chunks are persisted
             ↓
8. Chunk embeddings are generated
             ↓
9. Embeddings are persisted in pgvector
             ↓
10. User asks:
    "What did I do related to technical leadership?"
             ↓
11. Query embedding is generated
             ↓
12. pgvector finds relevant chunks
             ↓
13. Relevant source knowledge is returned
```

At this point M3 is complete.

M4 starts from the retrieved knowledge.

---

# 29. M3 → M4 Boundary

The most important architectural boundary is:

```text
                    M3
────────────────────────────────────
Documents
   ↓
Extracted Knowledge
   ↓
Document Chunks
   ↓
Embeddings
   ↓
Semantic Retrieval
────────────────────────────────────
                    ↓
                    ↓
                    ↓
                    M4
────────────────────────────────────
Expectations
   ↓
Relevant Evidence
   ↓
Evidence Evaluation
   ↓
Impact Analysis
   ↓
Coverage / Gaps
   ↓
Career Intelligence
────────────────────────────────────
```

M3 answers:

> **What knowledge do we have?**

M4 answers:

> **What does that knowledge demonstrate?**

---

# 30. M4 Starting Point

M4 should consume existing M3 capabilities rather than rebuilding retrieval.

Expected conceptual flow:

```text
Role / Goals / Expectations
             ↓
       Expectation
             ↓
   Semantic Retrieval
             ↓
   Relevant Evidence Chunks
             ↓
    Evidence Evaluation
             ↓
      Impact Analysis
             ↓
      Coverage / Gaps
             ↓
       Career Insight
```

This preserves the separation between:

```text
Knowledge
Evidence
Impact
```

---

# 31. What M3 Does Not Do

M3 intentionally does not implement:

- Impact scoring
- Evidence scoring
- Expectation coverage scoring
- Career-readiness scoring
- Promotion recommendations
- Performance ratings
- Manager recommendations
- Career-path recommendations
- AI career coaching
- Automated 1:1 conversations
- Final impact narratives

Those belong to later product capabilities.

---

# 32. Architectural Decisions

## Decision 1 — Document content is canonical

`DocumentChunk.content` represents source knowledge.

Embeddings are derived.

## Decision 2 — Embeddings are separate from DocumentChunk

Embedding-specific information belongs in the embedding model rather than the core knowledge entity.

This keeps semantic infrastructure concerns separate from source knowledge.

## Decision 3 — Provider abstraction

Embedding vendors are hidden behind:

```text
IEmbeddingService
```

This allows provider/model changes without changing domain logic.

## Decision 4 — No persistent Chunk ↔ Expectation mapping

M3 does not create a permanent direct relationship between expectations and chunks.

Semantic retrieval can dynamically establish relevance when required.

## Decision 5 — Semantic similarity is not impact

Vector similarity is a retrieval mechanism.

It is not a business metric.

## Decision 6 — Product APIs hide infrastructure

Consumers should interact with knowledge capabilities rather than vector database implementation details.

## Decision 7 — Derived knowledge must be regenerable

Documents remain the source of truth.

Chunks and embeddings can be recreated.

---

# 33. Database Considerations

The project uses PostgreSQL with pgvector.

Database migrations belong in the separate:

```text
myimpact-db
```

repository.

Application code should not become the owner of database migration history.

The database repository remains responsible for:

- Flyway migrations
- Schema evolution
- pgvector-related schema changes
- Database versioning

---

# 34. Development Database

Current development database configuration:

```text
Container:
myimpact-postgres

Database:
myimpact

Host:
localhost

Port:
5556
```

Do not destroy the database volume merely to resolve PostgreSQL collation warnings.

Avoid:

```bash
docker compose down -v
```

unless database data destruction is explicitly intended.

---

# 35. Future Backlog

The following future item remains intentionally outside M3:

```text
Future: Async Document Processing

Move Docling and subsequent document processing to a background
worker/queue with processing status, retries, and detailed
execution tracking.
```

This should be treated as future architecture work rather than part of the completed M3 milestone.

---

# 36. M3 Definition of Done

M3 is considered complete when the system can:

- [X] Accept PDF documents
- [X] Accept DOCX documents
- [X] Persist document metadata
- [X] Extract document text
- [X] Classify documents
- [X] Extract structured expectations where applicable
- [X] Create intelligent hierarchical document chunks
- [X] Persist document chunks
- [X] Generate embeddings
- [X] Support configurable embedding providers
- [X] Persist embeddings
- [X] Store vectors using PostgreSQL + pgvector
- [X] Generate query embeddings
- [X] Perform semantic retrieval
- [X] Support user/document scoped retrieval
- [X] Validate user isolation
- [X] Validate the complete knowledge pipeline
- [X] Pass the complete test suite

Final validation:

```text
323 passed
9 warnings
```

---

# 37. Repository Checkpoint

M3 development was completed on:

```text
Branch:
m3-development
```

Final M3 completion commit:

```text
368c256 M3.7: complete knowledge pipeline validation
```

Previous semantic retrieval checkpoint:

```text
1a44c3a m3.6.5: feat: add embedding storage and semantic retrieval
```

At the M3 completion checkpoint, the only untracked item was:

```text
backlog.txt
```

containing the future asynchronous document-processing item.

---

# 38. Important Source Files

The M3 implementation includes the following major areas.

### Embedding models

```text
app/models/embedding.py
```

### Embedding interface

```text
app/services/embedding/interface.py
```

### Embedding providers

```text
app/services/embedding/openai_service.py
app/services/embedding/azure_service.py
app/services/embedding/mock_service.py
```

### Embedding factory

```text
app/services/embedding/factory.py
```

### Document chunk embeddings

```text
app/models/document_chunk_embedding.py
app/repositories/document_chunk_embedding.py
app/services/document_chunk_embedding.py
```

### Semantic retrieval

```text
app/services/semantic_retrieval.py
```

### Knowledge tests

```text
tests/unit/services/knowledge/test_semantic_retrieval.py
tests/integration/services/test_semantic_retrieval.py
tests/integration/services/test_semantic_retrieval_isolation.py
tests/e2e/test_knowledge_pipeline.py
```

---

# 39. Working Rules for Future Development

The following rules should continue into M4 and beyond.

### 1. Inspect before changing

Always inspect the current implementation before introducing a new model, service, repository, or abstraction.

### 2. Avoid redundant models

Prefer extending an existing canonical model when it already represents the required concept.

### 3. Keep one source of truth

Do not duplicate data merely to make a feature easier to implement.

### 4. Keep infrastructure behind services

Business logic should not depend directly on:

- pgvector implementation
- embedding vendors
- database-specific details
- provider-specific APIs

### 5. Test after every meaningful milestone

Run focused tests first, followed by the complete suite at a clean checkpoint.

### 6. Commit clean checkpoints

Use meaningful commits for completed milestones.

### 7. Do not over-engineer

Introduce additional relationships, abstractions, or persistence only when a real product requirement justifies them.

### 8. Keep product concepts separate from infrastructure

For example:

```text
User asks:
"What evidence supports my technical leadership?"

Product concept:
Knowledge / Evidence retrieval

Internal implementation:
Embedding → pgvector → DocumentChunk
```

The latter should remain hidden from the product contract.

---

# 40. M3 Summary

M3 establishes the **knowledge foundation of MyImpact**.

The completed pipeline is:

```text
                    DOCUMENTS
                        │
                        ▼
                TEXT EXTRACTION
                        │
                        ▼
                CLASSIFICATION
                        │
             ┌──────────┴──────────┐
             │                     │
             ▼                     ▼
       EXPECTATIONS          DOCUMENT CHUNKS
                                   │
                                   ▼
                              EMBEDDINGS
                                   │
                                   ▼
                           POSTGRES + PGVECTOR
                                   │
                                   ▼
                         SEMANTIC RETRIEVAL
                                   │
                                   ▼
                            RELEVANT KNOWLEDGE
                                   │
                                   ▼
                              M4 EVIDENCE
                                   │
                                   ▼
                             IMPACT INTELLIGENCE
```

The architectural progression is therefore:

```text
M3
Knowledge
  ↓
M4
Evidence
  ↓
Impact
  ↓
M5
Assistant
```

The key principle remains:

> **MyImpact should not measure how much activity happened. It should use reliable source knowledge to understand what was expected, what evidence exists, and ultimately what impact was created.**

---

## Final M3 Checkpoint

```text
Milestone: M3 — Document Intelligence & Knowledge

Status: COMPLETE

Tests:
323 passed

Warnings:
9 dependency/deprecation warnings

Semantic Retrieval:
Implemented

Vector Storage:
PostgreSQL + pgvector

Embedding Providers:
Mock / OpenAI / Azure OpenAI

User Isolation:
Validated

End-to-End Knowledge Pipeline:
Validated

Next Major Milestone:
M4 — Impact Intelligence
```
