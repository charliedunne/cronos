"""SQLAlchemy ORM models for the Cronos backend."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    """An application user account.

    Credentials are stored as an Argon2id hash; ``is_active`` gates login
    (a disabled account cannot authenticate) and ``is_admin`` grants access
    to administrative endpoints such as account management.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: Sessions currently associated with this user.
    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    """An authenticated user session backed by an opaque random token.

    The token is the primary key and is delivered to the client as an
    httpOnly cookie (see design.md decision D2). A session is valid while
    ``revoked_at`` is NULL; logout or account disablement sets it.
    """

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: The user this session belongs to.
    user: Mapped["User"] = relationship(back_populates="sessions")


class Module(Base):
    """A top-level container for requirements.

    Names are unique across all modules (spec: requirement-store); a module
    that still contains requirements cannot be deleted, which the API
    enforces before issuing the DELETE (the FK is RESTRICT by default).
    """

    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: Requirements contained in this module.
    requirements: Mapped[list["Requirement"]] = relationship(back_populates="module")


class Requirement(Base):
    """A single requirement with a fixed attribute set.

    The human-readable identifier ("REQ-" + zero-padded number) is derived
    from ``req_no``, which is drawn from a monotonically advancing sequence,
    so identifiers are stable, unique, and never reused after deletion
    (design.md decision D4).
    """

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_requirements_title_nonempty"),
        CheckConstraint(
            "status IN ('draft', 'in-review', 'approved', 'deprecated')",
            name="ck_requirements_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="ck_requirements_priority",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id"), nullable=False, index=True
    )
    req_no: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        default=Sequence("requirement_req_no_seq"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium"
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: The module this requirement belongs to.
    module: Mapped["Module"] = relationship(back_populates="requirements")
    #: The exclusive editing lock, if any (at most one per requirement).
    lock: Mapped["Lock | None"] = relationship(
        back_populates="requirement", uselist=False
    )

    @property
    def identifier(self) -> str:
        """The stable human-readable identifier (e.g. ``REQ-000042``)."""
        return f"REQ-{self.req_no:06d}"

    @property
    def locked_by(self) -> str | None:
        """The username of the current lock holder, or None when unlocked."""
        return self.lock.holder.username if self.lock else None


class Lock(Base):
    """An exclusive editing lock on a single requirement.

    ``requirement_id`` is the primary key, so at most one lock row exists
    per requirement; a concurrent second INSERT fails with a unique
    violation which the API maps to HTTP 409 (design.md decision D5).
    Locks persist until released by the holder or force-released by an
    administrator — there is no expiry in v1.
    """

    __tablename__ = "locks"

    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )
    holder_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: The requirement this lock protects.
    requirement: Mapped["Requirement"] = relationship(back_populates="lock")
    #: The user holding the lock.
    holder: Mapped["User"] = relationship()
