#!/usr/bin/env python3
"""Command-line interface for the Ceph Primary PG Balancer.

This module provides the main entry point for analyzing and optimizing
the distribution of primary placement groups across OSDs in a Ceph cluster.
"""

import argparse
import sys
from . import collector, analyzer, optimizer, script_generator


def main():
    """Main entry point for the CLI.
    
    Orchestrates the complete workflow:
    1. Parse command-line arguments
    2. Collect cluster data from Ceph
    3. Analyze current primary distribution
    4. Check if cluster is already balanced
    5. Optimize primary assignments if needed
    6. Generate rebalancing script (unless --dry-run)
    
    Returns:
        None. Exits with status 0 on success.
    """
    parser = argparse.ArgumentParser(
        description='Analyze and optimize Ceph primary PG distribution'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze only, do not generate script'
    )
    parser.add_argument(
        '--target-cv',
        type=float,
        default=0.10,
        help='Target coefficient of variation (default: 0.10)'
    )
    parser.add_argument(
        '--output',
        default='./rebalance_primaries.sh',
        help='Output script path (default: ./rebalance_primaries.sh)'
    )
    
    args = parser.parse_args()
    
    # Step 1: Collect cluster data
    print("Collecting cluster data...")
    try:
        state = collector.build_cluster_state()
    except Exception as e:
        print(f"Error collecting cluster data: {e}")
        sys.exit(1)
    
    # Step 2: Calculate current statistics
    print("\nCurrent State:")
    try:
        current_stats = analyzer.calculate_statistics(
            [osd.primary_count for osd in state.osds.values()]
        )
        analyzer.print_summary(state, current_stats)
    except ValueError as e:
        print(f"Error calculating statistics: {e}")
        sys.exit(1)
    
    # Step 3: Check if already balanced
    if current_stats.cv <= args.target_cv:
        print(f"\nCluster already balanced (CV = {current_stats.cv:.2%})")
        print(f"Target CV of {args.target_cv:.2%} already achieved - no optimization needed")
        return
    
    # Step 4: Optimize primary distribution
    print(f"\nOptimizing (target CV = {args.target_cv:.2%})...")
    swaps = optimizer.optimize_primaries(state, args.target_cv)
    
    # Step 5: Handle case where no swaps were found
    if not swaps:
        print("\nNo optimization swaps found")
        print("The cluster may already be optimally balanced or no valid swaps exist")
        return
    
    # Step 6: Report proposed changes
    print(f"\nProposed {len(swaps)} primary reassignments")
    
    proposed_stats = analyzer.calculate_statistics(
        [osd.primary_count for osd in state.osds.values()]
    )
    print(f"Improvement: {current_stats.cv:.2%} -> {proposed_stats.cv:.2%}")
    
    # Step 7: Generate script or report dry-run
    if not args.dry_run:
        script_generator.generate_script(swaps, args.output)
        print(f"\nScript written to: {args.output}")
    else:
        print("\nDry run mode - no script generated")


if __name__ == '__main__':
    main()
