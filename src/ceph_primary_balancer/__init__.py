"""
Ceph Primary PG Balancer

A tool for analyzing and rebalancing primary placement group (PG) distribution
across Ceph OSDs. This package helps identify imbalanced primary PG assignments
and generates rebalancing scripts to optimize cluster performance.

Version History:
- v0.1.0-mvp: Initial MVP with OSD-level balancing
- v0.2.0: Phase 1 - Multi-dimensional optimization with host-level balancing
- v0.3.0: Phase 2 - Pool-level balancing with three-dimensional optimization
- v0.4.0: Phase 3 - Enhanced reporting and JSON export
- v0.5.0: Phase 4 Sprint 1 - Production safety features (--max-changes, health checks)

Phase 4 Sprint 1 Features:
- CLI option to limit number of changes (--max-changes)
- Automatic cluster health checks in generated scripts
- Swap limiting with state recalculation
- Production safety enhancements
"""

__version__ = "0.5.0"

# Package-level imports will be added as modules are implemented
__all__ = ["__version__"]
