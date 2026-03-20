# CLAUDE.md — Development Rules for ceph_primary_balancer

## Project Identity

**One-liner:** Balance primary PG assignments across Ceph OSDs, hosts, and pools using `ceph osd pg-upmap-primary`.

**Core constraint:** This tool only changes *which* OSD in an existing acting set is primary. It never moves PGs between OSDs. Zero data movement.

**Runtime dependency:** Python 3.8+ standard library only. No pip packages in production.

## Build & Test Commands

```bash
# Run all tests
PYTHONPATH=src pytest tests/ -v

# Run a single test file
PYTHONPATH=src pytest tests/test_scorer.py -v

# Run tests with coverage
PYTHONPATH=src pytest tests/ -v --cov=src/ceph_primary_balancer --cov-report=term-missing

# Run quick benchmark
PYTHONPATH=src python3 -m ceph_primary_balancer.benchmark_cli quick

# Run the CLI (requires live Ceph cluster or offline data)
PYTHONPATH=src python3 -m ceph_primary_balancer.cli --help
```

## Architecture

```
src/ceph_primary_balancer/
├── models.py            # Data models: OSDInfo, PoolInfo, HostInfo, PGInfo, ClusterState, SwapProposal
├── collector.py         # Gathers data from Ceph CLI (ceph osd tree, ceph pg dump)
├── analyzer.py          # Statistics, donor/receiver identification (OSD-level and per-pool)
├── scorer.py            # CV-based composite scoring across OSD/host/pool dimensions
├── dynamic_scorer.py    # DynamicScorer: adaptive weight updates during optimization
├── weight_strategies.py # Weight strategies: target_distance, two_phase
├── optimizers/
│   ├── base.py          # OptimizerBase ABC, stats tracking
│   └── greedy.py        # Greedy optimizer with O(1) delta scoring, stall detection, focused fallback
├── reporter.py          # Terminal output
├── exporter.py          # JSON export
├── script_generator.py  # Generates bash scripts with pg-upmap-primary commands
├── config.py            # Config file loading
├── offline.py           # Offline/air-gapped mode: load cluster data from exported archives
├── cli.py               # CLI entry point
├── benchmark_cli.py     # Benchmark CLI entry point
└── benchmark/           # Benchmark framework (generator, profiler, runner, scenarios, reporter)
```

## Development Principles

### 1. Simplicity Is Non-Negotiable

- **One optimizer, done right.** No optimizer registry, no strategy pattern, no plugin architecture. One algorithm in one file. If we find a better algorithm, we replace the old one.
- **No backward-compatibility shims.** No deprecated wrappers, no re-exports, no "will be removed in v2.0" code. Change it or don't.
- **No speculative abstractions.** Don't add interfaces, registries, or factory patterns for hypothetical future algorithms. YAGNI.
- **Delete, don't deprecate.** Dead code is worse than no code. When something is replaced, remove the old version completely.

### 2. The Algorithm Is The Product

- Every code change should be evaluated against one question: **does this make the balancing better, faster, or more correct?**
- If a change doesn't improve balance quality, performance, or correctness, it probably shouldn't exist.
- Benchmark before and after every algorithmic change. Numbers, not opinions.

### 3. Performance-Aware Design

- **Never copy full state to evaluate a swap.** The hot path is swap evaluation. Score deltas must be O(1), not O(N).
- **Donors/receivers must be per-dimension.** Global OSD-level donors/receivers cannot drive pool-level balancing. Each dimension needs its own imbalance analysis.
- **Normalize before combining.** Raw variances from different dimensions have different scales. Use coefficient of variation (CV) or normalize to [0,1] before weighting.

### 4. Testing Philosophy

- Tests prove the algorithm works. They don't prove the framework is clever.
- One `conftest.py` with shared cluster-building fixtures. No duplicated setup across 20 test files.
- Integration tests should test real workflows, not reimplementations of unit tests at a higher level.
- Benchmark tests are valuable. Keep them, but keep them focused.

