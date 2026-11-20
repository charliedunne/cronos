"""Administrative endpoints for managing user accounts (admin-only)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.deps import get_db, require_admin
from app.models import User
from app.routers.auth import UserOut
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserCreateRequest(BaseModel):
    """Payload for creating a new user account."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _get_user_or_404(db: DbSession, user_id: int) -> User:
    """Fetch a user by id or raise a 404.

    @param db Database session used for the lookup.
    @param user_id The id of the user to fetch.
    @return The matching :class:`User` row.
    @raises HTTPException 404 when no such user exists.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def create_user(
    payload: UserCreateRequest,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> User:
    """Create a new (non-admin) user account.

    @param payload The requested username and password.
    @param admin The administrator performing the action (enforced by
        :func:`require_admin`).
    @param db Database session for persisting the new account.
    @return The created user's public profile.
    @raises HTTPException 409 when the username is already taken.
    """
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on users.username rejected the insert.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username already exists",
        )
    db.refresh(user)
    return user


@router.post("/{user_id}/disable", response_model=UserOut)
def disable_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> User:
    """Disable an account.

    Disabling blocks login immediately and also invalidates the account's
    existing sessions (the session-validation dependency rejects disabled
    accounts).

    @param user_id The id of the account to disable.
    @param admin The administrator performing the action (enforced by
        :func:`require_admin`).
    @param db Database session for persisting the change.
    @return The updated user's public profile.
    @raises HTTPException 404 when no such user exists.
    """
    user = _get_user_or_404(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/enable", response_model=UserOut)
def enable_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> User:
    """Re-enable a previously disabled account.

    @param user_id The id of the account to re-enable.
    @param admin The administrator performing the action (enforced by
        :func:`require_admin`).
    @param db Database session for persisting the change.
    @return The updated user's public profile.
    @raises HTTPException 404 when no such user exists.
    """
    user = _get_user_or_404(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user
