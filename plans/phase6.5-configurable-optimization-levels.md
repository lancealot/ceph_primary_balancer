# Phase 6.5: Configurable Optimization Levels Implementation Plan
## Ceph Primary PG Balancer v1.2.5

**Date:** 2026-02-05  
**Prerequisites:** Phase 6 Complete (v1.2.0 - Advanced Algorithms)  
**Target Version:** 1.2.5  
**Status:** Planning  

---

## Executive Summary

Phase 6.5 enhances the optimizer with **toggleable optimization dimensions**, allowing users to selectively enable/disable OSD, HOST, and POOL level optimizations. This provides fine-grained control over the optimization strategy, enabling performance analysis, resource efficiency, and targeted problem-solving.

### Key Objectives

1. **Dimension Toggle System** - Enable/disable OSD, HOST, POOL optimization independently
2. **Performance Isolation** - Measure exact runtime/complexity cost of each dimension
3. **Strategy Comparison** - Benchmark all dimension combinations (OSD, HOST+OSD, etc.)
4. **Incremental Optimization** - Support staged rollout workflows
5. **Enhanced Benchmarking** - Compare strategies across different cluster types

### Why This Enhancement?

Current system uses **weights** to balance dimensions (e.g., 50% OSD, 30% HOST, 20% POOL), but users cannot **completely disable** a dimension to:
- Measure its performance impact
- Skip unnecessary computations
- Isolate troubleshooting
- Match optimization to cluster topology

| Current Approach | Enhanced Approach |
|-----------------|-------------------|
| Weight = 0.0 still computes variance | Disabled = skip computation entirely |
| Cannot measure dimension cost | Can isolate and benchmark each dimension |
| All dimensions always active | Mix-and-match based on needs |
| Generic "one size fits all" | Tailored to cluster topology |

---

## Motivation & Benefits

### 1. Performance Analysis & Time Complexity

**Problem:** Users don't know how much each dimension costs

**Solution:** Enable performance isolation

```bash
# Benchmark OSD-only (baseline)
python3 -m ceph_primary_balancer.benchmark_cli run \
    --optimization-levels osd \
    --output osd_only.json

# Benchmark OSD+HOST
python3 -m ceph_primary_balancer.benchmark_cli run \
    --optimization-levels osd,host \
    --output osd_host.json

# Benchmark Full 3D
python3 -m ceph_primary_balancer.benchmark_cli run \
    --optimization-levels osd,host,pool \
    --output full_3d.json

# Compare results
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --inputs osd_only.json,osd_host.json,full_3d.json
```

**Expected insights:**
```
Strategy      | Runtime | Iterations | Final CV | Swaps | Cost/Benefit
--------------|---------|------------|----------|-------|-------------
OSD-only      | 2.3s    | 45         | 0.08     | 38    | Baseline
OSD+HOST      | 5.1s    | 89         | 0.07     | 75    | 2.2× slower, 12% better
OSD+HOST+POOL | 8.7s    | 142        | 0.06     | 118   | 3.8× slower, 25% better
```

### 2. Algorithmic Trade-off Visualization

**Time Complexity by Strategy:**

| Strategy | Theoretical | Actual | Best For |
|----------|-------------|--------|----------|
| OSD-only | O(n) | Fast | Small clusters, quick fixes |
| OSD+HOST | O(n×h) | Medium | Multi-host imbalance |
| OSD+POOL | O(n×p) | Medium | Multi-pool workloads |
| HOST+POOL | O(h×p) | Medium | Network-focused |
| Full 3D | O(n×h×p) | Slowest | Large multi-pool clusters |

Where: n=OSDs, h=hosts, p=pools

### 3. Incremental/Staged Optimization

**Use case:** Production-safe progressive rebalancing

```bash
# Stage 1: Quick OSD balance (2 minutes, low risk)
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd \
    --target-cv 0.15 \
    --output stage1.sh

# Apply and monitor...

# Stage 2: Add host balancing (5 minutes, medium risk)
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host \
    --target-cv 0.10 \
    --output stage2.sh

# Stage 3: Fine-tune with pool awareness (optional)
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host,pool \
    --target-cv 0.05 \
    --output stage3.sh
```

**Benefits:**
- Lower risk per stage
- Can stop at "good enough"
- Easier troubleshooting if issues arise
- Faster initial improvement

### 4. Topology-Specific Optimization

**Single-pool cluster:**
```bash
# No pool variance to optimize, skip that dimension
--optimization-levels osd,host
```

**Single-host lab environment:**
```bash
# No host topology, OSD-only makes sense
--optimization-levels osd
```

**Network-constrained cluster:**
```bash
# Prioritize network balance
--optimization-levels host,pool
--weights host=0.6,pool=0.4
```

**Erasure-coded pools only:**
```bash
# EC pools benefit from pool-level balance
--optimization-levels pool
```

### 5. Troubleshooting & Root Cause Analysis

**Scenario:** Optimization not converging well

```bash
# Test if pool constraints are blocking convergence
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host \
    --dry-run

# Compare to full 3D
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host,pool \
    --dry-run
```

If OSD+HOST achieves better CV than Full 3D:
→ **Pool constraints are limiting optimization**
→ Consider relaxing pool isolation or adjusting weights

### 6. Resource Efficiency

**Memory savings:**
- Pool tracking disabled = no per-pool variance calculation
- Host tracking disabled = no host aggregation overhead