### 5. Documentation

- README.md: What it does, how to install, how to use.
- `docs/` may contain user-facing guides (usage, offline mode, installation, troubleshooting).
- Code comments explain *why*, not *what*.
- No docs for completed phases, historical benchmarks, or development history. That's what git log is for.
- No planning documents in the repo. Plans go in issues or discussion, not committed markdown.

### 6. Git Discipline

- Commit messages: imperative mood, explain the *why*. "Fix pool-level scoring to use CV instead of raw variance" not "Update scorer.py".
- One concern per commit. Don't mix refactoring with feature work.
- No generated files in the repo (benchmark results, HTML reports, comparison outputs).

## What NOT To Do

- Don't write documentation about features that don't work yet
- Don't create planning docs — just do the work
- Don't add abstractions "for future flexibility"
- Don't preserve backward compatibility with code that was wrong

## Progress

### Phase 1: Clean Slate — DONE
Removed `plans/`, deprecated `optimizer.py` wrapper, stale docs, release notes files, one-off scripts.

### Phase 2: Fix the algorithm — DONE
1. ~~Make swap evaluation O(1) using delta scoring~~ DONE
2. ~~Implement per-pool donor/receiver identification~~ DONE
3. ~~Normalize dimensional scores using CV~~ DONE
4. ~~Fix termination to check all enabled dimensions~~ DONE
5. ~~Per-pool optimization loop for pool-level convergence~~ DONE

### Phase 3: Validate with benchmarks — DONE
Benchmark results with all Phase 2 fixes (greedy, target CV 0.05, max 2000 iterations):
```
Scenario                        Swaps   Time     OSD CV          Host CV         Pool CV
Small 10 OSD / 2 pool              21   0.0s  0.200 → 0.020  0.066 → 0.000  0.264 → 0.081
Medium 100 OSD / 5 pool           302   5.5s  0.264 → 0.022  0.091 → 0.000  0.441 → 0.287
Large 500 OSD / 10 pool          1973 144.2s  0.300 → 0.024  0.095 → 0.002  0.563 → 0.264
Sparse 840 OSD / 30 pool          196   9.5s  0.327 → 0.221  0.056 → 0.000  0.248 → 0.208
Multi-pool 60 OSD / 20            782  19.8s  0.301 → 0.007  0.105 → 0.001  0.538 → 0.190
```

### Phase 4: Pool CV convergence — DONE
Pool CV is the hardest dimension to converge. OSD and host reach floor quickly, but pool CV stalls above target — especially for sparse clusters (many OSDs, few PGs per pool). Pool CV floor is structural: limited by acting set constraints (each PG can only choose primary from its ~3-member acting set) and integer primary counts. The `_pool_cv_floor` formula gives a theoretical lower bound; the true floor is higher due to acting set constraints.

#### 4a. Two-phase weight strategy — DONE
`TwoPhaseWeightStrategy` hard-switches from target_distance weights to pool-focused `(0.10, 0.05, 0.85)` when OSD and host CV both drop below `phase1_threshold`. Default threshold: `max(2 * target_cv, 0.15)` — the floor prevents the threshold from becoming uselessly low at small target_cv values.

#### 4b. Per-pool candidate search improvements — DONE
- CV floor margin: started at 1.10x (too conservative, skipped pools that could still improve), tightened to 1.02x so only pools truly at their theoretical floor are skipped. A *tighter* margin means *fewer* pools skipped — this is the permissive direction. The 1.02x value was chosen deliberately and should not be loosened.
- `pool_pgs` index cached for the entire optimization run (pool membership never changes across swaps)

#### 4c. Adaptive donor/receiver thresholds for small pools — DONE
For pools with `1 <= mean < 10` primaries/OSD, `identify_pool_donors_receivers()` uses absolute ±1 threshold instead of percentage. Prevents dead zones where no OSDs qualify as donors/receivers in small pools.

