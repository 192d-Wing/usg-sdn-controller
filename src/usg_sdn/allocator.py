"""Deterministic link-address allocator for numbered IPv6 underlay.

Every fabric link is given a /127 drawn from ``UnderlayConfig.link_pool``.

Allocation rules:
  * A ``Link`` has a canonical form (smaller (node,iface) wins as "A side"),
    so swapping A/B in the intent doesn't change allocation.
  * Assignments are stable while a link's canonical key doesn't change. Adding
    or removing links preserves existing allocations — new links consume the
    next free /127.
  * The persistent allocator reads/writes the ``link_address`` table and is
    the source of truth when a DB is available (controller + reconciler
    paths).
  * The stateless allocator gives the same answer deterministically from the
    intent alone (used by offline ``sdnctl render`` when no DB is configured).

A ``LinkAllocation`` always resolves the A-side to the numerically-lower /127
address in the subnet (``::0``) and the B-side to ``::1``, independent of how
the operator wrote the link in YAML.
"""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv6Address, IPv6Network

from .models.intent import Fabric, Link, UnderlayConfig


def canonical_key(link: Link) -> tuple[str, str]:
    """Return ``((lo_node, lo_iface), (hi_node, hi_iface))`` with lo <= hi."""
    a = (link.a_node, link.a_iface)
    b = (link.b_node, link.b_iface)
    lo, hi = (a, b) if a <= b else (b, a)
    return f"{lo[0]}:{lo[1]}", f"{hi[0]}:{hi[1]}"


@dataclass(frozen=True)
class LinkAllocation:
    """Concrete addressing for one link."""

    link_key: tuple[str, str]
    subnet: IPv6Network  # /127
    a_addr: IPv6Address  # lower host (canonical A side)
    b_addr: IPv6Address  # upper host (canonical B side)

    def endpoints_for(self, node: str, iface: str) -> tuple[IPv6Address, IPv6Address]:
        """Return (local_addr, remote_addr) from the perspective of ``(node, iface)``."""
        side = f"{node}:{iface}"
        if side == self.link_key[0]:
            return self.a_addr, self.b_addr
        if side == self.link_key[1]:
            return self.b_addr, self.a_addr
        raise ValueError(f"{side!r} is not an endpoint of link {self.link_key}")


def _iter_p127_subnets(pool: IPv6Network, prefix_len: int):
    """Yield every /``prefix_len`` subnet within ``pool``."""
    if pool.prefixlen > prefix_len:
        raise ValueError(
            f"link_pool /{pool.prefixlen} cannot be subdivided into /{prefix_len} prefixes"
        )
    for subnet in pool.subnets(new_prefix=prefix_len):
        yield subnet


def allocate_stateless(fabric: Fabric) -> dict[tuple[str, str], LinkAllocation]:
    """Deterministic allocation from the intent alone (no DB required).

    Sorts links by canonical key and assigns /127s in iteration order over
    ``link_pool``. Adequate for offline renders; not stable if a new link's
    canonical key sorts before an existing one.
    """
    cfg: UnderlayConfig = fabric.underlay
    if cfg.mode != "numbered":
        return {}

    keys_sorted = sorted(canonical_key(link) for link in fabric.links)
    out: dict[tuple[str, str], LinkAllocation] = {}
    subnet_iter = _iter_p127_subnets(cfg.link_pool, cfg.link_prefix_len)
    for key in keys_sorted:
        out[key] = _subnet_to_allocation(key, next(subnet_iter))
    return out


def _subnet_to_allocation(
    key: tuple[str, str], subnet: IPv6Network
) -> LinkAllocation:
    # /127: address[0] and address[1] are both valid host addresses (RFC 6164).
    a = subnet[0]
    b = subnet[1] if subnet.num_addresses > 1 else subnet[0]
    return LinkAllocation(link_key=key, subnet=subnet, a_addr=a, b_addr=b)


@dataclass(frozen=True)
class PoolStats:
    """Link-pool utilisation snapshot."""

    pool: str
    prefix_len: int
    total_slots: int
    used_slots: int

    @property
    def utilization(self) -> float:
        return self.used_slots / self.total_slots if self.total_slots else 0.0

    @property
    def free_slots(self) -> int:
        return self.total_slots - self.used_slots


