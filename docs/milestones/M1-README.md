# M1 --- AI Foundation

## Objective

Establish the MyImpact AI service with a provider-independent LLM
architecture, FastAPI API, automated validation, unit testing, and real
Groq integration.

M1 focuses on building a reliable AI foundation before introducing RAG,
MCP, agents, LangGraph, semantic routing, and the MyImpact domain
intelligence.

------------------------------------------------------------------------

## M1 Completed

-   [x] Python project foundation
-   [x] Pydantic Settings configuration
-   [x] `.env` / `.env.example` configuration
-   [x] `LLMProvider` enum
-   [x] `LLMRequest` / `LLMResponse`
-   [x] `ILLMService` interface
-   [x] `GroqLLMService`
-   [x] `AzureAIService`
-   [x] `MockLLMService`
-   [x] LLM Factory
-   [x] FastAPI `/health`
-   [x] FastAPI `/chat`
-   [x] Swagger/OpenAPI
-   [x] Ruff static analysis
-   [x] Automatic Ruff fixes
-   [x] Application import validation
-   [x] Unit tests
-   [x] Groq integration test
-   [x] Real Groq `/chat` execution

------------------------------------------------------------------------

## Architecture

``` text
                    HTTP Request
                         |
                         v
                  +-------------+
                  | ChatRequest |
                  +-------------+
                         |
                         v
                  +-------------+
                  | LLMRequest  |
                  +-------------+
                         |
                         v
                  +--------------+
                  | LLM Factory  |
                  +--------------+
                         |
                         v
                  +--------------+
                  | ILLMService  |
                  +--------------+
                    /     |      \
                   /      |       \
                  v       v        v
              Groq     Azure     Mock
             Service   Service   Service
                |        |         |
                v        v         v
              Groq     Azure      Unit
               API     OpenAI     Tests
                \        |         /
                 \       |        /
                  +------+-------+
                         |
                         v
                  +--------------+
                  | LLMResponse  |
                  +--------------+
                         |
                         v
                  +--------------+
                  | ChatResponse |
                  +--------------+
```

------------------------------------------------------------------------

## LLM Provider Abstraction

Application code should communicate through:

``` text
ILLMService
```

and should not directly depend on a specific LLM provider.

### Providers

  Provider         Purpose
  ---------------- ------------------------------
  GroqLLMService   Current working LLM provider
  AzureAIService   Azure OpenAI provider
  MockLLMService   Deterministic unit testing

Provider selection is controlled through:

``` env
LLM_PROVIDER=groq
```

------------------------------------------------------------------------

## Repository Structure

``` text
myimpact-ai/
├── app/
│   ├── main.py
│   ├── api/
│   ├── config/
│   │   └── settings.py
│   ├── models/
│   │   ├── chat.py
│   │   └── llm.py
│   ├── services/
│   │   └── llm/
│   │       ├── interface.py
│   │       ├── factory.py
│   │       ├── groq_service.py
│   │       ├── azure_service.py
│   │       └── mock_service.py
│   ├── agents/
│   ├── graph/
│   ├── rag/
│   ├── routing/
│   ├── context/
│   ├── guardrails/
│   └── mcp/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│   └── validate.py
│
├── .env.example
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

# Running Locally

## 1. Activate the virtual environment

``` bash
source .venv/bin/activate
```

Windows:

``` powershell
.venv\Scripts\activate
```

## 2. Configure environment

Copy:

``` bash
cp .env.example .env
```

Configure the required values:

``` env
LLM_PROVIDER=groq

GROQ_API_KEY=<your-key>
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=<configured-model>
```

Never commit `.env`.

------------------------------------------------------------------------

# Run the Application

``` bash
uvicorn app.main:app --reload --port 8000
```

Swagger:

``` text
http://localhost:8000/docs
```

Health:

``` text
http://localhost:8000/health
```

------------------------------------------------------------------------

# Test `/chat`

Example request:

``` json
{
  "message": "Explain MyImpact in one sentence."
}
```

Expected response structure:

``` json
{
  "response": "...",
  "model": "openai/gpt-oss-20b"
}
```

------------------------------------------------------------------------

# Validation

Run:

``` bash
python scripts/validate.py
```

The validation pipeline performs:

``` text
Python Syntax
      |
      v
Ruff Static Analysis
      |
      +--> Auto-fix safe issues
      |
      v
