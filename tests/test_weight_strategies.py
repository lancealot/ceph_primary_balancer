"""
Unit tests for weight calculation strategies.

Tests cover:
- ProportionalWeightStrategy
- TargetDistanceWeightStrategy
- WeightStrategyFactory
- Edge cases and validation

Phase 7.1: Dynamic Weight Optimization
"""

import pytest
from ceph_primary_balancer.weight_strategies import (
    WeightStrategy,
    ProportionalWeightStrategy,
    TargetDistanceWeightStrategy,
    AdaptiveHybridWeightStrategy,
    TwoPhaseWeightStrategy,
    WeightStrategyFactory,
    CVState
)


class TestCVState:
    """Test CVState dataclass."""
    
    def test_cv_state_creation(self):
        """Test CVState can be created."""
        state = CVState(osd_cv=0.40, host_cv=0.10, pool_cv=0.20)
        assert state.osd_cv == 0.40
        assert state.host_cv == 0.10
        assert state.pool_cv == 0.20
    
    def test_cv_state_as_tuple(self):
        """Test as_tuple() method."""
        state = CVState(osd_cv=0.40, host_cv=0.10, pool_cv=0.20)
        assert state.as_tuple() == (0.40, 0.10, 0.20)


class TestProportionalWeightStrategy:
    """Test CV-proportional strategy."""
    
    def test_proportional_calculation_basic(self):
        """Test basic proportional weight calculation."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (0.40, 0.10, 0.20)  # OSD=40%, Host=10%, Pool=20%
        weights = strategy.calculate_weights(
            cvs, 
            target_cv=0.10, 
            cv_history=[], 
            weight_history=[]
        )
        
        # Should be proportional: 40/70, 10/70, 20/70
        assert abs(weights[0] - 0.571) < 0.01  # OSD ≈ 57.1%
        assert abs(weights[1] - 0.143) < 0.01  # Host ≈ 14.3%
        assert abs(weights[2] - 0.286) < 0.01  # Pool ≈ 28.6%
        assert abs(sum(weights) - 1.0) < 0.001  # Sum to 1
    
    def test_proportional_equal_cvs(self):
        """Test with equal CVs."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (0.30, 0.30, 0.30)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        
        # Should be equal weights
        assert abs(weights[0] - 0.333) < 0.01
        assert abs(weights[1] - 0.333) < 0.01
        assert abs(weights[2] - 0.333) < 0.01
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_proportional_zero_cvs(self):
        """Test handling of all-zero CVs."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (0.0, 0.0, 0.0)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        
        # Should return balanced weights
        assert abs(weights[0] - 0.33) < 0.01
        assert abs(weights[1] - 0.33) < 0.01
        assert abs(weights[2] - 0.34) < 0.01
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_proportional_near_zero_cvs(self):
        """Test handling of very small CVs."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (0.00001, 0.00002, 0.00003)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        
        # Should return balanced weights (below threshold)
        assert abs(weights[0] - 0.33) < 0.01
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_proportional_one_dominant_cv(self):
        """Test with one CV much larger than others."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (0.90, 0.05, 0.05)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        
        # OSD should dominate
        assert weights[0] > 0.8  # OSD gets most weight
        assert weights[1] < 0.1  # Host/Pool small
        assert weights[2] < 0.1
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_proportional_name(self):
        """Test strategy name."""
        strategy = ProportionalWeightStrategy()
        assert strategy.name == "proportional"
    
    def test_proportional_ignores_target(self):
        """Test that proportional strategy ignores target CV."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (0.40, 0.10, 0.20)
        
        # Should give same result regardless of target
        weights1 = strategy.calculate_weights(cvs, target_cv=0.05, cv_history=[], weight_history=[])
        weights2 = strategy.calculate_weights(cvs, target_cv=0.20, cv_history=[], weight_history=[])
        
        assert weights1 == weights2


