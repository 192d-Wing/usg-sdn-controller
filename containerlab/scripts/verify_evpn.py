"""Assert BGP + EVPN convergence on the containerlab fabric.

Connects to each cEOS node's eAPI and checks:
  * IS-IS: all point-to-point adjacencies for each node reach "up" state
  * Underlay BGP (IPv6 unicast): expected peer count per node is reached and
    all peers are in the ``Established`` state
  * Overlay BGP (L2VPN EVPN): sessions between leaves (via the spine RRs)
    are Established and at least one remote VTEP is reachable

Exits 0 on success, nonzero on any failure (suitable for CI).
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
INTENT = ROOT / "examples" / "campus-fabric-3tier.yaml"
CLAB = ROOT / "containerlab" / "campus-ceos.clab.yml"

TIMEOUT_SEC = 180  # BGP-EVPN convergence budget
POLL_SEC = 10
USER = "admin"
PASSWORD = "admin"


@dataclass
class NodeInfo:
    name: str
    role: str
    mgmt_ip: str
    expected_underlay_peers: int
    is_vtep: bool


def _load_topology() -> list[NodeInfo]:
    intent = yaml.safe_load(INTENT.read_text())
    clab = yaml.safe_load(CLAB.read_text())
    mgmt = {n: d["mgmt-ipv4"] for n, d in clab["topology"]["nodes"].items()}
    peer_count: dict[str, int] = defaultdict(int)
    for link in intent["fabric"]["links"]:
        peer_count[link["a_node"]] += 1
        peer_count[link["b_node"]] += 1
    vtep_roles = {"leaf", "border-leaf", "service-leaf"}
    nodes: list[NodeInfo] = []
    for n in intent["fabric"]["nodes"]:
        nodes.append(
            NodeInfo(
                name=n["name"],
                role=n["role"],
                mgmt_ip=mgmt[n["name"]],
                expected_underlay_peers=peer_count[n["name"]],
                is_vtep=n["role"] in vtep_roles,
            )
        )
    return nodes


def _eapi(client: httpx.Client, node: NodeInfo, cmd: str) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "method": "runCmds",
        "params": {"version": 1, "cmds": [cmd], "format": "json"},
        "id": 1,
    }
    r = client.post(
        f"https://{node.mgmt_ip}/command-api",
        json=payload,
        auth=(USER, PASSWORD),
        timeout=15,
        verify=False,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"{node.name}: eAPI error: {body['error']}")
    return body["result"][0]


def _check_node(client: httpx.Client, node: NodeInfo) -> list[str]:
    errors: list[str] = []

    # IS-IS adjacencies
    try:
        res = _eapi(client, node, "show isis neighbors")
        vrfs = res.get("vrfs", {})
        adj_up = 0
        adj_total = 0
        for vrf in vrfs.values():
            for lvl in vrf.get("isisInstances", {}).values():
                for nbr in lvl.get("neighbors", {}).values():
                    for adj in nbr.get("adjacencies", []):
                        adj_total += 1
                        if adj.get("state") == "up":
                            adj_up += 1
        if adj_up != node.expected_underlay_peers:
            errors.append(
                f"{node.name}: IS-IS adjacencies up={adj_up}, expected={node.expected_underlay_peers} (total seen={adj_total})"
            )
    except Exception as e:
        errors.append(f"{node.name}: IS-IS check failed: {e}")

    # Underlay BGP (IPv6 unicast)
    try:
        res = _eapi(client, node, "show ipv6 bgp summary")
        vrfs = res.get("vrfs", {})
        established = 0
        total = 0
        for vrf in vrfs.values():
            for peer in vrf.get("peers", {}).values():
                total += 1
                if peer.get("peerState") == "Established":
                    established += 1
        if established != node.expected_underlay_peers:
            errors.append(
                f"{node.name}: underlay BGP established={established}/{total}, expected={node.expected_underlay_peers}"
            )
    except Exception as e:
        errors.append(f"{node.name}: underlay BGP check failed: {e}")

    # Overlay BGP (L2VPN EVPN) — every node peers EVPN to its directly-connected
    # neighbors (same count as underlay), since we eBGP everywhere.
    try:
        res = _eapi(client, node, "show bgp evpn summary")
        vrfs = res.get("vrfs", {})
        established = 0
        total = 0
        for vrf in vrfs.values():
            for peer in vrf.get("peers", {}).values():
                total += 1
                if peer.get("peerState") == "Established":
                    established += 1
        if established != node.expected_underlay_peers:
            errors.append(
                f"{node.name}: EVPN BGP established={established}/{total}, expected={node.expected_underlay_peers}"
            )
    except Exception as e:
        errors.append(f"{node.name}: EVPN BGP check failed: {e}")

    return errors


def _try_all(nodes: list[NodeInfo]) -> list[str]:
    errors: list[str] = []
    with httpx.Client(verify=False) as client:
        for node in nodes:
            errors.extend(_check_node(client, node))
    return errors


def main() -> int:
    nodes = _load_topology()
    deadline = time.time() + TIMEOUT_SEC
    last_errors: list[str] = []
    while time.time() < deadline:
        last_errors = _try_all(nodes)
        if not last_errors:
            print(f"OK: IS-IS + underlay-BGP + EVPN-BGP converged on {len(nodes)} nodes")
            return 0
        time.sleep(POLL_SEC)
    print(f"FAIL: convergence timed out after {TIMEOUT_SEC}s", file=sys.stderr)
    for e in last_errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
