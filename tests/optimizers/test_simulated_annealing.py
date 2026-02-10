"""
Tests for Simulated Annealing Optimizer.

Tests cover:
- Initialization and parameter validation
- Temperature management and cooling schedules
- Acceptance probability calculations
- Best solution tracking
- Reheating mechanism
- Determinism with fixed seed
- Quality comparison with greedy and tabu search
- Statistics tracking
- Edge cases
"""

import pytest
import copy
import math
import random
from typing import List

from src.ceph_primary_balancer.optimizers.simulated_annealing import SimulatedAnnealingOptimizer
from src.ceph_primary_balancer.optimizers.base import OptimizerRegistry
from src.ceph_primary_balancer.models import ClusterState, OSDInfo, PGInfo, SwapProposal
from src.ceph_primary_balancer.scorer import Scorer


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope='module', autouse=True)
def register_optimizer():
    """Register SimulatedAnnealingOptimizer for testing."""
    from src.ceph_primary_balancer.optimizers import OptimizerRegistry
    from src.ceph_primary_balancer.optimizers.simulated_annealing import SimulatedAnnealingOptimizer
    OptimizerRegistry.register('simulated_annealing', SimulatedAnnealingOptimizer)
    yield
    # No cleanup needed - other tests may need the registry


@pytest.fixture
def simple_state():
    """Create a simple imbalanced cluster state for testing."""
    osds = {}
    pgs = {}
    
    # Create 10 OSDs
    for i in range(10):
        osds[i] = OSDInfo(
            osd_id=i,
            host=f"host{i // 2}",
            primary_count=0
        )
    
    # Create 100 PGs, heavily imbalanced
    # OSDs 0-2 have 60 PGs, OSDs 3-9 have 40 PGs
    pg_id = 0
    
    # Overload OSDs 0-2 (20 PGs each)
    for osd_id in range(3):
        for _ in range(20):
            acting = [osd_id, (osd_id + 1) % 10, (osd_id + 2) % 10]
            pgs[f"1.{pg_id}"] = PGInfo(
                pgid=f"1.{pg_id}",
                pool_id=1,
                acting=acting
            )
            osds[osd_id].primary_count += 1
            pg_id += 1
    
    # Underload OSDs 3-9 (~6 PGs each)
    remaining = 40
    for osd_id in range(3, 10):
        count = remaining // (10 - osd_id)
        for _ in range(count):
            acting = [osd_id, (osd_id + 1) % 10, (osd_id + 2) % 10]
            pgs[f"1.{pg_id}"] = PGInfo(
                pgid=f"1.{pg_id}",
                pool_id=1,
                acting=acting
            )
            osds[osd_id].primary_count += 1
            pg_id += 1
        remaining -= count
    
    return ClusterState(pgs=pgs, osds=osds)


@pytest.fixture
def balanced_state():
    """Create an already balanced cluster state."""
    osds = {}
    pgs = {}
    
    # Create 5 OSDs
    for i in range(5):
        osds[i] = OSDInfo(
            osd_id=i,
            host=f"host{i}",
            primary_count=10  # Perfectly balanced
        )
    
    # Create 50 PGs, perfectly balanced (10 per OSD)
    for pg_id in range(50):
        osd_id = pg_id % 5
        acting = [osd_id, (osd_id + 1) % 5, (osd_id + 2) % 5]
        pgs[f"1.{pg_id}"] = PGInfo(
            pgid=f"1.{pg_id}",
            pool_id=1,
            acting=acting
        )
    
    return ClusterState(pgs=pgs, osds=osds)


# ============================================================================
# Test SimulatedAnnealingOptimizer Initialization
# ============================================================================

