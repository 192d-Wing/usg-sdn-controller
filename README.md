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

## Authentication & authorization

The API ships with two credential kinds and scope-based authorization:

- **API tokens** — `usgsdn_pat_*` opaque bearer tokens, hashed in the
  `api_token` table. Mint with `sdnctl token create` or `POST /auth/tokens`.
- **OIDC** — externally-issued JWTs validated against an issuer's JWKS
  (`USG_SDN_OIDC_ISSUER`, `USG_SDN_OIDC_AUDIENCE`). The controller is a
  resource server only; it doesn't run OAuth flows.

`USG_SDN_AUTH_ENABLED=false` (the default) skips all auth and assigns every
request a synthetic `anonymous` principal with all scopes — convenient for
dev, **never use in production**. Set it to `true` for any real deployment.

Built-in scopes:

| Scope                  | Routes                                               |
|------------------------|------------------------------------------------------|
| `intent:read`          | `GET /intent`                                        |
| `intent:write`         | `PUT /intent`                                        |
| `devices:read`         | `GET /devices`, `GET /devices/{name}`                |
| `devices:write`        | `PUT /devices/{name}`                                |
| `operations:read`      | `/operations/render`, `/diff`, `/pool-status`        |
| `operations:reconcile` | `POST /operations/reconcile`                         |
| `operations:push`      | `POST /operations/push` ⚠️ device-mutating          |
| `auth:read`            | `GET /auth/me`, `GET /auth/tokens`                   |
| `auth:write`           | `POST /auth/tokens`, `DELETE /auth/tokens/{id}`     |

Convenience role bundles: `viewer` ⊂ `operator` ⊂ `admin`.

```bash
# Mint a token for CI with read-only scope
sdnctl token create --name ci-bot --role viewer

# Use it
curl -H "Authorization: Bearer usgsdn_pat_xxxxx.yyyy..." \
     http://controller:8080/intent
```

## Integration test

`make integration` brings up a six-node cEOS-lab fabric under
[containerlab](https://containerlab.dev) matching `examples/campus-fabric-3tier.yaml`,
pushes the rendered configs, and asserts IS-IS + underlay-BGP + EVPN-BGP
convergence. See [`containerlab/README.md`](containerlab/README.md).

CI runs ruff + pytest on every push/PR (`.github/workflows/ci.yml`);
`.github/workflows/integration.yml` runs `make integration` nightly on any
self-hosted runner labeled `clab`.

## Status

Pre-alpha scaffold. Templates are starting points — verify against your OS version.
