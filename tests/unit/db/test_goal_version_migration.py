from pathlib import Path


def test_legacy_goal_backfill_creates_only_marked_version_one_records():
    migration = (
        Path(__file__).parents[4]
        / "myimpact-db"
        / "migrations"
        / "V20261108080000__add_goal_versions_and_validation_history.sql"
    ).read_text(encoding="utf-8")
    backfill = migration.split("INSERT INTO goal_versions", 1)[1].split(
        "CREATE TABLE goal_validation_runs", 1
    )[0]

    assert "'LEGACY'" in backfill
    assert "    1," in backfill
    assert "goal.updated_at" in backfill
    assert "'criterion_versions'" in backfill
    assert "'status'" not in backfill
    assert "INSERT INTO goal_validation_runs" not in migration


def test_goal_version_and_validation_rows_are_immutable_in_database():
    migration = (
        Path(__file__).parents[4]
        / "myimpact-db"
        / "migrations"
        / "V20261108080000__add_goal_versions_and_validation_history.sql"
    ).read_text(encoding="utf-8")

    assert "BEFORE UPDATE OR DELETE ON goal_versions" in migration
    assert "BEFORE UPDATE OR DELETE ON goal_validation_runs" in migration
    assert "pg_trigger_depth() <= 1" in migration
    assert "FOREIGN KEY (goal_version_id, goal_id)" in migration
