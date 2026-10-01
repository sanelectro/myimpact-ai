# MyImpact — M3 Document Intelligence
## Copilot Implementation Specification

**Milestone:** M3 — Document Intelligence  
**Status:** In Progress  
**Purpose:** Give GitHub Copilot a complete, ordered implementation plan for M3 so development can be automated in small, verifiable steps.

---

# 1. Context

MyImpact is an AI-powered engineering career / 1:1 assistant.

The previous milestones are already complete:

- **M1 — Foundation & LLM Abstraction**
- **M2 — Persistence & Data Layer**

M3 introduces the document intelligence capability that allows MyImpact to ingest documents and turn them into structured, searchable information that later milestones can use for AI reasoning.

M3 is intentionally focused on the **document lifecycle and document intelligence foundation**. Do not implement later career-analysis or 1:1-generation capabilities as part of M3 unless required as a dependency.

---

# 2. M3 Goal

Build a production-ready document intelligence pipeline:

```text
Document Upload
      ↓
Document Persistence
      ↓
File Storage
      ↓
Text / Content Extraction
      ↓
Document Classification
      ↓
Structured Expectation Extraction
      ↓
Metadata & Search
      ↓
Validated API + Tests
```

The system must be designed so that later milestones can consume the structured document information without needing to understand PDF/DOCX parsing details.

---

# 3. M3 Scope

M3 consists of seven implementation areas:

```text
M3.1  Document Domain & Persistence
M3.2  PDF/DOCX Upload
M3.3  Text Extraction
M3.4  Document Classification
M3.5  Structured Expectation Extraction
M3.6  Metadata / Search APIs
M3.7  Tests & Validation
```

---

# 4. Current Progress

The following M3 work has already been covered:

- Document foundation
- M3 scope definition
- Document storage / upload foundation
- Docling integration

Do not recreate these from scratch if the existing code already implements them.

Before making changes:

1. Inspect the existing repository.
2. Identify the current M3 implementation.
3. Reuse existing models, services, configuration and abstractions.
4. Extend rather than duplicate.
5. Keep M1 and M2 behaviour backward compatible.

---

# 5. Existing Architecture Principles

Preserve the architectural style established in M1 and M2.

The document subsystem should follow separation of concerns:

```text
API
 ↓
Application / Service
 ↓
Domain
 ↓
Infrastructure
 ↓
Persistence / File Storage / External Libraries
```

Do not place:

- Docling calls directly in API endpoints.
- Database queries directly in controllers/routes.
- Classification prompts directly in persistence code.
- File parsing logic directly in domain models.

External libraries must be isolated behind application-facing interfaces where practical.

---

# 6. M3.1 — Document Domain & Persistence

## Objective

Create the domain representation and persistence model for documents.

## Required capabilities

A document should have enough information to answer:

- What document is this?
- Who owns it?
- What type of document is it?
- Where is the source file?
- What is its processing status?
- When was it uploaded?
- When was it processed?
- What extraction/classification state does it have?
- What structured information was extracted?

## Suggested lifecycle

```text
UPLOADED
   ↓
PROCESSING
   ↓
EXTRACTED
   ↓
CLASSIFIED
   ↓
STRUCTURED
   ↓
COMPLETED
```

Failure must be representable without destroying the document record.

Example:

```text
PROCESSING
   ↓
FAILED
```

## Domain model

Use the existing project's naming conventions.

The model should conceptually contain:

```text
Document
 ├── Id
 ├── Owner / User reference
 ├── FileName
 ├── ContentType
 ├── FileSize
 ├── StorageReference
 ├── DocumentType
 ├── ProcessingStatus
 ├── ProcessingError
 ├── UploadedAt
 ├── ProcessedAt
 ├── ExtractedTextReference / ExtractedContent
 └── Classification / structured metadata references
```

Do not add fields that are not required by the current M3 flow.

## Persistence

Create the required:

- Entity/model mapping
- Migration
- Repository
- Repository implementation
- Service methods

Follow the repository and service conventions already established in M2.

## Acceptance criteria

- Document can be persisted.
- Document status can be updated.
- Failed processing can be represented.
- Document ownership is preserved.
- Existing M2 tests continue to pass.
- Migration runs successfully against PostgreSQL.

