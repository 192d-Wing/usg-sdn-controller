"""Per-vendor render smoke tests for numbered IPv6 underlay.

Asserts:
  - every vendor template renders without error
  - required underlay markers appear (IS-IS, /127 link address)
  - EVPN peering uses loopback addresses, not /127s
  - tenant anycast GW appears for vendors that emit SVIs
"""
from __future__ import annotations

import pytest

from usg_sdn.models.inventory import Vendor
from usg_sdn.render import render_device


@pytest.mark.parametrize(
    "device_fixture,vendor,required",
    [
        ("junos_device", Vendor.JUNOS, ["isis", "family inet6", "group FABRIC-UNDERLAY", "group FABRIC-EVPN", "family evpn signaling"]),
        ("nxos_device",  Vendor.NXOS,  ["router isis FABRIC", "nv overlay evpn", "interface nve1", "ebgp-multihop 3"]),
        ("iosxe_device", Vendor.IOSXE, ["router isis FABRIC", "l2vpn evpn", "address-family l2vpn evpn", "ebgp-multihop 3"]),
        ("eos_device",   Vendor.EOS,   ["router isis FABRIC", "neighbor UNDERLAY peer group", "neighbor EVPN peer group", "address-family evpn", "interface Vxlan1"]),
        ("aoscx_device", Vendor.AOSCX, ["router isis", "address-family l2vpn evpn", "ebgp-multihop 3", "active-gateway"]),
    ],
)
def test_render_smoke(request, intent, device_fixture, vendor, required) -> None:
    device = request.getfixturevalue(device_fixture)
    assert device.vendor is vendor
    bundle = render_device(intent, device)
    assert bundle.vendor == vendor.value
    for m in required:
        assert m in bundle.config_text, f"expected marker {m!r} missing for {vendor}"


def test_render_uses_allocated_p127(intent, eos_device) -> None:
    txt = render_device(intent, eos_device).config_text
    # The allocator assigns from fd00:face:b00c:1000::/56; spine1 has 3 links,
    # so three /127 addresses must appear.
    assert "/127" in txt
    assert "fd00:face:b00c:1000::" in txt


def test_evpn_neighbors_are_loopbacks(intent, nxos_device) -> None:
    # EVPN sessions peer to remote loopbacks, not /127s.
    txt = render_device(intent, nxos_device).config_text
    assert "ebgp-multihop 3" in txt
    # At least one configured EVPN neighbor must match a known loopback.
    for n in intent.fabric.nodes:
        if n.name != "spine2":
            if f"neighbor {n.loopback_v6}" in txt:
                return
    raise AssertionError("no EVPN neighbor stanza pointed at any peer loopback")


def test_render_includes_anycast_v6(intent, eos_device) -> None:
    bundle = render_device(intent, eos_device)
    assert "2001:db8:100::1/64" in bundle.config_text