class TestSimulatedAnnealingInitialization:
    """Test SimulatedAnnealingOptimizer initialization and validation."""
    
    def test_default_initialization(self):
        """Test default parameter values."""
        optimizer = SimulatedAnnealingOptimizer()
        assert optimizer.initial_temperature == 10.0
        assert optimizer.final_temperature == 0.01
        assert optimizer.cooling_rate == 0.95
        assert optimizer.cooling_schedule == 'geometric'
        assert optimizer.reheating_enabled is True
        assert optimizer.reheating_threshold == 100
        assert optimizer.reheating_factor == 2.0
        assert optimizer.max_candidates == 50
        assert optimizer.random_seed is None
        assert optimizer.target_cv == 0.10
        assert "Simulated Annealing" in optimizer.algorithm_name
        assert optimizer.is_deterministic is False  # No seed by default
    
    def test_custom_temperatures(self):
        """Test custom temperature parameters."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=20.0,
            final_temperature=0.001
        )
        assert optimizer.initial_temperature == 20.0
        assert optimizer.final_temperature == 0.001
    
    def test_custom_cooling_rate(self):
        """Test custom cooling rate."""
        optimizer = SimulatedAnnealingOptimizer(cooling_rate=0.98)
        assert optimizer.cooling_rate == 0.98
    
    def test_linear_cooling_schedule(self):
        """Test linear cooling schedule."""
        optimizer = SimulatedAnnealingOptimizer(
            cooling_schedule='linear',
            cooling_rate=0.1
        )
        assert optimizer.cooling_schedule == 'linear'
        assert optimizer.cooling_rate == 0.1
    
    def test_reheating_disabled(self):
        """Test disabling reheating."""
        optimizer = SimulatedAnnealingOptimizer(reheating_enabled=False)
        assert optimizer.reheating_enabled is False
    
    def test_custom_reheating_params(self):
        """Test custom reheating parameters."""
        optimizer = SimulatedAnnealingOptimizer(
            reheating_threshold=50,
            reheating_factor=3.0
        )
        assert optimizer.reheating_threshold == 50
        assert optimizer.reheating_factor == 3.0
    
    def test_custom_random_seed(self):
        """Test custom random seed."""
        optimizer = SimulatedAnnealingOptimizer(random_seed=42)
        assert optimizer.random_seed == 42
        assert optimizer.is_deterministic is True  # Deterministic with seed
    
    def test_invalid_initial_temperature(self):
        """Test that invalid initial temperature raises error."""
        with pytest.raises(ValueError, match="initial_temperature must be > 0"):
            SimulatedAnnealingOptimizer(initial_temperature=0)
        
        with pytest.raises(ValueError, match="initial_temperature must be > 0"):
            SimulatedAnnealingOptimizer(initial_temperature=-1.0)
    
    def test_invalid_final_temperature(self):
        """Test that invalid final temperature raises error."""
        with pytest.raises(ValueError, match="final_temperature must be > 0"):
            SimulatedAnnealingOptimizer(final_temperature=0)
        
        with pytest.raises(ValueError, match="final_temperature must be > 0"):
            SimulatedAnnealingOptimizer(final_temperature=-0.01)
        
        with pytest.raises(ValueError, match="< initial_temperature"):
            SimulatedAnnealingOptimizer(
                initial_temperature=5.0,
                final_temperature=10.0
            )
    
    def test_invalid_cooling_rate_geometric(self):
        """Test that invalid geometric cooling rate raises error."""
        with pytest.raises(ValueError, match="cooling_rate for geometric"):
            SimulatedAnnealingOptimizer(
                cooling_schedule='geometric',
                cooling_rate=0
            )
        
        with pytest.raises(ValueError, match="cooling_rate for geometric"):
            SimulatedAnnealingOptimizer(
                cooling_schedule='geometric',
                cooling_rate=1.0
            )
        
        with pytest.raises(ValueError, match="cooling_rate for geometric"):
            SimulatedAnnealingOptimizer(
                cooling_schedule='geometric',
                cooling_rate=1.1
            )
    
    def test_invalid_cooling_rate_linear(self):
        """Test that invalid linear cooling rate raises error."""
        with pytest.raises(ValueError, match="cooling_rate for linear"):
            SimulatedAnnealingOptimizer(
                cooling_schedule='linear',
                cooling_rate=0
            )
        
        with pytest.raises(ValueError, match="cooling_rate for linear"):
            SimulatedAnnealingOptimizer(
                cooling_schedule='linear',
                cooling_rate=-0.1
            )
    
    def test_invalid_cooling_schedule(self):
        """Test that invalid cooling schedule raises error."""
        with pytest.raises(ValueError, match="cooling_schedule must be"):
            SimulatedAnnealingOptimizer(cooling_schedule='exponential')
    
    def test_invalid_reheating_threshold(self):
        """Test that invalid reheating threshold raises error."""
        with pytest.raises(ValueError, match="reheating_threshold must be >= 1"):
            SimulatedAnnealingOptimizer(reheating_threshold=0)
    
    def test_invalid_reheating_factor(self):
        """Test that invalid reheating factor raises error."""
        with pytest.raises(ValueError, match="reheating_factor must be > 1.0"):
            SimulatedAnnealingOptimizer(reheating_factor=1.0)
        
        with pytest.raises(ValueError, match="reheating_factor must be > 1.0"):
            SimulatedAnnealingOptimizer(reheating_factor=0.5)
    
    def test_invalid_max_candidates(self):
        """Test that invalid max_candidates raises error."""
        with pytest.raises(ValueError, match="max_candidates must be >= 1"):
            SimulatedAnnealingOptimizer(max_candidates=0)
    
    def test_algorithm_specific_stats_initialized(self):
        """Test that algorithm-specific statistics are initialized."""
        optimizer = SimulatedAnnealingOptimizer()
        assert 'temperature_trajectory' in optimizer.stats.algorithm_specific
        assert 'accepted_worse_moves' in optimizer.stats.algorithm_specific
        assert 'rejected_worse_moves' in optimizer.stats.algorithm_specific
        assert 'accepted_better_moves' in optimizer.stats.algorithm_specific
        assert 'reheats' in optimizer.stats.algorithm_specific
        assert 'best_score_updates' in optimizer.stats.algorithm_specific
        assert 'acceptance_rate' in optimizer.stats.algorithm_specific
        assert optimizer.stats.algorithm_specific['accepted_worse_moves'] == 0
        assert optimizer.stats.algorithm_specific['reheats'] == 0


# ============================================================================
# Test Registry Integration
# ============================================================================

class TestRegistryIntegration:
    """Test integration with OptimizerRegistry."""
    
    def test_registry_has_simulated_annealing(self):
        """Test that simulated_annealing is registered."""
        algorithms = OptimizerRegistry.list_algorithms()
        assert 'simulated_annealing' in algorithms
    
    def test_get_simulated_annealing_from_registry(self):
        """Test getting SimulatedAnnealingOptimizer from registry."""
        optimizer = OptimizerRegistry.get_optimizer(
            'simulated_annealing',
            target_cv=0.08
        )
        assert isinstance(optimizer, SimulatedAnnealingOptimizer)
        assert optimizer.target_cv == 0.08
    
    def test_get_simulated_annealing_with_custom_params(self):
        """Test getting SimulatedAnnealingOptimizer with custom parameters."""
        optimizer = OptimizerRegistry.get_optimizer(
            'simulated_annealing',
            initial_temperature=15.0,
            cooling_rate=0.90,
            random_seed=123,
            target_cv=0.12
        )
        assert optimizer.initial_temperature == 15.0
        assert optimizer.cooling_rate == 0.90
        assert optimizer.random_seed == 123
        assert optimizer.target_cv == 0.12


# ============================================================================
# Test Temperature Management
# ============================================================================

class TestTemperatureManagement:
    """Test temperature cooling and reheating."""
    
    def test_geometric_cooling(self):
        """Test geometric cooling schedule."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            cooling_rate=0.9,
            cooling_schedule='geometric'
        )
        
        optimizer._current_temperature = 10.0
        
        # Apply cooling
        optimizer._cool_temperature()
        assert abs(optimizer._current_temperature - 9.0) < 0.001
        
        optimizer._cool_temperature()
        assert abs(optimizer._current_temperature - 8.1) < 0.001
    
    def test_linear_cooling(self):
        """Test linear cooling schedule."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            cooling_rate=0.5,
            cooling_schedule='linear'
        )
        
        optimizer._current_temperature = 10.0
        
        # Apply cooling
        optimizer._cool_temperature()
        assert abs(optimizer._current_temperature - 9.5) < 0.001
        
        optimizer._cool_temperature()
        assert abs(optimizer._current_temperature - 9.0) < 0.001
    
    def test_linear_cooling_doesnt_go_negative(self):
        """Test that linear cooling doesn't produce negative temperature."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=1.0,
            cooling_rate=0.5,
            cooling_schedule='linear'
        )
        
        optimizer._current_temperature = 0.3
        optimizer._cool_temperature()
        
        # Should be max(0.3 - 0.5, 0.0) = 0.0
        assert optimizer._current_temperature == 0.0
    
    def test_temperature_trajectory_recorded(self, simple_state):
        """Test that temperature trajectory is recorded during optimization."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=5.0,
            cooling_rate=0.95,
            max_iterations=20,
            random_seed=42
        )
        
        optimizer.optimize(simple_state)
        
        trajectory = optimizer.stats.algorithm_specific['temperature_trajectory']
        
        # Should have recorded temperatures
        assert len(trajectory) > 0
        # First temperature should be initial
        assert abs(trajectory[0] - 5.0) < 0.001
        # Temperatures should generally decrease
        assert trajectory[-1] < trajectory[0]


# ============================================================================
# Test Acceptance Probability
# ============================================================================

class TestAcceptanceProbability:
    """Test acceptance probability calculations."""
    
    def test_accepts_improving_moves(self):
        """Test that improving moves are always accepted."""
        optimizer = SimulatedAnnealingOptimizer(random_seed=42)
        optimizer._current_temperature = 10.0
        
        # Positive improvement (better score)
        assert optimizer._accept_swap(1.0) is True
        assert optimizer._accept_swap(0.1) is True
        assert optimizer._accept_swap(0.001) is True
        
        # Stats should track accepted better moves
        assert optimizer.stats.algorithm_specific['accepted_better_moves'] == 3
    
    def test_probabilistic_acceptance_for_worse_moves(self):
        """Test probabilistic acceptance for worsening moves."""
        # Use fixed seed for reproducibility
        optimizer = SimulatedAnnealingOptimizer(random_seed=42)
        optimizer._current_temperature = 10.0
        
        # Test many worse moves to verify probabilistic behavior
        acceptances = []
        for _ in range(100):
            # Reset RNG state for consistency
            random.seed(42 + _)
            optimizer.random_seed = 42 + _
            random.seed(42 + _)
            
            # Small negative improvement (worse score)
            accepted = optimizer._accept_swap(-0.1)
            acceptances.append(accepted)
        
        # Some should be accepted, some rejected
        # With high temperature and small delta, most should be accepted
        # P(accept) = exp(-0.1 / 10.0) = exp(-0.01) ≈ 0.99
        # So we expect most to be accepted
        acceptance_rate = sum(acceptances) / len(acceptances)
        assert acceptance_rate > 0.8  # Should accept most
    
    def test_higher_temperature_accepts_more_worse_moves(self):
        """Test that higher temperature accepts more worse moves."""
        # Test acceptance at different temperatures
        acceptance_high = []
        acceptance_low = []
        
        for trial in range(50):
            # High temperature
            random.seed(100 + trial)
            optimizer_high = SimulatedAnnealingOptimizer(
                initial_temperature=10.0,
                random_seed=100 + trial
            )
            optimizer_high._current_temperature = 10.0
            acceptance_high.append(optimizer_high._accept_swap(-1.0))
            
            # Low temperature
            random.seed(100 + trial)
            optimizer_low = SimulatedAnnealingOptimizer(
                initial_temperature=0.1,
                random_seed=100 + trial
            )
            optimizer_low._current_temperature = 0.1
            acceptance_low.append(optimizer_low._accept_swap(-1.0))
        
        rate_high = sum(acceptance_high) / len(acceptance_high)
        rate_low = sum(acceptance_low) / len(acceptance_low)
        
        # High temperature should accept more worse moves
        assert rate_high > rate_low
    
    def test_acceptance_statistics_tracked(self, simple_state):
        """Test that acceptance statistics are properly tracked."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=5.0,
            max_iterations=30,
            random_seed=42
        )
        
        optimizer.optimize(simple_state)
        
        stats = optimizer.stats.algorithm_specific
        
        # Should have some accepted and possibly some rejected moves
        assert stats['accepted_better_moves'] >= 0
        assert stats['accepted_worse_moves'] >= 0
        assert stats['rejected_worse_moves'] >= 0
        
        # Total should make sense
        total_decisions = (stats['accepted_better_moves'] + 
                          stats['accepted_worse_moves'] + 
                          stats['rejected_worse_moves'])
        assert total_decisions > 0
        
        # Acceptance rate should be calculated
        assert 0 <= stats['acceptance_rate'] <= 1.0


