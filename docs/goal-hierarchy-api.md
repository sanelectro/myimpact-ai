# Goal hierarchy API

Hierarchy operations are available under `/api/v1/goals` in `myimpact-ai`.
All operations require the authenticated goal owner and the existing `user_id`
query parameter. Parent and child must have the same owner. Goal Level does not
determine the relationship and skipped levels are allowed.

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
level, ownership, approval, lifecycle, evidence, or deferrals. The API does
not yet expose inherited evidence or aggregate child outcomes or impact.
Deploy the hierarchy database migration before enabling these routes.
