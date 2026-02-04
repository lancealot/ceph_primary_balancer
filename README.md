# Ceph Primary PG Balancer

**Version:** 1.1.0-dev 🚀 | **Status:** Phase 5 in Progress

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

### ✅ Production Release v1.0.0
**Core Optimization:**
- **Multi-dimensional optimization** with configurable weights
- **Host topology awareness** and balancing
- **Pool-specific filtering** and optimization
- Zero data movement (metadata only)

**Configuration Management (NEW in v1.0.0):**
- **Configuration file support** (`--config`) - JSON/YAML files
- **Example configurations** for common use cases (OSD-focused, host-focused, production-safe)
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

See [docs/BENCHMARK-USAGE.md](docs/BENCHMARK-USAGE.md) for complete benchmark documentation.

## 📖 Documentation

- [Installation Guide](docs/INSTALLATION.md) - Setup and prerequisites
- [Usage Guide](docs/USAGE.md) - Command examples and workflows
- [Benchmark Guide](docs/BENCHMARK-USAGE.md) - Comprehensive benchmarking framework (NEW)
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
