# Phase 5: Benchmark Framework Implementation Plan
## Ceph Primary PG Balancer v1.1.0

**Date:** 2026-02-03  
**Prerequisites:** Phase 4 Complete (v1.0.0)  
**Target Version:** 1.1.0  
**Status:** Planning Complete

---

## Executive Summary

Phase 5 introduces a comprehensive benchmarking framework to:
1. Measure and track optimizer performance
2. Evaluate optimization quality across scenarios
3. Enable future algorithm comparison
4. Generate realistic test datasets for validation

This framework is essential for:
- Performance regression detection
- Algorithm comparison and selection
- Scalability validation
- Quality assurance across different cluster configurations

---

## Architecture Overview

### Module Structure

```
src/ceph_primary_balancer/benchmark/
├── __init__.py              # Package initialization
├── generator.py             # Test data generation (~400 lines)
├── profiler.py              # Performance profiling (~300 lines)
├── quality_analyzer.py      # Optimization quality analysis (~350 lines)
├── runner.py                # Benchmark orchestration (~300 lines)
├── reporter.py              # Results reporting (~400 lines)
└── scenarios.py             # Standard test scenarios (~200 lines)

tests/benchmark/
├── test_generator.py        # Generator tests (~150 lines)
├── test_profiler.py         # Profiler tests (~100 lines)
├── test_quality_analyzer.py # Quality analyzer tests (~100 lines)
└── test_integration.py      # End-to-end benchmark tests (~150 lines)

config-examples/
└── benchmark-config.json    # Benchmark configuration template
```

### Total Effort Estimate

- **Production Code:** ~2,000 lines
- **Test Code:** ~500 lines
- **Documentation:** ~300 lines
- **Total:** ~2,800 lines

---

## Component Details

### 1. Test Data Generator (`generator.py`)

**Purpose:** Generate realistic synthetic cluster states for benchmarking

**Key Functions:**

```python
def generate_synthetic_cluster(
    num_osds: int = 100,
    num_hosts: int = 10,
    num_pools: int = 5,
    pgs_per_pool: int = 512,
    replication_factor: int = 3,
    imbalance_cv: float = 0.30,
    imbalance_pattern: str = 'random'
) -> ClusterState:
    """Generate realistic synthetic cluster with specified imbalance."""

def generate_ec_pool(
    k: int = 8,           # Data chunks
    m: int = 3,           # Parity chunks
    num_pgs: int = 2048,
    num_osds: int = 100,
    num_hosts: int = 10,
    imbalance_type: str = 'random'
) -> ClusterState:
    """Generate erasure-coded pool scenario."""

def generate_imbalance_pattern(
    num_osds: int,
    total_pgs: int,
    pattern_type: str
) -> List[int]:
    """Generate specific imbalance patterns.
    
    Pattern types:
    - 'random': Random distribution (natural cluster drift)
    - 'concentrated': Few OSDs severely overloaded
    - 'gradual': Linear gradient from low to high
    - 'bimodal': Two groups (high/low)
    - 'worst_case': All PGs on single OSD
    """

def generate_multi_pool_scenario(
    num_pools: int = 5,
    pools_config: List[dict] = None
) -> ClusterState:
    """Generate complex multi-pool scenario."""

def save_test_dataset(
    state: ClusterState,
    filepath: str,
    metadata: dict = None
):
    """Save generated cluster state as test dataset."""

def load_test_dataset(filepath: str) -> ClusterState:
    """Load previously generated test dataset."""
```

**Standard Test Datasets:**

```python
# Small scale datasets for quick testing
DATASET_SMALL_BALANCED = {
    'num_osds': 10,
    'num_pgs': 100,
    'imbalance_cv': 0.05
}

DATASET_SMALL_IMBALANCED = {
    'num_osds': 10,
    'num_pgs': 100,
    'imbalance_cv': 0.35
}

# Medium scale for standard benchmarks
DATASET_MEDIUM_REPLICATED = {
    'num_osds': 100,
    'num_pools': 3,
    'pgs_per_pool': 1024,
    'replication_factor': 3,
    'imbalance_cv': 0.25
}

DATASET_MEDIUM_EC = {
    'num_osds': 100,
    'k': 8,
    'm': 3,
    'num_pgs': 2048,
    'imbalance_type': 'concentrated'
}

# Large scale for scalability testing
DATASET_LARGE_MULTI_POOL = {
    'num_osds': 500,
    'num_hosts': 50,
    'num_pools': 10,
    'pgs_per_pool': 5000,
    'imbalance_cv': 0.30
}

# Extra-large for stress testing
DATASET_XLARGE_STRESS = {
    'num_osds': 1000,
    'num_hosts': 100,
    'num_pools': 20,
    'pgs_per_pool': 5000,
    'imbalance_cv': 0.35
}
```

