"""Shared FastAPI dependencies for the Cronos API."""

from typing import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from app.db import SessionLocal
from app.models import Session as SessionModel
from app.models import User

#: Name of the httpOnly cookie carrying the session token.
SESSION_COOKIE_NAME = "cronos_session"


def _unauthorized() -> HTTPException:
    """Build the standard 401 response for missing/invalid sessions."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )


def get_db() -> Generator[DbSession, None, None]:
    """Yield a database session bound to the request lifecycle.

    @return A generator yielding one SQLAlchemy session per request; the
        session is always closed when the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_session(
    request: Request, db: DbSession = Depends(get_db)
) -> SessionModel:
    """Validate the session cookie and return the active session row.

    @param request The incoming FastAPI request (source of the cookie).
    @param db Database session used for the lookup.
    @return The validated :class:`Session` row (its ``user`` is the caller).
    @raises HTTPException 401 when the cookie is missing, the session does
        not exist or has been revoked, or the account is disabled.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise _unauthorized()
    sess = db.get(SessionModel, token)
    if sess is None or sess.revoked_at is not None:
        raise _unauthorized()
    if not sess.user.is_active:
        # A disabled account loses access immediately (spec: user-auth).
        raise _unauthorized()
    return sess


def get_current_user(
    request: Request, db: DbSession = Depends(get_db)
) -> User:
    """Return the authenticated user for the current request.

    @param request The incoming FastAPI request (source of the cookie).
    @param db Database session used for the lookup.
    @return The :class:`User` holding a valid, non-revoked session.
    @raises HTTPException 401 when no valid session exists.
    """
    return get_current_session(request, db).user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Return the caller only if it is an administrator.

    @param user The authenticated caller (see :func:`get_current_user`).
    @return The :class:`User` when its ``is_admin`` flag is set.
    @raises HTTPException 403 when the caller is not an administrator.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user
