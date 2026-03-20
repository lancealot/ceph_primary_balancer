"""
Integration test for Ceph Primary PG Balancer using mock data.

This test validates the complete workflow without requiring a real Ceph cluster:
1. Load mock Ceph CLI output from fixture files
2. Build ClusterState from mock data
3. Analyze initial distribution and verify imbalance
4. Run optimization algorithm
5. Verify improvement and validate all swaps
"""

import unittest
import json
import os
from unittest.mock import patch, MagicMock
from typing import List

from ceph_primary_balancer import collector, analyzer
from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
from ceph_primary_balancer.analyzer import calculate_statistics
from ceph_primary_balancer.models import ClusterState, SwapProposal


class TestIntegration(unittest.TestCase):
    """
    Integration test for the Ceph Primary PG Balancer.
    
    Uses mock data to simulate a real Ceph cluster and validates
    that the optimization workflow produces correct results.
    """
    
    @classmethod
    def setUpClass(cls):
        """Load fixture files once for all tests."""
        # Determine fixture directory path
        test_dir = os.path.dirname(os.path.abspath(__file__))
        fixtures_dir = os.path.join(test_dir, 'fixtures')
        
        # Load sample pg dump
        pg_dump_path = os.path.join(fixtures_dir, 'sample_pg_dump.json')
        with open(pg_dump_path, 'r') as f:
            cls.pg_dump_data = json.load(f)
        
        # Load sample osd tree
        osd_tree_path = os.path.join(fixtures_dir, 'sample_osd_tree.json')
        with open(osd_tree_path, 'r') as f:
            cls.osd_tree_data = json.load(f)
    
    def mock_run_ceph_command(self, cmd: List[str]) -> dict:
        """
        Mock implementation of run_ceph_command that returns fixture data.
        
        Args:
            cmd: Command list (e.g., ['ceph', 'pg', 'dump', 'pgs', '-f', 'json'])
            
        Returns:
            Fixture data corresponding to the command
        """
        # Determine which command was run and return appropriate fixture
        if 'pg' in cmd and 'dump' in cmd:
            return self.pg_dump_data
        elif 'osd' in cmd and 'tree' in cmd:
            return self.osd_tree_data
        elif 'osd' in cmd and 'pool' in cmd and 'ls' in cmd:
            # Mock pool data for pool-level compatibility
            # Extract pools from pg_dump data
            pools_seen = set()
            for pg_stat in self.pg_dump_data.get('pg_map', {}).get('pg_stats', []):
                pgid = pg_stat['pgid']
                pool_id = int(pgid.split('.')[0])
                pools_seen.add(pool_id)
            
            # Create mock pool details
            return [
                {
                    "pool_id": pool_id,
                    "pool_name": f"pool_{pool_id}",
                    "size": 3,
                    "min_size": 2,
                    "pg_num": 30  # Mock value
                }
                for pool_id in sorted(pools_seen)
            ]
        else:
            raise ValueError(f"Unexpected command: {cmd}")
    
    def test_mock_cluster_balancing(self):
        """
        Integration test: validate full optimization workflow with mock data.
        
        Test Steps:
        1. Mock run_ceph_command to return fixture data
        2. Build ClusterState using collector module
        3. Verify initial imbalance (high CV)
        4. Run optimization algorithm
        5. Verify improvement (final CV < initial CV)
        6. Verify all swaps are valid (new primaries in acting sets)
        7. Verify no errors occurred
        """
        # Step 1: Mock the Ceph command execution
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            
            # Step 2: Build ClusterState from mock data
            state = collector.build_cluster_state()
            
            # Verify we loaded the expected number of PGs and OSDs
            self.assertEqual(len(state.pgs), 30, "Should have 30 PGs from fixture")
            self.assertEqual(len(state.osds), 10, "Should have 10 OSDs from fixture")
            
            # Step 3: Analyze initial distribution
            primary_counts = [osd.primary_count for osd in state.osds.values()]
            initial_stats = analyzer.calculate_statistics(primary_counts)
            
            # Verify initial imbalance exists
            self.assertGreater(initial_stats.cv, 0.10, 
                              "Initial CV should be > 10% to demonstrate imbalance")
            
            # Store initial variance for comparison
            initial_variance = calculate_statistics([o.primary_count for o in state.osds.values()]).std_dev ** 2
            
            # Step 4: Run optimization
            swaps = GreedyOptimizer(target_cv=0.10, max_iterations=1000).optimize(state)
            
            # Step 5: Verify improvement
            final_counts = [osd.primary_count for osd in state.osds.values()]
            final_stats = analyzer.calculate_statistics(final_counts)
            final_variance = calculate_statistics([o.primary_count for o in state.osds.values()]).std_dev ** 2
            
            # Verify improvement occurred
            self.assertLess(final_variance, initial_variance,
                           "Final variance should be less than initial variance")
            self.assertLess(final_stats.cv, initial_stats.cv,
                           "Final CV should be less than initial CV")
            
            # Verify we found at least some swaps
            self.assertGreater(len(swaps), 0, "Should have found at least one beneficial swap")
            
            # Step 6: Verify all swaps are valid
            # Reload original state to check swaps
            with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
                original_state = collector.build_cluster_state()
            
            for i, swap in enumerate(swaps):
                # Get the original PG
                original_pg = original_state.pgs[swap.pgid]
                
                # Verify old_primary matches original primary
                self.assertEqual(swap.old_primary, original_pg.primary,
                               f"Swap {i}: old_primary should match original PG primary")
                
                # Verify new_primary is in the original acting set
                self.assertIn(swap.new_primary, original_pg.acting,
                            f"Swap {i}: new_primary {swap.new_primary} must be in acting set {original_pg.acting}")
                
                # Verify new_primary is not the same as old_primary
                self.assertNotEqual(swap.old_primary, swap.new_primary,
                                  f"Swap {i}: Cannot swap to the same OSD")
                
                # Verify variance improvement is positive
                self.assertGreater(swap.score_improvement, 0,
                                 f"Swap {i}: Should have positive variance improvement")
            
            # Step 7: Verify final state integrity
            # Check that total primaries equals total PGs
            total_primaries = sum(osd.primary_count for osd in state.osds.values())
            self.assertEqual(total_primaries, len(state.pgs),
                           "Total primary count should equal total PG count")
            
            # Check that each PG has a valid primary
            for pg in state.pgs.values():
                self.assertIn(pg.primary, state.osds,
                            f"PG {pg.pgid} primary {pg.primary} should be a valid OSD")
                self.assertEqual(pg.primary, pg.acting[0],
                               f"PG {pg.pgid} primary should be first in acting set")
            


if __name__ == '__main__':
    unittest.main()
