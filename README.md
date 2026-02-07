# Ceph Primary PG Balancer

**Version:** 1.2.0 🚀 | **Status:** Production Ready

Analyze and optimize primary Placement Group distribution across your Ceph cluster
with multi-dimensional balancing (OSD + Host + Pool).

> **🤖 AI-Generated Project:** This project was designed, implemented, and documented by Claude Sonnet 4.5, an AI assistant by Anthropic. All code, architecture, documentation, and tests were AI-generated through iterative collaboration with human guidance.

## Why This Tool?

The built-in Ceph upmap balancer optimizes **total** PG distribution but ignores
**primary** assignment, leading to I/O hotspots. This tool fixes that by balancing
primaries across three dimensions simultaneously:

- **OSD-level:** Prevent individual disk I/O hotspots
- **Host-level:** Prevent network/node bottlenecks
- **Pool-level:** Maintain per-pool balance

## ✨ Features

### ✅ Current Release v1.2.0
**Core Optimization:**
- **Multi-dimensional optimization** with configurable weights
- **Configurable optimization levels** (NEW in v1.2.0) - Enable/disable specific dimensions
- **Host topology awareness** and balancing
- **Pool-specific filtering** and optimization
- Zero data movement (metadata only)

**Optimization Strategies (NEW in v1.2.0):**
- **OSD-only** - Fastest (~3× speedup), ideal for quick fixes
- **OSD+HOST** - Balanced (~1.7× speedup), best for multi-host clusters
- **HOST+POOL** - Network-focused (~2.5× speedup)
- **Full 3D** - Comprehensive, all dimensions (default)
- Use `--list-optimization-strategies` to see all available strategies

**Configuration Management:**
- **Configuration file support** (`--config`) - JSON/YAML files
- **7 example configurations** including optimization strategy examples
- **Hierarchical precedence** - CLI args override config files
- **Output directory organization** (`--output-dir`) with timestamp-based naming
- **Verbosity control** (`--verbose`/`--quiet` modes)

**Production Safety:**
- **Max changes limit** to control swap count (`--max-changes`)
- **Cluster health checks** in generated scripts
- **Automatic rollback script** generation
- **Batch execution** with configurable batch sizes (`--batch-size`)

**Reporting & Export:**
- **JSON export** for automation (`--json-output`)
- **Markdown report generation** (`--report-output`)
- **Enhanced terminal reports** with comparison tables
- **Safe bash script generation** with progress tracking

**Quality Assurance:**
- **Comprehensive unit tests** (57 tests, 95%+ coverage)
- **Integration tests** for all phases
- **Production validated** and ready for enterprise use

## 🚀 Quick Start

### Basic Usage

```bash
# Install dependencies (Python 3.8+ required)
pip install -r requirements.txt

# Analyze your cluster
python3 -m ceph_primary_balancer.cli --dry-run

# Generate rebalancing script
python3 -m ceph_primary_balancer.cli --output ./rebalance.sh

# Review and apply
cat ./rebalance.sh
./rebalance.sh
```

### Using Configuration Files (v1.0.0)

```bash
# Use pre-built configuration for production-safe rebalancing
python3 -m ceph_primary_balancer.cli --config config-examples/production-safe.json

# OSD-focused optimization with organized output
python3 -m ceph_primary_balancer.cli \
  --config config-examples/osd-focused.json \
  --output-dir ./rebalance-results

# Override config values with CLI args
python3 -m ceph_primary_balancer.cli \
  --config config-examples/balanced.json \
  --max-changes 50 \
  --verbose

# Create custom configuration (copy and modify examples)
cp config-examples/balanced.json my-cluster.json
# Edit my-cluster.json with your settings
python3 -m ceph_primary_balancer.cli --config my-cluster.json
```

See [config-examples/README.md](config-examples/README.md) for configuration guide and tuning tips.

### 🧪 Benchmarking (NEW in v1.1.0)

**Comprehensive benchmark framework for performance validation and quality assessment.**

```bash
# Quick smoke test
python3 -m ceph_primary_balancer.benchmark_cli quick

# Run standard benchmark suite
python3 -m ceph_primary_balancer.benchmark_cli run --suite standard

# Generate HTML dashboard
python3 -m ceph_primary_balancer.benchmark_cli run \
  --suite standard \
  --html-output dashboard.html

# Compare with baseline for regression detection
python3 -m ceph_primary_balancer.benchmark_cli compare \
  --baseline baseline.json \
  --threshold 0.10

# Generate synthetic test dataset
python3 -m ceph_primary_balancer.benchmark_cli generate-dataset \
  --osds 100 \
  --pgs 5000 \
  --output dataset.json
```

