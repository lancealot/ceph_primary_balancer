"""Unit tests for offline mode functionality."""

import unittest
import tempfile
import tarfile
import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

from ceph_primary_balancer import offline
from ceph_primary_balancer.offline import OfflineExportError


class TestOfflineExport(unittest.TestCase):
    """Test export archive handling."""
    
    def setUp(self):
        """Create test export archive."""
        self.temp_dir = tempfile.mkdtemp()
        self.export_dir = Path(self.temp_dir) / "ceph-cluster-export-test"
        self.export_dir.mkdir()
        
        # Create test export files
        self._create_test_export()
        
    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_export(self):
        """Create minimal valid export files."""
        # pg_dump.json
        pg_data = {
            "pg_stats": [
                {"pgid": "1.0", "acting": [0, 1, 2]},
                {"pgid": "1.1", "acting": [1, 2, 3]},
                {"pgid": "2.0", "acting": [2, 3, 4]}
            ]
        }
        with open(self.export_dir / "pg_dump.json", 'w') as f:
            json.dump(pg_data, f)
        
        # osd_tree.json
        osd_data = {
            "nodes": [
                {"id": -1, "name": "default", "type": "root"},
                {"id": -2, "name": "host-00", "type": "host", "children": [0, 1]},
                {"id": -3, "name": "host-01", "type": "host", "children": [2, 3]},
                {"id": 0, "name": "osd.0", "type": "osd", "parent": -2},
                {"id": 1, "name": "osd.1", "type": "osd", "parent": -2},
                {"id": 2, "name": "osd.2", "type": "osd", "parent": -3},
                {"id": 3, "name": "osd.3", "type": "osd", "parent": -3},
                {"id": 4, "name": "osd.4", "type": "osd", "parent": -3},
            ]
        }
        with open(self.export_dir / "osd_tree.json", 'w') as f:
            json.dump(osd_data, f)
        
        # pool_list.json
        pool_data = [
            {"pool": 1, "pool_name": "test_pool", "size": 3},
            {"pool": 2, "pool_name": "rbd", "size": 3}
        ]
        with open(self.export_dir / "pool_list.json", 'w') as f:
            json.dump(pool_data, f)
        
        # metadata.json
        metadata = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "export_date_local": datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z'),
            "export_hostname": "test-host",
            "cluster_fsid": "test-fsid-12345",
            "ceph_version": "ceph version 17.2.6 (pacific)",
            "num_osds": "5",
            "num_pgs": "3"
        }
        with open(self.export_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f)
    
    def _create_archive(self) -> str:
        """Create tar.gz archive of export directory."""
        archive_path = str(Path(self.temp_dir) / "export.tar.gz")
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(self.export_dir, arcname=self.export_dir.name)
        return archive_path
    
    def test_extract_valid_archive(self):
        """Test extracting valid tar.gz archive."""
        archive_path = self._create_archive()
        extracted_dir = offline.extract_export_archive(archive_path)
        
        self.assertTrue(os.path.exists(extracted_dir))
        self.assertTrue(os.path.isdir(extracted_dir))
        
        # Verify files exist
        self.assertTrue((Path(extracted_dir) / "pg_dump.json").exists())
        self.assertTrue((Path(extracted_dir) / "osd_tree.json").exists())
        self.assertTrue((Path(extracted_dir) / "pool_list.json").exists())
        self.assertTrue((Path(extracted_dir) / "metadata.json").exists())
    
    def test_extract_missing_file(self):
        """Test error when archive doesn't exist."""
        with self.assertRaises(OfflineExportError) as cm:
            offline.extract_export_archive("/nonexistent/file.tar.gz")
        self.assertIn("not found", str(cm.exception))
    
    def test_extract_invalid_format(self):
        """Test error with non-tar.gz file."""
        bad_file = Path(self.temp_dir) / "bad.txt"
        bad_file.write_text("not a tarball")
        
        with self.assertRaises(OfflineExportError) as cm:
            offline.extract_export_archive(str(bad_file))
        self.assertIn("Invalid export format", str(cm.exception))
    
    def test_validate_complete_export(self):
        """Test validation passes with all required files."""
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
    
    def test_validate_missing_pg_dump(self):
        """Test validation fails with missing pg_dump.json."""
        (self.export_dir / "pg_dump.json").unlink()
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertFalse(is_valid)
        self.assertIn("pg_dump.json", error)
    
    def test_validate_missing_osd_tree(self):
        """Test validation fails with missing osd_tree.json."""
        (self.export_dir / "osd_tree.json").unlink()
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertFalse(is_valid)
        self.assertIn("osd_tree.json", error)
    
    def test_validate_invalid_json(self):
        """Test validation fails with invalid JSON."""
        with open(self.export_dir / "metadata.json", 'w') as f:
            f.write("{ invalid json ")
        
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertFalse(is_valid)
        self.assertIn("Invalid JSON", error)
    
    def test_load_metadata(self):
        """Test loading metadata from export."""
        metadata = offline.load_metadata(str(self.export_dir))
        self.assertEqual(metadata["export_version"], "1.0")
        self.assertEqual(metadata["cluster_fsid"], "test-fsid-12345")
        self.assertEqual(metadata["export_hostname"], "test-host")
        self.assertEqual(metadata["num_osds"], "5")
    
    def test_calculate_export_age_recent(self):
        """Test export age calculation for recent export."""
        metadata = {"export_date": datetime.now(timezone.utc).isoformat()}
        age = offline.calculate_export_age(metadata)
        self.assertIn("minute", age.lower())
    
    def test_calculate_export_age_hours(self):
        """Test export age calculation for hours old export."""
        export_time = datetime.now(timezone.utc) - timedelta(hours=3)
        metadata = {"export_date": export_time.isoformat()}
        age = offline.calculate_export_age(metadata)
        self.assertIn("hour", age.lower())
    
    def test_calculate_export_age_days(self):
        """Test export age calculation for days old export."""
        export_time = datetime.now(timezone.utc) - timedelta(days=5)
        metadata = {"export_date": export_time.isoformat()}
        age = offline.calculate_export_age(metadata)
        self.assertIn("5 day", age)
    
    def test_calculate_export_age_no_date(self):
        """Test export age with missing date."""
        metadata = {}
        age = offline.calculate_export_age(metadata)
        self.assertEqual(age, "unknown age")


