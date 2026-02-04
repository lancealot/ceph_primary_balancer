# Phase 4: Implementation Task List

**Version:** 0.4.0 → 1.0.0
**Date:** 2026-02-04
**Status:** IN PROGRESS - Sprint 1: 100% Complete ✅ | Sprint 2: 100% Complete ✅ | Sprint 3: Ready to Start

This document provides an actionable, prioritized task list for completing Phase 4.

---

## Quick Summary

**What's Done:** ✅ Phases 1-3 Complete + Phase 4 Sprints 1-2 Complete (100%)
- Multi-dimensional balancing (OSD, Host, Pool)
- JSON export and markdown reporting
- Enhanced terminal output
- Integration tests passing
- ✅ **NEW v0.5.0:** --max-changes CLI option (Task 1.1)
- ✅ **NEW v0.5.0:** Cluster health checks in scripts (Task 1.2)
- ✅ **NEW v0.6.0:** Rollback script generation (Task 1.3)
- ✅ **NEW v0.7.0:** Batch execution support (Task 1.4)
- ✅ **NEW v0.8.0:** Comprehensive unit tests - 57 tests, 95%+ coverage (Task 1.5)
- ✅ **NEW v0.8.0:** Enhanced documentation (README.md, USAGE.md updated)

**What's Left:** Phase 4 Implementation (Sprint 3)
- Configuration file support
- Advanced CLI options (--output-dir, --verbose/--quiet)
- Final documentation polish

**Effort:** ~155 lines of code remaining for v1.0.0
**Progress:** Sprint 1: 100% (4/4 tasks) ✅ | Sprint 2: 100% (1/1 task) ✅ | Overall: 1,071 lines implemented

---

## Priority 1: Critical Production Features

These are essential for production use and should be implemented first.

### Task 1.1: Implement `--max-changes` Option ✅ COMPLETE
**File:** [`src/ceph_primary_balancer/cli.py`](../src/ceph_primary_balancer/cli.py)
**Effort:** 20 lines → **Actual:** 30 lines
**Priority:** HIGH
**Status:** ✅ **COMPLETED in v0.5.0**
**Summary:** [`plans/task-1.1-IMPLEMENTATION-SUMMARY.md`](task-1.1-IMPLEMENTATION-SUMMARY.md)

Add CLI argument to limit number of swaps:
```python
parser.add_argument(
    '--max-changes',
    type=int,
    default=None,
    help='Maximum number of primary reassignments (default: unlimited)'
)

# After optimization, before script generation:
if args.max_changes and len(swaps) > args.max_changes:
    print(f"Limiting to {args.max_changes} changes (found {len(swaps)} optimal swaps)")
    swaps = swaps[:args.max_changes]
```

**Test:** Verify that with `--max-changes 100`, exactly 100 swaps are generated

---

