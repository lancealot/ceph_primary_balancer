#!/usr/bin/env python3
"""CLI entry point for the Ceph Primary PG Balancer."""

import argparse
import sys
import copy
from datetime import datetime
from pathlib import Path
from . import collector, analyzer, script_generator
from .optimizers import GreedyOptimizer
from .scorer import Scorer
from .exporter import JSONExporter
from .reporter import Reporter
from .config import Config, ConfigError


def _section(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze and optimize Ceph primary PG distribution with three-dimensional balancing'
    )
    
    parser.add_argument(
        '--from-file',
        type=str,
        default=None,
        help='Load cluster data from exported .tar.gz file for offline/air-gapped use'
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Load configuration from JSON or YAML file'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for all generated files (timestamped names)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Minimal output, errors only'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Analyze only, do not generate script'
    )
    parser.add_argument(
        '--target-cv',
        type=float,
        default=0.01,
        help='Target coefficient of variation (default: 0.01). Low default ensures optimizer runs to swap exhaustion rather than stopping early.'
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
        help='Weight for OSD-level balance in scoring (default: 0.5)'
    )
    parser.add_argument(
        '--weight-host',
        type=float,
        default=0.3,
        help='Weight for host-level balance in scoring (default: 0.3)'
    )
    parser.add_argument(
        '--weight-pool',
        type=float,
        default=0.2,
        help='Weight for pool-level balance in scoring (default: 0.2)'
    )
    parser.add_argument(
        '--pool',
        type=int,
        default=None,
        help='Only optimize PGs from specified pool ID'
    )
    parser.add_argument(
        '--json-output',
        type=str,
        default=None,
        help='Export analysis results to JSON file'
    )
    parser.add_argument(
        '--report-output',
        type=str,
        default=None,
        help='Generate markdown analysis report'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['terminal', 'json', 'markdown', 'all'],
        default='terminal',
        help='Output format (default: terminal)'
    )
    parser.add_argument(
        '--max-changes',
        type=int,
        default=None,
        help='Maximum number of primary reassignments (optimizer iterations). '
             'Default: config max_iterations (10000). '
             'Useful for testing or limiting cluster impact.'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of commands to execute per batch in generated script (default: 50). '
             'Script will pause between batches for safety.'
    )
    
    parser.add_argument(
        '--optimization-levels',
        type=str,
        default='osd,host,pool',
        help='Comma-separated optimization levels (default: osd,host,pool)'
    )
    parser.add_argument(
        '--dynamic-weights',
        action='store_true',
        help='Enable dynamic weight adaptation for faster convergence'
    )
    
    parser.add_argument(
        '--dynamic-strategy',
        type=str,
        default='target_distance',
        choices=['target_distance', 'two_phase'],
        help='Dynamic weight strategy (default: target_distance). '
             'Only used if --dynamic-weights is enabled. '
             'target_distance: Focus on dimensions above target (recommended). '
             'two_phase: Hard switch to pool-focused weights once OSD/host converge.'
    )
    
    parser.add_argument(
        '--weight-update-interval',
        type=int,
        default=10,
        help='How often to recalculate dynamic weights in iterations (default: 10). '
             'Only used if --dynamic-weights is enabled.'
    )

    args = parser.parse_args()

    offline_mode = args.from_file is not None
    offline_metadata = None

    if offline_mode:
        _section("OFFLINE MODE")
        print(f"Loading cluster data from: {args.from_file}")
        
        # Import offline module and load metadata
        from . import offline
        
        try:
            if args.from_file.endswith('.tar.gz'):
                export_dir = offline.extract_export_archive(args.from_file)
            else:
                export_dir = args.from_file

            offline_metadata = offline.load_metadata(export_dir)
            export_age = offline.calculate_export_age(offline_metadata)

            print(f"  Date: {offline_metadata.get('export_date_local', 'unknown')} ({export_age})")
            print(f"  Host: {offline_metadata.get('export_hostname', 'unknown')}")
            print(f"  Ceph: {offline_metadata.get('ceph_version', 'unknown')}")

            if 'days' in export_age:
                days = int(export_age.split()[0])
                if days > 7:
                    print(f"  WARNING: Export is {export_age} — cluster state may have changed")

        except offline.OfflineExportError as e:
            print(f"Error loading offline export: {e}")
            sys.exit(1)
    
    if args.verbose and args.quiet:
        print("Error: Cannot specify both --verbose and --quiet")
        sys.exit(1)
    
    def vprint(msg):
        if args.verbose:
            print(msg)

    def qprint(msg):
        if not args.quiet:
            print(msg)

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
    
    # Apply config file values where CLI arg is still at its default
    _config_defaults = {
        'target_cv': (0.01, 'optimization.target_cv'),
        'weight_osd': (0.5, 'scoring.weights.osd'),
        'weight_host': (0.3, 'scoring.weights.host'),
        'weight_pool': (0.2, 'scoring.weights.pool'),
        'batch_size': (50, 'script.batch_size'),
        'dynamic_strategy': ('target_distance', 'optimization.dynamic_strategy'),
        'weight_update_interval': (10, 'optimization.weight_update_interval'),
    }
    for attr, (default_val, config_key) in _config_defaults.items():
        if getattr(args, attr) == default_val:
            setattr(args, attr, config.get(config_key, default_val))

    if args.max_changes is None:
        args.max_changes = config.get('optimization.max_changes')
    if not args.dynamic_weights:
        args.dynamic_weights = config.get('optimization.dynamic_weights', False)
    if args.dynamic_strategy != 'target_distance' and not args.dynamic_weights:
        args.dynamic_weights = True
    
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
    
    if args.batch_size <= 0:
        print("Error: --batch-size must be positive")
        sys.exit(1)
    
    weight_sum = args.weight_osd + args.weight_host + args.weight_pool
    if abs(weight_sum - 1.0) > 0.001:
        print(f"Error: Weights must sum to 1.0, got {weight_sum}")
        print(f"  --weight-osd={args.weight_osd} + --weight-host={args.weight_host} + --weight-pool={args.weight_pool} = {weight_sum}")
        sys.exit(1)
    
    if args.weight_osd < 0 or args.weight_host < 0 or args.weight_pool < 0:
        print("Error: Weights must be non-negative")
        sys.exit(1)
    
    if args.max_changes is not None and args.max_changes < 0:
        print("Error: --max-changes must be non-negative")
        sys.exit(1)
    
    enabled_levels = [level.strip() for level in args.optimization_levels.split(',')]
    valid_levels = {'osd', 'host', 'pool'}
    invalid = [l for l in enabled_levels if l not in valid_levels]
    if invalid or not enabled_levels:
        print(f"Error: Invalid optimization level(s): {', '.join(invalid or ['(none)'])}")
        print(f"Valid levels: osd, host, pool")
        sys.exit(1)
    
    # Dynamic weights: let the optimizer create a DynamicScorer instead of static
    if args.dynamic_weights:
        scorer = None
    else:
        scorer = Scorer(
            w_osd=args.weight_osd,
            w_host=args.weight_host,
            w_pool=args.weight_pool,
            enabled_levels=enabled_levels
        )
    
    if offline_mode:
        qprint("Loading cluster state from offline export...")
    else:
        qprint("Collecting cluster data from live cluster...")
    
    try:
        state = collector.build_cluster_state(from_file=args.from_file if offline_mode else None)
    except Exception as e:
        print(f"Error collecting cluster data: {e}")  # Always print errors
        sys.exit(1)
    
    qprint(f"Found {len(state.osds)} OSDs, {len(state.hosts)} hosts, {len(state.pools)} pools, {len(state.pgs)} PGs")
    vprint(f"  OSDs: {list(state.osds.keys())[:10]}..." if len(state.osds) > 10 else f"  OSDs: {list(state.osds.keys())}")
    
    _section("CURRENT STATE - OSD Level")
    try:
        current_stats_osd = analyzer.calculate_statistics(
            [osd.primary_count for osd in state.osds.values()]
        )
        analyzer.print_summary(state, current_stats_osd)
    except ValueError as e:
        print(f"Error calculating statistics: {e}")
        sys.exit(1)
    
    current_stats_host = None
    if state.hosts:
        _section("CURRENT STATE - Host Level")
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
    
    if state.pools:
        _section("CURRENT STATE - Pool Level")
        print(f"Total Pools: {len(state.pools)}")
        
        from .analyzer import get_pool_statistics_summary
        pool_stats = get_pool_statistics_summary(state)
        
        if pool_stats:
            # PG-weighted average CV across all pools
            from .analyzer import calculate_weighted_avg_pool_cv
            avg_pool_cv = calculate_weighted_avg_pool_cv(state)
            print(f"Average Pool CV (balanceable): {avg_pool_cv:.2%}")
            print(f"\nPer-Pool Statistics:")

            # Sort pools by CV (worst first)
            sorted_pool_stats = sorted(pool_stats.items(), key=lambda x: x[1].cv, reverse=True)
            for pool_id, pool_stat in sorted_pool_stats[:5]:  # Show top 5 pools
                pool = state.pools[pool_id]
                print(f"  Pool {pool_id} ({pool.pool_name}):")
                print(f"    PGs: {pool.pg_count}, CV: {pool_stat.cv:.2%}, "
                      f"Range: [{pool_stat.min_val}-{pool_stat.max_val}]")
    
    print()  # blank line before balance check
    all_below_target = True
    if 'osd' in enabled_levels and current_stats_osd.cv > args.target_cv:
        all_below_target = False
    if 'host' in enabled_levels and state.hosts:
        host_counts = [host.primary_count for host in state.hosts.values()]
        if host_counts and analyzer.calculate_statistics(host_counts).cv > args.target_cv:
            all_below_target = False
    if 'pool' in enabled_levels and state.pools:
        from .analyzer import calculate_weighted_avg_pool_cv
        avg_cv = calculate_weighted_avg_pool_cv(state)
        if avg_cv > args.target_cv:
            all_below_target = False
    if all_below_target:
        print(f"Cluster already balanced across all enabled dimensions (target CV = {args.target_cv:.2%})")
        return
    
    _section("OPTIMIZATION")
    print(f"Target CV: {args.target_cv:.2%} (checked across: {', '.join(enabled_levels)})")
    print(f"Scoring weights: OSD={args.weight_osd:.1f}, Host={args.weight_host:.1f}, Pool={args.weight_pool:.1f}")
    if args.pool is not None:
        if args.pool in state.pools:
            print(f"Pool filter: {args.pool} ({state.pools[args.pool].pool_name})")
        else:
            print(f"Warning: Pool {args.pool} not found, ignoring filter")
    print()
    
    original_state = copy.deepcopy(state)
    max_iterations = args.max_changes if args.max_changes is not None else config.get('optimization.max_iterations', 10000)

    print("Algorithm: greedy")
    optimizer = GreedyOptimizer(
        target_cv=args.target_cv,
        max_iterations=max_iterations,
        scorer=scorer,
        pool_filter=args.pool,
        enabled_levels=enabled_levels,
        dynamic_weights=args.dynamic_weights,
        dynamic_strategy=args.dynamic_strategy,
        weight_update_interval=args.weight_update_interval,
        verbose=True,
    )
    swaps = optimizer.optimize(state)
    
    if not swaps:
        print("\nNo optimization swaps found")
        print("The cluster may already be optimally balanced or no valid swaps exist")
        return
    
    _section("PROPOSED STATE - OSD Level")
    print(f"Proposed {len(swaps)} primary reassignments")
    
    proposed_stats_osd = analyzer.calculate_statistics(
        [osd.primary_count for osd in state.osds.values()]
    )
    print(f"OSD CV Improvement: {current_stats_osd.cv:.2%} -> {proposed_stats_osd.cv:.2%}")
    print(f"OSD Std Dev: {current_stats_osd.std_dev:.2f} -> {proposed_stats_osd.std_dev:.2f}")
    print(f"OSD Range: [{current_stats_osd.min_val}-{current_stats_osd.max_val}] -> [{proposed_stats_osd.min_val}-{proposed_stats_osd.max_val}]")
    
    if state.hosts:
        _section("PROPOSED STATE - Host Level")
        host_counts = [host.primary_count for host in state.hosts.values()]
        proposed_stats_host = analyzer.calculate_statistics(host_counts)
        print(f"Host CV Improvement: {current_stats_host.cv:.2%} -> {proposed_stats_host.cv:.2%}")
        print(f"Host Std Dev: {current_stats_host.std_dev:.2f} -> {proposed_stats_host.std_dev:.2f}")
        print(f"Host Range: [{current_stats_host.min_val}-{current_stats_host.max_val}] -> [{proposed_stats_host.min_val}-{proposed_stats_host.max_val}]")
    
    if state.pools:
        _section("PROPOSED STATE - Pool Level")
        
        from .analyzer import get_pool_statistics_summary
        current_pool_stats = get_pool_statistics_summary(state)
        
        if current_pool_stats:
            from .analyzer import calculate_weighted_avg_pool_cv
            avg_pool_cv = calculate_weighted_avg_pool_cv(state)
            print(f"Average Pool CV (balanceable): {avg_pool_cv:.2%}")

            # Show pools with most improvement or focus on filtered pool
            if args.pool is not None and args.pool in current_pool_stats:
                pool_stat = current_pool_stats[args.pool]
                pool = state.pools[args.pool]
                print(f"\nOptimized Pool {args.pool} ({pool.pool_name}):")
                print(f"  CV: {pool_stat.cv:.2%}")
                print(f"  Range: [{pool_stat.min_val}-{pool_stat.max_val}]")
    
    if args.json_output or args.format in ['json', 'all']:
        json_path = args.json_output or './analysis.json'
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
    
    if args.report_output or args.format in ['markdown', 'all']:
        report_path = args.report_output or './analysis.md'
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
    
    if args.format in ['terminal', 'all']:
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
    
    if not args.dry_run:
        script_generator.generate_script(
            swaps,
            args.output,
            batch_size=args.batch_size,
            offline_mode=offline_mode,
            export_metadata=offline_metadata if offline_mode else None
        )
        rollback_path = script_generator.generate_rollback_script(swaps, args.output)

        print(f"\nScript written to: {args.output} (batch size: {args.batch_size})")
        if rollback_path:
            print(f"Rollback script: {rollback_path}")
    else:
        print("\nDry run mode - no script generated")


if __name__ == '__main__':
    main()
