"""
Test suite for Phase 3: Enhanced Reporting and JSON Export.

Tests cover:
- JSON export functionality and schema compliance
- JSON round-trip integrity
- Enhanced terminal reporting
- Markdown report generation
- Multi-format output
- Reporter comparison tables
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.ceph_primary_balancer.models import (
    PGInfo, OSDInfo, HostInfo, PoolInfo, ClusterState, SwapProposal, Statistics
)
from src.ceph_primary_balancer.exporter import JSONExporter
from src.ceph_primary_balancer.reporter import Reporter
from src.ceph_primary_balancer.analyzer import calculate_statistics


class TestJSONExporter(unittest.TestCase):
    """Test JSONExporter functionality."""
    
    def setUp(self):
        """Set up test cluster state."""
        # Create simple cluster state for testing
        self.current_state = ClusterState(
            pgs={
                "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1, 2]),
                "1.1": PGInfo(pgid="1.1", pool_id=1, acting=[1, 2, 3]),
                "1.2": PGInfo(pgid="1.2", pool_id=1, acting=[2, 3, 0]),
                "1.3": PGInfo(pgid="1.3", pool_id=1, acting=[3, 0, 1]),
            },
            osds={
                0: OSDInfo(osd_id=0, host="host-01", primary_count=2, total_pg_count=3),
                1: OSDInfo(osd_id=1, host="host-01", primary_count=2, total_pg_count=3),
                2: OSDInfo(osd_id=2, host="host-02", primary_count=1, total_pg_count=3),
                3: OSDInfo(osd_id=3, host="host-02", primary_count=1, total_pg_count=3),
            },
            hosts={
                "host-01": HostInfo(hostname="host-01", osd_ids=[0, 1], primary_count=4, total_pg_count=6),
                "host-02": HostInfo(hostname="host-02", osd_ids=[2, 3], primary_count=2, total_pg_count=6),
            },
            pools={
                1: PoolInfo(pool_id=1, pool_name="test_pool", pg_count=4,
                           primary_counts={0: 2, 1: 2, 2: 1, 3: 1})
            }
        )
        
        # Simulate optimization
        self.proposed_state = ClusterState(
            pgs=self.current_state.pgs.copy(),
            osds={
                0: OSDInfo(osd_id=0, host="host-01", primary_count=1, total_pg_count=3),
                1: OSDInfo(osd_id=1, host="host-01", primary_count=2, total_pg_count=3),
                2: OSDInfo(osd_id=2, host="host-02", primary_count=2, total_pg_count=3),
                3: OSDInfo(osd_id=3, host="host-02", primary_count=1, total_pg_count=3),
            },
            hosts={
                "host-01": HostInfo(hostname="host-01", osd_ids=[0, 1], primary_count=3, total_pg_count=6),
                "host-02": HostInfo(hostname="host-02", osd_ids=[2, 3], primary_count=3, total_pg_count=6),
            },
            pools={
                1: PoolInfo(pool_id=1, pool_name="test_pool", pg_count=4,
                           primary_counts={0: 1, 1: 2, 2: 2, 3: 1})
            }
        )
        
        self.swaps = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=2, score_improvement=0.15),
        ]
        
        self.exporter = JSONExporter(tool_version="0.4.0-test")
    
    def test_export_schema_structure(self):
        """Test that exported JSON has correct schema structure."""
        result = self.exporter.export_analysis(
            self.current_state,
            self.proposed_state,
            self.swaps,
            cluster_fsid="test-fsid-123",
            analysis_type="full"
        )
        
        # Check top-level keys
        self.assertIn("schema_version", result)
        self.assertIn("metadata", result)
        self.assertIn("current_state", result)
        self.assertIn("proposed_state", result)
        self.assertIn("changes", result)
        self.assertIn("improvements", result)
        
        # Verify schema version
        self.assertEqual(result["schema_version"], "2.0")
        
        # Check metadata structure
        metadata = result["metadata"]
        self.assertIn("timestamp", metadata)
        self.assertIn("tool_version", metadata)
        self.assertIn("cluster_fsid", metadata)
        self.assertIn("analysis_type", metadata)
        self.assertEqual(metadata["tool_version"], "0.4.0-test")
        self.assertEqual(metadata["cluster_fsid"], "test-fsid-123")
        self.assertEqual(metadata["analysis_type"], "full")
    
    def test_export_current_state_structure(self):
        """Test current_state section structure."""
        result = self.exporter.export_analysis(
            self.current_state, self.proposed_state, self.swaps
        )
        
        current = result["current_state"]
        
        # Check totals
        self.assertIn("totals", current)
        self.assertEqual(current["totals"]["pgs"], 4)
        self.assertEqual(current["totals"]["osds"], 4)
        self.assertEqual(current["totals"]["hosts"], 2)
        self.assertEqual(current["totals"]["pools"], 1)
        
        # Check OSD level
        self.assertIn("osd_level", current)
        osd_level = current["osd_level"]
        self.assertIn("mean", osd_level)
        self.assertIn("std_dev", osd_level)
        self.assertIn("cv", osd_level)
        self.assertIn("min", osd_level)
        self.assertIn("max", osd_level)
        self.assertIn("p50", osd_level)
        self.assertIn("osd_details", osd_level)
        
        # Verify OSD details structure
        self.assertEqual(len(osd_level["osd_details"]), 4)
        osd_detail = osd_level["osd_details"][0]
        self.assertIn("osd_id", osd_detail)
        self.assertIn("host", osd_detail)
        self.assertIn("primary_count", osd_detail)
        self.assertIn("total_pgs", osd_detail)
        
        # Check host level
        self.assertIn("host_level", current)
        host_level = current["host_level"]
        self.assertIn("mean", host_level)
        self.assertIn("host_details", host_level)
        self.assertEqual(len(host_level["host_details"]), 2)
        
        # Check pool level
        self.assertIn("pool_level", current)
        pool_level = current["pool_level"]
        self.assertIn("pools", pool_level)
        self.assertEqual(len(pool_level["pools"]), 1)
        
        pool_data = pool_level["pools"][0]
        self.assertIn("pool_id", pool_data)
        self.assertIn("pool_name", pool_data)
        self.assertIn("pg_count", pool_data)
        self.assertIn("cv", pool_data)
        self.assertIn("per_osd_distribution", pool_data)
    
    def test_export_changes_structure(self):
        """Test changes section structure."""
        result = self.exporter.export_analysis(
            self.current_state, self.proposed_state, self.swaps
        )
        
        changes = result["changes"]
        self.assertEqual(len(changes), 1)
        
        change = changes[0]
        self.assertIn("pgid", change)
        self.assertIn("old_primary", change)
        self.assertIn("new_primary", change)
        self.assertIn("old_host", change)
        self.assertIn("new_host", change)
        self.assertIn("pool_name", change)
        self.assertIn("score_improvement", change)
        
        self.assertEqual(change["pgid"], "1.0")
        self.assertEqual(change["old_primary"], 0)
        self.assertEqual(change["new_primary"], 2)
        self.assertEqual(change["old_host"], "host-01")
        self.assertEqual(change["new_host"], "host-02")
        self.assertEqual(change["pool_name"], "test_pool")
    
    def test_export_improvements_structure(self):
        """Test improvements section structure."""
        result = self.exporter.export_analysis(
            self.current_state, self.proposed_state, self.swaps
        )
        
        improvements = result["improvements"]
        self.assertIn("osd_cv_reduction_pct", improvements)
        self.assertIn("host_cv_reduction_pct", improvements)
        self.assertIn("total_changes", improvements)
        self.assertIn("osds_affected", improvements)
        self.assertIn("hosts_affected", improvements)
        
        self.assertEqual(improvements["total_changes"], 1)
        self.assertEqual(improvements["osds_affected"], 2)  # OSDs 0 and 2
        self.assertEqual(improvements["hosts_affected"], 2)  # Both hosts
    
    def test_export_to_file(self):
        """Test JSON export to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_export.json")
            
            self.exporter.export_to_file(
                self.current_state,
                self.proposed_state,
                self.swaps,
                output_path
            )
            
            # Verify file exists
            self.assertTrue(os.path.exists(output_path))
            
            # Verify file is valid JSON
            with open(output_path, 'r') as f:
                data = json.load(f)
            
            # Basic schema validation
            self.assertIn("schema_version", data)
            self.assertEqual(data["schema_version"], "2.0")
            self.assertIn("metadata", data)
            self.assertIn("current_state", data)
    
    def test_json_round_trip(self):
        """Test JSON export and re-import maintains data integrity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "round_trip.json")
            
            # Export
            self.exporter.export_to_file(
                self.current_state,
                self.proposed_state,
                self.swaps,
                output_path
            )
            
            # Re-import
            with open(output_path, 'r') as f:
                data = json.load(f)
            
            # Verify critical data preserved
            self.assertEqual(data["current_state"]["totals"]["pgs"], 4)
            self.assertEqual(data["current_state"]["totals"]["osds"], 4)
            self.assertEqual(len(data["changes"]), 1)
            self.assertEqual(data["changes"][0]["pgid"], "1.0")
            
            # Verify OSD details preserved
            osd_details = data["current_state"]["osd_level"]["osd_details"]
            self.assertEqual(len(osd_details), 4)
            
            # Find OSD 0 and verify its data
            osd_0 = next(o for o in osd_details if o["osd_id"] == 0)
            self.assertEqual(osd_0["host"], "host-01")
            self.assertEqual(osd_0["primary_count"], 2)


class TestReporter(unittest.TestCase):
    """Test Reporter functionality."""
    
    def setUp(self):
        """Set up test cluster state."""
        self.current_state = ClusterState(
            pgs={
                "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1, 2]),
                "1.1": PGInfo(pgid="1.1", pool_id=1, acting=[1, 2, 3]),
                "1.2": PGInfo(pgid="1.2", pool_id=1, acting=[2, 3, 0]),
                "1.3": PGInfo(pgid="1.3", pool_id=1, acting=[3, 0, 1]),
            },
            osds={
                0: OSDInfo(osd_id=0, host="host-01", primary_count=2, total_pg_count=3),
                1: OSDInfo(osd_id=1, host="host-01", primary_count=2, total_pg_count=3),
                2: OSDInfo(osd_id=2, host="host-02", primary_count=1, total_pg_count=3),
                3: OSDInfo(osd_id=3, host="host-02", primary_count=1, total_pg_count=3),
            },
            hosts={
                "host-01": HostInfo(hostname="host-01", osd_ids=[0, 1], primary_count=4, total_pg_count=6),
                "host-02": HostInfo(hostname="host-02", osd_ids=[2, 3], primary_count=2, total_pg_count=6),
            },
            pools={
                1: PoolInfo(pool_id=1, pool_name="test_pool", pg_count=4,
                           primary_counts={0: 2, 1: 2, 2: 1, 3: 1})
            }
        )
        
        self.proposed_state = ClusterState(
            pgs=self.current_state.pgs.copy(),
            osds={
                0: OSDInfo(osd_id=0, host="host-01", primary_count=1, total_pg_count=3),
                1: OSDInfo(osd_id=1, host="host-01", primary_count=2, total_pg_count=3),
                2: OSDInfo(osd_id=2, host="host-02", primary_count=2, total_pg_count=3),
                3: OSDInfo(osd_id=3, host="host-02", primary_count=1, total_pg_count=3),
            },
            hosts={
                "host-01": HostInfo(hostname="host-01", osd_ids=[0, 1], primary_count=3, total_pg_count=6),
                "host-02": HostInfo(hostname="host-02", osd_ids=[2, 3], primary_count=3, total_pg_count=6),
            },
            pools={
                1: PoolInfo(pool_id=1, pool_name="test_pool", pg_count=4,
                           primary_counts={0: 1, 1: 2, 2: 2, 3: 1})
            }
        )
        
        self.swaps = [
            SwapProposal(pgid="1.0", old_primary=0, new_primary=2, score_improvement=0.15),
        ]
        
        self.reporter = Reporter(top_n=5)
    
    def test_terminal_report_generation(self):
        """Test terminal report generation."""
        report = self.reporter.generate_terminal_report(
            self.current_state,
            self.proposed_state,
            self.swaps
        )
        
        # Verify report is a string
        self.assertIsInstance(report, str)
        
        # Check for key sections
        self.assertIn("COMPREHENSIVE ANALYSIS REPORT", report)
        self.assertIn("CLUSTER OVERVIEW", report)
        self.assertIn("OSD Level Comparison", report)
        self.assertIn("Host Level Comparison", report)
        self.assertIn("Pool Level Comparison", report)
        self.assertIn("TOP DONORS AND RECEIVERS", report)
        self.assertIn("CHANGE SUMMARY", report)
        
        # Verify data appears in report
        self.assertIn("4", report)  # PG count
        self.assertIn("host-01", report)
        self.assertIn("host-02", report)
    
    def test_comparison_table_generation(self):
        """Test comparison table generation."""
        before_stats = calculate_statistics([2, 2, 1, 1])
        after_stats = calculate_statistics([1, 2, 2, 1])
        
        table = self.reporter.generate_comparison_table(
            before_stats,
            after_stats,
            "OSD"
        )
        
        self.assertIsInstance(table, str)
        self.assertIn("OSD Level Comparison", table)
        self.assertIn("Mean", table)
        self.assertIn("Std Dev", table)
        self.assertIn("CV", table)
        self.assertIn("Range", table)
        self.assertIn("Median", table)
        self.assertIn("Before", table)
        self.assertIn("After", table)
        self.assertIn("Change", table)
    
    def test_markdown_report_generation(self):
        """Test markdown report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_report.md")
            
            self.reporter.generate_markdown_report(
                self.current_state,
                self.proposed_state,
                self.swaps,
                output_path
            )
            
            # Verify file exists
            self.assertTrue(os.path.exists(output_path))
            
            # Read and verify content
            with open(output_path, 'r') as f:
                content = f.read()
            
            # Check for markdown elements
            self.assertIn("# Ceph Primary Balancer Analysis Report", content)
            self.assertIn("## Executive Summary", content)
            self.assertIn("## OSD-Level Analysis", content)
            self.assertIn("## Host-Level Analysis", content)
            self.assertIn("## Pool-Level Analysis", content)
            self.assertIn("## Top Donors and Receivers", content)
            self.assertIn("## Proposed Changes", content)
            self.assertIn("## Recommendations", content)
            
            # Check for markdown table syntax
            self.assertIn("| Metric |", content)
            self.assertIn("|--------|", content)
            
            # Verify data appears
            self.assertIn("test_pool", content)
            self.assertIn("host-01", content)
    
    def test_format_change_helper(self):
        """Test format change helper method."""
        # Test positive change
        result = self.reporter._format_change(10.0, 12.0)
        self.assertEqual(result, "+2.00")
        
        # Test negative change
        result = self.reporter._format_change(10.0, 8.0)
        self.assertEqual(result, "-2.00")
        
        # Test near-zero change
        result = self.reporter._format_change(10.0, 10.005)
        self.assertEqual(result, "~0")
    
    def test_calculate_percentage_change_helper(self):
        """Test percentage change calculation."""
        # Test reduction
        result = self.reporter._calculate_percentage_change(100.0, 80.0)
        self.assertEqual(result, "-20.0%")
        
        # Test increase
        result = self.reporter._calculate_percentage_change(80.0, 100.0)
        self.assertEqual(result, "+25.0%")
        
        # Test zero before value
        result = self.reporter._calculate_percentage_change(0.0, 10.0)
        self.assertEqual(result, "N/A")