class TestTargetDistanceWeightStrategy:
    """Test target-distance strategy."""
    
    def test_target_distance_all_above_target(self):
        """Test when all dimensions above target."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        cvs = (0.40, 0.20, 0.15)  # All above target of 10%
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Distances: 30%, 10%, 5% → weights should reflect this
        assert weights[0] > weights[1] > weights[2]  # OSD > Host > Pool
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_target_distance_some_at_target(self):
        """Test when some dimensions already at target."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        cvs = (0.40, 0.09, 0.15)  # Host already at target
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Host should get minimum weight only
        assert weights[1] == 0.05  # Exactly minimum
        assert weights[0] > weights[2]  # OSD > Pool
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_target_distance_all_at_target(self):
        """Test when all at/below target."""
        strategy = TargetDistanceWeightStrategy()
        
        cvs = (0.08, 0.09, 0.07)  # All at/below target
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Should return balanced weights
        assert abs(weights[0] - 0.33) < 0.05
        assert abs(weights[1] - 0.33) < 0.05
        assert abs(weights[2] - 0.34) < 0.05
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_target_distance_exact_calculation(self):
        """Test exact calculation matches specification."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.0)  # No min for exact test
        
        # From spec: OSD=40.63%, Host=9.51%, Pool=14.80%, target=10%
        cvs = (0.4063, 0.0951, 0.1480)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Expected: distance_osd=30.63, distance_host=0, distance_pool=4.80
        # Total=35.43, weights: 0.864, 0.000, 0.136
        assert abs(weights[0] - 0.864) < 0.01  # OSD
        assert abs(weights[1] - 0.000) < 0.01  # Host (0 distance)
        assert abs(weights[2] - 0.136) < 0.01  # Pool
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_target_distance_with_min_weight(self):
        """Test minimum weight enforcement."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.10)
        
        cvs = (0.40, 0.08, 0.15)  # Host below target
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # All weights should be at least min_weight
        assert all(w >= 0.10 for w in weights)
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_target_distance_min_weight_zero(self):
        """Test with min_weight=0 (no minimum)."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.0)
        
        cvs = (0.40, 0.08, 0.15)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Host should be exactly 0 (below target, no minimum)
        assert weights[1] == 0.0
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_target_distance_invalid_min_weight(self):
        """Test that invalid min_weight raises error."""
        with pytest.raises(ValueError, match="min_weight must be between"):
            TargetDistanceWeightStrategy(min_weight=-0.1)
        
        with pytest.raises(ValueError, match="min_weight must be between"):
            TargetDistanceWeightStrategy(min_weight=0.5)
    
    def test_target_distance_name(self):
        """Test strategy name."""
        strategy = TargetDistanceWeightStrategy()
        assert strategy.name == "target_distance"
    
    def test_target_distance_production_example(self):
        """Test with real production cluster data."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        # From your production cluster
        cvs = (0.4063, 0.0951, 0.1480)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # OSD should get most weight (far from target)
        assert weights[0] > 0.80  # OSD dominant
        # Host should get minimum (already at target)
        assert weights[1] == 0.05  # Minimum
        # Pool moderate
        assert 0.10 < weights[2] < 0.20
        assert abs(sum(weights) - 1.0) < 0.001


