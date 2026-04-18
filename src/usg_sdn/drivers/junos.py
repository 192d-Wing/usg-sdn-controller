"""Juniper Junos driver (NETCONF, load-merge/commit-confirmed)."""
from __future__ import annotations

from ..models.state import PushResult
from ._netconf import connect
from .base import CandidateHandle, DeviceDriver

_LOAD_TEMPLATE = """<load-configuration action="merge" format="text">
<configuration-text>{config}</configuration-text>
</load-configuration>"""


class JunosDriver(DeviceDriver):
    async def fetch_running(self) -> str:
        async with connect(self.device) as nc:
            resp = await nc.get_config(source="running")
            return resp.result

    async def load_candidate(self, config_text: str) -> CandidateHandle:
        async with connect(self.device) as nc:
            await nc.rpc(filter_=_LOAD_TEMPLATE.format(config=config_text))
        return CandidateHandle(device=self.device.name, reference="junos-candidate")

    async def validate(self, handle: CandidateHandle) -> None:
        async with connect(self.device) as nc:
            await nc.validate(source="candidate")

    async def commit_confirmed(self, handle: CandidateHandle, *, timeout_s: int = 120) -> PushResult:
        async with connect(self.device) as nc:
            await nc.rpc(filter_=f'<commit-configuration><confirmed/><confirm-timeout>{max(1, timeout_s // 60)}</confirm-timeout></commit-configuration>')
        return PushResult(device=self.device.name, ok=True, message="commit-confirmed")

    async def commit_finalize(self) -> None:
        async with connect(self.device) as nc:
            await nc.commit()

    async def discard(self, handle: CandidateHandle) -> None:
        async with connect(self.device) as nc:
            await nc.discard()
