#!/usr/bin/env python3
"""
Test script for rollback script generation functionality.

This script tests that:
1. Rollback scripts are generated correctly
2. Swaps are reversed (old/new primaries swapped)
3. Script content includes proper warnings and health checks
4. File naming is correct
"""

import os
import sys
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ceph_primary_balancer.models import SwapProposal
from ceph_primary_balancer.script_generator import generate_rollback_script


def test_rollback_script_generation():
    """Test that rollback script is generated with reversed swaps."""
    
    print("Testing rollback script generation...")
    print("=" * 60)
    
    # Create sample swaps
    test_swaps = [
        SwapProposal(pgid="1.a1", old_primary=10, new_primary=20, score_improvement=0.5),
        SwapProposal(pgid="1.b2", old_primary=15, new_primary=25, score_improvement=0.3),
        SwapProposal(pgid="2.c3", old_primary=30, new_primary=40, score_improvement=0.7),
    ]
    
    print(f"Created {len(test_swaps)} test swaps:")
    for swap in test_swaps:
        print(f"  {swap.pgid}: OSD.{swap.old_primary} -> OSD.{swap.new_primary}")
    print()
    
    # Create temporary output path
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_rebalance.sh")
        
        # Generate rollback script
        print(f"Generating rollback script...")
        rollback_path = generate_rollback_script(test_swaps, output_path)
        
        if not rollback_path:
            print("ERROR: Rollback script generation returned None")
            return False
        
        print(f"✓ Rollback script path: {rollback_path}")
        
        # Verify rollback script exists
        if not os.path.exists(rollback_path):
            print(f"ERROR: Rollback script not found at {rollback_path}")
            return False
        
        print(f"✓ Rollback script file exists")
        
        # Verify rollback script is executable
        if not os.access(rollback_path, os.X_OK):
            print(f"WARNING: Rollback script is not executable")
        else:
            print(f"✓ Rollback script is executable")
        
        # Read and verify rollback script content
        with open(rollback_path, 'r') as f:
            content = f.read()
        
        print(f"\n✓ Rollback script size: {len(content)} bytes")
        
        # Verify key content elements
        checks = [
            ("#!/bin/bash", "Shebang present"),
            ("ROLLBACK", "Rollback identifier present"),
            ("REVERSE", "Reverse warning present"),
            ("Checking cluster health", "Health check present"),
            ("HEALTH_OK", "Health status check present"),
            (f"TOTAL={len(test_swaps)}", "Correct total count"),
        ]
        
        print("\nContent verification:")
        all_passed = True
        for check_str, description in checks:
            if check_str in content:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - NOT FOUND")
                all_passed = False
        
        # Verify reversed swaps are in the script
        print("\nSwap reversal verification:")
        for swap in test_swaps:
            # In rollback, old and new are swapped, so we should see:
            # apply_mapping with the ORIGINAL old_primary as the target
            expected = f'apply_mapping "{swap.pgid}" {swap.old_primary}'
            if expected in content:
                print(f"  ✓ {swap.pgid}: OSD.{swap.new_primary} -> OSD.{swap.old_primary} (reversed)")
            else:
                print(f"  ✗ {swap.pgid}: Expected reversal not found")
                print(f"     Looking for: {expected}")
                all_passed = False
        
        # Show a sample of the script
        print("\n" + "=" * 60)
        print("First 20 lines of rollback script:")
        print("=" * 60)
        lines = content.split('\n')
        for i, line in enumerate(lines[:20], 1):
            print(f"{i:3d} | {line}")
        
        if len(lines) > 20:
            print(f"... ({len(lines) - 20} more lines)")
        
        return all_passed


def test_empty_swaps():
    """Test that empty swaps list is handled gracefully."""
    print("\n" + "=" * 60)
    print("Testing empty swaps list handling...")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_rebalance.sh")
        result = generate_rollback_script([], output_path)
        
        if result is None:
            print("✓ Empty swaps list correctly returns None")
            return True
        else:
            print("✗ Empty swaps list should return None")
            return False


if __name__ == '__main__':
    print("Rollback Script Generation Test Suite")
    print("=" * 60)
    print()
    
    # Run tests
    test1_passed = test_rollback_script_generation()
    test2_passed = test_empty_swaps()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    tests = [
        ("Rollback script generation", test1_passed),
        ("Empty swaps handling", test2_passed),
    ]
    
    for test_name, passed in tests:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in tests)
    
    print("=" * 60)
    if all_passed:
        print("ALL TESTS PASSED ✓")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED ✗")
        sys.exit(1)
