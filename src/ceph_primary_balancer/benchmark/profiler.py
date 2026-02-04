"""
Performance and memory profiling for optimizer benchmarking.

This module provides detailed performance metrics including runtime,
memory usage, and scalability analysis.
"""

import time
import tracemalloc
import sys
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import copy

from ..models import ClusterState
from ..optimizer import optimize_primaries
from ..scorer import Scorer
from .generator import generate_synthetic_cluster


@dataclass
class PerformanceMetrics:
    """Runtime performance metrics."""
    execution_time_total: float         # Total execution time (seconds)
    execution_time_optimize: float      # Optimization algorithm time
    execution_time_scoring: float       # Scoring calculation time (estimated)
    
    iterations_count: int               # Number of optimization iterations
    swaps_evaluated: int                # Total swaps evaluated (estimated)
    swaps_applied: int                  # Swaps actually applied
    
    swaps_per_second: float            # Throughput metric
    iterations_per_second: float        # Iteration rate
    time_per_iteration: float          # Average iteration time (ms)


@dataclass
class MemoryMetrics:
    """Memory usage metrics."""
    peak_memory_mb: float              # Peak memory usage
    memory_per_pg_kb: float            # Memory efficiency per PG
    memory_per_osd_kb: float           # Memory per OSD
    state_size_mb: float               # ClusterState object size estimate
    
    memory_start_mb: float             # Memory at start
    memory_end_mb: float               # Memory at end
    memory_delta_mb: float             # Memory growth during execution


@dataclass
class ScalabilityMetrics:
    """Scalability test results."""
    scale_factor: int                  # Scale multiplier
    num_osds: int
    num_pgs: int
    execution_time: float
    peak_memory_mb: float
    
    # Throughput metrics
    pgs_per_second: float
    osds_per_second: float


def _estimate_object_size(obj) -> float:
    """
    Estimate size of Python object in MB.
    
    Args:
        obj: Object to measure
        
    Returns:
        Estimated size in MB
    """
    size = sys.getsizeof(obj)
    
    # Recursively estimate dict/list sizes
    if isinstance(obj, dict):
        size += sum(_estimate_object_size(k) + _estimate_object_size(v) 
                   for k, v in obj.items())
    elif isinstance(obj, (list, tuple)):
        size += sum(_estimate_object_size(item) for item in obj)
    
    return size / (1024 * 1024)  # Convert to MB


