"""
Ceph Primary PG Balancer - Benchmark Framework

This module provides comprehensive benchmarking capabilities for testing
and validating the optimizer's performance, quality, and scalability.

Components:
- generator: Synthetic cluster state generation
- profiler: Performance and memory profiling
- quality_analyzer: Optimization quality metrics
- runner: Benchmark orchestration
- reporter: Results reporting
- scenarios: Standard test scenarios

"""

__version__ = "1.5.0"

from .generator import (
    generate_synthetic_cluster,
    generate_ec_pool,
    generate_imbalance_pattern,
    generate_multi_pool_scenario,
    save_test_dataset,
    load_test_dataset,
)

from .profiler import (
    profile_optimization,
    benchmark_scalability,
    PerformanceMetrics,
    MemoryMetrics,
    ScalabilityMetrics,
)

from .quality_analyzer import (
    analyze_balance_quality,
    analyze_convergence,
    BalanceQualityMetrics,
    ConvergenceMetrics,
    StabilityMetrics,
)

from .runner import (
    BenchmarkSuite,
    RegressionDetector,
)

from .reporter import (
    TerminalReporter,
    JSONReporter,
)

__all__ = [
    # Generator
    'generate_synthetic_cluster',
    'generate_ec_pool',
    'generate_imbalance_pattern',
    'generate_multi_pool_scenario',
    'save_test_dataset',
    'load_test_dataset',
    # Profiler
    'profile_optimization',
    'benchmark_scalability',
    'PerformanceMetrics',
    'MemoryMetrics',
    'ScalabilityMetrics',
    # Quality Analyzer
    'analyze_balance_quality',
    'analyze_convergence',
    'BalanceQualityMetrics',
    'ConvergenceMetrics',
    'StabilityMetrics',
    # Runner
    'BenchmarkSuite',
    'RegressionDetector',
    # Reporter
    'TerminalReporter',
    'JSONReporter',
]
