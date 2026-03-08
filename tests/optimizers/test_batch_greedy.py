"""
Tests for Batch Greedy Optimizer.

Tests cover:
- Initialization and parameter validation
- Batch swap selection logic
- Conflict detection (strict and relaxed modes)
- Determinism verification
- Integration with base class
- Performance characteristics
- Edge cases
"""

import pytest
import copy
from typing import List

from ceph_primary_balancer.optimizers.batch_greedy import BatchGreedyOptimizer
from ceph_primary_balancer.optimizers.base import OptimizerRegistry
from ceph_primary_balancer.models import ClusterState, OSDInfo, PGInfo, SwapProposal
from ceph_primary_balancer.scorer import Scorer


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope='module', autouse=True)
def register_optimizer():
    """Register BatchGreedyOptimizer for testing."""
    from ceph_primary_balancer.optimizers import OptimizerRegistry
    from ceph_primary_balancer.optimizers.batch_greedy import BatchGreedyOptimizer
    OptimizerRegistry.register('batch_greedy', BatchGreedyOptimizer)
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
# Test BatchGreedyOptimizer Initialization
# ============================================================================

class TestBatchGreedyInitialization:
    """Test BatchGreedyOptimizer initialization and validation."""
    
    def test_default_initialization(self):
        """Test default parameter values."""
        optimizer = BatchGreedyOptimizer()
        assert optimizer.batch_size == 10
        assert optimizer.conflict_detection == 'strict'
        assert optimizer.target_cv == 0.10
        assert optimizer.algorithm_name == "Batch Greedy (batch_size=10, mode=strict)"
        assert optimizer.is_deterministic is True
    
    def test_custom_batch_size(self):
        """Test custom batch size."""
        optimizer = BatchGreedyOptimizer(batch_size=20)
        assert optimizer.batch_size == 20
        assert optimizer.algorithm_name == "Batch Greedy (batch_size=20, mode=strict)"
    
    def test_relaxed_conflict_detection(self):
        """Test relaxed conflict detection mode."""
        optimizer = BatchGreedyOptimizer(conflict_detection='relaxed')
        assert optimizer.conflict_detection == 'relaxed'
        assert optimizer.algorithm_name == "Batch Greedy (batch_size=10, mode=relaxed)"
    
    def test_invalid_batch_size(self):
        """Test that invalid batch size raises error."""
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            BatchGreedyOptimizer(batch_size=0)
        
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            BatchGreedyOptimizer(batch_size=-5)
    
    def test_invalid_conflict_detection(self):
        """Test that invalid conflict detection mode raises error."""
        with pytest.raises(ValueError, match="conflict_detection must be 'strict' or 'relaxed'"):
            BatchGreedyOptimizer(conflict_detection='invalid')
    
    def test_algorithm_specific_stats_initialized(self):
        """Test that algorithm-specific statistics are initialized."""
        optimizer = BatchGreedyOptimizer()
        assert 'batches_applied' in optimizer.stats.algorithm_specific
        assert 'avg_batch_size' in optimizer.stats.algorithm_specific
        assert 'conflicts_detected' in optimizer.stats.algorithm_specific
        assert optimizer.stats.algorithm_specific['batches_applied'] == 0
        assert optimizer.stats.algorithm_specific['avg_batch_size'] == 0.0
        assert optimizer.stats.algorithm_specific['conflicts_detected'] == 0


# ============================================================================
# Test Registry Integration
# ============================================================================

