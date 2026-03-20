"""Integration test: host-level balancing on a synthetic imbalanced cluster."""

from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
from ceph_primary_balancer.analyzer import calculate_statistics


def test_host_balancing_improves_cv(host_imbalanced_cluster):
    """Optimizer reduces both OSD and host CV on a host-imbalanced cluster."""
    state = host_imbalanced_cluster

    initial_osd_cv = calculate_statistics(
        [o.primary_count for o in state.osds.values()]
    ).cv
    initial_host_cv = calculate_statistics(
        [h.primary_count for h in state.hosts.values()]
    ).cv

    scorer = Scorer(w_osd=0.7, w_host=0.3, w_pool=0.0)
    swaps = GreedyOptimizer(
        target_cv=0.10, max_iterations=1000, scorer=scorer,
    ).optimize(state)

    final_osd_cv = calculate_statistics(
        [o.primary_count for o in state.osds.values()]
    ).cv
    final_host_cv = calculate_statistics(
        [h.primary_count for h in state.hosts.values()]
    ).cv

    assert len(swaps) > 0, "Should find beneficial swaps"
    assert final_osd_cv < initial_osd_cv, (
        f"OSD CV should improve: {initial_osd_cv:.4f} -> {final_osd_cv:.4f}"
    )
    assert final_host_cv < initial_host_cv, (
        f"Host CV should improve: {initial_host_cv:.4f} -> {final_host_cv:.4f}"
    )

    # Primary count integrity
    total_primaries = sum(o.primary_count for o in state.osds.values())
    assert total_primaries == len(state.pgs)