**CPU savings:**
- Each disabled dimension eliminates variance calculation per swap
- Critical for 1000+ OSD clusters

**Example:** 500 OSDs, 50 hosts, 10 pools, 50,000 PGs
- Full 3D: ~15 MB memory, 45s runtime
- OSD+HOST: ~8 MB memory, 25s runtime (44% faster)
- OSD-only: ~3 MB memory, 12s runtime (73% faster)

### 7. Benchmark Quality Metrics

Enhanced benchmark reports will show:

```markdown
## Strategy Comparison Report

### OSD-Only Strategy
- Runtime: 2.3s
- Final OSD CV: 0.08
- Final HOST CV: 0.22 (not optimized)
- Final POOL CV: 0.31 (not optimized)
- Swaps: 38
- Score: FAST, simple, predictable

### OSD+HOST Strategy
- Runtime: 5.1s (2.2× slower)
- Final OSD CV: 0.09
- Final HOST CV: 0.07 (excellent!)
- Final POOL CV: 0.28 (not optimized)
- Swaps: 75
- Score: BALANCED, good for multi-host

### Full 3D Strategy
- Runtime: 8.7s (3.8× slower)
- Final OSD CV: 0.09
- Final HOST CV: 0.08
- Final POOL CV: 0.06 (excellent!)
- Swaps: 118
- Score: COMPREHENSIVE, best overall

### Recommendation
For this cluster: OSD+HOST provides best value (2.2× time for 12% improvement)
```

---

## Architecture Overview

### Configuration Model

#### Current (v1.2.0):
```json
{
  "scoring": {
    "weights": {
      "osd": 0.5,
      "host": 0.3,
      "pool": 0.2
    }
  }
}
```

**Limitation:** All dimensions always active, just weighted

#### Enhanced (v1.2.5):
```json
{
  "optimization": {
    "enabled_levels": ["osd", "host", "pool"],
    "target_cv": 0.10
  },
  "scoring": {
    "weights": {
      "osd": 0.5,
      "host": 0.3,
      "pool": 0.2
    }
  }
}
```

**Improvement:** Disabled dimensions skip computation entirely

### Module Changes

```
src/ceph_primary_balancer/
├── config.py                    # MODIFY: Add enabled_levels support
├── scorer.py                    # MODIFY: Skip disabled dimensions
├── optimizer.py                 # MODIFY: Conditional tracking
├── cli.py                       # MODIFY: Add --optimization-levels flag
└── benchmark/
    ├── runner.py                # MODIFY: Support strategy comparison
    ├── scenarios.py             # ADD: Strategy comparison scenarios
    └── reporter.py              # MODIFY: Strategy comparison reports

tests/
├── test_configurable_levels.py  # NEW: Test dimension toggling
├── test_strategy_benchmarks.py  # NEW: Benchmark integration tests
└── test_optimizer.py            # MODIFY: Add dimension toggle tests

docs/
├── USAGE.md                     # MODIFY: Add optimization-levels docs
├── BENCHMARK-USAGE.md           # MODIFY: Add strategy comparison
└── optimization-strategies.md   # NEW: Strategy selection guide
```

---

## Detailed Design

### 1. Configuration Schema

#### `config.py` Enhancement

```python
def _default_settings(self) -> Dict[str, Any]:
    """Return default configuration values."""
    return {
        'optimization': {
            'target_cv': 0.10,
            'max_changes': None,
            'max_iterations': 10000,
            'enabled_levels': ['osd', 'host', 'pool']  # NEW
        },
        'scoring': {
            'weights': {
                'osd': 0.5,
                'host': 0.3,
                'pool': 0.2
            }
        },
        # ... rest unchanged
    }

def validate_enabled_levels(self) -> None:
    """
    Validate enabled_levels configuration.
    
    Rules:
    - Must be list of strings
    - Valid values: 'osd', 'host', 'pool'
    - At least one level must be enabled
    - Weights for disabled levels are ignored
    """
    levels = self.get('optimization.enabled_levels', ['osd', 'host', 'pool'])
    
    if not isinstance(levels, list):
        raise ConfigError("enabled_levels must be a list")
    
    if not levels:
        raise ConfigError("At least one optimization level must be enabled")
    
    valid_levels = {'osd', 'host', 'pool'}
    for level in levels:
        if level not in valid_levels:
            raise ConfigError(f"Invalid level '{level}'. Valid: {valid_levels}")
    
    # Normalize weights for enabled levels only
    enabled_weights = {
        level: self.get(f'scoring.weights.{level}', 0.33)
        for level in levels
    }
    
    total = sum(enabled_weights.values())
    if total > 0:
        # Normalize to sum to 1.0
        for level in enabled_weights:
            enabled_weights[level] /= total
        
        # Update settings
        self.settings['scoring']['weights'] = enabled_weights
```

### 2. Scorer Enhancement

#### `scorer.py` Modification

