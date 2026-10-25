import argparse
import asyncio
import json

from app.evaluation.m66 import load_dataset, run_evaluation
from app.services.llm.factory import create_llm_service


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the M66 criterion-assessment evaluation dataset."
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="Override the repeat count declared in the evaluation dataset.",
    )
    arguments = parser.parse_args()

    report = asyncio.run(
        run_evaluation(
            create_llm_service(),
            load_dataset(),
            repeats=arguments.repeats,
        )
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
