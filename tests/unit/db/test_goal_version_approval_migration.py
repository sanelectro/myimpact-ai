from pathlib import Path


def test_version_approval_migration_is_scoped_and_immutable():
    migration = (
        Path(__file__).parents[4]
        / "myimpact-db"
        / "migrations"
        / "V20261108130000__add_goal_version_approvals.sql"
    ).read_text(encoding="utf-8")

    assert "UNIQUE (goal_version_id)" in migration
    assert "FOREIGN KEY (goal_version_id, goal_id)" in migration
    assert "BEFORE UPDATE OR DELETE ON goal_version_approvals" in migration
    assert "reject_goal_history_mutation()" in migration
