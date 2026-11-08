# MyImpact M7 – Code Changes Specification

**Milestone:** M7 – Impact Analysis  
**Version:** 0.1  
**Status:** Proposed implementation design; align with approved M7 database design before coding  
**Repository baseline:** Latest uploaded `myimpact-ai`, `myimpact-web`, `myimpact-api`, and `myimpact-db` snapshots dated 8 November 2026.

## Purpose

This folder translates `M7-Database-Changes.md` and the agreed M7 product direction into implementation-level guidance for types, domain structures, ORM models, repositories, API contracts, services, and frontend integration.

M7 must make the distinction between:

- **Employee self-assessed impact** – what the employee says they delivered and the impact they believe it created.
- **AI-assisted interpretation** – an advisory analysis grounded in source evidence, never a manager decision.
- **Manager-validated impact** – the manager's independently recorded assessment, rationale, and decision.

M7 must preserve rejected and `NEEDS_INFORMATION` evidence, feedback, review history, contribution/attribution, role coverage, gaps, trends, and traceability. Evidence approval and impact validation are separate concepts.

## Read in this order

1. [Domain, Types and Structures](01-M7-Domain-Types-and-Structures.md)
2. [ORM Models and Repositories](02-M7-ORM-Models-and-Repositories.md)
3. [API Contracts](03-M7-API-Contracts.md)
4. [Services and Business Rules](04-M7-Services-and-Business-Rules.md)
5. [Frontend Integration](05-M7-Frontend-Integration.md)

Related design: `M7-Database-Changes.md` (separate database specification).

## Architecture boundaries

| Repository | M7 responsibility |
|---|---|
| `myimpact-db` | SQL-first Flyway migrations for the seven proposed M7 tables. |
| `myimpact-ai` | Main product backend: domain types, SQLAlchemy models, repositories, services, FastAPI routes, schemas and authorization. |
| `myimpact-web` | TypeScript contracts, API client, query hooks and six Impact pages. |
| `myimpact-api` | Authentication service only in the inspected baseline. Do not move M7 product endpoints here. |

## Non-negotiable constraints

1. M6 remains the source of truth for goals, milestones, evidence, evidence mappings, evidence approvals, goal criteria and existing intelligence/review flows.
2. Do not add a second evidence approval workflow or duplicate evidence/evidence-mapping tables.
3. Do not repurpose the existing `impact_assessments` table. It remains the evidence-and-goal-level AI assessment store.
4. Do not assume a milestone is an achievement. The proposed `impact_statement` is the M7 employee-visible impact claim/outcome.
5. Do not create a shared performance-period catalogue in this implementation. `impact_analyses` owns the employee's date range until a shared cycle is explicitly designed.
6. Do not infer an employee's normalized organization role from the free-text `users.role` field. Role expectation links must reference the existing organization role catalogue and validate scope.
7. Do not expose an arbitrary universal impact score. Use dimensions, sourced measurements, evidence state, rationale and versioned perspectives.
8. Every API read and write must enforce employee/manager/organization authorization server-side. A caller-supplied `user_id` query parameter is not an authorization boundary.
9. Preserve rejected and `NEEDS_INFORMATION` evidence in evidence/review views and impact context. Do not silently filter them out of the employee's impact story.
10. Treat this folder as a design contract, not a request to change code or apply migrations automatically.

## Suggested implementation sequence

- **M7.2 – Backend foundations:** domain enums/types, SQLAlchemy models, repository interfaces/implementations, model registration, unit tests.
- **M7.3 – Core APIs and services:** employee analysis workspace, impact statements, evidence links, employee submission, manager assessment/versioning, authorization tests.
- **M7.4 – AI-assisted analysis and aggregation:** AI perspective generation, measurements, attribution, role coverage and trend read models.
- **M7.5 – Frontend:** six pages, comparison states, evidence/review traceability, loading/error/empty states.
- **M7.6 – Integrated validation:** migration + ORM + API + frontend contract + authorization + history + regression tests together.

Do not implement later phases by assuming earlier design questions are settled. The database document's open decisions must be resolved before the relevant migrations or endpoints are finalized.
