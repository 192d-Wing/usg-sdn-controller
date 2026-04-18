"""Desired/running state reconciler.

Every ``reconcile_interval_sec`` seconds the reconciler:
  1. loads the stored IntentDocument
  2. for each device in inventory, renders desired config
  3. fetches running config, computes diff + hash
  4. marks state as IN_SYNC / DRIFT / UNREACHABLE

**It does not push by default.** Pushes require an explicit CLI / API call.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..allocator import allocate_persistent
from ..drivers import driver_for
from ..logging import log
from ..models.inventory import Device
from ..models.state import DeviceStatus, PushResult
from ..render import config_diff, render_device
from ..store import DeviceRepo, IntentRepo, StateRepo, get_session


@dataclass
class DriftReport:
    device: str
    status: DeviceStatus
    diff: str
    message: str = ""


async def reconcile_once() -> list[DriftReport]:
    reports: list[DriftReport] = []
    async for session in get_session():
        intent = await IntentRepo(session).load()
        if intent is None:
            log.warning("no intent document stored, skipping reconciliation")
            return reports
        allocations = await allocate_persistent(intent.fabric, session)
        devices = await DeviceRepo(session).list()
        state_repo = StateRepo(session)
        for device in devices:
            reports.append(await _reconcile_device(device, intent, state_repo, allocations))
    return reports


async def _reconcile_device(device: Device, intent, state_repo: StateRepo, allocations) -> DriftReport:
    try:
        bundle = render_device(intent, device, allocations=allocations)
    except Exception as e:
        await state_repo.set(device.name, DeviceStatus.ERROR, message=f"render failed: {e}")
        return DriftReport(device=device.name, status=DeviceStatus.ERROR, diff="", message=str(e))

    drv = driver_for(device)
    try:
        running = await drv.fetch_running()
    except Exception as e:
        await state_repo.set(device.name, DeviceStatus.UNREACHABLE, message=str(e))
        return DriftReport(device=device.name, status=DeviceStatus.UNREACHABLE, diff="", message=str(e))

    diff = config_diff(running, bundle.config_text)
    status = DeviceStatus.IN_SYNC if not diff else DeviceStatus.DRIFT
    await state_repo.set(
        device.name,
        status,
        running_config_hash=drv.config_hash(running),
        rendered_config=bundle.config_text,
    )
    return DriftReport(device=device.name, status=status, diff=diff)


async def push_device(device_name: str, *, finalize: bool = True, timeout_s: int = 120) -> PushResult:
    async for session in get_session():
        device = await DeviceRepo(session).get(device_name)
        if device is None:
            return PushResult(device=device_name, ok=False, message="unknown device")
        intent = await IntentRepo(session).load()
        if intent is None:
            return PushResult(device=device_name, ok=False, message="no intent")
        allocations = await allocate_persistent(intent.fabric, session)
        bundle = render_device(intent, device, allocations=allocations)
        drv = driver_for(device)
        result = await drv.apply(bundle.config_text, timeout_s=timeout_s)
        if finalize and result.ok:
            try:
                await drv.commit_finalize()
            except Exception as e:
                return PushResult(device=device_name, ok=False, message=f"finalize failed: {e}")
        return result
    return PushResult(device=device_name, ok=False, message="session unavailable")


class Reconciler:
    def __init__(self, interval_sec: int) -> None:
        self.interval_sec = interval_sec
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                reports = await reconcile_once()
                drifted = sum(1 for r in reports if r.status == DeviceStatus.DRIFT)
                log.info("reconcile-tick", devices=len(reports), drifted=drifted)
            except Exception as e:
                log.error("reconcile-error", error=str(e))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_sec)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="reconciler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
