"""Tests for the requirement store (tasks 3.1-3.4)."""

import re
import uuid

from app.db import SessionLocal
from app.models import Module, Requirement, User
from app.security import hash_password


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _create_module(client, name: str | None = None) -> int:
    """Create a module through the API and return its id.

    @param client An authenticated test client performing the call.
    @param name Optional explicit name; a collision-free one is generated.
    @return The created module's id.
    """
    response = client.post(
        "/api/v1/modules", json={"name": name or _new_name("reqmod")}
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_requirement_returns_identifier(client, user):
    """A created requirement returns its assigned identifier and defaults
    (task 3.3)."""
    module_id = _create_module(client)

    created = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "First"}
    )
    assert created.status_code == 201
    body = created.json()
    assert re.fullmatch(r"REQ-\d{6}", body["identifier"])
    assert body["title"] == "First"
    assert body["text"] == ""
    assert body["status"] == "draft"
    assert body["priority"] == "medium"
    assert body["locked_by"] is None

    # Creating in a non-existent module yields 404.
    missing = client.post(
        "/api/v1/modules/99999999/requirements", json={"title": "ghost"}
    )
    assert missing.status_code == 404


def test_listing_includes_all_attributes_and_lock_state(client, user):
    """The module listing includes every attribute plus lock state (3.3)."""
    module_id = _create_module(client)

    client.post(
        f"/api/v1/modules/{module_id}/requirements",
        json={
            "title": "alpha",
            "text": "body text",
            "status": "in-review",
            "priority": "high",
        },
    )
    created = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "beta"}
    )
    requirement_id = created.json()["id"]

    # Lock one of them so the listing shows a non-null holder.
    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    listing = client.get(f"/api/v1/modules/{module_id}/requirements")
    assert listing.status_code == 200
    entries = {r["title"]: r for r in listing.json()}
    assert set(entries) == {"alpha", "beta"}

    alpha = entries["alpha"]
    for key in ("id", "identifier", "title", "text", "status", "priority", "locked_by"):
        assert key in alpha
    assert alpha["text"] == "body text"
    assert alpha["status"] == "in-review"
    assert alpha["priority"] == "high"
    assert alpha["locked_by"] is None

    beta = entries["beta"]
    assert beta["locked_by"] == user["username"]


def test_create_rejects_empty_title_and_invalid_enums(client, user):
    """Create rejects an empty title and invalid status/priority values with
    422 (task 3.4)."""
    module_id = _create_module(client)

    empty_title = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "   "}
    )
    assert empty_title.status_code == 422

    bad_status = client.post(
        f"/api/v1/modules/{module_id}/requirements",
        json={"title": "ok", "status": "shipped"},
    )
    assert bad_status.status_code == 422

    bad_priority = client.post(
        f"/api/v1/modules/{module_id}/requirements",
        json={"title": "ok", "priority": "urgent"},
    )
    assert bad_priority.status_code == 422

    # Nothing was created by the rejected payloads.
    listing = client.get(f"/api/v1/modules/{module_id}/requirements")
    assert listing.json() == []


def test_update_rejects_invalid_values_and_leaves_requirement_unchanged(
    client, user
):
    """Update rejects an empty title and invalid enum values with 422 and
    leaves the requirement unchanged (task 3.4)."""
    module_id = _create_module(client)
    created = client.post(
        f"/api/v1/modules/{module_id}/requirements",
        json={"title": "original", "status": "approved", "priority": "high"},
    )
    requirement_id = created.json()["id"]

    # The update endpoint requires the lock (editing-locks spec).
    assert client.post(f"/api/v1/requirements/{requirement_id}/lock").status_code == 200

    empty_title = client.patch(
        f"/api/v1/requirements/{requirement_id}", json={"title": ""}
    )
    assert empty_title.status_code == 422

    bad_status = client.patch(
        f"/api/v1/requirements/{requirement_id}", json={"status": "shipped"}
    )
    assert bad_status.status_code == 422

    bad_priority = client.patch(
        f"/api/v1/requirements/{requirement_id}", json={"priority": "urgent"}
    )
    assert bad_priority.status_code == 422

    # The requirement is unchanged and still locked.
    fetched = client.get(f"/api/v1/modules/{module_id}/requirements")
    entry = next(r for r in fetched.json() if r["id"] == requirement_id)
    assert entry["title"] == "original"
    assert entry["status"] == "approved"
    assert entry["priority"] == "high"
    assert entry["locked_by"] == user["username"]


def test_module_and_requirement_defaults() -> None:
    """A requirement created in a module gets defaults draft/medium and a
    REQ- identifier; rows are cleaned up afterwards."""
    username = _new_name("requser")
    module_name = _new_name("reqmodule")

    with SessionLocal() as session:
        user = User(username=username, password_hash=hash_password("pw"))
        session.add(user)
        session.commit()
        session.refresh(user)

        module = Module(name=module_name, created_by=user.id)
        session.add(module)
        session.commit()
        session.refresh(module)
        assert module.id is not None

        requirement = Requirement(
            module_id=module.id, title="A sample requirement", created_by=user.id
        )
        session.add(requirement)
        session.commit()
        session.refresh(requirement)

        # Defaults from the spec: status draft, priority medium.
        assert requirement.status == "draft"
        assert requirement.priority == "medium"
        assert requirement.text == ""

        # Identifier format: REQ- followed by a zero-padded number.
        assert re.fullmatch(r"REQ-\d{6}", requirement.identifier)
        assert requirement.req_no is not None and requirement.req_no >= 1

        # Cleanup (requirements first — FK to modules).
        session.query(Requirement).filter(Requirement.id == requirement.id).delete()
        session.query(Module).filter(Module.id == module.id).delete()
        session.query(User).filter(User.id == user.id).delete()
        session.commit()


def test_req_no_sequence_advances_and_never_repeats() -> None:
    """Two requirements created in sequence get distinct, increasing
    req_no values (the sequence only advances)."""
    username = _new_name("sequser")
    module_name = _new_name("seqmodule")

    with SessionLocal() as session:
        user = User(username=username, password_hash=hash_password("pw"))
        session.add(user)
        session.commit()
        session.refresh(user)

        module = Module(name=module_name, created_by=user.id)
        session.add(module)
        session.commit()
        session.refresh(module)

        first = Requirement(module_id=module.id, title="first", created_by=user.id)
        second = Requirement(module_id=module.id, title="second", created_by=user.id)
        session.add_all([first, second])
        session.commit()
        session.refresh(first)
        session.refresh(second)

        assert first.req_no < second.req_no
        assert first.identifier != second.identifier

        # Cleanup.
        session.query(Requirement).filter(Requirement.module_id == module.id).delete()
        session.query(Module).filter(Module.id == module.id).delete()
        session.query(User).filter(User.id == user.id).delete()
        session.commit()
