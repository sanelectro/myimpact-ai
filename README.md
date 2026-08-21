# MyImpact AI

> AI-powered engineering impact and performance intelligence platform.

MyImpact AI is designed to help engineers capture, understand, and present their professional impact by combining:

- Employee goals and expectations
- Role & responsibilities
- 1:1 discussions
- Jira work
- GitHub contributions
- Confluence knowledge
- Personal evidence uploaded by employees
- Engineering outcomes and incidents
- AI-assisted evidence mapping
- Impact assessment
- Evidence-backed performance reports

The system is designed as an **AI-native, evidence-driven platform** rather than a generic chatbot.

---

# Project Vision

The core idea is:

```text
Employee Expectations
        +
Enterprise Work Evidence
        +
Personal Evidence
        |
        v
   Evidence Collection
        |
        v
   Evidence Intelligence
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

The goal is to help an employee answer:

> **"What have I actually achieved, what impact did it create, and how does it align with my goals and role expectations?"**

---

# Repository

This repository contains the AI/backend intelligence foundation of MyImpact.

The initial project is split into three repositories:

```text
myimpact-ai    → AI / LLM / RAG / Agents / MCP / Intelligence
myimpact-api   → Backend API / Domain / Database
myimpact-web   → Frontend
```

High-level dependency:

```text
myimpact-web
      |
      v
myimpact-api
      |
      v
myimpact-ai
```

---

# Current Status

## Overall

🚧 **Project under active development**

## Milestone Status

| Milestone | Area | Status |
|---|---|---|
| **M1** | AI Foundation & LLM Vertical Slice | ✅ Complete |
| **M2** | Domain & Evidence Foundation | 🔜 Next |
| **M3** | Document Ingestion & RAG | 📋 Planned |
| **M4** | MCP Evidence Integration | 📋 Planned |
| **M5** | Evidence Intelligence | 📋 Planned |
| **M6** | Goal Mapping & Impact Assessment | 📋 Planned |
| **M7** | Agentic AI & LangGraph | 📋 Planned |
| **M8** | Reports & 1:1 Intelligence | 📋 Planned |
| **M9** | Frontend MVP | 📋 Planned |
| **M10** | Guardrails, HITL & Security | 📋 Planned |
| **M11** | Observability & AI Evaluation | 📋 Planned |
| **M12** | Production Readiness | 📋 Planned |

---

# M1 — AI Foundation

**Status: ✅ Complete**

M1 establishes the first working AI vertical slice.

## M1 Deliverables

- [x] Python project foundation
- [x] FastAPI application
- [x] Pydantic Settings
- [x] `.env` / `.env.example`
- [x] `LLMProvider` enum
- [x] `LLMRequest`
- [x] `LLMResponse`
- [x] `ILLMService` abstraction
- [x] `GroqLLMService`
- [x] `AzureAIService`
- [x] `MockLLMService`
- [x] LLM Factory
- [x] `/health`
- [x] `/chat`
- [x] Swagger/OpenAPI
- [x] Ruff static analysis
- [x] Automatic Ruff fixes
- [x] Application import validation
- [x] Unit tests
- [x] Integration tests
- [x] Real Groq integration
- [x] Real `/chat` LLM response

## M1 Architecture

```text
                     HTTP
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
           Groq API  Azure     Unit Tests
                       AI
                 \      |      /
                  \     |     /
                   +----+----+
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

## M1 Validation

```bash
python scripts/validate.py
```

Validation includes:

```text
Python Syntax
      |
      v
Ruff Static Analysis
      |
      +--> Automatic Safe Fixes
      |
      v
Ruff Re-check
      |
      v
Application Import
      |
      v
Validation Passed
```

## M1 Unit Tests

```bash
python -m pytest tests/unit -v
```

Current checkpoint:

```text
8 passed
```

## M1 Integration Tests

```bash
python -m pytest tests/integration -v -m integration
```

Current Groq integration test:

```text
1 passed
```

## M1 Documentation

Detailed M1 documentation is available under:

```text
docs/
└── milestones/
    └── M1-README.md
```

---

# M2 — Domain & Evidence Foundation

**Status: 🔜 Next**

M2 starts building the actual MyImpact domain.

