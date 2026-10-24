import shutil
import sys
from pathlib import Path

from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models.user import UserDB
from app.db.session import SessionLocal


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: cleanup_playwright_user.py <test-email>")

    email = sys.argv[1].strip().lower()
    if not email.startswith("playwright-m64-") or not email.endswith("@example.com"):
        raise SystemExit("Refusing to clean an account outside the M6.4 test namespace.")

    with SessionLocal() as session:
        user_id = session.scalar(select(UserDB.id).where(UserDB.email == email))
        if user_id is None:
            return
        session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()

    storage_root = (Path(__file__).resolve().parents[1] / "storage/documents").resolve()
    user_storage = (storage_root / user_id).resolve()
    if user_storage.parent != storage_root:
        raise RuntimeError("Refusing to remove storage outside the test user's directory.")
    if user_storage.exists():
        shutil.rmtree(user_storage)


if __name__ == "__main__":
    main()
