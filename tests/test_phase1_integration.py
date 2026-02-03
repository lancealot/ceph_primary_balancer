"""
Comprehensive Integration Test for Phase 1: Host-Level Balancing

This test simulates a realistic Ceph cluster with:
- 4 hosts with varying numbers of OSDs
- 1000 PGs distributed with intentional imbalance
- Realistic primary distribution scenarios

The test demonstrates:
- Host-level imbalance detection
- Multi-dimensional optimization
- Before/after metrics comparison
- Improvement in both OSD and host-level balance
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ceph_primary_balancer.models import PGInfo, OSDInfo, HostInfo, ClusterState
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.optimizer import optimize_primaries
from ceph_primary_balancer.analyzer import calculate_statistics


def create_realistic_imbalanced_cluster():
    """
    Create a realistic simulated Ceph cluster with intentional imbalance.
    
    Cluster configuration:
    - 4 hosts: host1 (6 OSDs), host2 (6 OSDs), host3 (4 OSDs), host4 (4 OSDs)
    - Total: 20 OSDs
    - 1000 PGs distributed with host-level imbalance
    
    Imbalance scenario:
    - Host1 and Host2 are overloaded with primaries
    - Host3 and Host4 are underutilized
    - OSD-level distribution is moderately balanced
    - Host-level distribution is severely imbalanced
    """
    
    # Define host topology
    host_configs = {
        "host1": [0, 1, 2, 3, 4, 5],      # 6 OSDs
        "host2": [6, 7, 8, 9, 10, 11],    # 6 OSDs
        "host3": [12, 13, 14, 15],        # 4 OSDs
        "host4": [16, 17, 18, 19],        # 4 OSDs
    }
    
    # Initialize OSDs
    osds = {}
    for hostname, osd_ids in host_configs.items():
        for osd_id in osd_ids:
            osds[osd_id] = OSDInfo(
                osd_id=osd_id,
                host=hostname,
                primary_count=0,
                total_pg_count=0
            )
    
    # Initialize hosts
    hosts = {}
    for hostname, osd_ids in host_configs.items():
        hosts[hostname] = HostInfo(
            hostname=hostname,
            osd_ids=osd_ids,
            primary_count=0,
            total_pg_count=0
        )
    
    # Create PGs with intentional imbalance
    pgs = {}
    
    # Primary distribution pattern: heavily favor host1 and host2
    # This creates host-level imbalance even with moderate OSD-level balance
    primary_distribution = [
        # host1 OSDs get 60 primaries each = 360 total
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # OSD 0: 60 primaries (repeated pattern)
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,  # OSD 1: 60 primaries
        2, 2, 2, 2, 2, 2, 2, 2, 2, 2,  # OSD 2: 60 primaries
        3, 3, 3, 3, 3, 3, 3, 3, 3, 3,  # OSD 3: 60 primaries
        4, 4, 4, 4, 4, 4, 4, 4, 4, 4,  # OSD 4: 60 primaries
        5, 5, 5, 5, 5, 5, 5, 5, 5, 5,  # OSD 5: 60 primaries
        # host2 OSDs get 55 primaries each = 330 total
        6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,   # OSD 6: 55 primaries
        7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,   # OSD 7: 55 primaries
        8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,   # OSD 8: 55 primaries
        9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9,   # OSD 9: 55 primaries
        10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,  # OSD 10: 55 primaries
        11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11,  # OSD 11: 55 primaries
        # host3 OSDs get 40 primaries each = 160 total
        12, 12, 12, 12, 12, 12, 12, 12,  # OSD 12: 40 primaries
        13, 13, 13, 13, 13, 13, 13, 13,  # OSD 13: 40 primaries
        14, 14, 14, 14, 14, 14, 14, 14,  # OSD 14: 40 primaries
        15, 15, 15, 15, 15, 15, 15, 15,  # OSD 15: 40 primaries
        # host4 OSDs get 37-38 primaries each = 150 total
        16, 16, 16, 16, 16, 16, 16, 16, 16,  # OSD 16: 38 primaries
        17, 17, 17, 17, 17, 17, 17, 17, 17,  # OSD 17: 38 primaries
        18, 18, 18, 18, 18, 18, 18, 18,     # OSD 18: 37 primaries
        19, 19, 19, 19, 19, 19, 19, 19,     # OSD 19: 37 primaries
    ]
    
    # Extend to 1000 PGs by repeating and filling remaining
    pg_count = 1000
    all_osds = list(range(20))
    
    for pg_idx in range(pg_count):
        pgid = f"1.{pg_idx:x}"  # Pool 1, hex PG number
        
        # Determine primary based on distribution pattern
        if pg_idx < len(primary_distribution) * 6:  # Repeat pattern
            primary = primary_distribution[pg_idx % len(primary_distribution)]
        else:
            # Fill remaining with round-robin
            primary = all_osds[pg_idx % 20]
        
        # Create realistic acting set (primary + 2 replicas)
        # Ensure replicas span different hosts to enable cross-host swaps
        acting = [primary]
        primary_host = osds[primary].host
        
        # Strategy: Place replicas on different hosts, prioritizing underutilized hosts
        # This ensures swaps from overloaded to underloaded hosts are possible
        remaining_osds = [osd for osd in all_osds if osd != primary]
        
        # Sort by host to get diverse placement
        remaining_osds.sort(key=lambda x: osds[x].host)
        
        # Add replicas from different hosts
        added_hosts = {primary_host}
        for osd_id in remaining_osds:
            if len(acting) >= 3:
                break
            replica_host = osds[osd_id].host
            if replica_host not in added_hosts:
                acting.append(osd_id)
                added_hosts.add(replica_host)
        
        # If we still need more OSDs (edge case), add any available
        for osd_id in remaining_osds:
            if len(acting) >= 3:
                break
            if osd_id not in acting:
                acting.append(osd_id)
        
        # Create PG
        pgs[pgid] = PGInfo(pgid=pgid, pool_id=1, acting=acting)
        
        # Update OSD counts
        osds[primary].primary_count += 1
        for osd_id in acting:
            osds[osd_id].total_pg_count += 1
    
    # Aggregate counts at host level
    for osd in osds.values():
        if osd.host in hosts:
            hosts[osd.host].primary_count += osd.primary_count
            hosts[osd.host].total_pg_count += osd.total_pg_count
    
    return ClusterState(pgs=pgs, osds=osds, hosts=hosts)


def print_cluster_statistics(state: ClusterState, label: str):
    """Print detailed statistics for the cluster at OSD and host levels."""
    print(f"\n{'='*70}")
    print(f"{label}")
    print('='*70)
    
    # OSD-level statistics
    osd_counts = [osd.primary_count for osd in state.osds.values()]
    osd_stats = calculate_statistics(osd_counts)
    
    print(f"\n📊 OSD-Level Statistics:")
    print(f"  Total OSDs:       {len(state.osds)}")
    print(f"  Total PGs:        {len(state.pgs)}")
    print(f"  Mean primaries:   {osd_stats.mean:.1f}")
    print(f"  Std Dev:          {osd_stats.std_dev:.2f}")
    print(f"  CV:               {osd_stats.cv:.2%} {'✓ BALANCED' if osd_stats.cv < 0.10 else '⚠ IMBALANCED'}")
    print(f"  Range:            [{osd_stats.min_val} - {osd_stats.max_val}]")
    print(f"  Median:           {osd_stats.p50:.1f}")
    
    # Host-level statistics
    if state.hosts:
        host_counts = [host.primary_count for host in state.hosts.values()]
        host_stats = calculate_statistics(host_counts)
        
        print(f"\n🖥️  Host-Level Statistics:")
        print(f"  Total Hosts:      {len(state.hosts)}")
        print(f"  Mean primaries:   {host_stats.mean:.1f}")
        print(f"  Std Dev:          {host_stats.std_dev:.2f}")
        print(f"  CV:               {host_stats.cv:.2%} {'✓ BALANCED' if host_stats.cv < 0.05 else '⚠ IMBALANCED'}")
        print(f"  Range:            [{host_stats.min_val} - {host_stats.max_val}]")
        print(f"  Median:           {host_stats.p50:.1f}")
        
        # Show per-host breakdown
        print(f"\n  Per-Host Distribution:")
        sorted_hosts = sorted(state.hosts.items(), 
                            key=lambda x: x[1].primary_count, 
                            reverse=True)
        for hostname, host in sorted_hosts:
            pct = (host.primary_count / len(state.pgs)) * 100
            bar_width = int(pct / 2)  # Scale to ~50 chars max
            bar = '█' * bar_width
            status = '✓' if abs(host.primary_count - host_stats.mean) < host_stats.std_dev else '⚠'
            print(f"    {hostname:10s}: {host.primary_count:4d} primaries ({pct:5.1f}%) {bar} {status}")
    
    return osd_stats, host_stats if state.hosts else None


def test_comprehensive_host_balancing_integration():
    """
    Comprehensive integration test for Phase 1 host-level balancing.
    
    This test demonstrates:
    1. Creation of realistic imbalanced cluster
    2. Detection of host-level imbalance
    3. Multi-dimensional optimization
    4. Significant improvement in both OSD and host balance
    5. Before/after metrics comparison
    """
    print("\n" + "="*70)
    print("PHASE 1: HOST-LEVEL BALANCING - COMPREHENSIVE INTEGRATION TEST")
    print("="*70)
    
    # Step 1: Create imbalanced cluster
    print("\n📦 Creating realistic simulated Ceph cluster...")
    print("   - 4 hosts with 20 total OSDs")
    print("   - 1000 PGs with intentional host-level imbalance")
    
    state = create_realistic_imbalanced_cluster()
    
    # Step 2: Analyze current state
    print_cluster_statistics(state, "INITIAL STATE (Before Optimization)")
    initial_osd_stats, initial_host_stats = print_cluster_statistics(state, "")
    
    # Step 3: Run optimization with host-aware scoring
    print(f"\n{'='*70}")
    print("🔧 Running Host-Aware Optimization...")
    print('='*70)
    print("\nOptimization Configuration:")
    print("  Scorer weights:   OSD=70%, Host=30% (Phase 1 defaults)")
    print("  Target OSD CV:    10%")
    print("  Algorithm:        Greedy with multi-dimensional scoring")
    
    # Create Phase 1 scorer (70% OSD, 30% Host)
    scorer = Scorer(w_osd=0.7, w_host=0.3, w_pool=0.0)
    
    # Run optimization
    print("\nOptimizing...\n")
    swaps = optimize_primaries(
        state,
        target_cv=0.10,
        max_iterations=1000,
        scorer=scorer
    )
    
    # Step 4: Analyze optimized state
    print(f"\n{'='*70}")
    print(f"Optimization complete: {len(swaps)} swaps applied")
    print('='*70)
    
    final_osd_stats, final_host_stats = print_cluster_statistics(state, "FINAL STATE (After Optimization)")
    
    # Step 5: Calculate improvements
    print(f"\n{'='*70}")
    print("📈 IMPROVEMENT SUMMARY")
    print('='*70)
    
    osd_cv_improvement = ((initial_osd_stats.cv - final_osd_stats.cv) / initial_osd_stats.cv) * 100
    osd_std_improvement = ((initial_osd_stats.std_dev - final_osd_stats.std_dev) / initial_osd_stats.std_dev) * 100
    
    print(f"\n🎯 OSD-Level Improvements:")
    print(f"  CV reduction:        {initial_osd_stats.cv:.2%} → {final_osd_stats.cv:.2%} ({osd_cv_improvement:+.1f}%)")
    print(f"  Std Dev reduction:   {initial_osd_stats.std_dev:.2f} → {final_osd_stats.std_dev:.2f} ({osd_std_improvement:+.1f}%)")
    print(f"  Range improvement:   [{initial_osd_stats.min_val}-{initial_osd_stats.max_val}] → [{final_osd_stats.min_val}-{final_osd_stats.max_val}]")
    
    if initial_host_stats and final_host_stats:
        host_cv_improvement = ((initial_host_stats.cv - final_host_stats.cv) / initial_host_stats.cv) * 100
        host_std_improvement = ((initial_host_stats.std_dev - final_host_stats.std_dev) / initial_host_stats.std_dev) * 100
        
        print(f"\n🖥️  Host-Level Improvements:")
        print(f"  CV reduction:        {initial_host_stats.cv:.2%} → {final_host_stats.cv:.2%} ({host_cv_improvement:+.1f}%)")
        print(f"  Std Dev reduction:   {initial_host_stats.std_dev:.2f} → {final_host_stats.std_dev:.2f} ({host_std_improvement:+.1f}%)")
        print(f"  Range improvement:   [{initial_host_stats.min_val}-{initial_host_stats.max_val}] → [{final_host_stats.min_val}-{final_host_stats.max_val}]")
    
    print(f"\n⚙️  Optimization Efficiency:")
    print(f"  Total swaps:         {len(swaps)}")
    print(f"  PGs affected:        {len(swaps)} / {len(state.pgs)} ({len(swaps)/len(state.pgs)*100:.1f}%)")
    if len(swaps) > 0:
        print(f"  Avg improvement:     {(initial_osd_stats.cv - final_osd_stats.cv) / len(swaps):.4%} CV per swap")
    else:
        print(f"  Avg improvement:     N/A (no swaps needed)")
    
    # Step 6: Validate results
    print(f"\n{'='*70}")
    print("✅ VALIDATION")
    print('='*70)
    
    validations = []
    
    # OSD-level validation
    if final_osd_stats.cv <= 0.10:
        validations.append(("✓", "OSD CV target achieved", f"{final_osd_stats.cv:.2%} ≤ 10%"))
    else:
        validations.append(("⚠", "OSD CV target not fully achieved", f"{final_osd_stats.cv:.2%}"))
    
    if final_osd_stats.cv < initial_osd_stats.cv:
        validations.append(("✓", "OSD balance improved", f"{osd_cv_improvement:.1f}% reduction"))
    
    # Host-level validation
    if final_host_stats and initial_host_stats:
        if final_host_stats.cv < initial_host_stats.cv:
            validations.append(("✓", "Host balance improved", f"{host_cv_improvement:.1f}% reduction"))
        
        if final_host_stats.cv <= 0.05:
            validations.append(("✓", "Host CV excellent", f"{final_host_stats.cv:.2%} ≤ 5%"))
    
    # Data integrity validation
    initial_total = sum(osd.primary_count for osd in state.osds.values())
    if initial_total == len(state.pgs):
        validations.append(("✓", "Primary count integrity", f"{initial_total} = {len(state.pgs)} PGs"))
    
    for status, check, detail in validations:
        print(f"  {status} {check:30s} {detail}")
    
    print(f"\n{'='*70}")
    print("🎉 PHASE 1 INTEGRATION TEST COMPLETE")
    print('='*70)
    
    # Return results for programmatic validation
    return {
        'initial_osd_cv': initial_osd_stats.cv,
        'final_osd_cv': final_osd_stats.cv,
        'initial_host_cv': initial_host_stats.cv if initial_host_stats else 0,
        'final_host_cv': final_host_stats.cv if final_host_stats else 0,
        'osd_improvement_pct': osd_cv_improvement,
        'host_improvement_pct': host_cv_improvement if initial_host_stats else 0,
        'swaps_count': len(swaps),
    }


if __name__ == "__main__":
    results = test_comprehensive_host_balancing_integration()
    
    # Verify minimum improvement thresholds
    print("\n" + "="*70)
    print("AUTOMATED VALIDATION")
    print("="*70)
    
    assertions = []
    
    # OSD-level assertions
    assertions.append((
        results['osd_improvement_pct'] > 5,
        f"OSD CV improved by >5%: {results['osd_improvement_pct']:.1f}%"
    ))
    
    assertions.append((
        results['final_osd_cv'] < results['initial_osd_cv'],
        f"OSD CV reduced: {results['initial_osd_cv']:.2%} → {results['final_osd_cv']:.2%}"
    ))
    
    # Host-level assertions
    if results['initial_host_cv'] > 0:
        assertions.append((
            results['host_improvement_pct'] > 2,
            f"Host CV improved by >2%: {results['host_improvement_pct']:.1f}%"
        ))
        
        assertions.append((
            results['final_host_cv'] < results['initial_host_cv'],
            f"Host CV reduced: {results['initial_host_cv']:.2%} → {results['final_host_cv']:.2%}"
        ))
    
    assertions.append((
        results['swaps_count'] > 0,
        f"Swaps generated: {results['swaps_count']}"
    ))
    
    all_passed = True
    for passed, message in assertions:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {message}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✅ All automated validations passed!")
        sys.exit(0)
    else:
        print("\n❌ Some validations failed!")
        sys.exit(1)
