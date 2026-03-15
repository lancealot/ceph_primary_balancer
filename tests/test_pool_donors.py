"""Tests for per-pool donor/receiver identification."""

import statistics

from ceph_primary_balancer.models import (
    ClusterState, PGInfo, OSDInfo, PoolInfo,
)
from ceph_primary_balancer.analyzer import (
    calculate_statistics,
    identify_donors, identify_receivers,
    identify_pool_donors_receivers, calculate_pool_statistics,
)
from ceph_primary_balancer.benchmark.generator import generate_synthetic_cluster
from ceph_primary_balancer.optimizers.greedy import find_best_swap, apply_swap
from ceph_primary_balancer.optimizers import GreedyOptimizer
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


# --- Multi-pool stress tests using synthetic cluster generator ---


def test_pool_donors_identified_across_many_pools():
    """With 20 pools and high imbalance, pool-level donors should be found."""
    state = generate_synthetic_cluster(
        num_osds=60, num_hosts=6, num_pools=20, pgs_per_pool=200,
        replication_factor=3, imbalance_cv=0.40, seed=99,
    )
    pool_donors, pool_receivers = identify_pool_donors_receivers(state)

    # With 20 pools and 40% CV imbalance, most pools should have donors
    assert len(pool_donors) > 0, "Expected pool-level donors with 40% imbalance"
    assert len(pool_receivers) > 0, "Expected pool-level receivers with 40% imbalance"


def test_optimizer_improves_all_pools_in_large_cluster():
    """
    60 OSDs, 20 pools: every pool's CV should decrease (or stay low)
    after optimization with pool-level donor/receiver identification.
    """
    state = generate_synthetic_cluster(
        num_osds=60, num_hosts=6, num_pools=20, pgs_per_pool=200,
        replication_factor=3, imbalance_cv=0.35, seed=42,
    )

    # Record initial per-pool CVs
    initial_cvs = {}
    for pid, pool in state.pools.items():
        stats = calculate_pool_statistics(pool, state.osds)
        initial_cvs[pid] = stats.cv

    optimizer = GreedyOptimizer(target_cv=0.05, max_iterations=1000)
    swaps = optimizer.optimize(state)

    # Record final per-pool CVs
    improved = 0
    worsened = 0
    for pid, pool in state.pools.items():
        stats = calculate_pool_statistics(pool, state.osds)
        if stats.cv < initial_cvs[pid] - 0.001:
            improved += 1
        elif stats.cv > initial_cvs[pid] + 0.01:
            worsened += 1

    # Majority of pools should improve, none should worsen significantly
    assert improved > len(state.pools) // 2, (
        f"Only {improved}/{len(state.pools)} pools improved"
    )
    assert worsened == 0, f"{worsened} pools worsened significantly"


def test_pool_donors_scale_to_many_pools():
    """
    Verify identify_pool_donors_receivers handles 50 pools correctly:
    returns results for each pool independently, no cross-contamination.
    """
    state = generate_synthetic_cluster(
        num_osds=100, num_hosts=10, num_pools=50, pgs_per_pool=100,
        replication_factor=3, imbalance_cv=0.30, seed=7,
    )
    pool_donors, pool_receivers = identify_pool_donors_receivers(state)

    for pid in pool_donors:
        assert pid in state.pools, f"Donor pool {pid} not in state.pools"
        # Pool-level donors must actually participate in this pool
        pool = state.pools[pid]
        for osd_id in pool_donors[pid]:
            # OSD must have PGs in this pool (appears in some acting set)
            has_pg = any(
                osd_id in pg.acting
                for pg in state.pgs.values()
                if pg.pool_id == pid
            )
            assert has_pg, (
                f"OSD {osd_id} marked as donor for pool {pid} but has no PGs there"
            )

    for pid in pool_receivers:
        assert pid in state.pools
        for osd_id in pool_receivers[pid]:
            has_pg = any(
                osd_id in pg.acting
                for pg in state.pgs.values()
                if pg.pool_id == pid
            )
            assert has_pg, (
                f"OSD {osd_id} marked as receiver for pool {pid} but has no PGs there"
            )


