"""Thin repository layer above SQLAlchemy."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from ..models.intent import IntentDocument
from ..models.inventory import Device, DeviceCredential, Vendor
from ..models.state import DeviceState, DeviceStatus
from .models_sql import ApiTokenRow, DeviceRow, DeviceStateRow, IntentRow


class IntentRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, doc: IntentDocument, *, id_: str = "current") -> None:
        payload = doc.model_dump(mode="json", by_alias=True)
        row = await self._s.get(IntentRow, id_)
        if row is None:
            row = IntentRow(id=id_, document=payload)
            self._s.add(row)
        else:
            row.document = payload
        await self._s.commit()

    async def load(self, id_: str = "current") -> IntentDocument | None:
        row = await self._s.get(IntentRow, id_)
        if row is None:
            return None
        return IntentDocument.model_validate(row.document)


class DeviceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(self, device: Device) -> None:
        row = await self._s.get(DeviceRow, device.name)
        cred = device.credential.model_dump(mode="json")
        if row is None:
            self._s.add(
                DeviceRow(
                    name=device.name,
                    vendor=device.vendor.value,
                    mgmt_address=str(device.mgmt_address),
                    os_version=device.os_version,
                    credential=cred,
                    tags=list(device.tags),
                )
            )
        else:
            row.vendor = device.vendor.value
            row.mgmt_address = str(device.mgmt_address)
            row.os_version = device.os_version
            row.credential = cred
            row.tags = list(device.tags)
        await self._s.commit()

    async def get(self, name: str) -> Device | None:
        row = await self._s.get(DeviceRow, name)
        if row is None:
            return None
        return Device(
            name=row.name,
            vendor=Vendor(row.vendor),
            mgmt_address=row.mgmt_address,
            os_version=row.os_version,
            credential=DeviceCredential.model_validate(row.credential),
            tags=list(row.tags or []),
        )

    async def list(self) -> list[Device]:
        result = await self._s.execute(select(DeviceRow))
        return [
            Device(
                name=r.name,
                vendor=Vendor(r.vendor),
                mgmt_address=r.mgmt_address,
                os_version=r.os_version,
                credential=DeviceCredential.model_validate(r.credential),
                tags=list(r.tags or []),
            )
            for r in result.scalars().all()
        ]


class AuthRepo:
    """CRUD for ``api_token`` rows. The plaintext token is never stored —
    callers must persist it themselves at creation time and discard."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        token_id: str,
        name: str,
        secret_hash: str,
        prefix: str,
        scopes: list[str],
    ) -> ApiTokenRow:
        row = ApiTokenRow(
            id=token_id,
            name=name,
            secret_hash=secret_hash,
            prefix=prefix,
            scopes=scopes,
        )
        self._s.add(row)
        await self._s.commit()
        return row

    async def list(self, *, include_revoked: bool = False) -> list[ApiTokenRow]:
        stmt = select(ApiTokenRow)
        if not include_revoked:
            stmt = stmt.where(ApiTokenRow.revoked_at.is_(None))
        rows = (await self._s.execute(stmt)).scalars().all()
        return list(rows)

    async def get(self, token_id: str) -> ApiTokenRow | None:
        return await self._s.get(ApiTokenRow, token_id)

    async def revoke(self, token_id: str) -> bool:
        row = await self._s.get(ApiTokenRow, token_id)
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(timezone.utc)
        await self._s.commit()
        return True


class StateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def set(
        self,
        device: str,
        status: DeviceStatus,
        *,
        running_config_hash: str | None = None,
        message: str | None = None,
        rendered_config: str | None = None,
    ) -> None:
        row = await self._s.get(DeviceStateRow, device)
        if row is None:
            row = DeviceStateRow(
                device=device,
                status=status.value,
                running_config_hash=running_config_hash,
                message=message,
                rendered_config=rendered_config,
            )
            self._s.add(row)
        else:
            row.status = status.value
            row.running_config_hash = running_config_hash
            row.message = message
            if rendered_config is not None:
                row.rendered_config = rendered_config
        await self._s.commit()

    async def get(self, device: str) -> DeviceState | None:
        row = await self._s.get(DeviceStateRow, device)
        if row is None:
            return None
        return DeviceState(
            device=row.device,
            status=DeviceStatus(row.status),
            running_config_hash=row.running_config_hash,
            message=row.message,
        )