### Task 1.2: Add Health Checks to Script Generation ✅ COMPLETE
**File:** [`src/ceph_primary_balancer/script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
**Effort:** 40 lines → **Actual:** 12 lines
**Priority:** HIGH
**Status:** ✅ **COMPLETED in v0.5.0**
**Summary:** [`plans/task-1.2-IMPLEMENTATION-SUMMARY.md`](task-1.2-IMPLEMENTATION-SUMMARY.md)

Add cluster health verification before executing commands:
```bash
# Add after confirmation prompt, before main commands:

echo "Checking cluster health..."
HEALTH=$(ceph health 2>/dev/null)
if [[ ! "$HEALTH" =~ ^HEALTH_OK ]] && [[ ! "$HEALTH" =~ ^HEALTH_WARN ]]; then
    echo "ERROR: Cluster health is $HEALTH"
    echo "Refusing to proceed with unhealthy cluster"
    read -p "Override and continue anyway? [y/N] " override
    [[ "$override" =~ ^[Yy]$ ]] || exit 1
fi
echo "Cluster health: $HEALTH"
echo ""
```

**Test:** Verify script checks health (can mock with `ceph() { echo "HEALTH_OK"; }`)

---

### Task 1.3: Generate Rollback Scripts ✅ COMPLETE
**File:** [`src/ceph_primary_balancer/script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
**Effort:** 50 lines → **Actual:** 138 lines (including comprehensive error handling)
**Priority:** HIGH
**Status:** ✅ **COMPLETED in v0.6.0**
**Summary:** [`plans/task-1.3-IMPLEMENTATION-SUMMARY.md`](task-1.3-IMPLEMENTATION-SUMMARY.md)

Create function to generate rollback script:
```python
def generate_rollback_script(swaps: List[SwapProposal], output_path: str) -> Optional[str]:
    """Generate script that reverses all proposed changes.
    
    Args:
        swaps: Original swap proposals
        output_path: Path for rollback script (typically *_rollback.sh)
    
    Returns:
        Path to generated rollback script, or None if generation failed
    """
    # Create reverse swaps (swap old and new)
    reverse_swaps = [
        SwapProposal(
            pgid=swap.pgid,
            old_primary=swap.new_primary,  # Reversed
            new_primary=swap.old_primary,   # Reversed
            score_improvement=0.0
        )
        for swap in swaps
    ]
    
    # Generate rollback script with comprehensive warnings
    rollback_path = output_path.replace('.sh', '_rollback.sh')
    # ... (132 lines of implementation with health checks, warnings, etc.)
    return rollback_path
```

Update [`cli.py`](../src/ceph_primary_balancer/cli.py) to call it:
```python
# After generating main script:
rollback_path = script_generator.generate_rollback_script(swaps, args.output)
if rollback_path:
    print(f"Rollback script: {rollback_path}")
```

**Test:** ✅ Verified rollback script reverses all operations (test suite passing)

---

### Task 1.4: Implement Batch Execution ✅ COMPLETE
**File:** [`src/ceph_primary_balancer/script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
**Effort:** 60 lines → **Actual:** 71 lines (script_generator.py + cli.py)
**Priority:** MEDIUM
**Status:** ✅ **COMPLETED in v0.7.0**

Add batch execution with configurable batch size:
```python
def generate_script(swaps: List[SwapProposal], output_path: str, batch_size: int = 50):
    """Generate script with batched commands.
    
    Args:
        swaps: Swap proposals to execute
        output_path: Output script path
        batch_size: Number of commands per batch (default: 50)
    """
    # ... existing header code ...
    
    # Add batch execution function
    script_content += f'''
BATCH_SIZE={batch_size}

apply_batch() {{
    local batch_num=$1
    local batch_start=$2
    local batch_end=$3
    
    echo ""
    echo "=== Batch $batch_num (commands $batch_start-$batch_end) ==="
    
    # Commands will be inserted here per batch
}}
'''
    
    # Group swaps into batches
    for i in range(0, len(swaps), batch_size):
        batch = swaps[i:i+batch_size]
        batch_num = i // batch_size + 1
        script_content += f'\n# Batch {batch_num}\n'
        for swap in batch:
            script_content += f'apply_mapping "{swap.pgid}" {swap.new_primary}\n'
    
    # ... existing footer code ...
```

**Test:** Verify script groups commands into batches

---

### Task 1.5: Unit Tests for Core Modules ✅ COMPLETE
**Files:** `tests/test_optimizer.py`, `tests/test_analyzer.py`, `tests/test_scorer.py`
**Effort:** 300 lines → **Actual:** 820 lines
**Priority:** HIGH
**Status:** ✅ **COMPLETED in v0.8.0**

**Implementation Results:**

**tests/test_optimizer.py** (~250 lines, 15 tests):
- ✅ `test_calculate_variance()` - Variance calculation correctness
- ✅ `test_simulate_swap_score()` - Score improvement calculation
- ✅ `test_apply_swap()` - State mutation correctness
- ✅ `test_find_best_swap()` - Best swap selection logic
- ✅ `test_optimize_primaries()` - Full optimization workflow
- ✅ Edge cases: empty clusters, single OSD, no valid swaps

**tests/test_analyzer.py** (~300 lines, 26 tests):
- ✅ `test_calculate_statistics()` - Mean, std dev, CV calculations
- ✅ `test_identify_donors()` - Donor OSD identification
- ✅ `test_identify_receivers()` - Receiver OSD identification
- ✅ `test_calculate_pool_statistics()` - Per-pool statistics
- ✅ Edge cases: zero primaries, identical counts, empty data

**tests/test_scorer.py** (~270 lines, 16 tests):
- ✅ `test_scorer_initialization()` - Weight validation
- ✅ `test_calculate_osd_variance()` - OSD-level variance
- ✅ `test_calculate_host_variance()` - Host-level variance
- ✅ `test_calculate_pool_variance()` - Pool-level variance
- ✅ `test_calculate_score()` - Composite scoring
- ✅ `test_get_multi_level_statistics()` - Multi-dimensional stats

**Test Results:**
- **57 tests total** across 3 test files
- **100% pass rate** - all tests passing
- **Coverage achieved:** ≥95% for all modules (exceeded target of 85%)
- **Runtime:** ~0.004s for full test suite
- All edge cases validated and passing

---

## Priority 2: Configuration & Advanced Options

### Task 2.1: Create Configuration Module
**File:** `src/ceph_primary_balancer/config.py` (NEW)  
**Effort:** 80 lines  
**Priority:** MEDIUM

```python
"""Configuration file support for Ceph Primary PG Balancer."""

import json
from typing import Dict, Any, Optional

class Config:
    """Load and manage configuration from JSON file."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize with optional config file path."""
        self.settings = self._default_settings()
        if config_path:
            self.load_file(config_path)
    
    def _default_settings(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'optimization': {
                'target_cv': 0.10,
                'max_changes': None,
                'max_iterations': 10000
            },
            'scoring': {
                'weights': {
                    'osd': 0.5,
                    'host': 0.3,
                    'pool': 0.2
                }
            },
            'output': {
                'directory': './',
                'json_export': False,
                'markdown_report': False,
                'script_name': 'rebalance_primaries.sh'
            },
            'script': {
                'batch_size': 50,
                'health_check': True,
                'generate_rollback': True,
                'organized_by_pool': False
            }
        }
    
    def load_file(self, path: str):
        """Load configuration from JSON file."""
        with open(path, 'r') as f:
            user_settings = json.load(f)
        self._merge_settings(user_settings)
    
    def _merge_settings(self, user_settings: Dict[str, Any]):
        """Merge user settings with defaults (user takes precedence)."""
        # Deep merge logic
    
    def get(self, key: str, default=None):
        """Get config value using dot notation (e.g., 'optimization.target_cv')."""
        keys = key.split('.')
        value = self.settings
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
```

**Test:** Unit tests for config loading and merging

---

### Task 2.2: Add `--config` CLI Option
**File:** [`src/ceph_primary_balancer/cli.py`](../src/ceph_primary_balancer/cli.py)  
**Effort:** 25 lines  
**Priority:** MEDIUM

```python
from .config import Config

parser.add_argument(
    '--config',
    type=str,
    default=None,
    help='Load configuration from JSON file'
)

# After argument parsing:
config = Config(args.config) if args.config else Config()

# Use config values as defaults, CLI args override:
target_cv = args.target_cv if args.target_cv != 0.10 else config.get('optimization.target_cv', 0.10)
max_changes = args.max_changes or config.get('optimization.max_changes')
```

**Test:** Verify config file values are used, CLI args override

---

### Task 2.3: Implement `--output-dir` Option
**File:** [`src/ceph_primary_balancer/cli.py`](../src/ceph_primary_balancer/cli.py)  
**Effort:** 30 lines  
**Priority:** MEDIUM

```python
import os
from datetime import datetime

parser.add_argument(
    '--output-dir',
    type=str,
    default=None,
    help='Output directory for all generated files'
)

# After argument parsing:
if args.output_dir:
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Update output paths
    if not args.output or args.output == './rebalance_primaries.sh':
        args.output = os.path.join(args.output_dir, f'rebalance_{timestamp}.sh')
    
    if args.json_output:
        if not os.path.dirname(args.json_output):
            args.json_output = os.path.join(args.output_dir, f'analysis_{timestamp}.json')
    
    if args.report_output:
        if not os.path.dirname(args.report_output):
            args.report_output = os.path.join(args.output_dir, f'report_{timestamp}.md')
    
    print(f"Output directory: {args.output_dir}")
```

**Test:** Verify all files created in specified directory

---

### Task 2.4: Add `--verbose` and `--quiet` Modes
**File:** [`src/ceph_primary_balancer/cli.py`](../src/ceph_primary_balancer/cli.py)  
**Effort:** 20 lines  
**Priority:** LOW

```python
parser.add_argument('--verbose', action='store_true', help='Verbose output')
parser.add_argument('--quiet', action='store_true', help='Minimal output')

# Validate
if args.verbose and args.quiet:
    print("Error: Cannot specify both --verbose and --quiet")
    sys.exit(1)

# Use throughout:
def vprint(msg):
    """Print if verbose mode enabled."""
    if args.verbose and not args.quiet:
        print(msg)

def qprint(msg):
    """Print unless quiet mode enabled."""
    if not args.quiet:
        print(msg)
```

**Test:** Verify output levels work correctly

---

### Task 2.5: Pool-Organized Batching
**File:** [`src/ceph_primary_balancer/script_generator.py`](../src/ceph_primary_balancer/script_generator.py)  
**Effort:** 25 lines  
**Priority:** LOW

```python
def generate_script_with_pool_batching(
    swaps: List[SwapProposal],
    state: ClusterState,
    output_path: str
):
    """Generate script with commands organized by pool."""
    # Group swaps by pool
    swaps_by_pool = {}
    for swap in swaps:
        pg = state.pgs[swap.pgid]
        pool_id = pg.pool_id
        if pool_id not in swaps_by_pool:
            swaps_by_pool[pool_id] = []
        swaps_by_pool[pool_id].append(swap)
    
    # Generate script with pool sections
    for pool_id, pool_swaps in swaps_by_pool.items():
        pool_name = state.pools[pool_id].pool_name
        script_content += f'\n# Pool {pool_id}: {pool_name} ({len(pool_swaps)} changes)\n'
        # ... add commands ...
```

**Test:** Verify script groups by pool

---

## Priority 3: Documentation & Polish

### Task 3.1: Update README.md
**File:** [`README.md`](../README.md)  
**Effort:** ~100 lines updates  
**Priority:** HIGH

**Changes:**
1. Fix broken link to `docs/DESIGN.md` (doesn't exist) → link to `docs/technical-specification.md`
2. Update Quick Start with proper commands:
   ```bash
   # Old (MVP):
   python ceph_primary_balancer.py --dry-run
   
   # New (v1.0):
   python -m ceph_primary_balancer.cli --dry-run
   # Or use entry point if installed:
   ceph-primary-balancer --dry-run
   ```
3. Add Phase 1-4 feature highlights
4. Update feature list with v1.0 capabilities

---

### Task 3.2: Update USAGE.md
**File:** [`docs/USAGE.md`](../docs/USAGE.md)  
**Effort:** ~200 lines  
**Priority:** HIGH

**Add sections:**
1. **Phase 1: Host-Level Balancing**
   ```bash
   # Prioritize host balance
   ceph-primary-balancer --weight-host 0.5 --weight-osd 0.3 --weight-pool 0.2
   ```

2. **Phase 2: Pool-Level Balancing**
   ```bash
   # Balance specific pool only
   ceph-primary-balancer --pool 1
   ```

3. **Phase 3: Reporting**
   ```bash
   # Generate all outputs
   ceph-primary-balancer --format all \
       --json-output analysis.json \
       --report-output report.md
   ```

4. **Phase 4: Advanced Options**
   ```bash
   # Use configuration file
   ceph-primary-balancer --config config.json
   
   # Limit changes
   ceph-primary-balancer --max-changes 100
   
   # Organize outputs
   ceph-primary-balancer --output-dir ./output-$(date +%Y%m%d)
   ```

5. **Complete Workflow Example**

---

### Task 3.3: Create ADVANCED-USAGE.md
**File:** `docs/ADVANCED-USAGE.md` (NEW)  
**Effort:** ~150 lines  
**Priority:** MEDIUM

**Sections:**
1. Configuration File Deep Dive
2. Weight Tuning Strategies
3. Batch Execution Best Practices
4. Rollback Procedures
5. Performance Optimization
6. Troubleshooting Production Issues

---

### Task 3.4: Create CONFIGURATION.md
**File:** `docs/CONFIGURATION.md` (NEW)  
**Effort:** ~100 lines  
**Priority:** MEDIUM

**Content:**
1. Complete configuration reference
2. JSON schema
3. Example configurations:
   - OSD-focused
   - Host-focused
   - Balanced (default)
   - Large cluster optimized
4. CLI vs config file precedence

---

### Task 3.5: Update CHANGELOG.md
**File:** [`CHANGELOG.md`](../CHANGELOG.md)  
**Effort:** ~50 lines  
**Priority:** MEDIUM

Add v1.0.0 entry with all Phase 4 features.

---

## Testing Checklist

### Unit Tests (New)
- [ ] `tests/test_models.py` - Data classes
- [ ] `tests/test_collector.py` - Data collection with mocks
- [ ] `tests/test_analyzer.py` - Statistics calculations
- [ ] `tests/test_optimizer.py` - Optimization logic
- [ ] `tests/test_script_generator.py` - Script generation
- [ ] `tests/test_config.py` - Configuration loading

### Integration Tests (Existing + Updates)
- [x] Phase 1 integration tests (existing)
- [x] Phase 2 integration tests (existing)
- [x] Phase 3 integration tests (existing)
- [ ] Phase 4 integration test (new features)

### Manual Testing
- [ ] End-to-end workflow with real cluster data
- [ ] Configuration file loading
- [ ] All CLI options work
- [ ] Script execution (dry-run mode)
- [ ] Rollback script functionality
- [ ] Output organization with `--output-dir`

---

## Definition of Done

### Code Complete
- [ ] All Priority 1 tasks implemented
- [ ] All Priority 2 tasks implemented
- [ ] All Priority 3 tasks implemented
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Test coverage ≥80% overall
- [ ] Test coverage ≥90% for critical modules
- [ ] No pylint errors

### Documentation Complete
- [ ] README.md updated
- [ ] USAGE.md updated with Phase 1-4
- [ ] ADVANCED-USAGE.md created
- [ ] CONFIGURATION.md created
- [ ] CHANGELOG.md updated with v1.0.0
- [ ] All code has docstrings
- [ ] All broken links fixed

### Release Ready
- [ ] Version bumped to 1.0.0 in `__init__.py`
- [ ] All success criteria from gap analysis met
- [ ] Performance benchmarks pass
- [ ] Backward compatibility verified
- [ ] Zero new external dependencies

---

## Quick Reference: File Change Summary

| File | Changes | Lines | Priority |
|------|---------|-------|----------|
| [`cli.py`](../src/ceph_primary_balancer/cli.py) | Add CLI options, config integration | ~80 | HIGH |
| [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py) | Health checks, rollback, batching | ~150 | HIGH |
| `config.py` (NEW) | Configuration file support | ~80 | MEDIUM |
| `tests/test_*.py` (NEW) | Comprehensive unit tests | ~500 | HIGH |
| [`README.md`](../README.md) | Update with v1.0 features | ~100 | HIGH |
| [`docs/USAGE.md`](../docs/USAGE.md) | Complete usage guide | ~200 | HIGH |
| `docs/ADVANCED-USAGE.md` (NEW) | Advanced features guide | ~150 | MEDIUM |
| `docs/CONFIGURATION.md` (NEW) | Config file reference | ~100 | MEDIUM |
| [`CHANGELOG.md`](../CHANGELOG.md) | v1.0.0 release notes | ~50 | MEDIUM |

**Total:** ~1,410 lines (880 code + 530 docs)

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize tasks** based on project timeline
3. **Implement Priority 1 tasks** first (production safety)
4. **Write unit tests** alongside implementation
5. **Update documentation** as features are completed
6. **Test thoroughly** before release
7. **Release v1.0.0** when all criteria met

---

See [`phase4-gap-analysis.md`](phase4-gap-analysis.md) for detailed analysis and context.
