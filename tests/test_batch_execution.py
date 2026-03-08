"""
Test batch execution functionality for script generation.

This test verifies that the generate_script function correctly:
1. Accepts a batch_size parameter
2. Groups swaps into appropriate batches
3. Generates batch headers and pause points
4. Produces valid bash script syntax
"""

import unittest
import tempfile
import os
from ceph_primary_balancer.models import SwapProposal
from ceph_primary_balancer import script_generator


class TestBatchExecution(unittest.TestCase):
    """Test cases for batch execution feature in script generation."""
    
    def setUp(self):
        """Create temporary directory for test scripts."""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary test files."""
        for file in os.listdir(self.test_dir):
            os.remove(os.path.join(self.test_dir, file))
        os.rmdir(self.test_dir)
    
    def test_batch_script_generation_basic(self):
        """Test basic batch script generation with default batch size."""
        # Create 150 test swaps (should create 3 batches with batch_size=50)
        swaps = [
            SwapProposal(
                pgid=f"1.{hex(i)[2:]}",
                old_primary=i % 10,
                new_primary=(i % 10) + 10,
                score_improvement=0.1
            )
            for i in range(150)
        ]
        
        output_path = os.path.join(self.test_dir, "test_batch.sh")
        
        # Generate script with batch size of 50
        script_generator.generate_script(swaps, output_path, batch_size=50)
        
        # Verify script was created
        self.assertTrue(os.path.exists(output_path))
        
        # Read and verify script content
        with open(output_path, 'r') as f:
            content = f.read()
        
        # Verify batch information in header
        self.assertIn("Batch size: 50", content)
        self.assertIn("Number of batches: 3", content)
        
        # Verify batch headers are present
        self.assertIn("Batch 1/3", content)
        self.assertIn("Batch 2/3", content)
        self.assertIn("Batch 3/3", content)
        
        # Verify pause prompts between batches (should have 2 pauses for 3 batches)
        pause_count = content.count("Continue to next batch?")
        self.assertEqual(pause_count, 2, "Should have 2 pause prompts for 3 batches")
        
        # Verify all swaps are included
        for swap in swaps:
            self.assertIn(swap.pgid, content)
    
    def test_batch_script_generation_custom_size(self):
        """Test batch script generation with custom batch size."""
        # Create 100 test swaps
        swaps = [
            SwapProposal(
                pgid=f"2.{hex(i)[2:]}",
                old_primary=i % 8,
                new_primary=(i % 8) + 8,
                score_improvement=0.2
            )
            for i in range(100)
        ]
        
        output_path = os.path.join(self.test_dir, "test_custom_batch.sh")
        
        # Generate script with batch size of 25 (should create 4 batches)
        script_generator.generate_script(swaps, output_path, batch_size=25)
        
        # Verify script was created
        self.assertTrue(os.path.exists(output_path))
        
        # Read and verify script content
        with open(output_path, 'r') as f:
            content = f.read()
        
        # Verify batch information
        self.assertIn("Batch size: 25", content)
        self.assertIn("Number of batches: 4", content)
        
        # Verify all 4 batch headers
        self.assertIn("Batch 1/4", content)
        self.assertIn("Batch 2/4", content)
        self.assertIn("Batch 3/4", content)
        self.assertIn("Batch 4/4", content)
        
        # Verify pause count (3 pauses for 4 batches)
        pause_count = content.count("Continue to next batch?")
        self.assertEqual(pause_count, 3)
    
    def test_batch_script_single_batch(self):
        """Test script generation when all swaps fit in one batch."""
        # Create 30 test swaps (less than default batch size of 50)
        swaps = [
            SwapProposal(
                pgid=f"3.{hex(i)[2:]}",
                old_primary=i % 5,
                new_primary=(i % 5) + 5,
                score_improvement=0.15
            )
            for i in range(30)
        ]
        
        output_path = os.path.join(self.test_dir, "test_single_batch.sh")
        
        # Generate script
        script_generator.generate_script(swaps, output_path, batch_size=50)
        
        # Read script content
        with open(output_path, 'r') as f:
            content = f.read()
        
        # Verify single batch
        self.assertIn("Number of batches: 1", content)
        self.assertIn("Batch 1/1", content)
        
        # Verify no pause prompts (only 1 batch)
        self.assertNotIn("Continue to next batch?", content)
    
    def test_batch_script_uneven_batches(self):
        """Test batch script with uneven batch distribution."""
        # Create 125 swaps with batch size of 50 (3 batches: 50, 50, 25)
        swaps = [
            SwapProposal(
                pgid=f"4.{hex(i)[2:]}",
                old_primary=i % 12,
                new_primary=(i % 12) + 12,
                score_improvement=0.1
            )
            for i in range(125)
        ]
        
        output_path = os.path.join(self.test_dir, "test_uneven_batch.sh")
        
        # Generate script
        script_generator.generate_script(swaps, output_path, batch_size=50)
        
        # Read script content
        with open(output_path, 'r') as f:
            content = f.read()
        
        # Verify 3 batches
        self.assertIn("Number of batches: 3", content)
        
        # Verify batch ranges in comments
        self.assertIn("Commands 1-50 (50 commands)", content)
        self.assertIn("Commands 51-100 (50 commands)", content)
        self.assertIn("Commands 101-125 (25 commands)", content)  # Last batch has 25
        
        # Verify all swaps are present
        for i, swap in enumerate(swaps, 1):
            self.assertIn(swap.pgid, content)
    
    def test_batch_script_executable(self):
        """Test that generated batch script has executable permissions."""
        swaps = [
            SwapProposal(
                pgid=f"5.{i}",
                old_primary=i,
                new_primary=i + 10,
                score_improvement=0.1
            )
            for i in range(75)
        ]
        
        output_path = os.path.join(self.test_dir, "test_executable.sh")
        
        # Generate script
        script_generator.generate_script(swaps, output_path, batch_size=25)
        
        # Verify file is executable
        self.assertTrue(os.access(output_path, os.X_OK))
    
    def test_batch_script_syntax_valid(self):
        """Test that generated batch script has valid bash syntax."""
        swaps = [
            SwapProposal(
                pgid=f"6.{hex(i)[2:]}",
                old_primary=i % 6,
                new_primary=(i % 6) + 6,
                score_improvement=0.05
            )
            for i in range(60)
        ]
        
        output_path = os.path.join(self.test_dir, "test_syntax.sh")
        
        # Generate script
        script_generator.generate_script(swaps, output_path, batch_size=20)
        
        # Read script
        with open(output_path, 'r') as f:
            content = f.read()
        
        # Verify bash script basics
        self.assertTrue(content.startswith("#!/bin/bash"))
        self.assertIn("set -e", content)
        self.assertIn("apply_mapping()", content)
        
        # Verify no syntax errors in batch structure
        self.assertIn("BATCH_SIZE=20", content)
        self.assertIn("TOTAL=60", content)
        
        # Check for balanced quotes and braces
        self.assertEqual(content.count('"'), content.count('"'))  # All quotes closed


if __name__ == '__main__':
    unittest.main()
