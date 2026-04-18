"""Aruba AOS-CX driver using the REST API (pyaoscx).

AOS-CX 10.x supports a "checkpoint" model: we create a checkpoint of the
running config before changes, then either ``checkpoint rollback`` on failure
or ``copy running startup`` on success.

Because AOS-CX REST is not fully idempotent for flat CLI text, we push the
rendered config via the CLI endpoint and rely on checkpoints for rollback.
"""
from __future__ import annotations

import asyncio
from functools import partial

import httpx

from ..config import settings
from ..models.state import PushResult
from .base import CandidateHandle, DeviceDriver


class AosCxDriver(DeviceDriver):
    def _base_url(self) -> str:
        return f"https://{self.device.mgmt_address}:{self.device.aoscx_rest_port}/rest/v10.13"

    async def _login(self, client: httpx.AsyncClient) -> None:
        user = self.device.credential.username or settings.aoscx_user
        password = (
            self.device.credential.password.get_secret_value()
            if self.device.credential.password is not None
            else settings.aoscx_password
        )
        r = await client.post(
            f"{self._base_url()}/login",
            params={"username": user, "password": password},
        )
        r.raise_for_status()

    async def _logout(self, client: httpx.AsyncClient) -> None:
        await client.post(f"{self._base_url()}/logout")

    async def fetch_running(self) -> str:
        async with httpx.AsyncClient(verify=settings.aoscx_verify_tls, timeout=30) as client:
            await self._login(client)
            try:
                r = await client.get(
                    f"{self._base_url()}/fullconfigs/running-config",
                    params={"type": "cli"},
                )
                r.raise_for_status()
                return r.text
            finally:
                await self._logout(client)

    async def _cli_exec(self, client: httpx.AsyncClient, cmds: list[str]) -> None:
        for cmd in cmds:
            r = await client.post(
                f"{self._base_url()}/cli",
                json={"cmd": cmd},
            )
            r.raise_for_status()

    async def load_candidate(self, config_text: str) -> CandidateHandle:
        checkpoint = f"sdn-{int(asyncio.get_event_loop().time())}"
        async with httpx.AsyncClient(verify=settings.aoscx_verify_tls, timeout=60) as client:
            await self._login(client)
            try:
                await self._cli_exec(client, [f"checkpoint post-config {checkpoint}"])
                await self._cli_exec(client, config_text.splitlines())
            finally:
                await self._logout(client)
        return CandidateHandle(device=self.device.name, reference=checkpoint)

    async def validate(self, handle: CandidateHandle) -> None:
        # AOS-CX applies commands as they come; no separate validate phase.
        return None

    async def commit_confirmed(self, handle: CandidateHandle, *, timeout_s: int = 120) -> PushResult:
        # AOS-CX doesn't have true commit-confirm. We treat the checkpoint
        # as the rollback target and let the reconciler finalize/discard.
        return PushResult(
            device=self.device.name,
            ok=True,
            message=f"applied; rollback target checkpoint={handle.reference}",
        )

    async def commit_finalize(self) -> None:
        async with httpx.AsyncClient(verify=settings.aoscx_verify_tls, timeout=30) as client:
            await self._login(client)
            try:
                await self._cli_exec(client, ["write memory"])
            finally:
                await self._logout(client)

    async def discard(self, handle: CandidateHandle) -> None:
        async with httpx.AsyncClient(verify=settings.aoscx_verify_tls, timeout=60) as client:
            await self._login(client)
            try:
                await self._cli_exec(client, [f"checkpoint rollback {handle.reference}"])
            finally:
                await self._logout(client)


_ = partial  # silence unused import when trimmed