class TestWeightStrategyFactory:
    """Test factory for creating strategies."""
    
    def test_get_proportional_strategy(self):
        """Test getting proportional strategy."""
        strategy = WeightStrategyFactory.get_strategy('proportional')
        assert isinstance(strategy, ProportionalWeightStrategy)
        assert strategy.name == 'proportional'
    
    def test_get_target_distance_strategy(self):
        """Test getting target distance strategy."""
        strategy = WeightStrategyFactory.get_strategy('target_distance')
        assert isinstance(strategy, TargetDistanceWeightStrategy)
        assert strategy.name == 'target_distance'
    
    def test_get_target_distance_with_params(self):
        """Test getting strategy with custom parameters."""
        strategy = WeightStrategyFactory.get_strategy('target_distance', min_weight=0.10)
        assert isinstance(strategy, TargetDistanceWeightStrategy)
        assert strategy.min_weight == 0.10
    
    def test_unknown_strategy(self):
        """Test error on unknown strategy."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            WeightStrategyFactory.get_strategy('nonexistent')
    
    def test_list_strategies(self):
        """Test listing available strategies."""
        strategies = WeightStrategyFactory.list_strategies()
        assert 'proportional' in strategies
        assert 'target_distance' in strategies
        assert 'adaptive_hybrid' in strategies
        assert 'two_phase' in strategies
        assert len(strategies) == 4
        # Should be sorted
        assert strategies == sorted(strategies)
    
    def test_register_custom_strategy(self):
        """Test registering a custom strategy."""
        
        class CustomStrategy(WeightStrategy):
            @property
            def name(self):
                return "custom"
            
            def calculate_weights(self, cvs, target_cv, cv_history, weight_history):
                return (0.5, 0.3, 0.2)
        
        # Register it
        WeightStrategyFactory.register_strategy('custom', CustomStrategy)
        
        # Should now be available
        assert 'custom' in WeightStrategyFactory.list_strategies()
        
        # Should be able to get it
        strategy = WeightStrategyFactory.get_strategy('custom')
        assert isinstance(strategy, CustomStrategy)
        
        # Clean up
        del WeightStrategyFactory._strategies['custom']
    
    def test_register_invalid_strategy(self):
        """Test that registering non-strategy raises error."""
        
        class NotAStrategy:
            pass
        
        with pytest.raises(ValueError, match="must inherit from WeightStrategy"):
            WeightStrategyFactory.register_strategy('invalid', NotAStrategy)


class TestWeightValidation:
    """Test weight validation logic."""
    
    def test_weights_sum_to_one(self):
        """Test that all strategies produce weights summing to 1.0."""
        strategies = [
            ProportionalWeightStrategy(),
            TargetDistanceWeightStrategy()
        ]
        
        test_cases = [
            (0.40, 0.10, 0.20),
            (0.30, 0.30, 0.30),
            (0.50, 0.05, 0.15),
            (0.15, 0.12, 0.18)
        ]
        
        for strategy in strategies:
            for cvs in test_cases:
                weights = strategy.calculate_weights(cvs, 0.10, [], [])
                assert abs(sum(weights) - 1.0) < 0.001, \
                    f"{strategy.name} weights don't sum to 1.0: {weights}"
    
    def test_weights_non_negative(self):
        """Test that all strategies produce non-negative weights."""
        strategies = [
            ProportionalWeightStrategy(),
            TargetDistanceWeightStrategy()
        ]
        
        test_cases = [
            (0.40, 0.10, 0.20),
            (0.0, 0.0, 0.0),
            (0.05, 0.05, 0.05)
        ]
        
        for strategy in strategies:
            for cvs in test_cases:
                weights = strategy.calculate_weights(cvs, 0.10, [], [])
                assert all(w >= 0 for w in weights), \
                    f"{strategy.name} produced negative weights: {weights}"


class TestEdgeCases:
    """Test edge cases and corner scenarios."""
    
    def test_very_small_differences(self):
        """Test with very small differences in CVs."""
        strategy = TargetDistanceWeightStrategy()
        
        cvs = (0.1001, 0.1002, 0.1003)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Should handle tiny differences gracefully
        assert abs(sum(weights) - 1.0) < 0.001
        assert all(w > 0 for w in weights)
    
    def test_very_large_cvs(self):
        """Test with unrealistically large CVs."""
        strategy = ProportionalWeightStrategy()
        
        cvs = (2.0, 1.5, 1.0)  # 200%, 150%, 100% CV (impossible but test robustness)
        weights = strategy.calculate_weights(cvs, 0.10, [], [])
        
        # Should still work
        assert abs(sum(weights) - 1.0) < 0.001
        assert all(w >= 0 for w in weights)
    
    def test_target_higher_than_all_cvs(self):
        """Test when target is higher than all current CVs."""
        strategy = TargetDistanceWeightStrategy()
        
        cvs = (0.05, 0.03, 0.04)
        target = 0.10  # All CVs below target
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Should return balanced weights
        assert abs(weights[0] - 0.33) < 0.05
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_one_cv_exactly_at_target(self):
        """Test when one CV is exactly at target."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        cvs = (0.40, 0.10, 0.20)  # Host exactly at target
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # Host should get minimum weight
        assert weights[1] == 0.05
        assert abs(sum(weights) - 1.0) < 0.001


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    def test_initial_severe_imbalance(self):
        """Test initial state of severely imbalanced cluster."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        # Severely imbalanced initial state
        cvs = (0.60, 0.25, 0.35)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # OSD should dominate (worst imbalance)
        assert weights[0] > 0.50
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_mid_optimization_state(self):
        """Test mid-optimization when some progress made."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        # Mid-optimization: some improvement
        cvs = (0.25, 0.12, 0.15)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # OSD still highest weight but not dominant
        assert weights[0] > weights[2] > weights[1]
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_near_target_state(self):
        """Test near-target state when almost done."""
        strategy = TargetDistanceWeightStrategy(min_weight=0.05)
        
        # Near target - only OSD slightly above
        cvs = (0.11, 0.09, 0.10)
        target = 0.10
        weights = strategy.calculate_weights(cvs, target, [], [])
        
        # OSD should dominate (only dimension above target)
        # Host and Pool get minimum weight (at/below target)
        assert weights[0] == 0.90  # OSD gets remaining after minimums
        assert weights[1] == 0.05  # Host gets minimum
        assert weights[2] == 0.05  # Pool gets minimum
        assert abs(sum(weights) - 1.0) < 0.001


