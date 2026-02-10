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
import os
from datetime import datetime
from pathlib import Path
from . import collector, analyzer, optimizer, script_generator
from .scorer import Scorer
from .exporter import JSONExporter
from .reporter import Reporter
from .config import Config, ConfigError


def print_optimization_strategies():
    """Print available optimization strategies and their descriptions."""
    print("\n" + "="*80)
    print("Available Optimization Strategies (Phase 6.5)")
    print("="*80 + "\n")
    
    strategies = [
        {
            'name': 'OSD-ONLY',
            'flag': '--optimization-levels osd',
            'description': 'Balances primary distribution across OSDs',
            'speed': 'Fastest strategy, simplest approach',
            'use_for': 'Small clusters, quick fixes, lab environments',
            'performance': 'Time: ~1× baseline, Memory: ~1× baseline'
        },
        {
            'name': 'OSD+HOST',
            'flag': '--optimization-levels osd,host',
            'description': 'Balances OSDs and host network load',
            'speed': 'Good balance of speed and quality',
            'use_for': 'Multi-host clusters, network hotspots',
            'performance': 'Time: ~2× baseline, Memory: ~1.5× baseline'
        },
        {
            'name': 'OSD+POOL',
            'flag': '--optimization-levels osd,pool',
            'description': 'Balances OSDs and per-pool distribution',
            'speed': 'Good for multi-pool workload isolation',
            'use_for': 'Multi-pool clusters, workload separation',
            'performance': 'Time: ~2× baseline, Memory: ~2× baseline'
        },
        {
            'name': 'HOST+POOL',
            'flag': '--optimization-levels host,pool',
            'description': 'Balances network and pool-level distribution',
            'speed': 'Network-focused optimization',
            'use_for': 'Network-constrained clusters',
            'performance': 'Time: ~1.5× baseline, Memory: ~1.5× baseline'
        },
        {
            'name': 'FULL-3D (DEFAULT)',
            'flag': '--optimization-levels osd,host,pool',
            'description': 'Comprehensive three-dimensional balancing',
            'speed': 'Best overall quality',
            'use_for': 'Production clusters, comprehensive optimization',
            'performance': 'Time: ~3-4× baseline, Memory: ~3× baseline'
        }
    ]
    
    for i, strategy in enumerate(strategies, 1):
        print(f"{i}. {strategy['name']}")
        print(f"   Usage: {strategy['flag']}")
        print(f"   Description: {strategy['description']}")
        print(f"   Speed: {strategy['speed']}")
        print(f"   Use for: {strategy['use_for']}")
        print(f"   Performance: {strategy['performance']}")
        print()
    
    print("Recommendation:")
    print("- Development/Testing: Use OSD-only for quick iterations")
    print("- Small Production (<100 OSDs): Use OSD+HOST")
    print("- Large Production (>100 OSDs): Use Full 3D")
    print("- Network-Constrained: Use HOST+POOL or OSD+HOST")
    print("- Single-Pool Clusters: Use OSD+HOST (skip pool optimization)")
    print("\n" + "="*80 + "\n")


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
    
    # Configuration file support (v1.0.0)
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Load configuration from JSON or YAML file (v1.0.0)'
    )
    
    # Output organization (v1.0.0)
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for all generated files with timestamp-based names (v1.0.0)'
    )
    
    # Verbosity control (v1.0.0)
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output with detailed information (v1.0.0)'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Minimal output, errors only (v1.0.0)'
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
    parser.add_argument(
        '--max-changes',
        type=int,
        default=None,
        help='Maximum number of primary reassignments to apply (default: unlimited). '
             'Useful for testing or limiting cluster impact.'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of commands to execute per batch in generated script (default: 50). '
             'Script will pause between batches for safety.'
    )
    
    # Phase 6.5: Configurable optimization levels
    parser.add_argument(
        '--optimization-levels',
        type=str,
        default='osd,host,pool',
        help='Comma-separated optimization levels: osd,host,pool (default: all). '
             'Examples: "osd" for OSD-only, "osd,host" for OSD+HOST. '
             'Phase 6.5: Enables selective dimension optimization for performance tuning.'
    )
    
    parser.add_argument(
        '--list-optimization-strategies',
        action='store_true',
        help='List available optimization strategies with descriptions and exit (Phase 6.5)'
    )
    
    # Phase 7.1: Dynamic weight adaptation
    parser.add_argument(
        '--dynamic-weights',
        action='store_true',
        help='Enable dynamic weight adaptation based on cluster state (Phase 7.1). '
             'Automatically adjusts optimization priorities for faster convergence and better results.'
    )
    
    parser.add_argument(
        '--dynamic-strategy',
        type=str,
        default='target_distance',
        choices=['proportional', 'target_distance', 'adaptive_hybrid'],
        help='Dynamic weight strategy (default: target_distance). '
             'Only used if --dynamic-weights is enabled. '
             'target_distance: Focus on dimensions above target (recommended). '
             'proportional: Weight proportionally to CV values. '
             'adaptive_hybrid: Advanced strategy with improvement tracking and smoothing.'
    )
    
    parser.add_argument(
        '--weight-update-interval',
        type=int,
        default=10,
        help='How often to recalculate dynamic weights in iterations (default: 10). '
             'Only used if --dynamic-weights is enabled.'
    )
    
    args = parser.parse_args()
    
    # Handle --list-optimization-strategies flag
    if args.list_optimization_strategies:
        print_optimization_strategies()
        sys.exit(0)
    
    # Validate verbose/quiet mutual exclusivity
    if args.verbose and args.quiet:
        print("Error: Cannot specify both --verbose and --quiet")
        sys.exit(1)
    
    # Define print helpers for verbosity control
    def vprint(msg):
        """Print if verbose mode enabled."""
        if args.verbose and not args.quiet:
            print(msg)
    
    def qprint(msg):
        """Print unless quiet mode enabled."""
        if not args.quiet:
            print(msg)
    
    # Load configuration file if specified (v1.0.0)
    config = None
    if args.config:
        vprint(f"Loading configuration from: {args.config}")
        try:
            config = Config(args.config)
            vprint("Configuration loaded successfully")
        except ConfigError as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)
    else:
        config = Config()  # Use defaults
    
    # Apply configuration values with CLI override precedence
    # CLI args > config file > defaults
    if args.target_cv == 0.10:  # Default value, check config
        args.target_cv = config.get('optimization.target_cv', 0.10)
    
    if args.weight_osd == 0.5:  # Default value
        args.weight_osd = config.get('scoring.weights.osd', 0.5)
    
    if args.weight_host == 0.3:  # Default value
        args.weight_host = config.get('scoring.weights.host', 0.3)
    
    if args.weight_pool == 0.2:  # Default value
        args.weight_pool = config.get('scoring.weights.pool', 0.2)
    
    if args.max_changes is None:
        args.max_changes = config.get('optimization.max_changes')
    
    if args.batch_size == 50:  # Default value
        args.batch_size = config.get('script.batch_size', 50)
    
    # Phase 7.1: Dynamic weights config support
    if not args.dynamic_weights:  # Not set via CLI
        args.dynamic_weights = config.get('optimization.dynamic_weights', False)
    
    if args.dynamic_strategy == 'target_distance':  # Default value
        args.dynamic_strategy = config.get('optimization.dynamic_strategy', 'target_distance')
    
    if args.weight_update_interval == 10:  # Default value
        args.weight_update_interval = config.get('optimization.weight_update_interval', 10)
    
    # Handle output directory (v1.0.0)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        vprint(f"Creating output directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp for filenames
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Update output paths with organized structure
        if args.output == './rebalance_primaries.sh':  # Default value
            script_name = config.get('output.script_name', 'rebalance_primaries.sh')
            script_name = script_name.replace('.sh', f'_{timestamp}.sh')
            args.output = str(output_dir / script_name)
        
        if args.json_output and not Path(args.json_output).is_absolute():
            # Relative path or just filename, place in output dir
            json_name = Path(args.json_output).name
            if json_name == args.json_output:  # Just filename
                json_name = f'analysis_{timestamp}.json'
            args.json_output = str(output_dir / json_name)
        elif args.output_dir and not args.json_output:
            # Auto-generate JSON output in output dir if requested by config
            if config.get('output.json_export', False):
                args.json_output = str(output_dir / f'analysis_{timestamp}.json')
        
        if args.report_output and not Path(args.report_output).is_absolute():
            # Relative path or just filename, place in output dir
            report_name = Path(args.report_output).name
            if report_name == args.report_output:  # Just filename
                report_name = f'report_{timestamp}.md'
            args.report_output = str(output_dir / report_name)
        elif args.output_dir and not args.report_output:
            # Auto-generate markdown report in output dir if requested by config
            if config.get('output.markdown_report', False):
                args.report_output = str(output_dir / f'report_{timestamp}.md')
        
        qprint(f"Output directory: {output_dir}")
    
    # Validate batch-size
    if args.batch_size <= 0:
        print("Error: --batch-size must be positive")
        sys.exit(1)
    
    # Validate weights
    weight_sum = args.weight_osd + args.weight_host + args.weight_pool
    if abs(weight_sum - 1.0) > 0.001:
        print(f"Error: Weights must sum to 1.0, got {weight_sum}")
        print(f"  --weight-osd={args.weight_osd} + --weight-host={args.weight_host} + --weight-pool={args.weight_pool} = {weight_sum}")
        sys.exit(1)
    
    if args.weight_osd < 0 or args.weight_host < 0 or args.weight_pool < 0:
        print("Error: Weights must be non-negative")
        sys.exit(1)
    
    # Validate max-changes
    if args.max_changes is not None and args.max_changes < 0:
        print("Error: --max-changes must be non-negative")
        sys.exit(1)
    
    # Phase 6.5: Parse and validate optimization levels
    enabled_levels = [level.strip() for level in args.optimization_levels.split(',')]
    valid_levels = {'osd', 'host', 'pool'}
    
    for level in enabled_levels:
        if level not in valid_levels:
            print(f"Error: Invalid optimization level '{level}'")
            print(f"Valid levels: {', '.join(sorted(valid_levels))}")
            print("Use --list-optimization-strategies to see available strategies")
            sys.exit(1)
    
    if not enabled_levels:
        print("Error: At least one optimization level must be enabled")
        sys.exit(1)
    
    # Create scorer with configured weights and enabled levels (Phase 6.5)
    scorer = Scorer(
        w_osd=args.weight_osd,
        w_host=args.weight_host,
        w_pool=args.weight_pool,
        enabled_levels=enabled_levels
    )
    
    # Step 1: Collect cluster data
    qprint("Collecting cluster data...")
    try:
        state = collector.build_cluster_state()
    except Exception as e:
        print(f"Error collecting cluster data: {e}")  # Always print errors
        sys.exit(1)
    
    qprint(f"Found {len(state.osds)} OSDs, {len(state.hosts)} hosts, {len(state.pools)} pools, {len(state.pgs)} PGs")
    vprint(f"  OSDs: {list(state.osds.keys())[:10]}..." if len(state.osds) > 10 else f"  OSDs: {list(state.osds.keys())}")
    
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
    
    swaps = optimizer.optimize_primaries(
        state,
        args.target_cv,
        scorer=scorer,
        pool_filter=args.pool,
        enabled_levels=enabled_levels,
        dynamic_weights=args.dynamic_weights,
        dynamic_strategy=args.dynamic_strategy,
        weight_update_interval=args.weight_update_interval
    )
    
    # Step 5: Handle case where no swaps were found
    if not swaps:
        print("\nNo optimization swaps found")
        print("The cluster may already be optimally balanced or no valid swaps exist")
        return
    
    # Step 5.5: Apply max-changes limit if specified
    if args.max_changes is not None and len(swaps) > args.max_changes:
        print("\n" + "="*60)
        print("APPLYING SWAP LIMIT")
        print("="*60)
        print(f"Optimization found {len(swaps)} beneficial swaps")
        print(f"Limiting to {args.max_changes} changes (--max-changes={args.max_changes})")
        print()
        
        # Truncate swap list to specified maximum
        swaps = swaps[:args.max_changes]
        
        # Restore state to pre-optimization and re-apply only limited swaps
        print(f"Recalculating proposed state with {len(swaps)} swaps...")
        state = copy.deepcopy(original_state)
        
        # Re-apply the limited set of swaps
        for swap in swaps:
            optimizer.apply_swap(state, swap)
        
        print(f"Proposed state recalculated with {len(swaps)} swaps")
    
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
        script_generator.generate_script(swaps, args.output, batch_size=args.batch_size)
        
        # Generate rollback script
        rollback_path = script_generator.generate_rollback_script(swaps, args.output)
        
        print(f"\n" + "="*60)
        print(f"Script written to: {args.output}")
        print(f"Batch size: {args.batch_size} commands per batch")
        if rollback_path:
            print(f"Rollback script: {rollback_path}")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("Dry run mode - no script generated")
        print("="*60)


if __name__ == '__main__':
    main()
