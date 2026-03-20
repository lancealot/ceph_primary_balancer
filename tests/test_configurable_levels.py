"""
Tests for configurable optimization levels.

Tests the ability to enable/disable specific optimization dimensions
(OSD, HOST, POOL) to provide performance optimization and targeted
balancing strategies.
"""

import pytest
from unittest.mock import patch, MagicMock
from ceph_primary_balancer.config import Config, ConfigError
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.models import ClusterState, OSDInfo, HostInfo, PoolInfo, PGInfo


def create_test_cluster() -> ClusterState:
    """Create a simple test cluster for testing."""
    pgs = {}
    osds = {}
    hosts = {}
    pools = {}

    # Create 6 OSDs across 2 hosts
    for i in range(6):
        host_id = f"host{i // 3}"
        osds[i] = OSDInfo(osd_id=i, host=host_id, primary_count=10 + i)

        if host_id not in hosts:
            hosts[host_id] = HostInfo(hostname=host_id)
        hosts[host_id].osd_ids.append(i)
        hosts[host_id].primary_count += osds[i].primary_count

    # Create 2 pools with some PGs
    for pool_id in [1, 2]:
        pool = PoolInfo(pool_id=pool_id, pool_name=f"pool{pool_id}", pg_count=5)
        pools[pool_id] = pool

        for pg_num in range(5):
            pgid = f"{pool_id}.{pg_num}"
            pg = PGInfo(pgid=pgid, pool_id=pool_id, acting=[0, 1, 2])
            pgs[pgid] = pg
            pool.primary_counts[0] = pool.primary_counts.get(0, 0) + 1

    return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)


class TestConfigEnabledLevels:
    """Test configuration support for enabled_levels."""
    
    def test_default_enabled_levels(self):
        """Test that default configuration has all three levels enabled."""
        config = Config()
        levels = config.get('optimization.enabled_levels')
        assert set(levels) == {'osd', 'host', 'pool'}
    
    def test_enabled_levels_validation_valid(self):
        """Test validation accepts valid enabled_levels."""
        config = Config()
        config.settings['optimization']['enabled_levels'] = ['osd', 'host']
        config.validate_enabled_levels()  # Should not raise
        
        # Check weights were normalized
        weights = config.settings['scoring']['weights']
        assert 'osd' in weights
        assert 'host' in weights
        assert 'pool' not in weights
    
    def test_enabled_levels_validation_empty(self):
        """Test validation rejects empty enabled_levels list."""
        config = Config()
        config.settings['optimization']['enabled_levels'] = []
        
        with pytest.raises(ConfigError, match="At least one"):
            config.validate_enabled_levels()
    
    def test_enabled_levels_validation_invalid_level(self):
        """Test validation rejects invalid level names."""
        config = Config()
        config.settings['optimization']['enabled_levels'] = ['osd', 'invalid']
        
        with pytest.raises(ConfigError, match="Invalid level"):
            config.validate_enabled_levels()
    
    def test_enabled_levels_validation_not_list(self):
        """Test validation rejects non-list enabled_levels."""
        config = Config()
        config.settings['optimization']['enabled_levels'] = 'osd'
        
        with pytest.raises(ConfigError, match="must be a list"):
            config.validate_enabled_levels()
    
    def test_weight_normalization_for_enabled_levels(self):
        """Test that weights are normalized for enabled levels only."""
        config = Config()
        config.settings['optimization']['enabled_levels'] = ['osd', 'host']
        config.settings['scoring']['weights'] = {
            'osd': 0.6,
            'host': 0.4,
            'pool': 0.5  # This should be ignored
        }
        
        config.validate_enabled_levels()
        
        weights = config.settings['scoring']['weights']
        assert 'osd' in weights
        assert 'host' in weights
        assert 'pool' not in weights
        
        # Should sum to 1.0 (normalized)
        total = weights['osd'] + weights['host']
        assert abs(total - 1.0) < 0.001


