"""
Optimizers package for Ceph Primary PG Balancer.

This package provides various optimization algorithms for balancing primary PG
distribution across OSDs, hosts, and pools. All optimizers implement the
OptimizerBase interface and can be instantiated via the OptimizerRegistry.

Phase 7: Advanced Optimization Algorithms
- Greedy: Fast, deterministic, proven (original algorithm)
- Batch Greedy: Multiple swaps per iteration for faster convergence
- Tabu Search: Memory-based search for better quality
- Simulated Annealing: Probabilistic search for global optimum
- Hybrid: Combined approaches for balanced performance

All algorithms work seamlessly with Phase 7.1 dynamic weight adaptation.
"""

from .base import OptimizerBase, OptimizerRegistry, OptimizerStats
from .greedy import GreedyOptimizer
from .batch_greedy import BatchGreedyOptimizer
from .tabu_search import TabuSearchOptimizer
from .simulated_annealing import SimulatedAnnealingOptimizer

# Register algorithms
OptimizerRegistry.register('greedy', GreedyOptimizer)
OptimizerRegistry.register('batch_greedy', BatchGreedyOptimizer)
OptimizerRegistry.register('tabu_search', TabuSearchOptimizer)
OptimizerRegistry.register('simulated_annealing', SimulatedAnnealingOptimizer)

__all__ = [
    'OptimizerBase',
    'OptimizerRegistry',
    'OptimizerStats',
    'GreedyOptimizer',
    'BatchGreedyOptimizer',
    'TabuSearchOptimizer',
    'SimulatedAnnealingOptimizer'
]
