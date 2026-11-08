# M8 — Services and Business Rules

**Target repository:** `myimpact-ai`  
**Status:** Proposed service design.

## 1. Suggested service boundaries

```text
Report API
  -> ReportApplicationService
       -> ReportAccessService
       -> ReportContextBuilder
            -> M6 Goal/Evidence/Insight readers
            -> M7 Impact Analysis readers
            -> Role catalogue reader
       -> ReportTemplateRegistry
       -> ReportGenerationOrchestrator
            -> LLM provider adapter
       -> ReportValidationService
       -> ReportRepository / SnapshotRepository
       -> ReportExportService
            -> PDF renderer
            -> DOCX renderer
            -> approved storage adapter
```

Keep API routing thin. Domain rules belong in domain policies/application services. Reuse existing dependency injection, repository, transaction and LLM provider patterns.

## 2. M8.1 — Context builder stories

### M8.1.1 Report domain foundation
- Define report kind, audience, period, lifecycle and content types.
- Add explicit legacy enum adapters.
- Validate report-kind/audience combinations.
- Acceptance: unit tests prove enum compatibility and invalid combinations are rejected.

### M8.1.2 Authorization-aware source aggregation
- Resolve authenticated actor and subject/team scope.
- Query M6 goals, goal assessments, evidence metadata and existing career/1:1 insights through stable service/read contracts.
- Query M7 impact analyses, statements, perspectives, measurements and attributions through M7 read contracts.
- Query role expectations only when role mapping is valid.
- Acceptance: no source is fetched outside the authorized subject/team and period.

### M8.1.3 Period and source filtering
- Define inclusive/exclusive date semantics consistently.
- Use source-specific event/effective dates; document fallback when a source has no date.
- Do not silently include stale or out-of-period records.
- Acceptance: boundary-date tests and source-specific filtering tests pass.

### M8.1.4 Snapshot creation
- Persist source manifest and bounded context payload.
- Pin source IDs/versions and retrieval time.
- Hash canonical snapshot payload where useful.
- Acceptance: later source updates do not mutate an existing snapshot.

### M8.1.5 Completeness assessment
- Compute section availability (`AVAILABLE`, `PARTIAL`, `UNAVAILABLE`) from explicit source presence/rules.
- Distinguish missing, null, not assessed, pending, rejected and zero.
- Acceptance: incomplete inputs result in explicit warnings, not invented values.

## 3. M8.2 — Generation engine stories

### M8.2.1 Orchestration
- Coordinate request validation, context, template, generation, schema parsing, validation and persistence.
- Use background processing if the existing architecture requires it for long tasks.
- Acceptance: every stage and failure is observable; retry does not duplicate reports.

### M8.2.2 Template registry
- Resolve active template by report kind, audience and locale.
- Pin exact template and prompt versions.
- Acceptance: historical reports remain associated with the original template version.

### M8.2.3 Prompt construction
- Build model input only from bounded snapshot fields.
- Clearly label source facts, employee claims, AI interpretations, manager decisions and suggestions.
- Instruct model to omit unsupported claims and return structured output.
- Acceptance: prompt construction is deterministic for a given snapshot/template and contains no unauthorized fields.

### M8.2.4 Structured generation
- Parse output against versioned Pydantic schema.
- Handle malformed JSON, missing required sections, provider timeout and refusal/error responses.
- Retry only transient failures with bounded policy.
- Acceptance: invalid output never becomes a draft-ready report.

### M8.2.5 Usage and operational metadata
- Record provider/model/version and token usage when available.
- Sanitize errors and logs.
- Acceptance: operational records contain enough diagnostics without raw sensitive context.

## 4. Report-specific composition rules

### Employee performance and goal progress
- Use M6 goal assessment output as supplied.
- Use M7 impact assessments as separate perspectives.
- Do not derive a new employee rating.
- Do not equate completed goals with impact.

### 1:1 brief
- Reuse M6.6 preparation service/data if present.
- Distinguish suggested questions from confirmed follow-up actions.
- Never invent prior meeting content.

### Career development
- Reuse M6 career insight output.
- Distinguish evidence-backed strengths, explicit gaps and missing evidence.
- Do not claim promotion readiness or prescribe a promotion outcome.

### Manager individual/team
- Use manager-scoped access.
- Keep employee/AI/manager perspectives separate.
- Avoid rankings and unapproved composite scores.
- Prevent double-counting shared impact.

## 5. M8.7 — Validation rules

Blocking errors (examples):
- Invalid report schema.
- Subject or period mismatch.
- Source reference does not resolve to snapshot manifest.
- Unsupported material numeric claim.
- Unauthorized source included.
- Contradiction between report claim and source state.
- Published content mutation attempt.

Warnings (examples):
- Missing impact assessment.
- Partial evidence coverage.
- Role mapping unavailable.
- Some source records lack dates.
- Pending or rejected evidence is mentioned with correct qualification.
- Suggested discussion prompt has no direct source (must be labeled as suggestion).

Every finding includes rule ID, severity, affected section/claim, explanation and remediation.

## 6. M8.8 — Publication and export rules

- Draft editing is limited to permitted narrative content and user-added notes.
- Editing a draft must not mutate M6/M7 source data.
- Publication requires an authorized actor and validation gate.
- Published version is immutable.
- Regeneration creates a new version and preserves lineage.
- Export artifact references exact report version and renderer version.
- Download always rechecks authorization.
- Failed export does not change report publication status.

## 7. Error handling and idempotency

- Idempotency key is scoped to actor and request payload.
- Same key + same payload returns existing request/result.
- Same key + different payload returns conflict.
- Retry transient provider/storage failures only.
- Never retry authorization or business validation failures automatically.
- Keep generation attempts as separate run records.
- Use bounded exponential backoff where consistent with project conventions.
- Ensure transaction boundaries prevent half-persisted report lifecycle states.

## 8. Observability

Record:
- Report ID, generation run ID, kind, audience and status.
- Stage durations and failure code.
- Provider/model and prompt/template versions.
- Token usage when available.
- Export format, renderer version and outcome.

Do not log full report text, source evidence, raw prompts or personally sensitive context by default.
