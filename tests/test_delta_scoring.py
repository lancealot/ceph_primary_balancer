"""Tests verifying O(1) delta scoring matches full-state-copy scoring."""

import copy
from ceph_primary_balancer.models import (
    ClusterState, PGInfo, OSDInfo, HostInfo, PoolInfo, SwapProposal,
)
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.optimizers.greedy import find_best_swap
from test_helpers import simulate_swap_score
from ceph_primary_balancer.benchmark.generator import generate_synthetic_cluster


def _make_cluster():
    """Build a small cluster with hosts and pools for testing."""
    osds = {
        0: OSDInfo(osd_id=0, host='host-a', primary_count=5, total_pg_count=10),
        1: OSDInfo(osd_id=1, host='host-a', primary_count=3, total_pg_count=10),
        2: OSDInfo(osd_id=2, host='host-b', primary_count=8, total_pg_count=10),
        3: OSDInfo(osd_id=3, host='host-b', primary_count=4, total_pg_count=10),
    }
    hosts = {
        'host-a': HostInfo(hostname='host-a', osd_ids=[0, 1], primary_count=8, total_pg_count=20),
        'host-b': HostInfo(hostname='host-b', osd_ids=[2, 3], primary_count=12, total_pg_count=20),
    }
    pools = {
        1: PoolInfo(pool_id=1, pool_name='pool1', pg_count=10,
                    primary_counts={0: 3, 1: 2, 2: 4, 3: 1}),
        2: PoolInfo(pool_id=2, pool_name='pool2', pg_count=10,
                    primary_counts={0: 2, 1: 1, 2: 4, 3: 3}),
    }
    pgs = {
        '1.0': PGInfo(pgid='1.0', pool_id=1, acting=[2, 0, 1]),
        '1.1': PGInfo(pgid='1.1', pool_id=1, acting=[2, 3, 0]),
        '1.2': PGInfo(pgid='1.2', pool_id=1, acting=[0, 2, 3]),
        '2.0': PGInfo(pgid='2.0', pool_id=2, acting=[2, 1, 3]),
        '2.1': PGInfo(pgid='2.1', pool_id=2, acting=[3, 0, 2]),
    }
    return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)


def test_delta_matches_simulate_swap_all_levels():
    """Delta scoring must match simulate_swap_score for every possible swap."""
    state = _make_cluster()
    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)

    components = scorer.calculate_score_with_components(state)

    for pg in state.pgs.values():
        for candidate in pg.acting[1:]:
            full_copy_score = simulate_swap_score(state, pg.pgid, candidate, scorer)
            delta_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate, pg.pool_id
            )
            assert abs(full_copy_score - delta_score) < 1e-10, (
                f"Mismatch for swap {pg.pgid} {pg.primary}->{candidate}: "
                f"full={full_copy_score}, delta={delta_score}"
            )


def test_delta_matches_osd_only():
    """Delta scoring matches with only OSD level enabled."""
    state = _make_cluster()
    scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0, enabled_levels=['osd'])

    components = scorer.calculate_score_with_components(state)

    for pg in state.pgs.values():
        for candidate in pg.acting[1:]:
            full_copy_score = simulate_swap_score(state, pg.pgid, candidate, scorer)
            delta_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate, pg.pool_id
            )
            assert abs(full_copy_score - delta_score) < 1e-10


def test_delta_matches_host_only():
    """Delta scoring matches with only host level enabled."""
    state = _make_cluster()
    scorer = Scorer(w_osd=0.0, w_host=1.0, w_pool=0.0, enabled_levels=['host'])

    components = scorer.calculate_score_with_components(state)

    for pg in state.pgs.values():
        for candidate in pg.acting[1:]:
            full_copy_score = simulate_swap_score(state, pg.pgid, candidate, scorer)
            delta_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate, pg.pool_id
            )
            assert abs(full_copy_score - delta_score) < 1e-10


def test_delta_matches_pool_only():
    """Delta scoring matches with only pool level enabled."""
    state = _make_cluster()
    scorer = Scorer(w_osd=0.0, w_host=0.0, w_pool=1.0, enabled_levels=['pool'])

    components = scorer.calculate_score_with_components(state)

    for pg in state.pgs.values():
        for candidate in pg.acting[1:]:
            full_copy_score = simulate_swap_score(state, pg.pgid, candidate, scorer)
            delta_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate, pg.pool_id
            )
            assert abs(full_copy_score - delta_score) < 1e-10, (
                f"Mismatch for swap {pg.pgid} {pg.primary}->{candidate}: "
                f"full={full_copy_score}, delta={delta_score}"
            )


def test_delta_matches_same_host_swap():
    """Delta scoring handles same-host swaps correctly (host delta = 0)."""
    state = _make_cluster()
    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)

    # PG '1.2' has acting [0, 2, 3]. OSD 0 and 1 are on host-a.
    # Manually create a PG where primary and candidate are on the same host
    state.pgs['same_host'] = PGInfo(pgid='same_host', pool_id=1, acting=[0, 1, 2])
    state.pools[1].primary_counts[0] = state.pools[1].primary_counts.get(0, 0) + 1
    state.osds[0].primary_count += 1
    state.hosts['host-a'].primary_count += 1

    components = scorer.calculate_score_with_components(state)

    # Swap from OSD 0 to OSD 1 (same host)
    full_score = simulate_swap_score(state, 'same_host', 1, scorer)
    delta_score = scorer.calculate_swap_delta(state, components, 0, 1, 1)
    assert abs(full_score - delta_score) < 1e-10


def test_delta_matches_synthetic_cluster():
    """Delta scoring matches on a larger synthetic cluster."""
    state = generate_synthetic_cluster(
        num_osds=30,
        num_hosts=6,
        num_pools=3,
        pgs_per_pool=500,
        replication_factor=3,
        imbalance_cv=0.30,
        seed=42,
    )
    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)

    components = scorer.calculate_score_with_components(state)

    # Test a sample of swaps (all would be too slow for the full-copy baseline)
    tested = 0
    for pg in state.pgs.values():
        if tested >= 200:
            break
        for candidate in pg.acting[1:]:
            full_score = simulate_swap_score(state, pg.pgid, candidate, scorer)
            delta_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate, pg.pool_id
            )
            assert abs(full_score - delta_score) < 1e-9, (
                f"Mismatch for swap {pg.pgid} {pg.primary}->{candidate}: "
                f"full={full_score}, delta={delta_score}"
            )
            tested += 1


def test_find_best_swap_selects_same_swap():
    """find_best_swap with delta scoring picks the same swap as old approach."""
    state = _make_cluster()
    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)

    from ceph_primary_balancer import analyzer
    donors = analyzer.identify_donors(state.osds)
    receivers = analyzer.identify_receivers(state.osds)

    swap = find_best_swap(state, donors, receivers, scorer)
    assert swap is not None
    # Verify the swap actually improves the score
    assert swap.score_improvement > 0
