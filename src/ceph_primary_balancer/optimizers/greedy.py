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

from typing import Dict, List, Optional, Set

from .base import OptimizerBase
from ..models import ClusterState, OSDInfo, SwapProposal, HostInfo, PoolInfo
from ..scorer import Scorer, _pool_cv_floor, UNBALANCEABLE_CV_FLOOR
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
                primary_counts=pool.primary_counts.copy(),  # Copy dict
                participating_osds=pool.participating_osds,  # Immutable during scoring
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
    scorer: Scorer,
    pool_donors: Optional[Dict[int, Set[int]]] = None,
    pool_receivers: Optional[Dict[int, Set[int]]] = None,
) -> Optional[SwapProposal]:
    """
    Find the single best swap that reduces composite score the most.

    A PG is a candidate if its primary is a donor at the OSD level OR at
    the pool level for that PG's pool. Similarly, a candidate OSD in the
    acting set qualifies if it's a receiver at OSD level OR pool level.
    This allows pool-imbalanced swaps to be proposed even when the involved
    OSDs are near the global mean.

    Args:
        state: Current ClusterState
        donors: OSD-level donor OSD IDs
        receivers: OSD-level receiver OSD IDs
        scorer: Scorer instance for composite scoring
        pool_donors: Per-pool donor sets (pool_id -> set of OSD IDs)
        pool_receivers: Per-pool receiver sets (pool_id -> set of OSD IDs)

    Returns:
        SwapProposal with best improvement, or None if no beneficial swaps found
    """
    if not donors and not pool_donors:
        return None
    if not receivers and not pool_receivers:
        return None

    pool_donors = pool_donors or {}
    pool_receivers = pool_receivers or {}

    # Compute score components once — all candidate evaluations use deltas from this
    components = scorer.calculate_score_with_components(state)
    current_score = components.total

    # Convert to sets for O(1) lookup
    donor_set = set(donors) if donors else set()
    receiver_set = set(receivers) if receivers else set()

    best_swap = None
    best_improvement = 0

    for pg in state.pgs.values():
        pool_id = pg.pool_id
        # Primary is a candidate donor if it's an OSD-level donor OR a
        # pool-level donor for this PG's pool
        is_donor = (pg.primary in donor_set or
                    pg.primary in pool_donors.get(pool_id, set()))
        if not is_donor:
            continue

        for candidate_osd in pg.acting[1:]:
            # Candidate is a receiver at OSD level or pool level
            is_receiver = (candidate_osd in receiver_set or
                           candidate_osd in pool_receivers.get(pool_id, set()))
            if not is_receiver:
                continue

            # O(1) delta scoring (O(p) for pool dimension)
            new_score = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate_osd, pool_id
            )
            improvement = current_score - new_score

            # Small relative bonus for cross-host swaps (tie-breaker only).
            # Only applied when improvement is positive — never select a
            # score-worsening swap just because it's cross-host.
            host_bonus = 0.0
            if improvement > 0 and state.hosts:
                if state.osds[pg.primary].host and state.osds[candidate_osd].host:
                    if state.osds[pg.primary].host != state.osds[candidate_osd].host:
                        host_bonus = improvement * 0.01

            effective_improvement = improvement + host_bonus

            if effective_improvement > best_improvement:
                best_improvement = effective_improvement
                best_swap = SwapProposal(
                    pgid=pg.pgid,
                    old_primary=pg.primary,
                    new_primary=candidate_osd,
                    score_improvement=improvement
                )

    return best_swap


