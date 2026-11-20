"""Tests for editing locks on work items (task 4.1)."""

import re
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Lock, Module, User, WorkItem
from app.security import hash_password


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _make_module_and_work_item(client) -> tuple[int, int]:
    """Create a module and one built-in requirement work item via the API.

    @param client An authenticated test client performing the calls.
    @return A tuple of (module_id, work_item_id).
    """
    module = client.post("/api/v1/modules", json={"name": _new_name("lockmod")})
    assert module.status_code == 201
    module_id = module.json()["id"]

    created = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "lockable", "attributes": {}},
    )
    assert created.status_code == 201
    return module_id, created.json()["id"]


def _module_id(work_item_id: int) -> int:
    """Find the module containing a work item via the ORM (test helper).

    @param work_item_id The work item whose module to look up.
    @return The containing module's id.
    """
    with SessionLocal() as session:
        row = session.get(WorkItem, work_item_id)
        return row.module_id


def test_second_lock_row_fails_at_database_level():
    """The locks table primary key rejects a second lock for one work item
    at the database level (task 4.1)."""
    username = _new_name("lockuser")
    module_name = _new_name("lockmodule")

    with SessionLocal() as session:
        user = User(username=username, password_hash=hash_password("pw"))
        session.add(user)
        session.commit()
        session.refresh(user)

        module = Module(name=module_name, created_by=user.id)
        session.add(module)
        session.commit()
        session.refresh(module)

        work_item = WorkItem(
            module_id=module.id, type_id=1, title="lockable", created_by=user.id
        )
        session.add(work_item)
        session.commit()
        session.refresh(work_item)
        work_item_id = work_item.id

        first = Lock(item_id=work_item_id, holder_id=user.id)
        session.add(first)
        session.commit()

        # A second lock row for the same work item violates the primary
        # key — this is what the API maps to HTTP 409 (design.md D5).
        second = Lock(item_id=work_item_id, holder_id=user.id)
        session.add(second)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Cleanup (locks cascade from the work item delete).
        session.query(WorkItem).filter(WorkItem.id == work_item_id).delete()
        session.query(Module).filter(Module.id == module.id).delete()
        session.query(User).filter(User.id == user.id).delete()
        session.commit()


def test_lock_records_holder_and_second_user_rejected(client, user, second_user):
    """Locking an unlocked work item records the holder; a second user's
    attempt is rejected with 409 and the original lock is unchanged."""
    _, item_id = _make_module_and_work_item(client)

    locked = client.post(f"/api/v1/work-items/{item_id}/lock")
    assert locked.status_code == 200
    assert locked.json()["locked_by"] == user["username"]

    conflict = second_user["client"].post(f"/api/v1/work-items/{item_id}/lock")
    assert conflict.status_code == 409

    listing = client.get(f"/api/v1/modules/{_module_id(item_id)}/work-items")
    entry = next(r for r in listing.json() if r["id"] == item_id)
    assert entry["locked_by"] == user["username"]


def test_release_unlocks_and_non_holder_cannot_release(client, user, second_user):
    """The holder can release; a non-holder cannot (403); after release any
    authenticated user can lock the work item."""
    _, item_id = _make_module_and_work_item(client)

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    forbidden = second_user["client"].delete(f"/api/v1/work-items/{item_id}/lock")
    assert forbidden.status_code == 403

    released = client.delete(f"/api/v1/work-items/{item_id}/lock")
    assert released.status_code == 204

    # After release, another user can immediately lock it.
    re_locked = second_user["client"].post(f"/api/v1/work-items/{item_id}/lock")
    assert re_locked.status_code == 200
    assert re_locked.json()["locked_by"] == second_user["username"]


def test_admin_can_force_release_any_lock(client, user, admin_client):
    """An administrator can force-release a lock held by another user; the
    work item then becomes lockable again. Force-releasing an already
    unlocked item is rejected with 409."""
    _, item_id = _make_module_and_work_item(client)

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    forced = admin_client["client"].post(f"/api/v1/work-items/{item_id}/force-release")
    assert forced.status_code == 200
    assert forced.json()["locked_by"] is None

    # Force-releasing an already unlocked work item is rejected.
    again = admin_client["client"].post(f"/api/v1/work-items/{item_id}/force-release")
    assert again.status_code == 409


