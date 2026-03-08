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
PYTHONPATH=src pytest tests/test_optimizer.py -v

# Run tests with coverage
PYTHONPATH=src pytest tests/ -v --cov=src/ceph_primary_balancer --cov-report=term-missing

# Run quick benchmark
PYTHONPATH=src python3 -m ceph_primary_balancer.benchmark_cli quick

# Run the CLI (requires live Ceph cluster or offline data)
PYTHONPATH=src python3 -m ceph_primary_balancer.cli --help
```

## Architecture (Target — post-simplification)

```
src/ceph_primary_balancer/
├── models.py          # Data models: OSDInfo, PoolInfo, HostInfo, PGInfo, ClusterState, SwapProposal
├── collector.py       # Gathers data from Ceph CLI (ceph osd tree, ceph pg dump)
├── analyzer.py        # Statistics, donor/receiver identification
├── scorer.py          # Composite scoring across OSD/host/pool dimensions
├── optimizer.py       # The optimization algorithm (single file, one strategy done well)
├── reporter.py        # Terminal output
├── exporter.py        # JSON export
├── script_generator.py # Generates bash scripts with pg-upmap-primary commands
├── config.py          # Config file loading
├── cli.py             # CLI entry point
└── benchmark/         # Benchmark framework (kept lean)
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

## Known Algorithmic Issues (Must Fix)

These are the real problems, ordered by impact:

### Critical: Pool balancing is broken by design

Donors and receivers are identified **only at the OSD level** using global primary counts. The pool variance component of the score influences swap *selection* but cannot create swap *candidates* that the OSD-level analysis wouldn't already propose. If a pool is imbalanced but its OSDs are near the global mean, no swaps will ever be proposed for that pool. **Pool-level balancing is decorative, not functional.**

**Fix direction:** The optimization loop must iterate per-pool. For each pool, identify which OSDs have too many/too few primaries *for that specific pool*, then find swaps within that pool's PG set.

### Critical: Swap evaluation is O(N) when it should be O(1)

`simulate_swap_score` copies the entire cluster state (all OSDs, all hosts, all pools, recalculates all host aggregations) for every single candidate swap. For 100 OSDs with 10k PGs, this means thousands of full-state copies per iteration. A swap only changes 2 OSD counts, 2 host counts, and 1 pool's distribution — the score delta can be computed directly.

**Fix direction:** Compute score delta from the 4-5 values that actually change. No copies, no re-aggregation.

### Major: Dimensional scores are not comparable

The composite score adds `w_osd * Var(osd_counts) + w_host * Var(host_counts) + w_pool * Avg(Var(pool_counts))`. These variances have completely different scales (hosts have ~10 members with large counts; OSDs have ~100 members with small counts). The dimension with the largest absolute variance dominates regardless of weights.

**Fix direction:** Score each dimension using coefficient of variation (CV = std/mean), which is scale-invariant. Then weight and combine.

### Minor: Termination only checks OSD dimension

Even with host and pool optimization enabled, the optimizer terminates when OSD CV drops below target. Host and pool dimensions are ignored for termination.

## What NOT To Do

- Don't add more optimizer algorithms until the one we have works correctly
- Don't add dynamic weights until static weights produce correct results
- Don't add features (offline mode, YAML config, batch execution modes) until the core algorithm is solid
- Don't write documentation about features that don't work yet
- Don't create planning docs — just do the work
- Don't add abstractions "for future flexibility"
- Don't preserve backward compatibility with code that was wrong
- Don't optimize for performance before correctness (but do keep O(1) swap eval in mind from the start)

## Simplification Roadmap

### Phase 1: Clean Slate (delete cruft)
Remove: `plans/`, deprecated `optimizer.py` wrapper, stale docs, release notes files, one-off scripts, example configs that duplicate each other, unused optimizer variants (tabu, SA, batch_greedy), dynamic_scorer.py, weight_strategies.py. Consolidate tests. Add `conftest.py`.

### Phase 2: Fix the algorithm
1. Make swap evaluation O(1) using delta scoring
2. Implement per-pool donor/receiver identification
3. Normalize dimensional scores using CV
4. Fix termination to check all enabled dimensions
5. Design the multi-dimension loop: for each pool → find pool-level swaps → score globally → pick best

### Phase 3: Validate with benchmarks
Run before/after benchmarks. The algorithm should be:
- **Faster** (O(1) swap eval instead of full-state copy)
- **More effective** (pool-level balance actually improves)
- **Equally good or better** on OSD/host dimensions

## Code Style

- No docstrings on obvious functions. Reserve docstrings for non-obvious behavior.
- Type hints on public function signatures. Not on local variables.
- f-strings for formatting. No `.format()` or `%`.
- `dataclass` for data models. No hand-rolled `__init__` boilerplate.
- Sort imports: stdlib, third-party, local. One blank line between groups.