---

### 2. Performance Profiler (`profiler.py`)

**Purpose:** Measure runtime performance and resource usage

**Metrics Classes:**

```python
@dataclass
class PerformanceMetrics:
    """Runtime performance metrics."""
    execution_time_total: float         # Total execution time (seconds)
    execution_time_optimize: float      # Optimization algorithm time
    execution_time_scoring: float       # Scoring calculation time
    execution_time_collection: float    # Data collection time
    
    iterations_count: int               # Number of optimization iterations
    swaps_evaluated: int                # Total swaps evaluated
    swaps_applied: int                  # Swaps actually applied
    
    swaps_per_second: float            # Throughput metric
    iterations_per_second: float        # Iteration rate
    time_per_iteration: float          # Average iteration time

@dataclass
class MemoryMetrics:
    """Memory usage metrics."""
    peak_memory_mb: float              # Peak memory usage
    memory_per_pg_kb: float            # Memory efficiency per PG
    memory_per_osd_kb: float           # Memory per OSD
    state_size_mb: float               # ClusterState object size
    
    memory_growth_rate: float          # MB/iteration
    gc_collections: int                # Garbage collection count

@dataclass
class ScalabilityMetrics:
    """Scalability test results."""
    scale_factor: int                  # Scale multiplier
    num_osds: int
    num_pgs: int
    execution_time: float
    memory_usage: float
    
    # Derived metrics
    time_complexity_fit: str           # O(n), O(n²), etc.
    memory_complexity_fit: str
```

**Key Functions:**

```python
def profile_optimization(
    state: ClusterState,
    target_cv: float = 0.10,
    scorer: Scorer = None
) -> Tuple[PerformanceMetrics, MemoryMetrics]:
    """Profile complete optimization run with detailed metrics."""

def benchmark_scalability(
    scales: List[Tuple[int, int]] = None
) -> List[ScalabilityMetrics]:
    """Test performance across different scales."""

def profile_hot_spots() -> dict:
    """Identify performance bottlenecks using cProfile."""

def track_memory_usage(func):
    """Decorator to track memory usage of function."""
```

---

### 3. Quality Analyzer (`quality_analyzer.py`)

**Purpose:** Evaluate optimization quality and solution characteristics

**Metrics Classes:**

```python
@dataclass
class BalanceQualityMetrics:
    """Balance quality across all dimensions."""
    # OSD-level metrics
    osd_cv_before: float
    osd_cv_after: float
    osd_cv_improvement_pct: float
    osd_variance_reduction_pct: float
    osd_range_reduction: int
    
    # Host-level metrics
    host_cv_before: float
    host_cv_after: float
    host_cv_improvement_pct: float
    
    # Pool-level metrics
    avg_pool_cv_before: float
    avg_pool_cv_after: float
    pool_cv_improvement_pct: float
    
    # Composite metrics
    composite_improvement: float
    fairness_index: float              # Jain's fairness index
    balance_score: float               # 0-100 overall score

@dataclass
class ConvergenceMetrics:
    """Convergence behavior analysis."""
    iterations_to_target: int
    iterations_total: int
    convergence_rate: float            # CV reduction per iteration
    diminishing_returns_point: int     # When improvement slows
    
    # Trajectories
    score_trajectory: List[float]      # Score at each iteration
    cv_trajectory: List[float]         # CV at each iteration
    improvement_trajectory: List[float] # Improvement per iteration
    
    # Convergence characteristics
    convergence_pattern: str           # linear, exponential, plateau
    convergence_efficiency: float      # Improvement per iteration

@dataclass
class StabilityMetrics:
    """Solution stability and consistency."""
    runs_count: int
    
    # Variability across runs
    cv_improvement_mean: float
    cv_improvement_std: float
    swaps_count_mean: float
    swaps_count_std: float
    
    # Solution similarity
    solution_similarity_pct: float     # % overlap between solutions
    determinism_score: float           # 0-100, higher = more deterministic

@dataclass
class MultiDimensionalBalance:
    """Balance across all optimization dimensions."""
    osd_balance_score: float           # 0-100
    host_balance_score: float          # 0-100
    pool_balance_score: float          # 0-100
    
    composite_score: float             # Weighted average
    bottleneck_dimension: str          # Which dimension limits improvement
    
    weight_sensitivity: dict           # How sensitive to weight changes
```