---

# 7. M3.2 — PDF/DOCX Upload

## Objective

Provide an API for uploading supported documents.

Initially support:

- PDF
- DOCX

Reject unsupported content types.

## Upload flow

```text
HTTP Request
     ↓
Validate request
     ↓
Validate file type
     ↓
Validate file size
     ↓
Create Document record
     ↓
Store source file
     ↓
Return Document ID
```

The upload API should not contain document parsing logic.

## API concept

Example:

```http
POST /documents
Content-Type: multipart/form-data
```

Request:

```text
file=<PDF or DOCX>
```

Response should contain the document identifier and processing state.

Example conceptual response:

```json
{
  "id": "document-id",
  "fileName": "performance-review.pdf",
  "contentType": "application/pdf",
  "status": "UPLOADED"
}
```

Use the project's existing response conventions rather than blindly copying this shape.

## Validation

At minimum:

- Empty file → reject
- Unsupported extension/content type → reject
- Oversized file → reject
- Invalid request → appropriate 4xx response

Do not trust the filename extension alone where content validation is available.

## Storage

Keep the physical file separate from the database record.

Conceptually:

```text
PostgreSQL
    |
    └── document metadata

File Storage
    |
    └── original PDF/DOCX
```

The database stores the storage reference rather than requiring the binary document to be embedded in the relational record.

---

# 8. M3.3 — Text / Content Extraction

## Objective

Extract usable content from uploaded PDF/DOCX documents.

The existing M3 work includes **Docling integration**.

Do not introduce a second parsing framework if Docling already satisfies the requirement.

## Architecture

Use an abstraction such as:

```text
IDocumentExtractor
       |
       +---- DoclingDocumentExtractor
```

The application layer should depend on the abstraction.

## Flow

```text
Document ID
    ↓
Load document metadata
    ↓
Locate source file
    ↓
Determine content type
    ↓
Document Extractor
    ↓
Normalized extracted content
    ↓
Persist extraction result
    ↓
Update processing status
```

## Normalized output

The extractor should provide a consistent internal representation regardless of source format.

Conceptually:

```text
ExtractedDocument
 ├── PlainText
 ├── Sections
 ├── Tables (if supported)
 ├── Headings
 ├── Pages / source locations
 └── Extraction metadata
```

Do not throw away source-location information if the extractor can provide it. Later AI features will need evidence and citations.

## Important design principle

The raw source document and extracted representation are different artifacts:

```text
Original Document
       ↓
Extraction
       ↓
Normalized Content
```

Keep enough information to reproduce or inspect the extraction.

## Acceptance criteria

- PDF extraction works.
- DOCX extraction works.
- Extracted content can be persisted/retrieved.
- Extraction failure updates document status.
- Extraction errors are captured without leaking internal stack traces through the API.
- Existing functionality remains backward compatible.

---

# 9. M3.4 — Document Classification

## Objective

Determine what kind of document has been uploaded.

Classification should be implemented as an application capability, not mixed into the extraction layer.

## Conceptual flow

```text
Extracted Content
       ↓
Classification Service
       ↓
Document Type
       +
Confidence
       +
Reason / Evidence
```

Potential document categories should be driven by MyImpact requirements and configuration rather than hard-coded throughout the application.

Examples may include:

- Performance / review document
- Goal document
- Career / development document
- Architecture / technical document
- Project document
- Other / Unknown

Do not assume every uploaded document must fit a known category.

Use:

```text
UNKNOWN
```

when confidence is insufficient.

## AI integration

Use the existing M1 LLM abstraction.

Do not call a specific provider directly from the classification service.

Conceptually:

```text
DocumentClassificationService
          ↓
       LLM abstraction
          ↓
   Configured provider
```

## Structured classification output

Prefer structured output such as:

```json
{
  "documentType": "GOAL_DOCUMENT",
  "confidence": 0.91,
  "reason": "Document contains annual objectives and measurable key results."
}
```

The exact schema should follow the existing project conventions.

## Guardrails

The classifier must:

- Return only supported categories.
- Handle unknown documents.
- Validate structured model output.
- Avoid treating low-confidence classification as fact.
- Preserve the original document even when classification fails.

---

# 10. M3.5 — Structured Expectation Extraction

