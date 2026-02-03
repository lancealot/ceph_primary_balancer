"""
Test script to analyze production cluster data from fixtures.

This script loads real cluster data from tests/fixtures/production_cluster
and runs the full optimization workflow to demonstrate results.
"""

import json
import os
import sys
from unittest.mock import patch

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ceph_primary_balancer import collector, analyzer, optimizer
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.exporter import JSONExporter
from ceph_primary_balancer.reporter import Reporter


def load_fixture(filename):
    """Load a fixture file from production_cluster directory."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        'fixtures',
        'production_cluster',
        filename
    )
    with open(fixture_path, 'r') as f:
        return json.load(f)


def mock_run_ceph_command(cmd):
    """Mock Ceph commands to return production fixture data."""
    if 'pg' in cmd and 'dump' in cmd:
        # Collector expects pg_stats at top level
        return load_fixture('pg_dump.json')
    elif 'osd' in cmd and 'tree' in cmd:
        return load_fixture('osd_tree.json')
    elif 'osd' in cmd and 'pool' in cmd and 'ls' in cmd:
        return load_fixture('pool_details.json')
    else:
        raise ValueError(f"Unexpected command: {cmd}")


def analyze_production_cluster():
    """Analyze the production cluster and generate reports."""
    
    print("=" * 80)
    print("PRODUCTION CLUSTER ANALYSIS")
    print("=" * 80)
    print()
    
    # Load cluster data with mocked commands
    with patch.object(collector, 'run_ceph_command', side_effect=mock_run_ceph_command):
        print("Loading cluster data from fixtures...")
        state = collector.build_cluster_state()
        print(f"✓ Loaded: {len(state.osds)} OSDs, {len(state.hosts)} hosts, "
              f"{len(state.pools)} pools, {len(state.pgs)} PGs")
        print()
    
    # Analyze current OSD-level distribution
    print("=" * 80)
    print("CURRENT STATE - OSD LEVEL")
    print("=" * 80)
    osd_counts = [osd.primary_count for osd in state.osds.values()]
    current_osd_stats = analyzer.calculate_statistics(osd_counts)
    
    print(f"Total OSDs:              {len(state.osds)}")
    print(f"Mean primaries per OSD:  {current_osd_stats.mean:.2f}")
    print(f"Std Dev:                 {current_osd_stats.std_dev:.2f}")
    print(f"Coefficient of Variation: {current_osd_stats.cv:.2%}")
    print(f"Range:                   [{current_osd_stats.min_val} - {current_osd_stats.max_val}]")
    print(f"Median:                  {current_osd_stats.p50:.1f}")
    print()
    
    # Show top 10 most loaded OSDs
    sorted_osds = sorted(state.osds.items(), key=lambda x: x[1].primary_count, reverse=True)
    print("Top 10 Most Loaded OSDs:")
    for osd_id, osd_info in sorted_osds[:10]:
        host = osd_info.host or "unknown"
        print(f"  OSD.{osd_id:3d} @ {host:20s}: {osd_info.primary_count:5d} primaries")
    print()
    
    # Analyze host-level distribution
    if state.hosts:
        print("=" * 80)
        print("CURRENT STATE - HOST LEVEL")
        print("=" * 80)
        host_counts = [host.primary_count for host in state.hosts.values()]
        current_host_stats = analyzer.calculate_statistics(host_counts)
        
        print(f"Total Hosts:             {len(state.hosts)}")
        print(f"Mean primaries per host: {current_host_stats.mean:.2f}")
        print(f"Std Dev:                 {current_host_stats.std_dev:.2f}")
        print(f"Coefficient of Variation: {current_host_stats.cv:.2%}")
        print(f"Range:                   [{current_host_stats.min_val} - {current_host_stats.max_val}]")
        print(f"Median:                  {current_host_stats.p50:.1f}")
        print()
        
        # Show top 10 most loaded hosts
        sorted_hosts = sorted(state.hosts.items(), key=lambda x: x[1].primary_count, reverse=True)
        print("Top 10 Most Loaded Hosts:")
        for hostname, host_info in sorted_hosts[:10]:
            print(f"  {hostname:25s}: {host_info.primary_count:5d} primaries across {len(host_info.osd_ids):2d} OSDs")
        print()
    
    # Analyze pool-level distribution
    if state.pools:
        print("=" * 80)
        print("CURRENT STATE - POOL LEVEL")
        print("=" * 80)
        from ceph_primary_balancer.analyzer import get_pool_statistics_summary
        
        pool_stats = get_pool_statistics_summary(state)
        print(f"Total Pools: {len(state.pools)}")
        
        if pool_stats:
            avg_pool_cv = sum(ps.cv for ps in pool_stats.values()) / len(pool_stats)
            print(f"Average Pool CV: {avg_pool_cv:.2%}")
            print()
            
            # Sort pools by CV (worst first)
            sorted_pools = sorted(pool_stats.items(), key=lambda x: x[1].cv, reverse=True)
            print(f"{'Pool ID':<10} {'Pool Name':<25} {'PG Count':<10} {'CV':<10} {'Range'}")
            print("-" * 80)
            for pool_id, pool_stat in sorted_pools:
                pool = state.pools[pool_id]
                print(f"{pool_id:<10} {pool.pool_name:<25} {pool.pg_count:<10} "
                      f"{pool_stat.cv:<10.2%} [{pool_stat.min_val}-{pool_stat.max_val}]")
        print()
    
    # Determine if optimization is needed
    print("=" * 80)
    print("OPTIMIZATION ASSESSMENT")
    print("=" * 80)
    
    target_cv = 0.10  # 10% target
    
    if current_osd_stats.cv <= target_cv:
        print(f"✓ Cluster is already well-balanced!")
        print(f"  Current OSD CV ({current_osd_stats.cv:.2%}) is within target ({target_cv:.2%})")
        return state, [], current_osd_stats, current_osd_stats
    
    print(f"⚠ Cluster could benefit from optimization")
    print(f"  Current OSD CV: {current_osd_stats.cv:.2%}")
    print(f"  Target CV:      {target_cv:.2%}")
    print(f"  Improvement potential: {((current_osd_stats.cv - target_cv) / current_osd_stats.cv * 100):.1f}%")
    print()
    
    # Run minimal optimization for smoke test
    print("=" * 80)
    print("RUNNING OPTIMIZATION (Limited)")
    print("=" * 80)
    print(f"Using three-dimensional scoring (OSD: 50%, Host: 30%, Pool: 20%)")
    print(f"Note: Running only 2 iterations for large cluster smoke test")
    print()
    
    # Create a copy of state for optimization
    import copy
    original_state = copy.deepcopy(state)
    
    # Create scorer with default weights
    scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
    
    # Run optimization with very limited iterations (just to verify it works)
    print("Running optimization (limited to 2 iterations for testing)...")
    swaps = optimizer.optimize_primaries(state, target_cv=target_cv, scorer=scorer, max_iterations=2)
    
    # Calculate final statistics
    final_osd_counts = [osd.primary_count for osd in state.osds.values()]
    final_osd_stats = analyzer.calculate_statistics(final_osd_counts)
    
    print()
    print("=" * 80)
    print("OPTIMIZATION RESULTS")
    print("=" * 80)
    print(f"Proposed swaps: {len(swaps)}")
    print()
    print(f"OSD-Level Improvement:")
    print(f"  CV:      {current_osd_stats.cv:.2%} → {final_osd_stats.cv:.2%} "
          f"({((current_osd_stats.cv - final_osd_stats.cv) / current_osd_stats.cv * 100):.1f}% reduction)")
    print(f"  Std Dev: {current_osd_stats.std_dev:.2f} → {final_osd_stats.std_dev:.2f}")
    print(f"  Range:   [{current_osd_stats.min_val}-{current_osd_stats.max_val}] → "
          f"[{final_osd_stats.min_val}-{final_osd_stats.max_val}]")
    print()
    
    if state.hosts:
        final_host_counts = [host.primary_count for host in state.hosts.values()]
        final_host_stats = analyzer.calculate_statistics(final_host_counts)
        print(f"Host-Level Improvement:")
        print(f"  CV:      {current_host_stats.cv:.2%} → {final_host_stats.cv:.2%} "
              f"({((current_host_stats.cv - final_host_stats.cv) / current_host_stats.cv * 100):.1f}% reduction)")
        print(f"  Std Dev: {current_host_stats.std_dev:.2f} → {final_host_stats.std_dev:.2f}")
        print()
    
    # Count affected entities
    affected_osds = set()
    affected_hosts = set()
    for swap in swaps:
        affected_osds.add(swap.old_primary)
        affected_osds.add(swap.new_primary)
        old_osd = original_state.osds.get(swap.old_primary)
        new_osd = original_state.osds.get(swap.new_primary)
        if old_osd and old_osd.host:
            affected_hosts.add(old_osd.host)
        if new_osd and new_osd.host:
            affected_hosts.add(new_osd.host)
    
    print(f"Impact:")
    print(f"  OSDs affected:  {len(affected_osds)} of {len(state.osds)} ({len(affected_osds)/len(state.osds)*100:.1f}%)")
    print(f"  Hosts affected: {len(affected_hosts)} of {len(state.hosts)} ({len(affected_hosts)/len(state.hosts)*100:.1f}%)")
    print()
    
    return original_state, state, swaps, current_osd_stats, final_osd_stats


def generate_reports(original_state, optimized_state, swaps):
    """Generate JSON and markdown reports."""
    
    print("=" * 80)
    print("GENERATING REPORTS")
    print("=" * 80)
    
    output_dir = os.path.join(os.path.dirname(__file__), 'fixtures', 'production_cluster', 'reports')
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate JSON export
    json_path = os.path.join(output_dir, 'analysis.json')
    exporter = JSONExporter(tool_version="0.4.0")
    exporter.export_to_file(
        current_state=original_state,
        proposed_state=optimized_state,
        swaps=swaps,
        output_path=json_path,
        cluster_fsid="production-cluster",
        analysis_type="full"
    )
    print(f"✓ JSON report exported: {json_path}")
    
    # Generate markdown report
    md_path = os.path.join(output_dir, 'analysis.md')
    reporter = Reporter(top_n=10)
    reporter.generate_markdown_report(
        current=original_state,
        proposed=optimized_state,
        swaps=swaps,
        output_path=md_path
    )
    print(f"✓ Markdown report generated: {md_path}")
    
    print()
    print(f"Reports saved to: {output_dir}")


if __name__ == '__main__':
    try:
        result = analyze_production_cluster()
        if len(result) == 5:
            original, optimized, swaps, current_stats, final_stats = result
        else:
            # Optimization skipped
            state, swaps, current_stats, final_stats = result
            original = optimized = state
        
        if swaps:
            generate_reports(original, optimized, swaps)
        
        print()
        print("=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)
        
    except FileNotFoundError as e:
        print(f"Error: Could not find fixture file: {e}")
        print("Make sure production cluster data is in tests/fixtures/production_cluster/")
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()
