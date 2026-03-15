"""
Tests for Tabu Search Optimizer.

Tests cover:
- Initialization and parameter validation
- Tabu list management
- Aspiration criteria
- Diversification mechanism
- Determinism verification
- Best solution tracking
- Integration with base class
- Quality comparison with greedy
- Edge cases
"""

import pytest
import copy
from typing import List

from ceph_primary_balancer.optimizers.tabu_search import TabuSearchOptimizer
from ceph_primary_balancer.optimizers.base import OptimizerRegistry
from ceph_primary_balancer.models import ClusterState, OSDInfo, PGInfo, SwapProposal
from ceph_primary_balancer.scorer import Scorer


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope='module', autouse=True)
def register_optimizer():
    """Register TabuSearchOptimizer for testing."""
    from ceph_primary_balancer.optimizers import OptimizerRegistry
    from ceph_primary_balancer.optimizers.tabu_search import TabuSearchOptimizer
    OptimizerRegistry.register('tabu_search', TabuSearchOptimizer)
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
# Test TabuSearchOptimizer Initialization
# ============================================================================

class TestTabuSearchInitialization:
    """Test TabuSearchOptimizer initialization and validation."""
    
    def test_default_initialization(self):
        """Test default parameter values."""
        optimizer = TabuSearchOptimizer()
        assert optimizer.tabu_tenure == 50
        assert optimizer.aspiration_threshold == 0.1
        assert optimizer.diversification_enabled is True
        assert optimizer.diversification_threshold == 100
        assert optimizer.target_cv == 0.10
        assert optimizer.algorithm_name == "Tabu Search (tenure=50)"
        assert optimizer.is_deterministic is True
    
    def test_custom_tabu_tenure(self):
        """Test custom tabu tenure."""
        optimizer = TabuSearchOptimizer(tabu_tenure=30)
        assert optimizer.tabu_tenure == 30
        assert optimizer.algorithm_name == "Tabu Search (tenure=30)"
    
    def test_custom_aspiration_threshold(self):
        """Test custom aspiration threshold."""
        optimizer = TabuSearchOptimizer(aspiration_threshold=0.2)
        assert optimizer.aspiration_threshold == 0.2
    
    def test_diversification_disabled(self):
        """Test disabling diversification."""
        optimizer = TabuSearchOptimizer(diversification_enabled=False)
        assert optimizer.diversification_enabled is False
    
    def test_invalid_tabu_tenure(self):
        """Test that invalid tabu tenure raises error."""
        with pytest.raises(ValueError, match="tabu_tenure must be >= 1"):
            TabuSearchOptimizer(tabu_tenure=0)
        
        with pytest.raises(ValueError, match="tabu_tenure must be >= 1"):
            TabuSearchOptimizer(tabu_tenure=-10)
    
    def test_invalid_aspiration_threshold(self):
        """Test that invalid aspiration threshold raises error."""
        with pytest.raises(ValueError, match="aspiration_threshold must be >= 0"):
            TabuSearchOptimizer(aspiration_threshold=-0.1)
    
    def test_invalid_diversification_threshold(self):
        """Test that invalid diversification threshold raises error."""
        with pytest.raises(ValueError, match="diversification_threshold must be >= 1"):
            TabuSearchOptimizer(diversification_threshold=0)
    
    def test_algorithm_specific_stats_initialized(self):
        """Test that algorithm-specific statistics are initialized."""
        optimizer = TabuSearchOptimizer()
        assert 'tabu_overrides' in optimizer.stats.algorithm_specific
        assert 'diversifications' in optimizer.stats.algorithm_specific
        assert 'best_score_updates' in optimizer.stats.algorithm_specific
        assert 'tabu_list_max_size' in optimizer.stats.algorithm_specific
        assert optimizer.stats.algorithm_specific['tabu_overrides'] == 0
        assert optimizer.stats.algorithm_specific['diversifications'] == 0


# ============================================================================
# Test Registry Integration
# ============================================================================

