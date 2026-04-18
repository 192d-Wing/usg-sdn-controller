"""Link allocator correctness + stability."""
from __future__ import annotations

from ipaddress import IPv6Address

from usg_sdn.allocator import allocate_stateless, canonical_key
from usg_sdn.models.intent import IntentDocument


def test_canonical_key_is_symmetric(intent: IntentDocument) -> None:
    for link in intent.fabric.links:
        k1 = canonical_key(link)
        k2 = canonical_key(
            link.model_copy(
                update={
                    "a_node": link.b_node,
                    "a_iface": link.b_iface,
                    "b_node": link.a_node,
                    "b_iface": link.a_iface,
                }
            )
        )
        assert k1 == k2


def test_allocation_unique_and_in_pool(intent: IntentDocument) -> None:
    allocs = allocate_stateless(intent.fabric)
    assert len(allocs) == len(intent.fabric.links)
    pool = intent.fabric.underlay.link_pool
    subnets = [a.subnet for a in allocs.values()]
    assert len(set(subnets)) == len(subnets), "duplicate /127 allocations"
    for a in allocs.values():
        assert a.subnet.subnet_of(pool)
        assert a.a_addr in a.subnet and a.b_addr in a.subnet
        assert a.a_addr != a.b_addr


def test_endpoints_for_consistency(intent: IntentDocument) -> None:
    allocs = allocate_stateless(intent.fabric)
    for link in intent.fabric.links:
        alloc = allocs[canonical_key(link)]
        a_local, a_remote = alloc.endpoints_for(link.a_node, link.a_iface)
        b_local, b_remote = alloc.endpoints_for(link.b_node, link.b_iface)
        assert a_local == b_remote
        assert a_remote == b_local
        assert isinstance(a_local, IPv6Address)


def test_allocation_stable_under_link_reorder(intent: IntentDocument) -> None:
    a1 = allocate_stateless(intent.fabric)
    reordered = intent.fabric.model_copy(
        update={"links": list(reversed(list(intent.fabric.links)))}
    )
    a2 = allocate_stateless(reordered)
    assert a1 == a2
