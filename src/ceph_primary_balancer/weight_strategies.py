"""
Weight calculation strategies for dynamic optimization.

This module provides different strategies for calculating optimization weights
that adapt based on the current cluster state. Each strategy implements a
calculate_weights() method that returns a tuple of (w_osd, w_host, w_pool)
summing to 1.0.

Phase 7.1: Dynamic Weight Optimization
"""

from abc import ABC, abstractmethod
from typing import Tuple, List, Optional
from dataclasses import dataclass


@dataclass
class CVState:
    """Current CV values for all dimensions."""
    osd_cv: float
    host_cv: float
    pool_cv: float
    
    def as_tuple(self) -> Tuple[float, float, float]:
        """Return CVs as tuple."""
        return (self.osd_cv, self.host_cv, self.pool_cv)


class WeightStrategy(ABC):
    """
    Base class for weight calculation strategies.
    
    All weight strategies must implement the calculate_weights() method
    to compute optimization weights based on current cluster state.
    """
    
    @abstractmethod
    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Calculate weights based on current state and history.
        
        Args:
            cvs: Current (osd_cv, host_cv, pool_cv) tuple
            target_cv: Target CV to achieve
            cv_history: Historical CV values
            weight_history: Historical weight values
            
        Returns:
            Tuple of (w_osd, w_host, w_pool) summing to 1.0
            
        Raises:
            ValueError: If calculated weights are invalid
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return strategy name."""
        pass
    
    def _validate_weights(self, weights: Tuple[float, float, float]) -> None:
        """
        Validate that weights are valid.
        
        Args:
            weights: Tuple of (w_osd, w_host, w_pool)
            
        Raises:
            ValueError: If weights are invalid
        """
        if len(weights) != 3:
            raise ValueError(f"Weights must be a 3-tuple, got {len(weights)} values")
        
        if any(w < 0 for w in weights):
            raise ValueError(f"Weights must be non-negative, got {weights}")
        
        total = sum(weights)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


class ProportionalWeightStrategy(WeightStrategy):
    """
    CV-proportional weighting strategy.
    
    Weights dimensions proportionally to their current CV values.
    Simple and intuitive, best for evenly imbalanced clusters.
    
    Formula:
        w_i = CV_i / Σ(CV_j)
    
    Example:
        If OSD=40%, Host=10%, Pool=20%:
        Total = 70%
        w_osd = 40/70 = 0.571 (57%)
        w_host = 10/70 = 0.143 (14%)
        w_pool = 20/70 = 0.286 (29%)
    """
    
    @property
    def name(self) -> str:
        return "proportional"
    
    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Calculate weights proportional to current CVs.
        
        Args:
            cvs: Current (osd_cv, host_cv, pool_cv)
            target_cv: Target CV (not used in this strategy)
            cv_history: Historical CV values (not used in this strategy)
            weight_history: Historical weight values (not used in this strategy)
            
        Returns:
            Tuple of (w_osd, w_host, w_pool) summing to 1.0
        """
        osd_cv, host_cv, pool_cv = cvs
        
        # Handle edge case: all CVs are zero or near-zero
        total = osd_cv + host_cv + pool_cv
        if total < 0.0001:
            # Return balanced weights
            return (0.33, 0.33, 0.34)
        
        # Simple proportional calculation
        w_osd = osd_cv / total
        w_host = host_cv / total
        w_pool = pool_cv / total
        
        weights = (w_osd, w_host, w_pool)
        self._validate_weights(weights)
        return weights


