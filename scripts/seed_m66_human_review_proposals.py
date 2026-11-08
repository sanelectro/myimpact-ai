"""Import a non-approved M6.6 human-review proposal into benchmark reference tables."""

from __future__ import annotations

import argparse
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.models.human_review import (
    BenchmarkCaseVersionDB,
    BenchmarkReviewProposalDB,
)
from app.db.session import SessionLocal
from app.evaluation.assessment_evaluation import load_dataset_by_id
from app.services.human_review import register_benchmark_dataset

DATASET_ID = "m66-intelligence-comparison-v3"
DATASET_VERSION = "m66-intelligence-comparison-v3"
SEED_ACTOR = "model-generated-proposal"


def _extract_case_proposals(markdown: str) -> tuple[dict[str, dict], set[str]]:
    attention_section = markdown.split(
        "## Cases needing benchmark-owner attention before ground-truth approval",
        maxsplit=1,
    )
    attention_ids: set[str] = set()
    if len(attention_section) == 2:
        attention_text = attention_section[1].split(
            "## Recommended use", maxsplit=1
        )[0]
        for line in attention_text.splitlines():
            if re.match(r"^\d+\.\s+\*\*", line):
                attention_ids.update(re.findall(r"`([^`]+)`", line))

    proposals: dict[str, dict] = {}
    blocks = re.split(r"(?=^### \d+\. `)", markdown, flags=re.MULTILINE)
    for block in blocks:
        header = re.match(r"^### \d+\. `([^`]+)`", block)
        if header is None:
            continue
        case_id = header.group(1)

        def required(pattern: str, field_name: str) -> str:
            match = re.search(pattern, block, flags=re.DOTALL)
            if match is None:
                raise ValueError(f"{case_id}: missing {field_name} in proposal.")
            return match.group(1).strip()

        label = required(
            r"\*\*Proposed human label:\*\*\s*\*\*`([^`]+)`\*\*",
            "proposed label",
        )
        rationale = required(
            r"\*\*Human rationale:\*\*\s*(.*?)(?=\n- \*\*|\n### |\Z)",
            "human rationale",
        )
        confidence_match = re.search(r"\*\*Confidence:\*\*\s*([^\r\n]+)", block)
        mappings_match = re.search(
            r"\*\*Evidence mapping\(s\):\*\*\s*([^\r\n]+)", block
        )
        source_flag_match = re.search(
            r"\*\*Reference review flag:\*\*\s*([^\r\n]+)", block
        )
        raw_mappings = mappings_match.group(1).strip() if mappings_match else ""
        mapping_ids = (
            []
            if raw_mappings.casefold() in {"", "none", "n/a"}
            else [
                value.strip().strip("`")
                for value in raw_mappings.split(";")
                if value.strip()
            ]
        )
        flags = []
        if source_flag_match:
            flags.append(source_flag_match.group(1).strip())
        if case_id in attention_ids:
            flags.append("Listed for benchmark-owner attention in the proposal.")
        proposals[case_id] = {
            "proposed_label": label,
            "rationale": rationale,
            "confidence": confidence_match.group(1).strip()
            if confidence_match
            else None,
            "evidence_mapping_ids": mapping_ids,
            "review_flags": flags,
            "requires_owner_attention": bool(flags),
        }
    return proposals, attention_ids