class TestIntegration(unittest.TestCase):
    """Integration tests for Phase 3 features."""
    
    def test_full_export_and_report_workflow(self):
        """Test complete workflow: export JSON and generate reports."""
        # Create test state
        state = ClusterState(
            pgs={
                "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1]),
                "1.1": PGInfo(pgid="1.1", pool_id=1, acting=[1, 0]),
            },
            osds={
                0: OSDInfo(osd_id=0, host="host-01", primary_count=1, total_pg_count=2),
                1: OSDInfo(osd_id=1, host="host-01", primary_count=1, total_pg_count=2),
            },
            hosts={
                "host-01": HostInfo(hostname="host-01", osd_ids=[0, 1], primary_count=2, total_pg_count=4),
            },
            pools={
                1: PoolInfo(pool_id=1, pool_name="pool1", pg_count=2, primary_counts={0: 1, 1: 1})
            }
        )
        
        swaps = []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "export.json")
            md_path = os.path.join(tmpdir, "report.md")
            
            # Export JSON
            exporter = JSONExporter()
            exporter.export_to_file(state, state, swaps, json_path)
            
            # Generate markdown report
            reporter = Reporter()
            reporter.generate_markdown_report(state, state, swaps, md_path)
            
            # Verify both files created
            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(md_path))
            
            # Verify JSON is valid
            with open(json_path, 'r') as f:
                json_data = json.load(f)
            self.assertIn("schema_version", json_data)
            
            # Verify markdown has content
            with open(md_path, 'r') as f:
                md_content = f.read()
            self.assertGreater(len(md_content), 100)


if __name__ == '__main__':
    unittest.main()