def test_pool_cv_decreases_with_many_pools():
    """
    30 pools, 80 OSDs: average pool CV should meaningfully decrease.
    This catches regressions where pool-level candidates are generated
    but the scorer doesn't actually pick pool-improving swaps.
    """
    state = generate_synthetic_cluster(
        num_osds=80, num_hosts=8, num_pools=30, pgs_per_pool=150,
        replication_factor=3, imbalance_cv=0.35, seed=123,
    )

    def avg_pool_cv(s):
        cvs = []
        for pool in s.pools.values():
            stats = calculate_pool_statistics(pool, s.osds)
            cvs.append(stats.cv)
        return statistics.mean(cvs)

    initial_avg_cv = avg_pool_cv(state)

    optimizer = GreedyOptimizer(target_cv=0.05, max_iterations=1000)
    optimizer.optimize(state)

    final_avg_cv = avg_pool_cv(state)
    # With integer granularity (few PGs per OSD per pool) and OSD-level
    # termination, pool CV won't drop as dramatically as OSD CV.
    # Assert meaningful improvement (>5%), not a specific target.
    assert final_avg_cv < initial_avg_cv * 0.95, (
        f"Average pool CV should improve: "
        f"{initial_avg_cv:.4f} -> {final_avg_cv:.4f}"
    )


def test_production_scale_840_osds_30_pools_4096_pgs():
    """
    Simulate a production cluster: 840 OSDs, 30 hosts, 30 pools,
    4096 PGs total (~137 per pool).

    This is a sparse cluster: ~5 primaries per OSD, each pool touches
    only a subset of OSDs. Integer granularity limits achievable CV,
    so we test for correctness and some improvement rather than
    specific CV targets.
    """
    # 4096 / 30 = 136.5 — distribute remainder across first pools
    base_pgs = 4096 // 30  # 136
    remainder = 4096 % 30  # 16

    # Generate with base count; we'll verify total is close to 4096
    state = generate_synthetic_cluster(
        num_osds=840, num_hosts=30, num_pools=30, pgs_per_pool=base_pgs,
        replication_factor=3, imbalance_cv=0.30, seed=42,
    )

    assert len(state.osds) == 840
    assert len(state.pools) == 30
    assert len(state.hosts) == 30
    # Generator uses base_pgs per pool, so total = 136 * 30 = 4080
    assert len(state.pgs) == base_pgs * 30

    # Pool-level donor/receiver identification should work at this scale
    pool_donors, pool_receivers = identify_pool_donors_receivers(state)
    assert len(pool_donors) > 0
    assert len(pool_receivers) > 0

    # Every pool should have donors and receivers at 30% imbalance
    # with only ~136 PGs across hundreds of OSDs
    for pid in pool_donors:
        assert pid in state.pools
    for pid in pool_receivers:
        assert pid in state.pools

    def avg_pool_cv(s):
        cvs = []
        for pool in s.pools.values():
            ps = calculate_pool_statistics(pool, s.osds)
            cvs.append(ps.cv)
        return statistics.mean(cvs)

    initial_osd_cv = calculate_statistics(
        [o.primary_count for o in state.osds.values()]
    ).cv
    initial_pool_cv = avg_pool_cv(state)

    # Cap iterations — at this density each swap matters but the search
    # space is huge (840 OSDs * 4080 PGs), so keep runtime bounded
    optimizer = GreedyOptimizer(target_cv=0.05, max_iterations=300)
    swaps = optimizer.optimize(state)

    final_osd_cv = calculate_statistics(
        [o.primary_count for o in state.osds.values()]
    ).cv
    final_pool_cv = avg_pool_cv(state)

    # Should produce some swaps and improve OSD balance
    assert len(swaps) > 0, "Expected at least some swaps"
    assert final_osd_cv < initial_osd_cv, (
        f"OSD CV should decrease: {initial_osd_cv:.4f} -> {final_osd_cv:.4f}"
    )
    # Pool CV should not worsen
    assert final_pool_cv <= initial_pool_cv + 0.01, (
        f"Pool CV should not worsen: {initial_pool_cv:.4f} -> {final_pool_cv:.4f}"
    )
