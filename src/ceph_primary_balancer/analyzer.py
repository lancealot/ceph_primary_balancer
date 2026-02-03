"""
Statistical analysis module for Ceph Primary PG Balancer.

This module provides functions to analyze primary PG distribution across OSDs,
calculate distribution statistics, identify imbalanced OSDs (donors and receivers),
and generate human-readable summary reports.
"""

import statistics
from typing import List, Dict

from .models import OSDInfo, ClusterState, Statistics


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
