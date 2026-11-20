"""API tests for the module management endpoints (task 3.2).

Tests take both ``client`` and ``user``: the ``user`` fixture logs the
shared client in as a temporary regular user, so ``client`` performs the
authenticated calls while ``user`` carries the account's metadata.
"""

import uuid

from app.db import SessionLocal
from app.models import Requirement


def _new_name(prefix: str) -> str:
    """Build a collision-free name for this test run."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_create_module_and_list(client, user):
    """A module created with a unique name appears in the module list."""
    name = _new_name("mod")
    response = client.post("/api/v1/modules", json={"name": name})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == name

    listing = client.get("/api/v1/modules")
    assert listing.status_code == 200
    assert any(m["name"] == name for m in listing.json())


def test_duplicate_module_name_rejected(client, user):
    """Creating a module with an already used name yields 409."""
    name = _new_name("dupmod")
    first = client.post("/api/v1/modules", json={"name": name})
    assert first.status_code == 201

    second = client.post("/api/v1/modules", json={"name": name})
    assert second.status_code == 409


def test_rename_module_and_conflict(client, user):
    """Renaming works; renaming to a name already in use yields 409."""
    name_a = _new_name("moda")
    name_b = _new_name("modb")
    mod_a = client.post("/api/v1/modules", json={"name": name_a})
    assert mod_a.status_code == 201
    module_id = mod_a.json()["id"]
    mod_b = client.post("/api/v1/modules", json={"name": name_b})
    assert mod_b.status_code == 201

    conflict = client.patch(f"/api/v1/modules/{module_id}", json={"name": name_b})
    assert conflict.status_code == 409

    new_name = _new_name("modc")
    renamed = client.patch(f"/api/v1/modules/{module_id}", json={"name": new_name})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == new_name


def test_delete_non_empty_module_rejected(client, user):
    """Deleting a module that still has requirements yields 409 and the
    requirement remains intact."""
    name = _new_name("fullmod")
    created = client.post("/api/v1/modules", json={"name": name})
    assert created.status_code == 201
    module_id = created.json()["id"]

    # Add a requirement directly through the ORM (requirement endpoints
    # land in task 3.3).
    with SessionLocal() as session:
        requirement = Requirement(
            module_id=module_id, title="keep me", created_by=user["id"]
        )
        session.add(requirement)
        session.commit()

    deleted = client.delete(f"/api/v1/modules/{module_id}")
    assert deleted.status_code == 409

    with SessionLocal() as session:
        still_there = (
            session.query(Requirement)
            .filter(Requirement.module_id == module_id)
            .first()
        )
        assert still_there is not None


def test_delete_empty_module_succeeds(client, user):
    """Deleting an empty module yields 204 and removes it from the list."""
    name = _new_name("emptymod")
    created = client.post("/api/v1/modules", json={"name": name})
    assert created.status_code == 201
    module_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/modules/{module_id}")
    assert deleted.status_code == 204

    listing = client.get("/api/v1/modules")
    assert listing.status_code == 200
    assert not any(m["id"] == module_id for m in listing.json())


def test_module_endpoints_require_authentication(client):
    """Unauthenticated requests to the module endpoints yield 401."""
    assert client.get("/api/v1/modules").status_code == 401
    assert (
        client.post("/api/v1/modules", json={"name": _new_name("anon")}).status_code
        == 401
    )
