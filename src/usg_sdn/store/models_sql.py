"""SQLAlchemy ORM mappings for persisted intent, inventory, and state."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, TimestampMixin


class IntentRow(Base, TimestampMixin):
    __tablename__ = "intent"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)


class DeviceRow(Base, TimestampMixin):
    __tablename__ = "device"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    vendor: Mapped[str] = mapped_column(String(16), nullable=False)
    mgmt_address: Mapped[str] = mapped_column(String(64), nullable=False)
    os_version: Mapped[str | None] = mapped_column(String(64))
    credential: Mapped[dict] = mapped_column(JSON, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)


class DeviceStateRow(Base, TimestampMixin):
    __tablename__ = "device_state"

    device: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    running_config_hash: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(Text)
    rendered_config: Mapped[str | None] = mapped_column(Text)


class ApiTokenRow(Base, TimestampMixin):
    """Persistent API tokens (hashed)."""

    __tablename__ = "api_token"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LinkAddressRow(Base, TimestampMixin):
    """Persistent /127 allocation for a fabric link.

    ``link_key`` is ``"{lo_node}:{lo_iface}|{hi_node}:{hi_iface}"`` in canonical
    lexicographic order — independent of how the operator wrote the Link.
    """

    __tablename__ = "link_address"

    link_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    subnet: Mapped[str] = mapped_column(String(64), nullable=False)
    a_addr: Mapped[str] = mapped_column(String(64), nullable=False)
    b_addr: Mapped[str] = mapped_column(String(64), nullable=False)