The objective is to move from:

```text
Generic LLM
```

to:

```text
MyImpact Domain Intelligence
```

## Initial Domain Model

```text
User
Goal
Evidence
EvidenceMapping
ImpactAssessment
Report
```

## Core Relationship

```text
User
 |
 +---- Goals
 |
 +---- Evidence
          |
          v
   Evidence Mapping
          |
          v
   Impact Assessment
          |
          v
        Report
```

## Personal Evidence

Employees must be able to continuously add their own evidence.

Examples:

- Project achievements
- Incident resolution
- Technical design
- Architecture decisions
- Mentoring
- Production improvements
- Automation
- Performance improvements
- Customer impact
- Certifications
- Awards
- Technical contributions

Because evidence can change over time:

```text
New Evidence
     |
     v
Evidence Mapping
     |
     v
Impact Assessment
     |
     v
Report Updated
```

Reports should therefore be treated as **dynamic artifacts**, not static documents.

---

# M3 — Document Ingestion & RAG

**Status: 📋 Planned**

Some enterprise information may not be available through MCP.

For example:

- Role & Responsibilities
- Annual Goals
- Manager 1:1 Check-ins
- Performance expectations
- Other Workday-related information

For the MVP, these will be provided as:

```text
PDF
DOCX
```

These documents will be ingested into the MyImpact knowledge layer.

## RAG Flow

```text
PDF / DOCX
    |
    v
Document Parser
    |
    v
Chunking
    |
    v
Embeddings
    |
    v
Vector Store
    |
    v
Retriever
    |
    v
Relevant Context
    |
    v
LLM
```

RAG will allow the system to answer questions such as:

> What are my current role expectations?

> What are my annual goals?

> What competencies am I expected to demonstrate?

---

# M4 — MCP Evidence Integration

**Status: 📋 Planned**

The POC has already validated the concept of connecting multiple MCPs.

Planned enterprise sources include:

```text
Jira
GitHub
Confluence
Workday
```

For the MVP, Workday may continue to use uploaded documents where an appropriate MCP is unavailable.

## Evidence Collection

```text
                 +------ Jira
                 |
                 +------ GitHub
                 |
Employee --------+------ Confluence
                 |
                 +------ Workday / Documents
                 |
                 +------ Personal Uploads
```

The AI system should not blindly copy all data.

Instead, it should retrieve evidence relevant to the employee and the requested analysis.

---

# M5 — Evidence Intelligence

**Status: 📋 Planned**

This milestone introduces intelligence around collected evidence.

The system should identify:

- What was done?
- Why was it done?
- What was the employee's contribution?
- What changed?
- What was the business/technical impact?
- What evidence supports the claim?
- Which goal or responsibility does it support?

Example:

```text
GitHub PR
   +
Jira Story
   +
Incident
   +
Confluence Design
   |
   v
Evidence Intelligence
   |
   v
"Implemented X which reduced Y
and improved Z."
```

The system should maintain links back to the original evidence.

---

# M6 — Goal Mapping & Impact Assessment

**Status: 📋 Planned**

Map evidence to:

```text
Role
 |
Goals
 |
Responsibilities
 |
Competencies
 |
Business Impact
```

Example:

```text
Jira Story
    |
    +---- Goal: Reliability
    |
    +---- Responsibility: Production Support
    |
    +---- Impact: Reduced incidents
```

Impact dimensions may include:

- Technical impact
- Business impact
- Customer impact
- Reliability
- Performance
- Cost optimization
- Automation
- Leadership
- Mentoring
- Innovation
- Operational excellence

---

# M7 — Agentic AI & LangGraph

**Status: 📋 Planned**

Agents will be introduced only after the domain and evidence foundation is stable.

Potential agents:

```text
                Orchestrator
                     |
        +------------+------------+
        |            |            |
        v            v            v
 Evidence Agent   Goal Agent   Impact Agent
        |            |            |
        +------------+------------+
                     |
                     v
                Report Agent
```

## Potential Responsibilities

### Evidence Agent

Find and validate evidence.

### Goal Agent

Understand goals, role expectations and responsibilities.

### Impact Agent

Assess the impact of evidence.

### Report Agent

Generate evidence-backed summaries and reports.

