"""
End-to-end comparison of all optimizers and weight strategies.

Tests a complex cluster: 800 OSDs, 30 hosts, ~5000 PGs, 30 pools
with a mix of replicated (size=3) and erasure-coded (k+m=4+2, 8+3) pools
of varying sizes.

With ~5000 PGs across 800 OSDs the cluster is sparse (~6 primaries/OSD),
which is realistic for clusters with many small pools. The absolute CV
values will be high, but relative comparison between optimizers is valid.

Run with:
    PYTHONPATH=src pytest tests/test_optimizer_comparison.py -v -s --tb=short
"""

import copy
import time
from typing import Dict, Any, List

import pytest

from ceph_primary_balancer.benchmark.generator import generate_multi_pool_scenario
from ceph_primary_balancer.optimizers import OptimizerRegistry
from ceph_primary_balancer.analyzer import calculate_statistics, get_pool_statistics_summary


# ---------------------------------------------------------------------------
# Cluster configuration
# ---------------------------------------------------------------------------

NUM_OSDS = 800
NUM_HOSTS = 30
TARGET_CV = 0.10
MAX_ITERATIONS = 500
SEED = 42

# 30 pools: mix of replicated (size 3), EC 4+2 (size 6), EC 8+3 (size 11)
# ~5120 total PGs
POOLS_CONFIG = [
    # --- 15 replicated pools (size 3) ---
    {"pgs": 256, "replication": 3, "imbalance_cv": 0.35, "pattern": "random"},
    {"pgs": 128, "replication": 3, "imbalance_cv": 0.25, "pattern": "concentrated"},
    {"pgs": 512, "replication": 3, "imbalance_cv": 0.40, "pattern": "gradual"},
    {"pgs": 64,  "replication": 3, "imbalance_cv": 0.20, "pattern": "bimodal"},
    {"pgs": 256, "replication": 3, "imbalance_cv": 0.30, "pattern": "random"},
    {"pgs": 128, "replication": 3, "imbalance_cv": 0.35, "pattern": "random"},
    {"pgs": 64,  "replication": 3, "imbalance_cv": 0.30, "pattern": "concentrated"},
    {"pgs": 256, "replication": 3, "imbalance_cv": 0.25, "pattern": "gradual"},
    {"pgs": 128, "replication": 3, "imbalance_cv": 0.40, "pattern": "bimodal"},
    {"pgs": 64,  "replication": 3, "imbalance_cv": 0.35, "pattern": "random"},
    {"pgs": 256, "replication": 3, "imbalance_cv": 0.30, "pattern": "random"},
    {"pgs": 128, "replication": 3, "imbalance_cv": 0.20, "pattern": "concentrated"},
    {"pgs": 64,  "replication": 3, "imbalance_cv": 0.25, "pattern": "gradual"},
    {"pgs": 256, "replication": 3, "imbalance_cv": 0.35, "pattern": "random"},
    {"pgs": 128, "replication": 3, "imbalance_cv": 0.30, "pattern": "bimodal"},
    # --- 10 EC 4+2 pools (size 6) ---
    {"pgs": 128, "replication": 6, "imbalance_cv": 0.35, "pattern": "random"},
    {"pgs": 256, "replication": 6, "imbalance_cv": 0.30, "pattern": "concentrated"},
    {"pgs": 64,  "replication": 6, "imbalance_cv": 0.40, "pattern": "gradual"},
    {"pgs": 128, "replication": 6, "imbalance_cv": 0.25, "pattern": "random"},
    {"pgs": 256, "replication": 6, "imbalance_cv": 0.35, "pattern": "bimodal"},
    {"pgs": 128, "replication": 6, "imbalance_cv": 0.30, "pattern": "random"},
    {"pgs": 64,  "replication": 6, "imbalance_cv": 0.35, "pattern": "concentrated"},
    {"pgs": 128, "replication": 6, "imbalance_cv": 0.40, "pattern": "gradual"},
    {"pgs": 256, "replication": 6, "imbalance_cv": 0.25, "pattern": "random"},
    {"pgs": 128, "replication": 6, "imbalance_cv": 0.30, "pattern": "bimodal"},
    # --- 5 EC 8+3 pools (size 11) ---
    {"pgs": 128, "replication": 11, "imbalance_cv": 0.35, "pattern": "random"},
    {"pgs": 64,  "replication": 11, "imbalance_cv": 0.30, "pattern": "concentrated"},
    {"pgs": 256, "replication": 11, "imbalance_cv": 0.40, "pattern": "gradual"},
    {"pgs": 128, "replication": 11, "imbalance_cv": 0.25, "pattern": "random"},
    {"pgs": 64,  "replication": 11, "imbalance_cv": 0.35, "pattern": "bimodal"},
]

