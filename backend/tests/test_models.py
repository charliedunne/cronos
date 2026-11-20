"""Tests for the user and session ORM models against the dev database."""

import uuid

from app.db import SessionLocal
from app.models import Session, User
from app.security import hash_password


def test_insert_user_and_session_rows() -> None:
    """User and session rows can be inserted directly via the ORM.

    Uses a unique username so reruns never collide; both rows are removed
    again at the end to keep the dev database clean.
    """
    username = f"test-{uuid.uuid4().hex[:12]}"
    token = f"test-token-{uuid.uuid4().hex}"

    with SessionLocal() as session:
        user = User(username=username, password_hash=hash_password("secret"))
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.id is not None
        # Column defaults applied.
        assert user.is_admin is False
        assert user.is_active is True
        assert user.created_at is not None

        sess = Session(token=token, user_id=user.id)
        session.add(sess)
        session.commit()
        session.refresh(sess)

        assert sess.revoked_at is None
        assert sess.user.username == username

        # Cleanup: remove the test rows (session first — FK to users).
        session.delete(sess)
        session.delete(user)
        session.commit()
