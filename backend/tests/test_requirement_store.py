"""Tests for the work item store endpoints (requirement-store spec).

The former single "requirement" element is now a typed work item: creation
selects a type from the admin-managed registry and supplies attribute values
that are validated against that type's definitions. The built-in
"requirement" type (id 1) preserves the previous behaviour with its
text/status/priority attributes, so these tests double as the regression
check for the migration of the old endpoints.
"""

import re
import uuid

from app.db import SessionLocal
from app.models import Module, User, WorkItem, WorkItemType
from app.security import hash_password


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _create_module(client) -> int:
    """Create a module through the API and return its id.

    @param client An authenticated test client performing the call.
    @return The new module's id.
    """
    created = client.post("/api/v1/modules", json={"name": _new_name("wimod")})
    assert created.status_code == 201
    return created.json()["id"]


def _create_work_item(client, module_id: int, **overrides) -> dict:
    """Create a built-in requirement work item through the API.

    @param client An authenticated test client performing the call.
    @param module_id The module to create the work item in.
    @param overrides Extra payload fields (title, attributes, type_id).
    @return The created work item body.
    """
    payload = {"type_id": 1, "title": "a requirement", "attributes": {}}
    payload.update(overrides)
    response = client.post(f"/api/v1/modules/{module_id}/work-items", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_work_item_assigns_identifier_and_defaults(client, user):
    """Creating a built-in requirement assigns a REQ identifier and applies
    the type's attribute defaults (text/status/priority)."""
    module_id = _create_module(client)

    body = _create_work_item(client, module_id)

    assert re.fullmatch(r"REQ-\d{6}", body["identifier"])
    assert body["title"] == "a requirement"
    assert body["type"] == {
        "id": 1,
        "name": "requirement",
        "id_prefix": "REQ",
        "is_builtin": True,
    }
    assert body["attributes"] == {
        "text": "",
        "status": "draft",
        "priority": "medium",
    }
    assert body["locked_by"] is None


def test_create_work_item_with_explicit_attribute_values(client, user):
    """Explicitly supplied attribute values are stored as given."""
    module_id = _create_module(client)

    body = _create_work_item(
        client,
        module_id,
        title="explicit",
        attributes={"text": "do the thing", "status": "approved", "priority": "high"},
    )

    assert body["attributes"] == {
        "text": "do the thing",
        "status": "approved",
        "priority": "high",
    }


def test_list_work_items_shows_type_attributes_and_order(client, user):
    """The module listing carries the nested type object, attribute values,
    and orders items by their identifier sequence."""
    module_id = _create_module(client)
    first = _create_work_item(client, module_id, title="first")
    second = _create_work_item(client, module_id, title="second")

    listing = client.get(f"/api/v1/modules/{module_id}/work-items")
    assert listing.status_code == 200
    bodies = listing.json()

    assert [b["id"] for b in bodies] == [first["id"], second["id"]]
    for body in bodies:
        assert body["type"]["name"] == "requirement"
        assert set(body["attributes"]) == {"text", "status", "priority"}
        assert re.fullmatch(r"REQ-\d{6}", body["identifier"])


def test_blank_title_rejected(client, user):
    """A whitespace-only title is rejected with 422 for every type."""
    module_id = _create_module(client)

    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "   ", "attributes": {}},
    )
    assert response.status_code == 422


def test_invalid_enum_value_rejected_with_errors_contract(client, user):
    """A value outside an enum's options yields 422 with the standard
    {"errors": [...]} body (one message per problem)."""
    module_id = _create_module(client)

    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "bad enum", "attributes": {"status": "bogus"}},
    )
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert isinstance(errors, list) and errors
    assert all(isinstance(e, str) for e in errors)


def test_reserved_and_unknown_keys_rejected(client, user):
    """Reserved system keys (title/id) and unknown attribute keys are
    rejected with 422."""
    module_id = _create_module(client)

    for bad_attributes in ({"id": 5}, {"title": "nope"}, {"unknown_key": 1}):
        response = client.post(
            f"/api/v1/modules/{module_id}/work-items",
            json={"type_id": 1, "title": "t", "attributes": bad_attributes},
        )
        assert response.status_code == 422, bad_attributes
        assert response.json()["detail"]["errors"]


