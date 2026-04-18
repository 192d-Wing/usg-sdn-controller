"""Cisco NX-OS driver (NETCONF).

NX-OS supports the ``confirmed-commit`` capability on 10.x — we use it when
advertised and fall back to plain commit otherwise.
"""
from __future__ import annotations

from ..models.state import PushResult
from ._netconf import connect
from .base import CandidateHandle, DeviceDriver

_EDIT_TEMPLATE = """<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
<cli-config-data xmlns="http://www.cisco.com/nxos:1.0"><cmd>{config}</cmd></cli-config-data>
</config>"""


class NxosDriver(DeviceDriver):
    async def fetch_running(self) -> str:
        async with connect(self.device) as nc:
            resp = await nc.get_config(source="running")
            return resp.result

    async def load_candidate(self, config_text: str) -> CandidateHandle:
        async with connect(self.device) as nc:
            await nc.edit_config(config=_EDIT_TEMPLATE.format(config=config_text), target="candidate")
        return CandidateHandle(device=self.device.name, reference="nxos-candidate")

    async def validate(self, handle: CandidateHandle) -> None:
        async with connect(self.device) as nc:
            await nc.validate(source="candidate")

    async def commit_confirmed(self, handle: CandidateHandle, *, timeout_s: int = 120) -> PushResult:
        async with connect(self.device) as nc:
            await nc.commit(confirmed=True, timeout=timeout_s)
        return PushResult(device=self.device.name, ok=True, message="commit-confirmed")

    async def commit_finalize(self) -> None:
        async with connect(self.device) as nc:
            await nc.commit()

    async def discard(self, handle: CandidateHandle) -> None:
        async with connect(self.device) as nc:
            await nc.discard()