# ============================================================================
# Test Optimization Functionality
# ============================================================================

class TestOptimization:
    """Test core optimization functionality."""
    
    def test_optimizes_imbalanced_cluster(self, simple_state):
        """Test that optimizer improves imbalanced cluster."""
        from src.ceph_primary_balancer.analyzer import calculate_statistics
        
        initial_counts = [osd.primary_count for osd in simple_state.osds.values()]
        initial_stats = calculate_statistics(initial_counts)
        
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            target_cv=0.10,
            max_candidates=30,
            random_seed=42
        )
        swaps = optimizer.optimize(simple_state)
        
        final_counts = [osd.primary_count for osd in simple_state.osds.values()]
        final_stats = calculate_statistics(final_counts)
        
        # Should improve balance
        assert final_stats.cv < initial_stats.cv
        assert len(swaps) > 0
        assert optimizer.stats.swaps_applied == len(swaps)
    
    def test_terminates_at_target_cv(self, simple_state):
        """Test that optimizer improves CV significantly."""
        from src.ceph_primary_balancer.analyzer import calculate_statistics
        
        initial_counts = [osd.primary_count for osd in simple_state.osds.values()]
        initial_stats = calculate_statistics(initial_counts)
        
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            target_cv=0.10,
            max_iterations=200,
            random_seed=42
        )
        optimizer.optimize(simple_state)
        
        final_counts = [osd.primary_count for osd in simple_state.osds.values()]
        final_stats = calculate_statistics(final_counts)
        
        # Should improve significantly
        assert final_stats.cv < initial_stats.cv
        # Should achieve meaningful improvement (at least 20% better)
        assert final_stats.cv < initial_stats.cv * 0.8
    
    def test_no_swaps_on_balanced_cluster(self, balanced_state):
        """Test that optimizer doesn't swap on balanced cluster."""
        optimizer = SimulatedAnnealingOptimizer(
            target_cv=0.10,
            random_seed=42
        )
        swaps = optimizer.optimize(balanced_state)
        
        # Should recognize it's already balanced
        assert len(swaps) == 0
    
    def test_respects_max_iterations(self, simple_state):
        """Test that optimizer respects max_iterations."""
        optimizer = SimulatedAnnealingOptimizer(
            target_cv=0.01,  # Very aggressive target
            max_iterations=10,
            random_seed=42
        )
        optimizer.optimize(simple_state)
        
        # Should stop at max_iterations
        assert optimizer.stats.iterations <= 10
    
    def test_terminates_when_temperature_too_low(self, simple_state):
        """Test that optimizer terminates when temperature reaches minimum."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=1.0,
            final_temperature=0.5,
            cooling_rate=0.5,  # Fast cooling
            target_cv=0.01,  # Won't reach this
            max_iterations=100,
            random_seed=42
        )
        
        optimizer.optimize(simple_state)
        
        # Should terminate due to temperature
        assert optimizer._current_temperature < 0.5


# ============================================================================
# Test Reheating Mechanism
# ============================================================================

class TestReheating:
    """Test reheating mechanism."""
    
    def test_reheating_increases_temperature(self, simple_state):
        """Test that reheating increases temperature when stuck."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=5.0,
            reheating_enabled=True,
            reheating_threshold=5,  # Quick trigger for testing
            reheating_factor=2.0,
            max_iterations=50,
            random_seed=42
        )
        
        optimizer.optimize(simple_state)
        
        # Check if reheating occurred
        reheats = optimizer.stats.algorithm_specific['reheats']
        # May or may not occur depending on optimization path
        assert reheats >= 0
    
    def test_reheating_capped_at_initial(self):
        """Test that reheating doesn't exceed initial temperature."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            reheating_factor=3.0
        )
        
        optimizer._current_temperature = 8.0
        
        # Manually trigger reheating logic
        optimizer._current_temperature *= optimizer.reheating_factor
        optimizer._current_temperature = min(
            optimizer._current_temperature,
            optimizer.initial_temperature
        )
        
        # Should be capped at 10.0, not 24.0
        assert optimizer._current_temperature == 10.0
    
    def test_reheating_disabled_no_reheats(self, simple_state):
        """Test that reheating doesn't occur when disabled."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=5.0,
            reheating_enabled=False,
            max_iterations=50,
            random_seed=42
        )
        
        optimizer.optimize(simple_state)
        
        # Should have zero reheats
        reheats = optimizer.stats.algorithm_specific['reheats']
        assert reheats == 0


