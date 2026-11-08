# Goal Validation Benchmark

`goal-validation-v1` is an independent 30-case starter benchmark in
`evaluation/goal_validation_v1.json`. It covers clarity/structure,
ownership/accountability, delivery-outcome-impact, SMART/measurability,
feasibility/role alignment, and conflicting/incomplete scenarios. It does not
read or write M6.6 datasets or result files.

## Status and review workflow

The complete starter dataset and every case are marked `DRAFT_UNREVIEWED`;
human review is `PENDING`, all reference values are explicitly provisional,
adjudicated references are empty, and threshold values are unset. Treat initial
metrics only as exploratory diagnostics—not human-approved ground truth,
release evidence, or a pass result.

1. Review every input and provisional reference with independent reviewers.
   Record reviewer identities, decisions, timestamps, and notes in the case
   `human_review.reviewer_slots`.
2. Resolve disagreements and update the case's `adjudicated_reference` with
   the agreed labels and rationale. Record adjudicator identity/time, set its
   adjudication status to `ADJUDICATED`, and mark the case label/review status
   `HUMAN_REVIEWED` / `APPROVED`.
3. After all cases are reviewed and adjudicated, record dataset-level
   approval and mark the dataset `HUMAN_REVIEWED`.
4. Product/QA owners must explicitly approve every required metric threshold
   in `threshold_approval.thresholds`, with approver and timestamp. There are
   deliberately no default numeric thresholds. For false-positive and
   false-negative rates, the approved threshold is a maximum; other thresholds
   are minimums.
5. Version any change to reviewed labels or approved thresholds and preserve
   the review/adjudication audit details. Never convert provisional starter
   labels into approved labels without this process.

The release gate remains closed unless dataset and case review/adjudication
metadata, approved references, and all required approved thresholds are
present and every metric satisfies its approved threshold. A draft dataset is
rejected if any threshold is marked approved or populated.

## Seed a database-backed human-review batch

The shared reviewer workspace supports Goal Validation separately from M6.6
evidence assessment. Seed two active, dedicated reviewer accounts under an
active platform administrator:

```powershell
python -m scripts.seed_goal_validation_review `
  --actor-user-id demo-myimpact-admin `
  --reviewer-ids demo-reviewer-1 demo-reviewer-2
```

This previews the 30 cases and 60 independent assignments without writes. Add
`--apply` to register the immutable dataset catalogue and create the review
batch. Repeating the command is idempotent; incompatible existing assignments
or changed versioned dataset content are rejected rather than overwritten.
The script uses existing Flyway-managed review tables and does not create or
modify application goals, evidence, reviewer accounts, reviews, or thresholds.

Reviewers sign in and open `/evaluate`, select `goal-validation-v1` in the
Review batch selector, and review their assigned cases. Both reviewers receive
all 30 cases. Goal structure and role/scenario context are shown without
provisional reference labels. Readiness options are READY, NEEDS_REFINEMENT,
NEEDS_DISCUSSION, and INVALID. Record dimension findings, missing information,
clarification questions, and the reasoning in the review rationale.

Saved reviews remain editable until each reviewer previews and confirms their
final batch submission. Independent-review isolation and adjudication reuse
the existing workflow. Seeding alone never counts as human review or release
approval; the standalone benchmark references and release gate still require
the separately documented review/adjudication and threshold approval process.

## Supplied AI proposal dataset

The supplied `milestones/M6.6-goal-validation-v1-final.json` is a separate
dataset, `goal-validation-v1` version `1.0.0`. Some case inputs differ from
the starter dataset above, even where case IDs match. Its inputs must not be
mixed with the original batch.

Preview its 30 cases, 30 proposals and 60 assignments with:

```powershell
python -m scripts.seed_goal_validation_proposals `
  --actor-user-id demo-myimpact-admin `
  --reviewer-ids demo-reviewer-1 demo-reviewer-2
```

Add `--apply` to seed this separate dual-review batch. The operation preserves
the existing batch, does not create human decisions, and can be repeated
without duplicating records. In this batch, each assigned reviewer sees the
suggested label and rationale before reviewing and the resulting review is
recorded as proposal-assisted, **not blind**. This is a deliberate operational
change from the source JSON's requested blind-review configuration; it does not
alter the immutable source document or the original blind batch. These reviews
cannot be used as evidence of independent blind review. Reviewers cannot see
each other's decisions before their own submission. Proposals are not approved
references or human decisions. Detailed findings, questions,
improvements and provenance remain in the supplied JSON, not in the proposal
display. Missing model, prompt, run and generation-time provenance is unknown
and is not inferred. Human adjudication and approved release thresholds are
still required. To review these cases, select `Goal Validation proposals (1.0.0)`
from the Review batch selector.

## Goal Validation label rename

`NEEDS_IMPROVEMENT` is now `NEEDS_REFINEMENT` (Needs Refinement), and
`NEEDS_REVIEW` is now `NEEDS_DISCUSSION` (Needs Discussion). Their meanings
and precedence are unchanged. This rename applies only to Goal Validation, not
similarly named lifecycle or evidence-assessment statuses. The original source
JSON and historical validation runs remain unchanged; legacy values are mapped
when interpreted. The benchmark evaluator accepts both vocabularies and compares
equivalent statuses.

Existing Goal Validation review batches can be migrated after pausing review
activity and stopping the old API process:

```powershell
python -m scripts.migrate_goal_validation_labels --actor-user-id demo-myimpact-admin
python -m scripts.migrate_goal_validation_labels --actor-user-id demo-myimpact-admin --apply
```

The first command is a dry run. The second updates review and proposal labels
and case catalogue snapshots in a single transaction, preserving identities,
rationales and finalization; it records old and new values and hashes as audit
events. It refuses unexpected catalogue content or existing human/AI comparison
records, and repeating it is safe. Run Flyway migrations before deploying the
updated engine. Previously issued review-preview tokens must be refreshed.

## Evaluate predictions

Provide a JSON array of records shaped like:

```json
[
  {
    "case_id": "gv-01",
    "repeat_index": 1,
    "prediction": {
      "dimensions": ["structure"],
      "findings": [
        {"dimension": "structure", "finding_code": "ambiguous_intent"}
      ],
      "questions": ["Which platform quality issue should this goal address?"],
      "improvement": "Name the quality dimension and a verifiable result.",
      "missing_information": ["desired_quality_dimension"],
      "status": "NEEDS_REFINEMENT",
      "accountability": null
    }
  }
]
```

Run the standalone loader, schema validation, and evaluator from `myimpact-ai`:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.goal_validation_benchmark `
  --predictions path\to\goal-validation-predictions.json
```

The JSON report is printed to stdout and includes dimension precision/recall/F1,
finding precision/recall/F1, missing-information recall, readiness accuracy and
ready false-positive/negative rates, accountability preservation, structured
output validity, and repeatability for cases with multiple runs. Results are
`NON_RELEASE_EXPLORATORY` until the release gate is explicitly satisfied.