```python
class Scorer:
    """
    Multi-dimensional scoring engine with configurable dimensions.
    """
    
    def __init__(
        self,
        w_osd: float = 0.5,
        w_host: float = 0.3,
        w_pool: float = 0.2,
        enabled_levels: Optional[List[str]] = None
    ):
        """
        Initialize scorer with dimension weights and enabled levels.
        
        Args:
            w_osd: Weight for OSD-level variance
            w_host: Weight for host-level variance
            w_pool: Weight for pool-level variance
            enabled_levels: List of enabled levels (None = all enabled)
        """
        # Determine enabled levels
        if enabled_levels is None:
            enabled_levels = ['osd', 'host', 'pool']
        
        self.enabled_levels = set(enabled_levels)
        
        # Validate at least one level is enabled
        if not self.enabled_levels:
            raise ValueError("At least one optimization level must be enabled")
        
        # Normalize weights for enabled levels only
        weights = {}
        if 'osd' in self.enabled_levels:
            weights['osd'] = w_osd
        if 'host' in self.enabled_levels:
            weights['host'] = w_host
        if 'pool' in self.enabled_levels:
            weights['pool'] = w_pool
        
        total = sum(weights.values())
        if total == 0:
            raise ValueError("Total weight of enabled levels cannot be zero")
        
        # Normalize to sum to 1.0
        self.w_osd = weights.get('osd', 0.0) / total if 'osd' in self.enabled_levels else 0.0
        self.w_host = weights.get('host', 0.0) / total if 'host' in self.enabled_levels else 0.0
        self.w_pool = weights.get('pool', 0.0) / total if 'pool' in self.enabled_levels else 0.0
    
    def calculate_score(self, state: ClusterState) -> float:
        """
        Calculate composite balance score.
        
        Only calculates variance for enabled dimensions, skipping computation
        for disabled dimensions entirely (not just weighting to 0).
        """
        score = 0.0
        
        # Only calculate if enabled
        if 'osd' in self.enabled_levels:
            osd_var = self.calculate_osd_variance(state)
            score += self.w_osd * osd_var
        
        if 'host' in self.enabled_levels:
            host_var = self.calculate_host_variance(state)
            score += self.w_host * host_var
        
        if 'pool' in self.enabled_levels:
            pool_var = self.calculate_pool_variance(state)
            score += self.w_pool * pool_var
        
        return score
    
    def is_level_enabled(self, level: str) -> bool:
        """Check if a specific level is enabled."""
        return level in self.enabled_levels
    
    def get_enabled_levels(self) -> List[str]:
        """Get list of enabled optimization levels."""
        return sorted(self.enabled_levels)
```

### 3. Optimizer Enhancement

#### `optimizer.py` Modification

```python
def optimize_primaries(
    state: ClusterState,
    target_cv: float = 0.10,
    max_iterations: int = 1000,
    scorer: Optional[Scorer] = None,
    pool_filter: Optional[int] = None,
    enabled_levels: Optional[List[str]] = None
) -> List[SwapProposal]:
    """
    Main optimization loop with configurable levels.
    
    Args:
        state: ClusterState to optimize
        target_cv: Target coefficient of variation
        max_iterations: Maximum iterations
        scorer: Scorer instance (created if None)
        pool_filter: Optional pool filter
        enabled_levels: Optimization levels to enable (None = all)
    """
    swaps = []
    
    if not state.osds:
        print("Warning: No OSDs found")
        return swaps
    
    # Create scorer with enabled levels
    if scorer is None:
        if enabled_levels:
            # Auto-adjust weights based on enabled levels
            num_levels = len(enabled_levels)
            weight = 1.0 / num_levels
            
            w_osd = weight if 'osd' in enabled_levels else 0.0
            w_host = weight if 'host' in enabled_levels else 0.0
            w_pool = weight if 'pool' in enabled_levels else 0.0
            
            scorer = Scorer(
                w_osd=w_osd,
                w_host=w_host,
                w_pool=w_pool,
                enabled_levels=enabled_levels
            )
        else:
            scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
    
    # Print optimization strategy
    levels_str = ', '.join(sorted(scorer.get_enabled_levels()))
    print(f"Optimization strategy: {levels_str.upper()}")
    print(f"Weights: OSD={scorer.w_osd:.2f}, HOST={scorer.w_host:.2f}, POOL={scorer.w_pool:.2f}")
    
    # Rest of optimization logic unchanged...
    for iteration in range(max_iterations):
        # ... existing code ...
        pass
    
    return swaps
```

### 4. CLI Enhancement

#### `cli.py` Modification

```python
parser.add_argument(
    '--optimization-levels',
    type=str,
    default='osd,host,pool',
    help='Comma-separated optimization levels: osd,host,pool (default: all)'
)

parser.add_argument(
    '--list-optimization-strategies',
    action='store_true',
    help='List available optimization strategies and exit'
)

# Usage examples:

# OSD-only optimization
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd \
    --dry-run

# OSD + HOST optimization
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host \
    --output rebalance.sh

# HOST + POOL optimization (skip OSD)
python3 -m ceph_primary_balancer.cli \
    --optimization-levels host,pool \
    --output rebalance.sh

# Full 3D (default)
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host,pool \
    --output rebalance.sh

# List strategies
python3 -m ceph_primary_balancer.cli --list-optimization-strategies
```

#### Strategy Listing Output