## Objective

Extract structured information from documents that is useful to MyImpact.

This is the first step from:

```text
Unstructured document
```

to:

```text
MyImpact knowledge
```

## Example

A document may contain:

> Lead architecture initiatives and improve platform reliability.

The system should extract structured information conceptually such as:

```text
Expectation
 ├── Category: Technical Leadership
 ├── Description: Lead architecture initiatives
 ├── Evidence expected: Architecture/design work
 └── Source location: document/page/section
```

## Extraction flow

```text
Document
   ↓
Extracted Content
   ↓
Document Classification
   ↓
Expectation Extraction
   ↓
Structured Expectations
   ↓
Persist
```

## Important distinction

Do not claim that an expectation was achieved.

M3 extracts:

```text
WHAT IS EXPECTED
```

Later milestones determine:

```text
WHAT WAS ACTUALLY DONE
```

This separation is essential.

## Suggested conceptual structure

```text
Expectation
 ├── Id
 ├── DocumentId
 ├── Category
 ├── Description
 ├── EvidenceHints
 ├── SourceReference
 ├── Confidence
 └── CreatedAt
```

Possible categories:

- Delivery
- Technical Leadership
- Architecture
- Mentoring
- Innovation
- Collaboration
- Operational Excellence
- Business / Domain Impact

Keep the category set configurable/extensible where practical.

## Evidence references

Every extracted expectation should retain its source.

Conceptually:

```text
Expectation
    ↓
Document
    ↓
Page / Section / Text Span
```

This allows future MyImpact responses to say:

> "This expectation comes from your annual goals document."

rather than producing unsupported claims.

---

# 11. M3.6 — Metadata & Search APIs

## Objective

Expose document information to the rest of MyImpact.

The APIs should support:

- List documents
- Get document metadata
- Get document status
- Get extracted content / structured information where appropriate
- Search/filter documents
- Retrieve extracted expectations

## Example API surface

Use the project's existing naming/versioning conventions.

Conceptually:

```http
POST   /documents
GET    /documents
GET    /documents/{id}
GET    /documents/{id}/status
GET    /documents/{id}/content
GET    /documents/{id}/expectations
```

Potential search:

```http
GET /documents?type=GOAL_DOCUMENT&status=COMPLETED
```

Do not expose internal storage paths.

## Search design

M3 search is primarily metadata / document retrieval.

Do not prematurely implement a full semantic/vector search platform unless it is already part of the existing M3 implementation.

Semantic RAG retrieval can be introduced in the appropriate later milestone.

---

# 12. M3.7 — Tests & Validation

## Objective

Make M3 production-quality and ensure M1/M2 remain stable.

## Unit tests

Test:

### Domain

- Document creation
- Status transitions
- Invalid transitions if state rules exist

### Upload

- Valid PDF
- Valid DOCX
- Empty file
- Unsupported type
- Oversized file

### Extraction

- Successful PDF extraction
- Successful DOCX extraction
- Extraction failure
- Empty extracted content

### Classification

- Known document type
- Unknown document
- Low confidence
- Invalid LLM response
- LLM/provider failure

### Expectation extraction

- Valid structured response
- Missing fields
- Invalid category
- Low confidence
- LLM failure
- Source reference preservation

### Repository

- Create
- Get
- Update status
- Search/filter

---

# 13. Integration Tests

Validate:

```text
Upload
  ↓
Persist
  ↓
Extract
  ↓
Classify
  ↓
Extract Expectations
  ↓
Persist
  ↓
Retrieve
```

Use the project's existing test infrastructure.

Do not make integration tests dependent on a live external LLM unless the existing test strategy explicitly requires it.

Prefer deterministic mocks/fakes for CI.

---

# 14. End-to-End M3 Scenario

The primary demonstration scenario should be:

```text
1. User uploads a PDF/DOCX.
              ↓
2. MyImpact creates a Document record.
              ↓
3. File is stored.
              ↓
4. Docling extracts content.
              ↓
5. Document is classified.
              ↓
6. Structured expectations are extracted.
              ↓
7. Results are persisted.
              ↓
8. User can inspect document metadata.
              ↓
9. User can retrieve extracted expectations.
```

Example:

