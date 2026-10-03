# MyImpact AI — M1 README

## Milestone 1 — AI Application Foundation

### Objective

M1 establishes the initial application foundation for MyImpact AI: a structured FastAPI application, environment-based configuration, an LLM provider abstraction, Groq/Azure AI/Mock implementations, a provider factory, chat API, tests, and project validation.

The key design goal is to keep the application independent of any single LLM provider.

### Architecture

```text
Client
  ↓
FastAPI
  ↓
Chat Endpoint
  ↓
LLM Service Interface
  ↓
LLM Provider
  ├── Groq
  ├── Azure AI
  └── Mock
```

---

## M1 Components

### 1. Application Foundation

Established the FastAPI project structure with separate areas for API, configuration, services, models, tests, and validation.

### 2. Configuration Management

Configuration is managed through Pydantic Settings and environment variables.

Example:

```env
LLM_PROVIDER=mock
```

Provider credentials and environment-specific values belong in `.env`. Do not commit `.env` or real credentials. `.env.example` provides the configuration reference.

### 3. LLM Provider Abstraction

Introduced an `ILLMService` interface so the application can work with different providers through a common contract.

```text
ILLMService
     ↓
 ┌───────────────┬────────────────┬────────────────┐
 ↓               ↓                ↓
Groq          Azure AI          Mock
```

### 4. Groq LLM Service

Implemented `GroqLLMService` for real LLM interaction through Groq.

### 5. Azure AI Service

Implemented `AzureAIService` to establish the Azure-based provider path.

### 6. Mock LLM Service

Implemented `MockLLMService` for deterministic local/unit testing without external LLM calls.

### 7. LLM Factory

Implemented the LLM factory to select the provider based on application configuration.

```text
LLM_PROVIDER
     ↓
LLM Factory
     ↓
Groq / Azure AI / Mock
```

### 8. Chat API

Added the initial chat endpoint using the provider abstraction rather than directly coupling the API to a provider.

---

## Testing

### Unit Tests

Run:

```bash
python -m pytest tests/unit -v
```

Final baseline:

```text
8 passed
```

### Groq Integration Test

Run:

```bash
python -m pytest tests/integration -v -m integration
```

Verified result:

```text
1 passed, 1 deselected
tests/integration/llm/test_groq_integration.py::test_groq_llm_service PASSED
```

The integration test requires the relevant provider credentials/configuration.

---

## Validation

Project validation is available through:

```bash
python scripts/validate.py
```

The validation workflow includes:

```text
[1/4] Python Syntax
      ✓ All Python files compiled successfully

[2/4] Static Analysis
      ✓ static analysis passed

[3/4] Application Import
      ✓ application import passed
```

Ruff static analysis and configured auto-fix behavior were also added to the validation workflow.

---

## Dependencies

The project maintains dependencies in:

```text
requirements.txt
```

The M1 dependency baseline includes the FastAPI/Pydantic stack, LLM provider dependencies, pytest, Ruff, and required supporting packages.

`email-validator` was added because Pydantic `EmailStr` requires it.

---

## Important M1 Fixes

The following issues were identified and resolved during M1:

- Added the missing `LLMProvider` enum and required import.
- Added the missing `ChatRequest` model.
- Corrected the `MockLLMService` interface import.
- Added `email-validator` for Pydantic `EmailStr`.
- Added Ruff/static analysis to the validation workflow.
- Added validation/build checks for Python syntax and application imports.

---

## Important Files

Key M1 areas include:

```text
app/
├── config/
│   └── settings.py
├── api/
├── services/
├── models/
└── ...

tests/
├── unit/
└── integration/

scripts/
└── validate.py

.env
.env.example
requirements.txt
```

Provider implementations include:

```text
GroqLLMService
AzureAIService
MockLLMService
```

The LLM interface and factory provide the common provider abstraction and selection mechanism.

---

## M1 Completion Checklist

- [x] FastAPI application foundation
- [x] Environment-based configuration
- [x] `.env.example`
- [x] LLM provider abstraction
- [x] Groq LLM service
- [x] Azure AI service
- [x] Mock LLM service
- [x] LLM factory
- [x] Chat endpoint
- [x] Unit tests
- [x] Groq integration test
- [x] Ruff/static analysis
- [x] Application import validation
- [x] Validation script
- [x] Dependency baseline

---

## M1 Result

M1 establishes:

```text
FastAPI
   ↓
Configuration
   ↓
LLM Abstraction
   ↓
Provider Factory
   ↓
Groq / Azure AI / Mock
```

The application is ready for persistence and data-layer development.

### M1 Boundary

M1 does not yet implement:

- PostgreSQL persistence
- SQLAlchemy persistence models
- Alembic migrations
- Repository layer
- Evidence version persistence
- Impact history persistence

These are introduced in M2.

---

## Next Milestone

### M2 — Persistence & Data Layer

M2 adds:

```text
Application
    ↓
Services
    ↓
Repositories
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

M2 introduces persistence concepts for:

```text
User
Goal
Evidence
EvidenceVersion
EvidenceMapping
ImpactAssessment
Report
```

**Milestone status: M1 Complete — application foundation established and ready for M2.**
