"""Jinja2-based per-vendor config renderer.

Takes an ``IntentDocument`` + a target ``Node`` and produces a ``RenderBundle``
whose ``config_text`` is vendor-native.
"""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv6Address
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ..allocator import LinkAllocation, allocate_stateless, canonical_key
from ..config import settings
from ..models.intent import Fabric, IntentDocument, Node
from ..models.inventory import Device, Vendor
from ..models.state import RenderBundle


@dataclass(frozen=True)
class _PeerLink:
    local_iface: str
    remote_node: str
    remote_iface: str
    description: str
    local_ipv6: IPv6Address | None = None   # /127 host, numbered mode only
    remote_ipv6: IPv6Address | None = None  # /127 host, numbered mode only
    prefix_len: int | None = None


def _peer_links_for(
    node_name: str,
    fabric: Fabric,
    allocations: dict[tuple[str, str], LinkAllocation] | None = None,
) -> list[_PeerLink]:
    peers: list[_PeerLink] = []
    numbered = fabric.underlay.mode == "numbered"
    for link in fabric.links:
        if link.a_node == node_name:
            local_iface, remote_node, remote_iface = link.a_iface, link.b_node, link.b_iface
        elif link.b_node == node_name:
            local_iface, remote_node, remote_iface = link.b_iface, link.a_node, link.a_iface
        else:
            continue

        desc = link.description or f"to {remote_node}"
        local_v6: IPv6Address | None = None
        remote_v6: IPv6Address | None = None
        prefix_len: int | None = None

        if numbered and allocations is not None:
            alloc = allocations[canonical_key(link)]
            local_v6, remote_v6 = alloc.endpoints_for(node_name, local_iface)
            prefix_len = alloc.subnet.prefixlen

        peers.append(
            _PeerLink(
                local_iface=local_iface,
                remote_node=remote_node,
                remote_iface=remote_iface,
                description=desc,
                local_ipv6=local_v6,
                remote_ipv6=remote_v6,
                prefix_len=prefix_len,
            )
        )
    return peers


class Renderer:
    def __init__(self, template_root: Path | None = None) -> None:
        root = template_root or settings.template_dir
        self._env = Environment(
            loader=FileSystemLoader(str(root)),
            autoescape=select_autoescape(enabled_extensions=()),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def render(
        self,
        intent: IntentDocument,
        device: Device,
        node: Node,
        *,
        allocations: dict[tuple[str, str], LinkAllocation] | None = None,
    ) -> RenderBundle:
        vendor = device.vendor.value
        if allocations is None and intent.fabric.underlay.mode == "numbered":
            allocations = allocate_stateless(intent.fabric)
        peers = _peer_links_for(node.name, intent.fabric, allocations)
        node_by_name = {n.name: n for n in intent.fabric.nodes}
        ctx = {
            "fabric": intent.fabric,
            "underlay": intent.fabric.underlay,
            "node": node,
            "device": device,
            "peers": peers,
            "node_by_name": node_by_name,
            "tenants": intent.tenants,
        }
        sections: list[str] = []
        for layer in ("underlay", "overlay", "tenant"):
            template = self._env.get_template(f"{vendor}/{layer}.j2")
            sections.append(template.render(**ctx))
        config_text = "\n".join(sections).rstrip() + "\n"
        return RenderBundle(device=device.name, vendor=vendor, config_text=config_text)


def render_device(
    intent: IntentDocument,
    device: Device,
    *,
    template_root: Path | None = None,
    allocations: dict[tuple[str, str], LinkAllocation] | None = None,
) -> RenderBundle:
    node = next((n for n in intent.fabric.nodes if n.inventory_ref == device.name), None)
    if node is None:
        raise ValueError(f"No fabric node references inventory device {device.name!r}.")
    assert device.vendor in Vendor
    return Renderer(template_root).render(intent, device, node, allocations=allocations)


__all__ = ["Renderer", "render_device", "_peer_links_for", "_PeerLink"]
