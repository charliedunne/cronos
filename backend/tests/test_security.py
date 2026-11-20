"""Unit tests for the Argon2id password hashing utility."""

from app.security import hash_password, verify_password


def test_hash_verify_round_trip() -> None:
    """A freshly hashed password verifies successfully."""
    stored = hash_password("correct horse battery staple")
    assert verify_password(stored, "correct horse battery staple") is True


def test_wrong_password_is_rejected() -> None:
    """A different password does not verify against the hash."""
    stored = hash_password("correct horse battery staple")
    assert verify_password(stored, "wrong password") is False


def test_hashes_are_salted_and_unique() -> None:
    """Hashing the same password twice yields different encoded hashes."""
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second
    # Both must still verify against the original plaintext.
    assert verify_password(first, "same-password") is True
    assert verify_password(second, "same-password") is True


def test_invalid_stored_hash_returns_false() -> None:
    """A malformed stored hash yields False instead of raising."""
    assert verify_password("not-a-valid-argon2-hash", "anything") is False
