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
├── models.py          # Data models: OSDInfo, PoolInfo, HostInfo, PGInfo, ClusterState, SwapProposal
├── collector.py       # Gathers data from Ceph CLI (ceph osd tree, ceph pg dump)
├── analyzer.py        # Statistics, donor/receiver identification (OSD-level and per-pool)
├── scorer.py          # CV-based composite scoring across OSD/host/pool dimensions
├── optimizers/        # Optimization algorithms
│   ├── base.py        # OptimizerBase ABC, OptimizerRegistry, stats tracking
│   ├── greedy.py      # Greedy optimizer (primary algorithm) with O(1) delta scoring
│   └── batch_greedy.py
├── reporter.py        # Terminal output
├── exporter.py        # JSON export
├── script_generator.py # Generates bash scripts with pg-upmap-primary commands
├── config.py          # Config file loading
├── cli.py             # CLI entry point
└── benchmark/         # Benchmark framework
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

### 5. Documentation Is Not A Feature

- README.md: What it does, how to install, how to use. That's it.
- Code comments explain *why*, not *what*.
- No separate docs for completed phases, historical benchmarks, or development history. That's what git log is for.
- No planning documents in the repo. Plans go in issues or discussion, not committed markdown.

### 6. Git Discipline

- Commit messages: imperative mood, explain the *why*. "Fix pool-level scoring to use CV instead of raw variance" not "Update scorer.py".
- One concern per commit. Don't mix refactoring with feature work.
- No generated files in the repo (benchmark results, HTML reports, comparison outputs).

## Completed Algorithmic Fixes

### ~~Critical: Pool balancing is broken by design~~ FIXED

Per-pool donor/receiver identification implemented in `analyzer.identify_pool_donors_receivers()`. The optimizer now generates swap candidates from both OSD-level and pool-level donors/receivers, so pool-imbalanced swaps are proposed even when involved OSDs are near the global mean.

### ~~Critical: Swap evaluation is O(N) when it should be O(1)~~ FIXED

`scorer.calculate_swap_delta()` computes score deltas from the 4-5 values that actually change. No state copies, no re-aggregation. `ScoreComponents` caches variance, mean, and sum-of-squares for O(1) delta computation. The old `simulate_swap_score()` remains only as a test oracle.

### ~~Major: Dimensional scores are not comparable~~ FIXED

Composite score now uses CV (coefficient of variation = std/mean) for each dimension instead of raw variance. CV is scale-invariant, so dimensions are comparable regardless of their absolute magnitude. Score = `w_osd * osd_cv + w_host * host_cv + w_pool * avg_pool_cv`.

### ~~Minor: Termination only checks OSD dimension~~ FIXED

Termination now checks ALL enabled dimensions (OSD, host, pool). The optimizer continues until every enabled dimension has CV at or below target_cv. The CLI pre-optimization check also considers all enabled dimensions before skipping optimization.

### ~~Minor: No per-pool optimization loop~~ FIXED

Each iteration now runs two candidate searches: the existing global search (OSD-level + pool-level donors/receivers) and a per-pool search that targets pools with CV above target. The per-pool search iterates all PGs in high-CV pools without donor/receiver filtering, catching swaps that threshold-based filtering misses. The better swap wins.

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
All three dimensions improve simultaneously. Multi-dimension termination + per-pool search dramatically improved pool convergence (e.g., Multi-pool Pool CV: 0.377 → 0.190). Runtime increased for Large scenario due to more iterations; `max_iterations` caps this in production.

### Phase 4: Pool CV convergence
Pool CV remains the hardest dimension to converge. OSD and host reach floor quickly, but pool CV stalls well above target — especially for sparse clusters (many OSDs, few PGs per pool). Three complementary improvements, each independently valuable:

#### 4a. Two-phase weight strategy
The `target_distance` dynamic strategy transitions weight toward pool too gradually — OSD/host are near their floor but still consuming 30%+ of weight. A hard cutover after OSD/host converge lets the optimizer spend its remaining iteration budget on pool CV.

1. Add `TwoPhaseWeightStrategy` to `weight_strategies.py` — hard switch from OSD/host-focused weights `(0.55, 0.35, 0.10)` to pool-focused weights `(0.10, 0.05, 0.85)` when OSD and host CV both drop below `phase1_threshold` (default: `2x target_cv`). Register in `WeightStrategyFactory`.
2. Add `TestTwoPhaseWeightStrategy` to `test_weight_strategies.py` — phase 1 behavior, phase 2 behavior, transition boundary, edge cases.
3. Validate with benchmarks — compare `target_distance` vs `two_phase` on existing scenarios. Key metric: final pool CV at same iteration budget. No CLI changes needed (`--dynamic-strategy two_phase` works via factory).

#### 4b. Per-pool candidate search improvements
The per-pool search in `find_best_pool_swap()` skips pools within 10% of their CV floor — too conservative for pools that still have viable swaps. The `pool_pgs` index is also rebuilt every iteration.

1. Relax the CV floor margin — use a tighter margin (e.g., 2% or absolute delta) so pools close to but not at floor are still searched.
2. Cache the `pool_pgs` index across iterations, invalidating only when a swap changes pool membership.
3. Benchmark impact on sparse scenarios (840 OSD / 30 pool).

#### 4c. Adaptive donor/receiver thresholds for small pools
The fixed 10% donor/receiver threshold in `identify_pool_donors_receivers()` fails for small pools. With 5 primaries/OSD average, the threshold is 5.5 — almost no OSDs qualify as donors, starving the global search of pool-improving candidates.

1. Use pool-size-adaptive thresholds: for pools with mean < 10 primaries/OSD, use absolute threshold (±1) instead of percentage.
2. Add tests for small-pool donor/receiver identification.
3. Benchmark impact on multi-pool scenarios.

## Code Style

- No docstrings on obvious functions. Reserve docstrings for non-obvious behavior.
- Type hints on public function signatures. Not on local variables.
- f-strings for formatting. No `.format()` or `%`.
- `dataclass` for data models. No hand-rolled `__init__` boilerplate.
- Sort imports: stdlib, third-party, local. One blank line between groups.
