"""Device inventory: addressable properties needed to reach a switch."""
from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Vendor(StrEnum):
    JUNOS = "junos"
    NXOS = "nxos"
    IOSXE = "iosxe"
    EOS = "eos"
    AOSCX = "aoscx"


class DeviceCredential(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str
    password: SecretStr | None = None
    ssh_key_path: str | None = None


class Device(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    vendor: Vendor
    os_version: str | None = None
    mgmt_address: IPv6Address | IPv4Address = Field(description="Management IP.")
    netconf_port: int = 830
    aoscx_rest_port: int = 443
    credential: DeviceCredential
    tags: list[str] = Field(default_factory=list)

    @property
    def uses_netconf(self) -> bool:
        return self.vendor in {Vendor.JUNOS, Vendor.NXOS, Vendor.IOSXE, Vendor.EOS}

    @property
    def uses_aoscx_rest(self) -> bool:
        return self.vendor is Vendor.AOSCX
