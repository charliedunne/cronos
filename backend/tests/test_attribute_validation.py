"""Tests for per-type attribute value validation (task 5.2).

A custom work-item type carries one attribute of each supported data type;
creating a work item with non-conforming values is rejected with 422 and the
standard ``{"errors": [...]}`` body, while conforming values are stored.
"""

import re
import uuid

from fastapi.testclient import TestClient

from test_work_item_types import TypeFactory


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


#: One attribute per supported data type, keyed by attribute key.
ALL_TYPES_ATTRIBUTES = [
    {"key": "s", "label": "String", "data_type": "string"},
    {"key": "t", "label": "Text", "data_type": "text"},
    {"key": "i", "label": "Integer", "data_type": "integer"},
    {"key": "b", "label": "Boolean", "data_type": "boolean"},
    {"key": "d", "label": "Date", "data_type": "date"},
    {
        "key": "e",
        "label": "Enum",
        "data_type": "enum",
        "options": ["minor", "major"],
    },
]

#: A fully conforming value map for :data:`ALL_TYPES_ATTRIBUTES`.
CONFORMING_VALUES = {
    "s": "a string",
    "t": "some text",
    "i": 42,
    "b": True,
    "d": "2026-11-20",
    "e": "minor",
}


def _create_all_types_type(factory: TypeFactory) -> dict:
    """Create a type with one attribute per data type and return its body.

    @param factory The admin-API type factory performing the call.
    @return The created type body.
    """
    return factory.create(
        id_prefix="VAL", attributes=list(ALL_TYPES_ATTRIBUTES)
    )


def _attempt_create(client: TestClient, module_id: int, type_id: int, values: dict) -> int:
    """POST a work item with the given attribute values; return the status.

    @param client An authenticated test client performing the call.
    @param module_id The module to create the work item in.
    @param type_id The work-item type to instantiate.
    @param values Attribute values for the type's definitions.
    @return The HTTP status code of the response.
    """
    return client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": type_id, "title": "validation item", "attributes": values},
    ).status_code


def _assert_rejected(response, expected_message: str) -> None:
    """Assert a 422 response carrying exactly the expected error message.

    @param response The API response to inspect.
    @param expected_message The single error message that must be present.
    """
    assert response.status_code == 422, response.text
    errors = response.json()["detail"]["errors"]
    assert isinstance(errors, list) and errors
    assert expected_message in errors


def test_wrong_data_type_rejected_per_type(client, user, admin_client):
    """Each data type rejects a value of the wrong kind with its own message."""
    factory = TypeFactory(admin_client["client"])
    body = _create_all_types_type(factory)
    module_id = client.post(
        "/api/v1/modules", json={"name": _new_name("valmod")}
    ).json()["id"]
    type_id = body["id"]

    # string / text: non-string values are rejected.
    for key in ("s", "t"):
        response = client.post(
            f"/api/v1/modules/{module_id}/work-items",
            json={"type_id": type_id, "title": "x", "attributes": {key: 42}},
        )
        _assert_rejected(response, f"Attribute '{key}' must be a string")

    # integer: bool is rejected explicitly (bool subclasses int in Python),
    # as is a numeric string.
    for bad in (True, "42"):
        response = client.post(
            f"/api/v1/modules/{module_id}/work-items",
            json={"type_id": type_id, "title": "x", "attributes": {"i": bad}},
        )
        _assert_rejected(response, "Attribute 'i' must be an integer")

    # boolean: an int is not a boolean.
    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": type_id, "title": "x", "attributes": {"b": 1}},
    )
    _assert_rejected(response, "Attribute 'b' must be a boolean")

    # date: non-ISO strings and impossible calendar dates are rejected.
    for bad in ("20/11/2026", "not-a-date", "2026-02-30"):
        response = client.post(
            f"/api/v1/modules/{module_id}/work-items",
            json={"type_id": type_id, "title": "x", "attributes": {"d": bad}},
        )
        _assert_rejected(
            response, "Attribute 'd' must be a date in YYYY-MM-DD format"
        )

    # enum: a value outside the declared options is rejected.
    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": type_id, "title": "x", "attributes": {"e": "critical"}},
    )
    _assert_rejected(response, "Attribute 'e' must be one of: minor, major")


def test_missing_required_attribute_rejected(client, user, admin_client):
    """Omitting a required attribute (with no default) yields 422; the
    message names the missing key."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        id_prefix="REQ",
        attributes=[
            {"key": "steps", "label": "Steps", "data_type": "text", "required": True},
            {"key": "note", "label": "Note", "data_type": "string"},
        ],
    )
    module_id = client.post(
        "/api/v1/modules", json={"name": _new_name("reqmod")}
    ).json()["id"]

    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={
            "type_id": body["id"],
            "title": "missing required",
            "attributes": {"note": "optional present"},
        },
    )
    _assert_rejected(response, "Missing required attribute 'steps'")


def test_blank_title_rejected_on_custom_type(client, user, admin_client):
    """The mandatory title is enforced on every type: a blank title yields a
    standard 422 validation body (pydantic)."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(id_prefix="TIT")
    module_id = client.post(
        "/api/v1/modules", json={"name": _new_name("titmod")}
    ).json()["id"]

    for blank in ("", "   "):
        response = client.post(
            f"/api/v1/modules/{module_id}/work-items",
            json={"type_id": body["id"], "title": blank, "attributes": {}},
        )
        assert response.status_code == 422, blank
        # Standard FastAPI validation body: a list of error objects.
        assert isinstance(response.json()["detail"], list)


def test_conforming_values_stored_and_identifier_prefixed(
    client, user, admin_client
):
    """Conforming values for all six data types are accepted and stored; the
    identifier carries the type's prefix."""
    factory = TypeFactory(admin_client["client"])
    body = _create_all_types_type(factory)
    module_id = client.post(
        "/api/v1/modules", json={"name": _new_name("okmod")}
    ).json()["id"]

    created = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={
            "type_id": body["id"],
            "title": "conforming item",
            "attributes": dict(CONFORMING_VALUES),
        },
    )
    assert created.status_code == 201, created.text
    result = created.json()
    assert re.fullmatch(r"VAL-\d{6}", result["identifier"])
    assert result["attributes"] == CONFORMING_VALUES
