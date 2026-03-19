"""
Base optimizer interface for Ceph Primary PG Balancer.

This module defines the abstract base class that all optimization algorithms
must implement, along with the registry for dynamic algorithm selection and
statistics tracking.

Phase 7: Advanced Optimization Algorithms Framework
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Type
import time

from ..models import ClusterState, SwapProposal
from ..scorer import Scorer


@dataclass
class OptimizerStats:
    """
    Statistics collected during optimization.
    
    Tracks key metrics about the optimization process including
    iterations, swaps evaluated and applied, score trajectory,
    and execution time.
    """
    iterations: int = 0
    swaps_evaluated: int = 0
    swaps_applied: int = 0
    score_trajectory: List[float] = field(default_factory=list)
    cv_trajectory: List[float] = field(default_factory=list)
    execution_time: float = 0.0
    algorithm_specific: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


class OptimizerBase(ABC):
    """
    Base class for all optimization algorithms.
    
    All optimizers must implement the optimize() method and return
    a list of SwapProposal objects representing the optimization path.
    
    The base class provides common functionality including:
    - Scorer management (fixed or dynamic weights)
    - Statistics tracking
    - Termination checking
    - Progress reporting
    
    Phase 7.1 Integration: All optimizers automatically work with
    DynamicScorer for adaptive weight optimization with zero extra code.
    """
    
    def __init__(
        self,
        target_cv: float = 0.01,
        max_iterations: int = 1000,
        scorer: Optional[Scorer] = None,
        pool_filter: Optional[int] = None,
        enabled_levels: Optional[List[str]] = None,
        dynamic_weights: bool = False,
        dynamic_strategy: str = 'target_distance',
        weight_update_interval: int = 10,
        strategy_params: Optional[dict] = None,
        verbose: bool = False,
        **kwargs
    ):
        """
        Initialize optimizer with common parameters.
        
        Args:
            target_cv: Target coefficient of variation (default: 0.10 = 10%)
            max_iterations: Maximum optimization iterations (default: 1000)
            scorer: Optional Scorer instance. If None, creates one based on parameters
            pool_filter: Optional pool_id to only optimize PGs from that pool
            enabled_levels: Optional list of enabled levels ['osd', 'host', 'pool']
            dynamic_weights: Enable dynamic weight adaptation (Phase 7.1)
            dynamic_strategy: Weight strategy ('proportional', 'target_distance', 'adaptive_hybrid')
            weight_update_interval: How often to recalculate weights (iterations)
            strategy_params: Optional parameters for weight strategy
            verbose: Enable progress output
            **kwargs: Algorithm-specific parameters
        """
        self.target_cv = target_cv
        self.max_iterations = max_iterations
        self.pool_filter = pool_filter
        self.enabled_levels = enabled_levels
        self.dynamic_weights = dynamic_weights
        self.dynamic_strategy = dynamic_strategy
        self.weight_update_interval = weight_update_interval
        self.strategy_params = strategy_params or {}
        self.verbose = verbose
        self.extra_params = kwargs
        
        # Create scorer if not provided
        if scorer is None:
            scorer = self._create_scorer()
        self.scorer = scorer
        
        # Statistics tracking
        self.stats = OptimizerStats()
        self._start_time = 0.0
    
    def _create_scorer(self) -> Scorer:
        """
        Create appropriate scorer based on configuration.
        
        Returns:
            Scorer instance (either Scorer or DynamicScorer)
        """
        if self.dynamic_weights:
            # Phase 7.1: Use DynamicScorer for adaptive weight optimization
            from ..dynamic_scorer import DynamicScorer
            
            return DynamicScorer(
                strategy=self.dynamic_strategy,
                target_cv=self.target_cv,
                update_interval=self.weight_update_interval,
                strategy_params=self.strategy_params,
                enabled_levels=self.enabled_levels
            )
        elif self.enabled_levels:
            # Auto-adjust weights based on enabled levels
            num_levels = len(self.enabled_levels)
            weight = 1.0 / num_levels
            
            w_osd = weight if 'osd' in self.enabled_levels else 0.0
            w_host = weight if 'host' in self.enabled_levels else 0.0
            w_pool = weight if 'pool' in self.enabled_levels else 0.0
            
            return Scorer(
                w_osd=w_osd,
                w_host=w_host,
                w_pool=w_pool,
                enabled_levels=self.enabled_levels
            )
        else:
            # Default: all levels enabled with Phase 2 weights
            return Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
    
    @abstractmethod
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """
        Optimize the cluster state and return list of swaps.
        
        This is the main method that must be implemented by all algorithms.
        It should iteratively find and apply swaps until termination conditions
        are met (target achieved, no more swaps, max iterations, etc.).
        
        Args:
            state: ClusterState to optimize (modified in place)
            
        Returns:
            List of SwapProposal objects applied during optimization
        """
        pass
    
    @property
    @abstractmethod
    def algorithm_name(self) -> str:
        """Return human-readable algorithm name."""
        pass
    
    @property
    @abstractmethod
    def is_deterministic(self) -> bool:
        """Return True if algorithm produces deterministic results."""
        pass
    
    def _start_timer(self):
        """Start the execution timer."""
        self._start_time = time.time()
    
    def _stop_timer(self):
        """Stop the execution timer and record elapsed time."""
        self.stats.execution_time = time.time() - self._start_time
    
    def _check_termination(self, state: ClusterState, iteration: int) -> bool:
        """Check if optimization should terminate.

        Terminates when max iterations reached or ALL enabled dimensions
        have CV at or below target_cv.
        """
        from ..analyzer import calculate_statistics

        if iteration >= self.max_iterations:
            return True

        enabled = self.scorer.enabled_levels

        if 'osd' in enabled:
            counts = [osd.primary_count for osd in state.osds.values()]
            if counts and calculate_statistics(counts).cv > self.target_cv:
                return False

        if 'host' in enabled and state.hosts:
            counts = [h.primary_count for h in state.hosts.values()]
            if counts and calculate_statistics(counts).cv > self.target_cv:
                return False

        if 'pool' in enabled and state.pools:
            from ..analyzer import calculate_weighted_avg_pool_cv
            avg_cv = calculate_weighted_avg_pool_cv(state)
            if avg_cv > self.target_cv:
                return False

        return True
    
    def _record_iteration(self, state: ClusterState):
        """
        Record statistics for current iteration.
        
        Args:
            state: Current cluster state
        """
        from ..analyzer import calculate_statistics
        
        # Calculate current score and CV
        score = self.scorer.calculate_score(state)
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = calculate_statistics(primary_counts)
        
        # Record trajectories
        self.stats.score_trajectory.append(score)
        self.stats.cv_trajectory.append(stats.cv)
        self.stats.iterations += 1
    
    def _print_progress(self, state: ClusterState, iteration: int, total_swaps: int):
        """
        Print progress message if verbose mode is enabled.
        
        Args:
            state: Current cluster state
            iteration: Current iteration number
            total_swaps: Total swaps applied so far
        """
        if not self.verbose:
            return
        
        from ..analyzer import calculate_statistics

        # Calculate OSD-level CV
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        osd_stats = calculate_statistics(primary_counts)
        
        msg = f"Iteration {iteration}: OSD CV = {osd_stats.cv:.2%}"
        
        # Add host-level CV if available
        if state.hosts:
            host_counts = [host.primary_count for host in state.hosts.values()]
            host_stats = calculate_statistics(host_counts)
            msg += f", Host CV = {host_stats.cv:.2%}"
        
        # Add pool-level CV if available (PG-weighted average)
        if state.pools:
            from ..analyzer import calculate_weighted_avg_pool_cv
            avg_pool_cv = calculate_weighted_avg_pool_cv(state)
            msg += f", Pool CV = {avg_pool_cv:.2%}"
        
        msg += f", Swaps = {total_swaps}"
        print(msg)
    
    def _print_summary(self):
        """Print optimization summary."""
        if not self.verbose:
            return
        
        print(f"\n=== Optimization Summary ===")
        print(f"Algorithm: {self.algorithm_name}")
        print(f"Iterations: {self.stats.iterations}")
        print(f"Swaps evaluated: {self.stats.swaps_evaluated}")
        print(f"Swaps applied: {self.stats.swaps_applied}")
        print(f"Execution time: {self.stats.execution_time:.2f}s")
        
        if self.stats.cv_trajectory:
            print(f"Initial CV: {self.stats.cv_trajectory[0]:.2%}")
            print(f"Final CV: {self.stats.cv_trajectory[-1]:.2%}")
            improvement = self.stats.cv_trajectory[0] - self.stats.cv_trajectory[-1]
            print(f"Improvement: {improvement:.2%}")
        
        # Print dynamic weights summary if applicable
        if self.dynamic_weights and hasattr(self.scorer, 'get_weight_history'):
            print("\n=== Dynamic Weight Evolution ===")
            weight_history = self.scorer.get_weight_history()
            
            if weight_history:
                # Show initial, mid, and final weights
                indices = [0]
                if len(weight_history) > 2:
                    indices.append(len(weight_history) // 2)
                if len(weight_history) > 1:
                    indices.append(len(weight_history) - 1)
                
                for idx in indices:
                    w = weight_history[idx]
                    iter_num = idx * self.weight_update_interval
                    print(f"  Iteration {iter_num:3d}: OSD={w[0]:.3f}, Host={w[1]:.3f}, Pool={w[2]:.3f}")
                
                print(f"Total weight updates: {len(weight_history)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Return optimization statistics.
        
        Returns:
            Dictionary containing all statistics
        """
        return self.stats.to_dict()


