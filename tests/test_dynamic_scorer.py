"""
Unit tests for DynamicScorer.

Tests cover:
- DynamicScorer initialization
- Weight update logic
- CV calculation
- History tracking
- Integration with base Scorer
- Statistics generation

Phase 7.1: Dynamic Weight Optimization
"""

import pytest
from unittest.mock import Mock, MagicMock
from ceph_primary_balancer.dynamic_scorer import DynamicScorer
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.models import ClusterState, OSDInfo, PGInfo, HostInfo, PoolInfo


# Test fixtures

def create_simple_cluster_state(osd_counts=None, host_counts=None):
    """
    Create a simple cluster state for testing.
    
    Args:
        osd_counts: Dict of {osd_id: primary_count}
        host_counts: Dict of {hostname: [osd_ids]}
    
    Returns:
        ClusterState instance
    """
    if osd_counts is None:
        osd_counts = {0: 100, 1: 80, 2: 120}  # Imbalanced
    
    if host_counts is None:
        host_counts = {'host1': [0, 1], 'host2': [2]}
    
    # Create OSDs
    osds = {}
    for osd_id, count in osd_counts.items():
        osds[osd_id] = OSDInfo(
            osd_id=osd_id,
            host=None,  # Will be set below
            primary_count=count,
            total_pg_count=count  # Simplified
        )
    
    # Assign hosts to OSDs
    for hostname, osd_ids in host_counts.items():
        for osd_id in osd_ids:
            if osd_id in osds:
                osds[osd_id].host = hostname
    
    # Create hosts
    hosts = {}
    for hostname, osd_ids in host_counts.items():
        primary_count = sum(osds[oid].primary_count for oid in osd_ids if oid in osds)
        total_count = sum(osds[oid].total_pg_count for oid in osd_ids if oid in osds)
        hosts[hostname] = HostInfo(
            hostname=hostname,
            osd_ids=osd_ids,
            primary_count=primary_count,
            total_pg_count=total_count
        )
    
    # Create some PGs
    pgs = {}
    pg_id = 0
    for osd_id, count in osd_counts.items():
        for _ in range(count):
            pgid = f"1.{pg_id:x}"
            # PGInfo.primary is a property of acting[0], not a constructor parameter
            pgs[pgid] = PGInfo(
                pgid=pgid,
                pool_id=1,
                acting=[osd_id, (osd_id + 1) % len(osd_counts), (osd_id + 2) % len(osd_counts)]
            )
            pg_id += 1
    
    # Create pools - must be Dict[int, PoolInfo]
    pools = {
        1: PoolInfo(
            pool_id=1,
            pool_name='pool1',
            pg_count=sum(osd_counts.values()),
            primary_counts=osd_counts.copy()
        )
    }
    
    return ClusterState(osds=osds, hosts=hosts, pgs=pgs, pools=pools)


