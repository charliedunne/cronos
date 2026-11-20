"""End-to-end API flow tests (task 6.1).

These tests exercise the complete user journey across every layer of the
API — authentication, modules, requirements, and editing locks — with two
(or more) real users, rather than one endpoint at a time. The scenarios
mirror what the frontend performs: log in, create a module, add a
requirement, block it for editing, hit the lock conflict, hand the lock
over, and edit while holding it.

A second test fires genuinely concurrent lock attempts from several users
to prove that exactly one wins and every other attempt is rejected with
409 (the database primary key on ``locks.requirement_id`` is the source
of truth, design.md decision D5).
"""

import re
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Requirement, User
from app.security import hash_password

from conftest import _cleanup_user_data, _login_client


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_end_to_end_two_user_flow(client, user, second_user):
    """Full journey with two users: auth → module → requirement → lock.

    User A authenticates, creates a module and a requirement, then blocks
    the requirement for editing. User B is rejected from both locking
    (409 conflict) and editing (409). After A releases the lock, B takes
    it over, edits the requirement, and the edits persist with the lock
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

    # --- Requirement: A creates one with a system-assigned id ---------
    created = client.post(
        f"/api/v1/modules/{module_id}/requirements",
        json={"title": "e2e requirement", "text": "The system shall do the thing."},
    )
    assert created.status_code == 201
    body = created.json()
    requirement_id = body["id"]
    assert re.fullmatch(r"REQ-\d{6}", body["identifier"])
    # Defaults apply when status/priority are omitted.
    assert body["status"] == "draft"
    assert body["priority"] == "medium"
    assert body["locked_by"] is None

    # B can see the requirement and its (unlocked) state.
    b_listing = second_user["client"].get(f"/api/v1/modules/{module_id}/requirements")
    assert b_listing.status_code == 200
    entry = next(r for r in b_listing.json() if r["id"] == requirement_id)
    assert entry["locked_by"] is None

    # --- Lock: A blocks the requirement -------------------------------
    locked = client.post(f"/api/v1/requirements/{requirement_id}/lock")
    assert locked.status_code == 200
    assert locked.json()["locked_by"] == user["username"]

    # B's concurrent lock attempt is rejected with a conflict and does
    # not disturb A's lock.
    conflict = second_user["client"].post(
        f"/api/v1/requirements/{requirement_id}/lock"
    )
    assert conflict.status_code == 409

    holder_now = client.get(f"/api/v1/modules/{module_id}/requirements").json()
    entry = next(r for r in holder_now if r["id"] == requirement_id)
    assert entry["locked_by"] == user["username"]

    # B cannot edit a requirement locked by A; the data is unchanged.
    rejected_edit = second_user["client"].patch(
        f"/api/v1/requirements/{requirement_id}", json={"title": "hijacked"}
    )
    assert rejected_edit.status_code == 409
    with SessionLocal() as session:
        row = session.get(Requirement, requirement_id)
        assert row.title == "e2e requirement"

    # --- Handover: A releases, B locks and edits ----------------------
    released = client.delete(f"/api/v1/requirements/{requirement_id}/lock")
    assert released.status_code == 204

    b_locked = second_user["client"].post(
        f"/api/v1/requirements/{requirement_id}/lock"
    )
    assert b_locked.status_code == 200
    assert b_locked.json()["locked_by"] == second_user["username"]

    updated = second_user["client"].patch(
        f"/api/v1/requirements/{requirement_id}",
        json={
            "title": "e2e requirement (revised)",
            "text": "The system shall do the thing, better.",
            "status": "in-review",
            "priority": "high",
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["title"] == "e2e requirement (revised)"
    assert updated_body["text"] == "The system shall do the thing, better."
    assert updated_body["status"] == "in-review"
    assert updated_body["priority"] == "high"
    # The lock is retained by B across the update.
    assert updated_body["locked_by"] == second_user["username"]

    # The edits are visible to A in the module listing (persistence).
    a_listing = client.get(f"/api/v1/modules/{module_id}/requirements").json()
    entry = next(r for r in a_listing if r["id"] == requirement_id)
    assert entry["title"] == "e2e requirement (revised)"
    assert entry["status"] == "in-review"
    assert entry["locked_by"] == second_user["username"]

    # B releases the lock, leaving the module in a clean state.
    final_release = second_user["client"].delete(
        f"/api/v1/requirements/{requirement_id}/lock"
    )
    assert final_release.status_code == 204


def test_concurrent_lock_conflict_rejection(client, user):
    """Several users race for the same lock; exactly one wins.

    N throwaway users fire their lock requests simultaneously against one
    unlocked requirement. The primary key on ``locks.requirement_id``
    guarantees a single winner: one 200, and a 409 for every other
    attempt, with the winner recorded as holder.
    """
    participants = 5

    # A creates the module and requirement that will be contested.
    module = client.post("/api/v1/modules", json={"name": _new_name("e2e-race")})
    assert module.status_code == 201
    module_id = module.json()["id"]
    created = client.post(
        f"/api/v1/modules/{module_id}/requirements", json={"title": "contested"}
    )
    assert created.status_code == 201
    requirement_id = created.json()["id"]

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
            response = racer["client"].post(
                f"/api/v1/requirements/{requirement_id}/lock"
            )
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
        listing = client.get(f"/api/v1/modules/{module_id}/requirements").json()
        entry = next(r for r in listing if r["id"] == requirement_id)
        assert entry["locked_by"] == winners[0]
    finally:
        for racer in racers:
            racer["client"].close()
            _cleanup_user_data(racer["id"])
