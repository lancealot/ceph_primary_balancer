"""
Ceph Primary PG Balancer

A tool for analyzing and rebalancing primary placement group (PG) distribution
across Ceph OSDs. This package helps identify imbalanced primary PG assignments
and generates rebalancing scripts to optimize cluster performance.

Version History:
- v0.1.0-mvp: Initial MVP with OSD-level balancing
- v0.2.0: Phase 1 - Multi-dimensional optimization with host-level balancing

Phase 1 Features:
- Host topology extraction from OSD tree
- Host-level statistics and variance calculation  
- Multi-dimensional scoring with configurable weights (OSD + Host)
- Host-aware swap prioritization
- Enhanced CLI with --weight-osd and --weight-host options
- Comprehensive host-level reporting
"""

__version__ = "0.2.0"

# Package-level imports will be added as modules are implemented
__all__ = ["__version__"]
