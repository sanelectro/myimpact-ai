# M5 — Product-Facing API

## Goal

M5 establishes a stable `/api/v1` boundary that exposes MyImpact use cases without coupling clients to persistence, retrieval, or LLM implementation details. It reuses the existing M3/M4 capabilities and does not introduce database migrations.

## Milestone sequence

| Milestone | Scope | Readme |
|---|---|---|
| M5.1 | API v1 boundary, error format, and product contract principles | [M5.1-README.md](./M5.1-README.md) |
| M5.2 | Knowledge documents and semantic retrieval | [M5.2-README.md](./M5.2-README.md) |
| M5.3 | Goal management and read-only document expectations | [M5.3-README.md](./M5.3-README.md) |
| M5.4 | Goal evidence and impact analysis | [M5.4-README.md](./M5.4-README.md) |
| M5.5 | Career insight and goal impact report | [M5.5-README.md](./M5.5-README.md) |
| M5.6 | Stateless product Chat API | [M5.6-README.md](./M5.6-README.md) |
| M5.7 | Integration coverage and v1 error-contract corrections | [M5.7-README.md](./M5.7-README.md) |

## API surface

### Knowledge

- `POST /api/v1/knowledge/documents`
- `GET /api/v1/knowledge/documents`
- `GET /api/v1/knowledge/documents/{document_id}`
- `POST /api/v1/knowledge/documents/{document_id}/reprocess`
- `GET /api/v1/knowledge/documents/{document_id}/expectations`
- `POST /api/v1/knowledge/retrieve`

### Goals, evidence, impact, and insight

- `POST /api/v1/goals`
- `GET /api/v1/goals`
- `GET /api/v1/goals/{goal_id}`
- `PUT /api/v1/goals/{goal_id}`
- `DELETE /api/v1/goals/{goal_id}`
- `GET /api/v1/goals/{goal_id}/evidence`
- `POST /api/v1/goals/{goal_id}/impact/analyze`
- `GET /api/v1/goals/{goal_id}/impact`
- `GET /api/v1/goals/{goal_id}/insight`
- `GET /api/v1/goals/{goal_id}/report`

### Chat

- `POST /api/v1/chat`

## Contract principles

- Keep product contracts focused on user intent and stable resource/use-case responses.
- Enforce ownership at the product API boundary.
- Do not expose storage paths, repositories, embeddings, vector-search internals, prompts, or provider/model details.
- Semantic retrieval is for discovery; it is not an impact score.
- Keep document expectations document-scoped unless a persisted goal relationship is introduced deliberately.
- Reuse existing domain services and preserve legacy routes outside `/api/v1`.
- M5 does not implement authentication. Where required, `user_id` is temporary request context pending authenticated-user context.
- Chat is stateless in this milestone: no conversation history or new persistence.

## Error contract

Errors from `/api/v1` use a stable envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": []
  }
}
```

Validation errors include validation details; HTTP errors use stable HTTP-derived codes such as `HTTP_404`. Unexpected errors return `INTERNAL_ERROR` without exposing implementation details. Legacy routes retain their existing error behavior.

## Scope boundaries

- No database migrations or new persistent models are introduced by the M5 API work.
- No M3/M4 intelligence behavior is changed.
- M5.4 does not create a persistent goal-to-expectation relationship.
- M5.5 report output is a product-facing view, not a persisted report entity.
- M5.6 does not add history, knowledge retrieval, goal-aware context, or assistant orchestration.
- M5.7 validates the delivered M5.1–M5.6 surface and standardizes the v1 error contract.

## Completion summary

M5.1–M5.7 define the product-facing API boundary and expose knowledge, goals, evidence, impact, insight/report, and stateless chat use cases. Consult the individual milestone readmes for each contract's specific scope and implementation notes.