class TestAdaptiveHybridWeightStrategy:
    """Test adaptive hybrid strategy with improvement tracking and smoothing."""
    
    def test_initialization_defaults(self):
        """Test default parameter initialization."""
        strategy = AdaptiveHybridWeightStrategy()
        
        assert strategy.min_weight == 0.05
        assert strategy.smoothing_factor == 0.3
        assert strategy.boost_factor == 1.5
        assert strategy.improvement_threshold == 0.02
        assert strategy.name == "adaptive_hybrid"
    
    def test_initialization_custom_params(self):
        """Test initialization with custom parameters."""
        strategy = AdaptiveHybridWeightStrategy(
            min_weight=0.10,
            smoothing_factor=0.5,
            boost_factor=2.0,
            improvement_threshold=0.05
        )
        
        assert strategy.min_weight == 0.10
        assert strategy.smoothing_factor == 0.5
        assert strategy.boost_factor == 2.0
        assert strategy.improvement_threshold == 0.05
    
    def test_invalid_parameters(self):
        """Test that invalid parameters raise ValueError."""
        # Invalid min_weight
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(min_weight=-0.1)
        
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(min_weight=0.5)
        
        # Invalid smoothing_factor
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(smoothing_factor=-0.1)
        
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(smoothing_factor=1.5)
        
        # Invalid boost_factor
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(boost_factor=0.5)
        
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(boost_factor=5.0)
        
        # Invalid improvement_threshold
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(improvement_threshold=-0.1)
        
        with pytest.raises(ValueError):
            AdaptiveHybridWeightStrategy(improvement_threshold=0.5)
    
    def test_no_history_target_distance_behavior(self):
        """Test that without history, strategy behaves like target-distance."""
        strategy = AdaptiveHybridWeightStrategy(smoothing_factor=0.0)  # No smoothing
        
        cvs = (0.40, 0.10, 0.20)  # OSD=40%, Host=10%, Pool=20%
        target = 0.10
        
        weights = strategy.calculate_weights(cvs, target, cv_history=[], weight_history=[])
        
        # Should focus on dimensions above target
        # OSD: 40-10=30, Host: 0, Pool: 20-10=10, Total=40
        # Expected: OSD=30/40=0.75, Host=0.05 (min), Pool=10/40=0.20 (adjusted)
        
        assert weights[0] > 0.6  # OSD gets most weight
        assert weights[1] >= 0.05  # Host gets minimum
        assert weights[2] > 0.1  # Pool gets some weight
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_improvement_tracking_boosts_slow_dimensions(self):
        """Test that slow-improving dimensions get boosted."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=0.0,  # No smoothing for clearer test
            boost_factor=2.0,
            improvement_threshold=0.10  # 10% improvement required
        )
        
        # Current state: all above target
        cvs = (0.30, 0.25, 0.20)
        target = 0.10
        
        # History shows:
        # OSD: 0.40 → 0.30 = 25% improvement (good!)
        # Host: 0.25 → 0.25 = 0% improvement (bad! boost!)
        # Pool: 0.22 → 0.20 = 9% improvement (marginal, boost!)
        cv_history = [(0.40, 0.25, 0.22)]
        
        weights = strategy.calculate_weights(cvs, target, cv_history, weight_history=[])
        
        # Host and Pool should get boosted (not improving enough)
        # OSD should not get boost (improving well)
        # So Host and Pool should have higher relative weight than base target-distance
        
        # Base target-distance: OSD=20, Host=15, Pool=10 → Total=45
        # Base weights: OSD=20/45=0.44, Host=15/45=0.33, Pool=10/45=0.22
        # After boost: OSD=0.44*1.0, Host=0.33*2.0, Pool=0.22*2.0
        # Renormalized: OSD gets relatively less, Host and Pool get more
        
        assert weights[1] > 0.25  # Host boosted (was 0.33, boosted to ~0.38)
        assert weights[2] > 0.15  # Pool boosted
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_smoothing_prevents_oscillation(self):
        """Test that exponential smoothing stabilizes weights."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=0.5,  # 50% smoothing
            boost_factor=1.0  # No boost to isolate smoothing effect
        )
        
        cvs = (0.30, 0.20, 0.15)
        target = 0.10
        
        # Previous weights were balanced
        prev_weights = (0.40, 0.35, 0.25)
        weight_history = [prev_weights]
        
        # Current target-distance would be different
        # But smoothing should blend with previous
        weights = strategy.calculate_weights(cvs, target, cv_history=[], weight_history=weight_history)
        
        # With 50% smoothing: new = 0.5*prev + 0.5*current
        # So weights should be between prev and pure target-distance
        
        # Verify weights are influenced by previous
        # (not exactly equal to pure target-distance)
        assert abs(sum(weights) - 1.0) < 0.001
        
        # Weights should be "between" previous and current calculation
        # This is a qualitative test - smoothing is working if weights aren't extreme
        assert 0.1 < weights[0] < 0.9
        assert 0.05 < weights[1] < 0.9
        assert 0.05 < weights[2] < 0.9
    
    def test_minimum_weight_enforcement(self):
        """Test that minimum weights are enforced."""
        strategy = AdaptiveHybridWeightStrategy(
            min_weight=0.10,
            smoothing_factor=0.0
        )
        
        # OSD far above target, others at target
        cvs = (0.50, 0.05, 0.05)
        target = 0.10
        
        weights = strategy.calculate_weights(cvs, target, cv_history=[], weight_history=[])
        
        # Host and Pool should get minimum weight
        assert weights[1] >= 0.10
        assert weights[2] >= 0.10
        # OSD gets the rest
        assert weights[0] >= 0.80
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_all_at_target_returns_balanced(self):
        """Test that all-at-target returns balanced weights."""
        strategy = AdaptiveHybridWeightStrategy()
        
        cvs = (0.08, 0.09, 0.07)  # All below target
        target = 0.10
        
        weights = strategy.calculate_weights(cvs, target, cv_history=[], weight_history=[])
        
        # Should return balanced weights
        assert abs(weights[0] - 0.33) < 0.02
        assert abs(weights[1] - 0.33) < 0.02
        assert abs(weights[2] - 0.34) < 0.02
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_improvement_rate_calculation(self):
        """Test improvement rate calculation logic."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=0.0,
            boost_factor=2.0,
            improvement_threshold=0.05
        )
        
        # Scenario: OSD improving fast, Host stagnant, Pool worsening
        current_cvs = (0.20, 0.30, 0.35)
        cv_history = [
            (0.40, 0.30, 0.30),  # 3 iterations ago
        ]
        
        # OSD: 0.40→0.20 = 50% improvement (great!)
        # Host: 0.30→0.30 = 0% improvement (stagnant, boost!)
        # Pool: 0.30→0.35 = -17% improvement (worsening, boost!)
        
        target = 0.10
        weights = strategy.calculate_weights(current_cvs, target, cv_history, weight_history=[])
        
        # Host and Pool should be boosted, OSD not boosted
        # Since all are above target, base allocation favors OSD (0.20-0.10=0.10)
        # vs Host (0.30-0.10=0.20) vs Pool (0.35-0.10=0.25)
        # Base: OSD=10/55, Host=20/55, Pool=25/55
        # After boost: OSD=10*1.0, Host=20*2.0, Pool=25*2.0
        # OSD should have less relative weight due to no boost
        
        assert weights[0] < 0.25  # OSD gets less (no boost)
        assert weights[1] > 0.30  # Host boosted
        assert weights[2] > 0.35  # Pool boosted (worst performer)
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_smoothing_with_multiple_history(self):
        """Test smoothing behavior with longer history."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=0.3,
            boost_factor=1.0
        )
        
        cvs = (0.30, 0.25, 0.20)
        target = 0.10
        
        # Multiple weight history entries
        weight_history = [
            (0.50, 0.30, 0.20),
            (0.45, 0.33, 0.22),
            (0.42, 0.35, 0.23),
        ]
        
        # Only last entry used for smoothing
        weights = strategy.calculate_weights(cvs, target, cv_history=[], weight_history=weight_history)
        
        # Weights should be smoothed with last entry (0.42, 0.35, 0.23)
        # Formula: 0.3*prev + 0.7*current
        assert abs(sum(weights) - 1.0) < 0.001
        assert 0.05 < weights[0] < 0.9
        assert 0.05 < weights[1] < 0.9
        assert 0.05 < weights[2] < 0.9
    
    def test_zero_smoothing_no_history_effect(self):
        """Test that zero smoothing ignores history."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=0.0,  # No smoothing
            boost_factor=1.0
        )
        
        cvs = (0.30, 0.20, 0.15)
        target = 0.10
        
        weight_history = [(0.50, 0.30, 0.20)]
        
        weights_with_history = strategy.calculate_weights(
            cvs, target, cv_history=[], weight_history=weight_history
        )
        
        weights_without_history = strategy.calculate_weights(
            cvs, target, cv_history=[], weight_history=[]
        )
        
        # With zero smoothing, weights should be identical
        assert weights_with_history == weights_without_history
    
    def test_full_smoothing_uses_previous(self):
        """Test that full smoothing (alpha=1.0) mostly uses previous weights."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=1.0,  # Full smoothing
            boost_factor=1.0
        )
        
        cvs = (0.30, 0.20, 0.15)
        target = 0.10
        
        prev_weights = (0.50, 0.30, 0.20)
        weight_history = [prev_weights]
        
        weights = strategy.calculate_weights(
            cvs, target, cv_history=[], weight_history=weight_history
        )
        
        # With alpha=1.0: new = 1.0*prev + 0.0*current = prev
        # Weights should be very close to previous (after renormalization)
        assert abs(weights[0] - prev_weights[0]) < 0.05
        assert abs(weights[1] - prev_weights[1]) < 0.05
        assert abs(weights[2] - prev_weights[2]) < 0.05
        assert abs(sum(weights) - 1.0) < 0.001
    
    def test_combined_boost_and_smoothing(self):
        """Test that boost and smoothing work together correctly."""
        strategy = AdaptiveHybridWeightStrategy(
            smoothing_factor=0.3,
            boost_factor=1.5,
            improvement_threshold=0.05
        )
        
        cvs = (0.25, 0.30, 0.28)
        target = 0.10
        
        # History shows OSD improving, Host stagnant
        cv_history = [(0.35, 0.30, 0.32)]
        weight_history = [(0.40, 0.30, 0.30)]
        
        weights = strategy.calculate_weights(cvs, target, cv_history, weight_history)
        
        # Should apply both boost (to Host) and smoothing (with prev weights)
        assert abs(sum(weights) - 1.0) < 0.001
        assert all(0.05 <= w <= 0.95 for w in weights)
    
    def test_edge_case_very_small_cvs(self):
        """Test edge case with very small CV values."""
        strategy = AdaptiveHybridWeightStrategy()
        
        cvs = (0.001, 0.002, 0.001)  # Very small
        target = 0.10
        
        weights = strategy.calculate_weights(cvs, target, cv_history=[], weight_history=[])
        
        # All below target, should return balanced
        assert abs(weights[0] - 0.33) < 0.02
        assert abs(weights[1] - 0.33) < 0.02
        assert abs(weights[2] - 0.34) < 0.02
        assert abs(sum(weights) - 1.0) < 0.001


