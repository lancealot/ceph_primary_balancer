"""
Optimization quality analysis for benchmarking.

This module provides metrics for evaluating the quality of optimization
results including balance improvement, convergence, and stability.
"""

import copy
import statistics
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

from ..models import ClusterState, SwapProposal, Statistics
from ..analyzer import calculate_statistics
from ..optimizers.greedy import GreedyOptimizer
from ..scorer import Scorer


@dataclass
class BalanceQualityMetrics:
    """Balance quality across all dimensions."""
    # OSD-level metrics
    osd_cv_before: float
    osd_cv_after: float
    osd_cv_improvement_pct: float
    osd_variance_reduction_pct: float
    osd_range_reduction: int
    
    # Host-level metrics
    host_cv_before: float
    host_cv_after: float
    host_cv_improvement_pct: float
    
    # Pool-level metrics
    avg_pool_cv_before: float
    avg_pool_cv_after: float
    pool_cv_improvement_pct: float
    
    # Composite metrics
    composite_improvement: float
    fairness_index: float              # Jain's fairness index
    balance_score: float               # 0-100 overall score
    
    # Swap statistics
    num_swaps: int
    swaps_per_osd: float


@dataclass
class ConvergenceMetrics:
    """Convergence behavior analysis."""
    iterations_to_target: int
    iterations_total: int
    convergence_rate: float            # CV reduction per iteration
    
    # Characteristics
    convergence_pattern: str           # linear, fast, slow, plateau
    convergence_efficiency: float      # Improvement per iteration
    
    # Initial vs final
    initial_cv: float
    final_cv: float
    total_improvement_pct: float


@dataclass
class StabilityMetrics:
    """Solution stability and consistency."""
    runs_count: int
    
    # Variability across runs
    cv_improvement_mean: float
    cv_improvement_std: float
    swaps_count_mean: float
    swaps_count_std: float
    
    # Determinism
    determinism_score: float           # 0-100, higher = more deterministic


def calculate_jains_fairness_index(counts: List[int]) -> float:
    """
    Calculate Jain's fairness index: (Σx)² / (n * Σx²)
    
    Result ranges from 1/n (worst) to 1.0 (perfect fairness).
    
    Args:
        counts: List of values to measure fairness
        
    Returns:
        Fairness index (0.0 to 1.0)
    """
    if not counts or all(c == 0 for c in counts):
        return 1.0  # Perfect fairness for empty or all-zero
    
    n = len(counts)
    sum_x = sum(counts)
    sum_x_squared = sum(x * x for x in counts)
    
    if sum_x_squared == 0:
        return 1.0
    
    fairness = (sum_x ** 2) / (n * sum_x_squared)
    return fairness


def score_balance_quality(
    cv: float,
    target_cv: float = 0.10
) -> float:
    """
    Convert CV to 0-100 quality score.
    
    Args:
        cv: Coefficient of variation
        target_cv: Target CV (default: 0.10)
        
    Returns:
        Quality score (0-100, higher is better)
    """
    if cv <= target_cv:
        # Already at or below target, give high score
        return 100.0
    
    # Linear scale from target to 0.50 CV
    # target_cv = 100, 0.50 = 0
    if cv >= 0.50:
        return 0.0
    
    score = 100.0 * (0.50 - cv) / (0.50 - target_cv)
    return max(0.0, min(100.0, score))


