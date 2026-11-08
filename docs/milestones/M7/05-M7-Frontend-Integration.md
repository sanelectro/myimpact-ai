# M7.5 – Frontend Integration

**Target repository:** `myimpact-web`

## 1. Current UI baseline

The inspected frontend already has:

- `src/pages/Impact/ImpactPage.tsx`
- `src/pages/Impact/ImpactDetailPage.tsx`
- `src/api/myImpact.ts`
- `src/types/api.ts`
- React Query for data loading and caching.

Current Impact UI is built around legacy goal-level AI impact assessments and displays impact type, summary, score and confidence. M7 must evolve this experience without mislabeling legacy AI confidence/score as employee or manager validation.

## 2. Proposed frontend structure

```text
src/
  types/
    impact.ts
  api/
    impact.ts
  hooks/
    impact/
      useImpactAnalysis.ts
      useImpactOverview.ts
      useImpactStatements.ts
      useImpactComparison.ts
      useImpactTrends.ts
  pages/Impact/
    ImpactLayout.tsx
    ImpactOverviewPage.tsx
    ImpactByGoalsPage.tsx
    ImpactRolePage.tsx
    ImpactEvidenceReviewsPage.tsx
    ImpactComparisonPage.tsx
    ImpactTrendsPage.tsx
    ImpactStatementDetailPage.tsx
    components/
      PerspectiveBadge.tsx
      EvidenceReviewState.tsx
      ImpactStatementCard.tsx
      MeasurementList.tsx
      AttributionList.tsx
      AssessmentVersionHistory.tsx
```

Names can be adapted to the existing route/layout conventions, but keep API clients, shared types, data hooks and page components separated.

## 3. TypeScript contracts

Create `src/types/impact.ts` for M7-specific contracts. Do not overload the existing legacy `ImpactAssessment` interface in `src/types/api.ts`.

Suggested types:

- `ImpactAnalysis`, `ImpactAnalysisStatus`
- `ImpactStatement`, `ImpactStatementStatus`, `ImpactDimension`
- `ImpactEvidenceLink`, `EvidenceApprovalStatus`, `ImpactEvidenceRelationship`
- `ImpactAssessmentPerspective`, `EmployeeAssessmentStatus`, `AIAssessmentStatus`, `ManagerAssessmentStatus`
- `ImpactAssessmentVersion`
- `ImpactMeasurement`, `ImpactAttribution`
- `ImpactRoleExpectation`
- page read models: `ImpactOverview`, `ImpactByGoal`, `ImpactRoleSummary`, `ImpactEvidenceReview`, `ImpactComparison`, `ImpactTrend`

Represent missing numeric values as `number | null`. Do not coerce null to 0. Keep evidence approval state separate from manager impact status.

## 4. API client and hooks

Create `src/api/impact.ts` for M7 endpoints. Keep existing legacy `getGoalImpact()` in `src/api/myImpact.ts` until the legacy UI is migrated and regression-checked.

Use React Query query keys scoped by analysis ID and filters, for example:

- `['impact-analysis', analysisId]`
- `['impact-overview', analysisId]`
- `['impact-goals', analysisId, filters]`
- `['impact-role', analysisId]`
- `['impact-evidence-reviews', analysisId, filters]`
- `['impact-comparison', analysisId]`
- `['impact-trends', analysisId, filters]`

Invalidate only affected queries after statement/evidence/assessment mutations. Do not optimistically display a manager acceptance before the server confirms it.

## 5. Six agreed Impact pages

### 5.1 Overview

- Selected analysis period and lifecycle status.
- Impact statement count.
- Employee self-assessment, AI and manager-validated counts displayed separately.
- Evidence review-state breakdown.
- Key outcome/measurement highlights with units and source links.
- Clear callouts for incomplete or unreviewed information.

### 5.2 By Goals

- Group impact statements by existing goal.
- Display goal progress/status separately from impact validation.
- Link to goal details and statement details.
- Show evidence coverage and manager decision per statement.

### 5.3 Role Impact

- Show existing role responsibilities and competencies in scope.
- Map statements and evidence to those expectations.
- Show coverage, partial coverage and gaps with explanation.
- Do not infer role assignment from free-text user role. If employee role context is unavailable, display that role mapping is not configured rather than guessing.

### 5.4 Evidence & Reviews

- List every linked evidence item, including `PENDING`, `APPROVED`, `NEEDS_INFORMATION` and `REJECTED`.
- Display manager feedback/review history available from existing sources.
- Show source URL/type, captured/updated date and evidence version where available.
- Explain whether the evidence is eligible for manager validation.
- Make it clear that evidence approval is not the same as manager acceptance of impact.

### 5.5 Comparison

- Three distinct columns/sections: Employee, AI, Manager.
- Show each perspective's latest version, status, summary, rationale, measurements and attribution.
- Show version history and superseded versions.
- Display missing assessment as “Not yet assessed”.
- Highlight agreement/disagreement without calculating an unapproved composite score.

### 5.6 Trends

- Trend impact statements and manager decisions across periods.
- Trend only comparable measurements (same metric and unit or explicitly normalized).
- Show missing data honestly; do not convert null to zero.
- Avoid counting the same outcome multiple times because it has multiple supporting evidence links.

## 6. Interaction and state rules

- Employee can create/edit own draft statements and submit a new self-assessment version.
- Submitted employee versions are read-only; later edits create a new version.
- Manager actions appear only when the backend says the actor is authorized.
- Manager decisions require rationale where the API contract requires it.
- AI results are labeled advisory and must never look like manager-approved results.
- Evidence review status is read-only in M7; use existing M6 approval/review workflows to request information, resubmit or make evidence decisions.
- Disable duplicate submissions while a mutation is in flight and handle `409` conflicts by refreshing current versions.

## 7. UX states

Every page must implement:

- Loading state.
- Empty state with a useful next action.
- Error state with retry.
- Partial-data state (e.g. no manager assessment yet).
- Permission-denied/not-found state.
- Stale-data/version-conflict state.

Do not show a success state until the API confirms the operation.

## 8. Accessibility and visualization

- Use text labels in addition to color for statuses.
- Provide accessible names for charts and tables.
- Ensure trend charts have a textual data/table alternative.
- Do not use a red/green-only distinction for accepted/rejected.
- Keep evidence review history readable on smaller screens; avoid hiding rejected items behind filters by default.

## 9. Frontend test requirements

- TypeScript contract tests or compile-time validation against API response types.
- Component tests for all four evidence states and all three perspectives.
- Employee/manager permission rendering tests.
- Empty, loading, error and partial perspective states.
- Comparison version selection and superseded history.
- Trend null handling and units.
- End-to-end employee submission → manager review → comparison update flow.
- Regression tests for existing goal-level legacy Impact routes until migration is complete.