### Phase 5: Performance optimizations — DONE
1. **Default target_cv: 0.10 → 0.01** — optimizer runs to swap exhaustion ("no beneficial swaps found") rather than stopping at an arbitrary target. Stagnation detection is the safety net.
2. **Pre-swap ScoreComponents cached per iteration** — computed once, shared across `find_best_swap`, `find_best_pool_swap`, `find_best_focused_swap`, and stall detection. Eliminates 2-5 redundant O(pools) computations per iteration.
3. **Post-swap components shared** — stagnation detection and `_record_iteration` share a single post-swap `calculate_score_with_components` call. Total scorer calls per iteration: 2 (down from 4-7).
4. **DynamicScorer iteration counting fixed** — scorer iteration count now tracks actual iterations (2 per optimizer iteration) instead of being inflated 4-7×. Weight updates happen at the configured interval relative to real optimizer progress.

Live cluster results (832 OSDs, 30 hosts, 30 pools, 5232 PGs):
```
Dimension   Before    After   Improvement
OSD CV      39.24%    7.66%      -80.5%
Host CV      9.51%    0.39%      -95.9%
Pool CV     67.80%   18.77%      -72.3%
Swaps: 1081, Time: 218s, Termination: swap exhaustion
```
Pool CV floor (18.77%) is structural — 26/30 pools are sparse (too few PGs per OSD), 4 balanceable pools all converged to within 2% of their theoretical minimum.

### Phase 6: Feature completeness — DONE
Features added after the algorithmic core stabilized:

1. **Configurable optimization levels** — `--optimization-levels osd,host,pool` enables/disables dimensions independently. Scorer skips disabled dimensions entirely (not just zero-weighted). Auto-normalizes weights for enabled levels.

2. **Dynamic weight strategies** — `DynamicScorer` wraps `Scorer` with periodic weight recalculation. Two strategies implemented in `weight_strategies.py`:
   - `target_distance` (default): weights proportional to distance from target CV, minimum weight floor prevents dimension neglect.
   - `two_phase`: target_distance in phase 1, hard-switches to pool-focused weights once OSD/host converge.

3. **Focused fallback search** — `find_best_focused_swap()` in `greedy.py` breaks local minima by creating a single-dimension scorer targeting the worst dimension. Bounded regression limit (default 0.001) prevents the focused swap from significantly worsening other dimensions.

4. **Stagnation detection** — tracks fallback frequency and composite score plateau over a sliding window. Terminates optimization when stuck rather than wasting iterations.

5. **Offline mode** — `--from-file` loads cluster data from exported `.tar.gz` archives for air-gapped environments. Export script, metadata validation, age warnings, manual health verification in generated scripts.

6. **OptimizerBase ABC** — common interface for optimizer algorithms with scorer management, stats tracking, termination checking, progress reporting. Batch greedy optimizer was added then removed per "delete, don't deprecate" — only `GreedyOptimizer` remains.

## Roadmap

Potential improvements, roughly ordered by impact:

### Research — DONE

#### Comparison with Ceph's built-in read balancer

Ceph added a native read (primary) balancer in Reef (v18, August 2023). It uses `pg-upmap-primary` — the same mechanism we use. Two modes: `read` (primary-only) and `upmap-read` (combines capacity + primary balancing). Reef only had the offline path (`osdmaptool --read`); the automatic online balancer mode was added in Squid (v19, 2024). Note: the Linux kernel client still does not support `pg-upmap-primary` as of late 2025 — kernel-based RBD and CephFS mounts will fail if these mappings exist.

**How Ceph's read balancer works (from OSDMap.cc source):**

1. **Architecture:** Python mgr module (`balancer/module.py`) is just an orchestrator — iterates pools and calls `OSDMap::balance_primaries()` in C++ once per pool. All algorithmic work is in C++.