class TestOfflineDataLoading(unittest.TestCase):
    """Test loading ClusterState from export files."""
    
    def setUp(self):
        """Create test export."""
        self.temp_dir = tempfile.mkdtemp()
        self.export_dir = Path(self.temp_dir) / "ceph-cluster-export-test"
        self.export_dir.mkdir()
        self._create_test_export()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_export(self):
        """Create test export files."""
        # pg_dump.json - 3 PGs across 2 pools
        pg_data = {
            "pg_stats": [
                {"pgid": "1.0", "acting": [0, 1, 2]},
                {"pgid": "1.1", "acting": [1, 2, 3]},
                {"pgid": "2.a", "acting": [2, 3, 4]}
            ]
        }
        with open(self.export_dir / "pg_dump.json", 'w') as f:
            json.dump(pg_data, f)
        
        # osd_tree.json - 5 OSDs across 2 hosts
        osd_data = {
            "nodes": [
                {"id": -1, "name": "default", "type": "root"},
                {"id": -2, "name": "host-00", "type": "host", "children": [0, 1]},
                {"id": -3, "name": "host-01", "type": "host", "children": [2, 3, 4]},
                {"id": 0, "name": "osd.0", "type": "osd"},
                {"id": 1, "name": "osd.1", "type": "osd"},
                {"id": 2, "name": "osd.2", "type": "osd"},
                {"id": 3, "name": "osd.3", "type": "osd"},
                {"id": 4, "name": "osd.4", "type": "osd"},
            ]
        }
        with open(self.export_dir / "osd_tree.json", 'w') as f:
            json.dump(osd_data, f)
        
        # pool_list.json
        pool_data = [
            {"pool": 1, "pool_name": "test_pool"},
            {"pool": 2, "pool_name": "rbd"}
        ]
        with open(self.export_dir / "pool_list.json", 'w') as f:
            json.dump(pool_data, f)
        
        # metadata.json
        metadata = {
            "export_version": "1.0",
            "export_date": datetime.now(timezone.utc).isoformat(),
            "cluster_fsid": "test-fsid"
        }
        with open(self.export_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f)
    
    def test_load_from_export_files(self):
        """Test loading ClusterState from export files."""
        state = offline.load_from_export_files(str(self.export_dir))
        
        # Verify structure
        self.assertEqual(len(state.pgs), 3)
        self.assertEqual(len(state.pools), 2)
        self.assertEqual(len(state.osds), 5)
        self.assertEqual(len(state.hosts), 2)
        
        # Verify PG data
        self.assertIn("1.0", state.pgs)
        self.assertEqual(state.pgs["1.0"].pool_id, 1)
        self.assertEqual(state.pgs["1.0"].acting[0], 0)  # Primary
        
        # Verify pool data
        self.assertIn(1, state.pools)
        self.assertEqual(state.pools[1].pool_name, "test_pool")
        
        # Verify OSD data
        self.assertIn(0, state.osds)
        self.assertIn(1, state.osds)
    
    def test_primary_counts_calculated(self):
        """Test that primary counts are correctly calculated."""
        state = offline.load_from_export_files(str(self.export_dir))
        
        # OSD 0 is primary for PG 1.0
        self.assertEqual(state.osds[0].primary_count, 1)
        
        # OSD 1 is primary for PG 1.1
        self.assertEqual(state.osds[1].primary_count, 1)
        
        # OSD 2 is primary for PG 2.a
        self.assertEqual(state.osds[2].primary_count, 1)
        
        # OSDs 3 and 4 are not primaries
        self.assertEqual(state.osds[3].primary_count, 0)
        self.assertEqual(state.osds[4].primary_count, 0)
    
    def test_total_pg_counts_calculated(self):
        """Test that total PG counts are correctly calculated."""
        state = offline.load_from_export_files(str(self.export_dir))
        
        # OSD 0: in acting set for 1.0
        self.assertEqual(state.osds[0].total_pg_count, 1)
        
        # OSD 1: in acting set for 1.0, 1.1
        self.assertEqual(state.osds[1].total_pg_count, 2)
        
        # OSD 2: in acting set for 1.0, 1.1, 2.a
        self.assertEqual(state.osds[2].total_pg_count, 3)
        
        # OSD 3: in acting set for 1.1, 2.a
        self.assertEqual(state.osds[3].total_pg_count, 2)
        
        # OSD 4: in acting set for 2.a
        self.assertEqual(state.osds[4].total_pg_count, 1)
    
    def test_host_counts_aggregated(self):
        """Test that host-level counts are aggregated from OSDs."""
        state = offline.load_from_export_files(str(self.export_dir))
        
        # host-00 has OSDs 0, 1
        # OSD 0: 1 primary, OSD 1: 1 primary = 2 primaries total
        self.assertEqual(state.hosts["host-00"].primary_count, 2)
        
        # host-01 has OSDs 2, 3, 4
        # OSD 2: 1 primary, OSDs 3,4: 0 primaries = 1 primary total
        self.assertEqual(state.hosts["host-01"].primary_count, 1)
    
    def test_pool_primary_counts(self):
        """Test per-pool primary counts are calculated."""
        state = offline.load_from_export_files(str(self.export_dir))
        
        # Pool 1 has PGs 1.0, 1.1
        # 1.0 primary: OSD 0, 1.1 primary: OSD 1
        self.assertEqual(state.pools[1].pg_count, 2)
        self.assertIn(0, state.pools[1].primary_counts)
        self.assertIn(1, state.pools[1].primary_counts)
        self.assertEqual(state.pools[1].primary_counts[0], 1)
        self.assertEqual(state.pools[1].primary_counts[1], 1)
        
        # Pool 2 has PG 2.a
        # 2.a primary: OSD 2
        self.assertEqual(state.pools[2].pg_count, 1)
        self.assertIn(2, state.pools[2].primary_counts)
        self.assertEqual(state.pools[2].primary_counts[2], 1)
    
    def test_load_from_export_invalid_files(self):
        """Test error when loading invalid export."""
        (self.export_dir / "osd_tree.json").unlink()
        
        with self.assertRaises(OfflineExportError):
            offline.load_from_export_files(str(self.export_dir))