```
Available Optimization Strategies:

1. OSD-ONLY (--optimization-levels osd)
   - Balances primary distribution across OSDs
   - Fastest strategy, simplest approach
   - Use for: Small clusters, quick fixes, lab environments
   - Time: ~1× baseline
   - Memory: ~1× baseline

2. OSD+HOST (--optimization-levels osd,host)
   - Balances OSDs and host network load
   - Good balance of speed and quality
   - Use for: Multi-host clusters, network hotspots
   - Time: ~2× baseline
   - Memory: ~1.5× baseline

3. OSD+POOL (--optimization-levels osd,pool)
   - Balances OSDs and per-pool distribution
   - Good for multi-pool workload isolation
   - Use for: Multi-pool clusters, workload separation
   - Time: ~2× baseline
   - Memory: ~2× baseline

4. HOST+POOL (--optimization-levels host,pool)
   - Balances network and pool-level distribution
   - Network-focused optimization
   - Use for: Network-constrained clusters
   - Time: ~1.5× baseline
   - Memory: ~1.5× baseline

5. FULL-3D (--optimization-levels osd,host,pool) [DEFAULT]
   - Comprehensive three-dimensional balancing
   - Best overall quality
   - Use for: Production clusters, comprehensive optimization
   - Time: ~3-4× baseline
   - Memory: ~3× baseline

Recommendation:
- Development/Testing: Use OSD-only for quick iterations
- Small Production (<100 OSDs): Use OSD+HOST
- Large Production (>100 OSDs): Use Full 3D
- Network-Constrained: Use HOST+POOL or OSD+HOST
- Single-Pool Clusters: Use OSD+HOST (skip pool optimization)
```

### 5. Benchmark Integration

#### New Strategy Comparison Scenarios

```python
# In benchmark/scenarios.py

STRATEGY_COMPARISON_SCENARIOS = [
    {
        'name': 'strategy_comparison_small',
        'description': 'Compare strategies on small cluster',
        'base_params': {
            'num_osds': 50,
            'num_hosts': 5,
            'num_pools': 2,
            'pgs_per_pool': 500,
            'imbalance_cv': 0.30
        },
        'strategies': [
            {'name': 'osd_only', 'levels': ['osd']},
            {'name': 'osd_host', 'levels': ['osd', 'host']},
            {'name': 'osd_pool', 'levels': ['osd', 'pool']},
            {'name': 'host_pool', 'levels': ['host', 'pool']},
            {'name': 'full_3d', 'levels': ['osd', 'host', 'pool']}
        ]
    },
    {
        'name': 'strategy_comparison_medium',
        'description': 'Compare strategies on medium cluster',
        'base_params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 5,
            'pgs_per_pool': 2000,
            'imbalance_cv': 0.30
        },
        'strategies': [
            {'name': 'osd_only', 'levels': ['osd']},
            {'name': 'osd_host', 'levels': ['osd', 'host']},
            {'name': 'full_3d', 'levels': ['osd', 'host', 'pool']}
        ]
    },
    {
        'name': 'strategy_comparison_topology_single_host',
        'description': 'Single-host cluster (OSD-only makes sense)',
        'base_params': {
            'num_osds': 50,
            'num_hosts': 1,
            'num_pools': 3,
            'pgs_per_pool': 1000,
            'imbalance_cv': 0.30
        },
        'strategies': [
            {'name': 'osd_only', 'levels': ['osd']},
            {'name': 'osd_pool', 'levels': ['osd', 'pool']},
        ]
    },
    {
        'name': 'strategy_comparison_topology_single_pool',
        'description': 'Single-pool cluster (skip pool optimization)',
        'base_params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 1,
            'pgs_per_pool': 5000,
            'imbalance_cv': 0.30
        },
        'strategies': [
            {'name': 'osd_only', 'levels': ['osd']},
            {'name': 'osd_host', 'levels': ['osd', 'host']},
        ]
    }
]
```

#### Benchmark CLI Commands

```bash
# Compare all strategies on standard scenarios
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --scenarios standard \
    --output strategy_comparison.json \
    --html-output strategy_comparison.html

# Compare specific strategies
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --strategies osd,osd+host,full-3d \
    --scenario medium \
    --output comparison.json

# Quick strategy comparison (small cluster)
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --scenario small \
    --quick

# Topology-specific comparison
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --scenario single-host \
    --output single_host_comparison.json
```

#### Enhanced Reporter Output