def test_update_without_lock_rejected_and_holder_update_retains_lock(client, user):
    """Updates without a lock are rejected; the holder's update succeeds and
    the lock is retained."""
    _, item_id = _make_module_and_work_item(client)

    rejected = client.patch(f"/api/v1/work-items/{item_id}", json={"title": "nope"})
    assert rejected.status_code == 409

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    updated = client.patch(
        f"/api/v1/work-items/{item_id}",
        json={
            "title": "updated title",
            "attributes": {"text": "updated text", "status": "approved", "priority": "high"},
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "updated title"
    assert body["attributes"]["text"] == "updated text"
    assert body["attributes"]["status"] == "approved"
    assert body["attributes"]["priority"] == "high"
    assert body["locked_by"] == user["username"]


def test_non_holder_update_rejected_and_work_item_unchanged(client, user, second_user):
    """A non-holder's update is rejected and the work item is unchanged."""
    _, item_id = _make_module_and_work_item(client)

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    rejected = second_user["client"].patch(
        f"/api/v1/work-items/{item_id}", json={"title": "hijacked"}
    )
    assert rejected.status_code == 409

    with SessionLocal() as session:
        row = session.get(WorkItem, item_id)
        assert row.title == "lockable"


def test_holder_deletes_work_item_and_identifier_not_reused(client, user):
    """Deleting without a lock is rejected; the holder's deletion removes the
    work item and its identifier is never reused."""
    module = client.post("/api/v1/modules", json={"name": _new_name("delmod")})
    assert module.status_code == 201
    module_id = module.json()["id"]

    first = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "first", "attributes": {}},
    )
    second = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "second", "attributes": {}},
    )
    assert first.status_code == 201 and second.status_code == 201
    first_id, second_id = first.json()["id"], second.json()["id"]
    first_identifier = first.json()["identifier"]

    # Deleting without holding the lock is rejected.
    rejected = client.delete(f"/api/v1/work-items/{first_id}")
    assert rejected.status_code == 409

    assert client.post(f"/api/v1/work-items/{first_id}/lock").status_code == 200
    deleted = client.delete(f"/api/v1/work-items/{first_id}")
    assert deleted.status_code == 204

    # A new work item must not reuse the deleted identifier.
    third = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "third", "attributes": {}},
    )
    assert third.status_code == 201
    third_body = third.json()
    assert third_body["identifier"] != first_identifier
    assert re.fullmatch(r"REQ-\d{6}", third_body["identifier"])

    listing = client.get(f"/api/v1/modules/{module_id}/work-items")
    identifiers = [r["identifier"] for r in listing.json()]
    assert first_identifier not in identifiers
    assert len(identifiers) == 2
    assert {second_id, third_body["id"]} == {r["id"] for r in listing.json()}


def test_lock_survives_logout(client, user):
    """A lock persists across the holder's logout and re-login; it remains
    releasable by the same user."""
    _, item_id = _make_module_and_work_item(client)

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    # Log out: the session is revoked and the cookie cleared.
    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    assert (
        client.get(f"/api/v1/modules/{_module_id(item_id)}/work-items").status_code
        == 401
    )

    # Log back in as the same user.
    relogin = client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    assert relogin.status_code == 200

    module_id = _module_id(item_id)
    listing = client.get(f"/api/v1/modules/{module_id}/work-items")
    entry = next(r for r in listing.json() if r["id"] == item_id)
    assert entry["locked_by"] == user["username"]

    # The same user can still release their own lock.
    released = client.delete(f"/api/v1/work-items/{item_id}/lock")
    assert released.status_code == 204


def test_lock_visible_to_other_users(client, user, second_user):
    """Another user's module listing shows the lock state and holder."""
    _, item_id = _make_module_and_work_item(client)

    assert client.post(f"/api/v1/work-items/{item_id}/lock").status_code == 200

    module_id = _module_id(item_id)
    listing = second_user["client"].get(f"/api/v1/modules/{module_id}/work-items")
    assert listing.status_code == 200
    entry = next(r for r in listing.json() if r["id"] == item_id)
    assert entry["locked_by"] == user["username"]
