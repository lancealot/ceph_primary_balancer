"""
Unit tests for the analyzer module.

Tests cover:
- Statistics calculation with various distributions
- Donor identification logic
- Receiver identification logic
- Pool statistics calculation
- Edge cases (empty data, single values, identical values)
"""

import unittest
from src.ceph_primary_balancer.analyzer import (
    calculate_statistics,
    identify_donors,
    identify_receivers,
    calculate_pool_statistics,
    get_pool_statistics_summary
)
from src.ceph_primary_balancer.models import (
    OSDInfo, PoolInfo, ClusterState, Statistics
)


class TestCalculateStatistics(unittest.TestCase):
    """Test statistics calculation function."""
    
    def test_statistics_with_known_values(self):
        """Test statistics with known simple values."""
        counts = [5, 10, 15]
        stats = calculate_statistics(counts)
        
        # Mean = (5 + 10 + 15) / 3 = 10
        self.assertAlmostEqual(stats.mean, 10.0)
        
        # Std dev = sqrt([(5-10)^2 + (10-10)^2 + (15-10)^2] / 2) = sqrt(50/2) ≈ 5.0
        self.assertAlmostEqual(stats.std_dev, 5.0, places=1)
        
        # CV = std_dev / mean = 5.0 / 10.0 = 0.5
        self.assertAlmostEqual(stats.cv, 0.5, places=2)
        
        # Min, max, median
        self.assertEqual(stats.min_val, 5)
        self.assertEqual(stats.max_val, 15)
        self.assertEqual(stats.p50, 10)
    
    def test_statistics_identical_values(self):
        """Test statistics when all values are identical."""
        counts = [10, 10, 10, 10]
        stats = calculate_statistics(counts)
        
        self.assertEqual(stats.mean, 10.0)
        self.assertEqual(stats.std_dev, 0.0)
        self.assertEqual(stats.cv, 0.0)
        self.assertEqual(stats.min_val, 10)
        self.assertEqual(stats.max_val, 10)
        self.assertEqual(stats.p50, 10)
    
    def test_statistics_single_value(self):
        """Test statistics with single value."""
        counts = [42]
        stats = calculate_statistics(counts)
        
        self.assertEqual(stats.mean, 42.0)
        self.assertEqual(stats.std_dev, 0.0)
        self.assertEqual(stats.cv, 0.0)
        self.assertEqual(stats.min_val, 42)
        self.assertEqual(stats.max_val, 42)
        self.assertEqual(stats.p50, 42)
    
    def test_statistics_with_zero_mean(self):
        """Test statistics when all values are zero."""
        counts = [0, 0, 0]
        stats = calculate_statistics(counts)
        
        self.assertEqual(stats.mean, 0.0)
        self.assertEqual(stats.std_dev, 0.0)
        self.assertEqual(stats.cv, 0.0)  # Should handle division by zero
    
    def test_statistics_empty_raises_error(self):
        """Test that empty list raises ValueError."""
        with self.assertRaises(ValueError):
            calculate_statistics([])
    
    def test_statistics_large_numbers(self):
        """Test statistics with large numbers."""
        counts = [1000, 2000, 3000, 4000]
        stats = calculate_statistics(counts)
        
        self.assertEqual(stats.mean, 2500.0)
        self.assertGreater(stats.std_dev, 0)
        self.assertEqual(stats.min_val, 1000)
        self.assertEqual(stats.max_val, 4000)
    
    def test_statistics_two_values(self):
        """Test statistics with exactly two values."""
        counts = [5, 15]
        stats = calculate_statistics(counts)
        
        self.assertEqual(stats.mean, 10.0)
        self.assertAlmostEqual(stats.std_dev, 7.07, places=1)  # sqrt(50)
        self.assertEqual(stats.min_val, 5)
        self.assertEqual(stats.max_val, 15)
        self.assertEqual(stats.p50, 10.0)


class TestIdentifyDonors(unittest.TestCase):
    """Test donor identification logic."""
    
    def test_identify_donors_basic(self):
        """Test basic donor identification."""
        # Mean = 10, threshold = 11 (10% above mean)
        # Donors: OSDs with count > 11
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),   # Below threshold
            1: OSDInfo(osd_id=1, primary_count=10),  # At mean
            2: OSDInfo(osd_id=2, primary_count=15)   # Above threshold (donor)
        }
        
        donors = identify_donors(osds, threshold_pct=0.1)
        
        self.assertEqual(donors, [2])
    
    def test_identify_donors_multiple(self):
        """Test identifying multiple donors."""
        # Mean = 10, threshold = 11
        osds = {
            0: OSDInfo(osd_id=0, primary_count=12),  # Donor
            1: OSDInfo(osd_id=1, primary_count=8),
            2: OSDInfo(osd_id=2, primary_count=15),  # Donor
            3: OSDInfo(osd_id=3, primary_count=5)
        }
        
        donors = identify_donors(osds, threshold_pct=0.1)
        
        # Should return sorted list
        self.assertEqual(donors, [0, 2])
    
    def test_identify_donors_none(self):
        """Test when no donors exist."""
        # All OSDs balanced
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=10)
        }
        
        donors = identify_donors(osds, threshold_pct=0.1)
        
        self.assertEqual(donors, [])
    
    def test_identify_donors_empty_osds(self):
        """Test with empty OSD dictionary."""
        donors = identify_donors({})
        self.assertEqual(donors, [])
    
    def test_identify_donors_custom_threshold(self):
        """Test with custom threshold percentage."""
        # Mean = (10 + 15 + 8) / 3 = 11, threshold = 13.2 (20% above mean)
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),  # Not donor (below threshold)
            1: OSDInfo(osd_id=1, primary_count=15),  # Donor (15 > 13.2)
            2: OSDInfo(osd_id=2, primary_count=8)
        }
        
        donors = identify_donors(osds, threshold_pct=0.2)
        
        self.assertEqual(donors, [1])


