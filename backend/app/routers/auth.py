"""Authentication endpoints: login, logout, and current-user lookup."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.deps import SESSION_COOKIE_NAME, get_current_session, get_current_user, get_db
from app.models import Session as SessionModel
from app.models import User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

#: Lifetime of the session cookie; server-side validity ends at logout.
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

#: Pre-computed hash used to equalize response timing when the username is
#: unknown, so login failures do not reveal whether a user exists.
_DUMMY_HASH = hash_password("timing-equalization-dummy")


class LoginRequest(BaseModel):
    """Credentials submitted at login."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    """Public representation of a user (never exposes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    is_active: bool


def _invalid_credentials() -> HTTPException:
    """Build the generic 401 returned for every login failure.

    The detail deliberately does not say whether the username or the
    password was wrong (spec: user-auth / invalid credentials).
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
    )


@router.post("/login")
def login(
    payload: LoginRequest, response: Response, db: DbSession = Depends(get_db)
) -> UserOut:
    """Authenticate with username and password; set the session cookie.

    @param payload The submitted credentials.
    @param response Response object used to set the session cookie.
    @param db Database session for user lookup and session creation.
    @return The authenticated user's public profile.
    @raises HTTPException 401 with a generic detail on any failure.
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None:
        # Burn comparable CPU time as a real verification.
        verify_password(_DUMMY_HASH, payload.password)
        raise _invalid_credentials()
    if not verify_password(user.password_hash, payload.password):
        raise _invalid_credentials()
    if not user.is_active:
        # Disabled accounts cannot log in (spec: user-auth).
        raise _invalid_credentials()

    token = secrets.token_urlsafe(32)
    db.add(SessionModel(token=token, user_id=user.id))
    db.commit()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        max_age=COOKIE_MAX_AGE_SECONDS,
    )
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(
    response: Response,
    session: SessionModel = Depends(get_current_session),
    db: DbSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke the caller's current session and clear the cookie.

    @param response Response object used to clear the session cookie.
    @param session The validated session row being revoked.
    @param db Database session for persisting the revocation.
    @return A short confirmation payload.
    """
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()

    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "logged out"}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Return the profile of the currently authenticated user.

    @param user The caller resolved from the session cookie.
    @return The user's public profile (401 when unauthenticated).
    """
    return UserOut.model_validate(user)
