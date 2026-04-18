"""Abstract vendor driver contract.

Each concrete driver must support:
  - fetch_running(): pull running config as text (for diff + hash).
  - load_candidate(): stage a candidate config (NETCONF <edit-config> or
    vendor-specific checkpoint).
  - commit_confirmed(timeout_s): commit with automatic rollback after timeout
    if commit-confirm is not re-confirmed. Falls back to standard commit if
    the OS doesn't support confirmed commits.
  - discard(): discard the staged candidate.
  - validate(): server-side validation where supported.

All methods are async.
"""
from __future__ import annotations

import abc
import hashlib
from dataclasses import dataclass

from ..models.inventory import Device
from ..models.state import PushResult


@dataclass
class CandidateHandle:
    """Opaque token returned by load_candidate to use during commit/discard."""

    device: str
    reference: str


class DeviceDriver(abc.ABC):
    def __init__(self, device: Device) -> None:
        self.device = device

    @abc.abstractmethod
    async def fetch_running(self) -> str: ...

    @abc.abstractmethod
    async def load_candidate(self, config_text: str) -> CandidateHandle: ...

    @abc.abstractmethod
    async def validate(self, handle: CandidateHandle) -> None: ...

    @abc.abstractmethod
    async def commit_confirmed(self, handle: CandidateHandle, *, timeout_s: int = 120) -> PushResult: ...

    @abc.abstractmethod
    async def commit_finalize(self) -> None: ...

    @abc.abstractmethod
    async def discard(self, handle: CandidateHandle) -> None: ...

    async def apply(self, config_text: str, *, timeout_s: int = 120) -> PushResult:
        handle = await self.load_candidate(config_text)
        try:
            await self.validate(handle)
            return await self.commit_confirmed(handle, timeout_s=timeout_s)
        except Exception:
            await self.discard(handle)
            raise

    @staticmethod
    def config_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
