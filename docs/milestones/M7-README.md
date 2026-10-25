# MyImpact — M7 Release Readiness

## Milestone overview

**Milestone:** M7  
**Status:** Not confirmed complete.

M7 makes the release go/no-go decision after M6.10 integrated end-to-end
validation is complete. It verifies that the tested product can be set up,
deployed, operated, and supported using documented procedures.

## Release acceptance checklist

- [ ] Fresh setup and database migrations work using documented instructions.
- [ ] Seed/demo data loads without enum, migration, or conflict errors.
- [ ] Full backend tests, frontend tests, type-check, and production build pass.
- [ ] API contracts, base URL configuration, CORS, and authentication issuer
  settings are verified.
- [ ] Production requirements for secrets, signing keys, HTTPS, secure cookies,
  trusted origins, email verification, and abuse protection are documented and
  satisfied.
- [ ] Deployment and rollback procedures are documented and verified.
- [ ] Monitoring, diagnostics, alerting, and support runbooks are ready.
- [ ] Known limitations, deferred scope, and data/privacy boundaries are
  documented.
- [ ] The README/runbook and user-facing operational guidance are current.
- [ ] M6.10 regression evidence and unresolved issues are reviewed.
- [ ] An explicit release go/no-go decision and its rationale are recorded.

## Integrated release review

Review the full agreed product scope validated under M6.10, including goal
criteria and evidence assessment, Impact Analysis, reports, and Admin Portal
and Platform Access. AI Assistant is not part of the current M6/M7 scope.

## Completion rule

Do not mark M7 complete solely because milestone documents or historical test
results exist. Record the current commit/environment, exact commands and
scenarios run, results, unresolved limitations, and release decision.