2. **Scoring:** `read_balance_score = max_primaries_on_any_osd / avg_primaries_per_osd` (RBS_FAIR mode). A ratio where 1.0 = perfect. This is a per-pool minimax metric — it only looks at the single most overloaded OSD, not the distribution shape. Sensitive to outliers rather than overall spread.

3. **Optimal score floor:** `ceil(PGs / OSDs) / (PGs / OSDs)`. For 32 PGs across 10 OSDs: `ceil(3.2) / 3.2 = 1.25`. Acknowledges the integer constraint but only at the single-OSD level.

4. **Desired distribution:** For each OSD: `desired = (pgs_on_osd / replica_count) * primary_affinity`, then scaled so the sum equals `pg_num`. The deviation score is `actual_primaries - desired_primaries` (positive = donor, negative = receiver).

5. **Swap loop:** Multi-pass greedy. Each pass iterates ALL PGs in the pool. For each PG, considers each OSD in the acting set. A swap is taken only when `(prim_score - potential_score) > 1` — the combined deviation gap must exceed 1.0. Scores are updated incrementally after each swap within a pass. The loop terminates when a full pass produces zero swaps.

6. **Safety net:** After all swaps, recalculates `read_balance_score`. If the score did NOT improve, **all mappings are discarded**.

7. **The `> 1` guard is critical for sparse pools:** When most OSDs have 0-1 primaries in a pool (the sparse case), deviation scores cluster near 0. The `(prim_score - potential_score) > 1` condition means almost no swaps qualify. The algorithm effectively gives up on sparse pools — exactly where balancing is hardest.

8. **Scope:** Operates **per-pool independently**. The Python module iterates pools sequentially. No cross-pool awareness, no global OSD load tracking, no coordination between pools.

9. **First-viable vs best-swap:** Takes the first beneficial swap found in PG iteration order, not the best swap. Suboptimal convergence compared to evaluating all candidates.

10. **Size-aware variant:** `calc_desired_prims_for_osdsizeopt` (RB_OSDSIZEOPT mode) accounts for heterogeneous OSD sizes using a `read_ratio`/`write_ratio` IO model. Technology preview status.

**Where our approach is stronger:**

| Dimension | Ceph built-in | ceph_primary_balancer |
|---|---|---|
| **Scoring metric** | Max-deviation ratio (single worst OSD) | CV across all OSDs (distribution shape) |
| **Dimensions** | OSD-level only | OSD + host + pool (3-dimensional) |
| **Host awareness** | None — no host-level balancing | Explicit host CV dimension with cross-host tie-breaking |
| **Cross-pool optimization** | Per-pool independently | Global optimization with per-pool donor/receiver identification |
| **Adaptive weights** | None | DynamicScorer with target_distance and two_phase strategies |
| **Swap selection** | First viable swap in PG iteration order | Best swap via scored evaluation of all candidates |
| **Local minima escape** | None — stops when no single swap improves | Three-tier search + focused fallback with regression limits |
| **Structural floor awareness** | Optimal score floor (single OSD) | Per-pool CV floor + unbalanceable pool exclusion |
| **Stagnation detection** | None — terminates when zero swaps in a full pass | Rolling window + per-dimension plateau tracking |
| **Sparse pool handling** | `> 1` guard effectively disables balancing | Adaptive ±1 thresholds for small pools, CV floor margin |
| **Termination safety** | Discards all changes if score didn't improve | Incremental — each swap is independently validated |

**Where Ceph's approach has advantages:**

| Dimension | Ceph built-in | ceph_primary_balancer |
|---|---|---|
| **Integration** | Native ceph-mgr module, runs automatically | External tool, requires manual invocation |
| **Primary affinity** | Respects `primary_affinity` per-OSD settings | Does not consider primary affinity (see Known Limitations) |
| **Client requirement** | Built-in, ships with Ceph | Separate install, Python 3.8+ |

**Key gap in Ceph's balancer — sparse pools are effectively ignored:**

