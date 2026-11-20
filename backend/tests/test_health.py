"""Tests for the liveness probe endpoint."""


def test_healthz_returns_ok(client) -> None:
    """The /healthz endpoint responds 200 with status ok."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
