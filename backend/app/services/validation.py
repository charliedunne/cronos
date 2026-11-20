"""Per-type attribute value validation (spec: work-items).

Conformance of a work item's attribute values against its type's attribute
definitions is enforced in the API layer (design.md decision D2): JSONB has
no DB-level type constraints. The service checks data type, required-ness,
and enum membership, applies defaults to omitted attributes, and rejects the
reserved system keys ``title`` / ``id``. Routers translate
:class:`AttributeValidationError` into HTTP 422 with a
``{"errors": [...]}`` body (one human-readable message per problem).
"""

from datetime import datetime
from typing import Any

from app.models import AttributeDefinition, WorkItemType

#: Keys reserved for the mandatory system attributes (spec: work-items).
RESERVED_KEYS = frozenset({"title", "id"})

#: Data types an attribute definition may declare (spec: work-items).
ALLOWED_DATA_TYPES = ("string", "text", "integer", "boolean", "date", "enum")


class AttributeValidationError(Exception):
    """Attribute values do not conform to a type's definitions.

    ``errors`` carries one human-readable message per problem so the API can
    report every issue in a single 422 response instead of failing on the
    first.
    """

    def __init__(self, errors: list[str]) -> None:
        """Collect the validation errors.

        @param errors One human-readable message per conformance problem.
        """
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_values(
    type_def: WorkItemType, provided: dict[str, Any]
) -> dict[str, Any]:
    """Validate attribute values against a type's definitions.

    Applies defaults to omitted attributes and returns the complete value
    map that should be stored on the work item. Non-required attributes
    without a default and without a supplied value are omitted from the
    result.

    @param type_def The work-item type whose definitions the values are
        checked against (its ``attributes`` relationship must be loaded).
    @param provided Raw attribute values supplied by the caller, keyed by
        attribute key; reserved keys (``title`` / ``id``) and unknown keys
        are rejected.
    @return The complete, conforming value map for storage in the work
        item's ``attributes`` column.
    @raises AttributeValidationError When a reserved or unknown key is used,
        a required value is missing, a value has the wrong data type, or an
        enum value is not in the allowed set.
    """
    errors: list[str] = []
    definitions = {a.key: a for a in type_def.attributes}

    for key in provided:
        if key in RESERVED_KEYS:
            errors.append(
                f"'{key}' is a reserved system attribute and cannot be set here"
            )
        elif key not in definitions:
            errors.append(f"Unknown attribute '{key}' for type '{type_def.name}'")

    result: dict[str, Any] = {}
    for key, definition in definitions.items():
        if key in provided:
            error = _check_value(definition, provided[key])
            if error is not None:
                errors.append(error)
            else:
                result[key] = provided[key]
        elif definition.default_value is not None:
            result[key] = definition.default_value
        elif definition.required:
            errors.append(f"Missing required attribute '{key}'")

    if errors:
        raise AttributeValidationError(errors)
    return result


def check_value(
    data_type: str, options: list[Any] | None, key: str, value: Any
) -> str | None:
    """Check a single value against an attribute's type and options.

    Exposed so the admin API can validate a definition's ``default_value``
    at creation/update time: defaults are applied by the system, so they
    must conform too (spec: work-items, per-type attribute values).

    @param data_type The declared data type of the attribute.
    @param options The allowed values for an enum attribute (else None).
    @param key The attribute key, used to phrase the error message.
    @param value The candidate value (any JSON type).
    @return A human-readable error message, or None when the value conforms.
    """
    return _check_core(data_type, options, key, value)


def _check_value(definition: AttributeDefinition, value: Any) -> str | None:
    """Check a single value against its definition.

    @param definition The attribute definition the value must conform to.
    @param value The supplied value (any JSON type).
    @return A human-readable error message, or None when the value conforms.
    """
    return _check_core(definition.data_type, definition.options, definition.key, value)


def _check_core(
    data_type: str, options: list[Any] | None, key: str, value: Any
) -> str | None:
    """Core conformance check shared by work-item and default validation.

    @param data_type The declared data type of the attribute.
    @param options The allowed values for an enum attribute (else None).
    @param key The attribute key, used to phrase the error message.
    @param value The candidate value (any JSON type).
    @return A human-readable error message, or None when the value conforms.
    """
    if data_type in ("string", "text"):
        if not isinstance(value, str):
            return f"Attribute '{key}' must be a string"
    elif data_type == "integer":
        # bool is a subclass of int in Python; reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int):
            return f"Attribute '{key}' must be an integer"
    elif data_type == "boolean":
        if not isinstance(value, bool):
            return f"Attribute '{key}' must be a boolean"
    elif data_type == "date":
        if not _is_iso_date(value):
            return f"Attribute '{key}' must be a date in YYYY-MM-DD format"
    elif data_type == "enum":
        allowed_options = options or []
        if value not in allowed_options:
            allowed = ", ".join(map(str, allowed_options))
            return f"Attribute '{key}' must be one of: {allowed}"
    else:  # unreachable: data_type is validated at definition time
        return f"Attribute '{key}' has an unknown data type"
    return None


def _is_iso_date(value: Any) -> bool:
    """Return True when value is a real date in YYYY-MM-DD format.

    @param value The candidate value (must be a string).
    @return True when the value parses as a calendar date, else False.
    """
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True
