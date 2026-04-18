"""Render / diff / push operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...allocator import allocate_persistent, pool_stats
from ...config import settings
from ...reconciler import reconcile_once
from ...reconciler.loop import push_device
from ...render import config_diff, render_device
from ...store import DeviceRepo, IntentRepo, get_session

router = APIRouter()


class RenderResponse(BaseModel):
    device: str
    vendor: str
    config_text: str


@router.post("/render", response_model=RenderResponse)
async def render(
    device_name: str = Query(alias="device"),
    session: AsyncSession = Depends(get_session),
) -> RenderResponse:
    device = await DeviceRepo(session).get(device_name)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown device")
    intent = await IntentRepo(session).load()
    if intent is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "no intent stored")
    allocations = await allocate_persistent(intent.fabric, session)
    bundle = render_device(intent, device, allocations=allocations)
    return RenderResponse(device=bundle.device, vendor=bundle.vendor, config_text=bundle.config_text)


class DiffResponse(BaseModel):
    device: str
    drift: bool
    diff: str


@router.post("/diff", response_model=DiffResponse)
async def diff(
    device_name: str = Query(alias="device"),
    session: AsyncSession = Depends(get_session),
) -> DiffResponse:
    from ...drivers import driver_for  # local import to avoid import cycles at startup

    device = await DeviceRepo(session).get(device_name)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown device")
    intent = await IntentRepo(session).load()
    if intent is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "no intent stored")
    allocations = await allocate_persistent(intent.fabric, session)
    bundle = render_device(intent, device, allocations=allocations)
    running = await driver_for(device).fetch_running()
    d = config_diff(running, bundle.config_text)
    return DiffResponse(device=device_name, drift=bool(d), diff=d)


@router.post("/push")
async def push(
    device_name: str = Query(alias="device"),
    confirm: bool = Query(default=False, description="Must be true to push."),
    timeout_s: int = Query(default=120, ge=10, le=600),
) -> dict:
    if not confirm:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "confirm=true is required to push config to a device",
        )
    result = await push_device(device_name, timeout_s=timeout_s)
    if not result.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, result.message)
    return result.model_dump(mode="json")


class PoolStatusResponse(BaseModel):
    pool: str
    prefix_len: int
    used: int
    total: int
    free: int
    utilization: float
    threshold: float
    alarm: bool


@router.get("/pool-status", response_model=PoolStatusResponse)
async def pool_status(session: AsyncSession = Depends(get_session)) -> PoolStatusResponse:
    intent = await IntentRepo(session).load()
    if intent is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "no intent stored")
    allocations = await allocate_persistent(
        intent.fabric,
        session,
        gc=settings.link_pool_gc,
        warn_threshold=settings.link_pool_warn_threshold,
    )
    stats = pool_stats(intent.fabric, allocations)
    return PoolStatusResponse(
        pool=stats.pool,
        prefix_len=stats.prefix_len,
        used=stats.used_slots,
        total=stats.total_slots,
        free=stats.free_slots,
        utilization=round(stats.utilization, 6),
        threshold=settings.link_pool_warn_threshold,
        alarm=stats.utilization >= settings.link_pool_warn_threshold,
    )


@router.post("/reconcile")
async def reconcile() -> list[dict]:
    reports = await reconcile_once()
    return [
        {"device": r.device, "status": r.status.value, "drift": bool(r.diff), "message": r.message}
        for r in reports
    ]
