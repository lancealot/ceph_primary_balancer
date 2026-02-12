#!/usr/bin/env python3
"""
Benchmark: Tabu Search vs Batch Greedy on a large cluster.

Generates a large synthetic cluster (500 OSDs, 50 hosts, 10 pools, 50k PGs)
and runs both optimizers head-to-head with identical initial state. Tabu search
is given a high iteration limit (5000) to allow thorough exploration beyond
local optima via its diversification mechanism.

Usage:
    python3 -m benchmarks.tabu_vs_batch_greedy
    python3 benchmarks/tabu_vs_batch_greedy.py
"""

import sys
import os
import time
import json
from copy import deepcopy
from pathlib import Path
from dataclasses import asdict

# Ensure the project src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ceph_primary_balancer.benchmark.generator import generate_synthetic_cluster
from ceph_primary_balancer.analyzer import calculate_statistics, get_pool_statistics_summary
from ceph_primary_balancer.optimizers import OptimizerRegistry
from ceph_primary_balancer.scorer import Scorer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CLUSTER_CONFIG = {
    "num_osds": 500,
    "num_hosts": 50,
    "num_pools": 10,
    "pgs_per_pool": 5000,
    "replication_factor": 3,
    "imbalance_cv": 0.30,
    "imbalance_pattern": "random",
    "seed": 42,
}

TARGET_CV = 0.10
SEED = 42

# Tabu search gets a high iteration budget to explore past local optima.
TABU_MAX_ITERATIONS = 5000
BATCH_GREEDY_MAX_ITERATIONS = 5000  # same budget for fairness

TABU_PARAMS = {
    "tabu_tenure": 50,
    "aspiration_threshold": 0.1,
    "diversification_enabled": True,
    "diversification_threshold": 100,
    "max_candidates": 50,
}

