# M3.6.5 — Embedding Storage & Semantic Retrieval

## Goal

Persist document-chunk embeddings in PostgreSQL with pgvector and provide a service-level semantic retrieval path.

## Included

- `DocumentChunkEmbedding` domain model
- PostgreSQL/pgvector persistence model
- Upsert and lookup by chunk
- Delete by chunk/document
- Exact cosine-similarity retrieval
- Embedding-model and dimension filtering
- `SemanticRetrievalService`
- `KnowledgeSearchResult`
- Unit and PostgreSQL integration tests
- `pgvector` Python dependency

## Intentionally not included

- Public retrieval API
- RAG orchestration
- Impact scoring
- Expectation-to-evidence evaluation
- Approximate vector indexes

The retrieval result is a knowledge retrieval result. Its similarity value is only a retrieval signal and is not an impact score.
