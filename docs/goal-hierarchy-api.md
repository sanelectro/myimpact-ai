# Goal hierarchy API

Hierarchy operations are available under `/api/v1/goals` in `myimpact-ai`.
All operations require the authenticated goal owner and the existing `user_id`
query parameter. Parent and child must have the same owner. Goal Level does not
determine the relationship and skipped levels are allowed.

- `POST /api/v1/goals` optionally accepts `parent_goal_id`. Goal creation,
  its initial definition version, and the first relationship event commit
  together. An absent, null, or omitted parent creates a standalone goal;
  a missing or unowned parent returns HTTP 404 without creating a goal.
  The parent is a relationship, not part of the definition version.
- `GET /{id}/hierarchy` returns the goal and its ancestors, nearest first.
  `limit` is between 1 and 100; `next_ancestor_id` identifies an ancestor
  omitted by the limit. The hierarchy read and all hierarchy writes use the
  database transaction lock.
- `GET /{id}/children` and `GET /{id}/relationship-history` accept `limit`
  (1-100) and `offset` (0 or greater). History is newest revision first.
- `PUT /{id}/parent` accepts `parent_goal_id`, `expected_revision`, and an
  optional `reason`.
- `DELETE /{id}/parent` accepts a JSON body containing `expected_revision` and
  an optional `reason`.

Both writes return `id`, `parent_goal_id`, and the resulting
`relationship_revision`. A stale revision or a cycle returns HTTP 409; an
unowned goal or parent returns HTTP 404. Same-parent writes are idempotent
after the revision check and do not create an event. Effective changes create
one append-only event in the same transaction. The database prevents deleting
referenced parents or goals with relationship history; the v1 goal delete
endpoint returns HTTP 409 for these restrictions.

Relationship changes do not create a goal-definition version or change goal
level, ownership, approval, lifecycle, evidence, or deferrals.

## Evidence context

- `POST /{id}/evidence-links` links an existing, active, owner-owned evidence
  record to an eligible goal. It accepts `evidence_id`, `relevance`,
  `mapping_kind` (`PRIMARY` by default or `CONTRIBUTION`), and an optional
  `contribution_description` for contribution mappings. The mapping gets
  a pending approval; duplicate links return HTTP 409.
- `GET /{id}/evidence-context` is an opt-in view of active evidence linked
  directly or to descendants. Results are deduplicated by evidence, with each
  real mapping exposed as an origin including its source goal, path, mapping
  kind, and approval status. `limit` (1-100) and `offset` paginate evidence;
  `max_depth` (0-100, default 20) limits descendant traversal. The traversal
  also visits at most 1,000 goals. `hierarchy_truncated` indicates that either
  limit omitted goals, so consumers must not treat a truncated view as complete.

The existing direct evidence endpoint and assessment behavior remain direct
only; inherited evidence does not create parent mappings or approvals. These
endpoints do not aggregate child outcomes or impact. Deploy the hierarchy and
evidence contribution database migrations before enabling the corresponding
API changes.

Goal definition updates may include `expected_deferred_requirements` alongside
an explicit `structured_fields.deferred_requirements` update. The server
compares it with the stored deferrals under the goal row lock and returns HTTP
409 if they changed. Clients that omit the optional expectation retain their
existing behavior, including preservation when deferrals are omitted.

## Separate measures

`GET /{id}/measures` reports direct-child lifecycle status counts, including
archived children, without an average or weighted roll-up. It includes the
existing, direct-only M6.6 criterion assessment and its criterion evidence
coverage. Clients already loading that assessment can pass
`include_assessment=false` to omit the duplicate assessment read; the field
is then null. Criteria have not been classified as execution or outcome, so that
assessment is not an outcome measure. `outcome_achievement` and
`demonstrated_impact` are currently null: neither child completion nor an
assessment score establishes them. Existing per-evidence advisory impact
assessments remain available from `GET /{id}/impact`; they are not aggregated
or inferred from descendants.