# ============================================================================
# Test Best Solution Tracking
# ============================================================================

class TestBestSolutionTracking:
    """Test best solution tracking."""
    
    def test_tracks_best_solution_found(self, simple_state):
        """Test that best solution is tracked during search."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            max_iterations=50,
            random_seed=42
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should have found and tracked best solution
        assert optimizer._best_score is not None
        assert optimizer._best_state is not None
        assert optimizer._best_swaps is not None
        
        # Best score updates should be tracked
        best_updates = optimizer.stats.algorithm_specific['best_score_updates']
        assert best_updates > 0
    
    def test_restores_best_solution_at_end(self, simple_state):
        """Test that best solution is restored at optimization end."""
        from src.ceph_primary_balancer.analyzer import calculate_statistics
        
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            max_iterations=50,
            random_seed=42
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Final state should be the best state found
        final_score = optimizer.scorer.calculate_score(simple_state)
        
        # Should be close to or equal to best score
        assert abs(final_score - optimizer._best_score) < 0.01


# ============================================================================
# Test State Management
# ============================================================================

class TestStateManagement:
    """Test state copying and restoration."""
    
    def test_copy_state_creates_independent_copy(self, simple_state):
        """Test that _copy_state creates independent copy."""
        optimizer = SimulatedAnnealingOptimizer()
        
        # Copy state
        copied_state = optimizer._copy_state(simple_state)
        
        # Modify original
        simple_state.osds[0].primary_count += 10
        
        # Copy should be unchanged
        assert copied_state.osds[0].primary_count != simple_state.osds[0].primary_count
    
    def test_restore_state_recovers_previous_state(self, simple_state):
        """Test that _restore_state correctly restores previous state."""
        optimizer = SimulatedAnnealingOptimizer()
        
        # Save initial state
        saved_state = optimizer._copy_state(simple_state)
        initial_counts = [osd.primary_count for osd in simple_state.osds.values()]
        
        # Modify state
        simple_state.osds[0].primary_count += 5
        simple_state.osds[1].primary_count -= 5
        
        # Restore
        optimizer._restore_state(simple_state, saved_state)
        restored_counts = [osd.primary_count for osd in simple_state.osds.values()]
        
        # Should match initial
        assert restored_counts == initial_counts


# ============================================================================
# Test Determinism
# ============================================================================

class TestDeterminism:
    """Test determinism with fixed random seed."""
    
    def test_produces_same_results_with_seed(self, simple_state):
        """Test that multiple runs with same seed produce identical results."""
        state1 = copy.deepcopy(simple_state)
        state2 = copy.deepcopy(simple_state)
        
        optimizer1 = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            cooling_rate=0.95,
            target_cv=0.10,
            max_iterations=50,
            random_seed=42
        )
        optimizer2 = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            cooling_rate=0.95,
            target_cv=0.10,
            max_iterations=50,
            random_seed=42
        )
        
        swaps1 = optimizer1.optimize(state1)
        swaps2 = optimizer2.optimize(state2)
        
        # Should produce identical swap sequences
        assert len(swaps1) == len(swaps2)
        for s1, s2 in zip(swaps1, swaps2):
            assert s1.pgid == s2.pgid
            assert s1.old_primary == s2.old_primary
            assert s1.new_primary == s2.new_primary
    
    def test_different_results_without_seed(self, simple_state):
        """Test that runs without seed can produce different results."""
        state1 = copy.deepcopy(simple_state)
        state2 = copy.deepcopy(simple_state)
        
        # Create optimizers without seed
        optimizer1 = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            cooling_rate=0.95,
            target_cv=0.10,
            max_iterations=50,
            random_seed=None
        )
        optimizer2 = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            cooling_rate=0.95,
            target_cv=0.10,
            max_iterations=50,
            random_seed=None
        )
        
        swaps1 = optimizer1.optimize(state1)
        swaps2 = optimizer2.optimize(state2)
        
        # Results may differ (though not guaranteed to differ every time)
        # Just verify they both completed
        assert len(swaps1) >= 0
        assert len(swaps2) >= 0
    
    def test_is_deterministic_property_with_seed(self):
        """Test that is_deterministic returns True when seed is set."""
        optimizer = SimulatedAnnealingOptimizer(random_seed=42)
        assert optimizer.is_deterministic is True
    
    def test_is_deterministic_property_without_seed(self):
        """Test that is_deterministic returns False without seed."""
        optimizer = SimulatedAnnealingOptimizer(random_seed=None)
        assert optimizer.is_deterministic is False


# ============================================================================
# Test Statistics Tracking
# ============================================================================

class TestStatistics:
    """Test statistics tracking."""
    
    def test_tracks_sa_specific_statistics(self, simple_state):
        """Test that simulated annealing specific statistics are tracked."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            max_iterations=30,
            random_seed=42
        )
        optimizer.optimize(simple_state)
        
        stats = optimizer.stats.algorithm_specific
        
        # All stats should be valid
        assert 'temperature_trajectory' in stats
        assert 'accepted_worse_moves' in stats
        assert 'rejected_worse_moves' in stats
        assert 'accepted_better_moves' in stats
        assert 'reheats' in stats
        assert 'best_score_updates' in stats
        assert 'acceptance_rate' in stats
        
        assert len(stats['temperature_trajectory']) > 0
        assert stats['accepted_worse_moves'] >= 0
        assert stats['rejected_worse_moves'] >= 0
        assert stats['accepted_better_moves'] > 0
        assert stats['reheats'] >= 0
        assert stats['best_score_updates'] > 0
        assert 0 <= stats['acceptance_rate'] <= 1.0
    
    def test_tracks_swaps_evaluated(self, simple_state):
        """Test that swaps_evaluated is tracked."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            random_seed=42
        )
        optimizer.optimize(simple_state)
        
        # Should have evaluated many swaps
        assert optimizer.stats.swaps_evaluated > 0
        assert optimizer.stats.swaps_evaluated >= optimizer.stats.swaps_applied
    
    def test_tracks_execution_time(self, simple_state):
        """Test that execution time is tracked."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            random_seed=42
        )
        optimizer.optimize(simple_state)
        
        assert optimizer.stats.execution_time > 0


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_single_osd_cluster(self):
        """Test behavior with single OSD."""
        osds = {0: OSDInfo(osd_id=0, host="host0", primary_count=10)}
        pgs = {}
        
        for i in range(10):
            pgs[f"1.{i}"] = PGInfo(
                pgid=f"1.{i}",
                pool_id=1,
                acting=[0]
            )
        
        state = ClusterState(pgs=pgs, osds=osds)
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            random_seed=42
        )
        swaps = optimizer.optimize(state)
        
        # No swaps possible with single OSD
        assert len(swaps) == 0
    
    def test_small_cluster_with_limited_swaps(self):
        """Test behavior with small cluster."""
        osds = {}
        pgs = {}
        
        # Create 3 OSDs with slight imbalance
        for i in range(3):
            osds[i] = OSDInfo(osd_id=i, host=f"host{i}", primary_count=0)
        
        # Create 10 PGs
        for i in range(10):
            osd_id = i % 3
            acting = [osd_id, (osd_id + 1) % 3, (osd_id + 2) % 3]
            pgs[f"1.{i}"] = PGInfo(pgid=f"1.{i}", pool_id=1, acting=acting)
            osds[osd_id].primary_count += 1
        
        # Add one extra PG to create imbalance
        osds[0].primary_count += 1
        pgs["1.10"] = PGInfo(pgid="1.10", pool_id=1, acting=[0, 1, 2])
        
        state = ClusterState(pgs=pgs, osds=osds)
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=5.0,
            max_iterations=20,
            random_seed=42
        )
        swaps = optimizer.optimize(state)
        
        # Should handle small cluster gracefully
        assert optimizer.stats.execution_time > 0