**Key Functions:**

```python
def analyze_balance_quality(
    original_state: ClusterState,
    optimized_state: ClusterState,
    swaps: List[SwapProposal]
) -> BalanceQualityMetrics:
    """Comprehensive balance quality analysis."""

def analyze_convergence(
    state: ClusterState,
    target_cv: float,
    scorer: Scorer
) -> ConvergenceMetrics:
    """Analyze convergence behavior with detailed trajectory."""

def analyze_stability(
    state: ClusterState,
    num_runs: int = 10
) -> StabilityMetrics:
    """Test solution stability across multiple runs."""

def analyze_multi_dimensional_balance(
    state: ClusterState,
    weight_combinations: List[Tuple[float, float, float]] = None
) -> MultiDimensionalBalance:
    """Analyze balance across dimensions with different weights."""

def calculate_jains_fairness_index(counts: List[int]) -> float:
    """Calculate Jain's fairness index: (Σx)² / (n * Σx²)"""

def score_balance_quality(
    cv: float,
    target_cv: float = 0.10
) -> float:
    """Convert CV to 0-100 quality score."""
```

---

### 4. Benchmark Runner (`runner.py`)

**Purpose:** Orchestrate benchmark execution and manage test scenarios

**Main Classes:**

```python
class BenchmarkSuite:
    """Main benchmark orchestration."""
    
    def __init__(self, config: dict = None):
        self.config = config or self._default_config()
        self.scenarios = self._load_scenarios()
    
    def run_all_benchmarks(self) -> BenchmarkResults:
        """Run complete benchmark suite."""
        return {
            'performance': self.run_performance_benchmarks(),
            'quality': self.run_quality_benchmarks(),
            'scalability': self.run_scalability_benchmarks(),
            'stability': self.run_stability_benchmarks()
        }
    
    def run_performance_benchmarks(self) -> dict:
        """Run performance benchmarks on standard scenarios."""
        results = {}
        for scenario in self.scenarios['performance']:
            state = self._generate_scenario(scenario)
            metrics = profile_optimization(state)
            results[scenario['name']] = metrics
        return results
    
    def run_quality_benchmarks(self) -> dict:
        """Run quality benchmarks across different cluster types."""
        results = {}
        for scenario in self.scenarios['quality']:
            original_state = self._generate_scenario(scenario)
            optimized_state = copy.deepcopy(original_state)
            swaps = optimize_primaries(optimized_state)
            
            quality = analyze_balance_quality(original_state, optimized_state, swaps)
            convergence = analyze_convergence(original_state)
            
            results[scenario['name']] = {
                'quality': quality,
                'convergence': convergence
            }
        return results
    
    def run_scalability_benchmarks(self) -> dict:
        """Test performance across different scales."""
        return benchmark_scalability()
    
    def run_stability_benchmarks(self) -> dict:
        """Test solution stability and determinism."""
        results = {}
        for scenario in self.scenarios['stability']:
            state = self._generate_scenario(scenario)
            stability = analyze_stability(state, num_runs=10)
            results[scenario['name']] = stability
        return results
    
    def run_regression_tests(
        self,
        baseline_path: str
    ) -> RegressionReport:
        """Compare current results against baseline."""
        baseline = self._load_baseline(baseline_path)
        current = self.run_all_benchmarks()
        return self._compare_results(baseline, current)
    
    def benchmark_optimizer_variants(
        self,
        optimizers: List[Tuple[str, callable]]
    ) -> ComparisonReport:
        """Compare different optimization algorithms."""
        results = {}
        for name, optimizer_func in optimizers:
            results[name] = self._benchmark_optimizer(optimizer_func)
        return self._generate_comparison_report(results)

class RegressionDetector:
    """Detect performance regressions."""
    
    def detect_regressions(
        self,
        baseline: BenchmarkResults,
        current: BenchmarkResults,
        threshold: float = 0.10  # 10% regression threshold
    ) -> List[Regression]:
        """Detect performance regressions."""

class ComparisonAnalyzer:
    """Compare different optimization algorithms."""
    
    def compare_algorithms(
        self,
        results: Dict[str, BenchmarkResults]
    ) -> ComparisonReport:
        """Generate comprehensive comparison."""
```

