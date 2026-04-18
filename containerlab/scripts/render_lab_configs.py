"""Render per-node cEOS configs for the containerlab integration test.

Reads ``examples/campus-fabric-3tier.yaml``, renders every fabric node against
the usg-sdn renderer as an ``Vendor.EOS`` device, prepends a lab bootstrap
(mgmt interface + eAPI + admin user) so the cEOS container comes up
reachable, and writes one ``<node>.cfg`` under ``containerlab/configs/``.

Idempotent. Safe to re-run.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from usg_sdn.models.intent import IntentDocument
from usg_sdn.models.inventory import Device, DeviceCredential, Vendor
from usg_sdn.render import render_device

ROOT = Path(__file__).resolve().parents[2]
INTENT = ROOT / "examples" / "campus-fabric-3tier.yaml"
CLAB = ROOT / "containerlab" / "campus-ceos.clab.yml"
OUT = ROOT / "containerlab" / "configs"


LAB_BOOTSTRAP = """!
! --- lab bootstrap (cEOS-only, added by render_lab_configs.py) ---
username admin privilege 15 role network-admin secret 0 admin
!
management api http-commands
   no shutdown
   protocol http
   protocol https
!
management api gnmi
   transport grpc default
!
vrf instance MGMT
!
interface Management0
   vrf MGMT
   ip address {mgmt_ip}/24
!
ip routing vrf MGMT
!
management api http-commands
   vrf MGMT
      no shutdown
!
no aaa root
!
"""


def _mgmt_ip_map() -> dict[str, str]:
    data = yaml.safe_load(CLAB.read_text())
    return {
        name: node["mgmt-ipv4"]
        for name, node in data["topology"]["nodes"].items()
    }


def main() -> None:
    intent = IntentDocument.model_validate(yaml.safe_load(INTENT.read_text()))
    mgmt = _mgmt_ip_map()
    OUT.mkdir(exist_ok=True)

    for node in intent.fabric.nodes:
        mgmt_ip = mgmt[node.name]
        device = Device(
            name=node.inventory_ref,
            vendor=Vendor.EOS,
            mgmt_address=mgmt_ip,
            credential=DeviceCredential(username="admin", password="admin"),
        )
        bundle = render_device(intent, device)
        body = LAB_BOOTSTRAP.format(mgmt_ip=mgmt_ip) + bundle.config_text
        path = OUT / f"{node.name}.cfg"
        path.write_text(body)
        print(f"wrote {path} ({len(body)} bytes, mgmt={mgmt_ip}, role={node.role.value})")


if __name__ == "__main__":
    main()