class TestOfflineDataParsing(unittest.TestCase):
    """Test parsing of raw Ceph command outputs."""
    
    def test_parse_pg_data(self):
        """Test PG data parsing."""
        data = {
            "pg_stats": [
                {"pgid": "3.a1", "acting": [12, 45, 67]},
                {"pgid": "5.2b", "acting": [23, 56, 89]}
            ]
        }
        
        pgs = offline._parse_pg_data(data)
        
        self.assertEqual(len(pgs), 2)
        self.assertEqual(pgs["3.a1"].pool_id, 3)
        self.assertEqual(pgs["3.a1"].primary, 12)
        self.assertEqual(pgs["5.2b"].pool_id, 5)
        self.assertEqual(pgs["5.2b"].primary, 23)
    
    def test_parse_osd_tree(self):
        """Test OSD tree parsing."""
        data = {
            "nodes": [
                {"id": -1, "name": "root", "type": "root"},
                {"id": -2, "name": "host-01", "type": "host", "children": [0, 1]},
                {"id": -3, "name": "host-02", "type": "host", "children": [2, 3]},
                {"id": 0, "name": "osd.0", "type": "osd"},
                {"id": 1, "name": "osd.1", "type": "osd"},
                {"id": 2, "name": "osd.2", "type": "osd"},
                {"id": 3, "name": "osd.3", "type": "osd"},
            ]
        }
        
        osds, hosts = offline._parse_osd_tree(data)
        
        self.assertEqual(len(osds), 4)
        self.assertEqual(len(hosts), 2)
        
        # Verify OSD-host relationships
        self.assertEqual(osds[0].host, "host-01")
        self.assertEqual(osds[1].host, "host-01")
        self.assertEqual(osds[2].host, "host-02")
        self.assertEqual(osds[3].host, "host-02")
        
        # Verify host OSD lists
        self.assertIn(0, hosts["host-01"].osd_ids)
        self.assertIn(1, hosts["host-01"].osd_ids)
        self.assertIn(2, hosts["host-02"].osd_ids)
        self.assertIn(3, hosts["host-02"].osd_ids)
    
    def test_parse_pool_data(self):
        """Test pool data parsing."""
        data = [
            {"pool": 1, "pool_name": "rbd"},
            {"pool": 3, "pool_name": "cephfs_data"},
            {"pool_id": 5, "pool_name": "test"}  # Alternative key
        ]
        
        pools = offline._parse_pool_data(data)
        
        self.assertEqual(len(pools), 3)
        self.assertEqual(pools[1].pool_name, "rbd")
        self.assertEqual(pools[3].pool_name, "cephfs_data")
        self.assertEqual(pools[5].pool_name, "test")
        
        # All should have empty counts initially
        self.assertEqual(pools[1].pg_count, 0)
        self.assertEqual(len(pools[1].primary_counts), 0)


if __name__ == '__main__':
    unittest.main()