class TestRegistryIntegration:
    """Test integration with OptimizerRegistry."""
    
    def test_registry_has_batch_greedy(self):
        """Test that batch_greedy is registered."""
        algorithms = OptimizerRegistry.list_algorithms()
        assert 'batch_greedy' in algorithms
    
    def test_get_batch_greedy_from_registry(self):
        """Test getting BatchGreedyOptimizer from registry."""
        optimizer = OptimizerRegistry.get_optimizer('batch_greedy', target_cv=0.08)
        assert isinstance(optimizer, BatchGreedyOptimizer)
        assert optimizer.target_cv == 0.08
    
    def test_get_batch_greedy_with_custom_params(self):
        """Test getting BatchGreedyOptimizer with custom parameters."""
        optimizer = OptimizerRegistry.get_optimizer(
            'batch_greedy',
            batch_size=15,
            conflict_detection='relaxed',
            target_cv=0.12
        )
        assert optimizer.batch_size == 15
        assert optimizer.conflict_detection == 'relaxed'
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
        
        optimizer = BatchGreedyOptimizer(target_cv=0.10, batch_size=5)
        swaps = optimizer.optimize(simple_state)
        
        final_counts = [osd.primary_count for osd in simple_state.osds.values()]
        final_stats = calculate_statistics(final_counts)
        
        # Should improve balance
        assert final_stats.cv < initial_stats.cv
        assert len(swaps) > 0
        assert optimizer.stats.swaps_applied == len(swaps)
    
    def test_terminates_at_target_cv(self, simple_state):
        """Test that optimizer stops at target CV."""
        from ceph_primary_balancer.analyzer import calculate_statistics
        
        optimizer = BatchGreedyOptimizer(target_cv=0.15, batch_size=10)
        optimizer.optimize(simple_state)
        
        final_counts = [osd.primary_count for osd in simple_state.osds.values()]
        final_stats = calculate_statistics(final_counts)
        
        # Should reach target (or get close)
        assert final_stats.cv <= 0.16  # Allow small margin
    
    def test_no_swaps_on_balanced_cluster(self, balanced_state):
        """Test that optimizer doesn't swap on balanced cluster."""
        optimizer = BatchGreedyOptimizer(target_cv=0.10)
        swaps = optimizer.optimize(balanced_state)
        
        # Should recognize it's already balanced
        assert len(swaps) == 0
    
    def test_respects_max_iterations(self, simple_state):
        """Test that optimizer respects max_iterations."""
        optimizer = BatchGreedyOptimizer(
            target_cv=0.01,  # Very aggressive target
            max_iterations=5,
            batch_size=3
        )
        optimizer.optimize(simple_state)
        
        # Should stop at max_iterations
        assert optimizer.stats.iterations <= 5


# ============================================================================
# Test Batch Selection Logic
# ============================================================================

