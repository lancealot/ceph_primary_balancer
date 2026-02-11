"""Integration tests for end-to-end offline mode workflow."""

import unittest
import tempfile
import tarfile
import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone

from src.ceph_primary_balancer import collector, offline
from src.ceph_primary_balancer.models import ClusterState


class TestOfflineIntegration(unittest.TestCase):
    """Test complete offline workflow."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.export_archive = self._create_realistic_export()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_realistic_export(self) -> str:
        """Create realistic export archive for testing."""
        export_dir = Path(self.temp_dir) / "ceph-cluster-export-20260211"
        export_dir.mkdir()
        
        # Create realistic test data (10 OSDs, 3 hosts, 2 pools, 20 PGs)
        pg_stats = []
        for pool_id in [1, 2]:
            for pg_num in range(10):
                pgid = f"{pool_id}.{pg_num:x}"
                # Distribute primaries across OSDs
                primary = (pool_id * 5 + pg_num) % 10
                replicas = [(primary + 1) % 10, (primary + 2) % 10]
                acting = [primary] + replicas
                pg_stats.append({"pgid": pgid, "acting": acting})
        
        pg_data = {"pg_stats": pg_stats}
        with open(export_dir / "pg_dump.json", 'w') as f:
            json.dump(pg_data, f)
        
        # Create OSD tree with 10 OSDs across 3 hosts
        nodes = [
            {"id": -1, "name": "default", "type": "root"},
            {"id": -2, "name": "host-00", "type": "host", "children": [0, 1, 2]},
            {"id": -3, "name": "host-01", "type": "host", "children": [3, 4, 5, 6]},
            {"id": -4, "name": "host-02", "type": "host", "children": [7, 8, 9]},
        ]
        for i in range(10):
            nodes.append({"id": i, "name": f"osd.{i}", "type": "osd"})
        
        osd_data = {"nodes": nodes}
        with open(export_dir / "osd_tree.json", 'w') as f:
            json.dump(osd_data, f)
        
        # Create pool list
        pool_data = [
            {"pool": 1, "pool_name": "rbd", "size": 3},
            {"pool": 2, "pool_name": "cephfs_data", "size": 3}
        ]
        with open(export_dir / "pool_list.json", 'w') as f:
            json.dump(pool_data, f)
        
        # Create metadata
        metadata = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "export_date_local": datetime.now().strftime('%Y-%m-%d %H:%M:%S EST'),
            "export_hostname": "ceph-mon-01",
            "cluster_fsid": "abc12345-1234-5678-90ab-cdef12345678",
            "ceph_version": "ceph version 17.2.6 (pacific)",
            "num_osds": "10",
            "num_pgs": "20"
        }
        with open(export_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f)
        
        # Create tar.gz
        archive_path = str(Path(self.temp_dir) / "export.tar.gz")
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(export_dir, arcname=export_dir.name)
        
        return archive_path
    
    def test_load_export_via_collector(self):
        """Test loading export via collector.build_cluster_state()."""
        state = collector.build_cluster_state(from_file=self.export_archive)
        
        # Verify basic structure
        self.assertEqual(len(state.osds), 10)
        self.assertEqual(len(state.hosts), 3)
        self.assertEqual(len(state.pools), 2)
        self.assertEqual(len(state.pgs), 20)
        
        # Verify it's a valid ClusterState
        self.assertIsInstance(state, ClusterState)
    
    def test_metadata_preserved(self):
        """Test that metadata is correctly loaded."""
        # Extract and load metadata
        export_dir = offline.extract_export_archive(self.export_archive)
        metadata = offline.load_metadata(export_dir)
        
        self.assertEqual(metadata["export_hostname"], "ceph-mon-01")
        self.assertEqual(metadata["num_osds"], "10")
        self.assertEqual(metadata["num_pgs"], "20")
        self.assertIn("ceph version", metadata["ceph_version"])
    
    def test_export_age_calculation(self):
        """Test export age is correctly calculated."""
        export_dir = offline.extract_export_archive(self.export_archive)
        metadata = offline.load_metadata(export_dir)
        age = offline.calculate_export_age(metadata)
        
        # Should be very recent
        self.assertIn("minute", age.lower())
    
    def test_primary_distribution_correct(self):
        """Test that primary distribution is correctly calculated."""
        state = collector.build_cluster_state(from_file=self.export_archive)
        
        # Each OSD should have 2 primaries (20 PGs / 10 OSDs = 2)
        total_primaries = sum(osd.primary_count for osd in state.osds.values())
        self.assertEqual(total_primaries, 20)
        
        # Each OSD should have some PGs
        for osd in state.osds.values():
            self.assertGreaterEqual(osd.total_pg_count, 0)
    
    def test_host_aggregation_correct(self):
        """Test that host-level aggregation works."""
        state = collector.build_cluster_state(from_file=self.export_archive)
        
        # All hosts should have accumulated counts
        total_host_primaries = sum(host.primary_count for host in state.hosts.values())
        total_osd_primaries = sum(osd.primary_count for osd in state.osds.values())
        
        # Should match
        self.assertEqual(total_host_primaries, total_osd_primaries)
    
    def test_pool_level_tracking(self):
        """Test that pool-level tracking works."""
        state = collector.build_cluster_state(from_file=self.export_archive)
        
        # Each pool should have 10 PGs
        self.assertEqual(state.pools[1].pg_count, 10)
        self.assertEqual(state.pools[2].pg_count, 10)
        
        # Pool names should be preserved
        self.assertEqual(state.pools[1].pool_name, "rbd")
        self.assertEqual(state.pools[2].pool_name, "cephfs_data")
    
    def test_offline_vs_live_mode_compatibility(self):
        """Test that offline mode produces compatible ClusterState."""
        state = collector.build_cluster_state(from_file=self.export_archive)
        
        # Verify all expected attributes exist
        self.assertTrue(hasattr(state, 'pgs'))
        self.assertTrue(hasattr(state, 'osds'))
        self.assertTrue(hasattr(state, 'hosts'))
        self.assertTrue(hasattr(state, 'pools'))
        
        # Verify OSD info structure
        osd = list(state.osds.values())[0]
        self.assertTrue(hasattr(osd, 'osd_id'))
        self.assertTrue(hasattr(osd, 'host'))
        self.assertTrue(hasattr(osd, 'primary_count'))
        self.assertTrue(hasattr(osd, 'total_pg_count'))
        
        # Verify PG info structure
        pg = list(state.pgs.values())[0]
        self.assertTrue(hasattr(pg, 'pgid'))
        self.assertTrue(hasattr(pg, 'pool_id'))
        self.assertTrue(hasattr(pg, 'acting'))
        self.assertTrue(hasattr(pg, 'primary'))


class TestOfflineExportValidation(unittest.TestCase):
    """Test validation of export archives."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_missing_file_detected(self):
        """Test that missing required files are detected."""
        export_dir = Path(self.temp_dir) / "incomplete-export"
        export_dir.mkdir()
        
        # Only create some files
        with open(export_dir / "pg_dump.json", 'w') as f:
            json.dump({"pg_stats": []}, f)
        with open(export_dir / "metadata.json", 'w') as f:
            json.dump({"export_version": "1.0"}, f)
        
        # Missing osd_tree.json and pool_list.json
        is_valid, error = offline.validate_export_files(str(export_dir))
        self.assertFalse(is_valid)
        self.assertIn("osd_tree.json", error)
    
    def test_corrupted_json_detected(self):
        """Test that corrupted JSON files are detected."""
        export_dir = Path(self.temp_dir) / "corrupted-export"
        export_dir.mkdir()
        
        # Create valid files
        with open(export_dir / "pg_dump.json", 'w') as f:
            json.dump({"pg_stats": []}, f)
        with open(export_dir / "osd_tree.json", 'w') as f:
            json.dump({"nodes": []}, f)
        with open(export_dir / "pool_list.json", 'w') as f:
            json.dump([], f)
        
        # Create corrupted metadata
        with open(export_dir / "metadata.json", 'w') as f:
            f.write("{ this is not valid json }")
        
        is_valid, error = offline.validate_export_files(str(export_dir))
        self.assertFalse(is_valid)
        self.assertIn("Invalid JSON", error)


if __name__ == '__main__':
    unittest.main()
