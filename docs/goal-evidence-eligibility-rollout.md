# Goal evidence eligibility rollout

Evidence submission for goals with user-managed versions requires both an
`ACTIVE` lifecycle state and a persisted `READY` validation run attached to the
latest goal version, plus an approval recorded for that exact version. A
validation result or approval for an earlier revision does not qualify. The API
determines eligibility from persisted goal/version/validation/approval records;
request data cannot claim a validation or approval status.

Only the most recent validation run for the latest goal version determines
readiness. A newer non-ready result supersedes an earlier READY result without
deleting history. If the goal changes during validation, the run remains linked
to the evaluated version and the API returns a conflict requiring revalidation
of the latest version.

Semantic runs now use `goal-semantic-validation-v2` for clarity, accountability,
scope, success criteria, measurability, delivery/outcome/impact boundaries,
timeline/feasibility, and role-alignment concerns. Earlier prompt versions remain
in history. Role-alignment text is employee-supplied, not an authoritative role
expectations source; the engine requests confirmation rather than inferring
misalignment. Human-reviewed benchmark quality and thresholds remain release
prerequisites.

Operational logs include completion/failure, goal and version identifiers,
prompt/model/rule versions, duration, finding dimensions, superseded runs, and
evidence eligibility rejection. Goal text, source text, and suggested content
are not included in these events.

All product routes are mounted with `authorize_request_user`, which verifies
the authenticated JWT identity and rejects mismatched query, path, JSON, or
form `user_id` values before route services run. Validation, validation history,
evidence eligibility, and evidence submission additionally check goal ownership.
The compatibility `user_id` parameter does not grant access by itself. The
platform-admin read exception does not apply to validation history or evidence
eligibility, and it never grants evidence submission or validation permission.

Approval and lifecycle remain distinct. The existing owner-authorized approve
action records an immutable approval for the latest version. For a draft goal it
also performs the existing transition to `APPROVED`. If a material edit creates
a newer version on an already approved or active goal, approving that version
does not change the goal's lifecycle status; it records approval of the new
version. Activation requires the latest version to be READY and approved.
Approval actor semantics are unchanged: employee confirmation is required;
manager approval is not required for the current implementation. The
version-scoped approval record does not imply a manager decision.

Goals created by the legacy-version backfill remain exempt by default so the
backfill does not disrupt existing approval, activation, or evidence workflows.
They are not assigned a `READY` result as part of the backfill, and legacy
versions cannot be validated. Set
`REQUIRE_VALIDATION_FOR_LEGACY_GOAL_EVIDENCE=true` to opt legacy goals into
validation-required activation and evidence eligibility. Since legacy versions
cannot become READY, edit a legacy goal to create a user-managed version before
using this strict mode.

The legacy exception applies only while a goal's latest version has origin
`LEGACY`. Creating a goal or saving a material revision creates a user-managed
version and always enables validation and approval checks, regardless of the
legacy setting. Operators can first deploy with the default compatibility
setting, then enable strict legacy enforcement after choosing an appropriate
migration and validation rollout.
