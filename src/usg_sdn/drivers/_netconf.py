"""Shared NETCONF client helper built on scrapli-netconf.

Connections are opened per operation for simplicity; callers needing persistent
sessions can wrap ``connect()`` in an ``async with`` themselves.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from scrapli_netconf.driver import AsyncNetconfDriver

from ..config import settings
from ..models.inventory import Device


@asynccontextmanager
async def connect(device: Device):
    kwargs = dict(
        host=str(device.mgmt_address),
        port=device.netconf_port,
        auth_username=device.credential.username or settings.device_ssh_user,
        auth_strict_key=False,
        transport_options={"open_cmd": []},
        timeout_socket=settings.device_ssh_timeout_sec,
        timeout_transport=settings.device_ssh_timeout_sec,
        timeout_ops=settings.device_ssh_timeout_sec,
    )
    if device.credential.password is not None:
        kwargs["auth_password"] = device.credential.password.get_secret_value()
    if device.credential.ssh_key_path:
        kwargs["auth_private_key"] = device.credential.ssh_key_path
    else:
        kwargs["auth_private_key"] = str(settings.device_ssh_key)

    driver = AsyncNetconfDriver(**kwargs)
    await driver.open()
    try:
        yield driver
    finally:
        await driver.close()