```text
Input:
Annual Goals.pdf

↓

Classification:
GOAL_DOCUMENT
Confidence: 94%

↓

Extracted Expectations:

1. Technical Leadership
   "Lead architecture initiatives"

2. Delivery
   "Improve sprint predictability"

3. Innovation
   "Drive adoption of engineering automation"
```

The system must preserve the evidence/source reference for each extracted item.

---

# 15. Error Handling

Every stage must fail independently where possible.

```text
Upload Failure
      ↓
Document remains absent / request fails

Extraction Failure
      ↓
Document = FAILED
      ↓
Error recorded

Classification Failure
      ↓
Extraction remains available
      ↓
Classification = FAILED / UNKNOWN

Expectation Extraction Failure
      ↓
Classification remains available
      ↓
Expectation extraction = FAILED
```

Do not delete the original document because a downstream AI step failed.

---

# 16. Observability

M3 should provide enough information to understand processing failures.

At minimum log:

- Document ID
- Processing stage
- Processing start/end
- Success/failure
- Error category
- Duration

Never log:

- Full document contents
- Sensitive personal information
- Full LLM prompts/responses unless explicitly allowed by the project's security design

Use structured logging consistent with the existing project.

---

# 17. Security Requirements

Documents may contain sensitive employee information.

Therefore:

- Enforce document ownership/authorization.
- Never expose another user's document through an ID alone.
- Do not expose physical storage paths.
- Validate uploads.
- Do not log raw document content.
- Do not expose raw LLM/provider errors.
- Apply authorization before document retrieval.
- Keep source evidence scoped to the authorized user.

The AI should process only the context the user is permitted to access.

---

# 18. LLM Abstraction Requirement

M1 already introduced provider-independent LLM abstraction.

M3 must use it.

Do NOT write:

```text
ClassificationService
    ↓
Groq SDK
```

or:

```text
ExpectationService
    ↓
Azure SDK
```

Instead:

```text
ClassificationService
       ↓
    ILLM / existing abstraction
       ↓
Configured Provider
```

This keeps M3 compatible with the provider architecture established in M1.

---

# 19. Docling Integration Requirement

Docling is already part of the M3 implementation.

Before adding extraction code:

1. Inspect the existing Docling integration.
2. Identify its interface.
3. Reuse the existing implementation.
4. Add missing capabilities around it.
5. Add tests around the integration boundary.

Do not create a parallel extraction implementation.

---

# 20. Recommended Implementation Order for Copilot

Copilot should implement M3 in this exact sequence unless the repository already contains the relevant piece.

```text
STEP 0
Inspect repository and existing M1/M2/M3 code.

STEP 1
Complete/verify Document domain model.

STEP 2
Complete/verify database migration and repository.

STEP 3
Complete/verify file storage abstraction.

STEP 4
Complete/verify PDF/DOCX upload API.

STEP 5
Complete/verify Docling extraction adapter.

STEP 6
Persist normalized extracted content.

STEP 7
Implement document classification service.

STEP 8
Integrate classification with existing LLM abstraction.

STEP 9
Implement structured expectation extraction.

STEP 10
Persist expectations + source references.

STEP 11
Implement document metadata/status APIs.

STEP 12
Implement expectation retrieval APIs.

STEP 13
Add unit tests.

STEP 14
Add integration tests.

STEP 15
Run full test suite.

STEP 16
Run lint/format/static analysis.

STEP 17
Run build.

STEP 18
Validate OpenAPI/Swagger.

STEP 19
Run PostgreSQL migration validation.

STEP 20
Perform end-to-end M3 verification.
```

---

# 21. Definition of Done

M3 is complete only when all of the following are true:

## Domain

- [ ] Document model implemented
- [ ] Document lifecycle/status implemented
- [ ] Expectations model implemented
- [ ] Source references implemented

## Persistence

- [ ] Database migration exists
- [ ] Repository implemented
- [ ] CRUD/status operations tested
- [ ] PostgreSQL validation completed

## Upload

- [ ] PDF supported
- [ ] DOCX supported
- [ ] File validation implemented
- [ ] File storage implemented
- [ ] Authorization implemented

## Extraction

- [ ] Existing Docling integration reused
- [ ] PDF extraction verified
- [ ] DOCX extraction verified
- [ ] Normalized content persisted
- [ ] Extraction errors handled

