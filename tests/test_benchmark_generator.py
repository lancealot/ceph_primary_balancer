"""
Unit tests for benchmark generator module.

Tests cover:
- Imbalance pattern generation (balanced, random, concentrated, gradual, bimodal, worst_case)
- Synthetic cluster generation with various configurations
- Erasure-coded pool generation
- Dataset persistence (save/load)
- Reproducibility with seeding
"""

import unittest
import json
import tempfile
import os
import statistics
from pathlib import Path

from ceph_primary_balancer.benchmark.generator import (
    generate_imbalance_pattern,
    generate_synthetic_cluster,
    generate_ec_pool,
    save_test_dataset,
    load_test_dataset
)
from ceph_primary_balancer.models import ClusterState


class TestImbalancePatternGeneration(unittest.TestCase):
    """Test imbalance pattern generation functions."""
    
    def test_generate_balanced_pattern(self):
        """Test balanced pattern has very low CV."""
        counts = generate_imbalance_pattern(
            num_osds=10,
            total_primaries=1000,
            pattern_type='balanced',
            target_cv=0.05
        )
        
        self.assertEqual(len(counts), 10)
        self.assertEqual(sum(counts), 1000)
        
        # Calculate CV
        mean = statistics.mean(counts)
        std_dev = statistics.stdev(counts)
        cv = std_dev / mean if mean > 0 else 0
        
        self.assertLess(cv, 0.05, "Balanced pattern should have CV < 0.05")
    
    def test_generate_random_pattern(self):
        """Test random pattern approximates target CV."""
        counts = generate_imbalance_pattern(
            num_osds=100,
            total_primaries=10000,
            pattern_type='random',
            target_cv=0.30
        )
        
        self.assertEqual(len(counts), 100)
        self.assertEqual(sum(counts), 10000)
        
        # Calculate CV
        mean = statistics.mean(counts)
        std_dev = statistics.stdev(counts)
        cv = std_dev / mean if mean > 0 else 0
        
        # Allow 50% tolerance around target
        self.assertGreater(cv, 0.15, "Random pattern CV too low")
        self.assertLess(cv, 0.45, "Random pattern CV too high")
    
    def test_generate_concentrated_pattern(self):
        """Test concentrated pattern creates hotspots."""
        counts = generate_imbalance_pattern(
            num_osds=100,
            total_primaries=10000,
            pattern_type='concentrated',
            target_cv=0.40
        )
        
        self.assertEqual(len(counts), 100)
        self.assertEqual(sum(counts), 10000)
        
        # Top 10% should have significantly more than average
        sorted_counts = sorted(counts, reverse=True)
        top_10_percent = sorted_counts[:10]
        avg_top = statistics.mean(top_10_percent)
        overall_avg = statistics.mean(counts)
        
        self.assertGreater(avg_top, overall_avg * 1.5, 
                          "Concentrated pattern should create hotspots")
    
    def test_generate_gradual_pattern(self):
        """Test gradual pattern creates linear gradient."""
        counts = generate_imbalance_pattern(
            num_osds=50,
            total_primaries=5000,
            pattern_type='gradual',
            target_cv=0.25
        )
        
        self.assertEqual(len(counts), 50)
        self.assertEqual(sum(counts), 5000)
        
        # Pattern should have variety (not all same)
        self.assertGreater(max(counts) - min(counts), 10,
                          "Gradual pattern should have variance")
    
    def test_generate_bimodal_pattern(self):
        """Test bimodal pattern creates two distinct groups."""
        counts = generate_imbalance_pattern(
            num_osds=100,
            total_primaries=10000,
            pattern_type='bimodal',
            target_cv=0.35
        )
        
        self.assertEqual(len(counts), 100)
        self.assertEqual(sum(counts), 10000)
        
        # Should have high and low groups
        sorted_counts = sorted(counts)
        bottom_half = sorted_counts[:50]
        top_half = sorted_counts[50:]
        
        avg_bottom = statistics.mean(bottom_half)
        avg_top = statistics.mean(top_half)
        
        self.assertGreater(avg_top, avg_bottom,
                          "Bimodal should have distinct groups")
    
    def test_generate_worst_case_pattern(self):
        """Test worst_case pattern creates extreme concentration."""
        counts = generate_imbalance_pattern(
            num_osds=20,
            total_primaries=1000,
            pattern_type='worst_case',
            target_cv=1.0
        )
        
        self.assertEqual(len(counts), 20)
        self.assertEqual(sum(counts), 1000)
        
        # Should have very high CV
        mean = statistics.mean(counts)
        std_dev = statistics.stdev(counts)
        cv = std_dev / mean if mean > 0 else 0
        
        self.assertGreater(cv, 0.5, "Worst case should have very high CV")
    
    def test_no_negative_counts(self):
        """Test that no pattern generates negative counts."""
        for pattern in ['balanced', 'random', 'concentrated', 'gradual', 'bimodal', 'worst_case']:
            counts = generate_imbalance_pattern(
                num_osds=50,
                total_primaries=5000,
                pattern_type=pattern,
                target_cv=0.30
            )
            self.assertTrue(all(c >= 0 for c in counts),
                           f"Pattern {pattern} should not have negative counts")


