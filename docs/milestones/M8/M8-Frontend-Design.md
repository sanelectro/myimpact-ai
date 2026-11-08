# M8 — Frontend Design

**Target repository:** `myimpact-web`  
**Status:** Proposed frontend implementation design.

## 1. Existing baseline

The 8 November 2026 uploaded frontend snapshot contains a Reports navigation/page placeholder. Existing API helpers are centralized in `src/api/myImpact.ts`, and shared API types are in `src/types/api.ts`. M8 should follow the current routing, React Query, component, styling and API-client conventions rather than impose a new frontend architecture.

## 2. Navigation and pages

Proposed navigation:
- Reports (landing/history)
- Generate Report (workflow)
- Report Preview (draft/published view)

Avoid creating a separate permanent navigation item for every report type. Select report type within the generation workflow.

## 3. Page responsibilities

### ReportsPage
- Recent reports visible to actor.
- Filters: report type, period, status and subject (manager only).
- Generate report action.
- Empty/loading/error states.
- Report metadata: type, subject, period, version, generated date and status.

### GenerateReportPage
- Report type selector.
- Audience derived/limited by actor authorization.
- Reporting-period picker.
- Subject employee selector for authorized managers.
- Team selector only for authorized team summary.
- Explain required source data and limitations.
- Submit generation and display progress/status.
- Prevent duplicate submission while pending.

### ReportPreviewPage
- Report title, subject and period.
- Section navigation and content.
- Validation findings and data-completeness notices.
- Source references/links where user has access.
- Draft editing for permitted narrative fields.
- Publish action when authorized.
- PDF and DOCX export actions.

### ReportHistoryPage (may be integrated into ReportsPage)
- Version lineage.
- Current/stale state.
- Generation and publication statuses.
- View/download historical versions.
- Regenerate as a new version.

## 4. Suggested frontend structure

```text
src/
  types/
    reporting.ts
  api/
    reporting.ts
  hooks/
    reporting/
      useReports.ts
      useReport.ts
      useGenerateReport.ts
      useReportHistory.ts
      useReportArtifacts.ts
  pages/
    Reports/
      ReportsPage.tsx
      GenerateReportPage.tsx
      ReportPreviewPage.tsx
      components/
        ReportTypeSelector.tsx
        ReportPeriodSelector.tsx
        SubjectSelector.tsx
        ReportStatusBadge.tsx
        ReportSection.tsx
        ReportValidationPanel.tsx
        ReportSourceReferences.tsx
        ReportDownloadActions.tsx
        ReportVersionHistory.tsx
```

Adapt names to existing folder and route conventions after checking the live checkout.

## 5. TypeScript contracts

Create `src/types/reporting.ts` for M8 types. Do not overload existing legacy report types without a deliberate adapter.

Types should cover:
- `ReportKind`, `ReportAudience`
- `ReportGenerationStatus`, `ReportPublicationStatus`, `ReportFreshness`
- `ReportSummary`, `ReportDetail`, `ReportContent`
- `ReportSection`, `ReportClaim`, `ReportSourceReference`
- `ReportValidationFinding`, `ReportValidationResult`
- `ReportArtifact`, `ReportVersion`
- request/response types for generation, draft edit, publish and export.

Use explicit `null` for missing numeric/source fields. Do not coerce null to zero.

## 6. API client and React Query

Create `src/api/reporting.ts` using the existing shared client and authentication behavior.

Suggested query keys:
- `['reports', filters]`
- `['report', reportId]`
- `['report-preview', reportId]`
- `['report-history', reportId]`
- `['report-validation', reportId]`
- `['report-artifacts', reportId]`

Invalidate only affected queries after draft edits, publish, regenerate or export. Do not optimistically mark generation complete or publication successful before API confirmation.

## 7. UX and interaction rules

- Actor and audience permissions are supplied by server/API capability response; client visibility is not a security boundary.
- Employee cannot select another employee.
- Manager selector lists only authorized employees.
- Keep source status labels visible and textual, not color-only.
- Distinguish source facts from AI suggestions.
- Do not hide warnings by default.
- Show section-level partial/unavailable states.
- Draft edits must not mutate source goals/evidence/impact.
- Published reports are read-only.
- Export downloads must use authorized API endpoints, not guessed storage URLs.

## 8. Required states

Every page and async operation handles:
- Loading.
- Empty.
- Error with retry.
- Partial data.
- Permission denied/not found.
- Generation pending.
- Generation failed.
- Validation failed/warnings.
- Draft ready.
- Published.
- Stale.
- Export pending/failed/succeeded.

## 9. Accessibility and responsive behavior

- Keyboard accessible forms, tabs and dialogs.
- Proper labels and focus management.
- Text labels in addition to status colors.
- Report content readable on mobile and desktop.
- Tables have headers and responsive fallback.
- Download controls have clear accessible names.
- Validation errors are announced and associated with relevant sections.

## 10. Frontend acceptance criteria

- Reports placeholder is replaced with functional landing/history.
- Employee and manager workflows use correct server-derived capabilities.
- Generation and export status reflect server response.
- Preview displays all structured sections and source references.
- Partial/missing data and validation warnings are visible.
- Published versions cannot be edited.
- PDF/DOCX download works and is permission checked.
- TypeScript build, component tests and E2E flows pass.
