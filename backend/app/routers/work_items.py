"""Endpoints for work items and their editing locks.

Covers the requirement-store spec (creation, browsing, deletion) and the
editing-locks spec (lock/unlock, holder-only modification, admin
force-release), generalized to typed work items (design.md D6). Modifying or
deleting a work item requires holding its lock; lock exclusivity itself is
guaranteed by the database primary key on ``locks.item_id`` (design.md D5).
Per-type attribute conformance is enforced via the validation service.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.deps import get_current_user, get_db, require_admin
from app.models import Lock, Module, User, WorkItem, WorkItemType
from app.services.validation import AttributeValidationError, validate_values

router = APIRouter(tags=["work-items"])


class WorkItemCreateRequest(BaseModel):
    """Payload for creating a work item inside a module."""

    type_id: int
    title: str = Field(min_length=1, max_length=255)
    attributes: dict[str, object] = {}

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        """Reject whitespace-only titles (spec: non-empty title)."""
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class WorkItemUpdateRequest(BaseModel):
    """Payload for updating a work item (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    attributes: dict[str, object] | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        """Reject whitespace-only titles (spec: non-empty title)."""
        if value is not None and not value.strip():
            raise ValueError("title must not be blank")
        return value


class WorkItemTypeOut(BaseModel):
    """Public representation of a work item's type."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    id_prefix: str
    is_builtin: bool


class WorkItemOut(BaseModel):
    """Public representation of a work item including type and lock state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    title: str
    type: WorkItemTypeOut
    attributes: dict[str, object]
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


def _get_work_item_or_404(db: DbSession, work_item_id: int) -> WorkItem:
    """Fetch a work item by id or raise a 404.

    @param db Database session used for the lookup.
    @param work_item_id The id of the work item to fetch.
    @return The matching :class:`WorkItem` row.
    @raises HTTPException 404 when no such work item exists.
    """
    work_item = db.get(WorkItem, work_item_id)
    if work_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found"
        )
    return work_item


def _require_lock_held(work_item: WorkItem, user: User) -> None:
    """Assert that the caller holds the work item's lock.

    @param work_item The work item about to be modified or deleted.
    @param user The authenticated caller.
    @raises HTTPException 409 when the work item is unlocked or locked by
        someone else.
    """
    if work_item.lock is None or work_item.lock.holder_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Work item must be locked by the caller before modification",
        )