---

### 5. Results Reporter (`reporter.py`)

**Purpose:** Generate reports and visualizations of benchmark results

**Report Types:**

```python
class TerminalReporter:
    """Generate terminal-based reports."""
    
    def generate_summary(self, results: BenchmarkResults) -> str:
        """Generate concise terminal summary."""
    
    def generate_detailed_report(self, results: BenchmarkResults) -> str:
        """Generate detailed terminal report with tables."""

class JSONReporter:
    """Export results as structured JSON."""
    
    def export_results(
        self,
        results: BenchmarkResults,
        filepath: str
    ):
        """Export complete results as JSON."""
    
    def export_comparison(
        self,
        comparison: ComparisonReport,
        filepath: str
    ):
        """Export comparison as JSON."""

class HTMLReporter:
    """Generate interactive HTML dashboard."""
    
    def generate_dashboard(
        self,
        results: BenchmarkResults,
        output_dir: str
    ):
        """Generate interactive HTML dashboard with charts."""
    
    def generate_comparison_dashboard(
        self,
        comparison: ComparisonReport,
        output_dir: str
    ):
        """Generate comparison dashboard."""

class ChartGenerator:
    """Generate performance and quality charts."""
    
    def plot_scalability(self, metrics: List[ScalabilityMetrics]) -> str:
        """Generate scalability chart (SVG or Chart.js)."""
    
    def plot_convergence(self, convergence: ConvergenceMetrics) -> str:
        """Generate convergence trajectory chart."""
    
    def plot_comparison(self, comparison: ComparisonReport) -> str:
        """Generate algorithm comparison charts."""
```

---

## Standard Test Scenarios

### Performance Scenarios

```python
PERFORMANCE_SCENARIOS = [
    {
        'name': 'small_quick',
        'description': 'Quick smoke test',
        'params': {'num_osds': 10, 'num_pgs': 100}
    },
    {
        'name': 'medium_standard',
        'description': 'Standard benchmark',
        'params': {'num_osds': 100, 'num_pgs': 10000}
    },
    {
        'name': 'large_production',
        'description': 'Production-like scale',
        'params': {'num_osds': 500, 'num_pgs': 50000}
    }
]
```

### Quality Scenarios

```python
QUALITY_SCENARIOS = [
    {
        'name': 'replicated_3_moderate',
        'description': 'Replicated pool, moderate imbalance',
        'params': {
            'replication_factor': 3,
            'imbalance_cv': 0.25
        }
    },
    {
        'name': 'ec_8_3_severe',
        'description': 'EC 8+3 pool, severe imbalance',
        'params': {
            'k': 8,
            'm': 3,
            'imbalance_type': 'concentrated'
        }
    },
    {
        'name': 'multi_pool_complex',
        'description': 'Multiple pools, varied imbalance',
        'params': {
            'num_pools': 5,
            'imbalance_cv': 0.30
        }
    }
]
```

---

## CLI Integration

### New Benchmark Commands

```bash
# Run full benchmark suite
ceph-primary-balancer-benchmark run --suite all

# Run specific benchmark category
ceph-primary-balancer-benchmark run --suite performance
ceph-primary-balancer-benchmark run --suite quality
ceph-primary-balancer-benchmark run --suite scalability

# Run with custom configuration
ceph-primary-balancer-benchmark run --config benchmark-config.json

# Compare with baseline
ceph-primary-balancer-benchmark compare --baseline results/baseline.json

# Generate test dataset
ceph-primary-balancer-benchmark generate-dataset \
    --osds 100 \
    --pgs 10000 \
    --imbalance 0.30 \
    --output dataset.json

# Run on custom dataset
ceph-primary-balancer-benchmark run \
    --dataset dataset.json \
    --output results.json
```

### Configuration File Format