class TargetDistanceWeightStrategy(WeightStrategy):
    """
    Target-distance weighting strategy.
    
    Weights dimensions based on distance from target CV, ignoring
    dimensions already at or below target. Recommended as default.
    
    Formula:
        distance_i = max(0, CV_i - target_cv)
        w_i = distance_i / Σ(distance_j)
    
    Example (target=10%):
        If OSD=40%, Host=9%, Pool=15%:
        distance_osd = max(0, 40-10) = 30
        distance_host = max(0, 9-10) = 0   ← Already at target!
        distance_pool = max(0, 15-10) = 5
        Total = 35
        
        w_osd = 30/35 = 0.857 (86%)  ← Focus here
        w_host = 0/35 = 0.000 (0%)   ← Ignore
        w_pool = 5/35 = 0.143 (14%)
    
    With minimum weight enforcement:
        w_host would be adjusted to min_weight (e.g., 0.05)
        Others renormalized to maintain sum=1.0
    """
    
    def __init__(self, min_weight: float = 0.05):
        """
        Initialize target-distance strategy.
        
        Args:
            min_weight: Minimum weight for any dimension (prevents complete neglect)
        
        Raises:
            ValueError: If min_weight is invalid
        """
        if min_weight < 0 or min_weight > 0.3:
            raise ValueError(f"min_weight must be between 0 and 0.3, got {min_weight}")
        
        self.min_weight = min_weight
    
    @property
    def name(self) -> str:
        return "target_distance"
    
    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Calculate weights based on distance from target.
        
        Args:
            cvs: Current (osd_cv, host_cv, pool_cv)
            target_cv: Target CV to achieve
            cv_history: Historical CV values (not used in this strategy)
            weight_history: Historical weight values (not used in this strategy)
            
        Returns:
            Tuple of (w_osd, w_host, w_pool) summing to 1.0
        """
        osd_cv, host_cv, pool_cv = cvs
        
        # Calculate distances (0 if already at/below target)
        osd_dist = max(0.0, osd_cv - target_cv)
        host_dist = max(0.0, host_cv - target_cv)
        pool_dist = max(0.0, pool_cv - target_cv)
        
        total_dist = osd_dist + host_dist + pool_dist
        
        # If all at target, use balanced weights
        if total_dist < 0.0001:
            return (0.33, 0.33, 0.34)
        
        # Calculate base weights
        w_osd = osd_dist / total_dist
        w_host = host_dist / total_dist
        w_pool = pool_dist / total_dist
        
        # Apply minimum weight constraint and renormalize properly
        weights = [w_osd, w_host, w_pool]
        
        # Count how many dimensions need the minimum weight
        num_at_min = sum(1 for w in weights if w < self.min_weight)
        
        if num_at_min == 0:
            # No adjustment needed
            return (w_osd, w_host, w_pool)
        
        # Allocate minimum weights first
        min_total = num_at_min * self.min_weight
        remaining = 1.0 - min_total
        
        if remaining < 0:
            # Too many dimensions need minimum - just use equal weights
            return (0.33, 0.33, 0.34)
        
        # Calculate scale factor for dimensions above minimum
        above_min_total = sum(w for w in weights if w >= self.min_weight)
        
        if above_min_total < 0.0001:
            # All dimensions below minimum - use equal weights
            return (0.33, 0.33, 0.34)
        
        scale_factor = remaining / above_min_total
        
        # Apply minimum weights and scale others
        adjusted = []
        for w in weights:
            if w < self.min_weight:
                adjusted.append(self.min_weight)
            else:
                adjusted.append(w * scale_factor)
        
        result = tuple(adjusted)
        self._validate_weights(result)
        return result


class AdaptiveHybridWeightStrategy(WeightStrategy):
    """
    Adaptive hybrid weighting strategy with improvement tracking.
    
    This advanced strategy combines target-distance weighting with improvement
    rate tracking and exponential smoothing. It boosts weights for dimensions
    that are improving slowly, while using smoothing to prevent oscillation.
    
    Features:
    - Target-distance base weighting (like TargetDistanceWeightStrategy)
    - Improvement rate tracking (dimensions not improving get boosted)
    - Exponential smoothing for stability (prevents rapid oscillation)
    - Boost factor for struggling dimensions
    
    Algorithm:
    1. Calculate target-distance weights (base allocation)
    2. Calculate improvement rates from CV history
    3. Apply boost factor to slow-improving dimensions
    4. Smooth with previous weights using exponential smoothing
    5. Normalize to sum=1.0
    
    Example:
        Initial: OSD=40%, Host=35%, Pool=15% (target=10%)
        After 10 iterations: OSD→30%, Host→34%, Pool→12%
        
        Improvement rates:
        - OSD: 25% reduction (fast!) → no boost
        - Host: 3% reduction (slow!) → apply boost
        - Pool: 20% reduction (good) → no boost
        
        Result: Increase host weight to accelerate its convergence
    
    Args:
        min_weight: Minimum weight for any dimension (default: 0.05)
        smoothing_factor: Alpha for exponential smoothing (default: 0.3)
                         0.0 = no smoothing, 1.0 = full smoothing
        boost_factor: Multiplier for slow-improving dimensions (default: 1.5)
        improvement_threshold: CV reduction rate threshold (default: 0.02)
    """
    
    def __init__(
        self,
        min_weight: float = 0.05,
        smoothing_factor: float = 0.3,
        boost_factor: float = 1.5,
        improvement_threshold: float = 0.02
    ):
        """
        Initialize adaptive hybrid strategy.
        
        Args:
            min_weight: Minimum weight for any dimension (0.0-0.3)
            smoothing_factor: Exponential smoothing alpha (0.0-1.0)
                            Higher values = more smoothing/stability
            boost_factor: Multiplier for struggling dimensions (1.0-3.0)
                         Higher values = more aggressive boosting
            improvement_threshold: Min CV reduction rate to avoid boost (0.0-0.1)
                                  Lower = more strict (more dimensions boosted)
        
        Raises:
            ValueError: If parameters are out of valid ranges
        """
        if not 0.0 <= min_weight <= 0.3:
            raise ValueError(f"min_weight must be in [0.0, 0.3], got {min_weight}")
        if not 0.0 <= smoothing_factor <= 1.0:
            raise ValueError(f"smoothing_factor must be in [0.0, 1.0], got {smoothing_factor}")
        if not 1.0 <= boost_factor <= 3.0:
            raise ValueError(f"boost_factor must be in [1.0, 3.0], got {boost_factor}")
        if not 0.0 <= improvement_threshold <= 0.1:
            raise ValueError(f"improvement_threshold must be in [0.0, 0.1], got {improvement_threshold}")
        
        self.min_weight = min_weight
        self.smoothing_factor = smoothing_factor
        self.boost_factor = boost_factor
        self.improvement_threshold = improvement_threshold
    
    @property
    def name(self) -> str:
        return "adaptive_hybrid"
    
    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Calculate adaptive weights with improvement tracking and smoothing.
        
        Args:
            cvs: Current (osd_cv, host_cv, pool_cv)
            target_cv: Target CV to achieve
            cv_history: Historical CV values (used for improvement rate)
            weight_history: Historical weight values (used for smoothing)
            
        Returns:
            Tuple of (w_osd, w_host, w_pool) summing to 1.0
        """
        osd_cv, host_cv, pool_cv = cvs
        
        # Step 1: Calculate base target-distance weights
        base_weights = self._calculate_target_distance_weights(cvs, target_cv)
        
        # Step 2: Calculate improvement rates if we have history
        if len(cv_history) >= 2:
            improvement_rates = self._calculate_improvement_rates(cvs, cv_history)
            boost_multipliers = self._calculate_boost_multipliers(improvement_rates)
            
            # Apply boost factors
            boosted = tuple(w * b for w, b in zip(base_weights, boost_multipliers))
            
            # Renormalize after boosting
            total = sum(boosted)
            if total > 0.0001:
                base_weights = tuple(w / total for w in boosted)
        
        # Step 3: Apply exponential smoothing if we have previous weights
        if weight_history:
            prev_weights = weight_history[-1]
            smoothed = self._apply_smoothing(base_weights, prev_weights)
        else:
            smoothed = base_weights
        
        # Step 4: Enforce minimum weights
        final_weights = self._enforce_minimum_weights(smoothed)
        
        self._validate_weights(final_weights)
        return final_weights
    
    def _calculate_target_distance_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float
    ) -> Tuple[float, float, float]:
        """
        Calculate base weights using target-distance approach.
        
        This is similar to TargetDistanceWeightStrategy but without
        minimum weight enforcement (applied later).
        """
        osd_cv, host_cv, pool_cv = cvs
        
        # Calculate distances
        osd_dist = max(0.0, osd_cv - target_cv)
        host_dist = max(0.0, host_cv - target_cv)
        pool_dist = max(0.0, pool_cv - target_cv)
        
        total_dist = osd_dist + host_dist + pool_dist
        
        # If all at target, use balanced weights
        if total_dist < 0.0001:
            return (0.33, 0.33, 0.34)
        
        # Simple proportional to distance
        return (osd_dist / total_dist, host_dist / total_dist, pool_dist / total_dist)
    
    def _calculate_improvement_rates(
        self,
        current_cvs: Tuple[float, float, float],
        cv_history: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Calculate improvement rate for each dimension.
        
        Improvement rate = (old_cv - current_cv) / old_cv
        Positive = improving, negative = worsening, 0 = no change
        
        Uses a lookback window (last 3 updates or all if fewer).
        """
        if not cv_history:
            return (0.0, 0.0, 0.0)
        
        # Use last 3 entries for trend calculation (or fewer if not available)
        lookback = min(3, len(cv_history))
        old_cvs = cv_history[-lookback]
        
        improvement_rates = []
        for old_cv, curr_cv in zip(old_cvs, current_cvs):
            if old_cv < 0.0001:
                # Already near zero, no improvement possible
                improvement_rates.append(1.0)  # Mark as "good"
            else:
                rate = (old_cv - curr_cv) / old_cv
                improvement_rates.append(rate)
        
        return tuple(improvement_rates)
    
    def _calculate_boost_multipliers(
        self,
        improvement_rates: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        """
        Calculate boost multipliers based on improvement rates.
        
        Dimensions improving slower than threshold get boosted.
        """
        multipliers = []
        for rate in improvement_rates:
            if rate < self.improvement_threshold:
                # Slow improvement or worsening → boost
                multipliers.append(self.boost_factor)
            else:
                # Good improvement → no boost
                multipliers.append(1.0)
        
        return tuple(multipliers)
    
    def _apply_smoothing(
        self,
        current_weights: Tuple[float, float, float],
        previous_weights: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        """
        Apply exponential smoothing to prevent rapid oscillation.
        
        Formula: smoothed = alpha * prev + (1 - alpha) * current
        
        Where alpha is the smoothing factor:
        - alpha=0.0: No smoothing (use current weights)
        - alpha=0.3: Moderate smoothing (default)
        - alpha=1.0: Full smoothing (use previous weights)
        """
        alpha = self.smoothing_factor
        
        smoothed = tuple(
            alpha * prev + (1 - alpha) * curr
            for prev, curr in zip(previous_weights, current_weights)
        )
        
        # Renormalize in case of floating point drift
        total = sum(smoothed)
        if total > 0.0001:
            smoothed = tuple(w / total for w in smoothed)
        
        return smoothed
    
    def _enforce_minimum_weights(
        self,
        weights: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        """
        Enforce minimum weight constraint.
        
        Similar to TargetDistanceWeightStrategy's approach.
        """
        weights_list = list(weights)
        
        # Count dimensions below minimum
        num_at_min = sum(1 for w in weights_list if w < self.min_weight)
        
        if num_at_min == 0:
            return weights  # No adjustment needed
        
        # Allocate minimum weights first
        min_total = num_at_min * self.min_weight
        remaining = 1.0 - min_total
        
        if remaining < 0:
            # Too constrained - use equal weights
            return (0.33, 0.33, 0.34)
        
        # Scale dimensions above minimum
        above_min_total = sum(w for w in weights_list if w >= self.min_weight)
        
        if above_min_total < 0.0001:
            return (0.33, 0.33, 0.34)
        
        scale_factor = remaining / above_min_total
        
        adjusted = []
        for w in weights_list:
            if w < self.min_weight:
                adjusted.append(self.min_weight)
            else:
                adjusted.append(w * scale_factor)
        
        return tuple(adjusted)


class TwoPhaseWeightStrategy(WeightStrategy):
    """
    Two-phase strategy: target_distance in phase 1, hard switch to
    pool-focused weights once OSD and host converge.

    Phase 1 delegates to ``TargetDistanceWeightStrategy`` so all three
    dimensions get proportional-to-distance weight — this is the proven
    approach for initial convergence.

    Phase 2 kicks in when OSD and host CV both drop below
    ``phase1_threshold`` (default: 2× target_cv).  Weights jump to
    ``phase2_weights`` so the remaining iteration budget targets pool CV,
    the hardest dimension.

    The hard switch is the key difference from pure target_distance:
    target_distance keeps OSD/host at ~30%+ weight even when they're
    at floor, stealing budget from pool convergence.
    """

    def __init__(
        self,
        phase1_threshold: float = 0.0,
        phase2_weights: Tuple[float, float, float] = (0.10, 0.05, 0.85),
        min_weight: float = 0.05,
    ):
        if phase1_threshold < 0:
            raise ValueError(f"phase1_threshold must be >= 0, got {phase1_threshold}")
        if len(phase2_weights) != 3 or any(v < 0 for v in phase2_weights) or abs(sum(phase2_weights) - 1.0) > 0.001:
            raise ValueError(f"phase2_weights must be 3 non-negative values summing to 1.0, got {phase2_weights}")
        self.phase1_threshold = phase1_threshold
        self.phase2_weights = phase2_weights
        self._phase1 = TargetDistanceWeightStrategy(min_weight=min_weight)

    @property
    def name(self) -> str:
        return "two_phase"

    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]],
    ) -> Tuple[float, float, float]:
        osd_cv, host_cv, pool_cv = cvs
        threshold = self.phase1_threshold if self.phase1_threshold > 0 else 2.0 * target_cv

        if osd_cv <= threshold and host_cv <= threshold:
            return self.phase2_weights
        return self._phase1.calculate_weights(cvs, target_cv, cv_history, weight_history)


class WeightStrategyFactory:
    """
    Factory for creating weight strategies.
    
    Provides a centralized way to instantiate weight strategies by name
    with optional parameters.
    """
    
    _strategies = {
        'proportional': ProportionalWeightStrategy,
        'target_distance': TargetDistanceWeightStrategy,
        'adaptive_hybrid': AdaptiveHybridWeightStrategy,
        'two_phase': TwoPhaseWeightStrategy,
    }
    
    @classmethod
    def get_strategy(cls, name: str, **kwargs) -> WeightStrategy:
        """
        Get weight strategy by name.
        
        Args:
            name: Strategy name ('proportional', 'target_distance')
            **kwargs: Strategy-specific parameters
            
        Returns:
            WeightStrategy instance
            
        Raises:
            ValueError: If strategy name unknown
            
        Examples:
            >>> factory = WeightStrategyFactory()
            >>> strategy = factory.get_strategy('proportional')
            >>> strategy = factory.get_strategy('target_distance', min_weight=0.1)
        """
        if name not in cls._strategies:
            raise ValueError(
                f"Unknown strategy '{name}'. "
                f"Available: {', '.join(sorted(cls._strategies.keys()))}"
            )
        
        return cls._strategies[name](**kwargs)
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        """
        List all available strategies.
        
        Returns:
            List of strategy names
        """
        return sorted(cls._strategies.keys())
    
    @classmethod
    def register_strategy(cls, name: str, strategy_class: type) -> None:
        """
        Register a new strategy.
        
        This allows users to add custom strategies.
        
        Args:
            name: Strategy name
            strategy_class: Strategy class (must inherit from WeightStrategy)
            
        Raises:
            ValueError: If strategy_class doesn't inherit from WeightStrategy
        """
        if not issubclass(strategy_class, WeightStrategy):
            raise ValueError(f"{strategy_class} must inherit from WeightStrategy")
        
        cls._strategies[name] = strategy_class
