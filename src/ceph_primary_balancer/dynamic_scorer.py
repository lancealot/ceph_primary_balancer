"""
Dynamic weight scorer for adaptive optimization.

This module provides the DynamicScorer class that extends the base Scorer
to automatically adjust weights based on the current cluster state. The weights
are updated periodically during optimization to focus effort on the dimensions
that need it most.

Phase 7.1: Dynamic Weight Optimization
"""

from typing import List, Tuple, Optional, Dict, Any
from .scorer import Scorer
from .models import ClusterState
from .analyzer import calculate_statistics
from .scorer import _osd_cv_floor
from .weight_strategies import get_strategy


class DynamicScorer(Scorer):
    """
    Dynamic weight scorer - automatically adjusts weights based on cluster state.
    
    This scorer extends the base Scorer class to provide adaptive weight
    adjustment. Weights are recalculated periodically based on the current
    CV values for each dimension, using the configured weight strategy.
    
    The key benefit is that optimization effort is focused on the dimensions
    that need it most, leading to faster convergence and better final balance.
    
    Attributes:
        strategy: Weight calculation strategy
        target_cv: Target CV to achieve
        update_interval: How often to recalculate weights (in iterations)
        iteration_count: Current iteration counter
        cv_history: Historical CV values for each dimension
        weight_history: Historical weight values
    
    Example:
        >>> scorer = DynamicScorer(
        ...     strategy='target_distance',
        ...     target_cv=0.10,
        ...     update_interval=10
        ... )
        >>> score = scorer.calculate_score(state)
        # Weights automatically adjust every 10 iterations
    """
    
    def __init__(
        self,
        strategy: str = 'target_distance',
        target_cv: float = 0.10,
        update_interval: int = 10,
        strategy_params: Optional[Dict[str, Any]] = None,
        enabled_levels: Optional[List[str]] = None,
        initial_weights: Optional[Tuple[float, float, float]] = None
    ):
        """
        Initialize dynamic scorer with adaptive weights.
        
        Args:
            strategy: Weight strategy name ('proportional', 'target_distance')
            target_cv: Target CV to achieve
            update_interval: How often to recalculate weights (iterations)
            strategy_params: Optional parameters for the weight strategy
            enabled_levels: List of enabled optimization levels (None = all)
            initial_weights: Optional initial weights (default: balanced)
        
        Raises:
            ValueError: If strategy is unknown or parameters invalid
        
        Example:
            >>> # Target-distance strategy with custom minimum weight
            >>> scorer = DynamicScorer(
            ...     strategy='target_distance',
            ...     target_cv=0.10,
            ...     update_interval=10,
            ...     strategy_params={'min_weight': 0.10}
            ... )
        """
        # Initialize with initial weights (will be updated dynamically)
        if initial_weights is None:
            initial_weights = (0.33, 0.33, 0.34)
        
        super().__init__(
            w_osd=initial_weights[0],
            w_host=initial_weights[1],
            w_pool=initial_weights[2],
            enabled_levels=enabled_levels
        )
        
        self.strategy_name = strategy
        self.target_cv = target_cv
        self.update_interval = update_interval
        self.strategy_params = strategy_params or {}
        
        # Create weight strategy
        self.weight_calculator = get_strategy(strategy, **self.strategy_params)
        
        # History tracking
        self.iteration_count = 0
        self.cv_history: List[Tuple[float, float, float]] = []
        self.weight_history: List[Tuple[float, float, float]] = []
        
    
    def _maybe_update_weights(self, state: ClusterState) -> None:
        """Trigger a weight update if we've reached the next interval boundary."""
        if self.iteration_count % self.update_interval == 0:
            self._update_weights(state)
        self.iteration_count += 1

    def calculate_score(self, state: ClusterState) -> float:
        self._maybe_update_weights(state)
        return super().calculate_score(state)

    def calculate_score_with_components(self, state):
        """Override to trigger dynamic weight updates before scoring.

        The optimizer's hot loop calls this (not calculate_score), so
        weights must update here to actually take effect.
        """
        self._maybe_update_weights(state)
        return super().calculate_score_with_components(state)
    
    def _update_weights(self, state: ClusterState) -> None:
        """
        Update weights based on current cluster state.

        Calculates current CV for each dimension and uses the configured
        weight strategy to determine new weights. Updates are tracked in
        history for later analysis.

        When OSD CV is near its theoretical integer floor, the OSD CV
        passed to the strategy is reduced by the floor amount so the
        strategy sees only the "improvable gap". This naturally shifts
        weight to pool/host as OSD approaches its limit.

        Args:
            state: Current ClusterState
        """
        # Calculate current CVs
        cvs = self._calculate_current_cvs(state)

        # Floor-aware adjustment: reduce OSD's effective CV by its
        # integer floor so the weight strategy allocates based on
        # improvable distance rather than raw CV.
        effective_cvs = cvs
        if state.osds and 'osd' in self.enabled_levels:
            osd_counts = [osd.primary_count for osd in state.osds.values()]
            if osd_counts:
                osd_mean = sum(osd_counts) / len(osd_counts)
                floor_cv = _osd_cv_floor(osd_mean)
                if floor_cv > 0:
                    effective_osd = max(0.0, cvs[0] - floor_cv)
                    effective_cvs = (effective_osd, cvs[1], cvs[2])

        # Get new weights from strategy
        new_weights = self.weight_calculator.calculate_weights(
            effective_cvs,
            self.target_cv,
            self.cv_history,
            self.weight_history
        )
        
        # Update weights (respecting enabled levels)
        self.w_osd = new_weights[0] if 'osd' in self.enabled_levels else 0.0
        self.w_host = new_weights[1] if 'host' in self.enabled_levels else 0.0
        self.w_pool = new_weights[2] if 'pool' in self.enabled_levels else 0.0
        
        # Renormalize if some levels disabled
        total = self.w_osd + self.w_host + self.w_pool
        if total > 0 and abs(total - 1.0) > 0.001:
            self.w_osd /= total
            self.w_host /= total
            self.w_pool /= total
        
        # Record history
        self.cv_history.append(cvs)
        self.weight_history.append((self.w_osd, self.w_host, self.w_pool))
    
    def _calculate_current_cvs(self, state: ClusterState) -> Tuple[float, float, float]:
        """
        Calculate current CV for each dimension.

        Args:
            state: Current ClusterState

        Returns:
            Tuple of (osd_cv, host_cv, pool_cv)
        """
        
        # Calculate OSD CV
        osd_cv = 0.0
        if state.osds and 'osd' in self.enabled_levels:
            osd_counts = [osd.primary_count for osd in state.osds.values()]
            if osd_counts:
                osd_stats = calculate_statistics(osd_counts)
                osd_cv = osd_stats.cv
        
        # Calculate Host CV
        host_cv = 0.0
        if state.hosts and 'host' in self.enabled_levels:
            host_counts = [host.primary_count for host in state.hosts.values()]
            if host_counts:
                host_stats = calculate_statistics(host_counts)
                host_cv = host_stats.cv
        
        # Calculate Pool CV (PG-weighted average across pools, excluding unbalanceable)
        pool_cv = 0.0
        if state.pools and 'pool' in self.enabled_levels:
            from .scorer import _pool_cv_floor, UNBALANCEABLE_CV_FLOOR
            weighted_sum = 0.0
            total_w = 0
            for pool_id, pool in state.pools.items():
                # Skip pools too sparse to balance
                n_part = len(pool.participating_osds) if pool.participating_osds else len(pool.primary_counts)
                if _pool_cv_floor(pool.pg_count, n_part) > UNBALANCEABLE_CV_FLOOR:
                    continue

                pool_pgs = [pg for pg in state.pgs.values() if pg.pool_id == pool_id]
                if pool_pgs:
                    osd_counts_in_pool: Dict[int, int] = {}
                    for pg in pool_pgs:
                        osd_counts_in_pool[pg.primary] = osd_counts_in_pool.get(pg.primary, 0) + 1

                    if osd_counts_in_pool:
                        pool_stats = calculate_statistics(list(osd_counts_in_pool.values()))
                        w = max(pool.pg_count, 1)
                        weighted_sum += pool_stats.cv * w
                        total_w += w

            if total_w > 0:
                pool_cv = weighted_sum / total_w
        
        return (osd_cv, host_cv, pool_cv)
    
    def get_weight_history(self) -> List[Tuple[float, float, float]]:
        """
        Return history of weight changes for analysis.
        
        Returns:
            List of (w_osd, w_host, w_pool) tuples
        
        Example:
            >>> history = scorer.get_weight_history()
            >>> for i, weights in enumerate(history):
            ...     print(f"Update {i}: OSD={weights[0]:.3f}")
        """
        return self.weight_history.copy()
    
    def get_cv_history(self) -> List[Tuple[float, float, float]]:
        """
        Return history of CV values for analysis.
        
        Returns:
            List of (osd_cv, host_cv, pool_cv) tuples
        
        Example:
            >>> cv_history = scorer.get_cv_history()
            >>> for i, cvs in enumerate(cv_history):
            ...     print(f"Update {i}: OSD CV={cvs[0]:.1%}")
        """
        return self.cv_history.copy()
    
    def get_current_weights(self) -> Tuple[float, float, float]:
        """
        Get current weight values.
        
        Returns:
            Tuple of (w_osd, w_host, w_pool)
        """
        return (self.w_osd, self.w_host, self.w_pool)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics about dynamic weight behavior.
        
        Returns:
            Dictionary containing:
                - strategy: Strategy name
                - target_cv: Target CV value
                - update_interval: Update frequency
                - num_updates: Number of weight updates performed
                - current_weights: Current weight values
                - initial_weights: Initial weight values (if any)
                - final_cvs: Final CV values (if any)
        """
        stats = {
            'strategy': self.strategy_name,
            'target_cv': self.target_cv,
            'update_interval': self.update_interval,
            'num_updates': len(self.weight_history),
            'total_iterations': self.iteration_count,
            'current_weights': self.get_current_weights()
        }
        
        if self.weight_history:
            stats['initial_weights'] = self.weight_history[0]
            stats['weight_evolution'] = {
                'min_osd': min(w[0] for w in self.weight_history),
                'max_osd': max(w[0] for w in self.weight_history),
                'min_host': min(w[1] for w in self.weight_history),
                'max_host': max(w[1] for w in self.weight_history),
                'min_pool': min(w[2] for w in self.weight_history),
                'max_pool': max(w[2] for w in self.weight_history),
            }
        
        if self.cv_history:
            stats['initial_cvs'] = self.cv_history[0]
            stats['final_cvs'] = self.cv_history[-1]
            stats['cv_improvement'] = {
                'osd': self.cv_history[0][0] - self.cv_history[-1][0],
                'host': self.cv_history[0][1] - self.cv_history[-1][1],
                'pool': self.cv_history[0][2] - self.cv_history[-1][2],
            }
        
        return stats
    
    def reset(self) -> None:
        """
        Reset iteration counter and history.
        
        Useful for running multiple optimization passes with the same scorer.
        """
        self.iteration_count = 0
        self.cv_history = []
        self.weight_history = []
