# MyImpact M3.6.2 — Intelligent Document Chunking

## Objective

Convert the normalized Markdown produced by document extraction into ordered, heading-aware knowledge chunks and persist those chunks as part of document processing.

## What is included

- `DocumentChunkingService`
- Markdown heading hierarchy parsing
- Canonical `heading_path` generation
- Content-only chunk bodies (headings are not duplicated into `content`)
- Multiple chunks under the same heading path
- Chunk splitting for large sections
- Support for documents/content without headings
- `DocumentService` integration after extraction/classification/expectation processing
- Safe replacement of existing chunks during reprocessing
- API dependency wiring for the production document-processing path
- Unit and integration tests

## Heading hierarchy

`heading_path` remains the canonical persisted breadcrumb:

```json
[
  "Engineering Expectations",
  "Technical Leadership",
  "Architecture"
]
```

The following are intentionally **not** persisted redundantly:

- heading
- heading level
- heading path text

They can be derived when needed:

```text
heading       = heading_path[-1]
heading_level = len(heading_path)
path_text     = " > ".join(heading_path)
```

## Processing flow

```text
Document
  ↓
Extract Markdown
  ↓
Classify
  ↓
Extract Expectations
  ↓
Chunk Markdown
  ↓
Persist DocumentChunk[]
```

Chunking is connected to `process_document()`, not to the low-level document creation/upload persistence method.

## Reprocessing behavior

The new chunks are generated first. Existing chunks are deleted only after chunk generation succeeds. Persistence is then performed in one database transaction.

If extraction/chunking fails before persistence, the existing chunks are left untouched.

## Deliberate exclusions

M3.6.2 does **not** include:

- public chunk APIs
- embeddings
- vector persistence
- semantic retrieval
- retrieval APIs

Those remain subsequent M3.6 steps.

## Copy locations

AI repo changes are under `myimpact-ai/`.

The Flyway migration from M3.6.1 remains the required database change and is included under `migrations/` for convenience.