class TestBatchSelection:
    """Test batch swap selection and conflict detection."""
    
    def test_finds_multiple_swaps(self, simple_state):
        """Test that _find_top_swaps returns multiple candidates."""
        optimizer = BatchGreedyOptimizer(batch_size=10)
        candidates = optimizer._find_top_swaps(simple_state, count=10)
        
        # Should find multiple beneficial swaps
        assert len(candidates) > 1
        
        # Should be sorted by improvement (best first)
        for i in range(len(candidates) - 1):
            assert candidates[i].score_improvement >= candidates[i + 1].score_improvement
    
    def test_respects_batch_size_limit(self, simple_state):
        """Test that _find_top_swaps respects count limit."""
        optimizer = BatchGreedyOptimizer(batch_size=5)
        candidates = optimizer._find_top_swaps(simple_state, count=5)
        
        assert len(candidates) <= 5
    
    def test_strict_conflict_detection_no_osd_reuse(self, simple_state):
        """Test strict mode prevents OSD reuse."""
        optimizer = BatchGreedyOptimizer(conflict_detection='strict')
        
        # Create conflicting swaps (same OSD)
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0),
            SwapProposal(pgid="1.1", old_primary=0, new_primary=6, score_improvement=9.0),  # Conflict: OSD 0
            SwapProposal(pgid="1.2", old_primary=1, new_primary=5, score_improvement=8.0),  # Conflict: OSD 5
            SwapProposal(pgid="1.3", old_primary=2, new_primary=7, score_improvement=7.0),  # OK
        ]
        
        batch = optimizer._select_non_conflicting_batch(candidates)
        
        # Should select first and fourth (non-conflicting)
        assert len(batch) == 2
        assert batch[0].pgid == "1.0"
        assert batch[1].pgid == "1.3"
    
    def test_strict_conflict_detection_no_pg_reuse(self, simple_state):
        """Test strict mode prevents PG reuse."""
        optimizer = BatchGreedyOptimizer(conflict_detection='strict')
        
        # Create conflicting swaps (same PG)
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0),
            SwapProposal(pgid="1.0", old_primary=0, new_primary=6, score_improvement=9.0),  # Conflict: PG 1.0
            SwapProposal(pgid="1.1", old_primary=1, new_primary=7, score_improvement=8.0),  # OK
        ]
        
        batch = optimizer._select_non_conflicting_batch(candidates)
        
        # Should select first and third (non-conflicting)
        assert len(batch) == 2
        assert batch[0].pgid == "1.0"
        assert batch[1].pgid == "1.1"
    
    def test_relaxed_conflict_detection_allows_osd_reuse(self, simple_state):
        """Test relaxed mode allows OSD reuse but not PG reuse."""
        optimizer = BatchGreedyOptimizer(conflict_detection='relaxed')
        
        # Create swaps with OSD reuse but different PGs
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0),
            SwapProposal(pgid="1.1", old_primary=0, new_primary=6, score_improvement=9.0),  # Same OSD 0, different PG
            SwapProposal(pgid="1.2", old_primary=1, new_primary=5, score_improvement=8.0),  # Same OSD 5, different PG
        ]
        
        batch = optimizer._select_non_conflicting_batch(candidates)
        
        # Should select all three (OSD reuse allowed in relaxed mode)
        assert len(batch) == 3
    
    def test_relaxed_conflict_detection_prevents_pg_reuse(self, simple_state):
        """Test relaxed mode still prevents PG reuse."""
        optimizer = BatchGreedyOptimizer(conflict_detection='relaxed')
        
        # Create swaps with PG reuse
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0),
            SwapProposal(pgid="1.0", old_primary=0, new_primary=6, score_improvement=9.0),  # Same PG
            SwapProposal(pgid="1.1", old_primary=1, new_primary=7, score_improvement=8.0),  # OK
        ]
        
        batch = optimizer._select_non_conflicting_batch(candidates)
        
        # Should select first and third (PG reuse forbidden)
        assert len(batch) == 2
        assert batch[0].pgid == "1.0"
        assert batch[1].pgid == "1.1"
    
    def test_conflict_statistics_tracked(self, simple_state):
        """Test that conflicts are tracked in statistics."""
        optimizer = BatchGreedyOptimizer(conflict_detection='strict')
        
        # Create conflicting swaps
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0),
            SwapProposal(pgid="1.1", old_primary=0, new_primary=6, score_improvement=9.0),  # Conflict
            SwapProposal(pgid="1.2", old_primary=1, new_primary=5, score_improvement=8.0),  # Conflict
        ]
        
        initial_conflicts = optimizer.stats.algorithm_specific['conflicts_detected']
        optimizer._select_non_conflicting_batch(candidates)
        final_conflicts = optimizer.stats.algorithm_specific['conflicts_detected']
        
        # Should have detected 2 conflicts
        assert final_conflicts - initial_conflicts == 2


# ============================================================================
# Test Determinism
# ============================================================================

class TestDeterminism:
    """Test that batch greedy is deterministic."""
    
    def test_produces_same_results(self, simple_state):
        """Test that multiple runs produce identical results."""
        state1 = copy.deepcopy(simple_state)
        state2 = copy.deepcopy(simple_state)
        
        optimizer1 = BatchGreedyOptimizer(batch_size=10, target_cv=0.10)
        optimizer2 = BatchGreedyOptimizer(batch_size=10, target_cv=0.10)
        
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
        optimizer = BatchGreedyOptimizer()
        assert optimizer.is_deterministic is True


# ============================================================================
# Test Statistics Tracking
# ============================================================================

