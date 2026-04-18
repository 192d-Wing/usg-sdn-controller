# usg-sdn-controller

Multi-vendor SDN controller for **Campus EVPN** fabrics.

- **Underlay:** IPv6-only, **numbered** with /127 p2p links + /128 loopbacks,
  IS-IS L2 multi-topology as IGP. (BGP-unnumbered mode is still wired in the
  intent schema for NOSes that support it, but the default and the rendered
  templates assume numbered.)
- **Overlay:** eBGP EVPN (AFI/SAFI 25/70) on loopbacks with `ebgp-multihop 3`;
  VXLAN data-plane, **symmetric IRB**, **distributed anycast gateway**
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

## Addressing

Every fabric link gets a /127 allocated from `fabric.underlay.link_pool`
(default `fd00:face:b00c:1000::/56`). Allocation is deterministic by
canonical link key (sorted endpoints) and is persisted to the `link_address`
table once the controller has a DB session, so re-ordering the intent
or adding a new link doesn't renumber existing links.

Loopbacks are operator-assigned on each `Node` (`loopback_v6`, typed as
`IPv6Address`, rendered as `/128`). A synthetic IPv4 router-id is derived
from the ASN for NOSes that insist on a dotted-quad (`Node.router_id_v4`).

## Why numbered instead of BGP-unnumbered

Numbered gives uniform behaviour across all five NOSes — no vendor-specific
workarounds for Junos (`dynamic-neighbor`) or IOS-XE (no `neighbor <iface>`
form). Trade-off: loss of ND-driven self-healing on cable swaps, and /127
bookkeeping the controller owns. For campus fabrics this is almost always
the right call.

## Safety

- **No auto-push.** The reconciler computes diffs but requires an explicit
  `sdnctl push --confirm` or API `POST /operations/push?confirm=true`.
- Every push stages through the vendor's candidate store (NETCONF) or a REST
  checkpoint (AOS-CX) with rollback-on-error.

## Status

Pre-alpha scaffold. Templates are starting points — verify against your OS version.