def _validation_error(exc: AttributeValidationError) -> HTTPException:
    """Translate a validation failure into the standard 422 contract.

    @param exc The raised :class:`AttributeValidationError`.
    @return An HTTPException carrying every problem in ``detail["errors"]``.
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"errors": exc.errors},
    )


@router.post(
    "/modules/{module_id}/work-items",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkItemOut,
)
def create_work_item(
    module_id: int,
    payload: WorkItemCreateRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> WorkItem:
    """Create a work item of the chosen type; the system assigns its id.

    The type is set at creation and immutable afterwards (spec:
    requirement-store). Attribute values are validated against the type's
    definitions before anything is persisted.

    @param module_id The id of the module to create the work item in.
    @param payload The chosen type, a non-empty title, and attribute values.
    @param user The authenticated caller (any role may create work items).
    @param db Database session for persisting the new work item.
    @return The created work item with its assigned identifier.
    @raises HTTPException 404 when no such module or type exists.
    @raises HTTPException 422 when attribute values do not conform.
    """
    module = _get_module_or_404(db, module_id)
    work_type = db.get(WorkItemType, payload.type_id)
    if work_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Work item type not found"
        )
    try:
        values = validate_values(work_type, payload.attributes)
    except AttributeValidationError as exc:
        raise _validation_error(exc) from exc

    work_item = WorkItem(
        module_id=module.id,
        type_id=work_type.id,
        title=payload.title,
        attributes=values,
        created_by=user.id,
    )
    db.add(work_item)
    db.commit()
    db.refresh(work_item)
    return work_item


@router.get("/modules/{module_id}/work-items", response_model=list[WorkItemOut])
def list_work_items(
    module_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> list[WorkItem]:
    """List a module's work items with type, attribute values, and locks.

    @param module_id The id of the module to browse.
    @param user The authenticated caller (any role may browse).
    @param db Database session for the lookup.
    @return The module's work items ordered by identifier sequence.
    @raises HTTPException 404 when no such module exists.
    """
    module = _get_module_or_404(db, module_id)
    return (
        db.query(WorkItem)
        .filter(WorkItem.module_id == module.id)
        .order_by(WorkItem.req_no)
        .all()
    )


@router.patch("/work-items/{work_item_id}", response_model=WorkItemOut)
def update_work_item(
    work_item_id: int,
    payload: WorkItemUpdateRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> WorkItem:
    """Update a locked work item's title and/or attribute values.

    Only the current lock holder may modify a work item; the lock is
    retained after the update (spec: editing-locks). Supplied values are
    merged over the stored ones and the complete map must conform to the
    type's definitions.

    @param work_item_id The id of the work item to update.
    @param payload The changes to apply (omitted fields are untouched).
    @param user The authenticated caller.
    @param db Database session for persisting the change.
    @return The updated work item.
    @raises HTTPException 404 when no such work item exists.
    @raises HTTPException 409 when the caller does not hold the lock.
    @raises HTTPException 422 when attribute values do not conform.
    """
    work_item = _get_work_item_or_404(db, work_item_id)
    _require_lock_held(work_item, user)

    if payload.title is not None:
        work_item.title = payload.title
    if payload.attributes is not None:
        merged = {**work_item.attributes, **payload.attributes}
        try:
            work_item.attributes = validate_values(work_item.type, merged)
        except AttributeValidationError as exc:
            raise _validation_error(exc) from exc
    work_item.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(work_item)
    return work_item


@router.delete(
    "/work-items/{work_item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_work_item(
    work_item_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    """Delete a work item; only the lock holder may do so.

    The identifier is never reused because it derives from a monotonically
    advancing sequence (design.md D1).

    @param work_item_id The id of the work item to delete.
    @param user The authenticated caller.
    @param db Database session for persisting the deletion.
    @raises HTTPException 404 when no such work item exists.
    @raises HTTPException 409 when the caller does not hold the lock.
    """
    work_item = _get_work_item_or_404(db, work_item_id)
    _require_lock_held(work_item, user)

    # Remove the lock explicitly (the FK cascade is a backstop).
    if work_item.lock is not None:
        db.delete(work_item.lock)
    db.delete(work_item)
    db.commit()


@router.post("/work-items/{work_item_id}/lock", response_model=WorkItemOut)
def lock_work_item(
    work_item_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> WorkItem:
    """Acquire the exclusive editing lock on a work item.

    The INSERT either succeeds or fails with a unique violation on
    ``locks.item_id``; there is no application-level check-then-set
    (design.md D5).

    @param work_item_id The id of the work item to lock.
    @param user The authenticated caller.
    @param db Database session for persisting the lock.
    @return The work item with its new lock state.
    @raises HTTPException 404 when no such work item exists.
    @raises HTTPException 409 when the work item is already locked.
    """
    work_item = _get_work_item_or_404(db, work_item_id)
    db.add(Lock(item_id=work_item.id, holder_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        # Another user holds the lock (or locked it concurrently).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Work item is already locked",
        )
    db.refresh(work_item)
    return work_item


@router.delete(
    "/work-items/{work_item_id}/lock", status_code=status.HTTP_204_NO_CONTENT
)
def unlock_work_item(
    work_item_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    """Release the lock on a work item; only the holder may do so.

    @param work_item_id The id of the work item to unlock.
    @param user The authenticated caller.
    @param db Database session for persisting the release.
    @raises HTTPException 404 when no such work item exists.
    @raises HTTPException 409 when the work item is not locked.
    @raises HTTPException 403 when the caller is not the lock holder.
    """
    work_item = _get_work_item_or_404(db, work_item_id)
    if work_item.lock is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Work item is not locked"
        )
    if work_item.lock.holder_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the lock holder can release this lock",
        )
    db.delete(work_item.lock)
    db.commit()


@router.post(
    "/work-items/{work_item_id}/force-release", response_model=WorkItemOut
)
def force_release_lock(
    work_item_id: int,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> WorkItem:
    """Force-release a lock regardless of its holder (admin only).

    @param work_item_id The id of the locked work item.
    @param admin The administrator performing the action (enforced by
        :func:`require_admin`).
    @param db Database session for persisting the release.
    @return The work item with its (now empty) lock state.
    @raises HTTPException 403 when the caller is not an administrator.
    @raises HTTPException 404 when no such work item exists.
    @raises HTTPException 409 when the work item is not locked.
    """
    work_item = _get_work_item_or_404(db, work_item_id)
    if work_item.lock is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Work item is not locked"
        )
    db.delete(work_item.lock)
    db.commit()
    db.refresh(work_item)
    return work_item
