# usg-sdn-controller

Multi-vendor SDN controller for **Campus EVPN** fabrics.

- **Underlay:** IPv6-only, BGP-unnumbered (IPv6 link-local peering), IS-IS L2 as IGP
- **Overlay:** EVPN (AFI/SAFI 25/70) with VXLAN data-plane, **symmetric IRB**,
  **distributed anycast gateway**
- **Vendors:** Juniper Junos (EX/QFX), Cisco NX-OS, Cisco IOS-XE, Arista EOS, Aruba AOS-CX 10.x
- **Transport:** NETCONF/SSH everywhere it's supported; AOS-CX uses REST (`pyaoscx`)

## Architecture

```
intent YAML ──▶ Pydantic models ──▶ store (SQL) ──▶ reconciler ──┐
                                                                 │
                                                                 ▼
                     per-vendor renderer (Jinja2) ──▶ driver ──▶ switch
                                                                 │
                                                  gNMI / NETCONF │
                                              telemetry  ◀───────┘
```

## Layout

| Path | Purpose |
|---|---|
| `src/usg_sdn/models/`      | Intent + inventory + operational-state Pydantic models |
| `src/usg_sdn/store/`       | Async SQLAlchemy persistence |
| `src/usg_sdn/render/`      | Jinja2 template loader, diff helpers |
| `src/usg_sdn/templates/`   | Per-vendor Jinja2 templates (underlay, overlay, tenant) |
| `src/usg_sdn/drivers/`     | Per-vendor device drivers (NETCONF / REST) |
| `src/usg_sdn/reconciler/`  | Desired ↔ running state reconciliation loop |
| `src/usg_sdn/api/`         | FastAPI REST API |
| `src/usg_sdn/cli/`         | `sdnctl` CLI (render, diff, push, verify) |
| `examples/`                | Sample intent YAML |
| `tests/`                   | Unit + render golden tests |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# render a fabric from intent YAML (no device contact)
sdnctl render --intent examples/campus-fabric.yaml --out build/

# start the controller API
usg-sdn

# diff a live device against desired config
sdnctl diff --device spine1

# push rendered config to a device (explicit; never automatic)
sdnctl push --device spine1 --confirm
```

## Vendor BGP-unnumbered support matrix

| Vendor / OS   | Native IPv6 LLA peering     | Notes |
|---------------|-----------------------------|-------|
| Cisco NX-OS   | ✅ `neighbor <iface>`       | 9.3(3)+ for EVPN |
| Arista EOS    | ✅ `neighbor <iface>`       | 4.27+ |
| Aruba AOS-CX  | ✅ `neighbor <lla>%<iface>` | 10.10+ |
| Juniper Junos | ⚠️ via dynamic-neighbors `allow fe80::/10` + `type external` (IPv6 LLA peering without /127) |
| Cisco IOS-XE  | ⚠️ requires IPv6 link-local neighbor + `ipv6 enable` on the interface |

The Junos and IOS-XE templates handle this via dynamic neighbors / explicit LLA neighbors; see comments inline.

## Safety

- **No auto-push.** The reconciler computes diffs but requires an explicit
  `sdnctl push --confirm` or API `POST /operations/push?confirm=true`.
- Every push stages through the vendor's candidate store (NETCONF) or a REST
  checkpoint (AOS-CX) with rollback-on-error.

## Status

Pre-alpha scaffold. Templates are starting points — verify against your OS version.
