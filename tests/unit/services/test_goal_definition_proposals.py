import pytest
from pydantic import ValidationError

from app.services.goal_definition_proposals import GoalProposalChanges, _equivalent_text


@pytest.mark.parametrize(
    ("original", "proposed", "equivalent"),
    [
        ("Original goal", "  Original   goal ", True),
        ("Original goal", "Original Goal", False),
        ("Original goal", "Original goal!", False),
        ("- First\n- Second", "- First\n  - Second", False),
        ("a  b", "a b", True),
        ("A **bold** goal", "A  **bold** goal", False),
        ("Original goal", "    Original goal", False),
        ("Original goal", "\tOriginal goal", False),
        ("Original", None, False),
        (None, None, True),
    ],
)
def test_plain_text_whitespace_comparison_is_conservative(original, proposed, equivalent):
    assert _equivalent_text(original, proposed) is equivalent


@pytest.mark.parametrize(
    "values",
    [{}, {"title": None}, {"title": "   "}, {"goal_level": "ANNUAL"}],
)
def test_text_proposal_rejects_empty_or_unsupported_changes(values):
    with pytest.raises(ValidationError):
        GoalProposalChanges(**values)


def test_text_proposal_accepts_clearing_description():
    changes = GoalProposalChanges(description=None)
    assert changes.model_dump(exclude_unset=True) == {"description": None}


def test_proposal_dates_are_serialized_and_invalid_dates_rejected():
    changes = GoalProposalChanges(start_date="2026-03-01", end_date=None)
    assert changes.model_dump(mode="json", exclude_unset=True) == {
        "start_date": "2026-03-01",
        "end_date": None,
    }
    with pytest.raises(ValidationError):
        GoalProposalChanges(start_date="not-a-date")