Ruff Re-check
      |
      v
Application Import
      |
      v
BUILD VALIDATION
```

Expected result:

``` text
Python syntax              PASS
Static analysis            PASS
Application import         PASS
Build validation           PASS
```

------------------------------------------------------------------------

# Testing

## Unit Tests

Unit tests must not call external services.

``` bash
python -m pytest tests/unit -v
```

Current M1 checkpoint:

``` text
8 passed
```

------------------------------------------------------------------------

## API Integration Tests

``` bash
python -m pytest tests/integration/api -v
```

These validate the FastAPI boundary.

------------------------------------------------------------------------

## Groq Integration Tests

Groq integration tests intentionally call the external Groq API.

``` bash
python -m pytest tests/integration -v -m integration
```

The test uses the application's configuration through `get_settings()`.

------------------------------------------------------------------------

## Run All Tests

``` bash
python -m pytest -v
```

This is the complete test command.

------------------------------------------------------------------------

# Test Strategy

``` text
                    Tests
                      |
          +-----------+-----------+
          |                       |
       Unit                   Integration
          |                       |
          v                       v
   No external calls       External services
          |                       |
          v                       v
   Fast / deterministic       Real Groq API
```

### Unit Tests

Test:

-   Settings
-   LLM provider selection
-   LLM Factory
-   ILLMService contract
-   MockLLMService

### Integration Tests

Test:

-   FastAPI application
-   `/health`
-   GroqLLMService
-   Real Groq connectivity

------------------------------------------------------------------------

# M1 Verification Status

  Area                    Status
  ----------------------- --------
  Repository foundation   ✅
  Configuration           ✅
  LLM abstraction         ✅
  Groq provider           ✅
  Azure provider          ✅
  Mock provider           ✅
  LLM Factory             ✅
  FastAPI                 ✅
  `/health`               ✅
  `/chat`                 ✅
  Ruff validation         ✅
  Application import      ✅
  Unit tests              ✅
  Groq integration        ✅
  Real LLM response       ✅

------------------------------------------------------------------------

# What M1 Does NOT Include

The following are intentionally deferred to later milestones:

-   Jira MCP
-   GitHub MCP
-   Confluence MCP
-   Workday MCP
-   RAG
-   PostgreSQL domain schema
-   pgvector
-   Semantic Router
-   LangChain orchestration
-   LangGraph
-   Evidence Agent
-   Goal Agent
-   Impact Agent
-   Report Agent
-   Multi-Agent workflow
-   Guardrails
-   Human-in-the-loop approval
-   Redis caching
-   AI tracing
-   AI evaluation
-   Complete frontend workflow

Workday-related information such as:

-   Goals
-   Role & Responsibilities
-   Annual Goals
-   1:1 Check-ins

will initially be provided as PDF/DOCX documents for the MVP.

Employees will also be able to upload their own personal evidence.

------------------------------------------------------------------------

# M1 Exit Criteria

M1 is considered complete when:

-   [x] Application starts successfully
-   [x] `/health` works
-   [x] Swagger is available
-   [x] Configuration loads from `.env`
-   [x] LLM provider abstraction is established
-   [x] Groq connectivity works
-   [x] Azure provider boundary exists
-   [x] Mock provider supports unit tests
-   [x] Ruff validation passes
-   [x] Application import passes
-   [x] Unit tests pass
-   [x] Groq integration test passes
-   [x] `/chat` returns a real LLM response

------------------------------------------------------------------------

# Next Milestone

M1 establishes the AI infrastructure.

The next milestone moves into the actual MyImpact problem:

``` text
Employee Expectations
        +
Enterprise Evidence
        +
Personal Evidence
        |
        v
   Evidence Model
        |
        v
   Goal Mapping
        |
        v
 Impact Assessment
        |
        v
 Evidence-backed Report
```

The initial domain models will be:

``` text
Goal
Evidence
EvidenceMapping
ImpactAssessment
Report
```

The next milestone should focus on the **domain and evidence
foundation**, rather than adding generic chatbot functionality.

------------------------------------------------------------------------

# M1 Completion

M1 provides the first reliable MyImpact AI vertical slice:

``` text
FastAPI
   |
   v
LLM Abstraction
   |
   v
Groq
   |
   v
Real LLM Response
```

The foundation is now ready for the MyImpact-specific intelligence
layer.
