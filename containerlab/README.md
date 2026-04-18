# containerlab integration test

End-to-end proof that the rendered per-vendor configs form a working
Campus EVPN fabric. The topology mirrors
`examples/campus-fabric-3tier.yaml` using **cEOS-lab** for every node —
Arista is the only vendor with a free-ish container image that containerlab
supports out-of-the-box. NX-OS, IOS-XE, AOS-CX, and Junos need their own
vendor-provided simulators and are not in this lab.

## Requirements

* Linux host with Docker
* [containerlab](https://containerlab.dev/install/) ≥ 0.57
* Arista cEOS-lab image imported as `ceos:latest`
  (download from https://www.arista.com/en/support/software-download,
  then `docker import cEOS-lab-<ver>.tar.xz ceos:latest`)
* Python 3.14 with this repo installed: `pip install -e '.[dev]'`

## Quick run

```bash
# Render configs, deploy the lab, and verify BGP-EVPN convergence.
make integration

# Or step-by-step:
make lab-render     # writes containerlab/configs/*.cfg
make lab-up         # containerlab deploy
make lab-verify     # asserts IS-IS + underlay-BGP + EVPN sessions Established
make lab-down
```

`integration` will render → deploy → sleep 90s → verify → destroy, and
returns non-zero if any node fails convergence.

## What gets verified

`containerlab/scripts/verify_evpn.py` connects to each node's eAPI and
checks:

1. **IS-IS** — every node has its expected point-to-point adjacencies up.
2. **Underlay BGP** (`show ipv6 bgp summary`) — every node has every
   directly-connected neighbor Established.
3. **EVPN BGP** (`show bgp evpn summary`) — every node has every
   directly-connected neighbor's loopback-based EVPN session Established.

Convergence budget is 180 s (polling every 10 s).

## Topology

```
        ssp1        ssp2         (super-spines, transit)
         │ │         │ │
         │ └─────────┘ │
         │ │         │ │
         sp1         sp2         (spines, transit)
         │ │         │ │
         │ └─────────┘ │
         │ │         │ │
         lf1         lf2         (leaves, VTEPs)
```

8 /127 link addresses drawn from `fd00:face:b00c:2000::/120` (128 slots,
6.25 % utilisation — well under the 75 % alarm threshold).

## Image override

If your cEOS image is tagged differently:

```bash
make lab-up CEOS_IMAGE=ceos:4.32.0F
```

…or edit `campus-ceos.clab.yml` directly.

## CI

`.github/workflows/integration.yml` runs `make integration` on any
self-hosted runner labeled `clab`. If no such runner is registered, the
workflow is simply unscheduled — the public CI workflow (`ci.yml`) still
runs lint, type-check, and unit tests on every push.
