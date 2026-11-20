"""Endpoints for the work-item type registry (spec: work-items).

Administrators create, modify, and delete work-item types and their
attribute definitions; listing is open to any authenticated user because
the element-creation UI needs the type catalog to render its dynamic form.
Reserved system keys (``title`` / ``id``) are rejected as attribute keys,
and a built-in type can never be deleted or renamed (design.md D3/D4).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.deps import get_current_user, get_db, require_admin
from app.models import AttributeDefinition, User, WorkItem, WorkItemType
from app.services.validation import (
    ALLOWED_DATA_TYPES,
    RESERVED_KEYS,
    check_value,
)

router = APIRouter(prefix="/work-item-types", tags=["work-item-types"])


class AttributeDefinitionIn(BaseModel):
    """Payload for creating or updating an attribute definition."""

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    data_type: str = Field(min_length=1, max_length=16)
    options: list[str] | None = None
    required: bool = False
    default_value: object | None = None
    #: Display order within the type; MUST be unique per type (spec:
    #: work-items). ``None`` means "assign automatically": on create the
    #: attribute is appended after the existing ones, on update the stored
    #: position is left unchanged.
    position: int | None = None

    @field_validator("key")
    @classmethod
    def _key_not_reserved(cls, value: str) -> str:
        """Reject the reserved system keys (spec: work-items)."""
        if value in RESERVED_KEYS:
            raise ValueError(f"'{value}' is a reserved attribute key")
        return value

    @field_validator("data_type")
    @classmethod
    def _valid_data_type(cls, value: str) -> str:
        """Reject data types outside the allowed set (spec: work-items)."""
        if value not in ALLOWED_DATA_TYPES:
            raise ValueError(
                f"data_type must be one of: {', '.join(ALLOWED_DATA_TYPES)}"
            )
        return value

    @model_validator(mode="after")
    def _enum_needs_options(self) -> "AttributeDefinitionIn":
        """An enum attribute must declare its allowed values (spec).

        A model-level check is used because a field validator for
        ``options`` would not run when the key is omitted from the payload
        (pydantic does not validate default values by default), which would
        silently persist an enum definition without options.
        """
        if self.data_type == "enum" and not self.options:
            raise ValueError("an enum attribute requires a non-empty options list")
        return self


class AttributeDefinitionOut(AttributeDefinitionIn):
    """Public representation of an attribute definition, including its id.

    The id is required by clients to address the per-attribute update and
    delete endpoints (``PATCH/DELETE /{type_id}/attributes/{attribute_id}`).
    """

    id: int


class WorkItemTypeCreate(BaseModel):
    """Payload for creating a work-item type with its initial attributes."""

    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    id_prefix: str = Field(min_length=1, max_length=16)
    attributes: list[AttributeDefinitionIn] = []


class WorkItemTypeUpdate(BaseModel):
    """Payload for modifying a work-item type (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    id_prefix: str | None = Field(default=None, min_length=1, max_length=16)


class WorkItemTypeOut(BaseModel):
    """Public representation of a type including its attribute definitions."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    id_prefix: str
    is_builtin: bool
    attributes: list[AttributeDefinitionOut]


def _get_type_or_404(db: DbSession, type_id: int) -> WorkItemType:
    """Fetch a work-item type by id or raise a 404.

    @param db Database session used for the lookup.
    @param type_id The id of the type to fetch.
    @return The matching :class:`WorkItemType` row.
    @raises HTTPException 404 when no such type exists.
    """
    work_type = db.get(WorkItemType, type_id)
    if work_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Work item type not found"
        )
    return work_type


def _get_attribute_or_404(
    db: DbSession, work_type: WorkItemType, attribute_id: int
) -> AttributeDefinition:
    """Fetch an attribute definition of a type or raise a 404.

    @param db Database session used for the lookup.
    @param work_type The type the attribute must belong to.
    @param attribute_id The id of the attribute definition to fetch.
    @return The matching :class:`AttributeDefinition` row.
    @raises HTTPException 404 when no such attribute exists on the type.
    """
    attribute = db.get(AttributeDefinition, attribute_id)
    if attribute is None or attribute.type_id != work_type.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attribute definition not found",
        )
    return attribute


def _check_default_conforms(payload: AttributeDefinitionIn) -> None:
    """Reject a default value that does not conform to the definition.

    Defaults are applied by the system at work-item creation time, so they
    must satisfy the same conformance rules as supplied values (spec:
    work-items, per-type attribute values).

    @param payload The attribute definition payload under validation.
    @raises HTTPException 422 when the default value is non-conforming.
    """
    if payload.default_value is None:
        return
    error = check_value(
        payload.data_type, payload.options, payload.key, payload.default_value
    )
    if error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": [f"default_value: {error}"]},
        )


def _next_position(db: DbSession, type_id: int) -> int:
    """Return the position at which a new attribute is appended.

    @param db Database session used for the lookup.
    @param type_id The id of the type being extended.
    @return One past the highest position in use (0 for an empty type).
    """
    highest = (
        db.query(func.max(AttributeDefinition.position))
        .filter(AttributeDefinition.type_id == type_id)
        .scalar()
    )
    return 0 if highest is None else highest + 1


def _assert_position_free(
    db: DbSession, type_id: int, position: int, exclude_attribute_id: int | None = None
) -> None:
    """Reject a position already used by another attribute of the type.

    Positions are unique within a type (spec: work-items); the check runs
    before the write so the caller receives a clear 409 instead of the
    generic integrity-conflict message from the ``(type_id, position)``
    constraint.

    @param db Database session used for the lookup.
    @param type_id The id of the type the position must be free in.
    @param position The candidate position value.
    @param exclude_attribute_id Id of an attribute being updated whose own
        current use of the position does not count as a conflict.
    @raises HTTPException 409 when another attribute already holds it.
    """
    query = db.query(AttributeDefinition.id).filter(
        AttributeDefinition.type_id == type_id,
        AttributeDefinition.position == position,
    )
    if exclude_attribute_id is not None:
        query = query.filter(AttributeDefinition.id != exclude_attribute_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Attribute position {position} is already used on this type",
        )


def _apply_definition(
    attribute: AttributeDefinition, payload: AttributeDefinitionIn
) -> None:
    """Copy a payload's fields onto an attribute definition row.

    The key is set at creation only. An omitted position (``None``) leaves
    the stored value unchanged; callers that create rows assign it before
    calling this function.

    @param attribute The row to update.
    @param payload The validated field values to apply.
    """
    attribute.label = payload.label
    attribute.data_type = payload.data_type
    attribute.options = payload.options if payload.data_type == "enum" else None
    attribute.required = payload.required
    attribute.default_value = payload.default_value
    if payload.position is not None:
        attribute.position = payload.position


@router.get("", response_model=list[WorkItemTypeOut])
def list_types(
    user: User = Depends(get_current_user), db: DbSession = Depends(get_db)
) -> list[WorkItemType]:
    """List all work-item types with their attribute definitions.

    Open to any authenticated user: the element-creation UI needs the type
    catalog to offer the type selector and render the dynamic form.

    @param user The authenticated caller (any role may browse).
    @param db Database session for the lookup.
    @return All types ordered by name, each with its attributes in order.
    """
    return db.query(WorkItemType).order_by(WorkItemType.name).all()


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=WorkItemTypeOut
)
def create_type(
    payload: WorkItemTypeCreate,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> WorkItemType:
    """Create a work-item type with its initial attribute definitions.

    @param payload The type's name, description, id prefix, and attributes.
    @param admin The administrator performing the action (enforced by
        :func:`require_admin`).
    @param db Database session for persisting the new type.
    @return The created type with its attributes.
    @raises HTTPException 409 when the name is already in use or two of the
        supplied attributes share a position.
    """
    work_type = WorkItemType(
        name=payload.name,
        description=payload.description,
        id_prefix=payload.id_prefix,
    )
    used_positions: set[int] = set()
    for attribute in payload.attributes:
        _check_default_conforms(attribute)
        if attribute.position is None:
            # Omitted positions are auto-assigned the smallest unused
            # non-negative value so the attribute is appended after the
            # explicitly positioned ones (spec: work-items).
            position = 0
            while position in used_positions:
                position += 1
        else:
            if attribute.position in used_positions:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Attribute position {attribute.position} is already "
                        "used on this type"
                    ),
                )
            position = attribute.position
        used_positions.add(position)
        work_type.attributes.append(
            AttributeDefinition(
                key=attribute.key,
                label=attribute.label,
                data_type=attribute.data_type,
                options=attribute.options if attribute.data_type == "enum" else None,
                required=attribute.required,
                default_value=attribute.default_value,
                position=position,
            )
        )
    db.add(work_type)
    try:
        db.commit()
    except IntegrityError:
        # Either the unique type name or a duplicate attribute key collided.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A work item type or attribute key already exists",
        )
    db.refresh(work_type)
    return work_type


@router.patch("/{type_id}", response_model=WorkItemTypeOut)
def update_type(
    type_id: int,
    payload: WorkItemTypeUpdate,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> WorkItemType:
    """Modify a work-item type's name, description, or id prefix.

    Built-in types cannot be renamed or have their id prefix changed; the
    description remains editable (design.md D3/D4). Renaming affects only
    newly created work items — existing identifiers are never rewritten.

    @param type_id The id of the type to modify.
    @param payload The fields to change (omitted fields are untouched).
    @param admin The administrator performing the action.
    @param db Database session for persisting the change.
    @return The updated type.
    @raises HTTPException 403 when modifying a built-in type's name or prefix.
    @raises HTTPException 404 when no such type exists.
    @raises HTTPException 409 when the new name is already in use.
    """
    work_type = _get_type_or_404(db, type_id)
    if payload.name is not None and payload.name != work_type.name:
        if work_type.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Built-in types cannot be renamed",
            )
        work_type.name = payload.name
    if payload.id_prefix is not None and payload.id_prefix != work_type.id_prefix:
        if work_type.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Built-in types cannot change their id prefix",
            )
        work_type.id_prefix = payload.id_prefix
    if payload.description is not None:
        work_type.description = payload.description

    try:
        db.commit()
    except IntegrityError:
        # The unique constraint on work_item_types.name rejected the rename.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A work item type with this name already exists",
        )
    db.refresh(work_type)
    return work_type


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_type(
    type_id: int,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> None:
    """Delete a work-item type that has no work items.

    The built-in type and any type that still has work items are rejected;
    the check and the delete run in one transaction (design.md D4).

    @param type_id The id of the type to delete.
    @param admin The administrator performing the action.
    @param db Database session for persisting the deletion.
    @raises HTTPException 403 when the type is built-in.
    @raises HTTPException 404 when no such type exists.
    @raises HTTPException 409 when the type still has work items.
    """
    work_type = _get_type_or_404(db, type_id)
    if work_type.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Built-in types cannot be deleted",
        )
    has_items = (
        db.query(WorkItem.id)
        .filter(WorkItem.type_id == work_type.id)
        .first()
        is not None
    )
    if has_items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Type still has work items and cannot be deleted",
        )
    db.delete(work_type)
    db.commit()


@router.post(
    "/{type_id}/attributes",
    status_code=status.HTTP_201_CREATED,
    response_model=AttributeDefinitionOut,
)
def create_attribute(
    type_id: int,
    payload: AttributeDefinitionIn,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> AttributeDefinition:
    """Add an attribute definition to a work-item type.

    @param type_id The id of the type to extend.
    @param payload The attribute's key, label, data type, and options.
    @param admin The administrator performing the action.
    @param db Database session for persisting the new definition.
    @return The created attribute definition.
    @raises HTTPException 404 when no such type exists.
    @raises HTTPException 409 when the key or position is already used on
        the type.
    """
    work_type = _get_type_or_404(db, type_id)
    _check_default_conforms(payload)
    if payload.position is not None:
        _assert_position_free(db, work_type.id, payload.position)
    # The key and position are set at creation only (the key is immutable
    # afterwards), so they are assigned here rather than in
    # :func:`_apply_definition`. An omitted position appends the attribute
    # after the existing ones (spec: work-items).
    attribute = AttributeDefinition(
        type_id=work_type.id,
        key=payload.key,
        position=(
            payload.position
            if payload.position is not None
            else _next_position(db, work_type.id)
        ),
    )
    _apply_definition(attribute, payload)
    db.add(attribute)
    try:
        db.commit()
    except IntegrityError:
        # The (type_id, key) unique constraint rejected the duplicate.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Attribute key '{payload.key}' already exists on this type",
        )
    db.refresh(attribute)
    return attribute


@router.patch(
    "/{type_id}/attributes/{attribute_id}", response_model=AttributeDefinitionOut
)
def update_attribute(
    type_id: int,
    attribute_id: int,
    payload: AttributeDefinitionIn,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> AttributeDefinition:
    """Modify an attribute definition (its key is immutable).

    @param type_id The id of the type owning the attribute.
    @param attribute_id The id of the attribute definition to modify.
    @param payload The new field values (the key must match the existing one).
    @param admin The administrator performing the action.
    @param db Database session for persisting the change.
    @return The updated attribute definition.
    @raises HTTPException 404 when no such type or attribute exists.
    """
    work_type = _get_type_or_404(db, type_id)
    attribute = _get_attribute_or_404(db, work_type, attribute_id)
    if payload.key != attribute.key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": ["An attribute key cannot be changed"]},
        )
    _check_default_conforms(payload)
    if payload.position is not None:
        # The attribute's own current use of the position is not a conflict.
        _assert_position_free(
            db, work_type.id, payload.position, exclude_attribute_id=attribute.id
        )
    _apply_definition(attribute, payload)
    db.commit()
    db.refresh(attribute)
    return attribute


@router.delete(
    "/{type_id}/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_attribute(
    type_id: int,
    attribute_id: int,
    admin: User = Depends(require_admin),
    db: DbSession = Depends(get_db),
) -> None:
    """Remove an attribute definition from a work-item type.

    Stored values for the key are stripped from all existing work items of
    the type in the same transaction, so no orphaned data remains and later
    updates of those items are not blocked by the unknown key.

    @param type_id The id of the type owning the attribute.
    @param attribute_id The id of the attribute definition to remove.
    @param admin The administrator performing the action.
    @param db Database session for persisting the deletion.
    @raises HTTPException 404 when no such type or attribute exists.
    """
    work_type = _get_type_or_404(db, type_id)
    attribute = _get_attribute_or_404(db, work_type, attribute_id)
    key = attribute.key

    items = (
        db.query(WorkItem).filter(WorkItem.type_id == work_type.id).all()
    )
    for item in items:
        if key in item.attributes:
            # JSONB is immutable in place; replace the dict to mark it dirty.
            item.attributes = {k: v for k, v in item.attributes.items() if k != key}

    db.delete(attribute)
    db.commit()
