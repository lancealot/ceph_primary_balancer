"""Integration test: three-dimensional balancing on a multi-pool cluster."""

from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
from ceph_primary_balancer.analyzer import calculate_statistics, get_pool_statistics_summary


def test_pool_balancing_improves_all_dimensions(multi_pool_cluster):
    """Optimizer improves OSD, host, and pool CV on a multi-pool cluster."""
    state = multi_pool_cluster

    initial_osd_cv = calculate_statistics(
        [o.primary_count for o in state.osds.values()]
    ).cv
    initial_host_cv = calculate_statistics(
        [h.primary_count for h in state.hosts.values()]
    ).cv
    initial_pool_stats = get_pool_statistics_summary(state)
    initial_avg_pool_cv = (
        sum(ps.cv for ps in initial_pool_stats.values()) / len(initial_pool_stats)
    )

    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
    swaps = GreedyOptimizer(
        target_cv=0.10, max_iterations=1000, scorer=scorer,
    ).optimize(state)

    final_osd_cv = calculate_statistics(
        [o.primary_count for o in state.osds.values()]
    ).cv
    final_host_cv = calculate_statistics(
        [h.primary_count for h in state.hosts.values()]
    ).cv
    final_pool_stats = get_pool_statistics_summary(state)
    final_avg_pool_cv = (
        sum(ps.cv for ps in final_pool_stats.values()) / len(final_pool_stats)
    )

    assert final_osd_cv <= initial_osd_cv, (
        f"OSD CV should not worsen: {initial_osd_cv:.4f} -> {final_osd_cv:.4f}"
    )
    assert final_host_cv <= initial_host_cv, (
        f"Host CV should not worsen: {initial_host_cv:.4f} -> {final_host_cv:.4f}"
    )
    assert final_avg_pool_cv <= initial_avg_pool_cv, (
        f"Pool CV should not worsen: {initial_avg_pool_cv:.4f} -> {final_avg_pool_cv:.4f}"
    )

    # Primary count integrity
    total_primaries = sum(o.primary_count for o in state.osds.values())
    assert total_primaries == len(state.pgs)

    # Per-pool integrity
    for pool in state.pools.values():
        pool_primaries = sum(pool.primary_counts.values())
        assert pool_primaries == pool.pg_count, (
            f"Pool {pool.pool_name}: {pool_primaries} primaries != {pool.pg_count} PGs"
        )
