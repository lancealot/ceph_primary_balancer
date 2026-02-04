#!/usr/bin/env python3
"""
Command-line interface for the Ceph Primary PG Balancer benchmark framework.

Usage:
    python3 -m ceph_primary_balancer.benchmark_cli run [options]
    python3 -m ceph_primary_balancer.benchmark_cli compare --baseline <file>
    python3 -m ceph_primary_balancer.benchmark_cli generate-dataset [options]
"""

import sys
import argparse
from pathlib import Path

from .benchmark.runner import BenchmarkSuite, RegressionDetector
from .benchmark.reporter import TerminalReporter, JSONReporter, SimpleHTMLReporter
from .benchmark.generator import generate_synthetic_cluster, save_test_dataset
from .benchmark.profiler import quick_benchmark


def cmd_run(args):
    """Run benchmark suite."""
    print("Initializing benchmark suite...")
    
    # Build config from args
    config = {
        'target_cv': args.target_cv,
        'seed': args.seed,
        'output_dir': args.output_dir,
        'save_datasets': args.save_datasets,
        'run_scalability': not args.no_scalability,
        'run_stability': args.stability,
        'stability_runs': args.stability_runs
    }
    
    # Select scenarios
    if args.suite == 'quick':
        from .benchmark.scenarios import get_quick_suite
        scenarios = get_quick_suite()
        config['performance_scenarios'] = [s['name'] for s in scenarios if 'performance' in s.get('description', '').lower()]
        config['quality_scenarios'] = [s['name'] for s in scenarios if 'quality' in s.get('description', '').lower() or 'replicated' in s.get('name', '')]
        config['run_scalability'] = False  # Quick suite should skip scalability
    elif args.suite == 'standard':
        from .benchmark.scenarios import get_standard_suite
        scenarios = get_standard_suite()
        config['performance_scenarios'] = [s['name'] for s in scenarios[:3]]
        config['quality_scenarios'] = [s['name'] for s in scenarios[3:]]
    elif args.suite == 'comprehensive':
        config['performance_scenarios'] = ['tiny_smoke', 'small_quick', 'medium_standard']
        config['quality_scenarios'] = ['replicated_3_moderate', 'replicated_3_severe', 'multi_pool_complex']
    elif args.suite == 'performance':
        config['performance_scenarios'] = ['tiny_smoke', 'small_quick', 'medium_standard']
        config['quality_scenarios'] = []
        config['run_scalability'] = True
    elif args.suite == 'quality':
        config['performance_scenarios'] = []
        config['quality_scenarios'] = ['replicated_3_moderate', 'replicated_3_severe', 'multi_pool_complex']
    else:
        config['performance_scenarios'] = ['small_quick']
        config['quality_scenarios'] = ['replicated_3_moderate']
    
    # Run benchmarks
    suite = BenchmarkSuite(config)
    results = suite.run_all_benchmarks()
    
    # Generate reports
    print("\nGenerating reports...")
    
    # Terminal summary
    if not args.quiet:
        summary = TerminalReporter.generate_summary(results)
        print("\n" + summary)
    
    # Detailed terminal report
    if args.detailed:
        detailed = TerminalReporter.generate_detailed_report(results)
        print("\n" + detailed)
    
    # Save JSON
    if args.json_output:
        JSONReporter.export_results(results, args.json_output)
        print(f"JSON results saved to: {args.json_output}")
    
    # Save HTML
    if args.html_output:
        SimpleHTMLReporter.generate_dashboard(results, args.html_output)
        print(f"HTML dashboard saved to: {args.html_output}")
    
    # Save to runner's default location
    output_dir = Path(config['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)
    default_json = output_dir / 'benchmark_results.json'
    suite.save_results(str(default_json))
    
    print("\n✓ Benchmark suite complete!")
    return 0


def cmd_compare(args):
    """Compare with baseline and detect regressions."""
    print(f"Loading baseline from: {args.baseline}")
    
    # Run current benchmarks
    suite = BenchmarkSuite({'seed': args.seed})
    current_results = suite.run_all_benchmarks()
    
    # Detect regressions
    print("\nDetecting regressions...")
    detector = RegressionDetector(threshold=args.threshold)
    regressions = detector.detect_regressions(args.baseline, current_results)
    
    # Generate report
    report = detector.generate_report(regressions)
    print("\n" + report)
    
    # Save comparison
    if args.output:
        comparison_data = {
            'baseline': args.baseline,
            'regressions': [
                {
                    'metric': r.metric_name,
                    'baseline': r.baseline_value,
                    'current': r.current_value,
                    'change_pct': r.change_pct,
                    'severity': r.severity
                }
                for r in regressions
            ]
        }
        JSONReporter.export_comparison(comparison_data, args.output)
        print(f"Comparison saved to: {args.output}")
    
    # Return non-zero if regressions found
    return 1 if regressions else 0


def cmd_generate_dataset(args):
    """Generate synthetic test dataset."""
    print(f"Generating dataset: {args.osds} OSDs, {args.pgs} PGs, CV={args.imbalance}")
    
    state = generate_synthetic_cluster(
        num_osds=args.osds,
        num_hosts=max(1, args.osds // 10),
        num_pools=max(1, args.pgs // 1000),
        pgs_per_pool=args.pgs // max(1, args.pgs // 1000),
        replication_factor=3,
        imbalance_cv=args.imbalance,
        imbalance_pattern=args.pattern,
        seed=args.seed
    )
    
    metadata = {
        'num_osds': args.osds,
        'num_pgs': args.pgs,
        'imbalance_cv': args.imbalance,
        'pattern': args.pattern,
        'seed': args.seed
    }
    
    save_test_dataset(state, args.output, metadata)
    print(f"✓ Dataset saved to: {args.output}")
    
    # Quick analysis
    from .analyzer import calculate_statistics
    counts = [osd.primary_count for osd in state.osds.values()]
    stats = calculate_statistics(counts)
    print(f"\nDataset statistics:")
    print(f"  Mean:   {stats.mean:.2f}")
    print(f"  Std:    {stats.std_dev:.2f}")
    print(f"  CV:     {stats.cv:.2%}")
    print(f"  Range:  {stats.min_val} - {stats.max_val}")
    
    return 0


def cmd_quick(args):
    """Run quick smoke test benchmark."""
    print("Running quick benchmark (smoke test)...")
    
    perf, mem = quick_benchmark(
        num_osds=args.osds,
        num_pgs=args.pgs,
        imbalance_cv=args.imbalance
    )
    
    print("\nResults:")
    print(f"  Execution time: {perf.execution_time_total:.3f}s")
    print(f"  Peak memory:    {mem.peak_memory_mb:.1f} MB")
    print(f"  Swaps applied:  {perf.swaps_applied}")
    print(f"  Throughput:     {perf.swaps_per_second:.1f} swaps/s")
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Ceph Primary PG Balancer - Benchmark Framework',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run benchmark suite')
    run_parser.add_argument('--suite', choices=['quick', 'standard', 'comprehensive', 'performance', 'quality', 'all'],
                           default='standard', help='Benchmark suite to run')
    run_parser.add_argument('--target-cv', type=float, default=0.10,
                           help='Target coefficient of variation (default: 0.10)')
    run_parser.add_argument('--seed', type=int, default=42,
                           help='Random seed for reproducibility (default: 42)')
    run_parser.add_argument('--output-dir', default='./benchmark_results',
                           help='Output directory (default: ./benchmark_results)')
    run_parser.add_argument('--json-output', help='Save JSON results to file')
    run_parser.add_argument('--html-output', help='Save HTML dashboard to file')
    run_parser.add_argument('--save-datasets', action='store_true',
                           help='Save generated test datasets')
    run_parser.add_argument('--no-scalability', action='store_true',
                           help='Skip scalability tests')
    run_parser.add_argument('--stability', action='store_true',
                           help='Run stability tests (slower)')
    run_parser.add_argument('--stability-runs', type=int, default=10,
                           help='Number of stability test runs (default: 10)')
    run_parser.add_argument('--detailed', action='store_true',
                           help='Show detailed terminal report')
    run_parser.add_argument('--quiet', action='store_true',
                           help='Minimal output')
    
    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare with baseline')
    compare_parser.add_argument('--baseline', required=True,
                               help='Baseline results JSON file')
    compare_parser.add_argument('--threshold', type=float, default=0.10,
                               help='Regression threshold (default: 0.10 = 10%%)')
    compare_parser.add_argument('--seed', type=int, default=42,
                               help='Random seed (default: 42)')
    compare_parser.add_argument('--output', help='Save comparison results to file')
    
    # Generate dataset command
    gen_parser = subparsers.add_parser('generate-dataset', help='Generate synthetic test dataset')
    gen_parser.add_argument('--osds', type=int, default=100,
                           help='Number of OSDs (default: 100)')
    gen_parser.add_argument('--pgs', type=int, default=5000,
                           help='Number of PGs (default: 5000)')
    gen_parser.add_argument('--imbalance', type=float, default=0.30,
                           help='Imbalance CV (default: 0.30)')
    gen_parser.add_argument('--pattern', default='random',
                           choices=['random', 'concentrated', 'gradual', 'bimodal', 'worst_case', 'balanced'],
                           help='Imbalance pattern (default: random)')
    gen_parser.add_argument('--seed', type=int, default=42,
                           help='Random seed (default: 42)')
    gen_parser.add_argument('--output', default='./test_dataset.json',
                           help='Output file path (default: ./test_dataset.json)')
    
    # Quick command
    quick_parser = subparsers.add_parser('quick', help='Quick smoke test')
    quick_parser.add_argument('--osds', type=int, default=10,
                             help='Number of OSDs (default: 10)')
    quick_parser.add_argument('--pgs', type=int, default=100,
                             help='Number of PGs (default: 100)')
    quick_parser.add_argument('--imbalance', type=float, default=0.30,
                             help='Imbalance CV (default: 0.30)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    try:
        if args.command == 'run':
            return cmd_run(args)
        elif args.command == 'compare':
            return cmd_compare(args)
        elif args.command == 'generate-dataset':
            return cmd_generate_dataset(args)
        elif args.command == 'quick':
            return cmd_quick(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
