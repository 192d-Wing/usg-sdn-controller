"""Operational-state records produced by the renderer and drivers."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DeviceStatus(StrEnum):
    UNKNOWN = "unknown"
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    DRIFT = "drift"
    IN_SYNC = "in-sync"
    ERROR = "error"


class RenderBundle(BaseModel):
    """Rendered per-device artifacts."""

    model_config = ConfigDict(frozen=True)

    device: str
    vendor: str
    config_text: str = Field(description="Vendor-native CLI/XML text.")
    structured: dict | None = Field(default=None, description="Optional structured payload (NETCONF XML fragments, REST JSON).")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeviceState(BaseModel):
    model_config = ConfigDict(frozen=True)

    device: str
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_seen: datetime | None = None
    running_config_hash: str | None = None
    message: str | None = None


class PushResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    device: str
    ok: bool
    message: str = ""
    diff: str | None = None
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
