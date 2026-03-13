"""
Statistical analysis module for Ceph Primary PG Balancer.

This module provides functions to analyze primary PG distribution across OSDs,
calculate distribution statistics, identify imbalanced OSDs (donors and receivers),
and generate human-readable summary reports.
"""

import statistics
from typing import Dict, List, Set, Tuple

from .models import OSDInfo, PoolInfo, ClusterState, Statistics


def calculate_statistics(counts: List[int]) -> Statistics:
    """
    Calculate statistical metrics for a distribution of primary counts.
    
    Args:
        counts: List of primary counts (one per OSD)
        
    Returns:
        Statistics object containing mean, std_dev, cv, min_val, max_val, and p50
        
    Raises:
        ValueError: If counts list is empty
        
    Note:
        - Uses Python's statistics module for calculations
        - Handles edge case where only 1 value exists (std_dev = 0.0)
        - CV (coefficient of variation) = std_dev / mean
        - Division by zero in CV calculation handled (returns 0.0)
    """
    # Validate input
    if not counts:
        raise ValueError("Cannot calculate statistics on empty counts list")
    
    mean = statistics.mean(counts)
    
    # Handle edge case: single value has no standard deviation
    if len(counts) == 1:
        std_dev = 0.0
    else:
        std_dev = statistics.stdev(counts)
    
    # Coefficient of variation (std_dev / mean)
    # Handle division by zero if all counts are 0
    cv = std_dev / mean if mean > 0 else 0.0
    
    min_val = min(counts)
    max_val = max(counts)
    p50 = statistics.median(counts)
    
    return Statistics(
        mean=mean,
        std_dev=std_dev,
        cv=cv,
        min_val=min_val,
        max_val=max_val,
        p50=p50
    )


def identify_donors(osds: Dict[int, OSDInfo], threshold_pct: float = 0.1) -> List[int]:
    """
    Identify OSDs with too many primaries (above threshold).
    
    Donors are OSDs that have significantly more primaries than average and
    should give up some primaries to achieve better balance.
    
    Args:
        osds: Dictionary mapping OSD ID to OSDInfo
        threshold_pct: Percentage threshold above mean (default: 0.1 = 10%)
        
    Returns:
        Sorted list of OSD IDs that are donors (primary_count > mean * (1 + threshold_pct))
    """
    if not osds:
        return []
    
    # Calculate mean primary count
    primary_counts = [osd.primary_count for osd in osds.values()]
    mean = statistics.mean(primary_counts)
    
    # Find OSDs above threshold
    threshold = mean * (1 + threshold_pct)
    donors = [osd_id for osd_id, osd in osds.items() if osd.primary_count > threshold]
    
    return sorted(donors)


def identify_receivers(osds: Dict[int, OSDInfo], threshold_pct: float = 0.1) -> List[int]:
    """
    Identify OSDs with too few primaries (below threshold).
    
    Receivers are OSDs that have significantly fewer primaries than average and
    can accept additional primaries to achieve better balance.
    
    Args:
        osds: Dictionary mapping OSD ID to OSDInfo
        threshold_pct: Percentage threshold below mean (default: 0.1 = 10%)
        
    Returns:
        Sorted list of OSD IDs that are receivers (primary_count < mean * (1 - threshold_pct))
    """
    if not osds:
        return []
    
    # Calculate mean primary count
    primary_counts = [osd.primary_count for osd in osds.values()]
    mean = statistics.mean(primary_counts)
    
    # Find OSDs below threshold
    threshold = mean * (1 - threshold_pct)
    receivers = [osd_id for osd_id, osd in osds.items() if osd.primary_count < threshold]
    
    return sorted(receivers)


def identify_pool_donors_receivers(
    state: ClusterState,
    threshold_pct: float = 0.1,
) -> Tuple[Dict[int, Set[int]], Dict[int, Set[int]]]:
    """
    Identify per-pool donors and receivers.

    For each pool, computes the mean primary count across participating OSDs
    (any OSD that appears in an acting set for that pool). OSDs above/below
    the threshold are donors/receivers for that pool.

    Returns:
        (pool_donors, pool_receivers) where each is a dict mapping
        pool_id -> set of OSD IDs.
    """
    if not state.pools:
        return {}, {}

    # Precompute participating OSDs per pool in a single pass over PGs
    pool_osds: Dict[int, Set[int]] = {}
    for pg in state.pgs.values():
        if pg.pool_id not in pool_osds:
            pool_osds[pg.pool_id] = set()
        pool_osds[pg.pool_id].update(pg.acting)

    pool_donors: Dict[int, Set[int]] = {}
    pool_receivers: Dict[int, Set[int]] = {}

    for pool_id, pool in state.pools.items():
        participating = pool_osds.get(pool_id, set())
        if len(participating) < 2:
            continue

        total_primaries = sum(pool.primary_counts.values())
        mean = total_primaries / len(participating)
        if mean == 0:
            continue

        hi = mean * (1 + threshold_pct)
        lo = mean * (1 - threshold_pct)

        donors = set()
        receivers = set()
        for osd_id in participating:
            count = pool.primary_counts.get(osd_id, 0)
            if count > hi:
                donors.add(osd_id)
            elif count < lo:
                receivers.add(osd_id)

        if donors and receivers:
            pool_donors[pool_id] = donors
            pool_receivers[pool_id] = receivers

    return pool_donors, pool_receivers


