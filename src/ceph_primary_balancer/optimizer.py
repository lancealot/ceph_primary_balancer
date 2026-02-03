"""
Greedy optimization algorithm for Ceph Primary PG Balancer.

This module implements the core optimization algorithm that iteratively finds
beneficial primary swaps to reduce score in the primary distribution across OSDs, hosts, and pools.
The greedy approach finds the single best swap in each iteration and applies it,
continuing until target balance is achieved or no more improvements are possible.

Phase 2 Update: Now supports three-dimensional optimization including pool-level awareness
and optional pool filtering for targeted optimization.
"""

from typing import Dict, List, Optional

from .models import ClusterState, OSDInfo, SwapProposal
from .scorer import Scorer
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


def simulate_swap_score(state: ClusterState, pgid: str, new_primary: int, scorer: Scorer) -> float:
    """
    Simulate what score would be AFTER a swap without modifying state.
    
    This function temporarily adjusts the primary counts at both OSD and host levels
    to calculate what the composite score would be if the swap were applied, without 
    actually modifying the ClusterState object.
    
    Args:
        state: Current ClusterState
        pgid: PG identifier to swap
        new_primary: OSD ID to become the new primary
        scorer: Scorer instance for composite scoring
        
    Returns:
        Simulated composite score after the swap
    """
    # Get the PG and current primary
    pg = state.pgs[pgid]
    old_primary = pg.primary
    
    # Create temporary OSDInfo objects with adjusted counts
    simulated_osds = {}
    for osd_id, osd in state.osds.items():
        simulated_osds[osd_id] = OSDInfo(
            osd_id=osd.osd_id,
            host=osd.host,
            primary_count=osd.primary_count,
            total_pg_count=osd.total_pg_count
        )
    
    # Adjust OSD counts
    simulated_osds[old_primary].primary_count -= 1
    simulated_osds[new_primary].primary_count += 1
    
    # Create temporary HostInfo objects with recalculated counts
    simulated_hosts = {}
    if state.hosts:
        from .models import HostInfo
        for hostname, host in state.hosts.items():
            simulated_hosts[hostname] = HostInfo(
                hostname=host.hostname,
                osd_ids=host.osd_ids[:],  # Copy list
                primary_count=0,
                total_pg_count=0
            )
        
        # Recalculate host-level aggregations
        for osd in simulated_osds.values():
            if osd.host and osd.host in simulated_hosts:
                simulated_hosts[osd.host].primary_count += osd.primary_count
                simulated_hosts[osd.host].total_pg_count += osd.total_pg_count
    
    # Create temporary PoolInfo objects with recalculated counts (Phase 2)
    simulated_pools = {}
    if state.pools:
        from .models import PoolInfo
        for pool_id, pool in state.pools.items():
            simulated_pools[pool_id] = PoolInfo(
                pool_id=pool.pool_id,
                pool_name=pool.pool_name,
                pg_count=pool.pg_count,
                primary_counts=pool.primary_counts.copy()  # Copy dict
            )
        
        # Update the affected pool's primary counts
        pg = state.pgs[pgid]
        pool_id = pg.pool_id
        if pool_id in simulated_pools:
            # Decrement old primary
            if old_primary in simulated_pools[pool_id].primary_counts:
                simulated_pools[pool_id].primary_counts[old_primary] -= 1
                if simulated_pools[pool_id].primary_counts[old_primary] == 0:
                    del simulated_pools[pool_id].primary_counts[old_primary]
            
            # Increment new primary
            if new_primary not in simulated_pools[pool_id].primary_counts:
                simulated_pools[pool_id].primary_counts[new_primary] = 0
            simulated_pools[pool_id].primary_counts[new_primary] += 1
    
    # Create simulated state
    simulated_state = ClusterState(
        pgs=state.pgs,  # PGs don't need to be copied for scoring
        osds=simulated_osds,
        hosts=simulated_hosts,
        pools=simulated_pools
    )
    
    return scorer.calculate_score(simulated_state)


