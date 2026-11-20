"""End-to-end API flow tests (task 6.1).

These tests exercise the complete user journey across every layer of the
API — authentication, modules, work items, and editing locks — with two
(or more) real users, rather than one endpoint at a time. The scenarios
mirror what the frontend performs: log in, create a module, add a work
item, block it for editing, hit the lock conflict, hand the lock over,
and edit while holding it.

A second test fires genuinely concurrent lock attempts from several users
to prove that exactly one wins and every other attempt is rejected with
409 (the database primary key on ``locks.item_id`` is the source of
truth, design.md decision D5). A third test runs the same journey on a
non-requirement work item type to prove the flow is generic over types.
"""

import re
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User, WorkItem
from app.security import hash_password

from conftest import _cleanup_user_data, _login_client


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_end_to_end_two_user_flow(client, user, second_user):
    """Full journey with two users: auth → module → work item → lock.

    User A authenticates, creates a module and a built-in requirement work
    item, then blocks the item for editing. User B is rejected from both
    locking (409 conflict) and editing (409). After A releases the lock,
    B takes it over, edits the item, and the edits persist with the lock
    retained by B.
    """
    # --- Auth: unauthenticated access is rejected ---------------------
    with TestClient(app, base_url="https://testserver") as anon:
        assert anon.get("/api/v1/modules").status_code == 401

    # A's session (established by the fixture) resolves to the right user.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == user["username"]

    # --- Module: A creates one and it appears in the listing ----------
    module = client.post("/api/v1/modules", json={"name": _new_name("e2e-mod")})
    assert module.status_code == 201
    module_id = module.json()["id"]

    listing = client.get("/api/v1/modules")
    assert any(m["id"] == module_id for m in listing.json())

    # --- Work item: A creates one with a system-assigned id -----------
    created = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={
            "type_id": 1,
            "title": "e2e requirement",
            "attributes": {"text": "The system shall do the thing."},
        },
    )
    assert created.status_code == 201
    body = created.json()
    work_item_id = body["id"]
    assert re.fullmatch(r"REQ-\d{6}", body["identifier"])
    # Defaults apply when status/priority are omitted.
    assert body["attributes"]["status"] == "draft"
    assert body["attributes"]["priority"] == "medium"
    assert body["locked_by"] is None

    # B can see the work item and its (unlocked) state.
    b_listing = second_user["client"].get(f"/api/v1/modules/{module_id}/work-items")
    assert b_listing.status_code == 200
    entry = next(r for r in b_listing.json() if r["id"] == work_item_id)
    assert entry["locked_by"] is None

    # --- Lock: A blocks the work item ---------------------------------
    locked = client.post(f"/api/v1/work-items/{work_item_id}/lock")
    assert locked.status_code == 200
    assert locked.json()["locked_by"] == user["username"]

    # B's concurrent lock attempt is rejected with a conflict and does
    # not disturb A's lock.
    conflict = second_user["client"].post(f"/api/v1/work-items/{work_item_id}/lock")
    assert conflict.status_code == 409

    holder_now = client.get(f"/api/v1/modules/{module_id}/work-items").json()
    entry = next(r for r in holder_now if r["id"] == work_item_id)
    assert entry["locked_by"] == user["username"]

    # B cannot edit a work item locked by A; the data is unchanged.
    rejected_edit = second_user["client"].patch(
        f"/api/v1/work-items/{work_item_id}", json={"title": "hijacked"}
    )
    assert rejected_edit.status_code == 409
    with SessionLocal() as session:
        row = session.get(WorkItem, work_item_id)
        assert row.title == "e2e requirement"

    # --- Handover: A releases, B locks and edits ----------------------
    released = client.delete(f"/api/v1/work-items/{work_item_id}/lock")
    assert released.status_code == 204

    b_locked = second_user["client"].post(f"/api/v1/work-items/{work_item_id}/lock")
    assert b_locked.status_code == 200
    assert b_locked.json()["locked_by"] == second_user["username"]

    updated = second_user["client"].patch(
        f"/api/v1/work-items/{work_item_id}",
        json={
            "title": "e2e requirement (revised)",
            "attributes": {
                "text": "The system shall do the thing, better.",
                "status": "in-review",
                "priority": "high",
            },
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["title"] == "e2e requirement (revised)"
    assert updated_body["attributes"]["text"] == "The system shall do the thing, better."
    assert updated_body["attributes"]["status"] == "in-review"
    assert updated_body["attributes"]["priority"] == "high"
    # The lock is retained by B across the update.
    assert updated_body["locked_by"] == second_user["username"]

    # The edits are visible to A in the module listing (persistence).
    a_listing = client.get(f"/api/v1/modules/{module_id}/work-items").json()
    entry = next(r for r in a_listing if r["id"] == work_item_id)
    assert entry["title"] == "e2e requirement (revised)"
    assert entry["attributes"]["status"] == "in-review"
    assert entry["locked_by"] == second_user["username"]

    # B releases the lock, leaving the module in a clean state.
    final_release = second_user["client"].delete(f"/api/v1/work-items/{work_item_id}/lock")
    assert final_release.status_code == 204


def test_concurrent_lock_conflict_rejection(client, user):
    """Several users race for the same lock; exactly one wins.

    N throwaway users fire their lock requests simultaneously against one
    unlocked work item. The primary key on ``locks.item_id`` guarantees a
    single winner: one 200, and a 409 for every other attempt, with the
    winner recorded as holder.
    """
    participants = 5

    # A creates the module and work item that will be contested.
    module = client.post("/api/v1/modules", json={"name": _new_name("e2e-race")})
    assert module.status_code == 201
    module_id = module.json()["id"]
    created = client.post(
        f"/api/v1/modules/{module_id}/work-items",
        json={"type_id": 1, "title": "contested", "attributes": {}},
    )
    assert created.status_code == 201
    work_item_id = created.json()["id"]

    # Create the racing users directly in the database, each with its own
    # logged-in client (one per thread; test clients are not shared).
    racers: list[dict] = []
    try:
        for _ in range(participants):
            username = _new_name("racer")
            password = "racer-password-1"
            with SessionLocal() as session:
                racer = User(username=username, password_hash=hash_password(password))
                session.add(racer)
                session.commit()
                session.refresh(racer)
                racer_id = racer.id
            racers.append(
                {
                    "id": racer_id,
                    "username": username,
                    "client": _login_client(username, password),
                }
            )

        def attempt_lock(racer: dict) -> tuple[str, int]:
            response = racer["client"].post(f"/api/v1/work-items/{work_item_id}/lock")
            return racer["username"], response.status_code

        with ThreadPoolExecutor(max_workers=participants) as pool:
            results = list(pool.map(attempt_lock, racers))

        winners = [name for name, code in results if code == 200]
        rejected = [code for _, code in results if code != 200]

        # Exactly one winner; every other attempt hit the conflict.
        assert len(winners) == 1, f"expected one winner, got {results}"
        assert len(rejected) == participants - 1
        assert all(code == 409 for code in rejected)

        # The single winner is recorded as the holder.
        listing = client.get(f"/api/v1/modules/{module_id}/work-items").json()
        entry = next(r for r in listing if r["id"] == work_item_id)
        assert entry["locked_by"] == winners[0]
    finally:
        for racer in racers:
            racer["client"].close()
            _cleanup_user_data(racer["id"])


def test_non_requirement_type_full_flow(client, user, second_user, admin_client):
    """The full create/lock/edit journey works on a non-requirement type.

    An administrator registers a "test-case" type with its own identifier
    prefix; a regular user then creates an item of that type and the whole
    lock/edit flow behaves exactly as it does for built-in requirements.
    (task 5.4)
    """
    # --- Admin registers a custom type --------------------------------
    type_payload = {
        "name": _new_name("test-case"),
        "description": "Manual test case",
        "id_prefix": "TC",
        "attributes": [
            {"key": "steps", "label": "Steps", "data_type": "text", "required": True},
            {
                "key": "expected",
                "label": "Expected result",
                "data_type": "text",
            },
        ],
    }
    created_type = admin_client["client"].post("/api/v1/work-item-types", json=type_payload)
    assert created_type.status_code == 201
    type_id = created_type.json()["id"]

    try:
        # --- A creates a work item of the custom type -----------------
        module = client.post("/api/v1/modules", json={"name": _new_name("e2e-tc")})
        assert module.status_code == 201
        module_id = module.json()["id"]

        created = client.post(
            f"/api/v1/modules/{module_id}/work-items",
            json={
                "type_id": type_id,
                "title": "login test case",
                "attributes": {"steps": "enter credentials, submit"},
            },
        )
        assert created.status_code == 201
        body = created.json()
        work_item_id = body["id"]
        # The identifier uses the custom type's prefix.
        assert re.fullmatch(r"TC-\d{6}", body["identifier"])
        # The nested type object reflects the custom type.
        assert body["type"]["id"] == type_id
        assert body["type"]["name"] == type_payload["name"]
        assert body["type"]["id_prefix"] == "TC"
        assert body["type"]["is_builtin"] is False

        # --- Lock and edit flow on the custom item --------------------
        locked = client.post(f"/api/v1/work-items/{work_item_id}/lock")
        assert locked.status_code == 200

        conflict = second_user["client"].post(f"/api/v1/work-items/{work_item_id}/lock")
        assert conflict.status_code == 409

        updated = client.patch(
            f"/api/v1/work-items/{work_item_id}",
            json={
                "title": "login test case (revised)",
                "attributes": {
                    "steps": "enter credentials, submit",
                    "expected": "user is logged in",
                },
            },
        )
        assert updated.status_code == 200
        assert updated.json()["attributes"]["expected"] == "user is logged in"

        released = client.delete(f"/api/v1/work-items/{work_item_id}/lock")
        assert released.status_code == 204
    finally:
        # Remove the item (locks cascade), then the type itself, so that
        # fixture teardown does not have to deal with registry rows.
        with SessionLocal() as session:
            session.query(WorkItem).filter(WorkItem.id == work_item_id).delete()
            session.commit()
        deleted_type = admin_client["client"].delete(f"/api/v1/work-item-types/{type_id}")
        assert deleted_type.status_code == 204