class OptimizerRegistry:
    """
    Registry for available optimization algorithms.
    
    Provides a centralized registry for all optimizer implementations,
    allowing dynamic algorithm selection by name. New algorithms can
    be registered using the register() class method.
    
    Example:
        # Register an algorithm
        OptimizerRegistry.register('my_algo', MyOptimizer)
        
        # Get an optimizer instance
        optimizer = OptimizerRegistry.get_optimizer('my_algo', target_cv=0.08)
        
        # List all algorithms
        algos = OptimizerRegistry.list_algorithms()
    """
    
    _algorithms: Dict[str, Type[OptimizerBase]] = {}
    
    @classmethod
    def register(cls, name: str, optimizer_class: Type[OptimizerBase]):
        """
        Register an optimizer class.
        
        Args:
            name: Algorithm name (e.g., 'greedy', 'batch_greedy')
            optimizer_class: Optimizer class (must inherit from OptimizerBase)
        """
        if not issubclass(optimizer_class, OptimizerBase):
            raise TypeError(f"{optimizer_class.__name__} must inherit from OptimizerBase")
        
        cls._algorithms[name] = optimizer_class
    
    @classmethod
    def get_optimizer(cls, name: str, **kwargs) -> OptimizerBase:
        """
        Get optimizer instance by name.
        
        Args:
            name: Algorithm name
            **kwargs: Parameters to pass to optimizer constructor
            
        Returns:
            Optimizer instance
            
        Raises:
            ValueError: If algorithm name is not registered
        """
        if name not in cls._algorithms:
            available = ', '.join(cls.list_algorithms())
            raise ValueError(
                f"Unknown algorithm: '{name}'. "
                f"Available algorithms: {available}"
            )
        
        return cls._algorithms[name](**kwargs)
    
    @classmethod
    def list_algorithms(cls) -> List[str]:
        """
        List all registered algorithm names.
        
        Returns:
            List of algorithm names
        """
        return sorted(cls._algorithms.keys())
    
    @classmethod
    def get_algorithm_info(cls, name: str) -> Dict[str, Any]:
        """
        Get information about a registered algorithm.
        
        Args:
            name: Algorithm name
            
        Returns:
            Dictionary with algorithm information
            
        Raises:
            ValueError: If algorithm name is not registered
        """
        if name not in cls._algorithms:
            raise ValueError(f"Unknown algorithm: '{name}'")
        
        optimizer_class = cls._algorithms[name]
        
        # Create temporary instance to get properties
        # Use minimal parameters to avoid errors
        try:
            temp_instance = optimizer_class(target_cv=0.10, max_iterations=1)
            return {
                'name': name,
                'class': optimizer_class.__name__,
                'algorithm_name': temp_instance.algorithm_name,
                'is_deterministic': temp_instance.is_deterministic,
                'docstring': optimizer_class.__doc__ or 'No description available'
            }
        except Exception:
            # If instantiation fails, return basic info
            return {
                'name': name,
                'class': optimizer_class.__name__,
                'algorithm_name': 'Unknown',
                'is_deterministic': 'Unknown',
                'docstring': optimizer_class.__doc__ or 'No description available'
            }
