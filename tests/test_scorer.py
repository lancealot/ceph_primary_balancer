"""
Unit tests for the scorer module.

Tests cover:
- Scorer initialization and weight validation
- OSD variance calculation
- Host variance calculation
- Pool variance calculation
- Composite score calculation
- Multi-level statistics retrieval
"""

import unittest
from src.ceph_primary_balancer.scorer import Scorer
from src.ceph_primary_balancer.models import (
    ClusterState, OSDInfo, HostInfo, PoolInfo, PGInfo
)


class TestScorerInitialization(unittest.TestCase):
    """Test Scorer initialization and weight validation."""
    
    def test_init_with_default_weights(self):
        """Test initialization with default weights."""
        scorer = Scorer()
        
        self.assertEqual(scorer.w_osd, 0.5)
        self.assertEqual(scorer.w_host, 0.3)
        self.assertEqual(scorer.w_pool, 0.2)
    
    def test_init_with_custom_weights(self):
        """Test initialization with custom weights."""
        scorer = Scorer(w_osd=0.7, w_host=0.2, w_pool=0.1)
        
        self.assertEqual(scorer.w_osd, 0.7)
        self.assertEqual(scorer.w_host, 0.2)
        self.assertEqual(scorer.w_pool, 0.1)
    
    def test_init_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        with self.assertRaises(ValueError):
            Scorer(w_osd=0.5, w_host=0.3, w_pool=0.3)  # Sum = 1.1
    
    def test_init_negative_weights_rejected(self):
        """Test that negative weights are rejected."""
        with self.assertRaises(ValueError):
            Scorer(w_osd=-0.1, w_host=0.6, w_pool=0.5)
    
    def test_init_allows_small_floating_point_error(self):
        """Test that small floating point errors are tolerated."""
        # Should not raise error despite minor floating point imprecision
        scorer = Scorer(w_osd=0.333333, w_host=0.333333, w_pool=0.333334)
        self.assertIsNotNone(scorer)
    
    def test_init_single_dimension_weight(self):
        """Test initialization with only one dimension."""
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        
        self.assertEqual(scorer.w_osd, 1.0)
        self.assertEqual(scorer.w_host, 0.0)
        self.assertEqual(scorer.w_pool, 0.0)


class TestOSDVarianceCalculation(unittest.TestCase):
    """Test OSD variance calculation."""
    
    def test_osd_variance_simple(self):
        """Test OSD variance with simple values."""
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=15)
        }
        state = ClusterState(pgs={}, osds=osds)
        
        variance = scorer.calculate_osd_variance(state)
        
        # Variance should be positive
        self.assertGreater(variance, 0)
    
    def test_osd_variance_identical_counts(self):
        """Test OSD variance when all counts are identical."""
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=10)
        }
        state = ClusterState(pgs={}, osds=osds)
        
        variance = scorer.calculate_osd_variance(state)
        
        # Variance should be zero for identical counts
        self.assertEqual(variance, 0.0)
    
    def test_osd_variance_empty_state(self):
        """Test OSD variance with no OSDs."""
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        state = ClusterState(pgs={}, osds={})
        
        variance = scorer.calculate_osd_variance(state)
        
        self.assertEqual(variance, 0.0)


class TestHostVarianceCalculation(unittest.TestCase):
    """Test host variance calculation."""
    
    def test_host_variance_simple(self):
        """Test host variance with simple values."""
        scorer = Scorer(w_osd=0.0, w_host=1.0, w_pool=0.0)
        hosts = {
            "host1": HostInfo(hostname="host1", osd_ids=[0], primary_count=50, total_pg_count=100),
            "host2": HostInfo(hostname="host2", osd_ids=[1], primary_count=100, total_pg_count=150),
            "host3": HostInfo(hostname="host3", osd_ids=[2], primary_count=150, total_pg_count=200)
        }
        state = ClusterState(pgs={}, osds={}, hosts=hosts)
        
        variance = scorer.calculate_host_variance(state)
        
        self.assertGreater(variance, 0)
    
    def test_host_variance_no_hosts(self):
        """Test host variance when no hosts exist."""
        scorer = Scorer(w_osd=0.0, w_host=1.0, w_pool=0.0)
        state = ClusterState(pgs={}, osds={})
        
        variance = scorer.calculate_host_variance(state)
        
        self.assertEqual(variance, 0.0)
    
    def test_host_variance_identical_counts(self):
        """Test host variance with identical counts."""
        scorer = Scorer(w_osd=0.0, w_host=1.0, w_pool=0.0)
        hosts = {
            "host1": HostInfo(hostname="host1", osd_ids=[0], primary_count=100, total_pg_count=200),
            "host2": HostInfo(hostname="host2", osd_ids=[1], primary_count=100, total_pg_count=200)
        }
        state = ClusterState(pgs={}, osds={}, hosts=hosts)
        
        variance = scorer.calculate_host_variance(state)
        
        self.assertEqual(variance, 0.0)