class TestIdentifyReceivers(unittest.TestCase):
    """Test receiver identification logic."""
    
    def test_identify_receivers_basic(self):
        """Test basic receiver identification."""
        # Mean = 10, threshold = 9 (10% below mean)
        # Receivers: OSDs with count < 9
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),   # Below threshold (receiver)
            1: OSDInfo(osd_id=1, primary_count=10),  # At mean
            2: OSDInfo(osd_id=2, primary_count=15)   # Above mean
        }
        
        receivers = identify_receivers(osds, threshold_pct=0.1)
        
        self.assertEqual(receivers, [0])
    
    def test_identify_receivers_multiple(self):
        """Test identifying multiple receivers."""
        # Mean = 10, threshold = 9
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),   # Receiver
            1: OSDInfo(osd_id=1, primary_count=12),
            2: OSDInfo(osd_id=2, primary_count=8),   # Receiver
            3: OSDInfo(osd_id=3, primary_count=15)
        }
        
        receivers = identify_receivers(osds, threshold_pct=0.1)
        
        # Should return sorted list
        self.assertEqual(receivers, [0, 2])
    
    def test_identify_receivers_none(self):
        """Test when no receivers exist."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=10)
        }
        
        receivers = identify_receivers(osds, threshold_pct=0.1)
        
        self.assertEqual(receivers, [])
    
    def test_identify_receivers_empty_osds(self):
        """Test with empty OSD dictionary."""
        receivers = identify_receivers({})
        self.assertEqual(receivers, [])
    
    def test_identify_receivers_custom_threshold(self):
        """Test with custom threshold percentage."""
        # Mean = 10, threshold = 8 (20% below mean)
        osds = {
            0: OSDInfo(osd_id=0, primary_count=9),   # Not receiver (only 10% below)
            1: OSDInfo(osd_id=1, primary_count=7),   # Receiver (30% below)
            2: OSDInfo(osd_id=2, primary_count=11)
        }
        
        receivers = identify_receivers(osds, threshold_pct=0.2)
        
        self.assertEqual(receivers, [1])


class TestCalculatePoolStatistics(unittest.TestCase):
    """Test pool statistics calculation."""
    
    def test_calculate_pool_statistics_basic(self):
        """Test basic pool statistics calculation."""
        pool = PoolInfo(
            pool_id=1,
            pool_name="test_pool",
            pg_count=10,
            primary_counts={0: 5, 1: 10, 2: 15}
        )
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=15)
        }
        
        stats = calculate_pool_statistics(pool, osds)
        
        # Should calculate stats for [5, 10, 15]
        self.assertAlmostEqual(stats.mean, 10.0)
        self.assertEqual(stats.min_val, 5)
        self.assertEqual(stats.max_val, 15)
    
    def test_calculate_pool_statistics_filters_missing_osds(self):
        """Test that pool statistics only includes valid OSDs."""
        pool = PoolInfo(
            pool_id=1,
            pool_name="test_pool",
            pg_count=10,
            primary_counts={0: 5, 99: 100}  # OSD 99 doesn't exist
        )
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5)
        }
        
        stats = calculate_pool_statistics(pool, osds)
        
        # Should only include OSD 0's count
        self.assertEqual(stats.mean, 5.0)
        self.assertEqual(stats.min_val, 5)
        self.assertEqual(stats.max_val, 5)
    
    def test_calculate_pool_statistics_no_primaries_raises_error(self):
        """Test error when pool has no primary assignments."""
        pool = PoolInfo(
            pool_id=1,
            pool_name="empty_pool",
            pg_count=0,
            primary_counts={}
        )
        osds = {
            0: OSDInfo(osd_id=0, primary_count=0)
        }
        
        with self.assertRaises(ValueError):
            calculate_pool_statistics(pool, osds)


class TestGetPoolStatisticsSummary(unittest.TestCase):
    """Test pool statistics summary generation."""
    
    def test_get_pool_statistics_summary_multiple_pools(self):
        """Test generating statistics for multiple pools."""
        pools = {
            1: PoolInfo(pool_id=1, pool_name="pool1", pg_count=10,
                       primary_counts={0: 5, 1: 5}),
            2: PoolInfo(pool_id=2, pool_name="pool2", pg_count=20,
                       primary_counts={0: 10, 1: 10})
        }
        osds = {
            0: OSDInfo(osd_id=0, primary_count=15),
            1: OSDInfo(osd_id=1, primary_count=15)
        }
        state = ClusterState(pgs={}, osds=osds, pools=pools)
        
        summary = get_pool_statistics_summary(state)
        
        # Should have stats for both pools
        self.assertIn(1, summary)
        self.assertIn(2, summary)
        self.assertAlmostEqual(summary[1].mean, 5.0)
        self.assertAlmostEqual(summary[2].mean, 10.0)
    
    def test_get_pool_statistics_summary_no_pools(self):
        """Test with no pools (Phase 1 scenario)."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10)
        }
        state = ClusterState(pgs={}, osds=osds, pools={})
        
        summary = get_pool_statistics_summary(state)
        
        # Should return empty dict
        self.assertEqual(summary, {})


if __name__ == '__main__':
    unittest.main()