def analyze_balance_quality(
    original_state: ClusterState,
    optimized_state: ClusterState,
    swaps: List[SwapProposal]
) -> BalanceQualityMetrics:
    """
    Comprehensive balance quality analysis.
    
    Args:
        original_state: ClusterState before optimization
        optimized_state: ClusterState after optimization
        swaps: List of swaps that were applied
        
    Returns:
        BalanceQualityMetrics
    """
    # OSD-level analysis
    osd_counts_before = [osd.primary_count for osd in original_state.osds.values()]
    osd_counts_after = [osd.primary_count for osd in optimized_state.osds.values()]
    
    osd_stats_before = calculate_statistics(osd_counts_before)
    osd_stats_after = calculate_statistics(osd_counts_after)
    
    osd_cv_before = osd_stats_before.cv
    osd_cv_after = osd_stats_after.cv
    osd_cv_improvement = ((osd_cv_before - osd_cv_after) / osd_cv_before * 100) if osd_cv_before > 0 else 0
    
    # Variance reduction
    variance_before = osd_stats_before.std_dev ** 2
    variance_after = osd_stats_after.std_dev ** 2
    variance_reduction = ((variance_before - variance_after) / variance_before * 100) if variance_before > 0 else 0
    
    # Range reduction
    range_before = osd_stats_before.max_val - osd_stats_before.min_val
    range_after = osd_stats_after.max_val - osd_stats_after.min_val
    range_reduction = range_before - range_after
    
    # Host-level analysis
    if original_state.hosts:
        host_counts_before = [host.primary_count for host in original_state.hosts.values()]
        host_counts_after = [host.primary_count for host in optimized_state.hosts.values()]
        
        host_stats_before = calculate_statistics(host_counts_before)
        host_stats_after = calculate_statistics(host_counts_after)
        
        host_cv_before = host_stats_before.cv
        host_cv_after = host_stats_after.cv
        host_cv_improvement = ((host_cv_before - host_cv_after) / host_cv_before * 100) if host_cv_before > 0 else 0
    else:
        host_cv_before = 0.0
        host_cv_after = 0.0
        host_cv_improvement = 0.0
    
    # Pool-level analysis
    if original_state.pools:
        pool_cvs_before = []
        pool_cvs_after = []
        
        for pool_id in original_state.pools:
            # Before
            pool_counts_before = list(original_state.pools[pool_id].primary_counts.values())
            if pool_counts_before:
                pool_stats_before = calculate_statistics(pool_counts_before)
                pool_cvs_before.append(pool_stats_before.cv)
            
            # After
            pool_counts_after = list(optimized_state.pools[pool_id].primary_counts.values())
            if pool_counts_after:
                pool_stats_after = calculate_statistics(pool_counts_after)
                pool_cvs_after.append(pool_stats_after.cv)
        
        avg_pool_cv_before = statistics.mean(pool_cvs_before) if pool_cvs_before else 0.0
        avg_pool_cv_after = statistics.mean(pool_cvs_after) if pool_cvs_after else 0.0
        pool_cv_improvement = ((avg_pool_cv_before - avg_pool_cv_after) / avg_pool_cv_before * 100) if avg_pool_cv_before > 0 else 0
    else:
        avg_pool_cv_before = 0.0
        avg_pool_cv_after = 0.0
        pool_cv_improvement = 0.0
    
    # Composite improvement (weighted average)
    composite_improvement = (
        0.5 * osd_cv_improvement +
        0.3 * host_cv_improvement +
        0.2 * pool_cv_improvement
    )
    
    # Fairness index
    fairness = calculate_jains_fairness_index(osd_counts_after)
    
    # Overall balance score
    balance_score = score_balance_quality(osd_cv_after)
    
    # Swap statistics
    num_swaps = len(swaps)
    num_osds = len(original_state.osds)
    swaps_per_osd = num_swaps / num_osds if num_osds > 0 else 0
    
    return BalanceQualityMetrics(
        osd_cv_before=osd_cv_before,
        osd_cv_after=osd_cv_after,
        osd_cv_improvement_pct=osd_cv_improvement,
        osd_variance_reduction_pct=variance_reduction,
        osd_range_reduction=range_reduction,
        host_cv_before=host_cv_before,
        host_cv_after=host_cv_after,
        host_cv_improvement_pct=host_cv_improvement,
        avg_pool_cv_before=avg_pool_cv_before,
        avg_pool_cv_after=avg_pool_cv_after,
        pool_cv_improvement_pct=pool_cv_improvement,
        composite_improvement=composite_improvement,
        fairness_index=fairness,
        balance_score=balance_score,
        num_swaps=num_swaps,
        swaps_per_osd=swaps_per_osd
    )


def analyze_convergence(
    state: ClusterState,
    target_cv: float = 0.10,
    scorer: Optional[Scorer] = None,
    max_iterations: int = 10000
) -> ConvergenceMetrics:
    """
    Analyze convergence behavior with detailed metrics.
    
    Args:
        state: ClusterState to optimize
        target_cv: Target CV for optimization
        scorer: Scorer instance (None = create default)
        max_iterations: Maximum iterations
        
    Returns:
        ConvergenceMetrics
    """
    if scorer is None:
        scorer = Scorer(
            weight_osd=0.5,
            weight_host=0.3,
            weight_pool=0.2
        )
    
    # Calculate initial CV
    initial_counts = [osd.primary_count for osd in state.osds.values()]
    initial_stats = calculate_statistics(initial_counts)
    initial_cv = initial_stats.cv
    
    # Run optimization
    state_copy = copy.deepcopy(state)
    swaps = GreedyOptimizer(
        target_cv=target_cv,
        max_iterations=max_iterations,
        scorer=scorer,
    ).optimize(state_copy)
    
    # Calculate final CV
    final_counts = [osd.primary_count for osd in state_copy.osds.values()]
    final_stats = calculate_statistics(final_counts)
    final_cv = final_stats.cv
    
    # Calculate metrics
    iterations_total = len(swaps)  # Approximation: 1 iteration ≈ 1 swap found
    
    # Find iterations to target (when CV first drops below target)
    # Since we don't track intermediate states, estimate based on final improvement
    if final_cv <= target_cv:
        # Assume linear convergence for estimation
        iterations_to_target = int(iterations_total * (initial_cv - target_cv) / (initial_cv - final_cv)) if initial_cv > final_cv else iterations_total
        iterations_to_target = min(iterations_to_target, iterations_total)
    else:
        iterations_to_target = iterations_total  # Didn't reach target
    
    # Convergence rate (CV reduction per iteration)
    convergence_rate = (initial_cv - final_cv) / iterations_total if iterations_total > 0 else 0
    
    # Convergence efficiency (improvement per iteration)
    total_improvement = ((initial_cv - final_cv) / initial_cv * 100) if initial_cv > 0 else 0
    convergence_efficiency = total_improvement / iterations_total if iterations_total > 0 else 0
    
    # Determine convergence pattern
    if convergence_efficiency > 1.0:
        pattern = 'fast'
    elif convergence_efficiency > 0.1:
        pattern = 'linear'
    elif convergence_efficiency > 0.01:
        pattern = 'slow'
    else:
        pattern = 'plateau'
    
    return ConvergenceMetrics(
        iterations_to_target=iterations_to_target,
        iterations_total=iterations_total,
        convergence_rate=convergence_rate,
        convergence_pattern=pattern,
        convergence_efficiency=convergence_efficiency,
        initial_cv=initial_cv,
        final_cv=final_cv,
        total_improvement_pct=total_improvement
    )


