"""Per-vendor driver registry."""
from __future__ import annotations

from ..models.inventory import Device, Vendor
from .aoscx import AosCxDriver
from .base import DeviceDriver
from .eos import EosDriver
from .iosxe import IosXeDriver
from .junos import JunosDriver
from .nxos import NxosDriver

_REGISTRY: dict[Vendor, type[DeviceDriver]] = {
    Vendor.JUNOS: JunosDriver,
    Vendor.NXOS: NxosDriver,
    Vendor.IOSXE: IosXeDriver,
    Vendor.EOS: EosDriver,
    Vendor.AOSCX: AosCxDriver,
}


def driver_for(device: Device) -> DeviceDriver:
    klass = _REGISTRY[device.vendor]
    return klass(device)


__all__ = [
    "AosCxDriver",
    "DeviceDriver",
    "EosDriver",
    "IosXeDriver",
    "JunosDriver",
    "NxosDriver",
    "driver_for",
]
