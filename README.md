# Ceph Primary PG Balancer

Analyze and optimize primary Placement Group distribution across your Ceph cluster.

## Why?

The built-in upmap balancer optimizes total PG distribution but ignores primary 
assignment, leading to I/O hotspots. This tool fixes that.

## Quick Start

​```bash
pip install -r requirements.txt
python ceph_primary_balancer.py --dry-run
​```

## Features

- Analyzes primary PG distribution across OSDs, hosts, and pools
- Calculates optimal primary assignments
- Generates executable rebalancing scripts
- Zero data movement (metadata only)

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Usage Examples](docs/USAGE.md)
- [Technical Design](docs/DESIGN.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Requirements

- Python 3.8+
- Ceph cluster with admin access
- `ceph` CLI available in PATH

## License

Apache 2.0
