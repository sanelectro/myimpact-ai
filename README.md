# MyImpact AI

AI engineering and orchestration layer for **MyImpact — AI Performance Intelligence Platform**.

## MVP goal

Prove this scenario:

> Given an employee's goals/expectations and work evidence, generate an evidence-backed Weekly Impact report.

For the initial development cycle, Jira, GitHub and Confluence MCPs are mocked. The already-validated real MCP connections can be plugged in later.

## Architecture
```text
User Request
     |
Semantic Router
     |
LangGraph
     |
     +--> Context Builder
     +--> Evidence Agent
     |      +--> Mock Jira MCP
     |      +--> Mock GitHub MCP
     |      +--> Mock Confluence MCP
     +--> RAG / Goal Context
     +--> Impact Agent
     +--> Validation Agent
     +--> Report Agent
     |
Evidence-backed Weekly Impact
```

## Structure
```text
myimpact-ai/
├── agents/
│   ├── evidence_agent/
│   ├── impact_agent/
│   ├── validation_agent/
│   └── report_agent/
├── graph/
├── rag/
├── routing/
├── context/
├── guardrails/
├── mcp/
│   ├── jira/
│   ├── github/
│   └── confluence/
├── mock-data/
├── prompts/
├── models/
├── evaluation/
├── tests/
├── config/
└── requirements.txt
```

## AI concepts
| Topic | MyImpact use |
|---|---|
| LLM / GenAI | Extraction, reasoning, report generation |
| RAG | Goals, role, 1:1 and document retrieval |
| Context Engineering | Task-specific employee context |
| Semantic Routing | Workflow selection |
| Agents | Evidence, impact, validation, report |
| Multi-Agent AI | Specialized agent collaboration |
| Agentic AI | Multi-step tool-using analysis |
| LangChain | LLM, tools, retrievers, structured output |
| LangGraph | Stateful orchestration |
| MCP | Jira, GitHub, Confluence |
| Guardrails | Evidence-backed claims and privacy |
| Human-in-the-loop | Employee confirmation |
| pgvector | Semantic retrieval |
| Tracing | LangSmith or Azure AI Foundry |
| Evaluation | Ground-truth quality measurement |
| Redis | Later caching |

## Mock MCP strategy
Keep the AI dependent on stable tool contracts:

```text
Evidence Agent
      |
 MCP Interface
   /       \
 Mock     Real
```

Development:
```text
MCP_MODE=MOCK
```

Later switch to real authenticated MCP without changing the core AI workflow.

## Ground-truth data
Create synthetic employees and known relationships. Example:

```text
Goal: Improve platform reliability

Jira: JIRA-101 Implement retry mechanism
GitHub: PR-201 Add retry mechanism
Confluence: HLD-01 Retry Architecture
```

These should represent one contribution so deduplication can be tested.

Also test:
- Strong goal evidence
- Missing evidence
- Personal evidence
- Duplicate evidence
- Conflicting evidence
- "Insufficient evidence" behavior

## RAG
```text
PDF/DOCX
  -> extraction
  -> chunks
  -> embeddings
  -> PostgreSQL + pgvector
  -> metadata filtering
  -> semantic retrieval
```

## Context Engineering
Build a controlled context package containing:
- Employee
- Reporting period
- Current goals
- Relevant responsibilities
- Relevant 1:1 context
- Relevant evidence
- Personal evidence

Do not send the entire knowledge base to the LLM.

## Guardrails
Material claims must have supporting evidence. The system must be able to say:
> Insufficient evidence.

Never invent percentages, outcomes or achievements.

## Evaluation
Measure:
- Evidence retrieval precision
- Goal mapping accuracy
- Evidence coverage
- Hallucination rate
- Router accuracy
- Confidence calibration
- Latency
- Token/cost efficiency
- User acceptance

## Local setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Environment variables should include only local placeholders, for example:
```text
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=
POSTGRES_CONNECTION_STRING=
LANGSMITH_API_KEY=
LANGCHAIN_TRACING_V2=
MCP_MODE=MOCK
```

Never commit credentials.

## Development order
1. Mock MCP data
2. Evidence model
3. Evidence retrieval
4. PostgreSQL persistence
5. Goal/Role/1:1 ingestion
6. pgvector + RAG
7. Context Builder
8. LangGraph
9. Evidence Agent
10. Impact Agent
11. Validation Agent
12. Report Agent
13. Weekly Impact UI integration
14. Guardrails
15. Tracing
16. Evaluation
17. Replace mock MCP with real MCP
