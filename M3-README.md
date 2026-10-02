# MyImpact AI — M3 Document Intelligence & Knowledge

> **M3 turns uploaded career information into structured, retrievable knowledge.**

## Milestone Goal

M3 establishes the document intelligence foundation required for MyImpact to understand role expectations, represent source knowledge, and retrieve relevant knowledge semantically.

M3 answers:

> **Can MyImpact understand and retrieve the user's career knowledge?**

M4 will build on this foundation to answer a different question:

> **What evidence demonstrates that the expectations are being met, and what impact did it create?**

---

# M3 Status

| Area | Status |
|---|---|
| M3.1 Document domain & persistence | ✅ Complete |
| M3.2 PDF/DOCX upload | ✅ Complete |
| M3.3 Text extraction | ✅ Complete |
| M3.4 Document classification | ✅ Complete |
| M3.5 Structured expectation extraction | ✅ Complete |
| M3.6.1 Knowledge / chunk model | ✅ Complete |
| M3.6.2 Intelligent document chunking | ✅ Complete |
| M3.6.3 Chunk ↔ expectation enrichment | ⏭️ Intentionally skipped |
| M3.6.4 Embedding provider abstraction | 🚧 Current step |
| M3.6.5 Vector persistence | ⏳ Pending |
| M3.6.6 Semantic retrieval | ⏳ Pending |
| M3.6.7 Knowledge retrieval API | ⏳ Pending |
| M3.6.8 End-to-end retrieval validation | ⏳ Pending |
| M3.7 Final validation | ⏳ Pending |

---

# Current Document Processing Flow

```text
PDF / DOCX
    │
    ▼
Document
    │
    ▼
Text Extraction
    │
    ├───────────────────┐
    ▼                   ▼
Classification      Expectation Extraction
    │                   │
    │                   ▼
    │             Structured Expectations
    │
    ▼
Intelligent Chunking
    │
    ▼
Document Chunks
```

A document does **not** have to produce expectations. Expectations are derived structured knowledge for documents where they are applicable.

For example:

```text
JL5 Roles & Responsibilities
    ├── Expectations
    └── Chunks

Development Journey
    └── Chunks
```

The Development Journey can later act as an evidence source without being forced into an expectation model.

---

# M3.5 — Structured Expectations

Expectation extraction is already implemented.

The processing pipeline uses the extracted document content and an LLM to identify structured expectations such as:

- expectation category
- expectation statement
- confidence

Expectations are persisted independently from document chunks.

This separation is intentional:

```text
Document
 ├── Structured Knowledge
 │      └── Expectations
 │
 └── Source Knowledge
        └── Chunks
```

We do **not** currently persist a chunk-to-expectation mapping.

That relationship can be discovered later during M4 evidence evaluation when an expectation is matched against relevant evidence.

---

# M3.6.1 — Knowledge / Chunk Model

`DocumentChunk` is the canonical source-knowledge representation.

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

## Heading hierarchy

`heading_path` is the canonical hierarchy.

Example:

```json
[
  "Engineering Expectations",
  "Technical Leadership",
  "Architecture"
]
```

Derived values such as the final heading, level, and display path are calculated when needed rather than persisted redundantly.

`chunk_index` preserves source-document order and is separate from heading hierarchy.

---

# M3.6.2 — Intelligent Document Chunking

The chunking service converts extracted Markdown into meaningful chunks while preserving document structure.

Capabilities include:

- Markdown heading hierarchy
- Canonical `heading_path`
- Multiple chunks under the same heading
- Large-section splitting
- Documents without headings
- Heading excluded from chunk content
- Safe replacement during document reprocessing
- Persistence through the document processing flow

Chunks remain an internal knowledge representation. M3 does not expose public CRUD APIs for chunks.

---

# M3.6.3 — Why Chunk ↔ Expectation Mapping Is Skipped

We intentionally do **not** create a `document_chunk_expectations` relationship at this stage.

The current model already provides:

```text
Document
 ├── Expectations
 └── Chunks
```

Creating a permanent relationship between every chunk and expectation would duplicate information without a demonstrated product need.