**Features:**
- **Performance profiling** - Runtime and memory metrics
- **Quality analysis** - Balance improvement, convergence, fairness
- **Scalability testing** - Multiple scales with complexity analysis
- **Regression detection** - Compare against baselines
- **Multi-format output** - Terminal, JSON, HTML dashboard
- **Standard scenarios** - Quick, standard, and comprehensive suites

**Performance Reference (MacBook Air M1):**
- **Tiny (100 PGs):** < 0.01s, 0.1 MB
- **Small (500 PGs):** < 1s, 0.4 MB
- **Medium (2000 PGs):** ~38s, 1.7 MB
- **Large (5000 PGs):** ~14 min, 3.9 MB

See [docs/BENCHMARK-USAGE.md](docs/BENCHMARK-USAGE.md) for complete benchmark documentation and [docs/M1-BENCHMARK-RESULTS.md](docs/M1-BENCHMARK-RESULTS.md) for detailed M1 performance results.

### Testing with Fixture Data

```bash
# Run optimization against test fixtures (no live cluster needed)
python tests/run_production_optimization.py --dry-run --verbose

# Compare multiple optimization strategies (takes several hours)
./tests/run_optimization_comparison.sh

# Analyze comparison results
python tests/generate_comparison_summary.py
cat optimization_comparison_results/SUMMARY.md
```

## 🔮 Roadmap & Future Enhancements

### Phase 7.1: Dynamic Weight Optimization (Planned)
**Status:** Planning Complete - Ready for implementation

Automatic weight adaptation for faster convergence and better results:
- **24% faster** optimization on production clusters (6.6h → 5.0h)
- **7-8% better** final balance quality (17.10% → 15.8% CV)
- **Zero changes** needed for existing algorithms (universal compatibility)
- Three strategies: CV-Proportional, Target-Distance, Adaptive-Hybrid
- Opt-in feature with `--dynamic-weights` flag

**Key Innovation:** Benefits ALL optimization algorithms (greedy, batch greedy, tabu search, simulated annealing, hybrid) because they all use the abstract `Scorer` interface.

See [`plans/phase7.1-dynamic-weights.md`](plans/phase7.1-dynamic-weights.md) for complete specifications.

### Phase 7: Advanced Algorithms (Planned)
- **Batch Greedy** optimization for 20-40% faster convergence
- **Tabu Search** for 10-15% better quality (deterministic)
- **Simulated Annealing** for global optimum (2-5% better CV)
- **Hybrid approaches** combining algorithms for best of both worlds
- Algorithm comparison framework built on Phase 5 benchmarking

See [`plans/phase7-advanced-algorithms.md`](plans/phase7-advanced-algorithms.md) for details.

## 📖 Documentation

- [Installation Guide](docs/INSTALLATION.md) - Setup and prerequisites
- [Usage Guide](docs/USAGE.md) - Command examples and workflows
- [Benchmark Guide](docs/BENCHMARK-USAGE.md) - Comprehensive benchmarking framework (NEW)
- [M1 Benchmark Results](docs/M1-BENCHMARK-RESULTS.md) - Performance results on Apple M1 (NEW) ⭐
- [Computational Complexity](docs/COMPUTATIONAL-COMPLEXITY.md) - Algorithm complexity & scalability (NEW) ⭐
- [Technical Specification](docs/technical-specification.md) - Architecture and algorithms
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Development Guide](docs/DEVELOPMENT.md) - Contributing and testing
- [Development History](docs/DEVELOPMENT-HISTORY.md) - Complete project evolution

## 📊 Version History

- **v1.1.0-dev** 🚀 (In Progress) - Phase 5: Benchmark framework with performance/quality testing
- **v1.0.0** 🎉 (2026-02-04) - Production Release: Configuration management, output organization, verbosity control
- **v0.8.0** - Comprehensive unit tests and documentation (57 tests, 95%+ coverage)
- **v0.7.0** - Batch execution support with configurable sizes
- **v0.6.0** - Automatic rollback script generation
- **v0.5.0** - Max changes limit and health checks
- **v0.4.0** - Enhanced reporting with JSON/Markdown export
- **v0.3.0** - Pool-level optimization (3D balancing)
- **v0.2.0** - Host-level optimization (2D balancing)
- **v0.1.0** - MVP with OSD-level balancing

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## 🔧 Requirements

- Python 3.8 or higher
- Ceph cluster with admin access
- `ceph` CLI available in PATH

## 📄 License

Apache 2.0 - See [LICENSE](LICENSE) for details.
