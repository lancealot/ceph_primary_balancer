"""
Ceph Primary PG Balancer

A tool for analyzing and rebalancing primary placement group (PG) distribution
across Ceph OSDs. This package helps identify imbalanced primary PG assignments
and generates rebalancing scripts to optimize cluster performance.

The MVP implementation focuses on:
- Collecting PG mapping data from Ceph clusters
- Analyzing primary PG distribution across OSDs
- Generating safe rebalancing scripts with configurable batch sizes
"""

__version__ = "0.1.0-mvp"

# Package-level imports will be added as modules are implemented
__all__ = ["__version__"]