class TestWeightStrategyFactoryExtended:
    """Extended tests for factory with adaptive_hybrid."""
    
    def test_get_adaptive_hybrid_strategy(self):
        """Test factory can create adaptive_hybrid strategy."""
        strategy = WeightStrategyFactory.get_strategy('adaptive_hybrid')
        
        assert isinstance(strategy, AdaptiveHybridWeightStrategy)
        assert strategy.name == 'adaptive_hybrid'
    
    def test_get_adaptive_hybrid_with_params(self):
        """Test factory can create adaptive_hybrid with custom params."""
        strategy = WeightStrategyFactory.get_strategy(
            'adaptive_hybrid',
            min_weight=0.10,
            smoothing_factor=0.5,
            boost_factor=2.0,
            improvement_threshold=0.03
        )
        
        assert isinstance(strategy, AdaptiveHybridWeightStrategy)
        assert strategy.min_weight == 0.10
        assert strategy.smoothing_factor == 0.5
        assert strategy.boost_factor == 2.0
        assert strategy.improvement_threshold == 0.03
    
    def test_list_strategies_includes_adaptive_hybrid(self):
        """Test that adaptive_hybrid is in the strategy list."""
        strategies = WeightStrategyFactory.list_strategies()

        assert 'adaptive_hybrid' in strategies
        assert 'proportional' in strategies
        assert 'target_distance' in strategies
        assert 'two_phase' in strategies
        assert len(strategies) == 4