```python
# In benchmark/reporter.py

def generate_strategy_comparison_report(results: Dict[str, Any]) -> str:
    """
    Generate strategy comparison report.
    
    Shows side-by-side comparison of different optimization strategies:
    - Runtime and memory
    - Convergence quality (CV per dimension)
    - Swap count and efficiency
    - Cost-benefit analysis
    """
    report = []
    
    report.append("# Optimization Strategy Comparison\n")
    report.append(f"Cluster: {results['cluster_params']}\n")
    report.append(f"Date: {results['timestamp']}\n\n")
    
    # Summary table
    report.append("## Strategy Performance Summary\n\n")
    report.append("| Strategy | Runtime | Memory | Final CV | Swaps | Efficiency |\n")
    report.append("|----------|---------|--------|----------|-------|------------|\n")
    
    for strategy, data in results['strategies'].items():
        runtime = data['runtime']
        memory = data['memory_mb']
        cv_osd = data['final_cv_osd']
        swaps = data['swap_count']
        efficiency = swaps / runtime if runtime > 0 else 0
        
        report.append(f"| {strategy:15} | {runtime:5.2f}s | {memory:5.1f} MB | "
                     f"{cv_osd:5.2%} | {swaps:5d} | {efficiency:5.1f} swaps/s |\n")
    
    # Detailed comparison
    report.append("\n## Detailed Analysis\n\n")
    
    for strategy, data in results['strategies'].items():
        report.append(f"### {strategy}\n\n")
        report.append(f"- **Runtime:** {data['runtime']:.2f}s\n")
        report.append(f"- **Memory:** {data['memory_mb']:.1f} MB\n")
        report.append(f"- **Iterations:** {data['iterations']}\n")
        report.append(f"- **Swaps Applied:** {data['swap_count']}\n")
        report.append(f"- **Final OSD CV:** {data['final_cv_osd']:.2%}\n")
        
        if 'final_cv_host' in data:
            report.append(f"- **Final HOST CV:** {data['final_cv_host']:.2%}\n")
        
        if 'final_cv_pool' in data:
            report.append(f"- **Final POOL CV:** {data['final_cv_pool']:.2%}\n")
        
        report.append(f"- **Quality Score:** {data.get('quality_score', 'N/A')}\n")
        report.append("\n")
    
    # Recommendations
    report.append("## Recommendations\n\n")
    
    # Find best strategy by different criteria
    fastest = min(results['strategies'].items(), key=lambda x: x[1]['runtime'])
    best_quality = min(results['strategies'].items(), 
                       key=lambda x: x[1]['final_cv_osd'])
    best_efficiency = max(results['strategies'].items(),
                          key=lambda x: x[1]['swap_count'] / x[1]['runtime'])
    
    report.append(f"- **Fastest:** {fastest[0]} ({fastest[1]['runtime']:.2f}s)\n")
    report.append(f"- **Best Quality:** {best_quality[0]} "
                 f"(CV: {best_quality[1]['final_cv_osd']:.2%})\n")
    report.append(f"- **Best Efficiency:** {best_efficiency[0]} "
                 f"({best_efficiency[1]['swap_count'] / best_efficiency[1]['runtime']:.1f} swaps/s)\n")
    
    return ''.join(report)
```

---

## Implementation Sprints

### Sprint 6.5A: Core Configuration (Week 1)

**Tasks:**
1. Add `enabled_levels` to configuration schema
2. Update `Config` class with validation
3. Modify `Scorer` to support enabled levels
4. Update `Scorer` to skip disabled dimensions
5. Unit tests for configuration and scorer
6. Documentation updates

**Deliverables:**
- Configuration support for enabled_levels
- Scorer correctly skips disabled dimensions
- Test coverage ≥90%

**Files Modified:**
- `src/ceph_primary_balancer/config.py` (~50 lines added)
- `src/ceph_primary_balancer/scorer.py` (~80 lines modified)
- `tests/test_config.py` (~100 lines added)
- `tests/test_scorer.py` (~150 lines added)

**Success Criteria:**
✅ Configuration validates enabled_levels correctly  
✅ Scorer skips computation for disabled dimensions  
✅ Weights auto-normalize for enabled levels  
✅ All tests pass  

---

### Sprint 6.5B: Optimizer Integration (Week 2)

**Tasks:**
1. Update `optimize_primaries()` to accept enabled_levels
2. Modify optimizer to skip tracking for disabled dimensions
3. Update CLI with `--optimization-levels` flag
4. Add `--list-optimization-strategies` command
5. Integration tests
6. Performance validation

**Deliverables:**
- CLI supports strategy selection
- Optimizer respects enabled levels
- Test coverage ≥85%

**Files Modified:**
- `src/ceph_primary_balancer/optimizer.py` (~100 lines modified)
- `src/ceph_primary_balancer/cli.py` (~150 lines added)
- `tests/test_optimizer.py` (~200 lines added)
- `tests/test_cli.py` (~100 lines added)

**Success Criteria:**
✅ CLI flag works correctly  
✅ Optimizer skips disabled dimension tracking  
✅ Performance improvement measurable  
✅ All tests pass  

---

### Sprint 6.5C: Benchmark Integration (Week 3)

**Tasks:**
1. Add strategy comparison scenarios
2. Implement `compare-strategies` command
3. Enhanced reporter for strategy comparison
4. Generate comparison reports (JSON, Markdown, HTML)
5. Benchmark all strategy combinations
6. Performance analysis

**Deliverables:**
- Strategy comparison benchmarks working
- Comprehensive comparison reports
- Performance insights documented

**Files Modified/Created:**
- `src/ceph_primary_balancer/benchmark/scenarios.py` (~150 lines added)
- `src/ceph_primary_balancer/benchmark/runner.py` (~200 lines modified)
- `src/ceph_primary_balancer/benchmark/reporter.py` (~250 lines added)
- `src/ceph_primary_balancer/benchmark_cli.py` (~100 lines added)
- `tests/test_strategy_benchmarks.py` (~200 lines new)

**Success Criteria:**
✅ Benchmark compares all strategies  
✅ Reports show clear performance differences  
✅ Recommendations generated automatically  
✅ All tests pass  

---

### Sprint 6.5D: Documentation & Release (Week 4)

**Tasks:**
1. Create optimization strategy selection guide
2. Update USAGE.md with --optimization-levels
3. Update BENCHMARK-USAGE.md with strategy comparison
4. Add configuration examples for each strategy
5. Performance tuning guide
6. Release v1.2.5

**Deliverables:**
- Complete documentation
- Strategy selection guide
- Configuration examples
- v1.2.5 release

**Files Created/Modified:**
- `docs/optimization-strategies.md` (new, ~300 lines)
- `docs/USAGE.md` (~100 lines added)
- `docs/BENCHMARK-USAGE.md` (~150 lines added)
- `config-examples/osd-only.json` (new)
- `config-examples/osd-host.json` (new)
- `config-examples/full-3d-optimized.json` (new)
- `CHANGELOG.md` (updated)
- `RELEASE-NOTES-v1.2.5.md` (new)

