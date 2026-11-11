import pytest
from pydantic import ValidationError

from app.services.goal_definition_proposals import GoalProposalTextChanges, _equivalent_text


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
        GoalProposalTextChanges(**values)


def test_text_proposal_accepts_clearing_description():
    changes = GoalProposalTextChanges(description=None)
    assert changes.model_dump(exclude_unset=True) == {"description": None}
