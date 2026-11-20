"""Tests for the work-item type registry endpoints (tasks 2.1-2.3, 5.1).

Administrators manage work-item types and their attribute definitions;
listing is open to any authenticated user (design.md D6). The built-in
"requirement" type (id 1) is protected from rename, prefix change, and
deletion. Types created here are cleaned up through the API on teardown —
the shared conftest cleanup does not touch ``work_item_types`` rows.
"""

import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import WorkItem, WorkItemType
from conftest import _type_factory_finalizers


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TypeFactory:
    """Create work-item types through the admin API and clean them up.

    Every type created via :meth:`create` is registered so that teardown can
    remove its work items (directly, since item deletion requires a lock)
    and then delete the type itself; cleanup happens through the ORM because
    it runs after fixture clients are closed.
    """

    def __init__(self, admin_client: TestClient) -> None:
        self._client = admin_client
        self._created: list[int] = []
        _type_factory_finalizers.append(self.cleanup)

    def create(self, **overrides) -> dict:
        """Create a type with a unique name and return its response body.

        @param overrides Extra payload fields (attributes, id_prefix, ...).
        @return The created type body (id, name, attributes with ids).
        """
        payload = {
            "name": _new_name("witype"),
            "description": "",
            "id_prefix": "TST",
            "attributes": [],
        }
        payload.update(overrides)
        response = self._client.post("/api/v1/work-item-types", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        self._created.append(body["id"])
        return body

    def deleted(self, type_id: int) -> None:
        """Mark a type as already deleted by the test under teardown."""
        if type_id in self._created:
            self._created.remove(type_id)

    def cleanup(self) -> None:
        """Remove all registered types and their work items via the ORM.

        This runs after fixture clients are closed (see the autouse
        ``_finalize_type_factories`` fixture in conftest), so it must not use
        them; direct ORM deletes are safe because attribute definitions and
        locks cascade from their parents.
        """
        if not self._created:
            return
        with SessionLocal() as session:
            session.query(WorkItem).filter(
                WorkItem.type_id.in_(self._created)
            ).delete(synchronize_session=False)
            session.query(WorkItemType).filter(
                WorkItemType.id.in_(self._created)
            ).delete(synchronize_session=False)
            session.commit()


def _create_module(client: TestClient) -> int:
    """Create a module through the API and return its id.

    @param client An authenticated test client performing the call.
    @return The new module's id.
    """
    created = client.post("/api/v1/modules", json={"name": _new_name("typemod")})
    assert created.status_code == 201
    return created.json()["id"]


def _create_item(client: TestClient, module_id: int, type_id: int, attributes=None) -> dict:
    """Create a work item of the given type through the API.

    @param client An authenticated test client performing the call.
    @param module_id The module to create the work item in.
    @param type_id The work-item type to instantiate.
    @param attributes Attribute values for the type's definitions.
    @return The created work item body.
    """
    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": type_id, "title": "an item", "attributes": attributes or {}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_creates_type_with_attributes(admin_client):
    """An administrator creates a type with attribute definitions; the
    response and listing expose each definition's id (needed to address the
    per-attribute update/delete endpoints)."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        attributes=[
            {"key": "steps", "label": "Steps", "data_type": "text", "position": 1},
            {
                "key": "severity",
                "label": "Severity",
                "data_type": "enum",
                "options": ["minor", "major"],
                "required": True,
                "position": 2,
            },
        ]
    )

    assert body["name"].startswith("witype-")
    assert body["is_builtin"] is False
    assert [a["key"] for a in body["attributes"]] == ["steps", "severity"]
    assert all(isinstance(a["id"], int) for a in body["attributes"])
    severity = next(a for a in body["attributes"] if a["key"] == "severity")
    assert severity["options"] == ["minor", "major"]
    assert severity["required"] is True

    listing = admin_client["client"].get("/api/v1/work-item-types")
    assert listing.status_code == 200
    names = [t["name"] for t in listing.json()]
    assert body["name"] in names


def test_duplicate_type_name_rejected(admin_client):
    """Creating a second type with an already used name yields 409."""
    factory = TypeFactory(admin_client["client"])
    name = _new_name("dupwitype")
    first = factory.create(name=name)

    second = admin_client["client"].post(
        "/api/v1/work-item-types", json={"name": name, "id_prefix": "XXX"}
    )
    assert second.status_code == 409

    # Renaming another type onto the same name is rejected as well.
    other = factory.create(id_prefix="YYY")
    conflict = admin_client["client"].patch(
        f"/api/v1/work-item-types/{other['id']}", json={"name": name}
    )
    assert conflict.status_code == 409


def test_delete_empty_type_succeeds(admin_client):
    """Deleting a type with no work items yields 204 and removes it."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create()

    deleted = admin_client["client"].delete(
        f"/api/v1/work-item-types/{body['id']}"
    )
    assert deleted.status_code == 204
    factory.deleted(body["id"])

    listing = admin_client["client"].get("/api/v1/work-item-types").json()
    assert all(t["id"] != body["id"] for t in listing)


def test_delete_non_empty_type_rejected(client, user, admin_client):
    """Deleting a type that still has work items yields 409; after the items
    are gone the deletion succeeds."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create()
    module_id = _create_module(client)
    item = _create_item(client, module_id, body["id"])

    rejected = admin_client["client"].delete(
        f"/api/v1/work-item-types/{body['id']}"
    )
    assert rejected.status_code == 409

    # Remove the item (lock first: deletion requires holding the lock).
    assert client.post(f"/api/v1/work-items/{item['id']}/lock").status_code == 200
    assert client.delete(f"/api/v1/work-items/{item['id']}").status_code == 204

    deleted = admin_client["client"].delete(
        f"/api/v1/work-item-types/{body['id']}"
    )
    assert deleted.status_code == 204
    factory.deleted(body["id"])


def test_builtin_type_is_protected(admin_client):
    """The built-in requirement type cannot be renamed, have its prefix
    changed, or be deleted; its description stays editable."""
    listing = admin_client["client"].get("/api/v1/work-item-types").json()
    builtin = next(t for t in listing if t["name"] == "requirement")
    assert builtin["is_builtin"] is True
    original_description = builtin["description"]

    try:
        renamed = admin_client["client"].patch(
            f"/api/v1/work-item-types/{builtin['id']}", json={"name": "renamed"}
        )
        assert renamed.status_code == 403

        reprefixed = admin_client["client"].patch(
            f"/api/v1/work-item-types/{builtin['id']}", json={"id_prefix": "XXX"}
        )
        assert reprefixed.status_code == 403

        deleted = admin_client["client"].delete(
            f"/api/v1/work-item-types/{builtin['id']}"
        )
        assert deleted.status_code == 403
    finally:
        # Restore the description if the edit below succeeded.
        pass

    edited = admin_client["client"].patch(
        f"/api/v1/work-item-types/{builtin['id']}",
        json={"description": "temporarily edited"},
    )
    assert edited.status_code == 200
    restored = admin_client["client"].patch(
        f"/api/v1/work-item-types/{builtin['id']}",
        json={"description": original_description},
    )
    assert restored.status_code == 200


def test_reserved_attribute_keys_rejected(admin_client):
    """The reserved system keys 'title' and 'id' are rejected as attribute
    definition keys with a standard 422 validation body."""
    factory = TypeFactory(admin_client["client"])

    for key in ("title", "id"):
        response = admin_client["client"].post(
            "/api/v1/work-item-types",
            json={
                "name": _new_name("reswitype"),
                "id_prefix": "RES",
                "attributes": [{"key": key, "label": "Nope", "data_type": "string"}],
            },
        )
        assert response.status_code == 422, key

    # Also rejected when adding to an existing type.
    body = factory.create()
    for key in ("title", "id"):
        response = admin_client["client"].post(
            f"/api/v1/work-item-types/{body['id']}/attributes",
            json={"key": key, "label": "Nope", "data_type": "string"},
        )
        assert response.status_code == 422, key


def test_invalid_data_type_and_enum_without_options_rejected(admin_client):
    """A data type outside the allowed set, or an enum without options, is
    rejected with a standard 422 validation body."""
    factory = TypeFactory(admin_client["client"])

    bad_type = admin_client["client"].post(
        "/api/v1/work-item-types",
        json={
            "name": _new_name("badwitype"),
            "id_prefix": "BAD",
            "attributes": [{"key": "k", "label": "K", "data_type": "float"}],
        },
    )
    assert bad_type.status_code == 422

    no_options = admin_client["client"].post(
        "/api/v1/work-item-types",
        json={
            "name": _new_name("nooptwitype"),
            "id_prefix": "NOO",
            "attributes": [{"key": "k", "label": "K", "data_type": "enum"}],
        },
    )
    assert no_options.status_code == 422


def test_regular_user_can_list_but_not_mutate(client, user):
    """Any authenticated user can list the type catalog (the creation form
    needs it), but only administrators may mutate it; unauthenticated
    requests are rejected with 401."""
    listing = client.get("/api/v1/work-item-types")
    assert listing.status_code == 200
    names = [t["name"] for t in listing.json()]
    assert "requirement" in names

    created = client.post(
        "/api/v1/work-item-types", json={"name": _new_name("nope"), "id_prefix": "NP"}
    )
    assert created.status_code == 403

    builtin_id = next(t["id"] for t in listing.json() if t["name"] == "requirement")
    patched = client.patch(
        f"/api/v1/work-item-types/{builtin_id}", json={"description": "hijack"}
    )
    assert patched.status_code == 403

    with TestClient(app, base_url="https://testserver") as anon:
        assert anon.get("/api/v1/work-item-types").status_code == 401


def test_default_value_conformance_checked(admin_client):
    """A definition's default value must conform to its data type; a
    non-conforming default yields 422 with the standard errors body."""
    factory = TypeFactory(admin_client["client"])

    response = admin_client["client"].post(
        "/api/v1/work-item-types",
        json={
            "name": _new_name("defwitype"),
            "id_prefix": "DEF",
            "attributes": [
                {
                    "key": "count",
                    "label": "Count",
                    "data_type": "integer",
                    "default_value": "not-an-int",
                }
            ],
        },
    )
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert isinstance(errors, list) and errors
    assert all(e.startswith("default_value: ") for e in errors)

    # A conforming default is accepted.
    body = factory.create(
        attributes=[
            {
                "key": "count",
                "label": "Count",
                "data_type": "integer",
                "default_value": 3,
            }
        ]
    )
    assert body["attributes"][0]["default_value"] == 3


def test_admin_adds_attribute_to_existing_type(admin_client):
    """Adding a new attribute definition to an existing type succeeds: the
    definition is returned with its id and stored fields, and it appears in
    the type listing afterwards (regression: the key used to be omitted from
    the INSERT, surfacing as a spurious 409 'already exists')."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create()

    created = admin_client["client"].post(
        f"/api/v1/work-item-types/{body['id']}/attributes",
        json={"key": "steps", "label": "Steps", "data_type": "text", "position": 1},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["key"] == "steps"
    assert payload["label"] == "Steps"
    assert payload["data_type"] == "text"
    assert payload["position"] == 1
    assert isinstance(payload["id"], int)

    listed = admin_client["client"].get("/api/v1/work-item-types")
    entry = next(t for t in listed.json() if t["id"] == body["id"])
    assert [a["key"] for a in entry["attributes"]] == ["steps"]


def test_duplicate_attribute_key_rejected(admin_client):
    """Adding an attribute whose key already exists on the type yields 409."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        attributes=[{"key": "steps", "label": "Steps", "data_type": "text"}]
    )

    duplicate = admin_client["client"].post(
        f"/api/v1/work-item-types/{body['id']}/attributes",
        json={"key": "steps", "label": "Steps again", "data_type": "text"},
    )
    assert duplicate.status_code == 409


def test_attribute_key_immutable_on_update(admin_client):
    """An attribute definition's key cannot be changed on update (422);
    updating the other fields with the same key succeeds."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        attributes=[{"key": "steps", "label": "Steps", "data_type": "text"}]
    )
    attribute_id = body["attributes"][0]["id"]

    renamed = admin_client["client"].patch(
        f"/api/v1/work-item-types/{body['id']}/attributes/{attribute_id}",
        json={"key": "other", "label": "Other", "data_type": "text"},
    )
    assert renamed.status_code == 422
    assert renamed.json()["detail"]["errors"] == ["An attribute key cannot be changed"]

    updated = admin_client["client"].patch(
        f"/api/v1/work-item-types/{body['id']}/attributes/{attribute_id}",
        json={"key": "steps", "label": "Steps (renamed label)", "data_type": "text"},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Steps (renamed label)"


def test_omitted_positions_are_auto_assigned(admin_client):
    """Omitted positions are auto-assigned so attributes are appended after
    the existing ones: on create-type the smallest unused non-negative value
    fills gaps left by explicit positions, and on add-attribute one past the
    highest position in use is used (0 for an empty type)."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        attributes=[
            {"key": "first", "label": "First", "data_type": "text"},
            {"key": "gap", "label": "Gap", "data_type": "text", "position": 5},
            {"key": "last", "label": "Last", "data_type": "text"},
        ]
    )
    positions = {a["key"]: a["position"] for a in body["attributes"]}
    assert positions == {"first": 0, "gap": 5, "last": 1}

    # Adding without a position appends after the highest one in use.
    appended = admin_client["client"].post(
        f"/api/v1/work-item-types/{body['id']}/attributes",
        json={"key": "appended", "label": "Appended", "data_type": "text"},
    )
    assert appended.status_code == 201
    assert appended.json()["position"] == 6

    # An empty type starts at position 0.
    empty = factory.create()
    first_attr = admin_client["client"].post(
        f"/api/v1/work-item-types/{empty['id']}/attributes",
        json={"key": "solo", "label": "Solo", "data_type": "text"},
    )
    assert first_attr.json()["position"] == 0


def test_duplicate_attribute_position_rejected(admin_client):
    """A position already used by another attribute of the same type is
    rejected with a clear 409, both when adding an attribute and when
    updating one to collide; re-stating an attribute's own position is fine."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        attributes=[
            {"key": "a", "label": "A", "data_type": "text"},
            {"key": "b", "label": "B", "data_type": "text"},
        ]
    )
    a_id = next(x["id"] for x in body["attributes"] if x["key"] == "a")
    b_id = next(x["id"] for x in body["attributes"] if x["key"] == "b")

    # Adding a third attribute at an existing position is rejected.
    conflict = admin_client["client"].post(
        f"/api/v1/work-item-types/{body['id']}/attributes",
        json={"key": "c", "label": "C", "data_type": "text", "position": 0},
    )
    assert conflict.status_code == 409
    assert "position 0" in conflict.json()["detail"]

    # Moving b onto a's position is rejected as well.
    moved = admin_client["client"].patch(
        f"/api/v1/work-item-types/{body['id']}/attributes/{b_id}",
        json={"key": "b", "label": "B", "data_type": "text", "position": 0},
    )
    assert moved.status_code == 409

    # Re-stating a's own position is not a conflict.
    same = admin_client["client"].patch(
        f"/api/v1/work-item-types/{body['id']}/attributes/{a_id}",
        json={"key": "a", "label": "A (same spot)", "data_type": "text", "position": 0},
    )
    assert same.status_code == 200
    assert same.json()["position"] == 0

    # A free position is accepted on update.
    swapped = admin_client["client"].patch(
        f"/api/v1/work-item-types/{body['id']}/attributes/{b_id}",
        json={"key": "b", "label": "B", "data_type": "text", "position": 2},
    )
    assert swapped.status_code == 200
    assert swapped.json()["position"] == 2

    # Omitting the position on update leaves the stored value unchanged.
    untouched = admin_client["client"].patch(
        f"/api/v1/work-item-types/{body['id']}/attributes/{a_id}",
        json={"key": "a", "label": "A (untouched)", "data_type": "text"},
    )
    assert untouched.status_code == 200
    assert untouched.json()["position"] == 0