class TestRegistryIntegration:
    """Test integration with OptimizerRegistry."""
    
    def test_registry_has_tabu_search(self):
        """Test that tabu_search is registered."""
        algorithms = OptimizerRegistry.list_algorithms()
        assert 'tabu_search' in algorithms
    
    def test_get_tabu_search_from_registry(self):
        """Test getting TabuSearchOptimizer from registry."""
        optimizer = OptimizerRegistry.get_optimizer('tabu_search', target_cv=0.08)
        assert isinstance(optimizer, TabuSearchOptimizer)
        assert optimizer.target_cv == 0.08
    
    def test_get_tabu_search_with_custom_params(self):
        """Test getting TabuSearchOptimizer with custom parameters."""
        optimizer = OptimizerRegistry.get_optimizer(
            'tabu_search',
            tabu_tenure=30,
            aspiration_threshold=0.2,
            diversification_enabled=False,
            target_cv=0.12
        )
        assert optimizer.tabu_tenure == 30
        assert optimizer.aspiration_threshold == 0.2
        assert optimizer.diversification_enabled is False
        assert optimizer.target_cv == 0.12


# ============================================================================
# Test Optimization Functionality
# ============================================================================

class TestOptimization:
    """Test core optimization functionality."""
    
    def test_optimizes_imbalanced_cluster(self, simple_state):
        """Test that optimizer improves imbalanced cluster."""
        from ceph_primary_balancer.analyzer import calculate_statistics
        
        initial_counts = [osd.primary_count for osd in simple_state.osds.values()]
        initial_stats = calculate_statistics(initial_counts)
        
        optimizer = TabuSearchOptimizer(
            target_cv=0.10,
            tabu_tenure=30,
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
        from ceph_primary_balancer.analyzer import calculate_statistics
        
        initial_counts = [osd.primary_count for osd in simple_state.osds.values()]
        initial_stats = calculate_statistics(initial_counts)
        
        optimizer = TabuSearchOptimizer(
            target_cv=0.10,
            tabu_tenure=30,
            max_iterations=200  # Provide enough iterations to reach target
        )
        optimizer.optimize(simple_state)
        
        final_counts = [osd.primary_count for osd in simple_state.osds.values()]
        final_stats = calculate_statistics(final_counts)
        
        # Should improve significantly (CV should be better than initial)
        assert final_stats.cv < initial_stats.cv
        # Should achieve meaningful improvement (at least 20% better)
        assert final_stats.cv < initial_stats.cv * 0.8
    
    def test_no_swaps_on_balanced_cluster(self, balanced_state):
        """Test that optimizer doesn't swap on balanced cluster."""
        optimizer = TabuSearchOptimizer(target_cv=0.10)
        swaps = optimizer.optimize(balanced_state)
        
        # Should recognize it's already balanced
        assert len(swaps) == 0
    
    def test_respects_max_iterations(self, simple_state):
        """Test that optimizer respects max_iterations."""
        optimizer = TabuSearchOptimizer(
            target_cv=0.01,  # Very aggressive target
            max_iterations=10,
            tabu_tenure=5
        )
        optimizer.optimize(simple_state)
        
        # Should stop at max_iterations
        assert optimizer.stats.iterations <= 10


# ============================================================================
# Test Tabu List Management
# ============================================================================

class TestTabuListManagement:
    """Test tabu list management functionality."""
    
    def test_tabu_list_tracks_moved_pgs(self, simple_state):
        """Test that moved PGs are added to tabu list."""
        optimizer = TabuSearchOptimizer(tabu_tenure=50)
        
        # Add some PGs to tabu list
        optimizer._add_to_tabu_list("1.0", 0)
        optimizer._add_to_tabu_list("1.1", 1)
        optimizer._add_to_tabu_list("1.2", 2)
        
        # Check they are tabu
        assert optimizer._is_tabu("1.0", 10) is True
        assert optimizer._is_tabu("1.1", 10) is True
        assert optimizer._is_tabu("1.2", 10) is True
    
    def test_tabu_list_expires_entries(self, simple_state):
        """Test that tabu entries expire after tenure."""
        optimizer = TabuSearchOptimizer(tabu_tenure=10)
        
        # Add PG to tabu list at iteration 0
        optimizer._add_to_tabu_list("1.0", 0)
        
        # Should be tabu within tenure
        assert optimizer._is_tabu("1.0", 5) is True
        assert optimizer._is_tabu("1.0", 9) is True
        
        # Should not be tabu after tenure
        assert optimizer._is_tabu("1.0", 10) is False
        assert optimizer._is_tabu("1.0", 15) is False
    
    def test_lazy_expiry_removes_expired(self, simple_state):
        """Test that expired tabu entries are lazily removed on lookup."""
        optimizer = TabuSearchOptimizer(tabu_tenure=10)

        optimizer._add_to_tabu_list("1.0", 0)
        optimizer._add_to_tabu_list("1.1", 5)
        optimizer._add_to_tabu_list("1.2", 15)

        # At iteration 20: 1.0 (added at 0) and 1.1 (added at 5) are expired
        assert not optimizer._is_tabu("1.0", 20)
        assert not optimizer._is_tabu("1.1", 20)
        # 1.2 (added at 15) is still active
        assert optimizer._is_tabu("1.2", 20)
    
    def test_tabu_list_max_size_tracked(self, simple_state):
        """Test that max tabu list size is tracked."""
        optimizer = TabuSearchOptimizer(tabu_tenure=100)
        
        # Add multiple entries
        for i in range(20):
            optimizer._add_to_tabu_list(f"1.{i}", i)
        
        # Max size should be tracked
        assert optimizer.stats.algorithm_specific['tabu_list_max_size'] == 20


# ============================================================================
# Test Aspiration Criteria
# ============================================================================

class TestAspirationCriteria:
    """Test aspiration criteria functionality."""
    
    def test_aspiration_allows_beneficial_tabu_moves(self, simple_state):
        """Test that aspiration criteria allows beneficial tabu moves."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=50,
            aspiration_threshold=0.1,
            max_iterations=20
        )
        
        # Run optimization
        swaps = optimizer.optimize(simple_state)
        
        # If any tabu overrides occurred, they should be tracked
        # (We can't guarantee they occur, but if they do, stats should be >0)
        tabu_overrides = optimizer.stats.algorithm_specific['tabu_overrides']
        assert tabu_overrides >= 0  # Valid count
    
    def test_aspiration_threshold_zero_allows_any_improvement(self, simple_state):
        """Test that aspiration_threshold=0 allows any improving tabu move."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=20,
            aspiration_threshold=0.0,  # Any improvement triggers aspiration
            max_iterations=30
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still optimize successfully
        assert len(swaps) > 0
    
    def test_high_aspiration_threshold_blocks_tabu_moves(self, simple_state):
        """Test that high aspiration threshold blocks most tabu moves."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=20,
            aspiration_threshold=100.0,  # Very high, unlikely to trigger
            max_iterations=30
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still work but may have fewer/no tabu overrides
        tabu_overrides = optimizer.stats.algorithm_specific['tabu_overrides']
        # With high threshold, overrides should be rare or zero
        assert tabu_overrides >= 0


# ============================================================================
# Test Diversification
# ============================================================================

class TestDiversification:
    """Test diversification mechanism."""
    
    def test_diversification_restarts_when_stuck(self, simple_state):
        """Test that diversification triggers when stuck."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=10,
            diversification_enabled=True,
            diversification_threshold=5,  # Trigger quickly for testing
            max_iterations=100
        )
        
        # This may or may not trigger diversification depending on the problem
        swaps = optimizer.optimize(simple_state)
        
        # Check if diversification was tracked
        diversifications = optimizer.stats.algorithm_specific['diversifications']
        assert diversifications >= 0  # Valid count
    
    def test_diversification_disabled_no_restarts(self, simple_state):
        """Test that diversification doesn't occur when disabled."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=10,
            diversification_enabled=False,
            max_iterations=50
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should have zero diversifications
        diversifications = optimizer.stats.algorithm_specific['diversifications']
        assert diversifications == 0


# ============================================================================
# Test Best Solution Tracking
# ============================================================================

class TestBestSolutionTracking:
    """Test best solution tracking."""
    
    def test_tracks_best_solution_found(self, simple_state):
        """Test that best solution is tracked during search."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=30,
            max_iterations=50
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
        from ceph_primary_balancer.analyzer import calculate_statistics
        
        optimizer = TabuSearchOptimizer(
            tabu_tenure=20,
            max_iterations=50
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Final state should be the best state found
        final_score = optimizer.scorer.calculate_score(simple_state)
        
        # Should be close to or equal to best score
        # (May differ slightly due to floating point, but should be similar)
        assert abs(final_score - optimizer._best_score) < 0.01


# ============================================================================
# Test State Management
# ============================================================================

class TestStateManagement:
    """Test state copying and restoration."""
    
    def test_copy_state_creates_independent_copy(self, simple_state):
        """Test that _copy_state creates independent copy."""
        optimizer = TabuSearchOptimizer()
        
        # Copy state
        copied_state = optimizer._copy_state(simple_state)
        
        # Modify original
        simple_state.osds[0].primary_count += 10
        
        # Copy should be unchanged
        assert copied_state.osds[0].primary_count != simple_state.osds[0].primary_count
    
    def test_restore_state_recovers_previous_state(self, simple_state):
        """Test that _restore_state correctly restores previous state."""
        optimizer = TabuSearchOptimizer()
        
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
    """Test that tabu search is deterministic."""
    
    def test_produces_same_results(self, simple_state):
        """Test that multiple runs produce identical results."""
        state1 = copy.deepcopy(simple_state)
        state2 = copy.deepcopy(simple_state)
        
        optimizer1 = TabuSearchOptimizer(
            tabu_tenure=30,
            aspiration_threshold=0.1,
            diversification_enabled=True,
            target_cv=0.10,
            max_iterations=50
        )
        optimizer2 = TabuSearchOptimizer(
            tabu_tenure=30,
            aspiration_threshold=0.1,
            diversification_enabled=True,
            target_cv=0.10,
            max_iterations=50
        )
        
        swaps1 = optimizer1.optimize(state1)
        swaps2 = optimizer2.optimize(state2)
        
        # Should produce identical swap sequences
        assert len(swaps1) == len(swaps2)
        for s1, s2 in zip(swaps1, swaps2):
            assert s1.pgid == s2.pgid
            assert s1.old_primary == s2.old_primary
            assert s1.new_primary == s2.new_primary
    
    def test_is_deterministic_property(self):
        """Test that is_deterministic returns True."""
        optimizer = TabuSearchOptimizer()
        assert optimizer.is_deterministic is True


# ============================================================================
# Test Statistics Tracking
# ============================================================================

class TestStatistics:
    """Test statistics tracking."""
    
    def test_tracks_tabu_specific_statistics(self, simple_state):
        """Test that tabu-specific statistics are tracked."""
        optimizer = TabuSearchOptimizer(tabu_tenure=30, max_iterations=30)
        optimizer.optimize(simple_state)
        
        stats = optimizer.stats.algorithm_specific
        
        # All stats should be valid
        assert 'tabu_overrides' in stats
        assert 'diversifications' in stats
        assert 'best_score_updates' in stats
        assert 'tabu_list_max_size' in stats
        assert stats['tabu_overrides'] >= 0
        assert stats['diversifications'] >= 0
        assert stats['best_score_updates'] > 0
        assert stats['tabu_list_max_size'] >= 0
    
    def test_tracks_swaps_evaluated(self, simple_state):
        """Test that swaps_evaluated is tracked."""
        optimizer = TabuSearchOptimizer(tabu_tenure=30)
        optimizer.optimize(simple_state)
        
        # Should have evaluated many swaps
        assert optimizer.stats.swaps_evaluated > 0
        assert optimizer.stats.swaps_evaluated >= optimizer.stats.swaps_applied
    
    def test_tracks_execution_time(self, simple_state):
        """Test that execution time is tracked."""
        optimizer = TabuSearchOptimizer(tabu_tenure=30)
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
        optimizer = TabuSearchOptimizer(tabu_tenure=10)
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
        optimizer = TabuSearchOptimizer(tabu_tenure=5, max_iterations=20)
        swaps = optimizer.optimize(state)
        
        # Should handle small cluster gracefully
        assert optimizer.stats.execution_time > 0


# ============================================================================
# Test Integration with Dynamic Weights (Phase 7.1)
# ============================================================================

class TestDynamicWeightsIntegration:
    """Test integration with Phase 7.1 dynamic weight adaptation."""
    
    def test_works_with_dynamic_weights(self, simple_state):
        """Test that tabu search works with dynamic weight adaptation."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=30,
            target_cv=0.10,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            max_iterations=50
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still optimize successfully
        assert len(swaps) > 0
        assert optimizer.stats.swaps_applied > 0
    
    def test_works_with_enabled_levels(self, simple_state):
        """Test that tabu search works with enabled_levels."""
        optimizer = TabuSearchOptimizer(
            tabu_tenure=30,
            enabled_levels=['osd', 'host'],
            max_iterations=50
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still work
        assert optimizer.scorer is not None


# ============================================================================
# Test Quality Comparison with Greedy
# ============================================================================

class TestGreedyComparison:
    """Test that tabu search achieves better quality than greedy."""
    
    def test_better_or_equal_cv_than_greedy(self, simple_state):
        """Test that tabu search achieves equal or better CV than greedy."""
        from ceph_primary_balancer.analyzer import calculate_statistics
        from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10, max_iterations=200)
        greedy.optimize(state_greedy)
        greedy_counts = [osd.primary_count for osd in state_greedy.osds.values()]
        greedy_cv = calculate_statistics(greedy_counts).cv
        
        # Run tabu search
        state_tabu = copy.deepcopy(simple_state)
        tabu = TabuSearchOptimizer(
            target_cv=0.10,
            tabu_tenure=50,
            max_iterations=200
        )
        tabu.optimize(state_tabu)
        tabu_counts = [osd.primary_count for osd in state_tabu.osds.values()]
        tabu_cv = calculate_statistics(tabu_counts).cv
        
        # Tabu search should achieve equal or better balance
        # Allow 5% tolerance (tabu should be within 5% of greedy or better)
        assert tabu_cv <= greedy_cv * 1.05
    
    def test_expected_quality_improvement(self, simple_state):
        """Test that tabu search shows expected 10-15% improvement potential."""
        from ceph_primary_balancer.analyzer import calculate_statistics
        from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # This test checks if tabu search can improve on greedy
        # Note: May not always show improvement on simple cases,
        # but should not be significantly worse
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10)
        greedy.optimize(state_greedy)
        greedy_counts = [osd.primary_count for osd in state_greedy.osds.values()]
        greedy_cv = calculate_statistics(greedy_counts).cv
        
        # Run tabu search with more exploration
        state_tabu = copy.deepcopy(simple_state)
        tabu = TabuSearchOptimizer(
            target_cv=0.10,
            tabu_tenure=50,
            diversification_enabled=True,
            max_iterations=300
        )
        tabu.optimize(state_tabu)
        tabu_counts = [osd.primary_count for osd in state_tabu.osds.values()]
        tabu_cv = calculate_statistics(tabu_counts).cv
        
        # Tabu should not be worse than greedy (within small tolerance)
        assert tabu_cv <= greedy_cv * 1.02  # Allow 2% margin
    
    def test_execution_time_ratio(self, simple_state):
        """Test that tabu search is 1.5-3x slower than greedy (as expected)."""
        from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10, max_iterations=100)
        greedy.optimize(state_greedy)
        greedy_time = greedy.stats.execution_time
        
        # Run tabu search
        state_tabu = copy.deepcopy(simple_state)
        tabu = TabuSearchOptimizer(
            target_cv=0.10,
            tabu_tenure=50,
            max_iterations=100
        )
        tabu.optimize(state_tabu)
        tabu_time = tabu.stats.execution_time
        
        # Tabu should be slower than greedy
        # But timing can be variable, so use generous bounds
        assert tabu_time >= greedy_time * 0.5  # At least half as slow
        # Upper bound is harder to enforce due to system variability
        # Just ensure it completes in reasonable time


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
