"""Pool stats + 75% alarm + persistent-allocator GC."""
from __future__ import annotations

from ipaddress import IPv6Network

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from usg_sdn.allocator import allocate_persistent, pool_stats
from usg_sdn.models.intent import IntentDocument
from usg_sdn.store.db import Base
from usg_sdn.store.models_sql import LinkAddressRow  # noqa: F401  register mapper


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s
    await engine.dispose()


def test_pool_stats_full_default_pool(intent: IntentDocument) -> None:
    from usg_sdn.allocator import allocate_stateless

    allocs = allocate_stateless(intent.fabric)
    stats = pool_stats(intent.fabric, allocs)
    # Default pool /56 with /127 prefix → 2^71 slots; allocations are a tiny fraction.
    assert stats.used_slots == len(intent.fabric.links)
    assert stats.total_slots > stats.used_slots
    assert stats.utilization < 0.01


def test_pool_stats_tight_pool_triggers_alarm(intent_3tier: IntentDocument) -> None:
    # 3-tier example uses /120 with /127 → 128 slots. 8 links → 6.25% (below 75%).
    # Shrink to verify the threshold trips.
    from usg_sdn.allocator import allocate_stateless

    tight = intent_3tier.fabric.model_copy(
        update={
            "underlay": intent_3tier.fabric.underlay.model_copy(
                update={"link_pool": IPv6Network("fd00:face:b00c:9000::/123")}  # /123 → 16 slots
            )
        }
    )
    allocs = allocate_stateless(tight)
    stats = pool_stats(tight, allocs)
    assert stats.total_slots == 16
    assert stats.used_slots == 8
    assert stats.utilization == 0.5  # not yet over the default threshold
    tighter = tight.model_copy(
        update={
            "underlay": tight.underlay.model_copy(
                update={"link_pool": IPv6Network("fd00:face:b00c:9000::/124")}  # /124 → 8 slots
            )
        }
    )
    allocs2 = allocate_stateless(tighter)
    stats2 = pool_stats(tighter, allocs2)
    assert stats2.utilization == 1.0
    assert stats2.utilization >= 0.75


async def test_persistent_allocator_gc_reclaims_rows(
    intent: IntentDocument, session: AsyncSession
) -> None:
    allocs_before = await allocate_persistent(intent.fabric, session)
    rows_before = (await session.execute(select(LinkAddressRow))).scalars().all()
    assert len(rows_before) == len(intent.fabric.links)

    # Remove two links from the intent; re-allocate with GC.
    trimmed = intent.fabric.model_copy(
        update={"links": list(intent.fabric.links)[:-2]}
    )
    allocs_after = await allocate_persistent(trimmed, session, gc=True)
    rows_after = (await session.execute(select(LinkAddressRow))).scalars().all()
    assert len(rows_after) == len(trimmed.links)
    assert len(allocs_after) == len(trimmed.links)
    # Addresses that survived are unchanged.
    for key, alloc in allocs_after.items():
        assert allocs_before[key] == alloc


async def test_persistent_allocator_reuses_reclaimed_slots(
    intent: IntentDocument, session: AsyncSession
) -> None:
    # Use a tight pool: exactly enough for the current link count.
    n_links = len(intent.fabric.links)
    # n_links=6 → /125 = 4 /127s, too tight; /124=8 is comfortable. Pick /124.
    tight_fabric = intent.fabric.model_copy(
        update={
            "underlay": intent.fabric.underlay.model_copy(
                update={
                    "link_pool": IPv6Network("fd00:face:b00c:ff00::/124"),  # 8 slots
                }
            )
        }
    )
    await allocate_persistent(tight_fabric, session)
    # Drop one link then add a different new link; GC should free the old /127
    # and the new link reuses it.
    links = list(tight_fabric.links)
    new_link = links[0].model_copy(
        update={
            "a_iface": "Ethernet99",
            "description": "replaces first link",
        }
    )
    replaced = tight_fabric.model_copy(update={"links": links[1:] + [new_link]})
    await allocate_persistent(replaced, session, gc=True)
    rows = (await session.execute(select(LinkAddressRow))).scalars().all()
    # Row count must still equal link count (no leaks, no duplicates).
    assert len(rows) == n_links
