# Ceph Primary PG Balancer

Balance primary PG assignments across Ceph OSDs, hosts, and pools using `ceph osd pg-upmap-primary`.

The built-in Ceph upmap balancer optimizes **total** PG distribution but ignores **primary** assignment, leading to I/O hotspots. This tool fixes that by balancing primaries across three dimensions simultaneously:

- **OSD-level:** Prevent individual disk I/O hotspots
- **Host-level:** Prevent network/node bottlenecks
- **Pool-level:** Maintain per-pool balance

**Zero data movement** — only changes which OSD in an existing acting set is primary.

> **Built by Claude.** This entire codebase — architecture, algorithms, tests, and documentation — was designed and written by Claude, an AI assistant by Anthropic. Human developers provide direction and review.

> **Alpha software.** Tested extensively with synthetic data but not yet validated on production clusters. Always review generated scripts before execution.

## Requirements

- Python 3.8+ (standard library only, no pip packages)
- Ceph cluster with admin access
- `ceph` CLI available in PATH

## Quick Start

```bash
# Analyze your cluster (dry run)
PYTHONPATH=src python3 -m ceph_primary_balancer.cli --dry-run

# Generate rebalancing script
PYTHONPATH=src python3 -m ceph_primary_balancer.cli --output ./rebalance.sh

# With specific optimization levels
PYTHONPATH=src python3 -m ceph_primary_balancer.cli \
  --optimization-levels osd,host,pool \
  --output ./rebalance.sh

# Offline mode (air-gapped environments)
PYTHONPATH=src python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export.tar.gz \
  --output rebalance.sh

# Review and apply
cat ./rebalance.sh
./rebalance.sh
```

## How It Works

The optimizer uses a greedy algorithm with O(1) delta scoring:

1. **Analyze** — identify donor OSDs (too many primaries) and receiver OSDs (too few) at both global and per-pool levels
2. **Score** — evaluate candidate swaps using a composite CV (coefficient of variation) across OSD, host, and pool dimensions
3. **Apply** — pick the best swap, apply it, repeat until target balance is reached

Scoring uses CV (std/mean) for each dimension, making them scale-invariant and comparable regardless of cluster size.

## Running Tests

```bash
PYTHONPATH=src pytest tests/ -v
```

## License

Apache 2.0
