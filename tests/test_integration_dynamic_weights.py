"""
Integration tests for dynamic weight optimization.

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

from ceph_primary_balancer import collector, analyzer, cli
from ceph_primary_balancer.optimizers.greedy import GreedyOptimizer
from ceph_primary_balancer.models import ClusterState, SwapProposal
from ceph_primary_balancer.dynamic_scorer import DynamicScorer
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.config import Config


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
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment after each test."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def mock_run_ceph_command(self, cmd: List[str]) -> dict:
        if 'pg' in cmd and 'dump' in cmd:
            return self.pg_dump_data
        elif 'osd' in cmd and 'tree' in cmd:
            return self.osd_tree_data
        elif 'osd' in cmd and 'pool' in cmd and 'ls' in cmd:
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
        """Dynamic weights work when enabled via GreedyOptimizer."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        initial_counts = [osd.primary_count for osd in state.osds.values()]
        initial_stats = analyzer.calculate_statistics(initial_counts)

        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)

        final_counts = [osd.primary_count for osd in state.osds.values()]
        final_stats = analyzer.calculate_statistics(final_counts)

        self.assertGreater(len(swaps), 0, "Should have found beneficial swaps")
        self.assertLess(final_stats.cv, initial_stats.cv, "CV should improve")

    def test_dynamic_weights_vs_fixed_weights(self):
        """Dynamic weights produce comparable or better results than fixed."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state_fixed = collector.build_cluster_state()
            state_dynamic = collector.build_cluster_state()

        swaps_fixed = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=False,
        ).optimize(state_fixed)

        fixed_counts = [osd.primary_count for osd in state_fixed.osds.values()]
        fixed_stats = analyzer.calculate_statistics(fixed_counts)

        swaps_dynamic = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state_dynamic)

        dynamic_counts = [osd.primary_count for osd in state_dynamic.osds.values()]
        dynamic_stats = analyzer.calculate_statistics(dynamic_counts)

        self.assertGreater(len(swaps_fixed), 0, "Fixed should find swaps")
        self.assertGreater(len(swaps_dynamic), 0, "Dynamic should find swaps")
        self.assertLess(fixed_stats.cv, 0.30, "Fixed should improve significantly")
        self.assertLess(dynamic_stats.cv, 0.30, "Dynamic should improve significantly")

        # Dynamic should be competitive (within 20% of fixed, or better)
        if fixed_stats.cv > 0.001:
            self.assertLess(dynamic_stats.cv, fixed_stats.cv * 1.2,
                           "Dynamic should be competitive with fixed weights")
        else:
            self.assertLess(dynamic_stats.cv, 0.05, "Dynamic achieved excellent balance")

    def test_config_file_dynamic_weights_loading(self):
        """Config file correctly loads dynamic weights settings."""
        config_path = os.path.join(self.test_dir, 'test_config.json')

        config_data = {
            "optimization": {
                "target_cv": 0.10,
                "max_iterations": 1000,
                "dynamic_weights": True,
                "dynamic_strategy": "two_phase",
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

        config = Config(config_path)

        self.assertTrue(config.get('optimization.dynamic_weights', False))
        self.assertEqual(config.get('optimization.dynamic_strategy', 'target_distance'),
                        'two_phase')
        self.assertEqual(config.get('optimization.weight_update_interval', 10), 15)

    def test_weight_update_interval_behavior(self):
        """Weight updates occur at the correct intervals."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        scorer = DynamicScorer(
            strategy='target_distance',
            target_cv=0.10,
            update_interval=5,
            enabled_levels=['osd', 'host', 'pool'],
            initial_weights=(0.5, 0.3, 0.2)
        )

        iteration_count = 25
        for i in range(iteration_count):
            score = scorer.calculate_score(state)
            if len(state.osds) > 0:
                osd_id = list(state.osds.keys())[0]
                state.osds[osd_id].primary_count += 1 if i % 2 == 0 else -1

        weight_history = scorer.get_weight_history()
        expected_updates = (iteration_count // 5) + 1

        # Allow some flexibility (+-1) due to implementation details
        self.assertGreaterEqual(len(weight_history), expected_updates - 1)
        self.assertLessEqual(len(weight_history), expected_updates + 1)

    def test_dynamic_weights_with_optimization_levels(self):
        """Dynamic weights work with different optimization levels."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        # Test with OSD-only
        swaps_osd = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            enabled_levels=['osd'],
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)

        self.assertGreater(len(swaps_osd), 0, "Should find swaps with OSD-only")

        # Reload state for next test
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        # Test with OSD+HOST
        swaps_osd_host = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            enabled_levels=['osd', 'host'],
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)

        self.assertGreater(len(swaps_osd_host), 0, "Should find swaps with OSD+HOST")

    def test_dynamic_scorer_statistics_output(self):
        """DynamicScorer produces comprehensive statistics."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        scorer = DynamicScorer(
            strategy='target_distance',
            target_cv=0.10,
            update_interval=10,
            enabled_levels=['osd', 'host', 'pool'],
            initial_weights=(0.5, 0.3, 0.2)
        )

        for i in range(30):
            scorer.calculate_score(state)
            if len(state.osds) > 0:
                osd_id = list(state.osds.keys())[i % len(state.osds)]
                state.osds[osd_id].primary_count += 1 if i % 2 == 0 else -1

        stats = scorer.get_statistics()

        self.assertIn('total_iterations', stats)
        self.assertIn('num_updates', stats)
        self.assertIn('initial_weights', stats)
        self.assertIn('current_weights', stats)
        self.assertIn('strategy', stats)
        self.assertIn('update_interval', stats)

        self.assertGreater(stats['total_iterations'], 0)
        self.assertGreater(stats['num_updates'], 0)
        self.assertEqual(stats['strategy'], 'target_distance')

    def test_edge_case_zero_update_interval(self):
        """System handles very frequent weight updates (interval=1)."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=100,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=1,
        ).optimize(state)

        self.assertGreater(len(swaps), 0, "Should find swaps even with interval=1")

    def test_edge_case_large_update_interval(self):
        """System handles infrequent weight updates (interval=10000)."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            state = collector.build_cluster_state()

        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10000,
        ).optimize(state)

        self.assertGreater(len(swaps), 0, "Should find swaps with large interval")

    def test_all_swaps_valid_with_dynamic_weights(self):
        """All swaps produced with dynamic weights are valid."""
        with patch.object(collector, 'run_ceph_command', side_effect=self.mock_run_ceph_command):
            original_state = collector.build_cluster_state()
            state = collector.build_cluster_state()

        swaps = GreedyOptimizer(
            target_cv=0.10,
            max_iterations=500,
            dynamic_weights=True,
            dynamic_strategy='target_distance',
            weight_update_interval=10,
        ).optimize(state)

        seen_pgids = set()

        for i, swap in enumerate(swaps):
            original_pg = original_state.pgs[swap.pgid]

            self.assertEqual(swap.old_primary, original_pg.primary,
                           f"Swap {i}: old_primary mismatch")
            self.assertIn(swap.new_primary, original_pg.acting,
                         f"Swap {i}: new_primary not in acting set")
            self.assertNotEqual(swap.old_primary, swap.new_primary,
                              f"Swap {i}: cannot swap to same OSD")
            self.assertNotIn(swap.pgid, seen_pgids,
                           f"Swap {i}: duplicate PG {swap.pgid}")
            seen_pgids.add(swap.pgid)


class TestDynamicWeightsCLI(unittest.TestCase):
    """Test CLI argument handling for dynamic weights."""

    def test_cli_help_includes_dynamic_weights(self):
        """CLI --help output includes dynamic weights options."""
        import subprocess

        result = subprocess.run(
            ['python3', '-m', 'ceph_primary_balancer.cli', '--help'],
            cwd='src',
            capture_output=True,
            text=True
        )

        help_text = result.stdout

        self.assertIn('--dynamic-weights', help_text)
        self.assertIn('--dynamic-strategy', help_text)
        self.assertIn('--weight-update-interval', help_text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
