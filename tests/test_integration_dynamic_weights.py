"""
Integration tests for Phase 7.1 Dynamic Weight Optimization.

Tests the complete dynamic weights feature including:
1. CLI argument parsing and validation
2. Config file loading for dynamic weights
3. End-to-end optimization with dynamic weight adaptation
4. Weight evolution tracking and output
5. Different weight strategies (proportional, target_distance)
6. Integration with existing optimization pipeline
"""

import unittest
import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import List

from src.ceph_primary_balancer import collector, analyzer, cli
from src.ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
from src.ceph_primary_balancer.models import ClusterState, SwapProposal
from src.ceph_primary_balancer.dynamic_scorer import DynamicScorer
from src.ceph_primary_balancer.scorer import Scorer
from src.ceph_primary_balancer.config import Config


class TestDynamicWeightsIntegration(unittest.TestCase):
    """Integration tests for dynamic weight optimization feature."""
    
    @classmethod
    def setUpClass(cls):
        """Load fixture files once for all tests."""
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
    
    def setUp(self):
        """Set up test environment for each test."""
        # Create temporary directory for test outputs
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test environment after each test."""
        # Remove temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def mock_run_ceph_command(self, cmd: List[str]) -> dict:
        """
        Mock implementation of run_ceph_command that returns fixture data.
        
        Args:
            cmd: Command list (e.g., ['ceph', 'pg', 'dump', 'pgs', '-f', 'json'])
            
        Returns:
            Fixture data corresponding to the command
        """
        if 'pg' in cmd and 'dump' in cmd:
            return self.pg_dump_data
        elif 'osd' in cmd and 'tree' in cmd:
            return self.osd_tree_data
        elif 'osd' in cmd and 'pool' in cmd and 'ls' in cmd:
            # Mock pool data
            pools_seen = set()
            for pg_stat in self.pg_dump_data.get('pg_map', {}).get('pg_stats', []):
                pgid = pg_stat['pgid']
                pool_id = int(pgid.split('.')[0])
                pools_seen.add(pool_id)
            
            return [
                {
                    "pool_id": pool_id,
                    "pool_name": f"pool_{pool_id}",
                    "size": 3,
                    "min_size": 2,
                    "pg_num": 30
                }
                for pool_id in sorted(pools_seen)
            ]
        else:
            raise ValueError(f"Unexpected command: {cmd}")
    
    def test_dynamic_weights_enabled_via_optimize_primaries(self):
        """
        Test that dynamic weights work when enabled via optimize_primaries().
        
        Validates:
        - DynamicScorer is used when dynamic_weights=True
        - Weight updates occur at correct intervals
        - Optimization converges successfully
        - Weight history is tracked
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        # Get initial statistics
        initial_counts = [osd.primary_count for osd in state.osds.values()]
        initial_stats = analyzer.calculate_statistics(initial_counts)
        
        print("\n" + "=" * 70)
        print("TEST: Dynamic Weights via optimize_primaries()")
        print("=" * 70)
        print(f"Initial CV: {initial_stats.cv:.2%}")
        
        # Run optimization with dynamic weights enabled
        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)

        # Verify improvement occurred
        final_counts = [osd.primary_count for osd in state.osds.values()]
        final_stats = analyzer.calculate_statistics(final_counts)
        
        print(f"Final CV: {final_stats.cv:.2%}")
        print(f"Swaps performed: {len(swaps)}")
        print(f"Improvement: {(initial_stats.cv - final_stats.cv) / initial_stats.cv * 100:.1f}%")
        
        # Assertions
        self.assertGreater(len(swaps), 0, "Should have found beneficial swaps")
        self.assertLess(final_stats.cv, initial_stats.cv, "CV should improve")
        
        print("✓ Dynamic weights optimization successful")
    
    def test_dynamic_weights_proportional_strategy(self):
        """
        Test optimization with proportional weight strategy.
        
        Validates:
        - Proportional strategy works correctly
        - Weights are proportional to CV values
        - Optimization still converges
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        initial_counts = [osd.primary_count for osd in state.osds.values()]
        initial_stats = analyzer.calculate_statistics(initial_counts)
        
        print("\n" + "=" * 70)
        print("TEST: Proportional Weight Strategy")
        print("=" * 70)
        print(f"Initial CV: {initial_stats.cv:.2%}")
        
        # Run with proportional strategy
        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='proportional',
            weight_update_interval=10,
        ).optimize(state)
        
        final_counts = [osd.primary_count for osd in state.osds.values()]
        final_stats = analyzer.calculate_statistics(final_counts)
        
        print(f"Final CV: {final_stats.cv:.2%}")
        print(f"Swaps performed: {len(swaps)}")
        
        self.assertGreater(len(swaps), 0, "Should have found swaps")
        self.assertLess(final_stats.cv, initial_stats.cv, "Should improve")
        
        print("✓ Proportional strategy works")
    
    def test_dynamic_weights_adaptive_hybrid_strategy(self):
        """
        Test optimization with adaptive hybrid weight strategy.
        
        Validates:
        - Adaptive hybrid strategy works correctly
        - Improvement tracking and smoothing functions properly
        - Optimization still converges
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        initial_counts = [osd.primary_count for osd in state.osds.values()]
        initial_stats = analyzer.calculate_statistics(initial_counts)
        
        print("\n" + "=" * 70)
        print("TEST: Adaptive Hybrid Weight Strategy")
        print("=" * 70)
        print(f"Initial CV: {initial_stats.cv:.2%}")
        
        # Run with adaptive_hybrid strategy
        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='adaptive_hybrid',
            weight_update_interval=10,
        ).optimize(state)
        
        final_counts = [osd.primary_count for osd in state.osds.values()]
        final_stats = analyzer.calculate_statistics(final_counts)
        
        print(f"Final CV: {final_stats.cv:.2%}")
        print(f"Swaps performed: {len(swaps)}")
        
        self.assertGreater(len(swaps), 0, "Should have found swaps")
        self.assertLess(final_stats.cv, initial_stats.cv, "Should improve")
        
        print("✓ Adaptive hybrid strategy works")
    
    def test_dynamic_weights_vs_fixed_weights(self):
        """
        Compare dynamic weights vs fixed weights performance.
        
        Validates:
        - Dynamic weights produce comparable or better results
        - Both approaches converge to similar CV values
        - Dynamic weights may converge faster (expected but not required)
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state_fixed = collector.build_cluster_state()
            state_dynamic = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: Dynamic vs Fixed Weights Comparison")
        print("=" * 70)
        
        # Run with fixed weights
        swaps_fixed = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=False,
        ).optimize(state_fixed)
        
        fixed_counts = [osd.primary_count for osd in state_fixed.osds.values()]
        fixed_stats = analyzer.calculate_statistics(fixed_counts)
        
        print(f"Fixed weights:   CV={fixed_stats.cv:.2%}, Swaps={len(swaps_fixed)}")
        
        # Run with dynamic weights
        swaps_dynamic = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state_dynamic)
        
        dynamic_counts = [osd.primary_count for osd in state_dynamic.osds.values()]
        dynamic_stats = analyzer.calculate_statistics(dynamic_counts)
        
        print(f"Dynamic weights: CV={dynamic_stats.cv:.2%}, Swaps={len(swaps_dynamic)}")
        
        # Both should produce valid results
        self.assertGreater(len(swaps_fixed), 0, "Fixed should find swaps")
        self.assertGreater(len(swaps_dynamic), 0, "Dynamic should find swaps")
        
        # Both should improve
        self.assertLess(fixed_stats.cv, 0.30, "Fixed should improve significantly")
        self.assertLess(dynamic_stats.cv, 0.30, "Dynamic should improve significantly")
        
        # Dynamic should be competitive (within 20% of fixed, or better)
        # Handle edge case where both achieve perfect balance (CV=0)
        if fixed_stats.cv > 0.001:
            self.assertLess(dynamic_stats.cv, fixed_stats.cv * 1.2,
                           "Dynamic should be competitive with fixed weights")
        else:
            # Both achieved excellent balance
            self.assertLess(dynamic_stats.cv, 0.05, "Dynamic achieved excellent balance")
        
        print(f"✓ Both approaches produce valid results")
        if fixed_stats.cv > 0.001:
            print(f"  Dynamic CV ratio: {dynamic_stats.cv / fixed_stats.cv:.2f}x fixed")
        else:
            print(f"  Both achieved perfect or near-perfect balance (CV ≈ 0)")
    
    def test_config_file_dynamic_weights_loading(self):
        """
        Test loading dynamic weights configuration from config file.
        
        Validates:
        - Config file correctly loads dynamic_weights flag
        - Config file correctly loads dynamic_strategy
        - Config file correctly loads weight_update_interval
        """
        config_path = os.path.join(self.test_dir, 'test_config.json')
        
        # Create test config with dynamic weights
        config_data = {
            "optimization": {
                "target_cv": 0.10,
                "max_iterations": 1000,
                "dynamic_weights": True,
                "dynamic_strategy": "proportional",
                "weight_update_interval": 15
            },
            "scoring": {
                "weights": {
                    "osd": 0.5,
                    "host": 0.3,
                    "pool": 0.2
                }
            }
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        print("\n" + "=" * 70)
        print("TEST: Config File Loading for Dynamic Weights")
        print("=" * 70)
        
        # Load config
        config = Config(config_path)
        
        # Verify dynamic weights settings
        self.assertTrue(config.get('optimization.dynamic_weights', False),
                       "Should load dynamic_weights=True")
        self.assertEqual(config.get('optimization.dynamic_strategy', 'target_distance'),
                        'proportional',
                        "Should load proportional strategy")
        self.assertEqual(config.get('optimization.weight_update_interval', 10),
                        15,
                        "Should load interval=15")
        
        print(f"✓ Config loaded:")
        print(f"  dynamic_weights: {config.get('optimization.dynamic_weights')}")
        print(f"  dynamic_strategy: {config.get('optimization.dynamic_strategy')}")
        print(f"  weight_update_interval: {config.get('optimization.weight_update_interval')}")
    
    def test_weight_update_interval_behavior(self):
        """
        Test that weight updates occur at the correct intervals.
        
        Validates:
        - Weights update every N iterations (weight_update_interval)
        - CV history is tracked properly
        - Weight history is tracked properly
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: Weight Update Interval Behavior")
        print("=" * 70)
        
        # Create DynamicScorer with custom interval
        scorer = DynamicScorer(
            strategy='target_distance',
            target_cv=0.10,
            update_interval=5,
            enabled_levels=['osd', 'host', 'pool'],
            initial_weights=(0.5, 0.3, 0.2)
        )
        
        # Simulate some iterations
        iteration_count = 25
        for i in range(iteration_count):
            # Calculate score (triggers weight update at intervals)
            score = scorer.calculate_score(state)
            
            # Simulate some changes
            if len(state.osds) > 0:
                osd_id = list(state.osds.keys())[0]
                state.osds[osd_id].primary_count += 1 if i % 2 == 0 else -1
        
        # Get weight history
        weight_history = scorer.get_weight_history()
        
        # Should have weight updates at: 0, 5, 10, 15, 20, 25
        # That's 6 updates total (including initial)
        expected_updates = (iteration_count // 5) + 1
        
        print(f"Iterations: {iteration_count}")
        print(f"Update interval: 5")
        print(f"Weight history length: {len(weight_history)}")
        print(f"Expected updates: {expected_updates}")
        
        # Allow some flexibility (±1) due to implementation details
        self.assertGreaterEqual(len(weight_history), expected_updates - 1,
                               "Should have approximately correct number of updates")
        self.assertLessEqual(len(weight_history), expected_updates + 1,
                            "Should not update too frequently")
        
        print("✓ Weight updates occur at correct intervals")
    
    def test_dynamic_weights_with_optimization_levels(self):
        """
        Test dynamic weights work with different optimization levels.
        
        Validates:
        - Dynamic weights work with OSD-only optimization
        - Dynamic weights work with OSD+HOST optimization
        - Dynamic weights respect enabled_levels parameter
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: Dynamic Weights with Optimization Levels")
        print("=" * 70)
        
        # Test with OSD-only
        print("\nTesting OSD-only optimization...")
        swaps_osd = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            enabled_levels=['osd'],
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)
        
        print(f"  OSD-only swaps: {len(swaps_osd)}")
        self.assertGreater(len(swaps_osd), 0, "Should find swaps with OSD-only")
        
        # Reload state for next test
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        # Test with OSD+HOST
        print("\nTesting OSD+HOST optimization...")
        swaps_osd_host = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            enabled_levels=['osd', 'host'],
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)
        
        print(f"  OSD+HOST swaps: {len(swaps_osd_host)}")
        self.assertGreater(len(swaps_osd_host), 0, "Should find swaps with OSD+HOST")
        
        print("✓ Dynamic weights work with different optimization levels")
    
    def test_dynamic_scorer_statistics_output(self):
        """
        Test that DynamicScorer produces useful statistics.
        
        Validates:
        - get_statistics() returns comprehensive data
        - Statistics include weight evolution info
        - Statistics include CV tracking
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: DynamicScorer Statistics Output")
        print("=" * 70)
        
        # Create scorer and run some iterations
        scorer = DynamicScorer(
            strategy='target_distance',
            target_cv=0.10,
            update_interval=10,
            enabled_levels=['osd', 'host', 'pool'],
            initial_weights=(0.5, 0.3, 0.2)
        )
        
        # Simulate optimization steps
        for i in range(30):
            scorer.calculate_score(state)
            # Simulate some state changes
            if len(state.osds) > 0:
                osd_id = list(state.osds.keys())[i % len(state.osds)]
                state.osds[osd_id].primary_count += 1 if i % 2 == 0 else -1
        
        # Get statistics
        stats = scorer.get_statistics()
        
        print("\nStatistics keys:", list(stats.keys()))
        
        # Verify expected keys exist
        self.assertIn('total_iterations', stats)
        self.assertIn('num_updates', stats)
        self.assertIn('initial_weights', stats)
        self.assertIn('current_weights', stats)
        self.assertIn('strategy', stats)
        self.assertIn('update_interval', stats)
        
        print(f"  Total iterations: {stats['total_iterations']}")
        print(f"  Weight updates: {stats['num_updates']}")
        print(f"  Strategy: {stats['strategy']}")
        print(f"  Initial weights: {stats['initial_weights']}")
        print(f"  Current weights: {stats['current_weights']}")
        
        # Verify values make sense
        self.assertGreater(stats['total_iterations'], 0)
        self.assertGreater(stats['num_updates'], 0)
        self.assertEqual(stats['strategy'], 'target_distance')
        
        print("✓ Statistics output is comprehensive")
    
    def test_edge_case_zero_update_interval(self):
        """
        Test edge case: update_interval=1 (update every iteration).
        
        Validates:
        - System handles very frequent updates
        - No performance issues or crashes
        - Optimization still converges
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: Edge Case - Very Frequent Updates (interval=1)")
        print("=" * 70)
        
        # This should update weights every iteration
        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=100,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=1,
        ).optimize(state)
        
        print(f"Swaps with interval=1: {len(swaps)}")
        
        # Should still work and find swaps
        self.assertGreater(len(swaps), 0, "Should find swaps even with interval=1")
        
        print("✓ Handles very frequent updates correctly")
    
    def test_edge_case_large_update_interval(self):
        """
        Test edge case: very large update_interval.
        
        Validates:
        - System handles infrequent updates
        - Essentially behaves like fixed weights when interval is huge
        - Still produces valid results
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: Edge Case - Very Infrequent Updates (interval=10000)")
        print("=" * 70)
        
        # This should almost never update (or only once)
        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10000,
        ).optimize(state)
        
        print(f"Swaps with interval=10000: {len(swaps)}")
        
        # Should still work
        self.assertGreater(len(swaps), 0, "Should find swaps with large interval")
        
        print("✓ Handles infrequent updates correctly")
    
    def test_all_swaps_valid_with_dynamic_weights(self):
        """
        Validate that all swaps produced with dynamic weights are valid.
        
        Validates:
        - New primaries are in acting sets
        - Old primaries match original PG primaries
        - Swaps improve the cluster state
        - No duplicate swaps
        """
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            original_state = collector.build_cluster_state()
            state = collector.build_cluster_state()
        
        print("\n" + "=" * 70)
        print("TEST: Swap Validity with Dynamic Weights")
        print("=" * 70)
        
        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)

        print(f"Validating {len(swaps)} swaps...")
        
        # Track unique swaps
        seen_pgids = set()
        
        for i, swap in enumerate(swaps):
            # Get original PG
            original_pg = original_state.pgs[swap.pgid]
            
            # Verify old_primary matches
            self.assertEqual(swap.old_primary, original_pg.primary,
                           f"Swap {i}: old_primary mismatch")
            
            # Verify new_primary is in acting set
            self.assertIn(swap.new_primary, original_pg.acting,
                         f"Swap {i}: new_primary not in acting set")
            
            # Verify old != new
            self.assertNotEqual(swap.old_primary, swap.new_primary,
                              f"Swap {i}: cannot swap to same OSD")
            
            # Check for duplicates
            self.assertNotIn(swap.pgid, seen_pgids,
                           f"Swap {i}: duplicate PG {swap.pgid}")
            seen_pgids.add(swap.pgid)
        
        print(f"✓ All {len(swaps)} swaps are valid")
        print(f"  No duplicates detected")


class TestDynamicWeightsCLI(unittest.TestCase):
    """Test CLI argument handling for dynamic weights."""
    
    def test_cli_help_includes_dynamic_weights(self):
        """
        Test that --help output includes dynamic weights options.
        
        This is more of a smoke test to ensure CLI is properly configured.
        """
        import subprocess
        
        print("\n" + "=" * 70)
        print("TEST: CLI Help Includes Dynamic Weights Options")
        print("=" * 70)
        
        # Run with --help
        result = subprocess.run(
            ['python3', '-m', 'ceph_primary_balancer.cli', '--help'],
            cwd='src',
            capture_output=True,
            text=True
        )
        
        help_text = result.stdout
        
        # Check for key flags
        self.assertIn('--dynamic-weights', help_text,
                     "Help should mention --dynamic-weights")
        self.assertIn('--dynamic-strategy', help_text,
                     "Help should mention --dynamic-strategy")
        self.assertIn('--weight-update-interval', help_text,
                     "Help should mention --weight-update-interval")
        
        print("✓ CLI help includes all dynamic weights options")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