def pool_stats(fabric: Fabric, allocations: dict[tuple[str, str], LinkAllocation]) -> PoolStats:
    cfg = fabric.underlay
    total = 1 << (cfg.link_prefix_len - cfg.link_pool.prefixlen)
    return PoolStats(
        pool=str(cfg.link_pool),
        prefix_len=cfg.link_prefix_len,
        total_slots=total,
        used_slots=len(allocations),
    )


async def allocate_persistent(
    fabric: Fabric,
    session,
    *,
    gc: bool = True,
    warn_threshold: float = 0.75,
) -> dict[tuple[str, str], LinkAllocation]:
    """Persistent, idempotent allocator backed by ``link_address`` rows.

    * Existing allocations for links that are still present are reused verbatim.
    * New links consume the next free /127 from the pool.
    * When ``gc=True`` (default), rows whose ``link_key`` is no longer in the
      fabric are deleted so the pool can be reused for tight-pool deployments.
    * When utilisation crosses ``warn_threshold`` (default 0.75), a structured
      warning is logged. Callers can still surface the same data via
      ``pool_stats()``.

    Note: ``link_key`` is globally unique across nodes only if node names are
    unique across fabrics. Multi-fabric deployments should add a ``fabric_id``
    column before enabling GC.
    """
    from sqlalchemy import select

    from .logging import log
    from .store.models_sql import LinkAddressRow

    cfg: UnderlayConfig = fabric.underlay
    if cfg.mode != "numbered":
        return {}

    rows = (await session.execute(select(LinkAddressRow))).scalars().all()
    existing: dict[str, LinkAddressRow] = {r.link_key: r for r in rows}

    def _key_str(key: tuple[str, str]) -> str:
        return f"{key[0]}|{key[1]}"

    wanted: set[str] = {_key_str(canonical_key(link)) for link in fabric.links}

    # GC stale rows first so their /127s become available for new links.
    reclaimed: list[LinkAddressRow] = []
    if gc:
        for ks, row in list(existing.items()):
            if ks not in wanted:
                reclaimed.append(row)
                del existing[ks]
        for row in reclaimed:
            await session.delete(row)
        if reclaimed:
            log.info(
                "link-pool-gc",
                reclaimed=len(reclaimed),
                keys=[r.link_key for r in reclaimed],
            )

    used_subnets: set[str] = {r.subnet for r in existing.values()}
    subnet_iter = _iter_p127_subnets(cfg.link_pool, cfg.link_prefix_len)

    def _next_free() -> IPv6Network:
        for subnet in subnet_iter:
            if str(subnet) not in used_subnets:
                used_subnets.add(str(subnet))
                return subnet
        raise RuntimeError("link_pool exhausted")

    out: dict[tuple[str, str], LinkAllocation] = {}
    new_rows: list[LinkAddressRow] = []
    for link in fabric.links:
        key = canonical_key(link)
        ks = _key_str(key)
        if ks in existing:
            row = existing[ks]
            out[key] = LinkAllocation(
                link_key=key,
                subnet=IPv6Network(row.subnet),
                a_addr=IPv6Address(row.a_addr),
                b_addr=IPv6Address(row.b_addr),
            )
            continue
        subnet = _next_free()
        alloc = _subnet_to_allocation(key, subnet)
        out[key] = alloc
        new_rows.append(
            LinkAddressRow(
                link_key=ks,
                subnet=str(alloc.subnet),
                a_addr=str(alloc.a_addr),
                b_addr=str(alloc.b_addr),
            )
        )

    if new_rows:
        session.add_all(new_rows)
    if new_rows or reclaimed:
        await session.commit()

    stats = pool_stats(fabric, out)
    if stats.utilization >= warn_threshold:
        log.warning(
            "link-pool-high-utilization",
            pool=stats.pool,
            used=stats.used_slots,
            total=stats.total_slots,
            utilization=round(stats.utilization, 4),
            threshold=warn_threshold,
        )
    return out
