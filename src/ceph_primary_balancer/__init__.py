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
- v0.6.0: Phase 4 Sprint 1 - Rollback script generation
- v0.7.0: Phase 4 Sprint 1 Complete - Batch execution support
- v0.8.0: Phase 4 Sprint 2 - Comprehensive unit tests and documentation
- v1.0.0: Phase 4 Sprint 3 Complete - Configuration management and production release
- v1.1.0: Phase 5 Complete - Comprehensive benchmark framework
- v1.2.0: Phase 6.5 Complete - Configurable optimization levels
- v1.3.0: Dynamic weight optimization with adaptive strategies
- v1.4.0: Advanced optimization algorithms (Greedy, Batch Greedy, Tabu Search, Simulated Annealing)
- v1.5.0: Offline mode for air-gapped environments

Production Features (v1.4.0):
✅ Multi-dimensional optimization (OSD, Host, Pool levels)
✅ Configurable optimization levels (enable/disable dimensions for performance tuning)
✅ Strategy selection (OSD-only, OSD+HOST, OSD+POOL, HOST+POOL, Full-3D)
✅ Production safety features (--max-changes, health checks, rollback scripts)
✅ Batch execution with configurable sizes
✅ Comprehensive test suite (65+ tests, 95%+ coverage)
✅ Configuration file support (JSON/YAML)
✅ Organized output directories (--output-dir)
✅ Verbosity control (--verbose/--quiet)
✅ Enhanced reporting (JSON export, markdown reports)
✅ Example configurations for common use cases
✅ Benchmark framework (performance, quality, scalability testing)
✅ Advanced optimization algorithms (greedy, batch_greedy, tabu_search, simulated_annealing)
✅ Algorithm registry with dynamic selection
✅ Deterministic optimization with configurable parameters
✅ Offline mode for air-gapped environments (export/analyze/execute workflow)
"""

__version__ = "1.5.0"

# Package-level imports will be added as modules are implemented
__all__ = ["__version__"]
