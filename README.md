# Ceph Primary PG Balancer

**Version:** 0.5.0 | **Status:** Production Beta (90% Complete)

Analyze and optimize primary Placement Group distribution across your Ceph cluster
with multi-dimensional balancing (OSD + Host + Pool).

## Why This Tool?

The built-in Ceph upmap balancer optimizes **total** PG distribution but ignores
**primary** assignment, leading to I/O hotspots. This tool fixes that by balancing
primaries across three dimensions simultaneously:

- **OSD-level:** Prevent individual disk I/O hotspots
- **Host-level:** Prevent network/node bottlenecks
- **Pool-level:** Maintain per-pool balance

## ✨ Features

### ✅ Implemented (v0.4.0+)
- Multi-dimensional optimization with configurable weights
- Host topology awareness and balancing
- Pool-specific filtering and optimization
- JSON export for automation (`--json-output`)
- Markdown report generation (`--report-output`)
- Safe bash script generation with progress tracking
- **Production safety: Max changes limit** (`--max-changes`) - v1.0.0
- Zero data movement (metadata only)

### ⏳ Coming Soon (v1.0.0 - Phase 4)
- Cluster health checks in scripts
- Rollback script generation
- Configuration file support

## 🚀 Quick Start

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

## 📖 Documentation

- [Installation Guide](docs/INSTALLATION.md) - Setup and prerequisites
- [Usage Guide](docs/USAGE.md) - Command examples and workflows
- [Technical Specification](docs/technical-specification.md) - Architecture and algorithms
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Development Guide](docs/DEVELOPMENT.md) - Contributing and testing

## 📊 Version History

- **v0.4.0** (Current) - Enhanced reporting with JSON/Markdown export - [Release Notes](RELEASE-NOTES-v0.4.0.md)
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
