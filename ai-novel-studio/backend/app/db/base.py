"""SQLAlchemy declarative base and shared column mixins.

Every table follows the conventions from the design document:

* a prefixed string primary key (``proj_…``, ``chap_…``);
* ``created_at`` / ``updated_at`` timestamps;
* a monotonically increasing ``row_version`` used for optimistic concurrency;
* a soft-delete marker so history and vectors are never silently destroyed.

``schema_version`` on the root table records the *file format* version, which
is deliberately separate from the application version.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Creation / modification timestamps maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class RowVersionMixin:
    """Optimistic concurrency counter, bumped on every update."""

    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class SoftDeleteMixin:
    """Soft deletion; retrieval and queries must filter these rows out."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="0",
        index=True,
    )


class SchemaVersionMixin:
    """File-format version, used by the migration runner."""

    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
