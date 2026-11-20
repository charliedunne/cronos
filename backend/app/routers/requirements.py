"""Endpoints for requirements and their editing locks.

Covers the requirement-store spec (creation, browsing, deletion) and the
editing-locks spec (lock/unlock, holder-only modification, admin
force-release). Modifying or deleting a requirement requires holding its
lock; lock exclusivity itself is guaranteed by the database primary key
on ``locks.requirement_id`` (design.md decision D5).
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.deps import get_current_user, get_db, require_admin
from app.models import Lock, Module, Requirement, User

router = APIRouter(tags=["requirements"])

#: Allowed values for the fixed attribute set (spec: requirement-store).
RequirementStatus = Literal["draft", "in-review", "approved", "deprecated"]
RequirementPriority = Literal["low", "medium", "high"]


class RequirementCreateRequest(BaseModel):
    """Payload for creating a requirement inside a module."""

    title: str = Field(min_length=1, max_length=255)
    text: str = ""
    status: RequirementStatus = "draft"
    priority: RequirementPriority = "medium"

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        """Reject whitespace-only titles (spec: non-empty title)."""
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class RequirementUpdateRequest(BaseModel):
    """Payload for updating a requirement (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    text: str | None = None
    status: RequirementStatus | None = None
    priority: RequirementPriority | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        """Reject whitespace-only titles (spec: non-empty title)."""
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value


class RequirementOut(BaseModel):
    """Public representation of a requirement including lock state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    title: str
    text: str
    status: str
    priority: str
    locked_by: str | None


def _get_module_or_404(db: DbSession, module_id: int) -> Module:
    """Fetch a module by id or raise a 404.

    @param db Database session used for the lookup.
    @param module_id The id of the module to fetch.
    @return The matching :class:`Module` row.
    @raises HTTPException 404 when no such module exists.
    """
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module not found"
        )
    return module


def _get_requirement_or_404(db: DbSession, requirement_id: int) -> Requirement:
    """Fetch a requirement by id or raise a 404.

    @param db Database session used for the lookup.
    @param requirement_id The id of the requirement to fetch.
    @return The matching :class:`Requirement` row.
    @raises HTTPException 404 when no such requirement exists.
    """
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found"
        )
    return requirement


def _require_lock_held(requirement: Requirement, user: User) -> None:
    """Assert that the caller holds the requirement's lock.

    @param requirement The requirement about to be modified or deleted.
    @param user The authenticated caller.
    @raises HTTPException 409 when the requirement is unlocked or locked
        by someone else.
    """
    if requirement.lock is None or requirement.lock.holder_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requirement must be locked by the caller before modification",
        )


@router.post(
    "/modules/{module_id}/requirements",
    status_code=status.HTTP_201_CREATED,
    response_model=RequirementOut,
)
def create_requirement(
    module_id: int,
    payload: RequirementCreateRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Requirement:
    """Create a requirement in a module; the system assigns its identifier.

    @param module_id The id of the module to create the requirement in.
    @param payload Title, text, and optional status/priority overrides.
    @param user The authenticated caller (any role may create requirements).
    @param db Database session for persisting the new requirement.
    @return The created requirement with its assigned identifier.
    @raises HTTPException 404 when no such module exists.
    """
    module = _get_module_or_404(db, module_id)
    requirement = Requirement(
        module_id=module.id,
        title=payload.title,
        text=payload.text,
        status=payload.status,
        priority=payload.priority,
        created_by=user.id,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


@router.get(
    "/modules/{module_id}/requirements", response_model=list[RequirementOut]
)
def list_requirements(
    module_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[Requirement]:
    """List the requirements of a module with attributes and lock state.

    @param module_id The id of the module to browse.
    @param user The authenticated caller (any role may browse).
    @param db Database session for the lookup.
    @return The module's requirements ordered by identifier.
    @raises HTTPException 404 when no such module exists.
    """
    module = _get_module_or_404(db, module_id)
    return (
        db.query(Requirement)
        .filter(Requirement.module_id == module.id)
        .order_by(Requirement.req_no)
        .all()
    )


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut)
def update_requirement(
    requirement_id: int,
    payload: RequirementUpdateRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Requirement:
    """Update the attributes of a locked requirement.

    Only the current lock holder may modify a requirement; the lock is
    retained after the update (spec: editing-locks).

    @param requirement_id The id of the requirement to update.
    @param payload The attribute changes to apply (omitted fields are untouched).
    @param user The authenticated caller.
    @param db Database session for persisting the change.
    @return The updated requirement.
    @raises HTTPException 404 when no such requirement exists.
    @raises HTTPException 409 when the caller does not hold the lock.
    """
    requirement = _get_requirement_or_404(db, requirement_id)
    _require_lock_held(requirement, user)

    if payload.title is not None:
        requirement.title = payload.title
    if payload.text is not None:
        requirement.text = payload.text
    if payload.status is not None:
        requirement.status = payload.status
    if payload.priority is not None:
        requirement.priority = payload.priority
    requirement.updated_at = func.now()

    db.commit()
    db.refresh(requirement)
    return requirement


@router.delete("/requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requirement(
    requirement_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    """Delete a requirement; only the lock holder may do so.

    The identifier is never reused because it derives from a monotonically
    advancing sequence (design.md decision D4).

    @param requirement_id The id of the requirement to delete.
    @param user The authenticated caller.
    @param db Database session for persisting the deletion.
    @raises HTTPException 404 when no such requirement exists.
    @raises HTTPException 409 when the caller does not hold the lock.
    """
    requirement = _get_requirement_or_404(db, requirement_id)
    _require_lock_held(requirement, user)

    # Remove the lock explicitly (the FK cascade is a backstop).
    if requirement.lock is not None:
        db.delete(requirement.lock)
    db.delete(requirement)
    db.commit()


@router.post("/requirements/{requirement_id}/lock", response_model=RequirementOut)
def lock_requirement(
    requirement_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Requirement:
    """Acquire the exclusive editing lock on a requirement.

    The INSERT either succeeds or fails with a unique violation on
    ``locks.requirement_id``; there is no application-level check-then-set
    (design.md decision D5).

    @param requirement_id The id of the requirement to lock.
    @param user The authenticated caller.
    @param db Database session for persisting the lock.
    @return The requirement with its new lock state.
    @raises HTTPException 404 when no such requirement exists.
    @raises HTTPException 409 when the requirement is already locked.
    """
    requirement = _get_requirement_or_404(db, requirement_id)
    db.add(Lock(requirement_id=requirement.id, holder_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        # Another user holds the lock (or locked it concurrently).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requirement is already locked",
        )
    db.refresh(requirement)
    return requirement


@router.delete(
    "/requirements/{requirement_id}/lock", status_code=status.HTTP_204_NO_CONTENT
)
def unlock_requirement(
    requirement_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    """Release the lock on a requirement; only the holder may do so.

    @param requirement_id The id of the requirement to unlock.
    @param user The authenticated caller.
    @param db Database session for persisting the release.
    @raises HTTPException 404 when no such requirement exists.
    @raises HTTPException 409 when the requirement is not locked.
    @raises HTTPException 403 when the caller is not the lock holder.
    """
    requirement = _get_requirement_or_404(db, requirement_id)
    if requirement.lock is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Requirement is not locked"
        )
    if requirement.lock.holder_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the lock holder can release this lock",
        )
    db.delete(requirement.lock)
    db.commit()


@router.post(
    "/requirements/{requirement_id}/force-release", response_model=RequirementOut
)
def force_release_lock(
    requirement_id: int,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> Requirement:
    """Force-release a lock regardless of its holder (admin only).

    @param requirement_id The id of the locked requirement.
    @param admin The administrator performing the action (enforced by
        :func:`require_admin`).
    @param db Database session for persisting the release.
    @return The requirement with its (now empty) lock state.
    @raises HTTPException 403 when the caller is not an administrator.
    @raises HTTPException 404 when no such requirement exists.
    @raises HTTPException 409 when the requirement is not locked.
    """
    requirement = _get_requirement_or_404(db, requirement_id)
    if requirement.lock is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Requirement is not locked"
        )
    db.delete(requirement.lock)
    db.commit()
    db.refresh(requirement)
    return requirement