### Orchestrator

Coordinate the workflow.

LangGraph may be used when the workflow requires:

- Stateful execution
- Multiple agents
- Conditional routing
- Retry
- Human approval
- Long-running workflows

---

# M8 — Reports & 1:1 Intelligence

**Status: 📋 Planned**

Generate useful reports from accumulated evidence.

Examples:

```text
Monthly Impact Report
Quarterly Impact Report
Annual Performance Report
Goal Progress Report
Promotion Evidence Report
1:1 Preparation Report
```

Example:

```text
Goals
  +
Evidence
  +
Impact Assessment
  |
  v
Performance Report
```

Reports should be:

- Evidence-backed
- Traceable
- Explainable
- Editable
- Continuously updateable

---

# M9 — Frontend MVP

**Status: 📋 Planned**

Frontend repository:

```text
myimpact-web
```

Initial MVP screens:

```text
Dashboard
   |
   +--- Goals
   |
   +--- Evidence
   |
   +--- Impact
   |
   +--- Reports
   |
   +--- Upload Documents
   |
   +--- Ask MyImpact
```

The employee should be able to:

1. View goals
2. Upload evidence
3. Review automatically discovered evidence
4. Correct mappings
5. View impact
6. Generate/update reports
7. Ask questions about their career evidence

---

# M10 — Guardrails, HITL & Security

**Status: 📋 Planned**

AI-generated performance information must not be treated as unquestionable truth.

The system should support:

```text
AI Recommendation
       |
       v
Human Review
       |
       +---- Approve
       |
       +---- Modify
       |
       +---- Reject
```

Potential controls:

- Evidence validation
- Source attribution
- Prompt injection protection
- PII protection
- Authorization
- Data isolation
- Human approval
- Confidence scores
- Audit trail

---

# M11 — Observability & AI Evaluation

**Status: 📋 Planned**

The system should provide visibility into AI execution.

Potential areas:

```text
LLM
 |
 +---- Tracing
 |
 +---- Token Usage
 |
 +---- Latency
 |
 +---- Retrieval Quality
 |
 +---- Agent Execution
 |
 +---- Evaluation
```

Potential tooling:

- LangSmith
- OpenTelemetry
- RAG evaluation
- LLM evaluation datasets
- Prompt/version tracking
- Cost monitoring

The exact tooling will be finalized when the agent/RAG architecture is implemented.

---

# M12 — Production Readiness

**Status: 📋 Planned**

Production hardening includes:

- CI/CD
- Containerization
- Kubernetes deployment
- Secrets management
- Authentication/authorization
- Monitoring
- Logging
- Alerting
- Performance testing
- Security testing
- Rate limiting
- Resilience
- Backup/recovery
- Cost controls

---

# AI Technology Roadmap

| Technology | Planned Usage | Status |
|---|---|---|
| LLM | Core language reasoning | ✅ M1 |
| LLM Provider Abstraction | Provider independence | ✅ M1 |
| Groq | Current LLM provider | ✅ M1 |
| Azure AI | Enterprise provider option | ✅ M1 |
| Mock LLM | Testing | ✅ M1 |
| RAG | Enterprise/document knowledge | M3 |
| Vector DB | Semantic retrieval | M3 |
| Semantic Router | Route requests to appropriate capability | Later |
| MCP | Enterprise evidence access | M4 |
| Agents | Specialized reasoning | M7 |
| Multi-Agent | Coordinated analysis | M7 |
| LangChain | LLM/RAG abstractions where useful | Later |
| LangGraph | Stateful agent orchestration | M7 |
| Tracing | AI observability | M11 |
| RAG Evaluation | Retrieval quality | M11 |
| LLM Evaluation | Response quality | M11 |
| Guardrails | AI safety and correctness | M10 |
| Human-in-the-loop | Approval/correction | M10 |

---

# Data Architecture Direction

The platform is expected to use different storage technologies for different purposes.

## Relational Database

PostgreSQL will store structured MyImpact domain information:

```text
User
Goal
Evidence
EvidenceMapping
ImpactAssessment
Report
```

Why PostgreSQL?

- Strong relationships
- Transactions
- Referential integrity
- Structured querying
- Reporting
- Auditability

---