def find_best_pool_swap(
    state: ClusterState,
    scorer: Scorer,
    target_cv: float,
    pool_pgs: Optional[Dict[int, list]] = None,
) -> Optional[SwapProposal]:
    """Find the best swap targeting pools with CV above target.

    Unlike find_best_swap, this does NOT require the primary to be an
    OSD-level or pool-level donor. It considers ALL PGs in high-CV pools,
    catching swaps that donor/receiver filtering would miss — especially
    for small pools where no single OSD crosses the donor threshold.

    Args:
        state: Current ClusterState
        scorer: Scorer instance for composite scoring
        target_cv: Target CV — only pools above this are searched
        pool_pgs: Pre-built index of pool_id -> list of PGs. If None, built
                  on the fly. Callers in tight loops should pass a cached index
                  since pool membership doesn't change across swaps.

    Returns:
        SwapProposal with best improvement, or None if no beneficial swaps found
    """
    if 'pool' not in scorer.enabled_levels or not state.pools:
        return None

    components = scorer.calculate_score_with_components(state)
    current_score = components.total

    # Use pre-built index if provided, otherwise build on the fly
    if pool_pgs is None:
        pool_pgs_idx: Dict[int, list] = {}
        for pg in state.pgs.values():
            pool_pgs_idx.setdefault(pg.pool_id, []).append(pg)
    else:
        pool_pgs_idx = pool_pgs

    best_swap = None
    best_improvement = 0.0

    for pool_id, pool_cv in components.pool_cvs.items():
        if pool_cv <= target_cv:
            continue

        # Skip pools already near their theoretical minimum CV —
        # no swap can meaningfully improve them further.
        # Use a tight 2% margin so pools close to (but not at) floor
        # are still searched for viable swaps.
        pool = state.pools.get(pool_id)
        if pool is not None:
            n_part = len(pool.participating_osds) if pool.participating_osds else components.pool_n.get(pool_id, 0)
            floor_cv = _pool_cv_floor(pool.pg_count, n_part)
            if floor_cv > 0 and pool_cv <= floor_cv * 1.02:
                continue

        for pg in pool_pgs_idx.get(pool_id, []):
            for candidate_osd in pg.acting[1:]:
                new_score = scorer.calculate_swap_delta(
                    state, components, pg.primary, candidate_osd, pool_id
                )
                improvement = current_score - new_score

                if improvement > best_improvement:
                    best_improvement = improvement
                    best_swap = SwapProposal(
                        pgid=pg.pgid,
                        old_primary=pg.primary,
                        new_primary=candidate_osd,
                        score_improvement=improvement,
                    )

    return best_swap