def calculate_pool_statistics(pool: PoolInfo, osds: Dict[int, OSDInfo]) -> Statistics:
    """
    Calculate statistical metrics for a single pool's primary distribution.
    
    Only includes OSDs that have at least one PG from this pool.
    
    Args:
        pool: PoolInfo object containing per-OSD primary counts
        osds: Dictionary of all OSDs in the cluster (for validation)
        
    Returns:
        Statistics object with pool-level metrics
        
    Raises:
        ValueError: If no OSDs have primaries for this pool
    """
    # Get primary counts only for OSDs that have PGs in this pool
    counts = [count for osd_id, count in pool.primary_counts.items() if osd_id in osds]
    
    if not counts:
        raise ValueError(f"Pool {pool.pool_name} has no primary assignments")
    
    return calculate_statistics(counts)


def get_pool_statistics_summary(state: ClusterState) -> Dict[int, Statistics]:
    """
    Calculate statistics for all pools in the cluster.
    
    Args:
        state: ClusterState containing pools and OSDs
        
    Returns:
        Dictionary mapping pool_id to Statistics object
    """
    pool_stats = {}
    
    for pool_id, pool in state.pools.items():
        if pool.primary_counts:  # Only calculate if pool has primaries
            try:
                pool_stats[pool_id] = calculate_pool_statistics(pool, state.osds)
            except ValueError:
                # Skip pools with no valid primary assignments
                continue
    
    return pool_stats


def calculate_average_pool_variance(state: ClusterState) -> float:
    """
    Calculate the average variance across all pools.
    
    This is used in three-dimensional scoring to measure pool-level balance.
    
    Args:
        state: ClusterState containing pools and OSDs
        
    Returns:
        float: Average variance across all pools (0.0 if no pools)
    """
    if not state.pools:
        return 0.0
    
    variances = []
    for pool in state.pools.values():
        if pool.primary_counts:
            try:
                stats = calculate_pool_statistics(pool, state.osds)
                variances.append(stats.std_dev ** 2)
            except ValueError:
                # Skip pools with no valid assignments
                continue
    
    if not variances:
        return 0.0
    
    return sum(variances) / len(variances)


def print_summary(state: ClusterState, stats: Statistics):
    """
    Print human-readable summary of cluster primary distribution to terminal.
    
    Displays comprehensive analysis including:
    - Total PG and OSD counts
    - Current statistical metrics (mean, std dev, CV, range, median)
    - Top 5 donors (OSDs with most primaries)
    - Top 5 receivers (OSDs with fewest primaries)
    
    Args:
        state: ClusterState containing all PGs and OSDs
        stats: Statistics object with calculated metrics
    """
    print("\nCluster Primary Distribution Analysis")
    print("=" * 50)
    print(f"Total PGs:  {len(state.pgs)}")
    print(f"Total OSDs: {len(state.osds)}")
    
    print("\nCurrent Statistics:")
    print(f"  Mean:        {stats.mean:.1f} primaries/OSD")
    print(f"  Std Dev:     {stats.std_dev:.1f}")
    print(f"  CV:          {stats.cv * 100:.1f}%")
    print(f"  Range:       {stats.min_val} - {stats.max_val}")
    print(f"  Median:      {stats.p50:.1f}")
    
    # Identify donors and receivers with 10% threshold
    donors = identify_donors(state.osds, threshold_pct=0.1)
    receivers = identify_receivers(state.osds, threshold_pct=0.1)
    
    # Sort OSDs by primary count for top N display
    osds_by_primaries = sorted(
        state.osds.items(),
        key=lambda x: x[1].primary_count,
        reverse=True
    )
    
    # Display top 5 donors (most primaries)
    print("\nTop 5 Donors (most primaries):")
    for i, (osd_id, osd_info) in enumerate(osds_by_primaries[:5]):
        print(f"  OSD.{osd_id}: {osd_info.primary_count} primaries")
    
    # Display top 5 receivers (fewest primaries)
    print("\nTop 5 Receivers (fewest primaries):")
    reversed_osds = list(reversed(osds_by_primaries))
    for i, (osd_id, osd_info) in enumerate(reversed_osds[:5]):
        print(f"  OSD.{osd_id}: {osd_info.primary_count} primaries")