def analyze_stability(
    state: ClusterState,
    num_runs: int = 10,
    target_cv: float = 0.10,
    scorer: Optional[Scorer] = None,
    max_iterations: int = 1000
) -> StabilityMetrics:
    """
    Test solution stability across multiple runs.
    
    Args:
        state: ClusterState to optimize
        num_runs: Number of optimization runs
        target_cv: Target CV
        scorer: Scorer instance (None = create default)
        max_iterations: Maximum optimization iterations
        
    Returns:
        StabilityMetrics
    """
    if scorer is None:
        scorer = Scorer(
            weight_osd=0.5,
            weight_host=0.3,
            weight_pool=0.2
        )
    
    # Calculate initial CV
    initial_counts = [osd.primary_count for osd in state.osds.values()]
    initial_stats = calculate_statistics(initial_counts)
    initial_cv = initial_stats.cv
    
    # Run multiple times and collect results
    cv_improvements = []
    swap_counts = []
    final_cvs = []
    
    for _ in range(num_runs):
        state_copy = copy.deepcopy(state)
        swaps = optimize_primaries(
            state=state_copy,
            scorer=scorer,
            target_cv=target_cv,
            max_iterations=max_iterations
        )
        
        # Calculate final CV
        final_counts = [osd.primary_count for osd in state_copy.osds.values()]
        final_stats = calculate_statistics(final_counts)
        final_cv = final_stats.cv
        
        # Record metrics
        cv_improvement = ((initial_cv - final_cv) / initial_cv * 100) if initial_cv > 0 else 0
        cv_improvements.append(cv_improvement)
        swap_counts.append(len(swaps))
        final_cvs.append(final_cv)
    
    # Calculate statistics
    cv_improvement_mean = statistics.mean(cv_improvements)
    cv_improvement_std = statistics.stdev(cv_improvements) if len(cv_improvements) > 1 else 0.0
    
    swaps_count_mean = statistics.mean(swap_counts)
    swaps_count_std = statistics.stdev(swap_counts) if len(swap_counts) > 1 else 0.0
    
    # Determinism score: inverse of variation
    # Perfect determinism (std = 0) = 100, high variation = 0
    cv_coefficient_of_variation = cv_improvement_std / cv_improvement_mean if cv_improvement_mean > 0 else 0
    determinism_score = max(0.0, 100.0 * (1.0 - min(1.0, cv_coefficient_of_variation)))
    
    return StabilityMetrics(
        runs_count=num_runs,
        cv_improvement_mean=cv_improvement_mean,
        cv_improvement_std=cv_improvement_std,
        swaps_count_mean=swaps_count_mean,
        swaps_count_std=swaps_count_std,
        determinism_score=determinism_score
    )


def analyze_multi_dimensional_balance(
    state: ClusterState,
    weight_combinations: Optional[List[Tuple[float, float, float]]] = None
) -> Dict[str, BalanceQualityMetrics]:
    """
    Analyze balance across dimensions with different weights.
    
    Args:
        state: ClusterState to optimize
        weight_combinations: List of (w_osd, w_host, w_pool) tuples
        
    Returns:
        Dict mapping weight combination name to BalanceQualityMetrics
    """
    if weight_combinations is None:
        weight_combinations = [
            (1.0, 0.0, 0.0),  # OSD-only
            (0.7, 0.3, 0.0),  # OSD-Host
            (0.5, 0.3, 0.2),  # Balanced (default)
            (0.3, 0.5, 0.2),  # Host-focused
            (0.3, 0.3, 0.4),  # Pool-focused
        ]
    
    results = {}
    
    for w_osd, w_host, w_pool in weight_combinations:
        # Validate weights sum to 1.0
        total = w_osd + w_host + w_pool
        if abs(total - 1.0) > 0.01:
            continue  # Skip invalid combinations
        
        # Create scorer with these weights
        scorer = Scorer(
            weight_osd=w_osd,
            weight_host=w_host,
            weight_pool=w_pool
        )
        
        # Optimize
        state_copy = copy.deepcopy(state)
        swaps = GreedyOptimizer(
            target_cv=0.10,
            scorer=scorer,
        ).optimize(state_copy)
        
        # Analyze quality
        quality = analyze_balance_quality(state, state_copy, swaps)
        
        # Create name for this combination
        name = f"OSD{int(w_osd*100)}_Host{int(w_host*100)}_Pool{int(w_pool*100)}"
        results[name] = quality
    
    return results