class TestTwoPhaseWeightStrategy:
    """Test two-phase weight strategy for pool CV convergence."""

    def test_phase1_delegates_to_target_distance(self):
        """Phase 1 uses target_distance weighting, not fixed weights."""
        strategy = TwoPhaseWeightStrategy()
        td = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.15, 0.03, 0.30)
        # OSD above threshold (0.10) → phase 1 → target_distance
        w = strategy.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        expected = td.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        assert w == expected

    def test_phase1_when_host_above_threshold(self):
        """Host still above threshold → phase 1 (target_distance)."""
        strategy = TwoPhaseWeightStrategy()
        td = TargetDistanceWeightStrategy(min_weight=0.05)
        cvs = (0.03, 0.15, 0.30)
        w = strategy.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        expected = td.calculate_weights(cvs=cvs, target_cv=0.05, cv_history=[], weight_history=[])
        assert w == expected

    def test_phase2_when_both_below_threshold(self):
        """OSD and host both below threshold → phase 2 weights."""
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.08, 0.06, 0.30), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_phase2_at_exact_threshold(self):
        """OSD and host exactly at threshold → phase 2 (≤ check)."""
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.10, 0.10, 0.30), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_default_threshold_scales_with_target(self):
        """Default threshold is 2× target_cv."""
        strategy = TwoPhaseWeightStrategy()
        # target_cv=0.10 → threshold = 0.20
        # OSD=0.15, Host=0.15 → both below 0.20 → phase 2
        weights = strategy.calculate_weights(
            cvs=(0.15, 0.15, 0.40), target_cv=0.10, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_explicit_threshold_overrides_default(self):
        """Explicit phase1_threshold overrides 2× target_cv."""
        strategy = TwoPhaseWeightStrategy(phase1_threshold=0.30)
        weights = strategy.calculate_weights(
            cvs=(0.25, 0.20, 0.40), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_custom_phase2_weights(self):
        """Custom phase 2 weights are used correctly."""
        strategy = TwoPhaseWeightStrategy(phase2_weights=(0.05, 0.05, 0.90))
        w = strategy.calculate_weights(
            cvs=(0.05, 0.05, 0.40), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert w == (0.05, 0.05, 0.90)

    def test_invalid_phase1_threshold(self):
        with pytest.raises(ValueError, match="phase1_threshold"):
            TwoPhaseWeightStrategy(phase1_threshold=-0.1)

    def test_invalid_phase2_weights(self):
        with pytest.raises(ValueError, match="phase2_weights"):
            TwoPhaseWeightStrategy(phase2_weights=(0.1, 0.1))

    def test_name(self):
        assert TwoPhaseWeightStrategy().name == "two_phase"

    def test_factory_creates_two_phase(self):
        strategy = WeightStrategyFactory.get_strategy('two_phase')
        assert isinstance(strategy, TwoPhaseWeightStrategy)
        assert strategy.name == 'two_phase'

    def test_factory_with_params(self):
        strategy = WeightStrategyFactory.get_strategy(
            'two_phase', phase1_threshold=0.15
        )
        assert isinstance(strategy, TwoPhaseWeightStrategy)
        assert strategy.phase1_threshold == 0.15

    def test_phase2_ignores_history(self):
        """Phase 2 only looks at current CVs, not history."""
        strategy = TwoPhaseWeightStrategy()
        cv_history = [(0.50, 0.50, 0.50), (0.30, 0.30, 0.30)]
        weight_history = [(0.33, 0.33, 0.34), (0.40, 0.40, 0.20)]
        weights = strategy.calculate_weights(
            cvs=(0.05, 0.05, 0.30), target_cv=0.05, cv_history=cv_history, weight_history=weight_history
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_all_dimensions_at_zero(self):
        """All CVs at zero → phase 2 (both below any threshold)."""
        strategy = TwoPhaseWeightStrategy()
        weights = strategy.calculate_weights(
            cvs=(0.0, 0.0, 0.0), target_cv=0.05, cv_history=[], weight_history=[]
        )
        assert weights == (0.10, 0.05, 0.85)

    def test_phase1_gives_pool_high_weight_when_pool_cv_high(self):
        """In phase 1, pool should get significant weight when pool CV is dominant."""
        strategy = TwoPhaseWeightStrategy()
        # OSD above threshold but pool CV is much higher
        weights = strategy.calculate_weights(
            cvs=(0.20, 0.15, 0.80), target_cv=0.05, cv_history=[], weight_history=[]
        )
        # target_distance should give pool the highest weight
        assert weights[2] > weights[0], "Pool should get more weight than OSD when pool CV >> OSD CV"
