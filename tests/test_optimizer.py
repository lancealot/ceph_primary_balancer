"""
Unit tests for the optimizer module.

Tests cover:
- Variance calculation
- Swap simulation
- Swap application
- Best swap finding logic
- Edge cases (empty clusters, single OSD, no valid swaps)
"""

import unittest
from src.ceph_primary_balancer.optimizer import (
    calculate_variance,
    simulate_swap_score,
    apply_swap,
    find_best_swap,
    optimize_primaries
)
from src.ceph_primary_balancer.models import (
    ClusterState, OSDInfo, PGInfo, HostInfo, PoolInfo, SwapProposal
)
from src.ceph_primary_balancer.scorer import Scorer


class TestCalculateVariance(unittest.TestCase):
    """Test variance calculation function."""
    
    def test_variance_with_known_values(self):
        """Test variance calculation with known inputs."""
        # Create OSDs with known primary counts: [5, 10, 15]
        # Mean = 10, Variance = [(5-10)^2 + (10-10)^2 + (15-10)^2] / 3 = 50/3 = 16.67
        osds = {
            0: OSDInfo(osd_id=0, primary_count=5),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=15)
        }
        variance = calculate_variance(osds)
        expected = 50.0 / 3.0  # ≈ 16.67
        self.assertAlmostEqual(variance, expected, places=2)
    
    def test_variance_with_identical_counts(self):
        """Test variance when all OSDs have same count."""
        # All OSDs with count=10, variance should be 0
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=10)
        }
        variance = calculate_variance(osds)
        self.assertEqual(variance, 0.0)
    
    def test_variance_empty_osds(self):
        """Test variance with empty OSD dictionary."""
        variance = calculate_variance({})
        self.assertEqual(variance, 0.0)
    
    def test_variance_single_osd(self):
        """Test variance with single OSD."""
        osds = {0: OSDInfo(osd_id=0, primary_count=10)}
        variance = calculate_variance(osds)
        self.assertEqual(variance, 0.0)


class TestSimulateSwapScore(unittest.TestCase):
    """Test swap simulation function."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
    
    def test_simulate_swap_reduces_variance(self):
        """Test that simulating a beneficial swap reduces score."""
        # Create state with imbalanced OSDs
        osds = {
            0: OSDInfo(osd_id=0, host="host1", primary_count=15),  # Overloaded
            1: OSDInfo(osd_id=1, host="host2", primary_count=5)    # Underloaded
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1])  # Primary on OSD 0
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        # Calculate current score
        current_score = self.scorer.calculate_score(state)
        
        # Simulate swapping PG 1.0 from OSD 0 to OSD 1
        simulated_score = simulate_swap_score(state, "1.0", 1, self.scorer)
        
        # Simulated score should be lower (better balance)
        self.assertLess(simulated_score, current_score)
    
    def test_simulate_swap_doesnt_modify_state(self):
        """Test that simulation doesn't modify the original state."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=5)
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1])
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        # Store original counts
        orig_count_0 = state.osds[0].primary_count
        orig_count_1 = state.osds[1].primary_count
        
        # Simulate swap
        simulate_swap_score(state, "1.0", 1, self.scorer)
        
        # Verify state unchanged
        self.assertEqual(state.osds[0].primary_count, orig_count_0)
        self.assertEqual(state.osds[1].primary_count, orig_count_1)


class TestApplySwap(unittest.TestCase):
    """Test swap application function."""
    
    def test_apply_swap_updates_counts(self):
        """Test that applying swap updates OSD primary counts."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=5)
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1])
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        swap = SwapProposal(pgid="1.0", old_primary=0, new_primary=1, score_improvement=1.0)
        apply_swap(state, swap)
        
        # Verify counts updated
        self.assertEqual(state.osds[0].primary_count, 9)
        self.assertEqual(state.osds[1].primary_count, 6)
    
    def test_apply_swap_updates_pg_acting(self):
        """Test that applying swap reorders PG acting list."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=5)
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1, 2])
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        swap = SwapProposal(pgid="1.0", old_primary=0, new_primary=1, score_improvement=1.0)
        apply_swap(state, swap)
        
        # Verify new primary is first in acting list
        self.assertEqual(state.pgs["1.0"].acting[0], 1)
        self.assertIn(0, state.pgs["1.0"].acting[1:])
    
    def test_apply_swap_updates_hosts(self):
        """Test that applying swap updates host primary counts."""
        hosts = {
            "host1": HostInfo(hostname="host1", osd_ids=[0], primary_count=10, total_pg_count=20),
            "host2": HostInfo(hostname="host2", osd_ids=[1], primary_count=5, total_pg_count=15)
        }
        osds = {
            0: OSDInfo(osd_id=0, host="host1", primary_count=10),
            1: OSDInfo(osd_id=1, host="host2", primary_count=5)
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1])
        }
        state = ClusterState(pgs=pgs, osds=osds, hosts=hosts)
        
        swap = SwapProposal(pgid="1.0", old_primary=0, new_primary=1, score_improvement=1.0)
        apply_swap(state, swap)
        
        # Verify host counts updated
        self.assertEqual(state.hosts["host1"].primary_count, 9)
        self.assertEqual(state.hosts["host2"].primary_count, 6)


