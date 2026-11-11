import pytest
from pydantic import ValidationError

from app.services.goal_definition_proposals import (
    GoalProposalChanges,
    _equivalent_definition,
    _equivalent_text,
)


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
    [{}, {"title": None}, {"title": "   "}, {"structured_fields": None}, {"goal_level": "ANNUAL"}],
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


def test_nested_proposal_comparison_preserves_types_order_and_formatting():
    assert _equivalent_definition({"outcome": "Improve quality"}, {"outcome": "Improve  quality"})
    assert not _equivalent_definition({"target": True}, {"target": 1})
    assert not _equivalent_definition(["First", "Second"], ["Second", "First"])
    assert not _equivalent_definition({"outcome": "- First"}, {"outcome": " - First"})
    assert not _equivalent_definition({"outcome": "Value"}, {"outcome": "Value", "target": None})


def test_structured_proposal_preserves_only_explicit_patch_fields():
    changes = GoalProposalChanges(structured_fields={"outcome": "  Improve reliability  "})
    assert changes.model_dump(mode="json", exclude_unset=True) == {
        "structured_fields": {"outcome": "Improve reliability"}
    }


@pytest.mark.parametrize(
    "updates",
    [
        None,
        [],
        [{"milestone_id": " "}],
        [{"milestone_id": "one"}],
        [{"milestone_id": "one", "title": None}],
        [{"milestone_id": "one", "title": "   "}],
        [{"milestone_id": "one", "status": "completed"}],
        [{"milestone_id": "one", "source": "manual"}],
        [{"milestone_id": "one", "title": "A"}, {"milestone_id": "one", "title": "B"}],
    ],
)
def test_milestone_proposal_rejects_invalid_updates(updates):
    with pytest.raises(ValidationError):
        GoalProposalChanges(milestone_updates=updates)


def test_milestone_proposal_preserves_explicit_fields_and_serializes_dates():
    changes = GoalProposalChanges(milestone_updates=[{
        "milestone_id": "one",
        "title": "  Revised title  ",
        "description": None,
        "due_date": "2026-03-01",
    }])
    assert changes.model_dump(mode="json", exclude_unset=True) == {
        "milestone_updates": [{
            "milestone_id": "one",
            "title": "Revised title",
            "description": None,
            "due_date": "2026-03-01",
        }]
    }