def apply_swap(state: ClusterState, swap: SwapProposal):
    """
    Apply a swap to the ClusterState (modifies state in place).
    
    This function updates:
    1. The PG's acting list to make the new_primary first
    2. The primary_count for both the old and new primary OSDs
    3. The primary_count for the affected hosts (if host tracking is enabled)
    
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
    old_osd = state.osds[swap.old_primary]
    new_osd = state.osds[swap.new_primary]
    
    old_osd.primary_count -= 1
    new_osd.primary_count += 1
    
    # Update host-level counts if host tracking is enabled
    if state.hosts:
        if old_osd.host and old_osd.host in state.hosts:
            state.hosts[old_osd.host].primary_count -= 1
        
        if new_osd.host and new_osd.host in state.hosts:
            state.hosts[new_osd.host].primary_count += 1
    
    # Update pool-level counts (Phase 2)
    if state.pools:
        pool_id = pg.pool_id
        if pool_id in state.pools:
            pool = state.pools[pool_id]
            
            # Decrement old primary
            if swap.old_primary in pool.primary_counts:
                pool.primary_counts[swap.old_primary] -= 1
                if pool.primary_counts[swap.old_primary] == 0:
                    del pool.primary_counts[swap.old_primary]
            
            # Increment new primary
            if swap.new_primary not in pool.primary_counts:
                pool.primary_counts[swap.new_primary] = 0
            pool.primary_counts[swap.new_primary] += 1


def find_best_swap(
    state: ClusterState,
    donors: List[int],
    receivers: List[int],
    scorer: Scorer
) -> Optional[SwapProposal]:
    """
    Find the single best swap that reduces composite score the most.
    
    This function evaluates all possible swaps from donors to receivers
    and returns the one that provides the greatest score improvement.
    Only OSDs in the PG's acting set are considered as candidates.
    
    Phase 2 Enhancement: Now uses three-dimensional scoring including pool-level balance.
    
    Args:
        state: Current ClusterState
        donors: List of OSD IDs with too many primaries
        receivers: List of OSD IDs with too few primaries
        scorer: Scorer instance for composite scoring
        
    Returns:
        SwapProposal with best improvement, or None if no beneficial swaps found
        
    Note:
        Returns None if donors or receivers lists are empty or if no valid swaps exist
    """
    # Handle empty donor or receiver lists
    if not donors or not receivers:
        return None
    
    current_score = scorer.calculate_score(state)
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
            
            # Calculate score after swap
            new_score = simulate_swap_score(state, pg.pgid, candidate_osd, scorer)
            improvement = current_score - new_score
            
            # Prioritize swaps that improve host balance
            # If hosts are being tracked, apply a small bonus for cross-host swaps
            host_bonus = 0.0
            if state.hosts and state.osds[pg.primary].host and state.osds[candidate_osd].host:
                old_host = state.osds[pg.primary].host
                new_host = state.osds[candidate_osd].host
                if old_host != new_host:
                    # Small bonus for cross-host swaps (helps break ties)
                    host_bonus = 0.01
            
            effective_improvement = improvement + host_bonus
            
            if effective_improvement > best_improvement:
                best_improvement = improvement  # Store actual improvement, not bonus
                best_swap = SwapProposal(
                    pgid=pg.pgid,
                    old_primary=pg.primary,
                    new_primary=candidate_osd,
                    score_improvement=improvement
                )
    
    return best_swap


def optimize_primaries(
    state: ClusterState,
    target_cv: float = 0.10,
    max_iterations: int = 1000,
    scorer: Optional[Scorer] = None,
    pool_filter: Optional[int] = None
) -> List[SwapProposal]:
    """
    Main greedy algorithm loop to find all beneficial swaps.
    
    This function iteratively finds and applies the best swap until:
    - Target CV (coefficient of variation) is achieved at OSD level, OR
    - No more donors/receivers exist, OR
    - No beneficial swaps are found, OR
    - Maximum iterations are reached
    
    Phase 2 Update: Now supports three-dimensional optimization with configurable
    scoring weights for OSD, host, and pool-level balance. Also supports pool filtering.
    
    Args:
        state: ClusterState to optimize (modified in place)
        target_cv: Target coefficient of variation for OSD level (default: 0.10 = 10%)
        max_iterations: Maximum number of iterations (default: 1000)
        scorer: Optional Scorer instance. If None, uses Phase 2 defaults (0.5 OSD, 0.3 host, 0.2 pool)
        pool_filter: Optional pool_id to only optimize PGs from that specific pool
        
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
    
    # Use default scorer if none provided (Phase 2 defaults)
    if scorer is None:
        scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
    
    # If pool filtering is enabled, print info
    if pool_filter is not None:
        if pool_filter in state.pools:
            pool_name = state.pools[pool_filter].pool_name
            pool_pg_count = state.pools[pool_filter].pg_count
            print(f"Pool filter enabled: Only optimizing pool {pool_filter} ({pool_name}) with {pool_pg_count} PGs")
        else:
            print(f"Warning: Pool filter {pool_filter} not found in cluster, ignoring filter")
            pool_filter = None
    
    for iteration in range(max_iterations):
        # Recalculate statistics based on current state
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = analyzer.calculate_statistics(primary_counts)
        
        # Check OSD-level CV target
        if stats.cv <= target_cv:
            print(f"Target OSD-level CV {target_cv:.2%} achieved!")
            break
        
        # Identify donors and receivers at OSD level
        donors = analyzer.identify_donors(state.osds)
        receivers = analyzer.identify_receivers(state.osds)
        
        if not donors or not receivers:
            print("No more donors or receivers")
            break
        
        # Find best swap using multi-dimensional scoring
        # If pool filtering is enabled, pass it to find_best_swap
        if pool_filter is not None:
            # Create a filtered state with only PGs from the target pool
            filtered_pgs = {pgid: pg for pgid, pg in state.pgs.items() if pg.pool_id == pool_filter}
            if not filtered_pgs:
                print(f"No PGs found in pool {pool_filter}")
                break
            
            # Create temporary state with filtered PGs for swap finding
            from .models import ClusterState as CS
            filtered_state = CS(pgs=filtered_pgs, osds=state.osds, hosts=state.hosts, pools=state.pools)
            swap = find_best_swap(filtered_state, donors, receivers, scorer)
        else:
            swap = find_best_swap(state, donors, receivers, scorer)
        
        if swap is None:
            print("No beneficial swaps found")
            break
        
        # Apply swap to state
        apply_swap(state, swap)
        swaps.append(swap)
        
        # Print progress every 10 iterations
        if iteration % 10 == 0:
            # Calculate host-level and pool-level CV if available
            host_cv_str = ""
            pool_cv_str = ""
            
            if state.hosts:
                host_counts = [host.primary_count for host in state.hosts.values()]
                host_stats = analyzer.calculate_statistics(host_counts)
                host_cv_str = f", Host CV = {host_stats.cv:.2%}"
            
            if state.pools:
                from .analyzer import get_pool_statistics_summary
                pool_stats = get_pool_statistics_summary(state)
                if pool_stats:
                    avg_pool_cv = sum(ps.cv for ps in pool_stats.values()) / len(pool_stats)
                    pool_cv_str = f", Avg Pool CV = {avg_pool_cv:.2%}"
            
            print(f"Iteration {iteration}: OSD CV = {stats.cv:.2%}{host_cv_str}{pool_cv_str}, Swaps = {len(swaps)}")
    
    return swaps