def profile_optimization(
    state: ClusterState,
    target_cv: float = 0.10,
    scorer: Optional[Scorer] = None,
    max_iterations: int = 10000
) -> Tuple[PerformanceMetrics, MemoryMetrics]:
    """
    Profile complete optimization run with detailed metrics.
    
    Args:
        state: ClusterState to optimize
        target_cv: Target coefficient of variation
        scorer: Scorer instance (None = create default)
        max_iterations: Maximum optimization iterations
        
    Returns:
        Tuple of (PerformanceMetrics, MemoryMetrics)
    """
    # Create scorer if not provided
    if scorer is None:
        scorer = Scorer(
            w_osd=0.5,
            w_host=0.3,
            w_pool=0.2
        )
    
    # Start memory tracking
    tracemalloc.start()
    memory_start = tracemalloc.get_traced_memory()[0] / (1024 * 1024)  # MB
    
    # Measure state size
    state_copy = copy.deepcopy(state)
    state_size = _estimate_object_size(state_copy)
    
    # Start timing
    start_time = time.time()
    
    # Run optimization
    optimize_start = time.time()
    swaps = optimize_primaries(
        state=state_copy,
        scorer=scorer,
        target_cv=target_cv,
        max_iterations=max_iterations
    )
    optimize_end = time.time()
    
    # End timing
    end_time = time.time()
    
    # Memory measurements
    memory_peak = tracemalloc.get_traced_memory()[1] / (1024 * 1024)  # MB
    memory_end = tracemalloc.get_traced_memory()[0] / (1024 * 1024)  # MB
    tracemalloc.stop()
    
    # Calculate metrics
    total_time = end_time - start_time
    optimize_time = optimize_end - optimize_start
    
    # Estimate scoring time (rough approximation)
    # Scoring happens during optimization, estimate as 30% of optimize time
    scoring_time = optimize_time * 0.3
    
    # Calculate throughput
    num_swaps = len(swaps)
    swaps_per_sec = num_swaps / optimize_time if optimize_time > 0 else 0
    
    # Estimate iterations (rough: depends on algorithm implementation)
    # For greedy algorithm, iterations ≈ number of swaps found
    estimated_iterations = num_swaps
    iterations_per_sec = estimated_iterations / optimize_time if optimize_time > 0 else 0
    time_per_iter_ms = (optimize_time * 1000) / estimated_iterations if estimated_iterations > 0 else 0
    
    # Estimate swaps evaluated (greedy evaluates many more than it applies)
    # Rough estimate: evaluated ≈ applied * (num_osds / 2)
    num_osds = len(state.osds)
    estimated_evaluated = num_swaps * max(1, num_osds // 2)
    
    # Calculate memory efficiency
    num_pgs = len(state.pgs)
    memory_per_pg = (memory_peak * 1024) / num_pgs if num_pgs > 0 else 0  # KB
    memory_per_osd = (memory_peak * 1024) / num_osds if num_osds > 0 else 0  # KB
    
    perf_metrics = PerformanceMetrics(
        execution_time_total=total_time,
        execution_time_optimize=optimize_time,
        execution_time_scoring=scoring_time,
        iterations_count=estimated_iterations,
        swaps_evaluated=estimated_evaluated,
        swaps_applied=num_swaps,
        swaps_per_second=swaps_per_sec,
        iterations_per_second=iterations_per_sec,
        time_per_iteration=time_per_iter_ms
    )
    
    mem_metrics = MemoryMetrics(
        peak_memory_mb=memory_peak,
        memory_per_pg_kb=memory_per_pg,
        memory_per_osd_kb=memory_per_osd,
        state_size_mb=state_size,
        memory_start_mb=memory_start,
        memory_end_mb=memory_end,
        memory_delta_mb=memory_end - memory_start
    )
    
    return perf_metrics, mem_metrics


def benchmark_scalability(
    scales: Optional[List[Tuple[int, int]]] = None,
    target_cv: float = 0.10,
    imbalance_cv: float = 0.30,
    seed: int = 42,
    max_iterations: int = 1000
) -> List[ScalabilityMetrics]:
    """
    Test performance across different scales.
    
    Args:
        scales: List of (num_osds, num_pgs) tuples to test
        target_cv: Target CV for optimization
        imbalance_cv: Initial imbalance CV
        seed: Random seed for reproducibility
        max_iterations: Maximum optimization iterations
        
    Returns:
        List of ScalabilityMetrics for each scale
    """
    # Default scales if not provided
    if scales is None:
        scales = [
            (10, 100),          # Tiny (smoke test)
            (50, 1000),         # Small
            (100, 5000),        # Medium
            (250, 12500),       # Large
            (500, 25000),       # X-Large
        ]
    
    results = []
    
    for scale_idx, (num_osds, num_pgs) in enumerate(scales):
        # Calculate derived parameters
        num_hosts = max(1, num_osds // 10)  # 10 OSDs per host
        num_pools = min(5, max(1, num_pgs // 1000))  # Scale pools with PGs
        pgs_per_pool = num_pgs // num_pools
        
        # Generate cluster
        state = generate_synthetic_cluster(
            num_osds=num_osds,
            num_hosts=num_hosts,
            num_pools=num_pools,
            pgs_per_pool=pgs_per_pool,
            replication_factor=3,
            imbalance_cv=imbalance_cv,
            imbalance_pattern='random',
            seed=seed + scale_idx  # Different seed per scale
        )
        
        # Profile optimization
        perf, mem = profile_optimization(
            state=state,
            target_cv=target_cv,
            max_iterations=max_iterations
        )
        
        # Calculate throughput
        pgs_per_sec = num_pgs / perf.execution_time_optimize if perf.execution_time_optimize > 0 else 0
        osds_per_sec = num_osds / perf.execution_time_optimize if perf.execution_time_optimize > 0 else 0
        
        results.append(ScalabilityMetrics(
            scale_factor=scale_idx + 1,
            num_osds=num_osds,
            num_pgs=num_pgs,
            execution_time=perf.execution_time_optimize,
            peak_memory_mb=mem.peak_memory_mb,
            pgs_per_second=pgs_per_sec,
            osds_per_second=osds_per_sec
        ))
    
    return results


def profile_hot_spots(
    state: ClusterState,
    target_cv: float = 0.10
) -> Dict[str, float]:
    """
    Identify performance bottlenecks using basic timing.
    
    Note: For detailed profiling, use cProfile externally:
        python -m cProfile -o output.prof -m ceph_primary_balancer.cli
    
    Args:
        state: ClusterState to optimize
        target_cv: Target CV
        
    Returns:
        Dict of function/section names to execution times
    """
    timings = {}
    
    # Time data collection (already collected, so this is artificial)
    start = time.time()
    _ = copy.deepcopy(state)
    timings['data_collection'] = time.time() - start
    
    # Time scorer initialization
    start = time.time()
    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
    timings['scorer_init'] = time.time() - start
    
    # Time initial score calculation
    start = time.time()
    _ = scorer.calculate_score(state)
    timings['initial_scoring'] = time.time() - start
    
    # Time optimization
    start = time.time()
    _ = optimize_primaries(state, scorer, target_cv, max_iterations=1000)
    timings['optimization'] = time.time() - start
    
    return timings


def estimate_complexity(
    scalability_results: List[ScalabilityMetrics]
) -> Dict[str, str]:
    """
    Estimate time and memory complexity from scalability results.
    
    Args:
        scalability_results: Results from benchmark_scalability
        
    Returns:
        Dict with 'time_complexity' and 'memory_complexity' estimates
    """
    if len(scalability_results) < 3:
        return {
            'time_complexity': 'insufficient_data',
            'memory_complexity': 'insufficient_data'
        }
    
    # Analyze time complexity by comparing ratios
    # Compare first and last results
    first = scalability_results[0]
    last = scalability_results[-1]
    
    scale_ratio = last.num_pgs / first.num_pgs
    time_ratio = last.execution_time / first.execution_time if first.execution_time > 0 else 0
    memory_ratio = last.peak_memory_mb / first.peak_memory_mb if first.peak_memory_mb > 0 else 0
    
    # Estimate time complexity
    if time_ratio < scale_ratio * 1.5:
        time_complexity = 'O(n) - Linear'
    elif time_ratio < scale_ratio ** 1.5:
        time_complexity = 'O(n log n) - Log-linear'
    elif time_ratio < scale_ratio ** 2:
        time_complexity = 'O(n²) - Quadratic'
    else:
        time_complexity = 'O(n³) or worse - Cubic+'
    
    # Estimate memory complexity
    if memory_ratio < scale_ratio * 1.5:
        memory_complexity = 'O(n) - Linear'
    elif memory_ratio < scale_ratio * 2:
        memory_complexity = 'O(n log n) - Log-linear'
    else:
        memory_complexity = 'O(n²) - Quadratic'
    
    return {
        'time_complexity': time_complexity,
        'memory_complexity': memory_complexity,
        'scale_ratio': scale_ratio,
        'time_ratio': time_ratio,
        'memory_ratio': memory_ratio
    }


def quick_benchmark(
    num_osds: int = 10,
    num_pgs: int = 100,
    imbalance_cv: float = 0.30
) -> Tuple[PerformanceMetrics, MemoryMetrics]:
    """
    Quick benchmark for smoke testing.
    
    Defaults to small cluster (10 OSDs, 100 PGs) for fast execution.
    
    Args:
        num_osds: Number of OSDs (default: 10 for quick test)
        num_pgs: Number of PGs (default: 100 for quick test)
        imbalance_cv: Initial imbalance
        
    Returns:
        Tuple of (PerformanceMetrics, MemoryMetrics)
    """
    state = generate_synthetic_cluster(
        num_osds=num_osds,
        num_hosts=max(1, num_osds // 10),
        num_pools=max(1, num_pgs // 1000),
        pgs_per_pool=num_pgs // max(1, num_pgs // 1000),
        replication_factor=3,
        imbalance_cv=imbalance_cv,
        seed=42
    )
    
    return profile_optimization(state)
