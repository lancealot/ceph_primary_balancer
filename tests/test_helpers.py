"""Shared test utilities — not production code."""

from ceph_primary_balancer.models import ClusterState, OSDInfo, HostInfo, PoolInfo
from ceph_primary_balancer.scorer import Scorer


def simulate_swap_score(state: ClusterState, pgid: str, new_primary: int, scorer: Scorer) -> float:
    """Full-state-copy swap simulation used as a test oracle for delta scoring.

    Creates a complete copy of OSD/host/pool counts with the swap applied,
    then scores the result. O(N) — only used in tests to verify that the
    O(1) delta scorer produces identical results.
    """
    pg = state.pgs[pgid]
    old_primary = pg.primary

    simulated_osds = {}
    for osd_id, osd in state.osds.items():
        simulated_osds[osd_id] = OSDInfo(
            osd_id=osd.osd_id, host=osd.host,
            primary_count=osd.primary_count, total_pg_count=osd.total_pg_count,
        )
    simulated_osds[old_primary].primary_count -= 1
    simulated_osds[new_primary].primary_count += 1

    simulated_hosts = {}
    if state.hosts:
        for hostname, host in state.hosts.items():
            simulated_hosts[hostname] = HostInfo(
                hostname=host.hostname, osd_ids=host.osd_ids[:],
                primary_count=0, total_pg_count=0,
            )
        for osd in simulated_osds.values():
            if osd.host and osd.host in simulated_hosts:
                simulated_hosts[osd.host].primary_count += osd.primary_count
                simulated_hosts[osd.host].total_pg_count += osd.total_pg_count

    simulated_pools = {}
    if state.pools:
        for pool_id, pool in state.pools.items():
            simulated_pools[pool_id] = PoolInfo(
                pool_id=pool.pool_id, pool_name=pool.pool_name,
                pg_count=pool.pg_count, primary_counts=pool.primary_counts.copy(),
                participating_osds=pool.participating_osds,
            )
        pool_id = pg.pool_id
        if pool_id in simulated_pools:
            if old_primary in simulated_pools[pool_id].primary_counts:
                simulated_pools[pool_id].primary_counts[old_primary] -= 1
                if simulated_pools[pool_id].primary_counts[old_primary] == 0:
                    del simulated_pools[pool_id].primary_counts[old_primary]
            if new_primary not in simulated_pools[pool_id].primary_counts:
                simulated_pools[pool_id].primary_counts[new_primary] = 0
            simulated_pools[pool_id].primary_counts[new_primary] += 1

    simulated_state = ClusterState(
        pgs=state.pgs, osds=simulated_osds,
        hosts=simulated_hosts, pools=simulated_pools,
    )
    return scorer.calculate_score(simulated_state)
