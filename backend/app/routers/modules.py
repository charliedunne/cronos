"""Endpoints for managing modules (spec: requirement-store).

Any authenticated user may create, rename, and delete modules; names are
unique across all modules and a module that still contains requirements
cannot be deleted.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.deps import get_current_user, get_db
from app.models import Module, Requirement, User

router = APIRouter(prefix="/modules", tags=["modules"])


class ModuleNameRequest(BaseModel):
    """Payload carrying a module name (used for create and rename)."""

    name: str = Field(min_length=1, max_length=128)


class ModuleOut(BaseModel):
    """Public representation of a module."""

    id: int
    name: str


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


@router.get("", response_model=list[ModuleOut])
def list_modules(
    user: User = Depends(get_current_user), db: DbSession = Depends(get_db)
) -> list[Module]:
    """List all modules.

    @param user The authenticated caller (any role may browse modules).
    @param db Database session for the lookup.
    @return All modules ordered by name.
    """
    return db.query(Module).order_by(Module.name).all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ModuleOut)
def create_module(
    payload: ModuleNameRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Module:
    """Create a new module with a unique name.

    @param payload The requested module name.
    @param user The authenticated caller (any role may create modules).
    @param db Database session for persisting the new module.
    @return The created module.
    @raises HTTPException 409 when the name is already in use.
    """
    module = Module(name=payload.name, created_by=user.id)
    db.add(module)
    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on modules.name rejected the insert.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A module with this name already exists",
        )
    db.refresh(module)
    return module


@router.patch("/{module_id}", response_model=ModuleOut)
def rename_module(
    module_id: int,
    payload: ModuleNameRequest,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Module:
    """Rename a module.

    @param module_id The id of the module to rename.
    @param payload The new name.
    @param user The authenticated caller (any role may rename modules).
    @param db Database session for persisting the change.
    @return The updated module.
    @raises HTTPException 404 when no such module exists.
    @raises HTTPException 409 when the new name is already in use.
    """
    module = _get_module_or_404(db, module_id)
    module.name = payload.name
    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on modules.name rejected the rename.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A module with this name already exists",
        )
    db.refresh(module)
    return module


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(
    module_id: int,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    """Delete a module that contains no requirements.

    @param module_id The id of the module to delete.
    @param user The authenticated caller (any role may delete modules).
    @param db Database session for persisting the deletion.
    @raises HTTPException 404 when no such module exists.
    @raises HTTPException 409 when the module still contains requirements.
    """
    module = _get_module_or_404(db, module_id)
    has_requirements = (
        db.query(Requirement.id)
        .filter(Requirement.module_id == module.id)
        .first()
        is not None
    )
    if has_requirements:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Module still contains requirements",
        )
    db.delete(module)
    db.commit()