**Success Criteria:**
✅ All documentation complete  
✅ Clear guidance for users  
✅ Configuration examples provided  
✅ Release notes comprehensive  

---

## Testing Strategy

### Unit Tests

**New Test Files:**

```python
# tests/test_configurable_levels.py

def test_config_enabled_levels_default():
    """Test default enabled levels are all three."""
    config = Config()
    levels = config.get('optimization.enabled_levels')
    assert set(levels) == {'osd', 'host', 'pool'}

def test_config_enabled_levels_validation():
    """Test validation of enabled_levels."""
    # Valid
    config = Config()
    config.settings['optimization']['enabled_levels'] = ['osd', 'host']
    config.validate_enabled_levels()  # Should not raise
    
    # Invalid: empty list
    config.settings['optimization']['enabled_levels'] = []
    with pytest.raises(ConfigError, match="At least one"):
        config.validate_enabled_levels()
    
    # Invalid: unknown level
    config.settings['optimization']['enabled_levels'] = ['osd', 'invalid']
    with pytest.raises(ConfigError, match="Invalid level"):
        config.validate_enabled_levels()

def test_scorer_skips_disabled_dimensions():
    """Test that scorer truly skips computation for disabled levels."""
    state = create_test_cluster()
    
    # OSD-only scorer
    scorer = Scorer(w_osd=1.0, enabled_levels=['osd'])
    
    # Verify it doesn't call host/pool variance methods
    with patch.object(scorer, 'calculate_host_variance') as mock_host:
        with patch.object(scorer, 'calculate_pool_variance') as mock_pool:
            score = scorer.calculate_score(state)
            
            # Should NOT be called
            mock_host.assert_not_called()
            mock_pool.assert_not_called()

def test_optimizer_respects_enabled_levels():
    """Test optimizer respects enabled_levels configuration."""
    state = create_imbalanced_cluster(num_osds=20, cv=0.30)
    
    # OSD-only optimization
    swaps = optimize_primaries(
        state,
        enabled_levels=['osd'],
        target_cv=0.10
    )
    
    # Should improve OSD balance
    osd_cv = calculate_osd_cv(state)
    assert osd_cv < 0.15

def test_cli_optimization_levels_flag():
    """Test CLI --optimization-levels flag parsing."""
    args = parse_args(['--optimization-levels', 'osd,host', '--dry-run'])
    
    assert set(args.optimization_levels.split(',')) == {'osd', 'host'}

def test_strategy_comparison_benchmark():
    """Test strategy comparison benchmark."""
    from benchmark.runner import run_strategy_comparison
    
    results = run_strategy_comparison(
        scenario='small',
        strategies=['osd', 'osd+host', 'full-3d']
    )
    
    # Verify all strategies ran
    assert len(results['strategies']) == 3
    
    # Verify OSD-only is fastest
    osd_time = results['strategies']['osd']['runtime']
    full_time = results['strategies']['full-3d']['runtime']
    assert osd_time < full_time
```

### Integration Tests

```python
def test_end_to_end_osd_only():
    """Test complete OSD-only optimization."""
    state = generate_synthetic_cluster(num_osds=50, imbalance_cv=0.30)
    
    swaps = optimize_primaries(
        state,
        target_cv=0.10,
        enabled_levels=['osd']
    )
    
    # Verify OSD balance improved
    assert calculate_osd_cv(state) < 0.12
    
    # Verify host CV NOT optimized (may still be high)
    # (This is expected with OSD-only)

def test_end_to_end_host_pool():
    """Test HOST+POOL optimization (skip OSD)."""
    state = generate_synthetic_cluster(
        num_osds=100,
        num_hosts=10,
        num_pools=5,
        imbalance_cv=0.30
    )
    
    swaps = optimize_primaries(
        state,
        target_cv=0.10,
        enabled_levels=['host', 'pool']
    )
    
    # Verify host and pool improved
    assert calculate_host_cv(state) < 0.15
    assert calculate_pool_avg_cv(state) < 0.15
    
    # OSD CV may not be optimal (not being optimized directly)

def test_strategy_comparison_all():
    """Test all strategy combinations."""
    strategies = [
        ['osd'],
        ['osd', 'host'],
        ['osd', 'pool'],
        ['host', 'pool'],
        ['osd', 'host', 'pool']
    ]
    
    base_state = generate_synthetic_cluster(num_osds=50, cv=0.30)
    
    results = {}
    for strategy in strategies:
        state = copy.deepcopy(base_state)
        
        start = time.time()
        swaps = optimize_primaries(state, enabled_levels=strategy)
        runtime = time.time() - start
        
        strategy_name = '+'.join(sorted(strategy))
        results[strategy_name] = {
            'runtime': runtime,
            'swaps': len(swaps),
            'osd_cv': calculate_osd_cv(state),
            'host_cv': calculate_host_cv(state),
            'pool_cv': calculate_pool_avg_cv(state)
        }
    
    # Verify all improved cluster in some way
    for strategy_name, data in results.items():
        assert data['swaps'] > 0
        # At least one CV should improve
        assert (data['osd_cv'] < 0.30 or 
                data['host_cv'] < 0.30 or 
                data['pool_cv'] < 0.30)
```