class TestSyntheticClusterGeneration(unittest.TestCase):
    """Test synthetic cluster generation."""
    
    def test_basic_cluster_generation(self):
        """Test basic cluster structure."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=100,
            replication_factor=3,
            imbalance_cv=0.25,
            seed=42
        )
        
        self.assertIsInstance(state, ClusterState)
        self.assertEqual(len(state.osds), 10)
        self.assertEqual(len(state.hosts), 2)
        self.assertEqual(len(state.pools), 1)
        self.assertEqual(len(state.pgs), 100)
    
    def test_replication_factor_enforcement(self):
        """Test that acting sets match replication factor."""
        state = generate_synthetic_cluster(
            num_osds=15,
            num_hosts=3,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            seed=42
        )
        
        for pg in state.pgs.values():
            self.assertEqual(len(pg.acting), 3,
                           f"PG {pg.pgid} should have 3 replicas")
    
    def test_host_distribution(self):
        """Test OSDs are distributed across hosts."""
        state = generate_synthetic_cluster(
            num_osds=20,
            num_hosts=4,
            num_pools=1,
            pgs_per_pool=100,
            replication_factor=3,
            seed=42
        )
        
        # Each host should have some OSDs
        for host in state.hosts.values():
            self.assertGreater(len(host.osd_ids), 0,
                             f"Host {host.hostname} should have OSDs")
        
        # Total OSDs across hosts should match
        total_osds = sum(len(h.osd_ids) for h in state.hosts.values())
        self.assertEqual(total_osds, 20)
    
    def test_primary_assignment(self):
        """Test primaries are acting[0]."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            seed=42
        )
        
        for pg in state.pgs.values():
            primary_osd = pg.acting[0]
            self.assertIn(primary_osd, state.osds,
                         f"PG {pg.pgid} primary {primary_osd} should exist")
    
    def test_pg_naming_convention(self):
        """Test PG naming follows pool.pg format."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=2,
            pgs_per_pool=50,
            replication_factor=3,
            seed=42
        )
        
        for pgid in state.pgs.keys():
            parts = pgid.split('.')
            self.assertEqual(len(parts), 2, f"PGID {pgid} should be pool.pg format")
            self.assertTrue(parts[0].isdigit(), f"Pool ID in {pgid} should be numeric")
            # PG number can be hex (e.g., "1.a")
            try:
                int(parts[1], 16)  # Try parsing as hex
            except ValueError:
                self.fail(f"PG number in {pgid} should be valid hex")
    
    def test_reproducibility_with_seed(self):
        """Test same seed produces identical clusters."""
        state1 = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=100,
            replication_factor=3,
            seed=12345
        )
        
        state2 = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=100,
            replication_factor=3,
            seed=12345
        )
        
        # Compare primary counts
        counts1 = [osd.primary_count for osd in state1.osds.values()]
        counts2 = [osd.primary_count for osd in state2.osds.values()]
        
        self.assertEqual(counts1, counts2, "Same seed should produce identical results")
    
    def test_different_seeds_produce_different_results(self):
        """Test different seeds produce different clusters."""
        state1 = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=100,
            replication_factor=3,
            seed=1
        )
        
        state2 = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=100,
            replication_factor=3,
            seed=999
        )
        
        # Compare primary counts
        counts1 = [osd.primary_count for osd in state1.osds.values()]
        counts2 = [osd.primary_count for osd in state2.osds.values()]
        
        self.assertNotEqual(counts1, counts2, 
                          "Different seeds should produce different results")


class TestECPoolGeneration(unittest.TestCase):
    """Test erasure-coded pool generation."""
    
    def test_ec_pool_structure(self):
        """Test EC pool basic structure."""
        state = generate_ec_pool(
            k=8,
            m=3,
            num_pgs=100,
            num_osds=50,
            num_hosts=5,
            seed=42
        )
        
        self.assertIsInstance(state, ClusterState)
        self.assertEqual(len(state.pgs), 100)
        self.assertEqual(len(state.osds), 50)
    
    def test_ec_acting_set_size(self):
        """Test EC acting sets have k+m members."""
        state = generate_ec_pool(
            k=6,
            m=2,
            num_pgs=50,
            num_osds=30,
            num_hosts=3,
            seed=42
        )
        
        for pg in state.pgs.values():
            self.assertEqual(len(pg.acting), 8,  # k+m = 6+2
                           f"EC PG {pg.pgid} should have 8 members (k=6, m=2)")
    
    def test_ec_imbalance_pattern(self):
        """Test EC pool can apply imbalance patterns."""
        state = generate_ec_pool(
            k=8,
            m=3,
            num_pgs=100,
            num_osds=50,
            num_hosts=5,
            imbalance_type='concentrated',
            seed=42
        )
        
        # Should have some imbalance
        counts = [osd.primary_count for osd in state.osds.values()]
        mean = statistics.mean(counts)
        std_dev = statistics.stdev(counts)
        cv = std_dev / mean if mean > 0 else 0
        
        self.assertGreater(cv, 0.1, "EC pool with concentrated pattern should have imbalance")


class TestDatasetPersistence(unittest.TestCase):
    """Test dataset save/load functionality."""
    
    def test_save_load_roundtrip(self):
        """Test save and load produces equivalent dataset."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            seed=42
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'test_dataset.json')
            
            # Save
            save_test_dataset(state, filepath, metadata={'test': 'value'})
            self.assertTrue(os.path.exists(filepath))
            
            # Load
            loaded_state = load_test_dataset(filepath)
            
            # Compare
            self.assertEqual(len(loaded_state.osds), len(state.osds))
            self.assertEqual(len(loaded_state.pgs), len(state.pgs))
            self.assertEqual(len(loaded_state.hosts), len(state.hosts))
            
            # Compare primary counts
            orig_counts = sorted([osd.primary_count for osd in state.osds.values()])
            loaded_counts = sorted([osd.primary_count for osd in loaded_state.osds.values()])
            self.assertEqual(orig_counts, loaded_counts)
    
    def test_metadata_preservation(self):
        """Test metadata is saved and loaded."""
        state = generate_synthetic_cluster(
            num_osds=5,
            num_hosts=1,
            num_pools=1,
            pgs_per_pool=20,
            replication_factor=3,
            seed=42
        )
        
        metadata = {
            'description': 'Test dataset',
            'created_by': 'unit_test',
            'version': '1.0'
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'test_with_metadata.json')
            
            save_test_dataset(state, filepath, metadata=metadata)
            
            # Read and check metadata
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.assertIn('metadata', data)
            self.assertEqual(data['metadata']['description'], 'Test dataset')
    
    def test_invalid_filepath_handling(self):
        """Test error handling for invalid file paths."""
        state = generate_synthetic_cluster(
            num_osds=5,
            num_hosts=1,
            num_pools=1,
            pgs_per_pool=20,
            replication_factor=3,
            seed=42
        )
        
        # Try to load non-existent file
        with self.assertRaises((FileNotFoundError, IOError)):
            load_test_dataset('/nonexistent/path/file.json')


if __name__ == '__main__':
    unittest.main()
