# Benchmark Framework

Performance validation, quality assessment, and regression detection for the optimizer.

## Quick Start

```bash
# Quick smoke test
python3 -m ceph_primary_balancer.benchmark_cli quick

# Run standard benchmark suite
python3 -m ceph_primary_balancer.benchmark_cli run --suite standard

# Generate HTML dashboard
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite standard \
  --html-output dashboard.html
```

## Module Structure

```
benchmark/
├── __init__.py              # Package exports
├── generator.py             # Synthetic cluster generation (~400 lines)
├── profiler.py              # Performance/memory profiling (~300 lines)
├── quality_analyzer.py      # Quality metrics (~350 lines)
├── runner.py                # Benchmark orchestration (~300 lines)
├── reporter.py              # Multi-format reporting (~400 lines)
└── scenarios.py             # Standard test scenarios (~200 lines)
```

## Features

### Test Data Generation
- Multiple imbalance patterns (random, concentrated, gradual, bimodal, worst-case)
- Configurable cluster sizes (OSDs, hosts, pools, PGs)
- Erasure-coded pool support
- Reproducible via seeding

### Performance Profiling
- Runtime metrics (total, optimization, scoring)
- Memory tracking (peak, delta, per-PG, per-OSD)
- Throughput analysis (swaps/sec, iterations/sec)
- Scalability testing across multiple scales
- Complexity estimation (O(n), O(n²), etc.)

### Quality Analysis
- Multi-dimensional balance metrics (OSD/Host/Pool)
- Convergence analysis
- Fairness index (Jain's)
- Balance quality scoring (0-100)
- Stability testing (determinism)

### Reporting
- Terminal output (summary and detailed)
- JSON export (structured data)
- HTML dashboard (simple, no dependencies)

### Regression Detection
- Baseline comparison
- Configurable thresholds
- Severity classification (minor, moderate, severe)

## Usage Examples

### Generate Test Dataset

```python
from ceph_primary_balancer.benchmark import generate_synthetic_cluster, save_test_dataset

state = generate_synthetic_cluster(
    num_osds=100,
    num_hosts=10,
    num_pools=5,
    pgs_per_pool=1024,
    imbalance_cv=0.30,
    seed=42
)

save_test_dataset(state, 'my_dataset.json')
```

### Profile Optimization

```python
from ceph_primary_balancer.benchmark import profile_optimization

perf, mem = profile_optimization(state, target_cv=0.10)

print(f"Time: {perf.execution_time_total:.3f}s")
print(f"Memory: {mem.peak_memory_mb:.1f} MB")
print(f"Swaps: {perf.swaps_applied}")
```

### Analyze Quality

```python
from ceph_primary_balancer.benchmark import analyze_balance_quality

quality = analyze_balance_quality(original_state, optimized_state, swaps)

print(f"OSD CV: {quality.osd_cv_before:.1%} → {quality.osd_cv_after:.1%}")
print(f"Improvement: {quality.osd_cv_improvement_pct:+.1f}%")
print(f"Score: {quality.balance_score:.1f}/100")
```

### Run Complete Suite

```python
from ceph_primary_balancer.benchmark import BenchmarkSuite

suite = BenchmarkSuite({'seed': 42})
results = suite.run_all_benchmarks()
suite.save_results('benchmark_results.json')
```

## Standard Scenarios

### Performance
- `tiny_smoke`: 10 OSDs, 100 PGs
- `small_quick`: 50 OSDs, 1k PGs
- `medium_standard`: 100 OSDs, 10k PGs
- `large_production`: 500 OSDs, 50k PGs

### Quality
- `replicated_3_moderate`: 3x replication, moderate imbalance
- `replicated_3_severe`: 3x replication, severe imbalance
- `ec_8_3_severe`: EC 8+3, concentrated imbalance
- `multi_pool_complex`: Multiple pools, varied patterns

### Scalability
- Scales from 10 OSDs/100 PGs to 500 OSDs/25k PGs
- Automatic complexity analysis

## Integration with CI/CD

The framework is designed for automated testing:

```bash
# Run and save baseline
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite standard \
  --json-output baseline.json

# Later: detect regressions
python3 -m ceph_primary_balancer.benchmark_cli compare \
  --baseline baseline.json \
  --threshold 0.10

# Exit code: 0 = pass, 1 = regressions detected
echo $?
```

## Performance Expectations

| Cluster Size | Typical Duration | Memory Usage |
|--------------|------------------|--------------|
| 10 OSDs, 100 PGs | ~0.05s | ~15 MB |
| 100 OSDs, 5k PGs | ~1s | ~80 MB |
| 500 OSDs, 25k PGs | ~8s | ~400 MB |

**Benchmark Suite:**
- Quick: 30-60 seconds
- Standard: 5-10 minutes
- Comprehensive: 15-30 minutes

## Dependencies

**Zero external dependencies** - Uses Python standard library only:
- `statistics` for calculations
- `tracemalloc` for memory profiling
- `time` for performance measurement
- `json` for data export
- `copy` for state management

## Documentation

- **Technical Spec**: [docs/technical-specification.md](../../../docs/technical-specification.md)
