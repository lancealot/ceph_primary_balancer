#!/usr/bin/env python3
"""Command-line interface for the Ceph Primary PG Balancer.

This module provides the main entry point for analyzing and optimizing
the distribution of primary placement groups across OSDs in a Ceph cluster.

Phase 2 Update: Now supports three-dimensional optimization with pool-level balancing
and configurable weights for OSD, host, and pool dimensions.
"""

import argparse
import sys
import copy
from . import collector, analyzer, optimizer, script_generator
from .scorer import Scorer
from .exporter import JSONExporter
from .reporter import Reporter


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
        description='Analyze and optimize Ceph primary PG distribution with three-dimensional balancing'
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
        help='Target coefficient of variation for OSD level (default: 0.10)'
    )
    parser.add_argument(
        '--output',
        default='./rebalance_primaries.sh',
        help='Output script path (default: ./rebalance_primaries.sh)'
    )
    parser.add_argument(
        '--weight-osd',
        type=float,
        default=0.5,
        help='Weight for OSD-level variance in scoring (default: 0.5, Phase 2)'
    )
    parser.add_argument(
        '--weight-host',
        type=float,
        default=0.3,
        help='Weight for host-level variance in scoring (default: 0.3)'
    )
    parser.add_argument(
        '--weight-pool',
        type=float,
        default=0.2,
        help='Weight for pool-level variance in scoring (default: 0.2, Phase 2)'
    )
    parser.add_argument(
        '--pool',
        type=int,
        default=None,
        help='Only optimize PGs from specified pool ID (optional, Phase 2)'
    )
    parser.add_argument(
        '--json-output',
        type=str,
        default=None,
        help='Export analysis results to JSON file (Phase 3)'
    )
    parser.add_argument(
        '--report-output',
        type=str,
        default=None,
        help='Generate markdown analysis report (Phase 3)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['terminal', 'json', 'markdown', 'all'],
        default='terminal',
        help='Output format: terminal (default), json, markdown, or all (Phase 3)'
    )
    
    args = parser.parse_args()
    
    # Validate weights
    weight_sum = args.weight_osd + args.weight_host + args.weight_pool
    if abs(weight_sum - 1.0) > 0.001:
        print(f"Error: Weights must sum to 1.0, got {weight_sum}")
        print(f"  --weight-osd={args.weight_osd} + --weight-host={args.weight_host} + --weight-pool={args.weight_pool} = {weight_sum}")
        sys.exit(1)
    
    if args.weight_osd < 0 or args.weight_host < 0 or args.weight_pool < 0:
        print("Error: Weights must be non-negative")
        sys.exit(1)
    
    # Create scorer with configured weights (Phase 2: three dimensions)
    scorer = Scorer(w_osd=args.weight_osd, w_host=args.weight_host, w_pool=args.weight_pool)
    
    # Step 1: Collect cluster data
    print("Collecting cluster data...")
    try:
        state = collector.build_cluster_state()
    except Exception as e:
        print(f"Error collecting cluster data: {e}")
        sys.exit(1)
    
    print(f"Found {len(state.osds)} OSDs, {len(state.hosts)} hosts, {len(state.pools)} pools, {len(state.pgs)} PGs")
    
    # Step 2: Calculate current statistics
    print("\n" + "="*60)
    print("CURRENT STATE - OSD Level")
    print("="*60)
    try:
        current_stats_osd = analyzer.calculate_statistics(
            [osd.primary_count for osd in state.osds.values()]
        )
        analyzer.print_summary(state, current_stats_osd)
    except ValueError as e:
        print(f"Error calculating statistics: {e}")
        sys.exit(1)
    
    # Step 2b: Calculate host-level statistics if available
    current_stats_host = None
    if state.hosts:
        print("\n" + "="*60)
        print("CURRENT STATE - Host Level")
        print("="*60)
        host_counts = [host.primary_count for host in state.hosts.values()]
        current_stats_host = analyzer.calculate_statistics(host_counts)
        print(f"Total Hosts: {len(state.hosts)}")
        print(f"Mean primaries per host: {current_stats_host.mean:.1f}")
        print(f"Std Dev: {current_stats_host.std_dev:.2f}")
        print(f"Coefficient of Variation: {current_stats_host.cv:.2%}")
        print(f"Range: {current_stats_host.min_val} - {current_stats_host.max_val}")
        print(f"Median: {current_stats_host.p50:.1f}")
        
        # Show top hosts by primary count
        sorted_hosts = sorted(state.hosts.items(),
                            key=lambda x: x[1].primary_count,
                            reverse=True)
        print(f"\nTop 5 hosts by primary count:")
        for hostname, host in sorted_hosts[:5]:
            print(f"  {hostname}: {host.primary_count} primaries across {len(host.osd_ids)} OSDs")
    
    # Step 2c: Calculate pool-level statistics if available (Phase 2)
    if state.pools:
        print("\n" + "="*60)
        print("CURRENT STATE - Pool Level")
        print("="*60)
        print(f"Total Pools: {len(state.pools)}")
        
        from .analyzer import get_pool_statistics_summary
        pool_stats = get_pool_statistics_summary(state)
        
        if pool_stats:
            # Calculate average CV across all pools
            avg_pool_cv = sum(ps.cv for ps in pool_stats.values()) / len(pool_stats)
            print(f"Average Pool CV: {avg_pool_cv:.2%}")
            print(f"\nPer-Pool Statistics:")
            
            # Sort pools by CV (worst first)
            sorted_pool_stats = sorted(pool_stats.items(), key=lambda x: x[1].cv, reverse=True)
            for pool_id, pool_stat in sorted_pool_stats[:5]:  # Show top 5 pools
                pool = state.pools[pool_id]
                print(f"  Pool {pool_id} ({pool.pool_name}):")
                print(f"    PGs: {pool.pg_count}, CV: {pool_stat.cv:.2%}, "
                      f"Range: [{pool_stat.min_val}-{pool_stat.max_val}]")
    
    # Step 3: Check if already balanced at OSD level
    print("\n" + "="*60)
    if current_stats_osd.cv <= args.target_cv:
        print(f"Cluster already balanced at OSD level (CV = {current_stats_osd.cv:.2%})")
        print(f"Target CV of {args.target_cv:.2%} already achieved - no optimization needed")
        return
    
    # Step 4: Optimize primary distribution with multi-dimensional scoring
    print(f"OPTIMIZATION")
    print("="*60)
    print(f"Target OSD CV: {args.target_cv:.2%}")
    print(f"Scoring weights: OSD={args.weight_osd:.1f}, Host={args.weight_host:.1f}, Pool={args.weight_pool:.1f}")
    if args.pool is not None:
        if args.pool in state.pools:
            print(f"Pool filter: {args.pool} ({state.pools[args.pool].pool_name})")
        else:
            print(f"Warning: Pool {args.pool} not found, ignoring filter")
    print()
    
    # Store original state for reporting (before optimization modifies it)
    original_state = copy.deepcopy(state)
    
    swaps = optimizer.optimize_primaries(state, args.target_cv, scorer=scorer, pool_filter=args.pool)
    
    # Step 5: Handle case where no swaps were found
    if not swaps:
        print("\nNo optimization swaps found")
        print("The cluster may already be optimally balanced or no valid swaps exist")
        return
    
    # Step 6: Report proposed changes
    print("\n" + "="*60)
    print("PROPOSED STATE - OSD Level")
    print("="*60)
    print(f"Proposed {len(swaps)} primary reassignments")
    
    proposed_stats_osd = analyzer.calculate_statistics(
        [osd.primary_count for osd in state.osds.values()]
    )
    print(f"OSD CV Improvement: {current_stats_osd.cv:.2%} -> {proposed_stats_osd.cv:.2%}")
    print(f"OSD Std Dev: {current_stats_osd.std_dev:.2f} -> {proposed_stats_osd.std_dev:.2f}")
    print(f"OSD Range: [{current_stats_osd.min_val}-{current_stats_osd.max_val}] -> [{proposed_stats_osd.min_val}-{proposed_stats_osd.max_val}]")
    
    # Step 6b: Report host-level improvements if available
    if state.hosts:
        print("\n" + "="*60)
        print("PROPOSED STATE - Host Level")
        print("="*60)
        host_counts = [host.primary_count for host in state.hosts.values()]
        proposed_stats_host = analyzer.calculate_statistics(host_counts)
        print(f"Host CV Improvement: {current_stats_host.cv:.2%} -> {proposed_stats_host.cv:.2%}")
        print(f"Host Std Dev: {current_stats_host.std_dev:.2f} -> {proposed_stats_host.std_dev:.2f}")
        print(f"Host Range: [{current_stats_host.min_val}-{current_stats_host.max_val}] -> [{proposed_stats_host.min_val}-{proposed_stats_host.max_val}]")
    
    # Step 6c: Report pool-level improvements if available (Phase 2)
    if state.pools:
        print("\n" + "="*60)
        print("PROPOSED STATE - Pool Level")
        print("="*60)
        
        from .analyzer import get_pool_statistics_summary
        current_pool_stats = get_pool_statistics_summary(state)
        
        if current_pool_stats:
            avg_pool_cv = sum(ps.cv for ps in current_pool_stats.values()) / len(current_pool_stats)
            print(f"Average Pool CV: {avg_pool_cv:.2%}")
            
            # Show pools with most improvement or focus on filtered pool
            if args.pool is not None and args.pool in current_pool_stats:
                pool_stat = current_pool_stats[args.pool]
                pool = state.pools[args.pool]
                print(f"\nOptimized Pool {args.pool} ({pool.pool_name}):")
                print(f"  CV: {pool_stat.cv:.2%}")
                print(f"  Range: [{pool_stat.min_val}-{pool_stat.max_val}]")
    
    # Step 7: Generate JSON export if requested (Phase 3)
    if args.json_output or args.format in ['json', 'all']:
        json_path = args.json_output or './analysis.json'
        print(f"\n" + "="*60)
        print("EXPORTING JSON ANALYSIS")
        print("="*60)
        try:
            from . import __version__
            exporter = JSONExporter(tool_version=__version__)
            exporter.export_to_file(
                current_state=original_state,
                proposed_state=state,
                swaps=swaps,
                output_path=json_path,
                cluster_fsid=None,  # Could be extracted from ceph status if needed
                analysis_type="full"
            )
            print(f"JSON analysis exported to: {json_path}")
        except Exception as e:
            print(f"Warning: Failed to export JSON: {e}")
    
    # Step 8: Generate markdown report if requested (Phase 3)
    if args.report_output or args.format in ['markdown', 'all']:
        report_path = args.report_output or './analysis.md'
        print(f"\n" + "="*60)
        print("GENERATING MARKDOWN REPORT")
        print("="*60)
        try:
            reporter = Reporter(top_n=10)
            reporter.generate_markdown_report(
                current=original_state,
                proposed=state,
                swaps=swaps,
                output_path=report_path
            )
            print(f"Markdown report generated: {report_path}")
        except Exception as e:
            print(f"Warning: Failed to generate markdown report: {e}")
    
    # Step 9: Generate enhanced terminal report if requested (Phase 3)
    if args.format in ['terminal', 'all']:
        print(f"\n" + "="*60)
        print("ENHANCED REPORT")
        print("="*60)
        try:
            reporter = Reporter(top_n=5)
            report = reporter.generate_terminal_report(
                current=original_state,
                proposed=state,
                swaps=swaps
            )
            print(report)
        except Exception as e:
            print(f"Warning: Failed to generate enhanced report: {e}")
    
    # Step 10: Generate script or report dry-run
    if not args.dry_run:
        script_generator.generate_script(swaps, args.output)
        print(f"\n" + "="*60)
        print(f"Script written to: {args.output}")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("Dry run mode - no script generated")
        print("="*60)


if __name__ == '__main__':
    main()