class TestStatistics:
    """Test statistics tracking."""
    
    def test_tracks_batch_statistics(self, simple_state):
        """Test that batch-specific statistics are tracked."""
        optimizer = BatchGreedyOptimizer(batch_size=5)
        optimizer.optimize(simple_state)
        
        stats = optimizer.stats.algorithm_specific
        
        # Should have applied at least one batch
        assert stats['batches_applied'] > 0
        
        # Average batch size should be reasonable
        assert stats['avg_batch_size'] > 0
        assert stats['avg_batch_size'] <= 5  # Can't exceed batch_size limit
    
    def test_tracks_swaps_evaluated(self, simple_state):
        """Test that swaps_evaluated is tracked."""
        optimizer = BatchGreedyOptimizer(batch_size=10)
        optimizer.optimize(simple_state)
        
        # Should have evaluated many swaps
        assert optimizer.stats.swaps_evaluated > 0
        assert optimizer.stats.swaps_evaluated >= optimizer.stats.swaps_applied
    
    def test_tracks_execution_time(self, simple_state):
        """Test that execution time is tracked."""
        optimizer = BatchGreedyOptimizer()
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
        optimizer = BatchGreedyOptimizer()
        swaps = optimizer.optimize(state)
        
        # No swaps possible with single OSD
        assert len(swaps) == 0
    
    def test_empty_candidate_list(self, simple_state):
        """Test _select_non_conflicting_batch with empty list."""
        optimizer = BatchGreedyOptimizer()
        batch = optimizer._select_non_conflicting_batch([])
        
        assert batch == []
    
    def test_single_candidate(self, simple_state):
        """Test _select_non_conflicting_batch with single candidate."""
        optimizer = BatchGreedyOptimizer()
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0)
        ]
        batch = optimizer._select_non_conflicting_batch(candidates)
        
        assert len(batch) == 1
        assert batch[0].pgid == "1.0"
    
    def test_all_conflicting_candidates(self, simple_state):
        """Test when all candidates conflict after first."""
        optimizer = BatchGreedyOptimizer(conflict_detection='strict')
        
        # All use same OSD
        candidates = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=5, score_improvement=10.0),
            SwapProposal(pgid="1.1", old_primary=0, new_primary=6, score_improvement=9.0),
            SwapProposal(pgid="1.2", old_primary=0, new_primary=7, score_improvement=8.0),
        ]
        batch = optimizer._select_non_conflicting_batch(candidates)
        
        # Should only select first
        assert len(batch) == 1
        assert batch[0].pgid == "1.0"


# ============================================================================
# Test Integration with Dynamic Weights (Phase 7.1)
# ============================================================================

class TestDynamicWeightsIntegration:
    """Test integration with Phase 7.1 dynamic weight adaptation."""
    
    def test_works_with_dynamic_weights(self, simple_state):
        """Test that batch greedy works with dynamic weight adaptation."""
        optimizer = BatchGreedyOptimizer(
            batch_size=5,
            target_cv=0.10,
            dynamic_weights=True,
            dynamic_strategy='target_distance'
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still optimize successfully
        assert len(swaps) > 0
        assert optimizer.stats.swaps_applied > 0
    
    def test_works_with_enabled_levels(self, simple_state):
        """Test that batch greedy works with enabled_levels."""
        optimizer = BatchGreedyOptimizer(
            batch_size=5,
            enabled_levels=['osd', 'host']
        )
        
        swaps = optimizer.optimize(simple_state)
        
        # Should still work
        assert optimizer.scorer is not None


# ============================================================================
# Test Comparison with Greedy
# ============================================================================

class TestGreedyComparison:
    """Test that batch greedy has similar quality to standard greedy."""
    
    def test_similar_final_cv(self, simple_state):
        """Test that final CV is similar to greedy."""
        from ceph_primary_balancer.analyzer import calculate_statistics
        from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10)
        greedy.optimize(state_greedy)
        greedy_counts = [osd.primary_count for osd in state_greedy.osds.values()]
        greedy_cv = calculate_statistics(greedy_counts).cv
        
        # Run batch greedy
        state_batch = copy.deepcopy(simple_state)
        batch = BatchGreedyOptimizer(target_cv=0.10, batch_size=10)
        batch.optimize(state_batch)
        batch_counts = [osd.primary_count for osd in state_batch.osds.values()]
        batch_cv = calculate_statistics(batch_counts).cv
        
        # Should achieve similar quality (within 5%)
        assert abs(batch_cv - greedy_cv) / greedy_cv < 0.05
    
    def test_fewer_iterations(self, simple_state):
        """Test that batch greedy uses fewer iterations (but more swaps per iteration)."""
        from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
        
        # Run greedy
        state_greedy = copy.deepcopy(simple_state)
        greedy = GreedyOptimizer(target_cv=0.10)
        greedy.optimize(state_greedy)
        
        # Run batch greedy
        state_batch = copy.deepcopy(simple_state)
        batch = BatchGreedyOptimizer(target_cv=0.10, batch_size=10)
        batch.optimize(state_batch)
        
        # Batch greedy should use fewer iterations
        # (but similar or slightly fewer total swaps due to parallelism)
        assert batch.stats.iterations <= greedy.stats.iterations


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
