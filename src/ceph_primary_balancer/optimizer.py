"""
Greedy optimization algorithm for Ceph Primary PG Balancer.

This module implements the core optimization algorithm that iteratively finds
beneficial primary swaps to reduce variance in the primary distribution across OSDs.
The greedy approach finds the single best swap in each iteration and applies it,
continuing until target balance is achieved or no more improvements are possible.
"""

from typing import Dict, List, Optional

from .models import ClusterState, OSDInfo, SwapProposal
from . import analyzer


def calculate_variance(osds: Dict[int, OSDInfo]) -> float:
    """
    Calculate variance of primary distribution across OSDs.
    
    Variance measures how spread out the primary counts are from the mean.
    Formula: Σ(count_i - mean)² / n
    
    Args:
        osds: Dictionary mapping OSD ID to OSDInfo
        
    Returns:
        Variance value (float)
    """
    if not osds:
        return 0.0
    
    # Extract all primary counts
    primary_counts = [osd.primary_count for osd in osds.values()]
    
    # Calculate mean
    mean = sum(primary_counts) / len(primary_counts)
    
    # Calculate variance: Σ(count_i - mean)² / n
    variance = sum((count - mean) ** 2 for count in primary_counts) / len(primary_counts)
    
    return variance


def simulate_swap_variance(state: ClusterState, pgid: str, new_primary: int) -> float:
    """
    Simulate what variance would be AFTER a swap without modifying state.
    
    This function temporarily adjusts the primary counts to calculate what
    the variance would be if the swap were applied, without actually modifying
    the ClusterState object.
    
    Args:
        state: Current ClusterState
        pgid: PG identifier to swap
        new_primary: OSD ID to become the new primary
        
    Returns:
        Simulated variance after the swap
    """
    # Get the PG and current primary
    pg = state.pgs[pgid]
    old_primary = pg.primary
    
    # Create a copy of primary counts for simulation
    simulated_counts = {osd_id: osd.primary_count for osd_id, osd in state.osds.items()}
    
    # Adjust counts: decrement old primary, increment new primary
    simulated_counts[old_primary] -= 1
    simulated_counts[new_primary] += 1
    
    # Calculate variance with simulated counts
    counts = list(simulated_counts.values())
    mean = sum(counts) / len(counts)
    variance = sum((count - mean) ** 2 for count in counts) / len(counts)
    
    return variance


def apply_swap(state: ClusterState, swap: SwapProposal):
    """
    Apply a swap to the ClusterState (modifies state in place).
    
    This function updates the PG's acting list to make the new_primary first
    and updates the primary_count for both the old and new primary OSDs.
    
    Args:
        state: ClusterState to modify
        swap: SwapProposal containing swap details
    """
    # Get the PG
    pg = state.pgs[swap.pgid]
    
    # Update the PG's acting list to make new_primary first
    # Remove new_primary from its current position
    new_acting = [osd for osd in pg.acting if osd != swap.new_primary]
    # Insert new_primary at the beginning
    new_acting.insert(0, swap.new_primary)
    pg.acting = new_acting
    
    # Update OSD primary counts
    state.osds[swap.old_primary].primary_count -= 1
    state.osds[swap.new_primary].primary_count += 1


def find_best_swap(
    state: ClusterState,
    donors: List[int],
    receivers: List[int]
) -> Optional[SwapProposal]:
    """
    Find the single best swap that reduces variance the most.
    
    This function evaluates all possible swaps from donors to receivers
    and returns the one that provides the greatest variance reduction.
    Only OSDs in the PG's acting set are considered as candidates.
    
    Args:
        state: Current ClusterState
        donors: List of OSD IDs with too many primaries
        receivers: List of OSD IDs with too few primaries
        
    Returns:
        SwapProposal with best improvement, or None if no beneficial swaps found
        
    Note:
        Returns None if donors or receivers lists are empty or if no valid swaps exist
    """
    # Handle empty donor or receiver lists
    if not donors or not receivers:
        return None
    
    current_variance = calculate_variance(state.osds)
    best_swap = None
    best_improvement = 0
    
    # For each PG where donor is primary
    for pg in state.pgs.values():
        if pg.primary not in donors:
            continue
        
        # For each candidate OSD in acting set (skip current primary)
        for candidate_osd in pg.acting[1:]:
            if candidate_osd not in receivers:
                continue
            
            # Calculate variance after swap
            new_variance = simulate_swap_variance(state, pg.pgid, candidate_osd)
            improvement = current_variance - new_variance
            
            if improvement > best_improvement:
                best_improvement = improvement
                best_swap = SwapProposal(
                    pgid=pg.pgid,
                    old_primary=pg.primary,
                    new_primary=candidate_osd,
                    variance_improvement=improvement
                )
    
    return best_swap


def optimize_primaries(
    state: ClusterState,
    target_cv: float = 0.10,
    max_iterations: int = 1000
) -> List[SwapProposal]:
    """
    Main greedy algorithm loop to find all beneficial swaps.
    
    This function iteratively finds and applies the best swap until:
    - Target CV (coefficient of variation) is achieved, OR
    - No more donors/receivers exist, OR
    - No beneficial swaps are found, OR
    - Maximum iterations are reached
    
    Args:
        state: ClusterState to optimize (modified in place)
        target_cv: Target coefficient of variation (default: 0.10 = 10%)
        max_iterations: Maximum number of iterations (default: 1000)
        
    Returns:
        List of all SwapProposal objects applied (empty list if no swaps possible)
        
    Note:
        Returns empty list if OSDs dictionary is empty or no optimization is possible
    """
    swaps = []
    
    # Handle edge case: no OSDs to optimize
    if not state.osds:
        print("Warning: No OSDs found, cannot optimize")
        return swaps
    
    for iteration in range(max_iterations):
        # Recalculate statistics based on current state
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = analyzer.calculate_statistics(primary_counts)
        
        if stats.cv <= target_cv:
            print(f"Target CV {target_cv} achieved!")
            break
        
        # Identify donors and receivers
        donors = analyzer.identify_donors(state.osds)
        receivers = analyzer.identify_receivers(state.osds)
        
        if not donors or not receivers:
            print("No more donors or receivers")
            break
        
        # Find best swap
        swap = find_best_swap(state, donors, receivers)
        
        if swap is None:
            print("No beneficial swaps found")
            break
        
        # Apply swap to state
        apply_swap(state, swap)
        swaps.append(swap)
        
        # Print progress every 10 iterations
        if iteration % 10 == 0:
            print(f"Iteration {iteration}: CV = {stats.cv:.2%}, Swaps = {len(swaps)}")
    
    return swaps
