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

Phase 3 Features:
- JSON export with comprehensive cluster state and analysis results
- Enhanced terminal reporting with formatted tables
- Markdown report generation with detailed analysis
- Multi-format output support (terminal, JSON, markdown)
- Schema-versioned JSON output for automation integration
- Before/after comparisons at all levels (OSD, Host, Pool)
"""

__version__ = "0.4.0"

# Package-level imports will be added as modules are implemented
__all__ = ["__version__"]