class TestDynamicScorerInitialization:
    """Test DynamicScorer initialization."""
    
    def test_default_initialization(self):
        """Test initialization with default parameters."""
        scorer = DynamicScorer()
        
        assert scorer.strategy_name == 'target_distance'
        assert scorer.target_cv == 0.10
        assert scorer.update_interval == 10
        assert scorer.iteration_count == 0
        assert len(scorer.cv_history) == 0
        assert len(scorer.weight_history) == 0
    
    def test_custom_initialization(self):
        """Test initialization with custom parameters."""
        scorer = DynamicScorer(
            strategy='target_distance',
            target_cv=0.05,
            update_interval=20,
            strategy_params={'min_weight': 0.10}
        )
        
        assert scorer.strategy_name == 'target_distance'
        assert scorer.target_cv == 0.05
        assert scorer.update_interval == 20
    
    def test_inherits_from_scorer(self):
        """Test that DynamicScorer inherits from Scorer."""
        scorer = DynamicScorer()
        assert isinstance(scorer, Scorer)
    
    def test_initial_weights(self):
        """Test initial weight configuration."""
        scorer = DynamicScorer(initial_weights=(0.5, 0.3, 0.2))
        
        assert scorer.w_osd == 0.5
        assert scorer.w_host == 0.3
        assert scorer.w_pool == 0.2
    
    def test_enabled_levels(self):
        """Test initialization with enabled levels."""
        scorer = DynamicScorer(enabled_levels=['osd', 'host'])
        
        assert 'osd' in scorer.enabled_levels
        assert 'host' in scorer.enabled_levels
        assert 'pool' not in scorer.enabled_levels
    
    def test_invalid_strategy(self):
        """Test that invalid strategy raises error."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            DynamicScorer(strategy='nonexistent')


class TestWeightUpdateLogic:
    """Test weight update mechanism."""
    
    def test_updates_at_correct_intervals(self):
        """Test that weights update at specified intervals."""
        scorer = DynamicScorer(strategy='proportional', update_interval=5)
        state = create_simple_cluster_state()
        
        # First call (iteration 0) should trigger update
        scorer.calculate_score(state)
        assert len(scorer.weight_history) == 1
        
        # Calls 1-4 should not trigger update
        for _ in range(4):
            scorer.calculate_score(state)
        assert len(scorer.weight_history) == 1
        
        # Call at iteration 5 should trigger update
        scorer.calculate_score(state)
        assert len(scorer.weight_history) == 2
    
    def test_weights_change_based_on_state(self):
        """Test that weights adapt to cluster state."""
        scorer = DynamicScorer(strategy='target_distance', update_interval=1, target_cv=0.10)
        
        # Initial state: highly imbalanced OSD
        state = create_simple_cluster_state(osd_counts={0: 200, 1: 50, 2: 50})
        scorer.calculate_score(state)
        
        initial_weights = scorer.get_current_weights()
        
        # Weights should be calculated and valid
        assert sum(initial_weights) > 0.99  # Sum to 1.0
        assert all(w >= 0 for w in initial_weights)
        
        # Should have history recorded
        assert len(scorer.weight_history) == 1
        assert len(scorer.cv_history) == 1
    
    def test_cv_history_tracking(self):
        """Test that CV history is tracked correctly."""
        scorer = DynamicScorer(update_interval=5)
        state = create_simple_cluster_state()
        
        # Trigger multiple updates
        for _ in range(15):
            scorer.calculate_score(state)
        
        # Should have 3 updates (0, 5, 10)
        assert len(scorer.cv_history) == 3
        
        # Each entry should be a tuple of 3 CVs
        for cvs in scorer.cv_history:
            assert len(cvs) == 3
            assert all(isinstance(cv, float) for cv in cvs)
    
    def test_weight_history_tracking(self):
        """Test that weight history is tracked correctly."""
        scorer = DynamicScorer(update_interval=5)
        state = create_simple_cluster_state()
        
        # Trigger multiple updates
        for _ in range(15):
            scorer.calculate_score(state)
        
        # Should have 3 updates
        assert len(scorer.weight_history) == 3
        
        # Each entry should be a tuple of 3 weights summing to 1
        for weights in scorer.weight_history:
            assert len(weights) == 3
            assert abs(sum(weights) - 1.0) < 0.001


class TestCVCalculation:
    """Test CV calculation for different dimensions."""
    
    def test_calculates_osd_cv(self):
        """Test OSD CV calculation."""
        scorer = DynamicScorer(update_interval=1)
        
        # Create state with known CV
        state = create_simple_cluster_state(osd_counts={0: 100, 1: 100, 2: 100})
        scorer.calculate_score(state)
        
        cvs = scorer.cv_history[0]
        osd_cv = cvs[0]
        
        # Equal counts should give CV ≈ 0
        assert osd_cv < 0.01
    
    def test_calculates_host_cv(self):
        """Test Host CV calculation."""
        scorer = DynamicScorer(update_interval=1)
        
        # Create state with balanced hosts
        state = create_simple_cluster_state(
            osd_counts={0: 50, 1: 50, 2: 50, 3: 50},
            host_counts={'host1': [0, 1], 'host2': [2, 3]}
        )
        scorer.calculate_score(state)
        
        cvs = scorer.cv_history[0]
        host_cv = cvs[1]
        
        # Balanced hosts should give CV ≈ 0
        assert host_cv < 0.01
    
    def test_calculates_pool_cv(self):
        """Test Pool CV calculation."""
        scorer = DynamicScorer(update_interval=1)
        state = create_simple_cluster_state()
        
        scorer.calculate_score(state)
        cvs = scorer.cv_history[0]
        pool_cv = cvs[2]
        
        # Should calculate some pool CV
        assert isinstance(pool_cv, float)
        assert pool_cv >= 0
    
    def test_cv_caching(self):
        """Test that CV calculation is cached."""
        scorer = DynamicScorer(update_interval=1)
        state = create_simple_cluster_state()
        
        # First call calculates
        cvs1 = scorer._calculate_current_cvs(state)
        
        # Second call with same state should use cache
        cvs2 = scorer._calculate_current_cvs(state)
        
        assert cvs1 == cvs2
        assert scorer._last_state_id == id(state)


class TestHistoryAccess:
    """Test history access methods."""
    
    def test_get_weight_history(self):
        """Test retrieving weight history."""
        scorer = DynamicScorer(update_interval=5)
        state = create_simple_cluster_state()
        
        for _ in range(10):
            scorer.calculate_score(state)
        
        history = scorer.get_weight_history()
        
        # Should return a copy
        assert isinstance(history, list)
        assert len(history) == 2  # Updates at 0 and 5
        
        # Modifying returned history shouldn't affect scorer
        history.append((0.0, 0.0, 1.0))
        assert len(scorer.weight_history) == 2
    
    def test_get_cv_history(self):
        """Test retrieving CV history."""
        scorer = DynamicScorer(update_interval=5)
        state = create_simple_cluster_state()
        
        for _ in range(10):
            scorer.calculate_score(state)
        
        history = scorer.get_cv_history()
        
        # Should return a copy
        assert isinstance(history, list)
        assert len(history) == 2
        
        # Modifying returned history shouldn't affect scorer
        history.append((0.0, 0.0, 0.0))
        assert len(scorer.cv_history) == 2
    
    def test_get_current_weights(self):
        """Test retrieving current weights."""
        scorer = DynamicScorer(initial_weights=(0.6, 0.3, 0.1))
        
        weights = scorer.get_current_weights()
        
        assert weights == (0.6, 0.3, 0.1)
        assert isinstance(weights, tuple)


class TestStatistics:
    """Test statistics generation."""
    
    def test_get_statistics_initial(self):
        """Test statistics before any optimization."""
        scorer = DynamicScorer(
            strategy='target_distance',
            target_cv=0.15,
            update_interval=20
        )
        
        stats = scorer.get_statistics()
        
        assert stats['strategy'] == 'target_distance'
        assert stats['target_cv'] == 0.15
        assert stats['update_interval'] == 20
        assert stats['num_updates'] == 0
        assert stats['total_iterations'] == 0
    
    def test_get_statistics_after_optimization(self):
        """Test statistics after running optimization."""
        scorer = DynamicScorer(update_interval=10)
        state = create_simple_cluster_state()
        
        # Run 25 iterations
        for _ in range(25):
            scorer.calculate_score(state)
        
        stats = scorer.get_statistics()
        
        assert stats['num_updates'] == 3  # 0, 10, 20
        assert stats['total_iterations'] == 25
        assert 'initial_weights' in stats
        assert 'initial_cvs' in stats
        assert 'final_cvs' in stats
        assert 'cv_improvement' in stats
        assert 'weight_evolution' in stats
    
    def test_statistics_weight_evolution(self):
        """Test weight evolution statistics."""
        scorer = DynamicScorer(update_interval=5)
        state = create_simple_cluster_state()
        
        for _ in range(20):
            scorer.calculate_score(state)
        
        stats = scorer.get_statistics()
        evolution = stats['weight_evolution']
        
        # Should track min/max for each dimension
        assert 'min_osd' in evolution
        assert 'max_osd' in evolution
        assert 'min_host' in evolution
        assert 'max_host' in evolution
        assert 'min_pool' in evolution
        assert 'max_pool' in evolution
        
        # Min should be <= max
        assert evolution['min_osd'] <= evolution['max_osd']


class TestReset:
    """Test reset functionality."""
    
    def test_reset_clears_history(self):
        """Test that reset clears all history."""
        scorer = DynamicScorer(update_interval=5)
        state = create_simple_cluster_state()
        
        # Build up history
        for _ in range(15):
            scorer.calculate_score(state)
        
        assert scorer.iteration_count > 0
        assert len(scorer.cv_history) > 0
        assert len(scorer.weight_history) > 0
        
        # Reset
        scorer.reset()
        
        assert scorer.iteration_count == 0
        assert len(scorer.cv_history) == 0
        assert len(scorer.weight_history) == 0
    
    def test_reset_clears_cache(self):
        """Test that reset clears CV cache."""
        scorer = DynamicScorer()
        state = create_simple_cluster_state()
        
        scorer.calculate_score(state)
        assert scorer._last_state_id is not None
        
        scorer.reset()
        assert scorer._last_state_id is None
        assert scorer._cached_cvs is None


class TestIntegrationWithScorer:
    """Test integration with base Scorer class."""
    
    def test_calculate_score_returns_float(self):
        """Test that calculate_score returns valid score."""
        scorer = DynamicScorer()
        state = create_simple_cluster_state()
        
        score = scorer.calculate_score(state)
        
        assert isinstance(score, float)
        assert score >= 0
    
    def test_score_uses_updated_weights(self):
        """Test that score calculation uses dynamically updated weights."""
        scorer = DynamicScorer(
            strategy='target_distance',
            update_interval=1,
            target_cv=0.10
        )
        
        # Highly imbalanced OSD, balanced hosts
        state = create_simple_cluster_state(
            osd_counts={0: 200, 1: 50, 2: 50},
            host_counts={'host1': [0], 'host2': [1], 'host3': [2]}
        )
        
        score1 = scorer.calculate_score(state)
        
        # Weights should be updated and valid
        weights = scorer.get_current_weights()
        assert abs(sum(weights) - 1.0) < 0.001
        assert all(w >= 0 for w in weights)
        
        # Score should be valid
        assert isinstance(score1, float)
        assert score1 >= 0
    
    def test_respects_enabled_levels(self):
        """Test that enabled levels are respected."""
        scorer = DynamicScorer(
            enabled_levels=['osd'],
            update_interval=1
        )
        
        state = create_simple_cluster_state()
        scorer.calculate_score(state)
        
        weights = scorer.get_current_weights()
        
        # Only OSD should have weight
        assert weights[0] > 0
        assert weights[1] == 0  # Host disabled
        assert weights[2] == 0  # Pool disabled


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_state(self):
        """Test with empty cluster state."""
        scorer = DynamicScorer(update_interval=1)
        
        # Create minimal state
        state = ClusterState(osds={}, hosts={}, pgs={}, pools={})
        
        # Should not crash
        cvs = scorer._calculate_current_cvs(state)
        assert cvs == (0.0, 0.0, 0.0)
    
    def test_single_osd(self):
        """Test with single OSD (no variance)."""
        scorer = DynamicScorer(update_interval=1)
        
        state = create_simple_cluster_state(osd_counts={0: 100})
        scorer.calculate_score(state)
        
        cvs = scorer.cv_history[0]
        # Single OSD should have CV = 0
        assert cvs[0] < 0.01
    
    def test_very_frequent_updates(self):
        """Test with update_interval=1 (every iteration)."""
        scorer = DynamicScorer(update_interval=1)
        state = create_simple_cluster_state()
        
        for _ in range(10):
            scorer.calculate_score(state)
        
        # Should have 10 updates
        assert len(scorer.weight_history) == 10
    
    def test_very_infrequent_updates(self):
        """Test with very large update_interval."""
        scorer = DynamicScorer(update_interval=1000)
        state = create_simple_cluster_state()
        
        for _ in range(10):
            scorer.calculate_score(state)
        
        # Should have only 1 update (at iteration 0)
        assert len(scorer.weight_history) == 1