def test_create_type_rejects_colliding_positions(admin_client):
    """Creating a type whose initial attributes share a position yields 409
    and leaves no partial type behind."""
    factory = TypeFactory(admin_client["client"])
    name = _new_name("poswitype")

    conflict = admin_client["client"].post(
        "/api/v1/work-item-types",
        json={
            "name": name,
            "id_prefix": "POS",
            "attributes": [
                {"key": "a", "label": "A", "data_type": "text", "position": 0},
                {"key": "b", "label": "B", "data_type": "text", "position": 0},
            ],
        },
    )
    assert conflict.status_code == 409

    listing = admin_client["client"].get("/api/v1/work-item-types").json()
    assert all(t["name"] != name for t in listing)


def test_deleting_attribute_strips_stored_values(client, user, admin_client):
    """Deleting an attribute definition removes the key from all stored
    work items of the type, so later updates are not blocked by it."""
    factory = TypeFactory(admin_client["client"])
    body = factory.create(
        attributes=[
            {"key": "steps", "label": "Steps", "data_type": "text"},
            {"key": "note", "label": "Note", "data_type": "string"},
        ]
    )
    note_id = next(a["id"] for a in body["attributes"] if a["key"] == "note")

    module_id = _create_module(client)
    item = _create_item(
        client, module_id, body["id"], {"steps": "do it", "note": "remember"}
    )
    assert item["attributes"]["note"] == "remember"

    deleted = admin_client["client"].delete(
        f"/api/v1/work-item-types/{body['id']}/attributes/{note_id}"
    )
    assert deleted.status_code == 204

    listing = client.get(f"/api/v1/modules/{module_id}/work-items").json()
    entry = next(b for b in listing if b["id"] == item["id"])
    assert "note" not in entry["attributes"]
    assert entry["attributes"]["steps"] == "do it"

    # The item can still be updated; the stripped key no longer exists.
    assert client.post(f"/api/v1/work-items/{item['id']}/lock").status_code == 200
    updated = client.patch(
        f"/api/v1/work-items/{item['id']}", json={"attributes": {"steps": "done"}}
    )
    assert updated.status_code == 200
    assert updated.json()["attributes"] == {"steps": "done"}