ALGORITHMS = ["greedy", "batch_greedy", "tabu_search"]

WEIGHT_CONFIGS = [
    {"name": "static_default", "dynamic_weights": False},
    {"name": "dyn_proportional", "dynamic_weights": True, "dynamic_strategy": "proportional"},
    {"name": "dyn_target_distance", "dynamic_weights": True, "dynamic_strategy": "target_distance"},
    {"name": "dyn_adaptive_hybrid", "dynamic_weights": True, "dynamic_strategy": "adaptive_hybrid"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def measure_cvs(state) -> Dict[str, float]:
    """Extract OSD, host, and average pool CVs from a cluster state."""
    osd_counts = [osd.primary_count for osd in state.osds.values()]
    osd_cv = calculate_statistics(osd_counts).cv

    host_counts = [h.primary_count for h in state.hosts.values()]
    host_cv = calculate_statistics(host_counts).cv

    pool_stats = get_pool_statistics_summary(state)
    pool_cvs = [ps.cv for ps in pool_stats.values()] if pool_stats else [0.0]
    avg_pool_cv = sum(pool_cvs) / len(pool_cvs)
    max_pool_cv = max(pool_cvs) if pool_cvs else 0.0

    return {
        "osd_cv": osd_cv,
        "host_cv": host_cv,
        "avg_pool_cv": avg_pool_cv,
        "max_pool_cv": max_pool_cv,
    }


def run_optimizer(state, algorithm: str, weight_cfg: dict) -> Dict[str, Any]:
    """Run a single optimizer configuration and return metrics."""
    state_copy = copy.deepcopy(state)

    kwargs = {
        "target_cv": TARGET_CV,
        "max_iterations": MAX_ITERATIONS,
        "dynamic_weights": weight_cfg.get("dynamic_weights", False),
    }
    if weight_cfg.get("dynamic_weights"):
        kwargs["dynamic_strategy"] = weight_cfg["dynamic_strategy"]
        kwargs["weight_update_interval"] = 10

    if algorithm == "batch_greedy":
        kwargs["batch_size"] = 10
    elif algorithm == "tabu_search":
        kwargs["tabu_tenure"] = 50

    optimizer = OptimizerRegistry.get_optimizer(algorithm, **kwargs)

    t0 = time.time()
    swaps = optimizer.optimize(state_copy)
    elapsed = time.time() - t0

    final_cvs = measure_cvs(state_copy)

    return {
        "algorithm": algorithm,
        "weights": weight_cfg["name"],
        "swaps": len(swaps),
        "iterations": optimizer.stats.iterations,
        "time_s": elapsed,
        **final_cvs,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cluster_state():
    """Generate the complex test cluster once for all tests."""
    print(f"\nGenerating cluster: {NUM_OSDS} OSDs, {NUM_HOSTS} hosts, "
          f"{len(POOLS_CONFIG)} pools, seed={SEED}")
    state = generate_multi_pool_scenario(
        num_pools=len(POOLS_CONFIG),
        pools_config=POOLS_CONFIG,
        num_osds=NUM_OSDS,
        num_hosts=NUM_HOSTS,
        seed=SEED,
    )
    initial = measure_cvs(state)
    total_pgs = len(state.pgs)
    print(f"  Total PGs: {total_pgs}")
    print(f"  Initial CVs — OSD: {initial['osd_cv']:.3f}  "
          f"Host: {initial['host_cv']:.3f}  "
          f"Pool(avg): {initial['avg_pool_cv']:.3f}  "
          f"Pool(max): {initial['max_pool_cv']:.3f}")
    return state


@pytest.fixture(scope="module")
def initial_cvs(cluster_state):
    return measure_cvs(cluster_state)


# ---------------------------------------------------------------------------
# Main comparison test
# ---------------------------------------------------------------------------

def test_optimizer_comparison(cluster_state, initial_cvs):
    """Run all optimizer+weight combinations and print a ranked comparison."""
    results = []

    total = len(ALGORITHMS) * len(WEIGHT_CONFIGS)
    run_num = 0

    for algo in ALGORITHMS:
        for wcfg in WEIGHT_CONFIGS:
            run_num += 1
            label = f"{algo}/{wcfg['name']}"
            print(f"\n  [{run_num}/{total}] {label} ...", end="", flush=True)

            result = run_optimizer(cluster_state, algo, wcfg)
            results.append(result)

            print(f" {result['time_s']:.1f}s, {result['swaps']} swaps, "
                  f"OSD={result['osd_cv']:.3f} Host={result['host_cv']:.3f} "
                  f"Pool={result['avg_pool_cv']:.3f}")

    # Sort by composite score (lower = better)
    for r in results:
        r["composite"] = 0.5 * r["osd_cv"] + 0.3 * r["host_cv"] + 0.2 * r["avg_pool_cv"]
    results.sort(key=lambda r: r["composite"])

    # Print ranked table
    print(f"\n{'='*130}")
    print(f"  COMPARISON RESULTS — {NUM_OSDS} OSDs, {NUM_HOSTS} hosts, "
          f"{len(POOLS_CONFIG)} pools, {len(cluster_state.pgs)} PGs, "
          f"target CV={TARGET_CV}, max_iter={MAX_ITERATIONS}")
    print(f"  Initial: OSD CV={initial_cvs['osd_cv']:.3f}  "
          f"Host CV={initial_cvs['host_cv']:.3f}  "
          f"Pool CV(avg)={initial_cvs['avg_pool_cv']:.3f}  "
          f"Pool CV(max)={initial_cvs['max_pool_cv']:.3f}")
    print(f"{'='*130}")
    print(f"{'Rank':<5} {'Algorithm':<24} {'Weights':<22} "
          f"{'Swaps':>6} {'Iters':>6} {'Time':>8} "
          f"{'OSD CV':>8} {'Host CV':>8} {'Pool CV':>9} {'MaxPool':>8} {'Score':>8}")
    print(f"{'-'*130}")

    for i, r in enumerate(results, 1):
        print(f"{i:<5} {r['algorithm']:<24} {r['weights']:<22} "
              f"{r['swaps']:>6} {r['iterations']:>6} {r['time_s']:>7.1f}s "
              f"{r['osd_cv']:>8.4f} {r['host_cv']:>8.4f} "
              f"{r['avg_pool_cv']:>9.4f} {r['max_pool_cv']:>8.4f} {r['composite']:>8.4f}")

    print(f"{'='*130}")

    # Category winners
    best_osd = min(results, key=lambda r: r["osd_cv"])
    best_host = min(results, key=lambda r: r["host_cv"])
    best_pool = min(results, key=lambda r: r["avg_pool_cv"])
    best_time = min(results, key=lambda r: r["time_s"])
    best_overall = results[0]

    print(f"\n  Best OSD CV:     {best_osd['algorithm']}/{best_osd['weights']} = {best_osd['osd_cv']:.4f}")
    print(f"  Best Host CV:    {best_host['algorithm']}/{best_host['weights']} = {best_host['host_cv']:.4f}")
    print(f"  Best Pool CV:    {best_pool['algorithm']}/{best_pool['weights']} = {best_pool['avg_pool_cv']:.4f}")
    print(f"  Fastest:         {best_time['algorithm']}/{best_time['weights']} = {best_time['time_s']:.1f}s")
    print(f"  Best Overall:    {best_overall['algorithm']}/{best_overall['weights']} = {best_overall['composite']:.4f}")

    # Sanity: every optimizer should improve or maintain OSD CV
    for r in results:
        assert r["osd_cv"] <= initial_cvs["osd_cv"] + 0.01, \
            f"{r['algorithm']}/{r['weights']}: OSD CV got worse"
