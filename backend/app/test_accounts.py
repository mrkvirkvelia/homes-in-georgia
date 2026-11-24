"""Test server (TEST_MODE): demo data on first run + the shared test password on every sign-in account.
`python -m app.test_accounts` (deploy/test-push.sh runs it after each deploy; safe to repeat).

Accounts (password: TEST_PASSWORD from .env.test): irakli (superadmin), david (superadmin), nino (operator),
georgiy / levan (agents) — the people of app.seed_demo."""
import os
import sys

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import User
from app.services import users


def main() -> int:
    if not settings.TEST_MODE:
        print("refused: TEST_MODE is off (this is not the test server)")
        return 1
    pw = os.environ.get("TEST_PASSWORD", "")
    if len(pw) < 8:
        print("TEST_PASSWORD (8+ chars) is not set")
        return 1
    from app import seed_demo
    try:
        seed_demo.seed()  # skips when the demo people exist
    except Exception as e:  # noqa: BLE001 — a demo object the newer publish rules refuse; the people are in already
        print(f"demo data: partly ({e})")
    db = SessionLocal()
    if not db.scalar(select(User).where(User.login == "irakli")):
        db.add(User(name="Иракли", role="superadmin", login="irakli"))
        db.flush()
    n = 0
    for u in db.scalars(select(User).where(User.login.is_not(None))):
        u.password_hash, u.is_active = users.hash_password(pw), True
        n += 1
    db.commit()
    print(f"test accounts ready: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