class TestPoolVarianceCalculation(unittest.TestCase):
    """Test pool variance calculation."""
    
    def test_pool_variance_simple(self):
        """Test pool variance with simple values."""
        scorer = Scorer(w_osd=0.0, w_host=0.0, w_pool=1.0)
        pools = {
            1: PoolInfo(pool_id=1, pool_name="pool1", pg_count=10,
                       primary_counts={0: 3, 1: 7})
        }
        osds = {
            0: OSDInfo(osd_id=0, primary_count=3),
            1: OSDInfo(osd_id=1, primary_count=7)
        }
        state = ClusterState(pgs={}, osds=osds, pools=pools)
        
        variance = scorer.calculate_pool_variance(state)
        
        self.assertGreater(variance, 0)
    
    def test_pool_variance_no_pools(self):
        """Test pool variance when no pools exist."""
        scorer = Scorer(w_osd=0.0, w_host=0.0, w_pool=1.0)
        state = ClusterState(pgs={}, osds={}, pools={})
        
        variance = scorer.calculate_pool_variance(state)
        
        self.assertEqual(variance, 0.0)
    
    def test_pool_variance_multiple_pools(self):
        """Test average pool variance across multiple pools."""
        scorer = Scorer(w_osd=0.0, w_host=0.0, w_pool=1.0)
        pools = {
            1: PoolInfo(pool_id=1, pool_name="pool1", pg_count=10,
                       primary_counts={0: 5, 1: 5}),  # Balanced
            2: PoolInfo(pool_id=2, pool_name="pool2", pg_count=20,
                       primary_counts={0: 5, 1: 15})   # Imbalanced
        }
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=20)
        }
        state = ClusterState(pgs={}, osds=osds, pools=pools)
        
        variance = scorer.calculate_pool_variance(state)
        
        # Should be average of two pool variances
        self.assertGreater(variance, 0)


class TestCompositeScore(unittest.TestCase):
    """Test composite score calculation."""
    
    def test_composite_score_osd_only(self):
        """Test composite score with only OSD dimension."""
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),
            1: OSDInfo(osd_id=1, primary_count=15)
        }
        state = ClusterState(pgs={}, osds=osds)
        
        score = scorer.calculate_score(state)
        
        # Score should equal OSD variance
        osd_variance = scorer.calculate_osd_variance(state)
        self.assertAlmostEqual(score, osd_variance)
    
    def test_composite_score_multi_dimensional(self):
        """Test composite score with all dimensions."""
        scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
        
        hosts = {
            "host1": HostInfo(hostname="host1", osd_ids=[0], primary_count=10, total_pg_count=20),
            "host2": HostInfo(hostname="host2", osd_ids=[1], primary_count=20, total_pg_count=30)
        }
        osds = {
            0: OSDInfo(osd_id=0, host="host1", primary_count=10),
            1: OSDInfo(osd_id=1, host="host2", primary_count=20)
        }
        pools = {
            1: PoolInfo(pool_id=1, pool_name="pool1", pg_count=30,
                       primary_counts={0: 10, 1: 20})
        }
        state = ClusterState(pgs={}, osds=osds, hosts=hosts, pools=pools)
        
        score = scorer.calculate_score(state)
        
        # Score should be weighted sum
        osd_var = scorer.calculate_osd_variance(state)
        host_var = scorer.calculate_host_variance(state)
        pool_var = scorer.calculate_pool_variance(state)
        
        expected = 0.5 * osd_var + 0.3 * host_var + 0.2 * pool_var
        self.assertAlmostEqual(score, expected)
    
    def test_composite_score_perfect_balance(self):
        """Test composite score when cluster is perfectly balanced."""
        scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10)
        }
        state = ClusterState(pgs={}, osds=osds)
        
        score = scorer.calculate_score(state)
        
        # Score should be zero for perfect balance
        self.assertEqual(score, 0.0)
    
    def test_composite_score_lower_is_better(self):
        """Test that lower scores indicate better balance."""
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        
        # Balanced state
        balanced_osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10)
        }
        balanced_state = ClusterState(pgs={}, osds=balanced_osds)
        balanced_score = scorer.calculate_score(balanced_state)
        
        # Imbalanced state
        imbalanced_osds = {
            0: OSDInfo(osd_id=0, primary_count=5),
            1: OSDInfo(osd_id=1, primary_count=15)
        }
        imbalanced_state = ClusterState(pgs={}, osds=imbalanced_osds)
        imbalanced_score = scorer.calculate_score(imbalanced_state)
        
        # Balanced should have lower score
        self.assertLess(balanced_score, imbalanced_score)


class TestGetStatisticsMultiLevel(unittest.TestCase):
    """Test multi-level statistics retrieval."""
    
    def test_get_statistics_multi_level(self):
        """Test retrieving statistics at all levels."""
        scorer = Scorer()
        
        hosts = {
            "host1": HostInfo(hostname="host1", osd_ids=[0], primary_count=10, total_pg_count=20)
        }
        osds = {
            0: OSDInfo(osd_id=0, host="host1", primary_count=10)
        }
        pools = {
            1: PoolInfo(pool_id=1, pool_name="pool1", pg_count=10,
                       primary_counts={0: 10})
        }
        state = ClusterState(pgs={}, osds=osds, hosts=hosts, pools=pools)
        
        stats = scorer.get_statistics_multi_level(state)
        
        # Should have OSD, host, and pool stats
        self.assertIn('osd', stats)
        self.assertIn('host', stats)
        self.assertIn('pool', stats)
        
        # Each should be a Statistics object
        self.assertEqual(stats['osd'].mean, 10.0)


if __name__ == '__main__':
    unittest.main()
