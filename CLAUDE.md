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
│   ├── batch_greedy.py
│   ├── tabu_search.py
│   └── simulated_annealing.py
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

## Remaining Algorithmic Issues

### Minor: No per-pool optimization loop

The optimizer finds the single globally-best swap per iteration. A per-pool loop (for each pool, find best swap within that pool's PGs, then pick the globally best) would improve pool-level convergence, especially for clusters with many small pools.

## What NOT To Do

- Don't write documentation about features that don't work yet
- Don't create planning docs — just do the work
- Don't add abstractions "for future flexibility"
- Don't preserve backward compatibility with code that was wrong

## Progress

### Phase 1: Clean Slate — DONE
Removed `plans/`, deprecated `optimizer.py` wrapper, stale docs, release notes files, one-off scripts.

### Phase 2: Fix the algorithm — 4 of 5 DONE
1. ~~Make swap evaluation O(1) using delta scoring~~ DONE
2. ~~Implement per-pool donor/receiver identification~~ DONE
3. ~~Normalize dimensional scores using CV~~ DONE
4. ~~Fix termination to check all enabled dimensions~~ DONE
5. Design the multi-dimension loop: for each pool → find pool-level swaps → score globally → pick best

### Phase 3: Validate with benchmarks — IN PROGRESS
Benchmark results with CV-based scoring (greedy, target CV 0.05, max 2000 iterations):
```
Scenario                        Swaps   Time     OSD CV          Host CV         Pool CV
Small 10 OSD / 2 pool              11   0.0s  0.238 → 0.071  0.085 → 0.000  0.283 → 0.135
Medium 100 OSD / 5 pool           479   3.8s  0.266 → 0.050  0.092 → 0.001  0.372 → 0.168
Large 500 OSD / 10 pool          1487  70.0s  0.299 → 0.114  0.093 → 0.000  0.523 → 0.382
Sparse 840 OSD / 30 pool          191   4.8s  0.327 → 0.225  0.056 → 0.000  0.248 → 0.212
Multi-pool 60 OSD / 20            390   3.4s  0.301 → 0.050  0.105 → 0.001  0.538 → 0.377
```
All three dimensions improve simultaneously. Host CV reaches near-zero. Pool CV improves meaningfully but plateaus — remaining items 4 and 5 above will address this.

## Code Style

- No docstrings on obvious functions. Reserve docstrings for non-obvious behavior.
- Type hints on public function signatures. Not on local variables.
- f-strings for formatting. No `.format()` or `%`.
- `dataclass` for data models. No hand-rolled `__init__` boilerplate.
- Sort imports: stdlib, third-party, local. One blank line between groups.