BATCH_GREEDY_PARAMS = {
    "batch_size": 10,
    "conflict_detection": "strict",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def compute_cv_summary(state):
    """Return dict of OSD / host / pool CV values for a cluster state."""
    osd_counts = [osd.primary_count for osd in state.osds.values()]
    osd_stats = calculate_statistics(osd_counts)

    host_cv = None
    if state.hosts:
        host_counts = [h.primary_count for h in state.hosts.values()]
        host_stats = calculate_statistics(host_counts)
        host_cv = host_stats.cv

    pool_cv = None
    if state.pools:
        pool_stats = get_pool_statistics_summary(state)
        if pool_stats:
            pool_cv = sum(ps.cv for ps in pool_stats.values()) / len(pool_stats)

    return {
        "osd_cv": osd_stats.cv,
        "host_cv": host_cv,
        "pool_cv": pool_cv,
        "osd_min": osd_stats.min_val,
        "osd_max": osd_stats.max_val,
        "osd_mean": osd_stats.mean,
        "osd_std": osd_stats.std_dev,
    }


def format_cv(cv):
    return f"{cv:.4%}" if cv is not None else "N/A"


def print_separator(char="=", width=72):
    print(char * width)


def print_cv_table(label, summary):
    print(f"  {label}:")
    print(f"    OSD  CV:  {format_cv(summary['osd_cv'])}")
    print(f"    Host CV:  {format_cv(summary['host_cv'])}")
    print(f"    Pool CV:  {format_cv(summary['pool_cv'])}")
    print(f"    OSD range: {summary['osd_min']} .. {summary['osd_max']}  "
          f"(mean={summary['osd_mean']:.1f}, std={summary['osd_std']:.1f})")


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------
def run_benchmark():
    print_separator()
    print("BENCHMARK: Tabu Search vs Batch Greedy  (large cluster)")
    print_separator()
    print()

    # ---- Generate cluster ------------------------------------------------
    print(f"Generating cluster: {CLUSTER_CONFIG['num_osds']} OSDs, "
          f"{CLUSTER_CONFIG['num_hosts']} hosts, "
          f"{CLUSTER_CONFIG['num_pools']} pools, "
          f"{CLUSTER_CONFIG['pgs_per_pool']} PGs/pool "
          f"({CLUSTER_CONFIG['num_pools'] * CLUSTER_CONFIG['pgs_per_pool']} total PGs)")
    print(f"Imbalance: CV={CLUSTER_CONFIG['imbalance_cv']}, "
          f"pattern={CLUSTER_CONFIG['imbalance_pattern']}, seed={SEED}")
    print()

    t0 = time.time()
    base_state = generate_synthetic_cluster(**CLUSTER_CONFIG)
    gen_time = time.time() - t0
    print(f"Cluster generated in {gen_time:.2f}s")

    initial_summary = compute_cv_summary(base_state)
    print_cv_table("Initial state", initial_summary)
    print()

    # ---- Prepare two independent copies ----------------------------------
    state_tabu = deepcopy(base_state)
    state_batch = deepcopy(base_state)

    results = {}

    # ---- Run Batch Greedy ------------------------------------------------
    print_separator("-")
    print(f"Running Batch Greedy  (max_iterations={BATCH_GREEDY_MAX_ITERATIONS})")
    print_separator("-")

    batch_opt = OptimizerRegistry.get_optimizer(
        "batch_greedy",
        target_cv=TARGET_CV,
        max_iterations=BATCH_GREEDY_MAX_ITERATIONS,
        verbose=True,
        **BATCH_GREEDY_PARAMS,
    )

    t0 = time.time()
    batch_swaps = batch_opt.optimize(state_batch)
    batch_time = time.time() - t0

    batch_summary = compute_cv_summary(state_batch)
    batch_stats = batch_opt.get_stats()

    print()
    print_cv_table("Batch Greedy result", batch_summary)
    print(f"    Swaps applied: {len(batch_swaps)}")
    print(f"    Iterations:    {batch_stats['iterations']}")
    print(f"    Wall time:     {batch_time:.2f}s")
    print(f"    Batches:       {batch_stats['algorithm_specific']['batches_applied']}")
    print(f"    Avg batch sz:  {batch_stats['algorithm_specific']['avg_batch_size']:.1f}")
    print()

    results["batch_greedy"] = {
        "cv": batch_summary,
        "swaps": len(batch_swaps),
        "iterations": batch_stats["iterations"],
        "wall_time_s": batch_time,
        "stats": batch_stats,
    }

    # ---- Run Tabu Search -------------------------------------------------
    print_separator("-")
    print(f"Running Tabu Search  (max_iterations={TABU_MAX_ITERATIONS})")
    print(f"  tenure={TABU_PARAMS['tabu_tenure']}, "
          f"aspiration={TABU_PARAMS['aspiration_threshold']}, "
          f"diversification_threshold={TABU_PARAMS['diversification_threshold']}, "
          f"max_candidates={TABU_PARAMS['max_candidates']}")
    print_separator("-")

    tabu_opt = OptimizerRegistry.get_optimizer(
        "tabu_search",
        target_cv=TARGET_CV,
        max_iterations=TABU_MAX_ITERATIONS,
        verbose=True,
        **TABU_PARAMS,
    )

    t0 = time.time()
    tabu_swaps = tabu_opt.optimize(state_tabu)
    tabu_time = time.time() - t0

    tabu_summary = compute_cv_summary(state_tabu)
    tabu_stats = tabu_opt.get_stats()

    print()
    print_cv_table("Tabu Search result", tabu_summary)
    print(f"    Swaps applied:      {len(tabu_swaps)}")
    print(f"    Iterations:         {tabu_stats['iterations']}")
    print(f"    Wall time:          {tabu_time:.2f}s")
    print(f"    Diversifications:   {tabu_stats['algorithm_specific']['diversifications']}")
    print(f"    Tabu overrides:     {tabu_stats['algorithm_specific']['tabu_overrides']}")
    print(f"    Best score updates: {tabu_stats['algorithm_specific']['best_score_updates']}")
    print(f"    Max tabu list size: {tabu_stats['algorithm_specific']['tabu_list_max_size']}")
    print()

    results["tabu_search"] = {
        "cv": tabu_summary,
        "swaps": len(tabu_swaps),
        "iterations": tabu_stats["iterations"],
        "wall_time_s": tabu_time,
        "stats": tabu_stats,
    }

    # ---- Comparison ------------------------------------------------------
    print_separator("=")
    print("COMPARISON SUMMARY")
    print_separator("=")
    print()
    print(f"{'Metric':<28} {'Batch Greedy':>16} {'Tabu Search':>16} {'Winner':>12}")
    print("-" * 72)

    def winner(bg, ts, lower_better=True):
        if bg is None or ts is None:
            return "---"
        if lower_better:
            return "Tabu" if ts < bg else ("Batch" if bg < ts else "Tie")
        return "Tabu" if ts > bg else ("Batch" if bg > ts else "Tie")

    rows = [
        ("OSD CV", batch_summary["osd_cv"], tabu_summary["osd_cv"], True),
        ("Host CV", batch_summary["host_cv"], tabu_summary["host_cv"], True),
        ("Pool CV", batch_summary["pool_cv"], tabu_summary["pool_cv"], True),
        ("Swaps applied", len(batch_swaps), len(tabu_swaps), True),
        ("Iterations", batch_stats["iterations"], tabu_stats["iterations"], True),
        ("Wall time (s)", batch_time, tabu_time, True),
    ]

    for label, bg_val, ts_val, lower in rows:
        if isinstance(bg_val, float) and bg_val < 1:
            bg_str = format_cv(bg_val)
            ts_str = format_cv(ts_val)
        else:
            bg_str = f"{bg_val}" if bg_val is not None else "N/A"
            ts_str = f"{ts_val}" if ts_val is not None else "N/A"
            if isinstance(bg_val, float):
                bg_str = f"{bg_val:.2f}"
                ts_str = f"{ts_val:.2f}"
        w = winner(bg_val, ts_val, lower)
        print(f"  {label:<26} {bg_str:>16} {ts_str:>16} {w:>12}")

    print()

    # ---- Highlight -------------------------------------------------------
    bg_osd = batch_summary["osd_cv"]
    ts_osd = tabu_summary["osd_cv"]
    if ts_osd < bg_osd:
        pct = (bg_osd - ts_osd) / bg_osd * 100
        print(f"  -> Tabu Search achieved {pct:.1f}% lower OSD CV than Batch Greedy.")
    elif bg_osd < ts_osd:
        pct = (ts_osd - bg_osd) / ts_osd * 100
        print(f"  -> Batch Greedy achieved {pct:.1f}% lower OSD CV than Tabu Search.")
    else:
        print("  -> Both algorithms achieved the same OSD CV.")

    print(f"  -> Tabu Search used {tabu_time / batch_time:.1f}x the wall time of Batch Greedy.")
    print()

    # ---- Save JSON results -----------------------------------------------
    output_dir = Path(__file__).resolve().parent.parent / "benchmark_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "tabu_vs_batch_greedy.json"

    export = {
        "config": {
            "cluster": CLUSTER_CONFIG,
            "target_cv": TARGET_CV,
            "tabu_max_iterations": TABU_MAX_ITERATIONS,
            "batch_greedy_max_iterations": BATCH_GREEDY_MAX_ITERATIONS,
            "tabu_params": TABU_PARAMS,
            "batch_greedy_params": BATCH_GREEDY_PARAMS,
        },
        "initial_cv": initial_summary,
        "results": results,
    }

    with open(output_path, "w") as f:
        json.dump(export, f, indent=2, default=str)

    print(f"Results saved to: {output_path}")
    print_separator()


if __name__ == "__main__":
    run_benchmark()
