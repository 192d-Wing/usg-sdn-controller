"""SQLAlchemy ORM mappings for persisted intent, inventory, and state."""
from __future__ import annotations

from sqlalchemy import JSON, String, Text
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
