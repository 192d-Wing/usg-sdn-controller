"""Jinja2-based per-vendor config renderer.

Takes an ``IntentDocument`` + a target ``Node`` and produces a ``RenderBundle``
whose ``config_text`` is vendor-native.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ..config import settings
from ..models.intent import Fabric, IntentDocument, Node, Tenant
from ..models.inventory import Device, Vendor
from ..models.state import RenderBundle


@dataclass(frozen=True)
class _PeerLink:
    local_iface: str
    remote_node: str
    remote_iface: str
    description: str


def _peer_links_for(node_name: str, fabric: Fabric) -> list[_PeerLink]:
    peers: list[_PeerLink] = []
    for link in fabric.links:
        if link.a_node == node_name:
            peers.append(
                _PeerLink(
                    local_iface=link.a_iface,
                    remote_node=link.b_node,
                    remote_iface=link.b_iface,
                    description=link.description or f"to {link.b_node}",
                )
            )
        elif link.b_node == node_name:
            peers.append(
                _PeerLink(
                    local_iface=link.b_iface,
                    remote_node=link.a_node,
                    remote_iface=link.a_iface,
                    description=link.description or f"to {link.a_node}",
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

    def render(self, intent: IntentDocument, device: Device, node: Node) -> RenderBundle:
        vendor = device.vendor.value
        peers = _peer_links_for(node.name, intent.fabric)
        node_by_name = {n.name: n for n in intent.fabric.nodes}
        ctx = {
            "fabric": intent.fabric,
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
) -> RenderBundle:
    node = next((n for n in intent.fabric.nodes if n.inventory_ref == device.name), None)
    if node is None:
        raise ValueError(f"No fabric node references inventory device {device.name!r}.")
    assert device.vendor in Vendor
    return Renderer(template_root).render(intent, device, node)


__all__ = ["Renderer", "render_device", "_peer_links_for", "_PeerLink", "Tenant"]
