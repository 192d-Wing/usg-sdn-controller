"""Device inventory endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.inventory import Device
from ...store import DeviceRepo, get_session

router = APIRouter()


@router.get("", response_model=list[Device])
async def list_devices(session: AsyncSession = Depends(get_session)) -> list[Device]:
    return await DeviceRepo(session).list()


@router.put("/{name}", response_model=Device)
async def upsert_device(
    name: str,
    device: Device,
    session: AsyncSession = Depends(get_session),
) -> Device:
    if device.name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path name must match body name",
        )
    await DeviceRepo(session).upsert(device)
    return device


@router.get("/{name}", response_model=Device)
async def get_device(name: str, session: AsyncSession = Depends(get_session)) -> Device:
    device = await DeviceRepo(session).get(name)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such device")
    return device
