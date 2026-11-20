"""Password hashing utilities.

Passwords are hashed with Argon2id (see design.md decision D3) using the
current OWASP-recommended minimum parameters: memory cost 19 MiB, time cost
2, parallelism 1.
"""

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

#: Argon2id hasher configured with OWASP-recommended minimum parameters.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(plain: str) -> str:
    """Hash a plaintext password with Argon2id.

    @param plain The plaintext password to hash.
    @return The encoded Argon2id hash string (parameters, salt, digest).
    """
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    """Verify a plaintext password against a stored Argon2id hash.

    @param stored_hash The encoded Argon2id hash to check against.
    @param plain The candidate plaintext password.
    @return True if the password matches the hash; False on mismatch or if
        the stored value is not a valid hash for this configuration.
    """
    try:
        return _hasher.verify(stored_hash, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError, HashingError):
        # Mismatch or malformed/invalid stored hash: treat as "no match" so
        # callers get a uniform rejection without leaking error details.
        return False