```json
{
  "benchmark": {
    "suites": ["performance", "quality", "scalability"],
    "iterations": 3,
    "output_dir": "./benchmark_results",
    "generate_html": true,
    "save_datasets": true
  },
  "performance": {
    "scales": [
      {"osds": 10, "pgs": 100},
      {"osds": 100, "pgs": 10000},
      {"osds": 500, "pgs": 50000}
    ],
    "profile_memory": true,
    "profile_cpu": true
  },
  "quality": {
    "scenarios": [
      "replicated_3_moderate",
      "ec_8_3_severe",
      "multi_pool_complex"
    ],
    "stability_runs": 10
  },
  "regression": {
    "baseline": "./baseline.json",
    "threshold": 0.10
  }
}
```

---

## Implementation Sprints

### Sprint 5A: Foundation (Week 5)

1. **Task 5A.1:** Create benchmark module structure
2. **Task 5A.2:** Implement test data generator
3. **Task 5A.3:** Implement performance profiler
4. **Task 5A.4:** Create basic unit tests

**Deliverables:**
- Working test data generator
- Performance profiling capability
- Standard test datasets

---

### Sprint 5B: Quality & Analysis (Week 6)

1. **Task 5B.1:** Implement quality analyzer
2. **Task 5B.2:** Implement benchmark runner
3. **Task 5B.3:** Create standard test scenarios
4. **Task 5B.4:** Add quality analysis tests

**Deliverables:**
- Complete quality analysis
- Benchmark orchestration
- Standard scenario library

---

### Sprint 5C: Reporting & CLI (Week 7)

1. **Task 5C.1:** Implement terminal reporter
2. **Task 5C.2:** Implement JSON reporter
3. **Task 5C.3:** Implement HTML dashboard generator
4. **Task 5C.4:** Add CLI commands
5. **Task 5C.5:** Integration testing

**Deliverables:**
- Multi-format reporting
- CLI integration
- Comprehensive tests

---

### Sprint 5D: Documentation & Polish (Week 8)

1. **Task 5D.1:** Write benchmark usage guide
2. **Task 5D.2:** Create example benchmarks
3. **Task 5D.3:** Performance tuning guide
4. **Task 5D.4:** Final testing and release v1.1.0

**Deliverables:**
- Complete documentation
- Example configurations
- v1.1.0 release

---

## Success Criteria

### Functional Requirements

- ✅ Generate synthetic clusters of various scales
- ✅ Generate EC pool scenarios
- ✅ Profile runtime performance accurately
- ✅ Track memory usage
- ✅ Analyze optimization quality
- ✅ Detect performance regressions
- ✅ Compare different algorithms
- ✅ Generate comprehensive reports

### Performance Requirements

- ✅ Benchmark suite completes in <30 minutes for standard scenarios
- ✅ Memory profiling overhead <10%
- ✅ HTML dashboard generates in <5 seconds
- ✅ Support datasets up to 100k PGs

### Quality Requirements

- ✅ Test coverage ≥80% for benchmark module
- ✅ All metrics validated against known values
- ✅ Regression detection accuracy >95%
- ✅ Deterministic results for same inputs

---

## Future Enhancements (v1.2+)

1. **Continuous Benchmarking**
   - GitHub Actions integration
   - Automated baseline updates
   - Performance tracking over time

2. **Advanced Visualizations**
   - 3D balance visualization
   - Interactive cluster explorer
   - Animated optimization replay

3. **Machine Learning Integration**
   - Predict optimal weights
   - Anomaly detection
   - Performance forecasting

4. **Distributed Benchmarking**
   - Parallel benchmark execution
   - Multi-node testing
   - Cloud integration

---

## Dependencies

**Zero New External Dependencies** (maintaining Phase 4 commitment)

Using Python stdlib:
- `cProfile` for profiling
- `tracemalloc` for memory tracking
- `statistics` for calculations
- `json` for data export
- `html` for dashboard generation

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Benchmark suite too slow | Implement quick/full modes, parallel execution |
| Memory overhead | Stream large datasets, implement cleanup |
| Complex HTML generation | Use simple template, progressive enhancement |
| Test data unrealistic | Validate against real cluster patterns |
| Regression false positives | Tune thresholds, require confirmation |

---

## Conclusion

Phase 5 provides essential infrastructure for:
- **Performance validation** - Ensure optimizations don't regress
- **Algorithm research** - Compare different optimization strategies
- **Quality assurance** - Validate balance improvements
- **Future development** - Foundation for advanced features

This framework enables confident evolution of the optimizer while maintaining quality and performance standards.