Later, M4 can perform:

```text
Expectation
     │
     ▼
Semantic retrieval
     │
     ▼
Relevant evidence chunks
     │
     ▼
Impact / evidence evaluation
```

This keeps M3 simple and leaves the relationship as an intelligence result rather than a prematurely persisted structural relationship.

---

# M3.6.4 — Embedding Provider Abstraction

The current step introduces a provider-neutral embedding contract.

```text
                    IEmbeddingService
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          OpenAI         Azure          Mock
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    EmbeddingResponse
```

The abstraction supports batched inputs because document processing will normally embed multiple chunks together.

Current implementation:

```text
app/models/embedding.py
app/services/embedding/interface.py
app/services/embedding/openai_service.py
app/services/embedding/azure_service.py
app/services/embedding/mock_service.py
app/services/embedding/factory.py
```

The existing `openai` Python dependency is reused; no additional embedding SDK is required.

## Configuration

Embedding provider selection:

```env
EMBEDDING_PROVIDER=mock
```

Supported providers:

```text
mock
openai
azure
```

OpenAI configuration:

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Azure configuration:

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=
```

The mock provider is the default so unit tests and local development do not require an external embedding service.

## What M3.6.4 does not do yet

It intentionally does **not**:

- store vectors in PostgreSQL
- add pgvector
- perform similarity search
- modify `DocumentChunk` to contain a vector
- create a retrieval endpoint
- perform RAG

Those belong to the next M3.6 steps.

---

# Next: M3.6.5 — Vector Persistence

The next step will decide and implement vector persistence, currently expected to use PostgreSQL with `pgvector`.

The important design principle is:

```text
DocumentChunk.content
        │
        ▼
Embedding Provider
        │
        ▼
Derived Vector Representation
        │
        ▼
Vector Store
```

The chunk content remains the canonical source. Embeddings are derived data and can be regenerated if the embedding model changes.

---

# Future Semantic Retrieval

Once vector persistence is available:

```text
Natural-language query
        │
        ▼
Query embedding
        │
        ▼
Vector similarity search
        │
        ▼
Relevant document chunks
```

The product-level API should represent knowledge retrieval rather than expose internal chunk mechanics. The expected future boundary is conceptually:

```http
POST /knowledge/retrieve
```

The user should not need to provide internal fields such as `chunk_id`, `heading_path`, or embedding configuration just to ask a knowledge question.

---

# M4 Relationship

M3 provides the knowledge foundation.

M4 will combine:

```text
Role / Goals / Expectations
             +
       Evidence sources
             +
     Retrieved knowledge
             ↓
      Evidence evaluation
             ↓
        Impact analysis
```

For example:

```text
JL5 Roles & Responsibilities
        │
        └── Expectation:
            "Drive architecture decisions"

Development Journey
        │
        └── Evidence chunks:
            "Led Vessel Simulator architecture..."

                 ↓

        M4 Evidence Evaluation
```

The system should not equate vector similarity with impact score. Semantic similarity is used to find potentially relevant evidence; impact evaluation is a separate intelligence step.

---

# Validation

The repository checkpoint before M3.6.4 had:

```text
299 tests passing
```

For M3.6.4, run the focused embedding tests first:

```bash
pytest tests/unit/services/embedding -v
```

Then run the complete suite:

```bash
pytest -v
```

M3.6.4 should preserve the existing M3 behavior while adding only the embedding abstraction and its provider implementations.

---

# M3 Definition of Done

M3 is complete when MyImpact can:

1. Accept PDF/DOCX career documents.
2. Extract their content.
3. Classify the document.
4. Derive structured expectations where applicable.
5. Represent source knowledge as ordered hierarchical chunks.
6. Generate embeddings through a provider-neutral abstraction.
7. Persist those embeddings in a vector-capable store.
8. Retrieve relevant knowledge semantically.
9. Expose knowledge retrieval through a product-level API.
10. Validate the complete ingestion-to-retrieval flow.

At that point MyImpact has a usable **Personal Career Knowledge System** foundation, ready for M4 Impact Intelligence.
