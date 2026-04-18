"""Declarative intent model for a Campus EVPN fabric.

A user expresses desired state as an IntentDocument (YAML/JSON); the controller
reconciles per-device config against it.
"""
from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv6Address, IPv6Interface, IPv6Network
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]


class NodeRole(StrEnum):
    SPINE = "spine"
    LEAF = "leaf"
    BORDER_LEAF = "border-leaf"
    SERVICE_LEAF = "service-leaf"


class Node(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    role: NodeRole
    inventory_ref: Name = Field(description="Matches Device.name in inventory.")
    loopback_v6: IPv6Address = Field(
        description="IPv6 loopback / router-id source. Also used as VTEP IP (synthesized from v6).",
    )
    isis_net: str = Field(
        pattern=r"^49\.[0-9a-f]{4}\.([0-9a-f]{4}\.){2}[0-9a-f]{4}\.00$",
        description="IS-IS NET (NSAP). Example: 49.0001.0000.0000.0001.00",
    )
    asn: int = Field(ge=64512, le=65534, description="Private 16-bit ASN for BGP-unnumbered peering.")


class Link(BaseModel):
    model_config = ConfigDict(frozen=True)

    a_node: Name
    a_iface: str
    b_node: Name
    b_iface: str
    mtu: int = 9216
    description: str | None = None


class L2Vni(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    vni: int = Field(ge=1, le=16_777_214)
    vlan_id: int = Field(ge=1, le=4094)
    rd_auto: bool = True
    rt_import: list[str] = Field(default_factory=list)
    rt_export: list[str] = Field(default_factory=list)
    description: str | None = None


class AnycastGateway(BaseModel):
    model_config = ConfigDict(frozen=True)

    v6_gateway: IPv6Interface = Field(
        description="Gateway address with prefix length, e.g. 2001:db8:100::1/64."
    )
    v4_gateway: str | None = Field(default=None, description="Optional dual-stack SVI address in CIDR form.")
    anycast_mac: str = Field(
        default="00:00:5E:00:01:FE",
        pattern=r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$",
        description="Distributed anycast gateway MAC (same on every leaf).",
    )


class L3Vni(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    vni: int = Field(ge=1, le=16_777_214)
    vrf: Name
    rd_auto: bool = True
    rt_import: list[str] = Field(default_factory=list)
    rt_export: list[str] = Field(default_factory=list)


class Vrf(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    l3_vni: int = Field(ge=1, le=16_777_214)
    l2_vnis: list[Name] = Field(default_factory=list, description="L2 VNI names that route into this VRF.")


class Tenant(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    vrfs: list[Vrf] = Field(default_factory=list)
    l2_vnis: list[L2Vni] = Field(default_factory=list)
    l3_vnis: list[L3Vni] = Field(default_factory=list)
    anycast_gateways: dict[Name, AnycastGateway] = Field(
        default_factory=dict, description="Keyed by L2Vni.name."
    )

    @field_validator("anycast_gateways")
    @classmethod
    def _validate_gw_refs(
        cls, v: dict[str, AnycastGateway], info: object
    ) -> dict[str, AnycastGateway]:
        return v


class Fabric(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    underlay_prefix: IPv6Network = Field(
        default=IPv6Network("fd00:face:b00c::/48"),
        description="Informational; links use IPv6 link-local so no prefix is configured.",
    )
    loopback_prefix: IPv6Network = Field(default=IPv6Network("fd00:face:b00c:10::/64"))
    isis_area: str = Field(default="49.0001", description="Derived area from NET.")
    mtu: int = 9216
    nodes: list[Node]
    links: list[Link]

    @field_validator("nodes")
    @classmethod
    def _unique_node_names(cls, v: list[Node]) -> list[Node]:
        names = [n.name for n in v]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate node names in fabric.")
        return v


class IntentDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_version: str = Field(default="sdn.usg/v1", alias="apiVersion")
    kind: str = "Fabric"
    fabric: Fabric
    tenants: list[Tenant] = Field(default_factory=list)