---

## Performance Targets

### Expected Performance Characteristics

| Strategy | Time vs Full | Memory vs Full | Best Use Case |
|----------|--------------|----------------|---------------|
| OSD-only | 0.3× (3× faster) | 0.3× | Quick fixes, small clusters |
| OSD+HOST | 0.6× (1.7× faster) | 0.5× | Multi-host clusters |
| OSD+POOL | 0.7× (1.4× faster) | 0.6× | Multi-pool clusters |
| HOST+POOL | 0.4× (2.5× faster) | 0.4× | Network-focused |
| Full 3D | 1.0× (baseline) | 1.0× | Comprehensive optimization |

### Quality vs Performance Trade-offs

```
Quality (Final CV) vs Runtime:

OSD-only:       ████████░░░░ (67% quality, 100% speed)
OSD+HOST:       ██████████░░ (83% quality, 60% speed)
OSD+POOL:       ██████████░░ (83% quality, 70% speed)
HOST+POOL:      ████████░░░░ (67% quality, 40% speed)
Full 3D:        ████████████ (100% quality, 100% time)
```

### Benchmark Scenarios

```bash
# Quick comparison (2-5 minutes)
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --scenario small \
    --strategies all \
    --iterations 3

# Standard comparison (15-30 minutes)
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --scenario medium \
    --strategies all \
    --iterations 5

# Comprehensive comparison (1-2 hours)
python3 -m ceph_primary_balancer.benchmark_cli compare-strategies \
    --scenarios all \
    --strategies all \
    --iterations 10 \
    --output comprehensive.json \
    --html-output comprehensive.html
```

---

## Configuration Examples

### Example 1: OSD-Only (Fast)

```json
{
  "optimization": {
    "enabled_levels": ["osd"],
    "target_cv": 0.12,
    "max_iterations": 500
  },
  "scoring": {
    "weights": {
      "osd": 1.0
    }
  },
  "output": {
    "directory": "./rebalance-osd-only"
  }
}
```

**Use for:** Development, testing, small clusters, quick fixes

### Example 2: OSD+HOST (Balanced)

```json
{
  "optimization": {
    "enabled_levels": ["osd", "host"],
    "target_cv": 0.10,
    "max_iterations": 1000
  },
  "scoring": {
    "weights": {
      "osd": 0.6,
      "host": 0.4
    }
  },
  "output": {
    "directory": "./rebalance-osd-host"
  }
}
```

**Use for:** Most production clusters, good balance of speed and quality

### Example 3: Full 3D (Comprehensive)

```json
{
  "optimization": {
    "enabled_levels": ["osd", "host", "pool"],
    "target_cv": 0.08,
    "max_iterations": 2000
  },
  "scoring": {
    "weights": {
      "osd": 0.5,
      "host": 0.3,
      "pool": 0.2
    }
  },
  "output": {
    "directory": "./rebalance-full-3d"
  }
}
```

**Use for:** Large production clusters, best overall balance

### Example 4: Network-Focused

```json
{
  "optimization": {
    "enabled_levels": ["host", "pool"],
    "target_cv": 0.10,
    "max_iterations": 1000
  },
  "scoring": {
    "weights": {
      "host": 0.7,
      "pool": 0.3
    }
  },
  "output": {
    "directory": "./rebalance-network"
  }
}
```

**Use for:** Network-constrained clusters, host-level hotspots

---

## Documentation Requirements

### User Documentation

1. **Optimization Strategy Guide** (`docs/optimization-strategies.md`)
   - Decision tree for strategy selection
   - Performance characteristics of each strategy
   - When to use each approach
   - Configuration examples

2. **Updated Usage Guide** (`docs/USAGE.md`)
   - `--optimization-levels` flag documentation
   - Strategy selection examples
   - Performance considerations

3. **Updated Benchmark Guide** (`docs/BENCHMARK-USAGE.md`)
   - Strategy comparison benchmarks
   - How to interpret results
   - Recommendations by cluster type

4. **Configuration Reference** (update existing)
   - `enabled_levels` parameter
   - Weight normalization behavior
   - Validation rules

### Developer Documentation

1. **Architecture Update**
   - How enabled_levels works internally
   - Scorer modification details
   - Performance optimization techniques

2. **Testing Guide**
   - How to test new strategies
   - Benchmark integration
   - Performance validation

---

## Success Criteria

### Functional Requirements

✅ Configuration supports `enabled_levels` list  
✅ Scorer skips computation for disabled dimensions (not just weight=0)  
✅ CLI supports `--optimization-levels` flag  
✅ All strategy combinations work correctly  
✅ Benchmark framework supports strategy comparison  
✅ Reports clearly show performance differences  

### Performance Requirements

✅ OSD-only is 2.5-3.5× faster than Full 3D  
✅ OSD+HOST is 1.5-2.0× faster than Full 3D  
✅ Memory usage scales with enabled dimensions  
✅ No performance regression for Full 3D (backward compatible)  

### Quality Requirements

✅ Test coverage ≥90% for new code  
✅ All existing tests still pass  
✅ Integration tests for all strategies  
✅ Benchmark comparison report generated  
✅ Documentation complete and clear  

---

## Backward Compatibility

### v1.2.0 Compatibility

All existing configurations and CLI commands continue to work:

