# Benchmark Framework Usage Guide

**Version:** v1.1.0  
**Status:** Phase 5 Complete

> **🤖 AI-Generated Project:** This project was designed, implemented, and documented by Claude Sonnet 4.5, an AI assistant by Anthropic.

This guide covers the comprehensive benchmarking framework for the Ceph Primary PG Balancer.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Command Reference](#command-reference)
4. [Benchmark Types](#benchmark-types)
5. [Understanding Results](#understanding-results)
6. [Advanced Usage](#advanced-usage)
7. [Integration with CI/CD](#integration-with-cicd)

---

## Overview

The benchmark framework provides comprehensive testing and validation capabilities:

- **Performance Benchmarks**: Measure runtime and memory usage
- **Quality Benchmarks**: Evaluate optimization effectiveness
- **Scalability Tests**: Validate performance across different scales
- **Stability Tests**: Assess solution determinism
- **Regression Detection**: Compare against baselines

### Key Features

✅ **Zero external dependencies** (Python stdlib only)  
✅ **Multiple output formats** (Terminal, JSON, HTML)  
✅ **Reproducible results** (seeded random generation)  
✅ **Standard test scenarios** (quick, standard, comprehensive suites)  
✅ **Regression detection** (automated comparison)

---

## Quick Start

### Run Quick Benchmark (Smoke Test)

```bash
# Quick smoke test (< 1 minute)
python3 -m ceph_primary_balancer.benchmark_cli quick
```

### Run Standard Benchmark Suite

```bash
# Standard suite (5-10 minutes)
python3 -m ceph_primary_balancer.benchmark_cli run --suite standard
```

### Run With HTML Dashboard

```bash
# Generate HTML dashboard
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite standard \
  --html-output ./results/dashboard.html
```

---

## Command Reference

### `run` - Execute Benchmark Suite

Run benchmark tests across multiple scenarios.

**Syntax:**
```bash
python3 -m ceph_primary_balancer.benchmark_cli run [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--suite {quick\|standard\|comprehensive\|performance\|quality\|all}` | Benchmark suite | `standard` |
| `--target-cv FLOAT` | Target coefficient of variation | `0.10` |
| `--seed INT` | Random seed for reproducibility | `42` |
| `--output-dir PATH` | Output directory | `./benchmark_results` |
| `--json-output PATH` | Save JSON results | None |
| `--html-output PATH` | Save HTML dashboard | None |
| `--save-datasets` | Save generated test datasets | False |
| `--no-scalability` | Skip scalability tests | False |
| `--stability` | Run stability tests (slower) | False |
| `--stability-runs INT` | Number of stability runs | `10` |
| `--detailed` | Show detailed terminal report | False |
| `--quiet` | Minimal output | False |

**Examples:**

```bash
# Quick suite with JSON export
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite quick \
  --json-output results.json

# Comprehensive suite with all outputs
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite comprehensive \
  --json-output results.json \
  --html-output dashboard.html \
  --detailed

# Performance-focused tests
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite performance \
  --no-scalability

# Quality-focused with stability tests
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite quality \
  --stability \
  --stability-runs 20
```

### `compare` - Regression Detection

Compare current performance against a baseline.

**Syntax:**
```bash
python3 -m ceph_primary_balancer.benchmark_cli compare --baseline FILE [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--baseline PATH` | Baseline results JSON (required) | - |
| `--threshold FLOAT` | Regression threshold (0.10 = 10%) | `0.10` |
| `--seed INT` | Random seed | `42` |
| `--output PATH` | Save comparison results | None |

**Examples:**

```bash
# Compare with baseline
python3 -m ceph_primary_balancer.benchmark_cli compare \
  --baseline baseline_v1.0.0.json

# Stricter threshold (5% regression)
python3 -m ceph_primary_balancer.benchmark_cli compare \
  --baseline baseline_v1.0.0.json \
  --threshold 0.05 \
  --output comparison_results.json
```

**Exit Codes:**
- `0`: No regressions detected
- `1`: Regressions detected or error

### `generate-dataset` - Create Test Data

Generate synthetic cluster datasets for testing.

**Syntax:**
```bash
python3 -m ceph_primary_balancer.benchmark_cli generate-dataset [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--osds INT` | Number of OSDs | `100` |
| `--pgs INT` | Number of PGs | `5000` |
| `--imbalance FLOAT` | Imbalance CV | `0.30` |
| `--pattern {random\|concentrated\|gradual\|bimodal\|worst_case\|balanced}` | Imbalance pattern | `random` |
| `--seed INT` | Random seed | `42` |
| `--output PATH` | Output file | `./test_dataset.json` |

**Examples:**

```bash
# Generate small dataset
python3 -m ceph_primary_balancer.benchmark_cli generate-dataset \
  --osds 50 \
  --pgs 1000 \
  --output small_dataset.json

# Generate worst-case scenario
python3 -m ceph_primary_balancer.benchmark_cli generate-dataset \
  --osds 100 \
  --pgs 5000 \
  --pattern worst_case \
  --output worst_case.json

# Generate large balanced dataset
python3 -m ceph_primary_balancer.benchmark_cli generate-dataset \
  --osds 500 \
  --pgs 50000 \
  --pattern balanced \
  --imbalance 0.05 \
  --output large_balanced.json
```

### `quick` - Smoke Test

Run a quick smoke test benchmark.

**Syntax:**
```bash
python3 -m ceph_primary_balancer.benchmark_cli quick [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--osds INT` | Number of OSDs | `100` |
| `--pgs INT` | Number of PGs | `5000` |
| `--imbalance FLOAT` | Imbalance CV | `0.30` |

**Example:**
```bash
python3 -m ceph_primary_balancer.benchmark_cli quick --osds 50 --pgs 1000
```

---

## Benchmark Types

### Performance Benchmarks

Measure runtime and memory consumption.

**Scenarios:**
- `tiny_smoke`: 10 OSDs, 100 PGs (quick validation)
- `small_quick`: 50 OSDs, 500 PGs (fast feedback)
- `medium_standard`: 100 OSDs, 10k PGs (standard benchmark)
- `large_production`: 500 OSDs, 50k PGs (production scale)

**Metrics Collected:**
- Total execution time
- Optimization algorithm time
- Memory usage (peak, delta, per-PG, per-OSD)
- Throughput (swaps/sec, iterations/sec)

### Quality Benchmarks

Evaluate optimization effectiveness.

**Scenarios:**
- `replicated_3_moderate`: Replicated pool, moderate imbalance (CV 25%)
- `replicated_3_severe`: Replicated pool, severe imbalance (CV 40%)
- `ec_8_3_severe`: Erasure-coded 8+3 pool, concentrated imbalance
- `multi_pool_complex`: Multiple pools with varied configurations
- `gradual_imbalance`: Linear gradient pattern
- `bimodal_imbalance`: Two-group distribution

**Metrics Collected:**
- OSD/Host/Pool-level CV improvements
- Balance quality score (0-100)
- Fairness index (Jain's index)
- Convergence rate and pattern
- Number of swaps required

### Scalability Benchmarks

Test performance across different scales.

**Default Scales:**
- Scale 1: 10 OSDs, 100 PGs (tiny)
- Scale 2: 50 OSDs, 1k PGs (small)
- Scale 3: 100 OSDs, 5k PGs (medium)
- Scale 4: 250 OSDs, 12.5k PGs (large)
- Scale 5: 500 OSDs, 25k PGs (x-large)

**Complexity Analysis:**
Automatically estimates time and memory complexity (O(n), O(n log n), O(n²), etc.)

### Stability Benchmarks

Assess solution determinism across multiple runs.

**Metrics:**
- Mean CV improvement across runs
- Standard deviation of improvements
- Mean swap count
- Determinism score (0-100)

**Interpretation:**
- **95-100**: Excellent (highly deterministic)
- **80-95**: Good (mostly deterministic)
- **60-80**: Fair (moderate variability)
- **<60**: Poor (high variability)

---

## Understanding Results

### Terminal Output

```
======================================================================
BENCHMARK RESULTS SUMMARY
======================================================================

📊 PERFORMANCE BENCHMARKS
----------------------------------------------------------------------
  small_quick:
    Time:   1.234s
    Memory: 45.2 MB
    Swaps:  78 (63.2/s)

✨ QUALITY BENCHMARKS
----------------------------------------------------------------------
  replicated_3_moderate:
    OSD CV:  25.0% → 8.5% (+66.0%)
    Score:   95.2/100
    Swaps:   142

📈 SCALABILITY BENCHMARKS
----------------------------------------------------------------------
  Scale    OSDs     PGs        Time (s)    Memory (MB)
  --------------------------------------------------------------
  1        10       100        0.045       12.3
  2        50       1000       0.234       34.5
  3        100      5000       1.123       78.9
  4        250      12500      3.456       189.2
  5        500      25000      8.234       412.5
```

### JSON Output Structure

```json
{
  "performance": {
    "scenario_name": {
      "perf": {
        "execution_time_total": 1.234,
        "execution_time_optimize": 1.123,
        "swaps_applied": 78,
        "swaps_per_second": 63.2
      },
      "mem": {
        "peak_memory_mb": 45.2,
        "memory_per_pg_kb": 9.04
      }
    }
  },
  "quality": {
    "scenario_name": {
      "quality": {
        "osd_cv_before": 0.25,
        "osd_cv_after": 0.085,
        "osd_cv_improvement_pct": 66.0,
        "balance_score": 95.2
      },
      "convergence": {
        "initial_cv": 0.25,
        "final_cv": 0.085,
        "convergence_pattern": "linear"
      }
    }
  },
  "scalability": [ ... ],
  "stability": { ... },
  "metadata": { ... }
}
```

### HTML Dashboard

The HTML dashboard provides:
- Interactive tables with performance metrics
- Quality improvement summaries
- Scalability charts (via simple tables)
- Color-coded results (green=good, yellow=warn, red=bad)

Open `dashboard.html` in any web browser.

---

## Advanced Usage

### Custom Test Scenarios

Create custom scenarios programmatically:

```python
from ceph_primary_balancer.benchmark import (
    generate_synthetic_cluster,
    profile_optimization,
    analyze_balance_quality
)

# Generate custom cluster
state = generate_synthetic_cluster(
    num_osds=200,
    num_hosts=20,
    num_pools=8,
    pgs_per_pool=2048,
    imbalance_cv=0.35,
    imbalance_pattern='concentrated',
    seed=123
)

# Profile optimization
perf, mem = profile_optimization(state, target_cv=0.08)

print(f"Time: {perf.execution_time_total:.3f}s")
print(f"Memory: {mem.peak_memory_mb:.1f} MB")
```

### Regression Testing Workflow

```bash
# 1. Establish baseline (v1.0.0)
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite standard \
  --seed 42 \
  --json-output baseline_v1.0.0.json

# 2. After code changes, run comparison
python3 -m ceph_primary_balancer.benchmark_cli compare \
  --baseline baseline_v1.0.0.json \
  --threshold 0.10 \
  --output regression_report.json

# 3. Check exit code
echo $?  # 0 = pass, 1 = regressions detected
```

### Batch Testing Multiple Configurations

```bash
#!/bin/bash
# Test multiple weight configurations

for weights in "1.0,0.0,0.0" "0.7,0.3,0.0" "0.5,0.3,0.2"; do
    echo "Testing weights: $weights"
    python3 -m ceph_primary_balancer.benchmark_cli run \
        --suite quality \
        --json-output "results_${weights}.json"
done
```

### Analyzing Imbalance Patterns

Test how optimizer handles different patterns:

```bash
# Test each pattern
for pattern in random concentrated gradual bimodal worst_case; do
    python3 -m ceph_primary_balancer.benchmark_cli generate-dataset \
        --pattern $pattern \
        --output "dataset_${pattern}.json"
done
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Performance Regression Tests

on: [push, pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      
      - name: Run benchmarks
        run: |
          python3 -m ceph_primary_balancer.benchmark_cli run \
            --suite quick \
            --json-output results.json
      
      - name: Compare with baseline
        run: |
          python3 -m ceph_primary_balancer.benchmark_cli compare \
            --baseline baseline.json \
            --threshold 0.15 \
            --output regression.json
      
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: benchmark-results
          path: |
            results.json
            regression.json
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    stages {
        stage('Benchmark') {
            steps {
                sh '''
                    python3 -m ceph_primary_balancer.benchmark_cli run \
                      --suite standard \
                      --json-output results.json \
                      --html-output dashboard.html
                '''
            }
        }
        stage('Regression Check') {
            steps {
                sh '''
                    python3 -m ceph_primary_balancer.benchmark_cli compare \
                      --baseline baseline.json \
                      --threshold 0.10 || exit 1
                '''
            }
        }
    }
    post {
        always {
            publishHTML([
                reportDir: '.',
                reportFiles: 'dashboard.html',
                reportName: 'Benchmark Dashboard'
            ])
        }
    }
}
```

---

## Performance Expectations

### Typical Runtimes

| Benchmark Suite | Scenarios | Typical Duration | Notes |
|----------------|-----------|------------------|-------|
| Quick | 1 quality scenario | **< 5 seconds** | No scalability tests |
| Standard | 5 scenarios | 10-20 minutes* | Includes medium-scale tests |
| Comprehensive | 10+ scenarios | 30-60 minutes* | All scenarios |
| With Scalability | +5 scales | +15-30 minutes | Tests up to 500 OSDs |
| With Stability | +10 runs | +20-40 minutes | Multiple runs per scenario |

\* *Note: Standard and comprehensive suites include large scenarios (10k+ PGs) which significantly increase runtime. Consider using custom configurations for faster testing.*

### Memory Requirements

| Cluster Scale | Peak Memory | Per-PG Memory |
|--------------|-------------|---------------|
| 10 OSDs, 100 PGs | 0.1 MB | 0.86 KB |
| 50 OSDs, 1k PGs | 0.8 MB | 0.84 KB |
| 100 OSDs, 5k PGs | ~4 MB | ~0.8 KB |
| 500 OSDs, 25k PGs | ~20 MB | ~0.8 KB |

---

## Troubleshooting

### Benchmarks Running Too Slow

**Solution 1**: Use quick suite
```bash
python3 -m ceph_primary_balancer.benchmark_cli run --suite quick
```

**Solution 2**: Skip scalability tests
```bash
python3 -m ceph_primary_balancer.benchmark_cli run --no-scalability
```

**Solution 3**: Run specific benchmark type
```bash
python3 -m ceph_primary_balancer.benchmark_cli run --suite performance
```

### Memory Errors on Large Datasets

**Solution**: Test incrementally
```bash
# Start small
python3 -m ceph_primary_balancer.benchmark_cli quick --osds 50

# Gradually increase
python3 -m ceph_primary_balancer.benchmark_cli quick --osds 100
python3 -m ceph_primary_balancer.benchmark_cli quick --osds 250
```

### Inconsistent Results

**Cause**: Different random seeds

**Solution**: Always use same seed
```bash
python3 -m ceph_primary_balancer.benchmark_cli run --seed 42
```

---

## References

- **Main Documentation**: [README.md](../README.md)
- **Usage Guide**: [USAGE.md](USAGE.md)
- **Technical Specification**: [technical-specification.md](technical-specification.md)
- **Phase 5 Plan**: [plans/phase5-benchmark-framework.md](../plans/phase5-benchmark-framework.md)

---

**Version:** v1.1.0  
**Last Updated:** 2026-02-04  
**Status:** Phase 5 Complete
