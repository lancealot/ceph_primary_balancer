"""
Weight calculation strategies for dynamic optimization.

Two strategies are available:
- target_distance: Weights proportional to distance from target CV (default)
- two_phase: target_distance in phase 1, hard switch to pool-focused once OSD/host converge
"""

from typing import Tuple, List


class TargetDistanceWeightStrategy:
    """Weights dimensions based on distance from target CV.

    Dimensions already at or below target get minimum weight so they're
    not completely neglected.  The rest is distributed proportionally
    to each dimension's distance from target.
    """

    name = "target_distance"

    def __init__(self, min_weight: float = 0.05):
        if min_weight < 0 or min_weight > 0.3:
            raise ValueError(f"min_weight must be between 0 and 0.3, got {min_weight}")
        self.min_weight = min_weight

    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]],
    ) -> Tuple[float, float, float]:
        osd_cv, host_cv, pool_cv = cvs

        osd_dist = max(0.0, osd_cv - target_cv)
        host_dist = max(0.0, host_cv - target_cv)
        pool_dist = max(0.0, pool_cv - target_cv)

        total_dist = osd_dist + host_dist + pool_dist
        if total_dist < 0.0001:
            return (0.33, 0.33, 0.34)

        w_osd = osd_dist / total_dist
        w_host = host_dist / total_dist
        w_pool = pool_dist / total_dist

        # Enforce minimum weight and renormalize
        weights = [w_osd, w_host, w_pool]
        num_at_min = sum(1 for w in weights if w < self.min_weight)
        if num_at_min == 0:
            return (w_osd, w_host, w_pool)

        min_total = num_at_min * self.min_weight
        remaining = 1.0 - min_total
        if remaining < 0:
            return (0.33, 0.33, 0.34)

        above_min_total = sum(w for w in weights if w >= self.min_weight)
        if above_min_total < 0.0001:
            return (0.33, 0.33, 0.34)

        scale = remaining / above_min_total
        adjusted = tuple(
            self.min_weight if w < self.min_weight else w * scale
            for w in weights
        )
        return adjusted


class TwoPhaseWeightStrategy:
    """Two-phase strategy: target_distance initially, hard switch to
    pool-focused weights once OSD and host converge.

    The pool-focused phase kicks in when OSD and host CV both drop below
    threshold (default: max(2 * target_cv, 0.15)).  The hard switch stops
    OSD/host from stealing iteration budget once they're "good enough".
    """

    name = "two_phase"

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

    def calculate_weights(
        self,
        cvs: Tuple[float, float, float],
        target_cv: float,
        cv_history: List[Tuple[float, float, float]],
        weight_history: List[Tuple[float, float, float]],
    ) -> Tuple[float, float, float]:
        osd_cv, host_cv, pool_cv = cvs
        # Floor at 0.15 so threshold doesn't become uselessly low
        # at small target_cv values (e.g. 0.01 → 2× = 0.02).
        threshold = self.phase1_threshold if self.phase1_threshold > 0 else max(2.0 * target_cv, 0.15)

        if osd_cv <= threshold and host_cv <= threshold:
            return self.phase2_weights
        return self._phase1.calculate_weights(cvs, target_cv, cv_history, weight_history)


# Simple lookup — no factory, no registry.
STRATEGIES = {
    'target_distance': TargetDistanceWeightStrategy,
    'two_phase': TwoPhaseWeightStrategy,
}


def get_strategy(name: str, **kwargs):
    """Get a weight strategy by name."""
    if name not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{name}'. Available: {', '.join(sorted(STRATEGIES))}")
    return STRATEGIES[name](**kwargs)