class TestScorerEnabledLevels:
    """Test Scorer with enabled_levels support."""
    
    def test_scorer_default_all_enabled(self):
        """Test scorer with default (all levels enabled)."""
        scorer = Scorer()
        
        assert scorer.is_level_enabled('osd')
        assert scorer.is_level_enabled('host')
        assert scorer.is_level_enabled('pool')
        assert set(scorer.get_enabled_levels()) == {'host', 'osd', 'pool'}
    
    def test_scorer_osd_only(self):
        """Test scorer with OSD-only optimization."""
        scorer = Scorer(w_osd=1.0, enabled_levels=['osd'])
        
        assert scorer.is_level_enabled('osd')
        assert not scorer.is_level_enabled('host')
        assert not scorer.is_level_enabled('pool')
        
        # Weights should be normalized
        assert scorer.w_osd == 1.0
        assert scorer.w_host == 0.0
        assert scorer.w_pool == 0.0
    
    def test_scorer_osd_host(self):
        """Test scorer with OSD+HOST optimization."""
        scorer = Scorer(w_osd=0.6, w_host=0.4, enabled_levels=['osd', 'host'])
        
        assert scorer.is_level_enabled('osd')
        assert scorer.is_level_enabled('host')
        assert not scorer.is_level_enabled('pool')
        
        # Weights should be normalized to sum to 1.0
        assert abs(scorer.w_osd - 0.6) < 0.001
        assert abs(scorer.w_host - 0.4) < 0.001
        assert scorer.w_pool == 0.0
    
    def test_scorer_host_pool(self):
        """Test scorer with HOST+POOL optimization (skip OSD)."""
        scorer = Scorer(w_host=0.7, w_pool=0.3, enabled_levels=['host', 'pool'])
        
        assert not scorer.is_level_enabled('osd')
        assert scorer.is_level_enabled('host')
        assert scorer.is_level_enabled('pool')
        
        assert scorer.w_osd == 0.0
        assert abs(scorer.w_host - 0.7) < 0.001
        assert abs(scorer.w_pool - 0.3) < 0.001
    
    def test_scorer_empty_enabled_levels_raises(self):
        """Test that empty enabled_levels raises ValueError."""
        with pytest.raises(ValueError, match="At least one"):
            Scorer(enabled_levels=[])
    
    def test_scorer_invalid_level_raises(self):
        """Test that invalid level name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid optimization level"):
            Scorer(enabled_levels=['osd', 'invalid'])
    
    def test_scorer_zero_weight_enabled_levels_raises(self):
        """Test that zero weights for all enabled levels raises ValueError."""
        with pytest.raises(ValueError, match="Total weight.*cannot be zero"):
            Scorer(w_osd=0.0, w_host=0.0, enabled_levels=['osd', 'host'])


class TestScorerSkipsDisabledDimensions:
    """Test that scorer truly skips computation for disabled dimensions."""
    
    def test_osd_only_skips_host_pool_computation(self):
        """Test that OSD-only scorer doesn't call host/pool variance methods."""
        state = create_test_cluster()
        scorer = Scorer(w_osd=1.0, enabled_levels=['osd'])
        
        # Patch the variance calculation methods
        with patch.object(scorer, 'calculate_host_variance') as mock_host:
            with patch.object(scorer, 'calculate_pool_variance') as mock_pool:
                # Call calculate_osd_variance normally
                original_osd_method = Scorer.calculate_osd_variance
                
                score = scorer.calculate_score(state)
                
                # Verify host and pool methods were NOT called
                mock_host.assert_not_called()
                mock_pool.assert_not_called()
                
                # Score should be non-zero (from OSD variance)
                assert score > 0
    
    def test_host_pool_skips_osd_computation(self):
        """Test that HOST+POOL scorer doesn't call OSD variance method."""
        state = create_test_cluster()
        scorer = Scorer(w_host=0.6, w_pool=0.4, enabled_levels=['host', 'pool'])
        
        with patch.object(scorer, 'calculate_osd_variance') as mock_osd:
            score = scorer.calculate_score(state)
            
            # Verify OSD method was NOT called
            mock_osd.assert_not_called()
            
            # Score should be non-zero (from host and pool variance)
            assert score > 0
    
    def test_pool_only_skips_osd_host_computation(self):
        """Test that POOL-only scorer doesn't call OSD/host variance methods."""
        state = create_test_cluster()
        scorer = Scorer(w_pool=1.0, enabled_levels=['pool'])
        
        with patch.object(scorer, 'calculate_osd_variance') as mock_osd:
            with patch.object(scorer, 'calculate_host_variance') as mock_host:
                score = scorer.calculate_score(state)
                
                # Verify OSD and host methods were NOT called
                mock_osd.assert_not_called()
                mock_host.assert_not_called()
                
                # Score should be >= 0 (from pool variance)
                assert score >= 0