The `(prim_score - potential_score) > 1` guard in the swap loop means a swap only fires when the combined deviation gap exceeds 1.0. In sparse pools (e.g., 32 PGs across 100 OSDs), most OSDs have 0-1 primaries and deviation scores cluster near 0. Almost no swaps qualify, so the algorithm does very little. Our approach handles this via adaptive ±1 donor/receiver thresholds and per-pool CV floor estimation that recognizes the structural limit and works within it.

**Key gap in Ceph's balancer — no host-level awareness:**

Ceph tracker issue #42321 (the original feature request, still "Fix Under Review" as of 2024) explicitly noted that the read balancer "balanced OSDs within nodes effectively, but significant imbalances persisted between different hosts." This is exactly the problem our host CV dimension solves. Ceph's read balancer optimizes per-OSD primary counts but has no concept of host-level, rack-level, or any failure-domain-level primary distribution. In a cluster where hosts have different numbers of OSDs, perfectly balanced per-OSD counts can still produce heavily imbalanced per-host read load.

**Key gap in Ceph's balancer — no cross-pool coordination:**

By optimizing each pool independently, Ceph's balancer can create conflicts where balancing pool A worsens the global OSD distribution. Our approach optimizes all pools simultaneously with a weighted composite score, so improving pool CV doesn't come at the cost of OSD or host balance.

**Ideas worth adopting:**

- **Primary affinity:** Some operators set `primary_affinity=0` on specific OSDs (e.g., OSDs being drained, slow hardware, or asymmetric workload roles). We should respect this — currently we'd try to assign primaries to OSDs that the operator explicitly excluded. See "Known Limitations" below.

**Conclusion:** Our tool fills a genuine gap. Ceph's native read balancer is a single-dimension, per-pool greedy optimizer with no host awareness and no cross-pool coordination. For small homogeneous clusters with few pools, it works fine. For large clusters with many pools, heterogeneous host sizes, or sparse pool distributions — exactly the hard cases — our multi-dimensional approach with adaptive weights and structural floor awareness produces materially better results.

### Known Limitations

- **`primary_affinity` is assumed to be 1.0 for all OSDs.** Ceph allows operators to set `primary_affinity` per OSD (0.0–1.0) to control which OSDs are preferred as primaries. Common uses: draining an OSD, deprioritizing slow hardware, or asymmetric workload roles. This tool does not read or respect `primary_affinity` — it will assign primaries to OSDs with `primary_affinity=0` if they appear in acting sets. Operators using non-default `primary_affinity` should review generated scripts before applying.

### Cleanup
- **`_check_termination()` redundancy** — `base.py:_check_termination()` recalculates OSD/host/pool stats that are already available from the cached `ScoreComponents`. Should accept pre-computed components.
- **`_record_iteration()` fallback** — `base.py:_record_iteration()` calls `calculate_score()` when no pre-computed score is passed. The greedy optimizer always passes a score, but the fallback path exists. Could be simplified.
- **Remove `target_cv` plumbing** — `target_cv` defaults to 0.01, which is low enough that stagnation detection always terminates the optimizer before the CV target is reached. No realistic scenario benefits from a higher value. Hardcode 0.01 (or a module constant) and remove the flag from CLI args, config parsing, optimizer constructors, DynamicScorer, weight strategies, and benchmark infrastructure.
- **Remove `docs/ceph-upstream-pr-outline.md`** — Planning document for an upstream Ceph contribution. Should be migrated to the ceph/ceph fork where the PR work will happen, then deleted from this repo.

## Code Style

- No docstrings on obvious functions. Reserve docstrings for non-obvious behavior.
- Type hints on public function signatures. Not on local variables.
- f-strings for formatting. No `.format()` or `%`.
- `dataclass` for data models. No hand-rolled `__init__` boilerplate.
- Sort imports: stdlib, third-party, local. One blank line between groups.
