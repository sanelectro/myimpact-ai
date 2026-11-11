from datetime import date

import pytest

from app.services.goal_hierarchy import _date_conflicts


@pytest.mark.parametrize(
    ("parent_start", "parent_end", "child_start", "child_end", "expected"),
    [
        ("2026-01-01", "2026-12-31", "2026-01-01", "2026-12-31", []),
        ("2026-01-01", "2026-12-31", None, None, []),
        (None, None, "2025-01-01", "2027-01-01", []),
        ("2026-01-01", None, "2025-12-31", None, [("start_date", "start_date")]),
        (None, "2026-12-31", None, "2027-01-01", [("end_date", "end_date")]),
        ("2026-01-01", None, None, "2025-12-31", [("end_date", "start_date")]),
        (None, "2026-12-31", "2027-01-01", None, [("start_date", "end_date")]),
        (
            "2026-01-01", "2026-12-31", "2025-01-01", "2027-01-01",
            [("start_date", "start_date"), ("end_date", "end_date")],
        ),
    ],
)
def test_known_parent_and_child_boundaries(parent_start, parent_end, child_start, child_end, expected):
    def parse(value):
        return date.fromisoformat(value) if value is not None else None

    conflicts = _date_conflicts(
        "parent", parse(parent_start), parse(parent_end), "child", parse(child_start), parse(child_end)
    )
    assert [(item.child_field, item.parent_field) for item in conflicts] == expected
    assert all(item.parent_goal_id == "parent" and item.child_goal_id == "child" for item in conflicts)
