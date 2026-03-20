"""Shared test fixtures for cluster-building."""

import pytest

from ceph_primary_balancer.models import (
    PGInfo, OSDInfo, HostInfo, PoolInfo, ClusterState,
)


def _build_osds_and_hosts(host_configs):
    """Build OSD and host dicts from a {hostname: [osd_ids]} mapping."""
    osds = {}
    for hostname, osd_ids in host_configs.items():
        for osd_id in osd_ids:
            osds[osd_id] = OSDInfo(
                osd_id=osd_id, host=hostname,
                primary_count=0, total_pg_count=0,
            )
    hosts = {}
    for hostname, osd_ids in host_configs.items():
        hosts[hostname] = HostInfo(
            hostname=hostname, osd_ids=osd_ids,
            primary_count=0, total_pg_count=0,
        )
    return osds, hosts


def _make_acting_set(primary, all_osds, osds, replica_count=3):
    """Build an acting set with replicas on different hosts."""
    acting = [primary]
    primary_host = osds[primary].host
    added_hosts = {primary_host}

    # First pass: replicas from different hosts
    for osd_id in all_osds:
        if len(acting) >= replica_count:
            break
        host = osds[osd_id].host
        if osd_id != primary and host not in added_hosts:
            acting.append(osd_id)
            added_hosts.add(host)

    # Second pass: fill remaining slots
    for osd_id in all_osds:
        if len(acting) >= replica_count:
            break
        if osd_id not in acting:
            acting.append(osd_id)

    return acting


def _tally_counts(pgs, osds, hosts, pools=None):
    """Aggregate primary/PG counts on OSDs, hosts, and optionally pools."""
    for pg in pgs.values():
        primary = pg.primary
        osds[primary].primary_count += 1
        for osd_id in pg.acting:
            osds[osd_id].total_pg_count += 1
        if pools and pg.pool_id in pools:
            pool = pools[pg.pool_id]
            pool.pg_count += 1
            pool.primary_counts[primary] = pool.primary_counts.get(primary, 0) + 1

    for osd in osds.values():
        if osd.host in hosts:
            hosts[osd.host].primary_count += osd.primary_count
            hosts[osd.host].total_pg_count += osd.total_pg_count


def build_host_imbalanced_cluster():
    """20-OSD, 4-host, 1-pool cluster with host-level primary imbalance.

    Host1/2 are overloaded with primaries; host3/4 are underutilized.
    OSD-level balance is moderate; host-level balance is poor.
    """
    host_configs = {
        "host1": [0, 1, 2, 3, 4, 5],
        "host2": [6, 7, 8, 9, 10, 11],
        "host3": [12, 13, 14, 15],
        "host4": [16, 17, 18, 19],
    }
    osds, hosts = _build_osds_and_hosts(host_configs)
    all_osds = list(range(20))

    # Primary distribution: host1 gets ~60/OSD, host2 ~55, host3 ~40, host4 ~37-38
    primary_distribution = (
        [0]*10 + [1]*10 + [2]*10 + [3]*10 + [4]*10 + [5]*10 +
        [6]*11 + [7]*11 + [8]*11 + [9]*11 + [10]*11 + [11]*11 +
        [12]*8 + [13]*8 + [14]*8 + [15]*8 +
        [16]*9 + [17]*9 + [18]*8 + [19]*8
    )

    pgs = {}
    pg_count = 1000
    for pg_idx in range(pg_count):
        pgid = f"1.{pg_idx:x}"
        if pg_idx < len(primary_distribution) * 6:
            primary = primary_distribution[pg_idx % len(primary_distribution)]
        else:
            primary = all_osds[pg_idx % 20]
        acting = _make_acting_set(primary, all_osds, osds)
        pgs[pgid] = PGInfo(pgid=pgid, pool_id=1, acting=acting)

    _tally_counts(pgs, osds, hosts)
    return ClusterState(pgs=pgs, osds=osds, hosts=hosts)


def build_multi_pool_cluster():
    """15-OSD, 3-host, 3-pool cluster with per-pool primary imbalance.

    Pool 1 (400 PGs): primaries concentrated on host1.
    Pool 2 (300 PGs): primaries concentrated on host2.
    Pool 3 (200 PGs): primaries concentrated on host3.
    """
    host_configs = {
        "host1": [0, 1, 2, 3, 4],
        "host2": [5, 6, 7, 8, 9],
        "host3": [10, 11, 12, 13, 14],
    }
    osds, hosts = _build_osds_and_hosts(host_configs)
    all_osds = list(range(15))

    pools = {
        1: PoolInfo(pool_id=1, pool_name="rbd_ssd", pg_count=0, primary_counts={}),
        2: PoolInfo(pool_id=2, pool_name="rbd_hdd", pg_count=0, primary_counts={}),
        3: PoolInfo(pool_id=3, pool_name="cephfs_data", pg_count=0, primary_counts={}),
    }

    pgs = {}
    pg_counter = 0

    pool_distributions = [
        (1, [0]*50 + [1]*50 + [2]*50 + [3]*50 + [4]*50 +
             [5]*30 + [6]*30 + [7]*30 + [8]*30 + [9]*30),
        (2, [5]*50 + [6]*50 + [7]*50 + [8]*50 + [9]*50 +
             [0]*10 + [1]*10 + [2]*10 + [3]*10 + [4]*10),
        (3, [10]*35 + [11]*35 + [12]*35 + [13]*35 + [14]*35 +
             [0]*5 + [1]*5 + [2]*5 + [3]*5 + [4]*5),
    ]

    for pool_id, distribution in pool_distributions:
        for primary in distribution:
            pgid = f"{pool_id}.{pg_counter:x}"
            acting = _make_acting_set(primary, all_osds, osds)
            pgs[pgid] = PGInfo(pgid=pgid, pool_id=pool_id, acting=acting)
            pg_counter += 1

    _tally_counts(pgs, osds, hosts, pools)
    return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)


@pytest.fixture
def host_imbalanced_cluster():
    """Fixture: 20-OSD cluster with host-level imbalance."""
    return build_host_imbalanced_cluster()


@pytest.fixture
def multi_pool_cluster():
    """Fixture: 15-OSD, 3-pool cluster with per-pool imbalance."""
    return build_multi_pool_cluster()
