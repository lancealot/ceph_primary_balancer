"""Tests for per-pool donor/receiver identification."""

from ceph_primary_balancer.models import (
    ClusterState, PGInfo, OSDInfo, PoolInfo,
)
from ceph_primary_balancer.analyzer import (
    identify_donors, identify_receivers,
    identify_pool_donors_receivers, calculate_pool_statistics,
)
from ceph_primary_balancer.optimizers.greedy import find_best_swap, apply_swap
from ceph_primary_balancer.scorer import Scorer


def _make_pool_imbalanced_cluster():
    """
    Cluster where OSD-level balance is perfect but Pool 1 is severely
    imbalanced. Without pool-level donors/receivers, no swaps would be
    proposed for Pool 1.

    4 OSDs, each with 10 total primaries (perfect OSD balance).
    Pool 1: OSD 0 has 8 primaries, OSDs 1-3 have ~0-1 each.
    Pool 2: roughly even.
    """
    osds = {
        0: OSDInfo(osd_id=0, host='h0', primary_count=10, total_pg_count=20),
        1: OSDInfo(osd_id=1, host='h1', primary_count=10, total_pg_count=20),
        2: OSDInfo(osd_id=2, host='h2', primary_count=10, total_pg_count=20),
        3: OSDInfo(osd_id=3, host='h3', primary_count=10, total_pg_count=20),
    }

    # Pool 1: 10 PGs, severely imbalanced — OSD 0 is primary for 8 of them
    pool1_pgs = {}
    pool1_primary_counts = {0: 8, 1: 1, 2: 1, 3: 0}
    for i in range(8):
        pool1_pgs[f'1.{i}'] = PGInfo(pgid=f'1.{i}', pool_id=1,
                                      acting=[0, (i % 3) + 1, ((i + 1) % 3) + 1])
    pool1_pgs['1.8'] = PGInfo(pgid='1.8', pool_id=1, acting=[1, 0, 2])
    pool1_pgs['1.9'] = PGInfo(pgid='1.9', pool_id=1, acting=[2, 0, 3])

    # Pool 2: 30 PGs, roughly balanced
    pool2_pgs = {}
    pool2_primary_counts = {0: 2, 1: 9, 2: 9, 3: 10}
    for i in range(30):
        primary = [0, 1, 1, 1, 2, 2, 2, 3, 3, 3][i % 10]
        others = [o for o in range(4) if o != primary]
        pool2_pgs[f'2.{i}'] = PGInfo(pgid=f'2.{i}', pool_id=2,
                                      acting=[primary, others[0], others[1]])

    pgs = {**pool1_pgs, **pool2_pgs}

    pools = {
        1: PoolInfo(pool_id=1, pool_name='pool1', pg_count=10,
                    primary_counts=pool1_primary_counts),
        2: PoolInfo(pool_id=2, pool_name='pool2', pg_count=30,
                    primary_counts=pool2_primary_counts),
    }

    hosts = {}  # Skip hosts for simplicity

    return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)


def test_osd_level_sees_no_donors_when_balanced():
    """When OSD-level is balanced, global donors/receivers should be empty."""
    state = _make_pool_imbalanced_cluster()
    donors = identify_donors(state.osds)
    receivers = identify_receivers(state.osds)
    assert donors == []
    assert receivers == []


def test_pool_level_identifies_imbalanced_pool():
    """Pool-level donors/receivers should identify Pool 1's imbalance."""
    state = _make_pool_imbalanced_cluster()
    pool_donors, pool_receivers = identify_pool_donors_receivers(state)

    # Pool 1 should have donors (OSD 0 with 8 primaries, mean ~2.5)
    assert 1 in pool_donors
    assert 0 in pool_donors[1]

    # Pool 1 should have receivers (OSDs with 0-1 primaries)
    assert 1 in pool_receivers
    assert len(pool_receivers[1]) > 0


def test_find_best_swap_proposes_pool_swap_when_osd_balanced():
    """
    With pool-level donors/receivers, find_best_swap should propose swaps
    for pool-imbalanced PGs even when OSD-level balance is perfect.
    """
    state = _make_pool_imbalanced_cluster()
    scorer = Scorer(w_osd=0.5, w_host=0.0, w_pool=0.5, enabled_levels=['osd', 'pool'])

    # OSD-level: no donors/receivers
    donors = identify_donors(state.osds)
    receivers = identify_receivers(state.osds)
    assert donors == []
    assert receivers == []

    # Pool-level: Pool 1 has donors/receivers
    pool_donors, pool_receivers = identify_pool_donors_receivers(state)

    # Without pool donors/receivers: no swap possible
    swap_without = find_best_swap(state, donors, receivers, scorer)
    assert swap_without is None

    # With pool donors/receivers: swap should be proposed
    swap_with = find_best_swap(state, donors, receivers, scorer,
                                pool_donors, pool_receivers)
    assert swap_with is not None
    assert swap_with.score_improvement > 0

    # The swap should move a primary FROM Pool 1's donor (OSD 0)
    assert swap_with.old_primary == 0
    # The PG should be from Pool 1
    assert state.pgs[swap_with.pgid].pool_id == 1


def test_pool_balance_improves_after_swaps():
    """Run multiple swaps and verify Pool 1 variance decreases."""
    state = _make_pool_imbalanced_cluster()
    scorer = Scorer(w_osd=0.5, w_host=0.0, w_pool=0.5, enabled_levels=['osd', 'pool'])

    pool1 = state.pools[1]
    initial_stats = calculate_pool_statistics(pool1, state.osds)
    initial_cv = initial_stats.cv

    for _ in range(20):
        donors = identify_donors(state.osds)
        receivers = identify_receivers(state.osds)
        pool_donors, pool_receivers = identify_pool_donors_receivers(state)

        swap = find_best_swap(state, donors, receivers, scorer,
                               pool_donors, pool_receivers)
        if swap is None:
            break
        apply_swap(state, swap)

    final_stats = calculate_pool_statistics(pool1, state.osds)
    assert final_stats.cv < initial_cv, (
        f"Pool 1 CV should decrease: {initial_cv:.4f} -> {final_stats.cv:.4f}"
    )


def test_pool_donors_empty_for_balanced_pools():
    """Pool-level donors/receivers should be empty for balanced pools."""
    osds = {i: OSDInfo(osd_id=i, primary_count=10, total_pg_count=20)
            for i in range(4)}
    pools = {
        1: PoolInfo(pool_id=1, pool_name='p1', pg_count=40,
                    primary_counts={0: 10, 1: 10, 2: 10, 3: 10}),
    }
    pgs = {}
    for i in range(40):
        primary = i % 4
        others = [o for o in range(4) if o != primary]
        pgs[f'1.{i}'] = PGInfo(pgid=f'1.{i}', pool_id=1,
                                acting=[primary, others[0], others[1]])

    state = ClusterState(pgs=pgs, osds=osds, pools=pools)
    pool_donors, pool_receivers = identify_pool_donors_receivers(state)

    assert 1 not in pool_donors
    assert 1 not in pool_receivers
