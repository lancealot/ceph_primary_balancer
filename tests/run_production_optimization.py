#!/usr/bin/env python3
"""
Run full optimization on production cluster fixtures using the main CLI logic.

This script patches the collector to use fixture data instead of running
actual Ceph commands, allowing comprehensive optimization testing on
production-scale data without a live cluster.

Usage:
    python tests/run_production_optimization.py [CLI OPTIONS]
    
Examples:
    # Full 3D optimization with default settings
    python tests/run_production_optimization.py
    
    # OSD-only optimization (faster)
    python tests/run_production_optimization.py --optimization-levels osd
    
    # Limit to 100 swaps
    python tests/run_production_optimization.py --max-changes 100
    
    # Custom target CV
    python tests/run_production_optimization.py --target-cv 0.05
    
    # Generate reports
    python tests/run_production_optimization.py --json-output analysis.json --report-output report.md
    
    # Use output directory with timestamps
    python tests/run_production_optimization.py --output-dir ./production_results --verbose
"""

import json
import os
import sys
from unittest.mock import patch

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ceph_primary_balancer import collector


def load_fixture(filename):
    """Load a fixture file from production_cluster directory."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        'fixtures',
        'production_cluster',
        filename
    )
    print(f"Loading fixture: {fixture_path}")
    with open(fixture_path, 'r') as f:
        return json.load(f)


def mock_run_ceph_command(cmd):
    """Mock Ceph commands to return production fixture data."""
    if 'pg' in cmd and 'dump' in cmd:
        return load_fixture('pg_dump.json')
    elif 'osd' in cmd and 'tree' in cmd:
        return load_fixture('osd_tree.json')
    elif 'osd' in cmd and 'pool' in cmd and 'ls' in cmd:
        return load_fixture('pool_details.json')
    else:
        raise ValueError(f"Unexpected command: {cmd}")


def main():
    """Run the CLI with mocked data collection."""
    print("="*80)
    print("PRODUCTION CLUSTER OPTIMIZATION")
    print("Using fixture data from tests/fixtures/production_cluster/")
    print("="*80)
    print()
    
    # Patch the collector's run_ceph_command to use fixtures
    with patch.object(collector, 'run_ceph_command', side_effect=mock_run_ceph_command):
        # Import and run the CLI main function
        # This must be imported AFTER patching to ensure it uses the mocked function
        from ceph_primary_balancer.cli import main as cli_main
        
        # The CLI will parse sys.argv, so command-line arguments work naturally
        cli_main()


if __name__ == '__main__':
    try:
        main()
    except FileNotFoundError as e:
        print(f"\nError: Could not find fixture file: {e}")
        print("Make sure production cluster data is in tests/fixtures/production_cluster/")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOptimization interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError during optimization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