class TestScorerCalculations:
    """Test scorer calculations with different enabled levels."""
    
    def test_all_enabled_combines_all_dimensions(self):
        """Test that all-enabled scorer combines all three dimensions using CV."""
        import math
        state = create_test_cluster()
        scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)

        # Calculate composite score (now CV-based)
        score = scorer.calculate_score(state)

        # Score should be positive and less than raw variance-based score
        assert score > 0
        # CV values are typically between 0 and 1, so the score should be modest
        assert score < 2.0

    def test_osd_only_score(self):
        """Test that OSD-only score equals OSD CV."""
        import math
        state = create_test_cluster()
        scorer = Scorer(w_osd=1.0, enabled_levels=['osd'])

        osd_var = scorer.calculate_osd_variance(state)
        osd_counts = [osd.primary_count for osd in state.osds.values()]
        mean = sum(osd_counts) / len(osd_counts)
        expected_cv = math.sqrt(osd_var) / mean

        score = scorer.calculate_score(state)

        assert abs(score - expected_cv) < 0.001
    
    def test_different_strategies_produce_different_scores(self):
        """Test that different strategies produce different scores."""
        state = create_test_cluster()
        
        scorer_osd = Scorer(w_osd=1.0, enabled_levels=['osd'])
        scorer_host = Scorer(w_host=1.0, enabled_levels=['host'])
        scorer_all = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
        
        score_osd = scorer_osd.calculate_score(state)
        score_host = scorer_host.calculate_score(state)
        score_all = scorer_all.calculate_score(state)
        
        # Scores should be different (with high probability)
        assert score_osd != score_host
        assert score_osd != score_all
        assert score_host != score_all


class TestScorerGetEnabledLevels:
    """Test getter methods for enabled levels."""
    
    def test_get_enabled_levels_osd_only(self):
        """Test getting enabled levels for OSD-only."""
        scorer = Scorer(enabled_levels=['osd'])
        levels = scorer.get_enabled_levels()
        
        assert levels == ['osd']
    
    def test_get_enabled_levels_multiple(self):
        """Test getting enabled levels for multiple dimensions."""
        scorer = Scorer(enabled_levels=['pool', 'osd', 'host'])
        levels = scorer.get_enabled_levels()
        
        # Should be sorted
        assert levels == ['host', 'osd', 'pool']
    
    def test_is_level_enabled(self):
        """Test is_level_enabled method."""
        scorer = Scorer(enabled_levels=['osd', 'host'])
        
        assert scorer.is_level_enabled('osd')
        assert scorer.is_level_enabled('host')
        assert not scorer.is_level_enabled('pool')


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""
    
    def test_scorer_without_enabled_levels_works(self):
        """Test that Scorer works without enabled_levels argument (backward compat)."""
        scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
        
        # Should default to all enabled
        assert scorer.is_level_enabled('osd')
        assert scorer.is_level_enabled('host')
        assert scorer.is_level_enabled('pool')
    
    def test_existing_scorer_calls_work(self):
        """Test that existing scorer usage patterns still work."""
        state = create_test_cluster()
        scorer = Scorer()  # Default constructor
        
        # All existing methods should work
        score = scorer.calculate_score(state)
        osd_var = scorer.calculate_osd_variance(state)
        host_var = scorer.calculate_host_variance(state)
        pool_var = scorer.calculate_pool_variance(state)
        stats = scorer.get_statistics_multi_level(state)
        
        assert score > 0
        assert osd_var >= 0
        assert host_var >= 0
        assert pool_var >= 0
        assert 'osd' in stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