class TestFindBestSwap(unittest.TestCase):
    """Test best swap finding logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
    
    def test_find_best_swap_simple(self):
        """Test finding best swap in simple scenario."""
        # OSD 0 overloaded, OSD 1 underloaded
        osds = {
            0: OSDInfo(osd_id=0, primary_count=15),
            1: OSDInfo(osd_id=1, primary_count=5)
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1]),
            "1.1": PGInfo(pgid="1.1", pool_id=1, acting=[0, 1])
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        donors = [0]
        receivers = [1]
        
        swap = find_best_swap(state, donors, receivers, self.scorer)
        
        # Should find a valid swap
        self.assertIsNotNone(swap)
        self.assertEqual(swap.old_primary, 0)
        self.assertEqual(swap.new_primary, 1)
        self.assertGreater(swap.score_improvement, 0)
    
    def test_find_best_swap_no_valid_swaps(self):
        """Test when no valid swaps exist."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10)
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0])  # OSD 1 not in acting set
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        donors = [0]
        receivers = [1]
        
        swap = find_best_swap(state, donors, receivers, self.scorer)
        
        # Should return None when no valid swaps
        self.assertIsNone(swap)
    
    def test_find_best_swap_selects_best_improvement(self):
        """Test that the swap with best improvement is selected."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=20),  # Very overloaded
            1: OSDInfo(osd_id=1, primary_count=10),
            2: OSDInfo(osd_id=2, primary_count=5)    # Very underloaded
        }
        pgs = {
            "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1]),  # Can swap to 1
            "1.1": PGInfo(pgid="1.1", pool_id=1, acting=[0, 2])   # Can swap to 2 (better)
        }
        state = ClusterState(pgs=pgs, osds=osds)
        
        donors = [0]
        receivers = [1, 2]
        
        swap = find_best_swap(state, donors, receivers, self.scorer)
        
        # Should prefer swap to OSD 2 (more underloaded)
        self.assertIsNotNone(swap)
        self.assertEqual(swap.old_primary, 0)
        # Should be OSD 2 since it creates better balance
        self.assertEqual(swap.new_primary, 2)


class TestOptimizePrimaries(unittest.TestCase):
    """Test full optimization workflow."""
    
    def test_optimize_improves_balance(self):
        """Test that optimization improves overall balance."""
        # Create imbalanced cluster
        osds = {
            0: OSDInfo(osd_id=0, primary_count=15),
            1: OSDInfo(osd_id=1, primary_count=5)
        }
        pgs = {
            f"1.{i}": PGInfo(pgid=f"1.{i}", pool_id=1, acting=[0, 1])
            for i in range(10)
        }
        state = ClusterState(pgs=pgs, osds=osds)
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        
        # Calculate initial score
        initial_score = scorer.calculate_score(state)
        
        # Optimize
        swaps = optimize_primaries(state, scorer=scorer, target_cv=0.05, max_iterations=100)
        
        # Calculate final score
        final_score = scorer.calculate_score(state)
        
        # Verify improvement
        self.assertLess(final_score, initial_score)
        self.assertGreater(len(swaps), 0)
    
    def test_optimize_respects_max_iterations(self):
        """Test that optimization stops at max_iterations."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=20),
            1: OSDInfo(osd_id=1, primary_count=0)
        }
        pgs = {
            f"1.{i}": PGInfo(pgid=f"1.{i}", pool_id=1, acting=[0, 1])
            for i in range(20)
        }
        state = ClusterState(pgs=pgs, osds=osds)
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        
        # Run with limited iterations
        swaps = optimize_primaries(state, scorer=scorer, max_iterations=3)
        
        # Should stop at max_iterations even if not fully balanced
        self.assertLessEqual(len(swaps), 3)
    
    def test_optimize_already_balanced(self):
        """Test optimization when cluster is already balanced."""
        osds = {
            0: OSDInfo(osd_id=0, primary_count=10),
            1: OSDInfo(osd_id=1, primary_count=10)
        }
        pgs = {
            f"1.{i}": PGInfo(pgid=f"1.{i}", pool_id=1, acting=[i % 2, (i+1) % 2])
            for i in range(20)
        }
        state = ClusterState(pgs=pgs, osds=osds)
        scorer = Scorer(w_osd=1.0, w_host=0.0, w_pool=0.0)
        
        # Optimize
        swaps = optimize_primaries(state, scorer=scorer, target_cv=0.10)
        
        # Should find no swaps needed
        self.assertEqual(len(swaps), 0)


if __name__ == '__main__':
    unittest.main()
