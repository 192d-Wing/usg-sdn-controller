"""Super-spine role + is_vtep gating in rendered config."""
from __future__ import annotations

from usg_sdn.models.intent import IntentDocument, NodeRole
from usg_sdn.models.inventory import Device, DeviceCredential, Vendor
from usg_sdn.render import render_device


def _dev(name: str, vendor: Vendor) -> Device:
    return Device(
        name=name,
        vendor=vendor,
        mgmt_address="fd00::1",
        credential=DeviceCredential(username="sdn"),
    )


def test_super_spine_role_accepted(intent_3tier: IntentDocument) -> None:
    roles = {n.name: n.role for n in intent_3tier.fabric.nodes}
    assert roles["ssp1"] is NodeRole.SUPER_SPINE
    assert roles["ssp2"] is NodeRole.SUPER_SPINE


def test_is_vtep_computed_correctly(intent_3tier: IntentDocument) -> None:
    by_name = {n.name: n for n in intent_3tier.fabric.nodes}
    assert by_name["lf1"].is_vtep is True
    assert by_name["sp1"].is_vtep is False
    assert by_name["ssp1"].is_vtep is False


def test_super_spine_has_no_vtep_config(intent_3tier: IntentDocument) -> None:
    """A super-spine must not render VTEP or tenant VNI state."""
    # Cover all vendors for the super-spine role to verify every template gates.
    for vendor in (Vendor.EOS, Vendor.NXOS, Vendor.IOSXE, Vendor.AOSCX, Vendor.JUNOS):
        dev = _dev("ssp1", vendor)
        txt = render_device(intent_3tier, dev).config_text
        forbidden_markers = {
            Vendor.EOS:   ["interface Vxlan1", "vxlan source-interface", "ip virtual-router"],
            Vendor.NXOS:  ["interface nve1", "fabric forwarding anycast-gateway-mac"],
            Vendor.IOSXE: ["l2vpn evpn\n replication-type", "default-gateway advertise"],
            Vendor.AOSCX: ["overlay\n    source-interface", "active-gateway"],
            Vendor.JUNOS: ["switch-options {", "vtep-source-interface"],
        }[vendor]
        for m in forbidden_markers:
            assert m not in txt, f"{vendor}: super-spine should not render {m!r}"


def test_leaf_still_has_vtep_config(intent_3tier: IntentDocument) -> None:
    txt = render_device(intent_3tier, _dev("lf1", Vendor.EOS)).config_text
    assert "interface Vxlan1" in txt
    assert "ip virtual-router mac-address" in txt
