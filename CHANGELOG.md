# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
- Phase 4: Advanced features and production readiness

## [0.4.0] - 2026-02-03 - Phase 3: Enhanced Reporting and JSON Export

### Added
- **JSON Export Module**: Comprehensive JSON export with schema versioning
  - New module: `exporter.py` with `JSONExporter` class (~330 lines)
  - Schema version 2.0 with metadata, current/proposed state, changes, and improvements
  - Export complete cluster state at all levels (OSD, Host, Pool)
  - Before/after statistics with detailed breakdowns
  - `--json-output` CLI argument for JSON file export
  - `export_to_file()` method for direct file output
  - Round-trip compatible JSON structure for automation
- **Enhanced Reporting Module**: Multi-format reporting capabilities
  - New module: `reporter.py` with `Reporter` class (~580 lines)
  - Enhanced terminal reports with formatted comparison tables
  - Before/after comparisons at all three dimensions
  - Top N donors/receivers identification (configurable, default: 10)
  - Visual formatting with bars and alignment
  - `--report-output` CLI argument for markdown reports
- **Markdown Report Generation**: Detailed analysis reports
  - Executive summary with key improvements
  - Comparison tables for OSD, Host, and Pool levels
  - Top donors/receivers tables with host information
  - Sample changes table (first 20 swaps)
  - Implementation recommendations and expected outcomes
  - Professional formatting suitable for documentation
- **Multi-Format Output**: Flexible output options
  - `--format` CLI argument: `terminal`, `json`, `markdown`, or `all`
  - Default: `terminal` (backward compatible)
  - `json`: Export JSON only
  - `markdown`: Generate markdown report only
  - `all`: Generate all three output formats
- **Enhanced Terminal Output**: Improved readability
  - Formatted comparison tables with aligned columns
  - Percentage change calculations
  - Top movers section with donor/receiver rankings
  - Change summary with affected entity counts
  - Professional report layout

### Changed
- CLI now imports `JSONExporter` and `Reporter` modules
- CLI stores original state before optimization for accurate reporting
- Enhanced help text with Phase 3 options clearly documented
- `__version__` updated to "0.4.0"
- Package docstring updated with Phase 3 feature summary

### Technical Details
- New module: `src/ceph_primary_balancer/exporter.py` (~330 lines)
- New module: `src/ceph_primary_balancer/reporter.py` (~580 lines)
- Updated module: `src/ceph_primary_balancer/cli.py` (+80 lines)
- Updated module: `src/ceph_primary_balancer/__init__.py` (version bump + docs)
- Total new code: ~910 lines of production code
- Zero new dependencies (Python stdlib only)
- Full backward compatibility maintained

### Performance
- JSON export adds minimal overhead (~100ms for typical clusters)
- Markdown generation is fast (<50ms)
- Enhanced terminal output has no measurable performance impact
- Deep copy of state for reporting adds <200ms

### Usage Examples
```bash
# Generate JSON export
ceph-primary-balancer --json-output ./analysis.json

# Generate markdown report
ceph-primary-balancer --report-output ./analysis.md

# Generate all outputs
ceph-primary-balancer --format all --json-output analysis.json --report-output analysis.md

# Traditional terminal output (default, backward compatible)
ceph-primary-balancer
```

## [0.3.0] - 2026-02-03 - Phase 2: Pool-Level Optimization

### Added
- **Three-dimensional optimization**: Composite scoring across OSD, host, and pool levels
- **Pool data collection**: Automatic extraction of pool information from `ceph osd pool ls detail`
- **PoolInfo data model**: Track per-pool primary distribution across OSDs
- **Pool-level statistics**: Calculate CV, variance, and balance metrics per pool
- **Pool filtering**: `--pool` option to optimize specific pools in isolation
- **Enhanced scoring weights**:
  - `--weight-osd`: Weight for OSD-level variance (default: 0.5, changed from 0.7)
  - `--weight-host`: Weight for host-level variance (default: 0.3)
  - `--weight-pool`: Weight for pool-level variance (default: 0.2, new)
- **Pool-aware optimization**: Swaps now update pool-level primary counts
- **Enhanced reporting**:
  - Pool-level statistics in current and proposed state sections
  - Average pool CV and per-pool CV display
  - Top 5 pools by CV shown in analysis
