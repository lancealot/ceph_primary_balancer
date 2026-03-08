"""
Greedy optimization algorithm for Ceph Primary PG Balancer.

This module implements the original greedy optimization algorithm that iteratively
finds the single best swap in each iteration and applies it, continuing until
target balance is achieved or no more improvements are possible.

The greedy approach is:
- Fast: O(n²) per iteration where n is number of PGs
- Deterministic: Always produces the same result for the same input
- Proven: Battle-tested in production environments
- Simple: Easy to understand and debug

Phase 7 Update: Refactored into OptimizerBase architecture while maintaining
100% backward compatibility with existing behavior.
"""

from typing import Dict, List, Optional

from .base import OptimizerBase
from ..models import ClusterState, OSDInfo, SwapProposal, HostInfo, PoolInfo
from ..scorer import Scorer
from .. import analyzer


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
    4. The primary_counts for the affected pool (if pool tracking is enabled)
    
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

    Uses O(1) delta scoring for OSD/host dimensions and O(p) for pool
    dimension (where p = OSDs in affected pool), avoiding full state copies.

    Args:
        state: Current ClusterState
        donors: List of OSD IDs with too many primaries
        receivers: List of OSD IDs with too few primaries
        scorer: Scorer instance for composite scoring

    Returns:
        SwapProposal with best improvement, or None if no beneficial swaps found
    """
    if not donors or not receivers:
        return None

    # Compute score components once — all candidate evaluations use deltas from this
    components = scorer.calculate_score_with_components(state)
    current_score = components.total

    # Convert to sets for O(1) lookup
    donor_set = set(donors)
    receiver_set = set(receivers)

    best_swap = None
    best_improvement = 0

    for pg in state.pgs.values():
        if pg.primary not in donor_set:
            continue

        for candidate_osd in pg.acting[1:]:
            if candidate_osd not in receiver_set:
                continue

            # O(1) delta scoring (O(p) for pool dimension)
            new_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate_osd, pg.pool_id
            )
            improvement = current_score - new_score

            # Small bonus for cross-host swaps (helps break ties)
            host_bonus = 0.0
            if state.hosts and state.osds[pg.primary].host and state.osds[candidate_osd].host:
                if state.osds[pg.primary].host != state.osds[candidate_osd].host:
                    host_bonus = 0.01

            effective_improvement = improvement + host_bonus

            if effective_improvement > best_improvement:
                best_improvement = improvement
                best_swap = SwapProposal(
                    pgid=pg.pgid,
                    old_primary=pg.primary,
                    new_primary=candidate_osd,
                    score_improvement=improvement
                )

    return best_swap


class GreedyOptimizer(OptimizerBase):
    """
    Greedy optimization algorithm for primary PG balancing.
    
    This is the original algorithm that has been used in production. It finds
    the single best swap in each iteration and applies it, continuing until
    the target balance is achieved or no more improvements are possible.
    
    Characteristics:
    - Deterministic: Always produces the same result for the same input
    - Fast: Typically converges in 500-1000 iterations
    - Simple: Easy to understand and debug
    - Proven: Battle-tested in production
    
    Phase 7 Update: Refactored to use OptimizerBase architecture while
    maintaining 100% backward compatibility.
    
    Phase 7.1 Integration: Automatically works with DynamicScorer for
    adaptive weight optimization with no additional code.
    """
    
    @property
    def algorithm_name(self) -> str:
        """Return human-readable algorithm name."""
        return "Greedy"
    
    @property
    def is_deterministic(self) -> bool:
        """Return True - greedy algorithm is deterministic."""
        return True
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """
        Run greedy optimization algorithm.
        
        Iteratively finds and applies the best swap until:
        - Target CV is achieved at OSD level, OR
        - No more donors/receivers exist, OR
        - No beneficial swaps are found, OR
        - Maximum iterations are reached
        
        Args:
            state: ClusterState to optimize (modified in place)
            
        Returns:
            List of all SwapProposal objects applied
        """
        swaps = []
        
        # Handle edge case: no OSDs to optimize
        if not state.osds:
            if self.verbose:
                print("Warning: No OSDs found, cannot optimize")
            return swaps
        
        # Start timer
        self._start_timer()
        
        # Print optimization strategy
        if self.verbose:
            levels_str = ', '.join(self.scorer.get_enabled_levels()).upper()
            print(f"Optimization strategy: {levels_str}")
            
            if not self.dynamic_weights:
                print(f"Weights: OSD={self.scorer.w_osd:.2f}, HOST={self.scorer.w_host:.2f}, POOL={self.scorer.w_pool:.2f}")
            else:
                print(f"Dynamic weights enabled: {self.dynamic_strategy} strategy")
                print(f"Weight updates every {self.weight_update_interval} iterations")
                print(f"Initial weights: OSD={self.scorer.w_osd:.2f}, HOST={self.scorer.w_host:.2f}, POOL={self.scorer.w_pool:.2f}")
        
        # Print pool filter info if enabled
        if self.pool_filter is not None and self.verbose:
            if self.pool_filter in state.pools:
                pool_name = state.pools[self.pool_filter].pool_name
                pool_pg_count = state.pools[self.pool_filter].pg_count
                print(f"Pool filter enabled: Only optimizing pool {self.pool_filter} ({pool_name}) with {pool_pg_count} PGs")
            else:
                print(f"Warning: Pool filter {self.pool_filter} not found in cluster, ignoring filter")
                self.pool_filter = None
        
        # Main optimization loop
        for iteration in range(self.max_iterations):
            # Check termination conditions
            if self._check_termination(state, iteration):
                if self.verbose:
                    primary_counts = [osd.primary_count for osd in state.osds.values()]
                    stats = analyzer.calculate_statistics(primary_counts)
                    print(f"Target OSD-level CV {self.target_cv:.2%} achieved!")
                break
            
            # Identify donors and receivers at OSD level
            donors = analyzer.identify_donors(state.osds)
            receivers = analyzer.identify_receivers(state.osds)
            
            if not donors or not receivers:
                if self.verbose:
                    print("No more donors or receivers")
                break
            
            # Find best swap
            # If pool filtering is enabled, create filtered state
            if self.pool_filter is not None:
                filtered_pgs = {pgid: pg for pgid, pg in state.pgs.items() if pg.pool_id == self.pool_filter}
                if not filtered_pgs:
                    if self.verbose:
                        print(f"No PGs found in pool {self.pool_filter}")
                    break
                
                # Create temporary state with filtered PGs for swap finding
                filtered_state = ClusterState(
                    pgs=filtered_pgs,
                    osds=state.osds,
                    hosts=state.hosts,
                    pools=state.pools
                )
                swap = find_best_swap(filtered_state, donors, receivers, self.scorer)
            else:
                swap = find_best_swap(state, donors, receivers, self.scorer)
            
            if swap is None:
                if self.verbose:
                    print("No beneficial swaps found")
                break
            
            # Apply swap to state
            apply_swap(state, swap)
            swaps.append(swap)
            
            # Update statistics
            self.stats.swaps_evaluated += 1  # In greedy, evaluated = applied
            self.stats.swaps_applied += 1
            self._record_iteration(state)
            
            # Print progress every 10 iterations
            if self.verbose and iteration % 10 == 0:
                self._print_progress(state, iteration, len(swaps))
        
        # Stop timer
        self._stop_timer()
        
        # Print summary
        if self.verbose:
            self._print_summary()
        
        return swaps