def find_best_focused_swap(
    state: ClusterState,
    scorer: Scorer,
    target_cv: float,
    max_regression: float = 0.001,
) -> Optional[SwapProposal]:
    """Find the best swap targeting the dimension furthest from target.

    When composite scoring hits a local minimum, this function breaks the
    deadlock by searching for swaps that improve the worst dimension while
    accepting bounded regression in the composite score. It creates a
    temporary single-dimension scorer for candidate evaluation, then filters
    results by the composite regression limit.

    Args:
        state: Current ClusterState
        scorer: Main scorer (for composite score and enabled_levels)
        target_cv: Target CV threshold
        max_regression: Maximum allowed composite score worsening (absolute)

    Returns:
        SwapProposal or None if no acceptable swap found
    """
    import math

    components = scorer.calculate_score_with_components(state)
    current_score = components.total

    # Determine which dimension is furthest from target
    dim_gaps = []
    if 'osd' in scorer.enabled_levels and components.osd_cv > target_cv:
        dim_gaps.append(('osd', components.osd_cv - target_cv))
    if 'host' in scorer.enabled_levels and components.host_cv > target_cv:
        dim_gaps.append(('host', components.host_cv - target_cv))
    if 'pool' in scorer.enabled_levels:
        for pool_id, pool_cv in components.pool_cvs.items():
            if pool_cv > target_cv:
                dim_gaps.append(('pool', pool_cv - target_cv))
                break  # Just need to know pool dimension is above target

    if not dim_gaps:
        return None

    # Sort by gap descending, focus on the worst dimension
    dim_gaps.sort(key=lambda x: x[1], reverse=True)
    focus_dim = dim_gaps[0][0]

    # Create a single-dimension scorer to find dimension-improving swaps
    focused_scorer = Scorer(
        w_osd=1.0 if focus_dim == 'osd' else 0.0,
        w_host=1.0 if focus_dim == 'host' else 0.0,
        w_pool=1.0 if focus_dim == 'pool' else 0.0,
        enabled_levels=[focus_dim],
    )

    focused_components = focused_scorer.calculate_score_with_components(state)
    focused_score = focused_components.total

    best_swap = None
    best_composite_delta = max_regression  # worst allowed regression
    best_focused_improvement = 0.0

    for pg in state.pgs.values():
        for candidate_osd in pg.acting[1:]:
            # Check focused dimension improvement
            new_focused = focused_scorer.calculate_swap_delta(
                state, focused_components, pg.primary, candidate_osd, pg.pool_id
            )
            focused_improvement = focused_score - new_focused
            if focused_improvement <= 0:
                continue

            # Check composite regression is bounded
            new_composite = scorer.calculate_swap_delta(
                state, components, pg.primary, candidate_osd, pg.pool_id
            )
            composite_delta = new_composite - current_score  # positive = regression

            if composite_delta > max_regression:
                continue

            # Pick the swap with best focused improvement among acceptable ones
            if (focused_improvement > best_focused_improvement or
                    (focused_improvement == best_focused_improvement and
                     composite_delta < best_composite_delta)):
                best_focused_improvement = focused_improvement
                best_composite_delta = composite_delta
                best_swap = SwapProposal(
                    pgid=pg.pgid,
                    old_primary=pg.primary,
                    new_primary=candidate_osd,
                    score_improvement=-composite_delta,
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

        Each iteration runs two candidate searches:
        1. Global search using OSD-level and pool-level donors/receivers
        2. Per-pool search targeting pools with CV above target

        The better swap wins. Continues until all enabled dimensions
        reach target CV, no beneficial swaps remain, or max iterations.

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
        
        # Stall detection: stop when focused fallback churns without progress.
        # Uses a rolling window instead of strict consecutive count, because
        # normal search paths may occasionally find swaps (also useless),
        # resetting a consecutive counter and letting the loop continue.
        stall_limit = 10
        fallback_window_size = 20   # track fallback usage over this many iterations
        fallback_window: List[bool] = []  # rolling window of was-fallback flags
        worst_cv_at_fallback_window_start: Optional[float] = None

        # Global stagnation detection: stop when worst aggregate dimension
        # plateaus across ALL search paths (not just focused fallback)
        stagnation_window = 50       # check progress over this many iterations
        stagnation_cv_at_window_start: Optional[float] = None
        stagnation_window_iter = 0

        # Pre-build pool_pgs index once — pool membership never changes
        # across swaps (swaps only change which OSD is primary, not which
        # pool a PG belongs to), so this is safe to cache for the entire run.
        pool_pgs_cache: Dict[int, list] = {}
        for pg in state.pgs.values():
            pool_pgs_cache.setdefault(pg.pool_id, []).append(pg)

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

            # Identify per-pool donors and receivers
            pool_donors, pool_receivers = analyzer.identify_pool_donors_receivers(state)

            # Compute search state once (handles pool_filter)
            if self.pool_filter is not None:
                filtered_pgs = {pgid: pg for pgid, pg in state.pgs.items() if pg.pool_id == self.pool_filter}
                if not filtered_pgs:
                    if self.verbose:
                        print(f"No PGs found in pool {self.pool_filter}")
                    break
                search_state = ClusterState(
                    pgs=filtered_pgs,
                    osds=state.osds,
                    hosts=state.hosts,
                    pools=state.pools
                )
            else:
                search_state = state

            # Find best swap using donor/receiver filtering
            swap = find_best_swap(search_state, donors, receivers, self.scorer,
                                  pool_donors, pool_receivers)

            # If normal threshold found nothing, retry with relaxed threshold
            # (0%) so any OSD above mean is a donor and any below mean is a
            # receiver. This prevents stalling on sparse clusters where the
            # 10% threshold creates a dead zone (e.g., mean=6.2, all OSDs
            # at 5-8).
            if swap is None:
                relaxed_donors = analyzer.identify_donors(state.osds, threshold_pct=0.0)
                relaxed_receivers = analyzer.identify_receivers(state.osds, threshold_pct=0.0)
                relaxed_pool_d, relaxed_pool_r = analyzer.identify_pool_donors_receivers(
                    state, threshold_pct=0.0
                )
                swap = find_best_swap(search_state, relaxed_donors, relaxed_receivers,
                                      self.scorer, relaxed_pool_d, relaxed_pool_r)

            # Also search for pool-targeted swaps (catches candidates that
            # donor/receiver filtering misses for small/imbalanced pools).
            # Compare with whatever the global search found and pick the best.
            pool_swap = find_best_pool_swap(state, self.scorer, self.target_cv, pool_pgs=pool_pgs_cache)
            if pool_swap is not None:
                if swap is None or pool_swap.score_improvement > swap.score_improvement:
                    swap = pool_swap

            # Last resort: dimension-focused search to escape local minimum.
            # Accepts bounded composite regression to improve the worst dimension.
            used_focused_fallback = False
            if swap is None:
                swap = find_best_focused_swap(
                    state, self.scorer, self.target_cv,
                    max_regression=0.001,
                )
                if swap is not None:
                    used_focused_fallback = True
                    if self.verbose:
                        print(f"  [focused fallback] found swap with improvement={swap.score_improvement:.6f}")

            if swap is None:
                if self.verbose:
                    print("No beneficial swaps found")
                break

            # Stall detection: track focused fallback usage in a rolling
            # window.  If fallback fires >= stall_limit times within the
            # last fallback_window_size iterations AND no aggregate
            # dimension improved, we're stuck.  We check aggregate CVs
            # (OSD, Host, weighted-average Pool) rather than individual
            # pool CVs or composite score, because focused fallback
            # deliberately accepts composite regression and may improve
            # some pools while others stay stuck.
            fallback_window.append(used_focused_fallback)
            if len(fallback_window) > fallback_window_size:
                fallback_window.pop(0)
            fallback_count = sum(fallback_window)
            if fallback_count >= stall_limit:
                components = self.scorer.calculate_score_with_components(state)
                dim_cvs = []
                if 'osd' in self.scorer.enabled_levels:
                    dim_cvs.append(components.osd_cv)
                if 'host' in self.scorer.enabled_levels:
                    dim_cvs.append(components.host_cv)
                if 'pool' in self.scorer.enabled_levels:
                    dim_cvs.append(components.avg_pool_cv)
                worst_cv = max(dim_cvs) if dim_cvs else 0.0

                if worst_cv_at_fallback_window_start is None:
                    worst_cv_at_fallback_window_start = worst_cv
                if worst_cv >= worst_cv_at_fallback_window_start * 0.99:
                    # Worst aggregate dimension hasn't improved by 1% — truly stalled
                    if self.verbose:
                        print(f"Stalled: {fallback_count} focused-fallback iterations "
                              f"in last {len(fallback_window)}, worst CV {worst_cv:.2%} "
                              f"not improving (was {worst_cv_at_fallback_window_start:.2%})")
                    break
                # Some dimension is improving — continue
                fallback_window.clear()
                worst_cv_at_fallback_window_start = worst_cv
            
            # Apply swap to state
            apply_swap(state, swap)
            swaps.append(swap)

            # Update statistics
            self.stats.swaps_evaluated += 1  # In greedy, evaluated = applied
            self.stats.swaps_applied += 1
            self._record_iteration(state)

            # Global stagnation detection: if the worst aggregate dimension
            # hasn't improved over a window of iterations, stop.
            stag_components = self.scorer.calculate_score_with_components(state)
            stag_cvs = []
            if 'osd' in self.scorer.enabled_levels:
                stag_cvs.append(stag_components.osd_cv)
            if 'host' in self.scorer.enabled_levels:
                stag_cvs.append(stag_components.host_cv)
            if 'pool' in self.scorer.enabled_levels:
                stag_cvs.append(stag_components.avg_pool_cv)
            stag_worst_cv = max(stag_cvs) if stag_cvs else 0.0

            if stagnation_cv_at_window_start is None:
                stagnation_cv_at_window_start = stag_worst_cv
                stagnation_window_iter = iteration
            elif iteration - stagnation_window_iter >= stagnation_window:
                if stag_worst_cv >= stagnation_cv_at_window_start * 0.99:
                    if self.verbose:
                        print(f"  [stagnation] worst CV {stag_worst_cv:.2%} not improving "
                              f"(was {stagnation_cv_at_window_start:.2%}) "
                              f"over last {stagnation_window} iterations, stopping")
                    break
                # Reset window
                stagnation_cv_at_window_start = stag_worst_cv
                stagnation_window_iter = iteration

            # Print progress every 10 iterations
            if self.verbose and iteration % 10 == 0:
                self._print_progress(state, iteration, len(swaps))
        
        # Stop timer
        self._stop_timer()
        
        # Print summary
        if self.verbose:
            self._print_summary()
        
        return swaps