## Vector Database

A vector store will be introduced when RAG is implemented.

It will store embeddings for:

```text
Role documents
Goal documents
1:1 documents
Confluence content
Relevant evidence
Other knowledge documents
```

Purpose:

```text
Natural language query
        |
        v
Embedding
        |
        v
Vector Search
        |
        v
Relevant Context
```

PostgreSQL + pgvector may be considered to reduce infrastructure complexity if it satisfies the MVP scale and retrieval requirements.

The final decision will be made during M3.

---

## Cache

Caching can be introduced where repeated expensive operations occur.

Potential candidates:

```text
LLM responses
Embedding generation
MCP responses
Frequently accessed documents
Frequently used user context
```

Redis is a potential implementation.

Caching should not be introduced everywhere by default. It should be added where latency, cost, or repeated retrieval justifies it.

---

# High-Level Architecture

```text
                        +----------------+
                        | myimpact-web   |
                        |   Frontend     |
                        +-------+--------+
                                |
                                v
                        +----------------+
                        | myimpact-api   |
                        | Backend/API    |
                        +-------+--------+
                                |
                                v
                    +-------------------------+
                    |      myimpact-ai        |
                    |                         |
                    |  Router / Orchestrator  |
                    |          |              |
                    |    +-----+-----+        |
                    |    |           |        |
                    |   RAG        Agents     |
                    |    |           |        |
                    |    +-----+-----+        |
                    |          |              |
                    |         LLM             |
                    +----------+--------------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
           MCPs           Vector Store      PostgreSQL
              |
       +------+------+ 
       |      |      |
     Jira   GitHub Confluence

        +----------------------+
        | PDF / DOCX Documents |
        +----------------------+
```

---

# Core AI Flow

```text
User Question / Request
          |
          v
     Semantic Router
          |
          +-------------------+
          |                   |
          v                   v
      RAG Search           MCP Retrieval
          |                   |
          +---------+---------+
                    |
                    v
              Context Builder
                    |
                    v
                  Agent
                    |
                    v
                   LLM
                    |
                    v
             Evidence-backed
                 Response
```

---

# Development Principles

## 1. Evidence First

AI-generated conclusions should be backed by actual evidence whenever possible.

## 2. Traceability

The system should be able to answer:

> "Why did the AI reach this conclusion?"

## 3. Provider Independence

Application code should depend on interfaces rather than specific LLM providers.

```text
Application
    |
    v
ILLMService
    |
    +---- Groq
    +---- Azure
    +---- Mock
```

## 4. Incremental AI Adoption

Do not introduce agents, RAG, MCP, LangGraph and vector databases prematurely.

Each technology should solve a specific problem.

## 5. Human-in-the-loop

Employees should be able to correct:

- Evidence
- Goal mappings
- Impact assessments
- Generated reports

## 6. Continuous Evidence

Evidence can be added at any time.

Therefore:

```text
New Evidence
     |
     v
Re-evaluate Mapping
     |
     v
Re-evaluate Impact
     |
     v
Update Report
```

---

# Development Sequence

```text
M1
AI Foundation
    |
    v
M2
Domain + Evidence
    |
    v
M3
Documents + RAG
    |
    v
M4
MCP Integration
    |
    v
M5
Evidence Intelligence
    |
    v
M6
Goal + Impact Assessment
    |
    v
M7
Agents + LangGraph
    |
    v
M8
Reports
    |
    v
M9
Frontend MVP
    |
    v
M10
Guardrails + HITL
    |
    v
M11
Observability + Evaluation
    |
    v
M12
Production
```

---

# Current Focus

## 🔜 M2 — Domain & Evidence Foundation

The immediate objective is **not** to build more generic LLM features.

The next focus is to establish the MyImpact domain model and evidence lifecycle:

```text
Goal
 |
 +---- Evidence
          |
          v
   Evidence Mapping
          |
          v
   Impact Assessment
          |
          v
        Report
```

This creates the foundation required for RAG, MCP, agents and eventually the complete MyImpact experience.

---

# M1 Completion

M1 provides the first reliable MyImpact AI vertical slice:

```text
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

The foundation is now ready for the MyImpact-specific intelligence layer.

---

# License

This project is currently under development.