- **Progress tracking**: Shows OSD CV, Host CV, and Average Pool CV during optimization

### Changed
- `ClusterState` now includes `pools` dictionary for pool-level tracking
- `Scorer` default weights updated to balanced three-dimensional approach (0.5/0.3/0.2)
- `calculate_pool_variance()` now fully implemented (was placeholder in Phase 1)
- `optimize_primaries()` accepts optional `pool_filter` parameter for targeted optimization
- `simulate_swap_score()` now updates pool-level counts in simulated state
- `apply_swap()` updates OSD, host, and pool-level primary counts
- CLI description updated to mention "three-dimensional balancing"
- Progress messages show all three dimensions during optimization

### Technical Details
- Updated module: `models.py` (+14 lines for PoolInfo)
- Updated module: `collector.py` (+40 lines for pool collection)
- Updated module: `analyzer.py` (+90 lines for pool statistics)
- Updated module: `scorer.py` (+20 lines for pool variance)
- Updated module: `optimizer.py` (+90 lines for pool-aware optimization)
- Updated module: `cli.py` (+50 lines for pool options and reporting)
- Total new/modified code: ~304 lines
- All Phase 1 functionality preserved with backward compatibility

### Performance
- Pool-level tracking adds minimal overhead (<5% for typical clusters)
- Three-dimensional scoring maintains sub-second performance for typical swap evaluation
- Pool filtering significantly speeds up targeted optimization

## [0.2.0] - 2026-02-03 - Phase 1: Host-Level Balancing

### Added
- **Multi-dimensional optimization**: Composite scoring across OSD and host levels
- **Host topology extraction**: Automatic detection of host-to-OSD relationships from `ceph osd tree`
- **HostInfo data model**: Track primary counts aggregated at host level
- **Scorer module**: Configurable multi-dimensional scoring with weights
  - `--weight-osd`: Weight for OSD-level variance (default: 0.7)
  - `--weight-host`: Weight for host-level variance (default: 0.3)
- **Host-aware optimization**: Swaps now consider both OSD and host balance
- **Enhanced reporting**: 
  - Separate statistics for OSD and host levels
  - Before/after comparison at both dimensions
  - Top 5 hosts by primary count display
- **Comprehensive test suite**: Phase 1 host balancing tests with 8 test cases

### Changed
- `OSDInfo` now includes `host` field linking to parent host
- `ClusterState` now includes `hosts` dictionary for host-level tracking
- `SwapProposal` now uses `score_improvement` (with `variance_improvement` as backward-compatible alias)
- `optimize_primaries()` accepts optional `Scorer` parameter for custom weights
- `find_best_swap()` uses composite scoring and prioritizes cross-host swaps
- `apply_swap()` updates both OSD and host-level primary counts
- CLI output restructured with clear sections for OSD and host levels
- Progress messages show both OSD CV and Host CV during optimization

### Fixed
- Host-level bottlenecks that could cause network saturation
- Optimization now balances primaries across physical hosts, not just OSDs

### Technical Details
- New module: `src/ceph_primary_balancer/scorer.py` (~180 lines)
- Updated modules: `models.py`, `collector.py`, `optimizer.py`, `cli.py`
- New test file: `tests/test_host_balancing.py` (~280 lines)
- Total new/modified code: ~510 lines

## [0.1.0-mvp] - 2026-01-20 - MVP Release

### Added
- Initial MVP release
- OSD-level primary PG distribution analysis
- Greedy optimization algorithm targeting coefficient of variation (CV)
- Statistical analysis: mean, std dev, CV, min, max, median
- Donor/receiver identification based on mean threshold
- Safe bash script generation with progress tracking
- CLI with `--dry-run`, `--target-cv`, and `--output` options
- Integration test suite with mock Ceph data

### Technical Details
- Zero external dependencies (Python stdlib only)
- ~590 lines of production code
- 6 core modules: models, collector, analyzer, optimizer, script_generator, cli

### Known Limitations
- OSD-level optimization only (no host or pool awareness)
- Simple variance-based scoring (no multi-dimensional optimization)
- Basic terminal output (no JSON export)
