"""Declarative intent model for a Campus EVPN fabric.

A user expresses desired state as an IntentDocument (YAML/JSON); the controller
reconciles per-device config against it.
"""
from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv6Address, IPv6Interface, IPv6Network
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field, field_validator

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
        description="IPv6 loopback (/128). Used as router-id and EVPN/VTEP source.",
    )
    isis_net: str = Field(
        pattern=r"^49\.[0-9a-f]{4}\.([0-9a-f]{4}\.){2}[0-9a-f]{4}\.00$",
        description="IS-IS NET (NSAP). Example: 49.0001.0000.0000.0001.00",
    )
    asn: int = Field(ge=64512, le=65534, description="Private 16-bit ASN for BGP peering.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def router_id_v4(self) -> str:
        """Synthetic IPv4 router-id derived from ASN.

        Several NOSes (Junos, NX-OS, AOS-CX) insist on a dotted-quad router-id
        even on v6-only underlays. We derive a stable placeholder from the ASN
        (0.0.<hi>.<lo>) so the operator doesn't have to track a separate pool.
        Operators who want explicit v4 router-ids can override by setting
        ``Node.router_id_v4`` via a custom model extension.
        """
        hi = (self.asn >> 8) & 0xFF
        lo = self.asn & 0xFF
        return f"0.0.{hi}.{lo}"


class Link(BaseModel):
    model_config = ConfigDict(frozen=True)

    a_node: Name
    a_iface: str
    b_node: Name
    b_iface: str
    mtu: int = 9216
    description: str | None = None


class UnderlayConfig(BaseModel):
    """Fabric underlay addressing + peering policy."""

    model_config = ConfigDict(frozen=True)

    mode: Literal["numbered", "unnumbered"] = Field(
        default="numbered",
        description="'numbered' uses IPv6 /127 p2p addresses; 'unnumbered' uses IPv6 LLA peering.",
    )
    link_pool: IPv6Network = Field(
        default=IPv6Network("fd00:face:b00c:1000::/56"),
        description="Pool from which /127 p2p link prefixes are allocated.",
    )
    link_prefix_len: int = Field(default=127, ge=64, le=127)
    loopback_pool: IPv6Network = Field(default=IPv6Network("fd00:face:b00c:10::/64"))
    loopback_prefix_len: int = Field(default=128, ge=64, le=128)


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


class Fabric(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Name
    underlay: UnderlayConfig = Field(default_factory=UnderlayConfig)
    isis_area: str = Field(default="49.0001", description="IS-IS area; should match Node.isis_net.")
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
