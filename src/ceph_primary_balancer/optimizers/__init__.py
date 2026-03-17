"""
Optimizers package for Ceph Primary PG Balancer.

All optimizers implement the OptimizerBase interface and can be instantiated
via the OptimizerRegistry.

Available algorithms:
- Greedy: Fast, deterministic, proven (primary algorithm)
- Batch Greedy: Multiple swaps per iteration for faster convergence
"""

from .base import OptimizerBase, OptimizerRegistry, OptimizerStats
from .greedy import GreedyOptimizer
from .batch_greedy import BatchGreedyOptimizer

# Register algorithms
OptimizerRegistry.register('greedy', GreedyOptimizer)
OptimizerRegistry.register('batch_greedy', BatchGreedyOptimizer)

__all__ = [
    'OptimizerBase',
    'OptimizerRegistry',
    'OptimizerStats',
    'GreedyOptimizer',
    'BatchGreedyOptimizer',
]