## AI

- [ ] Document classification implemented
- [ ] Existing LLM abstraction reused
- [ ] Structured output validated
- [ ] Unknown/low-confidence classification handled
- [ ] Expectation extraction implemented
- [ ] Source evidence preserved

## APIs

- [ ] Upload API
- [ ] List API
- [ ] Get metadata API
- [ ] Status API
- [ ] Content API where required
- [ ] Expectations API
- [ ] Search/filter support

## Quality

- [ ] Unit tests
- [ ] Integration tests
- [ ] Full regression suite
- [ ] Lint/static analysis
- [ ] Build passes
- [ ] Swagger/OpenAPI validated
- [ ] PostgreSQL validation completed
- [ ] No sensitive document content in logs

---

# 22. Copilot Working Rules

When using GitHub Copilot to implement this milestone, give Copilot this context:

1. **Inspect before changing.**
2. Do not recreate functionality that already exists.
3. Preserve M1 and M2 behaviour.
4. Follow existing project naming and folder conventions.
5. Follow existing dependency injection patterns.
6. Follow existing repository/service/API patterns.
7. Use the existing LLM abstraction.
8. Reuse the existing Docling integration.
9. Keep domain, application and infrastructure concerns separated.
10. Add tests with every significant implementation step.
11. Do not introduce unnecessary frameworks.
12. Do not implement future milestones prematurely.
13. Do not replace working code merely for stylistic reasons.
14. Keep changes small and reviewable.
15. After each step, run the relevant tests before proceeding.
16. Never silently invent business rules not defined in this specification.
17. Where a required business rule is genuinely missing, mark it as a TODO rather than guessing.

---

# 23. Suggested Copilot Prompt

Use the following prompt as the starting instruction for Copilot:

> You are implementing **MyImpact M3 — Document Intelligence**.
>
> Read `MYIMPACT_M3_DOCUMENT_INTELLIGENCE.md` completely before changing code.
>
> First inspect the repository and identify what has already been implemented for M1, M2 and M3.
>
> Do not recreate existing functionality.
>
> Determine the current M3 completion point and continue from there.
>
> Implement M3 incrementally in the order defined by the specification:
>
> 1. Document domain and persistence
> 2. PDF/DOCX upload
> 3. Text/content extraction using the existing Docling integration
> 4. Document classification using the existing LLM abstraction
> 5. Structured expectation extraction
> 6. Metadata/search/retrieval APIs
> 7. Tests and validation
>
> For each step:
>
> - Inspect existing code first.
> - Make the smallest coherent change.
> - Follow existing project architecture and conventions.
> - Add/update tests.
> - Run relevant tests.
> - Fix failures before moving to the next step.
> - Do not implement future milestones.
>
> Important architectural constraints:
>
> - API must not contain business logic.
> - Domain must not depend on infrastructure.
> - Document parsing must be isolated behind an abstraction.
> - Use the existing Docling integration.
> - Use the existing provider-independent LLM abstraction.
> - Preserve document ownership and authorization.
> - Preserve source references for extracted information.
> - Never treat extracted expectations as evidence that the employee actually achieved them.
> - Do not expose sensitive document contents through logs or errors.
>
> At the beginning, report:
>
> - Current M3 implementation status
> - Files/modules already implementing M3
> - Missing M3 components
> - The first implementation step you will take
>
> Then implement only that first step and validate it before continuing.

---

# 24. M3 → Next Milestone Boundary

M3 ends with:

```text
Documents
   ↓
Extracted Content
   ↓
Classification
   ↓
Structured Expectations
   ↓
Searchable / Retrievable Data
```

M3 does **not** yet determine:

```text
What the engineer actually did
```

That will be handled by later MyImpact capabilities using evidence from engineering systems.

The conceptual boundary is:

```text
M3

WHAT IS EXPECTED?
        ↓
Document Intelligence


Later MyImpact

WHAT ACTUALLY HAPPENED?
        ↓
Evidence Intelligence


Later

WHAT WAS THE IMPACT?
        ↓
Impact Analysis


Later

HOW DO I PREPARE FOR MY 1:1?
        ↓
1:1 Intelligence
```

This separation should be preserved throughout development.