def seed(proposal_path: Path) -> dict[str, int]:
    markdown = proposal_path.read_text(encoding="utf-8")
    proposals, _ = _extract_case_proposals(markdown)
    dataset = load_dataset_by_id(DATASET_ID, DATASET_VERSION)
    dataset_cases = {case["case_id"]: case for case in dataset["cases"]}
    if set(proposals) != set(dataset_cases):
        missing = sorted(set(dataset_cases) - set(proposals))
        unknown = sorted(set(proposals) - set(dataset_cases))
        raise ValueError(
            f"Proposal cases do not match {DATASET_ID}: missing={missing}, unknown={unknown}"
        )

    for case_id, proposal in proposals.items():
        allowed_labels = dataset_cases[case_id].get("review_label_options", [])
        if proposal["proposed_label"] not in allowed_labels:
            raise ValueError(
                f"{case_id}: {proposal['proposed_label']} is not in its category label set."
            )

    source_document = proposal_path.name
    with SessionLocal() as db:
        dataset_version = register_benchmark_dataset(
            db,
            dataset=dataset,
            dataset_id=DATASET_ID,
            dataset_version=DATASET_VERSION,
            actor_user_id=SEED_ACTOR,
        )
        case_versions = {
            case.case_id: case
            for case in db.scalars(
                select(BenchmarkCaseVersionDB).where(
                    BenchmarkCaseVersionDB.dataset_id == DATASET_ID,
                    BenchmarkCaseVersionDB.dataset_version == DATASET_VERSION,
                )
            ).all()
        }
        if set(case_versions) != set(dataset_cases):
            raise RuntimeError("Registered catalogue did not produce all 52 case versions.")

        inserted = 0
        owner_attention = 0
        for case_id, proposal in proposals.items():
            case = dataset_cases[case_id]
            labels = case.get("labels", {})
            provisional_label = (
                labels.get("provisional_reference_label")
                if isinstance(labels, dict)
                else None
            ) or (labels.get("expected_result") if isinstance(labels, dict) else None)
            if proposal["proposed_label"] != provisional_label:
                mismatch = (
                    "Proposed label differs from the catalogue's provisional reference "
                    f"({provisional_label})."
                )
                if mismatch not in proposal["review_flags"]:
                    proposal["review_flags"].append(mismatch)
                    proposal["requires_owner_attention"] = True

            existing = db.scalar(
                select(BenchmarkReviewProposalDB).where(
                    BenchmarkReviewProposalDB.case_version_id
                    == case_versions[case_id].id,
                    BenchmarkReviewProposalDB.source_document == source_document,
                )
            )
            proposal_data = {
                "proposed_label": proposal["proposed_label"],
                "provisional_expected_label": provisional_label,
                "rationale": proposal["rationale"],
                "confidence": proposal["confidence"],
                "evidence_mapping_ids": proposal["evidence_mapping_ids"],
                "review_flags": proposal["review_flags"],
                "requires_owner_attention": proposal["requires_owner_attention"],
            }
            if existing is not None:
                actual_data = {
                    key: getattr(existing, key) for key in proposal_data
                }
                if actual_data != proposal_data:
                    raise ValueError(
                        f"Existing proposal for {case_id} differs; refusing to overwrite it."
                    )
                if existing.status in {"PROPOSED", "NEEDS_OWNER_REVIEW"}:
                    owner_attention += int(existing.requires_owner_attention)
                continue

            db.add(
                BenchmarkReviewProposalDB(
                    id=hashlib.sha256(
                        f"{case_versions[case_id].id}:{source_document}".encode("utf-8")
                    ).hexdigest(),
                    case_version_id=case_versions[case_id].id,
                    source_document=source_document,
                    source_dataset_id=DATASET_ID,
                    source_dataset_version=DATASET_VERSION,
                    status=(
                        "NEEDS_OWNER_REVIEW"
                        if proposal["requires_owner_attention"]
                        else "PROPOSED"
                    ),
                    created_at=datetime.now(UTC),
                    created_by=SEED_ACTOR,
                    **proposal_data,
                )
            )
            inserted += 1
            owner_attention += int(proposal["requires_owner_attention"])

        db.commit()
        return {
            "cases_in_proposal": len(proposals),
            "proposals_inserted": inserted,
            "proposals_already_present": len(proposals) - inserted,
            "needs_owner_attention": owner_attention,
            "catalogue_case_count": dataset_version.case_count,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposal-file",
        type=Path,
        required=True,
        help="Path to the supplied human-review proposal Markdown file.",
    )
    args = parser.parse_args()
    for key, value in seed(args.proposal_file).items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