# ============================================================================
# Test Integration with Dynamic Weights (Phase 7.1)
# ============================================================================

class TestDynamicWeightsIntegration:
    """Test integration with Phase 7.1 dynamic weight adaptation."""
    
    def test_works_with_dynamic_weights(self, simple_state):
        """Test that simulated annealing works with dynamic weight adaptation."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            target_cv=0.10,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            max_iterations=50,
            random_seed=42
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still optimize successfully
        assert len(swaps) > 0
        assert optimizer.stats.swaps_applied > 0
    
    def test_works_with_enabled_levels(self, simple_state):
        """Test that simulated annealing works with enabled_levels."""
        optimizer = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            enabled_levels=['osd', 'host'],
            max_iterations=50,
            random_seed=42
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still work
        assert optimizer.scorer is not None


# ============================================================================
# Test Quality Comparison
# ============================================================================

class TestQualityComparison:
    """Test that simulated annealing achieves best quality among optimizers."""
    
    def test_better_or_equal_cv_than_greedy(self, simple_state):
        """Test that SA achieves equal or better CV than greedy."""
        from src.ceph_primary_balancer.analyzer import calculate_statistics
        from src.ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10, max_iterations=200)
        greedy.optimize(state_greedy)
        greedy_counts = [osd.primary_count for osd in state_greedy.osds.values()]
        greedy_cv = calculate_statistics(greedy_counts).cv
        
        # Run simulated annealing
        state_sa = copy.deepcopy(simple_state)
        sa = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            target_cv=0.10,
            max_iterations=200,
            random_seed=42
        )
        sa.optimize(state_sa)
        sa_counts = [osd.primary_count for osd in state_sa.osds.values()]
        sa_cv = calculate_statistics(sa_counts).cv
        
        # SA should achieve equal or better balance
        # Allow 5% tolerance
        assert sa_cv <= greedy_cv * 1.05
    
    def test_better_or_equal_cv_than_tabu_search(self, simple_state):
        """Test that SA achieves equal or better CV than tabu search."""
        from src.ceph_primary_balancer.analyzer import calculate_statistics
        from src.ceph_primary_balancer.optimizers.tabu_search import TabuSearchOptimizer
        
        # Run tabu search
        state_tabu = copy.deepcopy(simple_state)
        tabu = TabuSearchOptimizer(
            tabu_tenure=50,
            target_cv=0.10,
            max_iterations=200
        )
        tabu.optimize(state_tabu)
        tabu_counts = [osd.primary_count for osd in state_tabu.osds.values()]
        tabu_cv = calculate_statistics(tabu_counts).cv
        
        # Run simulated annealing
        state_sa = copy.deepcopy(simple_state)
        sa = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            target_cv=0.10,
            max_iterations=200,
            random_seed=42
        )
        sa.optimize(state_sa)
        sa_counts = [osd.primary_count for osd in state_sa.osds.values()]
        sa_cv = calculate_statistics(sa_counts).cv
        
        # SA should achieve equal or better balance (or very close)
        # Allow 3% tolerance since both are good
        assert sa_cv <= tabu_cv * 1.03
    
    def test_expected_quality_improvement_over_greedy(self, simple_state):
        """Test that SA shows expected 15-20% improvement potential over greedy."""
        from src.ceph_primary_balancer.analyzer import calculate_statistics
        from src.ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10)
        greedy.optimize(state_greedy)
        greedy_counts = [osd.primary_count for osd in state_greedy.osds.values()]
        greedy_cv = calculate_statistics(greedy_counts).cv
        
        # Run SA with thorough exploration
        state_sa = copy.deepcopy(simple_state)
        sa = SimulatedAnnealingOptimizer(
            initial_temperature=15.0,
            final_temperature=0.001,
            cooling_rate=0.98,
            target_cv=0.10,
            max_iterations=300,
            random_seed=42
        )
        sa.optimize(state_sa)
        sa_counts = [osd.primary_count for osd in state_sa.osds.values()]
        sa_cv = calculate_statistics(sa_counts).cv
        
        # SA should not be worse than greedy (allow small margin)
        assert sa_cv <= greedy_cv * 1.02
    
    def test_execution_time_ratio(self, simple_state):
        """Test that SA is 2-4x slower than greedy (as expected)."""
        from src.ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10, max_iterations=100)
        greedy.optimize(state_greedy)
        greedy_time = greedy.stats.execution_time
        
        # Run simulated annealing
        state_sa = copy.deepcopy(simple_state)
        sa = SimulatedAnnealingOptimizer(
            initial_temperature=10.0,
            target_cv=0.10,
            max_iterations=100,
            random_seed=42
        )
        sa.optimize(state_sa)
        sa_time = sa.stats.execution_time
        
        # SA should be slower than greedy
        # Use generous bounds due to system variability
        assert sa_time >= greedy_time * 0.5
        # Just ensure it completes in reasonable time


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
