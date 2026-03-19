"""
Unit tests for weight calculation strategies.

Tests TargetDistanceWeightStrategy and TwoPhaseWeightStrategy.
"""

import pytest
from ceph_primary_balancer.weight_strategies import (
    TargetDistanceWeightStrategy,
    TwoPhaseWeightStrategy,
    get_strategy,
)


class TestTargetDistanceWeightStrategy:
    """Test target-distance strategy."""

    def test_all_above_target(self):
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.40, 0.20, 0.15)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert weights[0] > weights[1] > weights[2]
        assert abs(sum(weights) - 1.0) < 0.001

    def test_some_at_target(self):
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.40, 0.09, 0.15)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert weights[1] == 0.05
        assert weights[0] > weights[2]
        assert abs(sum(weights) - 1.0) < 0.001

    def test_all_at_target(self):
        strategy = TargetDistanceWeightStrategy()
        cvs = (0.08, 0.09, 0.07)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert abs(weights[0] - 0.33) < 0.05
        assert abs(sum(weights) - 1.0) < 0.001

    def test_exact_calculation(self):
        strategy = TargetDistanceWeightStrategy(min_weight=0.0)
        cvs = (0.4063, 0.0951, 0.1480)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert abs(weights[0] - 0.864) < 0.01
        assert abs(weights[1] - 0.000) < 0.01
        assert abs(weights[2] - 0.136) < 0.01

    def test_min_weight_enforcement(self):
        strategy = TargetDistanceWeightStrategy(min_weight=0.10)
        cvs = (0.40, 0.08, 0.15)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert all(w >= 0.10 for w in weights)
        assert abs(sum(weights) - 1.0) < 0.001

    def test_min_weight_zero(self):
        strategy = TargetDistanceWeightStrategy(min_weight=0.0)
        cvs = (0.40, 0.08, 0.15)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert weights[1] == 0.0
        assert abs(sum(weights) - 1.0) < 0.001

    def test_invalid_min_weight(self):
        with pytest.raises(ValueError):
            TargetDistanceWeightStrategy(min_weight=-0.1)
        with pytest.raises(ValueError):
            TargetDistanceWeightStrategy(min_weight=0.5)

    def test_name(self):
        assert TargetDistanceWeightStrategy().name == "target_distance"

    def test_production_example(self):
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.4063, 0.0951, 0.1480)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        assert weights[0] > 0.80
        assert weights[1] == 0.05
        assert 0.10 < weights[2] < 0.20


class TestTwoPhaseWeightStrategy:
    """Test two-phase weight strategy for pool CV convergence."""

    def test_phase1_delegates_to_target_distance(self):
        strategy = TwoPhaseWeightStrategy()
        td = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.20, 0.03, 0.30)
        w = strategy.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        expected = td.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        assert w == expected

    def test_phase1_when_host_above_threshold(self):
        strategy = TwoPhaseWeightStrategy()
        td = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.03, 0.20, 0.30)
        w = strategy.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        expected = td.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        assert w == expected

    def test_phase2_when_both_below_threshold(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.08, 0.06, 0.30), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_phase2_at_exact_threshold(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.10, 0.10, 0.30), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_default_threshold_scales_with_target(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.15, 0.15, 0.40), target_cv=0.10, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_default_threshold_has_floor(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.10, 0.05, 0.30), target_cv=0.01, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

        td = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs_p1 = (0.20, 0.05, 0.30)
        weights_p1 = strategy.calculate_weights(
            cvs=cvs_p1, target_cv=0.01, cv_history=[], weight_history=[]
        )
        expected = td.calculate_weights(cvs=cvs_p1, target_cv=0.01, cv_history=[], weight_history=[])
        assert weights_p1 == expected

    def test_explicit_threshold_overrides_default(self):
        strategy = TwoPhaseWeightStrategy(phase1_threshold=0.30)
        weights = strategy.calculate_weights(
            cvs=(0.25, 0.20, 0.40), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_custom_phase2_weights(self):
        strategy = TwoPhaseWeightStrategy(phase2_weights=(0.05, 0.05, 0.90))
        w = strategy.calculate_weights(
            cvs=(0.05, 0.05, 0.40), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert w == (0.05, 0.05, 0.90)

    def test_invalid_phase1_threshold(self):
        with pytest.raises(ValueError):
            TwoPhaseWeightStrategy(phase1_threshold=-0.1)

    def test_invalid_phase2_weights(self):
        with pytest.raises(ValueError):
            TwoPhaseWeightStrategy(phase2_weights=(0.1, 0.1))

    def test_name(self):
        assert TwoPhaseWeightStrategy().name == "two_phase"

    def test_phase2_ignores_history(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.05, 0.05, 0.30), target_cv=0.05,
            cv_history=[(0.50, 0.50, 0.50)],
            weight_history=[(0.33, 0.33, 0.34)]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_all_dimensions_at_zero(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.0, 0.0, 0.0), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_phase1_gives_pool_high_weight_when_pool_cv_high(self):
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.20, 0.15, 0.80), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights[2] > weights[0]


class TestGetStrategy:
    """Test the get_strategy lookup function."""

    def test_get_target_distance(self):
        s = get_strategy('target_distance')
        assert isinstance(s, TargetDistanceWeightStrategy)

    def test_get_two_phase(self):
        s = get_strategy('two_phase')
        assert isinstance(s, TwoPhaseWeightStrategy)

    def test_get_with_params(self):
        s = get_strategy('target_distance', min_weight=0.10)
        assert s.min_weight == 0.10

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy('nonexistent')
