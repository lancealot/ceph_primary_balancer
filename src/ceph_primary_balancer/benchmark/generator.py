"""
Synthetic cluster state generator for benchmarking.

This module generates realistic test datasets with configurable parameters
for testing and validating the optimizer's performance and quality.
"""

import random
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import asdict

from ..models import PGInfo, OSDInfo, HostInfo, PoolInfo, ClusterState


def generate_imbalance_pattern(
    num_osds: int,
    total_primaries: int,
    pattern_type: str = 'random',
    target_cv: float = 0.30
) -> List[int]:
    """
    Generate specific imbalance patterns for primary distribution.
    
    Args:
        num_osds: Number of OSDs in cluster
        total_primaries: Total number of primaries to distribute
        pattern_type: Type of imbalance pattern
        target_cv: Target coefficient of variation for imbalance
        
    Pattern types:
        - 'random': Random distribution (natural cluster drift)
        - 'concentrated': Few OSDs severely overloaded
        - 'gradual': Linear gradient from low to high
        - 'bimodal': Two groups (high/low)
        - 'worst_case': All PGs on single OSD (testing extreme)
        - 'balanced': Near-perfect balance (CV < 0.05)
        
    Returns:
        List of primary counts per OSD
    """
    mean = total_primaries / num_osds
    
    if pattern_type == 'balanced':
        # Nearly perfect balance with small random variations
        counts = [int(mean) for _ in range(num_osds)]
        remainder = total_primaries - sum(counts)
        for i in range(remainder):
            counts[i % num_osds] += 1
        return counts
    
    elif pattern_type == 'random':
        # Random distribution targeting specific CV
        std_dev = target_cv * mean
        counts = []
        for _ in range(num_osds):
            count = int(random.gauss(mean, std_dev))
            count = max(0, count)  # No negative counts
            counts.append(count)
        
        # Adjust to match total
        current_total = sum(counts)
        if current_total != total_primaries:
            diff = total_primaries - current_total
            if diff > 0:
                for _ in range(diff):
                    counts[random.randint(0, num_osds - 1)] += 1
            else:
                for _ in range(-diff):
                    idx = random.randint(0, num_osds - 1)
                    if counts[idx] > 0:
                        counts[idx] -= 1
        return counts
    
    elif pattern_type == 'concentrated':
        # Few OSDs with most primaries (hotspot scenario)
        counts = [0] * num_osds
        hotspot_count = max(1, num_osds // 10)  # 10% are hotspots
        
        # Assign 70% to hotspots
        hotspot_primaries = int(total_primaries * 0.7)
        per_hotspot = hotspot_primaries // hotspot_count
        for i in range(hotspot_count):
            counts[i] = per_hotspot
        
        # Distribute remainder across all OSDs
        remainder = total_primaries - sum(counts)
        for i in range(remainder):
            counts[i % num_osds] += 1
        
        return counts
    
    elif pattern_type == 'gradual':
        # Linear gradient from low to high
        min_count = int(mean * (1 - target_cv))
        max_count = int(mean * (1 + target_cv))
        
        counts = []
        for i in range(num_osds):
            # Linear interpolation
            ratio = i / (num_osds - 1) if num_osds > 1 else 0
            count = int(min_count + ratio * (max_count - min_count))
            counts.append(count)
        
        # Adjust to match total
        diff = total_primaries - sum(counts)
        if diff > 0:
            counts[-1] += diff
        elif diff < 0:
            counts[0] += diff
        
        return counts
    
    elif pattern_type == 'bimodal':
        # Two distinct groups: high and low
        counts = []
        half = num_osds // 2
        
        low_count = int(mean * 0.7)
        high_count = int(mean * 1.3)
        
        for i in range(num_osds):
            if i < half:
                counts.append(low_count)
            else:
                counts.append(high_count)
        
        # Adjust to match total
        diff = total_primaries - sum(counts)
        if diff > 0:
            counts[-1] += diff
        elif diff < 0:
            counts[0] += diff
        
        return counts
    
    elif pattern_type == 'worst_case':
        # All primaries on single OSD (extreme imbalance)
        counts = [0] * num_osds
        counts[0] = total_primaries
        return counts
    
    else:
        raise ValueError(f"Unknown pattern type: {pattern_type}")


def generate_synthetic_cluster(
    num_osds: int = 100,
    num_hosts: int = 10,
    num_pools: int = 5,
    pgs_per_pool: int = 512,
    replication_factor: int = 3,
    imbalance_cv: float = 0.30,
    imbalance_pattern: str = 'random',
    seed: Optional[int] = None
) -> ClusterState:
    """
    Generate realistic synthetic cluster with specified imbalance.
    
    Args:
        num_osds: Number of OSDs in cluster
        num_hosts: Number of hosts (OSDs distributed evenly)
        num_pools: Number of pools to create
        pgs_per_pool: PGs per pool
        replication_factor: Replica count per PG
        imbalance_cv: Target coefficient of variation for imbalance
        imbalance_pattern: Type of imbalance pattern (see generate_imbalance_pattern)
        seed: Random seed for reproducibility (None = random)
        
    Returns:
        ClusterState with synthetic data
    """
    if seed is not None:
        random.seed(seed)
    
    # Validate inputs
    if num_osds < replication_factor:
        raise ValueError(f"num_osds ({num_osds}) must be >= replication_factor ({replication_factor})")
    
    if num_hosts > num_osds:
        raise ValueError(f"num_hosts ({num_hosts}) cannot exceed num_osds ({num_osds})")
    
    # Create OSDs with host assignments
    osds_per_host = num_osds // num_hosts
    osds = {}
    for osd_id in range(num_osds):
        host_idx = osd_id // osds_per_host if osds_per_host > 0 else 0
        host_idx = min(host_idx, num_hosts - 1)  # Handle remainder
        hostname = f"host-{host_idx:02d}"
        osds[osd_id] = OSDInfo(
            osd_id=osd_id,
            host=hostname,
            primary_count=0,
            total_pg_count=0
        )
    
    # Create hosts
    hosts = {}
    for host_idx in range(num_hosts):
        hostname = f"host-{host_idx:02d}"
        host_osd_ids = [
            osd_id for osd_id, osd_info in osds.items()
            if osd_info.host == hostname
        ]
        hosts[hostname] = HostInfo(
            hostname=hostname,
            osd_ids=host_osd_ids,
            primary_count=0,
            total_pg_count=0
        )
    
    # Create pools
    pools = {}
    for pool_id in range(1, num_pools + 1):
        pools[pool_id] = PoolInfo(
            pool_id=pool_id,
            pool_name=f"pool_{pool_id}",
            pg_count=pgs_per_pool,
            primary_counts={}
        )
    
    # Generate PGs with imbalanced primaries
    pgs = {}
    total_pgs = num_pools * pgs_per_pool
    
    # Generate primary distribution pattern
    primary_distribution = generate_imbalance_pattern(
        num_osds=num_osds,
        total_primaries=total_pgs,
        pattern_type=imbalance_pattern,
        target_cv=imbalance_cv
    )
    
    # Track which OSDs need primaries
    osd_primary_queue = []
    for osd_id, count in enumerate(primary_distribution):
        osd_primary_queue.extend([osd_id] * count)
    
    # Shuffle for randomness
    random.shuffle(osd_primary_queue)
    
    # Assign PGs
    pg_idx = 0
    for pool_id in range(1, num_pools + 1):
        for pg_num in range(pgs_per_pool):
            # Create PG ID (format: pool_id.pg_num_hex)
            pgid = f"{pool_id}.{pg_num:x}"
            
            # Assign primary from queue
            if pg_idx < len(osd_primary_queue):
                primary_osd = osd_primary_queue[pg_idx]
            else:
                primary_osd = random.randint(0, num_osds - 1)
            
            # Select replicas (excluding primary, ensuring enough OSDs)
            available_osds = [o for o in range(num_osds) if o != primary_osd]
            replica_count = min(replication_factor - 1, len(available_osds))
            replicas = random.sample(available_osds, replica_count)
            
            # Create acting set (primary first)
            acting = [primary_osd] + replicas
            
            # Create PGInfo
            pgs[pgid] = PGInfo(
                pgid=pgid,
                pool_id=pool_id,
                acting=acting
            )
            
            # Update counts
            osds[primary_osd].primary_count += 1
            for osd_id in acting:
                osds[osd_id].total_pg_count += 1

            # Update pool tracking
            pools[pool_id].participating_osds.update(acting)
            if primary_osd not in pools[pool_id].primary_counts:
                pools[pool_id].primary_counts[primary_osd] = 0
            pools[pool_id].primary_counts[primary_osd] += 1

            pg_idx += 1
    
    # Update host counts
    for host_info in hosts.values():
        host_info.primary_count = sum(
            osds[osd_id].primary_count for osd_id in host_info.osd_ids
        )
        host_info.total_pg_count = sum(
            osds[osd_id].total_pg_count for osd_id in host_info.osd_ids
        )
    
    return ClusterState(
        pgs=pgs,
        osds=osds,
        hosts=hosts,
        pools=pools
    )


def generate_ec_pool(
    k: int = 8,
    m: int = 3,
    num_pgs: int = 2048,
    num_osds: int = 100,
    num_hosts: int = 10,
    imbalance_type: str = 'random',
    imbalance_cv: float = 0.30,
    seed: Optional[int] = None
) -> ClusterState:
    """
    Generate erasure-coded pool scenario (k+m configuration).
    
    Args:
        k: Number of data chunks
        m: Number of parity chunks
        num_pgs: Number of PGs in pool
        num_osds: Total OSDs in cluster
        num_hosts: Number of hosts
        imbalance_type: Imbalance pattern type
        imbalance_cv: Target CV for imbalance
        seed: Random seed for reproducibility
        
    Returns:
        ClusterState with EC pool
    """
    if seed is not None:
        random.seed(seed)
    
    chunk_count = k + m
    
    if num_osds < chunk_count:
        raise ValueError(f"num_osds ({num_osds}) must be >= k+m ({chunk_count})")
    
    # Generate using standard function with EC parameters
    return generate_synthetic_cluster(
        num_osds=num_osds,
        num_hosts=num_hosts,
        num_pools=1,
        pgs_per_pool=num_pgs,
        replication_factor=chunk_count,
        imbalance_cv=imbalance_cv,
        imbalance_pattern=imbalance_type,
        seed=seed
    )


def generate_multi_pool_scenario(
    num_pools: int = 5,
    pools_config: Optional[List[Dict]] = None,
    num_osds: int = 100,
    num_hosts: int = 10,
    seed: Optional[int] = None
) -> ClusterState:
    """
    Generate complex multi-pool scenario with varied configurations.
    
    Args:
        num_pools: Number of pools to create
        pools_config: List of pool configurations (None = auto-generate)
        num_osds: Total OSDs in cluster
        num_hosts: Number of hosts
        seed: Random seed for reproducibility
        
    pools_config format:
        [
            {
                'pgs': 512,
                'replication': 3,
                'imbalance_cv': 0.25,
                'pattern': 'random'
            },
            ...
        ]
        
    Returns:
        ClusterState with multiple pools
    """
    if seed is not None:
        random.seed(seed)
    
    # Auto-generate pool configs if not provided
    if pools_config is None:
        patterns = ['random', 'concentrated', 'gradual', 'bimodal']
        pools_config = []
        for i in range(num_pools):
            pools_config.append({
                'pgs': random.choice([256, 512, 1024, 2048]),
                'replication': random.choice([3, 3, 3, 5]),  # 3 is most common
                'imbalance_cv': random.uniform(0.15, 0.40),
                'pattern': patterns[i % len(patterns)]
            })
    
    # Generate base cluster structure (just OSDs and hosts)
    osds_per_host = num_osds // num_hosts
    osds = {}
    for osd_id in range(num_osds):
        host_idx = osd_id // osds_per_host if osds_per_host > 0 else 0
        host_idx = min(host_idx, num_hosts - 1)
        hostname = f"host-{host_idx:02d}"
        osds[osd_id] = OSDInfo(
            osd_id=osd_id,
            host=hostname,
            primary_count=0,
            total_pg_count=0
        )
    
    hosts = {}
    for host_idx in range(num_hosts):
        hostname = f"host-{host_idx:02d}"
        host_osd_ids = [
            osd_id for osd_id, osd_info in osds.items()
            if osd_info.host == hostname
        ]
        hosts[hostname] = HostInfo(
            hostname=hostname,
            osd_ids=host_osd_ids,
            primary_count=0,
            total_pg_count=0
        )
    
    # Generate pools and PGs
    pools = {}
    pgs = {}
    
    for pool_idx, pool_config in enumerate(pools_config[:num_pools]):
        pool_id = pool_idx + 1
        pgs_count = pool_config.get('pgs', 512)
        replication = pool_config.get('replication', 3)
        imbalance_cv = pool_config.get('imbalance_cv', 0.30)
        pattern = pool_config.get('pattern', 'random')
        
        # Create pool
        pools[pool_id] = PoolInfo(
            pool_id=pool_id,
            pool_name=f"pool_{pool_id}",
            pg_count=pgs_count,
            primary_counts={}
        )
        
        # Generate primary distribution for this pool
        primary_distribution = generate_imbalance_pattern(
            num_osds=num_osds,
            total_primaries=pgs_count,
            pattern_type=pattern,
            target_cv=imbalance_cv
        )
        
        # Create primary queue
        osd_primary_queue = []
        for osd_id, count in enumerate(primary_distribution):
            osd_primary_queue.extend([osd_id] * count)
        random.shuffle(osd_primary_queue)
        
        # Generate PGs for this pool
        for pg_num in range(pgs_count):
            pgid = f"{pool_id}.{pg_num:x}"
            
            # Assign primary
            if pg_num < len(osd_primary_queue):
                primary_osd = osd_primary_queue[pg_num]
            else:
                primary_osd = random.randint(0, num_osds - 1)
            
            # Select replicas
            available_osds = [o for o in range(num_osds) if o != primary_osd]
            replica_count = min(replication - 1, len(available_osds))
            replicas = random.sample(available_osds, replica_count)
            
            acting = [primary_osd] + replicas
            
            pgs[pgid] = PGInfo(
                pgid=pgid,
                pool_id=pool_id,
                acting=acting
            )
            
            # Update counts
            osds[primary_osd].primary_count += 1
            for osd_id in acting:
                osds[osd_id].total_pg_count += 1

            # Update pool tracking
            pools[pool_id].participating_osds.update(acting)
            if primary_osd not in pools[pool_id].primary_counts:
                pools[pool_id].primary_counts[primary_osd] = 0
            pools[pool_id].primary_counts[primary_osd] += 1
    
    # Update host counts
    for host_info in hosts.values():
        host_info.primary_count = sum(
            osds[osd_id].primary_count for osd_id in host_info.osd_ids
        )
        host_info.total_pg_count = sum(
            osds[osd_id].total_pg_count for osd_id in host_info.osd_ids
        )
    
    return ClusterState(
        pgs=pgs,
        osds=osds,
        hosts=hosts,
        pools=pools
    )


def save_test_dataset(
    state: ClusterState,
    filepath: str,
    metadata: Optional[Dict] = None
):
    """
    Save generated cluster state as test dataset.
    
    Args:
        state: ClusterState to save
        filepath: Output file path (.json)
        metadata: Optional metadata to include
    """
    # Convert dataclasses to dicts
    pool_dicts = {}
    for pool_id, pool in state.pools.items():
        d = asdict(pool)
        d['participating_osds'] = sorted(d['participating_osds'])  # set -> list for JSON
        pool_dicts[str(pool_id)] = d

    data = {
        'metadata': metadata or {},
        'pgs': {pgid: asdict(pg) for pgid, pg in state.pgs.items()},
        'osds': {str(osd_id): asdict(osd) for osd_id, osd in state.osds.items()},
        'hosts': {hostname: asdict(host) for hostname, host in state.hosts.items()},
        'pools': pool_dicts,
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def load_test_dataset(filepath: str) -> ClusterState:
    """
    Load previously generated test dataset.
    
    Args:
        filepath: Path to dataset file (.json)
        
    Returns:
        ClusterState loaded from file
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Reconstruct dataclasses
    pgs = {
        pgid: PGInfo(**pg_data)
        for pgid, pg_data in data['pgs'].items()
    }
    
    osds = {
        int(osd_id): OSDInfo(**osd_data)
        for osd_id, osd_data in data['osds'].items()
    }
    
    hosts = {
        hostname: HostInfo(**host_data)
        for hostname, host_data in data['hosts'].items()
    }
    
    pools = {}
    for pool_id, pool_data in data['pools'].items():
        # Handle legacy exports that don't have participating_osds
        pool_data.pop('participating_osds', None)
        pools[int(pool_id)] = PoolInfo(**pool_data)

    # Recompute participating_osds from PGs
    for pg in pgs.values():
        if pg.pool_id in pools:
            pools[pg.pool_id].participating_osds.update(
                osd_id for osd_id in pg.acting if osd_id in osds
            )

    return ClusterState(
        pgs=pgs,
        osds=osds,
        hosts=hosts,
        pools=pools
    )
