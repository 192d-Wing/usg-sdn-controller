"""Per-vendor render smoke tests.

These tests are not golden-file comparisons (templates will churn). They
assert:
  - template renders without error for every vendor
  - required underlay / overlay markers appear
  - tenant anycast GW appears somewhere in output
"""
from __future__ import annotations

import pytest

from usg_sdn.models.inventory import Vendor
from usg_sdn.render import render_device


@pytest.mark.parametrize(
    "device_fixture,vendor,markers",
    [
        ("junos_device", Vendor.JUNOS, ["isis", "protocols", "bgp", "evpn", "vxlan"]),
        ("nxos_device",  Vendor.NXOS,  ["router isis FABRIC", "nv overlay evpn", "interface nve1", "fabric forwarding anycast-gateway-mac"]),
        ("iosxe_device", Vendor.IOSXE, ["router isis FABRIC", "l2vpn evpn", "router bgp", "vrf definition"]),
        ("eos_device",   Vendor.EOS,   ["router isis FABRIC", "router bgp", "address-family evpn", "interface Vxlan1", "ip virtual-router"]),
        ("aoscx_device", Vendor.AOSCX, ["router isis", "router bgp", "address-family l2vpn evpn", "active-gateway"]),
    ],
)
def test_render_smoke(request, intent, device_fixture, vendor, markers) -> None:
    device = request.getfixturevalue(device_fixture)
    assert device.vendor is vendor
    bundle = render_device(intent, device)
    assert bundle.vendor == vendor.value
    for m in markers:
        assert m in bundle.config_text, f"expected marker {m!r} missing for {vendor}"


def test_render_includes_anycast_v6(intent, eos_device) -> None:
    bundle = render_device(intent, eos_device)
    assert "2001:db8:100::1/64" in bundle.config_text
