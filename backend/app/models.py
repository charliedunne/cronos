"""SQLAlchemy ORM models for the Cronos backend."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    """A top-level container for work items.

    Names are unique across all modules (spec: requirement-store); a module
    that still contains work items cannot be deleted, which the API enforces
    before issuing the DELETE (the FK is RESTRICT by default).
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

    #: Work items contained in this module.
    work_items: Mapped[list["WorkItem"]] = relationship(back_populates="module")


class WorkItemType(Base):
    """A kind of work item, defined and managed by administrators.

    Every work item is an instance of exactly one type (spec: work-items).
    ``id_prefix`` is the stable prefix rendered into each work item's
    human-readable identifier; built-in types (``is_builtin``) cannot be
    deleted or renamed (design.md decision D3).
    """

    __tablename__ = "work_item_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    id_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: The attribute definitions of this type, in display order. Positions
    #: are unique within a type (see the table constraint), and the id tie-
    #: break keeps the ordering deterministic regardless.
    attributes: Mapped[list["AttributeDefinition"]] = relationship(
        back_populates="type",
        cascade="all, delete-orphan",
        order_by="AttributeDefinition.position, AttributeDefinition.id",
    )


class AttributeDefinition(Base):
    """One typed attribute carried by the work items of a type.

    ``key`` is unique within the type and MUST NOT be a reserved system key
    (``title`` / ``id`` — spec: work-items, mandatory system attributes).
    ``options`` holds the allowed values for enum attributes; ``default_value``
    (JSONB) is applied when a work item omits the attribute. ``position``
    orders the attributes for display and is unique within the type (spec:
    work-items, attribute definitions); an omitted position is auto-assigned
    by the API so the attribute is appended after the existing ones.
    """

    __tablename__ = "attribute_definitions"
    __table_args__ = (
        UniqueConstraint("type_id", "key", name="uq_attribute_definitions_type_key"),
        UniqueConstraint(
            "type_id", "position", name="uq_attribute_definitions_type_position"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("work_item_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(16), nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_value: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The type this attribute belongs to.
    type: Mapped["WorkItemType"] = relationship(back_populates="attributes")


class WorkItem(Base):
    """A single element of a module, typed by a :class:`WorkItemType`.

    Every work item carries the mandatory system attributes — a non-empty
    ``title`` (first-class column) and a system-assigned identifier rendered
    as ``<TYPE_PREFIX>-<zero-padded seq>`` from the monotonically advancing
    global sequence, so identifiers are stable, unique, and never reused
    after deletion (design.md decisions D1/D2). All other attribute values
    live in the JSONB ``attributes`` column, keyed by the attribute
    definition's key. The type is set at creation and immutable.
    """

    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_requirements_title_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id"), nullable=False, index=True
    )
    type_id: Mapped[int] = mapped_column(
        ForeignKey("work_item_types.id"), nullable=False, index=True
    )
    req_no: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        default=Sequence("requirement_req_no_seq"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: The module this work item belongs to.
    module: Mapped["Module"] = relationship(back_populates="work_items")
    #: The type of this work item (immutable after creation).
    type: Mapped["WorkItemType"] = relationship()
    #: The exclusive editing lock, if any (at most one per work item).
    lock: Mapped["Lock | None"] = relationship(
        back_populates="work_item", uselist=False
    )

    @property
    def identifier(self) -> str:
        """The stable human-readable identifier (e.g. ``REQ-000042``)."""
        return f"{self.type.id_prefix}-{self.req_no:06d}"

    @property
    def locked_by(self) -> str | None:
        """The username of the current lock holder, or None when unlocked."""
        return self.lock.holder.username if self.lock else None


class Lock(Base):
    """An exclusive editing lock on a single work item.

    ``item_id`` is the primary key, so at most one lock row exists per work
    item; a concurrent second INSERT fails with a unique violation which the
    API maps to HTTP 409 (design.md decision D5). Locks persist until
    released by the holder or force-released by an administrator — there is
    no expiry in v1.
    """

    __tablename__ = "locks"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), primary_key=True
    )
    holder_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: The work item this lock protects.
    work_item: Mapped["WorkItem"] = relationship(back_populates="lock")
    #: The user holding the lock.
    holder: Mapped["User"] = relationship()
