"""Per-vendor render smoke tests for numbered IPv6 underlay.

With role-aware gating, VTEP and tenant markers only appear on leaf / border /
service-leaf nodes. Spines and super-spines emit transit-only config.
"""
from __future__ import annotations

import pytest

from usg_sdn.models.inventory import Device, DeviceCredential, Vendor
from usg_sdn.render import render_device


def _dev(name: str, vendor: Vendor) -> Device:
    return Device(
        name=name,
        vendor=vendor,
        mgmt_address="fd00::1",
        credential=DeviceCredential(username="sdn"),
    )


@pytest.mark.parametrize(
    "device_fixture,vendor,required",
    [
        # leaves/border render VTEP + tenant state
        ("junos_device",  Vendor.JUNOS, ["isis", "family inet6", "group FABRIC-UNDERLAY", "group FABRIC-EVPN", "family evpn signaling", "switch-options"]),
        ("iosxe_device",  Vendor.IOSXE, ["router isis FABRIC", "l2vpn evpn", "address-family l2vpn evpn", "ebgp-multihop 3", "vrf definition"]),
        ("aoscx_device",  Vendor.AOSCX, ["router isis", "address-family l2vpn evpn", "ebgp-multihop 3", "active-gateway"]),
        # spines are eBGP-EVPN transit only (no VTEP block)
        ("nxos_device",   Vendor.NXOS,  ["router isis FABRIC", "nv overlay evpn", "router bgp", "ebgp-multihop 3"]),
        ("eos_device",    Vendor.EOS,   ["router isis FABRIC", "neighbor UNDERLAY peer group", "neighbor EVPN peer group", "address-family evpn"]),
    ],
)
def test_render_smoke(request, intent, device_fixture, vendor, required) -> None:
    device = request.getfixturevalue(device_fixture)
    assert device.vendor is vendor
    bundle = render_device(intent, device)
    assert bundle.vendor == vendor.value
    for m in required:
        assert m in bundle.config_text, f"expected marker {m!r} missing for {vendor}"


def test_spine_has_no_vtep_block(intent, nxos_device, eos_device) -> None:
    assert "interface nve1" not in render_device(intent, nxos_device).config_text
    assert "interface Vxlan1" not in render_device(intent, eos_device).config_text


def test_leaf_renders_anycast_v6(intent) -> None:
    # aoscx_device fixture points at leaf2 — a VTEP — so anycast state must appear.
    dev = _dev("leaf2", Vendor.AOSCX)
    txt = render_device(intent, dev).config_text
    assert "2001:db8:100::1" in txt


def test_render_uses_allocated_p127(intent, eos_device) -> None:
    txt = render_device(intent, eos_device).config_text
    assert "/127" in txt
    assert "fd00:face:b00c:1000::" in txt


def test_evpn_neighbors_are_loopbacks(intent, nxos_device) -> None:
    """EVPN sessions peer to remote loopbacks (ebgp-multihop), not /127s."""
    txt = render_device(intent, nxos_device).config_text
    assert "ebgp-multihop 3" in txt
    for n in intent.fabric.nodes:
        if n.name != "spine2" and f"neighbor {n.loopback_v6}" in txt:
            return
    raise AssertionError("no EVPN neighbor stanza pointed at any peer loopback")