def test_create_with_unknown_type_rejected_404(client, user):
    """Creating a work item of a non-existent type yields 404."""
    module_id = _create_module(client)

    response = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 999999, "title": "t", "attributes": {}},
    )
    assert response.status_code == 404


def test_patch_requires_lock_and_holder_patch_merges(client, user):
    """Updating without the lock is rejected; the holder's update merges the
    supplied values over the stored ones, validates the full map, and retains
    the lock. A non-conforming update changes nothing."""
    module_id = _create_module(client)
    body = _create_work_item(client, module_id, title="original")
    item_id = body["id"]

    rejected = client.patch(
        f"/api/v1/work-items/{item_id}", json={"title": "no lock"}
    )
    assert rejected.status_code == 409

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    updated = client.patch(
        f"/api/v1/work-items/{item_id}",
        json={"title": "updated", "attributes": {"status": "approved"}},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "updated"
    # Untouched attributes survive the merge.
    assert body["attributes"]["status"] == "approved"
    assert body["attributes"]["text"] == ""
    assert body["attributes"]["priority"] == "medium"
    assert body["locked_by"] == user["username"]

    # A non-conforming update is rejected and leaves the stored values intact.
    bad = client.patch(
        f"/api/v1/work-items/{item_id}",
        json={"attributes": {"priority": "urgent"}},
    )
    assert bad.status_code == 422

    listing = client.get(f"/api/v1/modules/{module_id}/work-items").json()
    entry = next(b for b in listing if b["id"] == item_id)
    assert entry["attributes"]["priority"] == "medium"


def test_delete_requires_lock_and_holder_delete_removes(client, user):
    """Deleting without the lock is rejected; the holder's deletion removes
    the work item from the module."""
    module_id = _create_module(client)
    body = _create_work_item(client, module_id)
    item_id = body["id"]

    rejected = client.delete(f"/api/v1/work-items/{item_id}")
    assert rejected.status_code == 409

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200
    deleted = client.delete(f"/api/v1/work-items/{item_id}")
    assert deleted.status_code == 204

    listing = client.get(f"/api/v1/modules/{module_id}/work-items").json()
    assert all(b["id"] != item_id for b in listing)


def test_identifier_renders_type_prefix_from_global_sequence():
    """The identifier is rendered as <TYPE_PREFIX>-<zero-padded seq> from the
    shared global sequence, so different types share one numbering space
    (design.md D1)."""
    username = _new_name("sequser")
    with SessionLocal() as session:
        owner = User(username=username, password_hash=hash_password("pw"))
        session.add(owner)
        session.commit()
        session.refresh(owner)

        module = Module(name=_new_name("seqmod"), created_by=owner.id)
        session.add(module)
        session.commit()
        session.refresh(module)

        custom_type = WorkItemType(
            name=_new_name("bugtype"), id_prefix="BUG"
        )
        session.add(custom_type)
        session.commit()
        session.refresh(custom_type)

        first = WorkItem(
            module_id=module.id, type_id=1, title="first", created_by=owner.id
        )
        second = WorkItem(
            module_id=module.id, type_id=custom_type.id, title="second",
            created_by=owner.id,
        )
        session.add_all([first, second])
        session.commit()
        session.refresh(first)
        session.refresh(second)

        assert re.fullmatch(r"REQ-\d{6}", first.identifier)
        assert re.fullmatch(r"BUG-\d{6}", second.identifier)
        # Both draw from the same global sequence.
        assert second.req_no == first.req_no + 1

        # Cleanup (locks cascade from work item deletes).
        session.query(WorkItem).filter(
            WorkItem.module_id == module.id
        ).delete(synchronize_session=False)
        session.delete(custom_type)
        session.delete(module)
        session.delete(owner)
        session.commit()