```bash
# Old command (still works, uses Full 3D by default)
python3 -m ceph_primary_balancer.cli --dry-run

# Old config (still works, defaults to all levels)
{
  "scoring": {
    "weights": {
      "osd": 0.5,
      "host": 0.3,
      "pool": 0.2
    }
  }
}
```

### Migration Path

Users can opt-in to new features:

```bash
# Start using optimization levels
python3 -m ceph_primary_balancer.cli \
    --optimization-levels osd,host \
    --dry-run

# Update config file
{
  "optimization": {
    "enabled_levels": ["osd", "host"]
  }
}
```

No breaking changes to existing functionality.

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Performance regression | High | Extensive benchmarking, comparison with v1.2.0 |
| Incorrect dimension skipping | High | Comprehensive unit tests, validation |
| User confusion | Medium | Clear documentation, strategy listing command |
| Configuration complexity | Medium | Good defaults, examples for common cases |
| Benchmark overhead | Low | Quick/standard/comprehensive modes |

---

## Future Enhancements (v1.3+)

### Adaptive Strategy Selection

Auto-select optimal strategy based on cluster topology:

```python
def auto_select_strategy(state: ClusterState) -> List[str]:
    """Auto-select best optimization strategy."""
    num_osds = len(state.osds)
    num_hosts = len(state.hosts) if state.hosts else 1
    num_pools = len(state.pools) if state.pools else 1
    
    # Single host → OSD-only
    if num_hosts <= 1:
        return ['osd']
    
    # Single pool → OSD+HOST
    if num_pools <= 1:
        return ['osd', 'host']
    
    # Small cluster → Full 3D (fast enough)
    if num_osds < 100:
        return ['osd', 'host', 'pool']
    
    # Large cluster → OSD+HOST (balance speed/quality)
    return ['osd', 'host']
```

### Multi-Phase Optimization

Progressive optimization with automatic phase switching:

```bash
# Phase 1: Quick OSD balance
# Phase 2: Add HOST if not converged
# Phase 3: Add POOL for final refinement
python3 -m ceph_primary_balancer.cli \
    --optimization-strategy adaptive \
    --phases 3
```

### Per-Pool Strategy

Different strategies for different pools:

```json
{
  "optimization": {
    "global_levels": ["osd", "host"],
    "per_pool_overrides": {
      "1": {"levels": ["osd", "host", "pool"]},  // Critical pool
      "2": {"levels": ["osd"]}                    // Less important
    }
  }
}
```

---

## Version History & Roadmap

### v1.0.0 (Released)
✅ Multi-dimensional optimization with weights  

### v1.1.0 (Released)
✅ Benchmark framework  

### v1.2.0 (Released)
✅ Advanced algorithms (Batch Greedy, Tabu Search, Simulated Annealing)  

### v1.2.5 (This Phase)
🎯 Configurable optimization levels  
🎯 Strategy comparison benchmarks  
🎯 Performance isolation and analysis  

### v1.3.0 (Future)
⏳ Adaptive strategy selection  
⏳ Multi-phase optimization  
⏳ Auto-tuning framework  

### v2.0.0 (Future)
⏳ Per-pool strategies  
⏳ Real-time monitoring and rebalancing  
⏳ ML-based optimization  

---

## Estimated Effort

### Code Additions/Modifications

- **Production Code:** ~800 lines
  - `config.py`: ~50 lines
  - `scorer.py`: ~100 lines
  - `optimizer.py`: ~100 lines
  - `cli.py`: ~150 lines
  - `benchmark/scenarios.py`: ~150 lines
  - `benchmark/runner.py`: ~150 lines
  - `benchmark/reporter.py`: ~100 lines

- **Test Code:** ~800 lines
  - `test_configurable_levels.py`: ~300 lines (new)
  - `test_strategy_benchmarks.py`: ~200 lines (new)
  - Modifications to existing tests: ~300 lines

- **Documentation:** ~1,000 lines
  - `optimization-strategies.md`: ~400 lines (new)
  - Usage guide updates: ~200 lines
  - Benchmark guide updates: ~200 lines
  - Configuration examples: ~200 lines

**Total:** ~2,600 lines

### Timeline

- **Sprint 6.5A:** Week 1 (Configuration & Scorer)
- **Sprint 6.5B:** Week 2 (Optimizer & CLI)
- **Sprint 6.5C:** Week 3 (Benchmark Integration)
- **Sprint 6.5D:** Week 4 (Documentation & Release)

**Total Duration:** 4 weeks

---

## Conclusion

Phase 6.5 transforms the Ceph Primary PG Balancer from a fixed multi-dimensional optimizer into a flexible, configurable system where users can:

1. **Choose their optimization strategy** based on cluster topology and needs
2. **Measure exact performance cost** of each optimization dimension
3. **Optimize incrementally** with staged rollouts
4. **Troubleshoot effectively** by isolating dimension conflicts
5. **Save resources** by skipping unnecessary computations

This enhancement provides **measurable value** through:
- **Performance insights** - Data-driven strategy selection
- **Resource efficiency** - Up to 3× faster for OSD-only
- **Production safety** - Incremental optimization workflows
- **Flexibility** - Match optimization to cluster topology

**Target Release:** v1.2.5 - 4 weeks after Phase 6 completion

---

**Document Status:** Planning Complete  
**Next Step:** Architecture review and approval  
**Dependencies:** Phase 6 (v1.2.0) must be complete  
**Backward Compatibility:** 100% - All v1.2.0 features continue to work
