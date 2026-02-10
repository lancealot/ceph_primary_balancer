"""
DEPRECATED: Backward compatibility wrapper for optimizer module.

This module is maintained for backward compatibility with existing code.
New code should use the optimizers package directly:

    from ceph_primary_balancer.optimizers import GreedyOptimizer, OptimizerRegistry
    
    # Create optimizer instance
    optimizer = GreedyOptimizer(target_cv=0.10)
    swaps = optimizer.optimize(state)
    
    # Or use registry
    optimizer = OptimizerRegistry.get_optimizer('greedy', target_cv=0.10)
    swaps = optimizer.optimize(state)

This wrapper will be removed in v2.0.0.

Phase 7 Refactoring: The greedy algorithm has been moved to optimizers.greedy
to support the new multi-algorithm architecture. All functionality remains
identical - this wrapper ensures zero breaking changes.
"""

import warnings
from typing import Dict, List, Optional

from .models import ClusterState, OSDInfo, SwapProposal
from .scorer import Scorer
from .optimizers.greedy import (
    calculate_variance as _calculate_variance,
    simulate_swap_score as _simulate_swap_score,
    apply_swap as _apply_swap,
    find_best_swap as _find_best_swap,
    GreedyOptimizer
)


def calculate_variance(osds: Dict[int, OSDInfo]) -> float:
    """
    DEPRECATED: Use optimizers.greedy.calculate_variance instead.
    
    Calculate variance of primary distribution across OSDs.
    
    Args:
        osds: Dictionary mapping OSD ID to OSDInfo
        
    Returns:
        Variance value (float)
    """
    return _calculate_variance(osds)


def simulate_swap_score(state: ClusterState, pgid: str, new_primary: int, scorer: Scorer) -> float:
    """
    DEPRECATED: Use optimizers.greedy.simulate_swap_score instead.
    
    Simulate what score would be AFTER a swap without modifying state.
    
    Args:
        state: Current ClusterState
        pgid: PG identifier to swap
        new_primary: OSD ID to become the new primary
        scorer: Scorer instance for composite scoring
        
    Returns:
        Simulated composite score after the swap
    """
    return _simulate_swap_score(state, pgid, new_primary, scorer)


def apply_swap(state: ClusterState, swap: SwapProposal):
    """
    DEPRECATED: Use optimizers.greedy.apply_swap instead.
    
    Apply a swap to the ClusterState (modifies state in place).
    
    Args:
        state: ClusterState to modify
        swap: SwapProposal containing swap details
    """
    return _apply_swap(state, swap)


def find_best_swap(
    state: ClusterState,
    donors: List[int],
    receivers: List[int],
    scorer: Scorer
) -> Optional[SwapProposal]:
    """
    DEPRECATED: Use optimizers.greedy.find_best_swap instead.
    
    Find the single best swap that reduces composite score the most.
    
    Args:
        state: Current ClusterState
        donors: List of OSD IDs with too many primaries
        receivers: List of OSD IDs with too few primaries
        scorer: Scorer instance for composite scoring
        
    Returns:
        SwapProposal with best improvement, or None if no beneficial swaps found
    """
    return _find_best_swap(state, donors, receivers, scorer)


def optimize_primaries(
    state: ClusterState,
    target_cv: float = 0.10,
    max_iterations: int = 1000,
    scorer: Optional[Scorer] = None,
    pool_filter: Optional[int] = None,
    enabled_levels: Optional[List[str]] = None,
    dynamic_weights: bool = False,
    dynamic_strategy: str = 'target_distance',
    weight_update_interval: int = 10,
    strategy_params: Optional[dict] = None
) -> List[SwapProposal]:
    """
    DEPRECATED: Use GreedyOptimizer class instead.
    
    Main greedy algorithm loop to find all beneficial swaps.
    
    This function is maintained for backward compatibility. New code should use:
    
        from ceph_primary_balancer.optimizers import GreedyOptimizer
        optimizer = GreedyOptimizer(target_cv=0.10, ...)
        swaps = optimizer.optimize(state)
    
    Phase 7 Update: Now delegates to GreedyOptimizer while maintaining
    100% backward compatibility with existing behavior.
    
    Args:
        state: ClusterState to optimize (modified in place)
        target_cv: Target coefficient of variation for OSD level (default: 0.10 = 10%)
        max_iterations: Maximum number of iterations (default: 1000)
        scorer: Optional Scorer instance. If None, creates one based on parameters
        pool_filter: Optional pool_id to only optimize PGs from that specific pool
        enabled_levels: Optional list of enabled optimization levels ['osd', 'host', 'pool'].
                       If None, all levels are enabled (default behavior).
        dynamic_weights: Enable dynamic weight adaptation (default: False)
        dynamic_strategy: Weight strategy ('proportional', 'target_distance', default: 'target_distance')
        weight_update_interval: How often to recalculate weights in iterations (default: 10)
        strategy_params: Optional parameters for weight strategy (e.g., {'min_weight': 0.10})
        
    Returns:
        List of all SwapProposal objects applied (empty list if no swaps possible)
    """
    # Optionally add deprecation warning (commented out for now to avoid noise)
    # warnings.warn(
    #     "optimizer.optimize_primaries() is deprecated. "
    #     "Use GreedyOptimizer class instead: "
    #     "from ceph_primary_balancer.optimizers import GreedyOptimizer",
    #     DeprecationWarning,
    #     stacklevel=2
    # )
    
    # Create GreedyOptimizer instance with all parameters
    optimizer = GreedyOptimizer(
        target_cv=target_cv,
        max_iterations=max_iterations,
        scorer=scorer,
        pool_filter=pool_filter,
        enabled_levels=enabled_levels,
        dynamic_weights=dynamic_weights,
        dynamic_strategy=dynamic_strategy,
        weight_update_interval=weight_update_interval,
        strategy_params=strategy_params,
        verbose=True  # Match original behavior of printing output
    )
    
    # Run optimization and return swaps
    return optimizer.optimize(state)
