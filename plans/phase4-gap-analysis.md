# Phase 4 Gap Analysis & Implementation Plan

**Date:** 2026-02-03  
**Current Version:** 0.4.0 (Phase 3 Complete)  
**Target Version:** 1.0.0 (Phase 4 Complete)  
**Project Completion:** 85% → 100%

---

## Executive Summary

This document analyzes the gaps between the current implementation (v0.4.0) and the complete specification outlined in [`completion-roadmap.md`](completion-roadmap.md) and [`technical-specification.md`](../docs/technical-specification.md). Phase 3 is fully complete with all reporting and JSON export features implemented and tested. Phase 4 represents the final 15% of work to reach production readiness.

### Current State ✅

**Completed Features:**
- ✅ OSD-level balancing (MVP, v0.1.0)
- ✅ Host-level balancing (Phase 1, v0.2.0)
- ✅ Pool-level balancing (Phase 2, v0.3.0)
- ✅ Three-dimensional scoring with configurable weights
- ✅ JSON export with schema versioning (Phase 3, v0.4.0)
- ✅ Enhanced terminal reporting with tables (Phase 3)
- ✅ Markdown report generation (Phase 3)
- ✅ Multi-format output (terminal/json/markdown/all)
- ✅ Integration tests for all phases

**Test Coverage:**
- 8 tests for Phase 1 (host balancing)
- Integration tests for Phases 1, 2, 3
- 12 tests for Phase 3 (export/reporting)
- Total: ~25 integration tests
- **Gap:** No unit tests for individual modules

---

## Gap Analysis

### 1. CLI Features (High Priority)

| Feature | Status | Spec Reference | Priority |
|---------|--------|----------------|----------|
| `--dry-run` | ✅ Implemented | tech-spec §6.3 | N/A |
| `--target-cv` | ✅ Implemented | tech-spec §6.3 | N/A |
| `--output` | ✅ Implemented | tech-spec §6.3 | N/A |
| `--weight-osd/host/pool` | ✅ Implemented | tech-spec §6.3 | N/A |
| `--pool` filter | ✅ Implemented | tech-spec §6.3 | N/A |
| `--json-output` | ✅ Implemented | roadmap Phase 3 | N/A |
| `--report-output` | ✅ Implemented | roadmap Phase 3 | N/A |
| `--format` | ✅ Implemented | roadmap Phase 3 | N/A |
| **`--max-changes N`** | ❌ **Missing** | tech-spec §6.3, roadmap P4-T2 | **HIGH** |
| **`--output-dir DIR`** | ❌ **Missing** | tech-spec §6.3, roadmap P4-T3 | **MEDIUM** |
| **`--config FILE`** | ❌ **Missing** | tech-spec §6.3, roadmap P4-T4 | **MEDIUM** |
| **`--verbose`** | ❌ **Missing** | roadmap P4-T5 | **LOW** |
| **`--quiet`** | ❌ **Missing** | roadmap P4-T5 | **LOW** |

**Impact:** 3 high/medium priority CLI features missing (~80 lines of code)

---

### 2. Script Generation Features (High Priority)

Current [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py) (~115 lines) is basic:

| Feature | Status | Spec Reference | Lines Needed |
|---------|--------|----------------|--------------|
| Basic script generation | ✅ Implemented | MVP | N/A |
| Confirmation prompt | ✅ Implemented | MVP | N/A |
| Progress tracking | ✅ Implemented | MVP | N/A |
| Error counting | ✅ Implemented | MVP | N/A |
| **Pre-execution health checks** | ❌ **Missing** | tech-spec §5.3, roadmap P4-T6 | ~40 lines |
| **Batch execution** | ❌ **Missing** | tech-spec §5.3, roadmap P4-T7 | ~50 lines |
| **Rollback script generation** | ❌ **Missing** | tech-spec §5.3, roadmap P4-T8 | ~40 lines |
| **Pool-organized batching** | ❌ **Missing** | roadmap P4-T9 | ~20 lines |

**Impact:** Critical production safety features missing (~150 lines of code)

**Missing Features Detail:**

1. **Health Checks** - Script should verify cluster health before proceeding:
   ```bash
   HEALTH=$(ceph health 2>/dev/null)
   if [[ ! "$HEALTH" =~ ^HEALTH_OK ]] && [[ ! "$HEALTH" =~ ^HEALTH_WARN ]]; then
       echo "ERROR: Cluster health is $HEALTH"
       exit 1
   fi
   ```

2. **Batch Execution** - Group commands into batches for progress tracking:
   ```bash
   BATCH_SIZE=50
   apply_batch() {
       local batch_num=$1
       echo "=== Batch $batch_num ==="
       # Execute batch of commands
   }
   ```

3. **Rollback Script** - Automatically generate reverse operations:
   ```bash
   cat > rollback.sh << 'EOF'
   # Reverse all changes
   ceph osd pg-upmap-primary 1.a3 12  # Reverse of: 12 -> 45
   EOF
   ```

4. **Pool Organization** - Group commands by pool for better tracking

---

### 3. Configuration File Support (Medium Priority)

| Component | Status | Spec Reference | Lines Needed |
|-----------|--------|----------------|--------------|
| YAML/JSON parser | ❌ **Missing** | roadmap §4.4.3, P4-T1 | ~80 lines |
| Config validation | ❌ **Missing** | roadmap P4-T1 | ~20 lines |
| CLI integration | ❌ **Missing** | roadmap P4-T4 | ~15 lines |

**Impact:** Cannot load settings from file (~115 lines of code for new [`config.py`](../src/ceph_primary_balancer/config.py) module)

**Configuration File Format (from roadmap):**
```yaml
# ceph_primary_balancer.yaml
optimization:
  target_cv: 0.10
  max_changes: 500
  max_iterations: 10000

scoring:
  weights:
    osd: 0.5
    host: 0.3
    pool: 0.2

output:
  directory: "./balancer_output"
  json_export: true
  markdown_report: true
  script_name: "rebalance_{timestamp}.sh"

script:
  batch_size: 50
  health_check: true
  generate_rollback: true
  organized_by_pool: true
```

---

### 4. Test Coverage Gaps (High Priority)

Current testing is **integration-focused only**. Missing unit tests:

| Module | Current Tests | Missing Unit Tests | Priority |
|--------|---------------|-------------------|----------|
| [`models.py`](../src/ceph_primary_balancer/models.py) | 0 unit tests | Data class validation, properties | HIGH |
| [`collector.py`](../src/ceph_primary_balancer/collector.py) | 0 unit tests | Mock command execution, JSON parsing | HIGH |
| [`analyzer.py`](../src/ceph_primary_balancer/analyzer.py) | 0 unit tests | Statistics calculations, edge cases | HIGH |
| [`optimizer.py`](../src/ceph_primary_balancer/optimizer.py) | 0 unit tests | Swap finding, variance calculation | HIGH |
| [`scorer.py`](../src/ceph_primary_balancer/scorer.py) | 8 integration tests | Isolated scoring logic | MEDIUM |
| [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py) | 0 unit tests | Script generation, formatting | MEDIUM |
| [`exporter.py`](../src/ceph_primary_balancer/exporter.py) | 7 integration tests | Schema validation | LOW |
| [`reporter.py`](../src/ceph_primary_balancer/reporter.py) | 5 integration tests | Report formatting | LOW |
| [`cli.py`](../src/ceph_primary_balancer/cli.py) | 0 unit tests | Argument parsing, workflow | LOW |

**Impact:** Need ~500 lines of unit tests for comprehensive coverage

**Target Coverage (from roadmap):**
- Overall: ≥80%
- Critical modules (optimizer, scorer, analyzer): ≥90%

---

### 5. Documentation Gaps (Medium Priority)

| Document | Status | Issues | Priority |
|----------|--------|--------|----------|
| [`README.md`](../README.md) | ⚠️ Outdated | References non-existent `docs/DESIGN.md`, MVP-era commands | MEDIUM |
| [`USAGE.md`](../docs/USAGE.md) | ⚠️ Outdated | MVP-era only, missing Phase 1-3 features | HIGH |
| [`technical-specification.md`](../docs/technical-specification.md) | ✅ Complete | Up to date | N/A |
| [`INSTALLATION.md`](../docs/INSTALLATION.md) | ✅ Complete | Up to date | N/A |
| [`TROUBLESHOOTING.md`](../docs/TROUBLESHOOTING.md) | ✅ Complete | Up to date | N/A |
| **Advanced Usage Guide** | ❌ **Missing** | No examples for Phase 4 features | MEDIUM |
| **Configuration File Guide** | ❌ **Missing** | No config file documentation | MEDIUM |

**Impact:** Users cannot fully utilize Phase 1-3 features due to outdated docs

---

## Implementation Roadmap

### Phase 4A: Critical Production Features (Priority 1)

**Goal:** Add production safety and essential CLI features  
**Effort:** ~300 lines of code

#### Tasks

**4A.1: Implement `--max-changes` Option**
- **File:** [`cli.py`](../src/ceph_primary_balancer/cli.py)
- **Lines:** ~20
- **Description:** Limit number of swaps to prevent excessive changes
- **Implementation:**
  ```python
  parser.add_argument('--max-changes', type=int, default=None,
                     help='Maximum number of primary reassignments')
  
  # In optimization section:
  if args.max_changes and len(swaps) > args.max_changes:
      swaps = swaps[:args.max_changes]
      print(f"Limited to {args.max_changes} changes (optimization found {len(all_swaps)})")
  ```

**4A.2: Enhanced Script Generation with Health Checks**
- **File:** [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
- **Lines:** ~40
- **Description:** Add pre-execution cluster health verification
- **Implementation:** Add health check section before commands

**4A.3: Rollback Script Generation**
- **File:** [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
- **Lines:** ~40
- **Description:** Auto-generate script to reverse all changes
- **Implementation:**
  ```python
  def generate_rollback_script(swaps: List[SwapProposal], output_path: str):
      """Generate script that reverses all proposed changes."""
      rollback_swaps = [
          SwapProposal(s.pgid, s.new_primary, s.old_primary, 0)
          for s in swaps
      ]
      rollback_path = output_path.replace('.sh', '_rollback.sh')
      generate_script(rollback_swaps, rollback_path)
  ```

**4A.4: Batch Execution Support**
- **File:** [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
- **Lines:** ~50
- **Description:** Group commands into configurable batches
- **Implementation:** Add `apply_batch()` function with batch size parameter

**4A.5: Critical Unit Tests**
- **Files:** `tests/test_optimizer.py`, `tests/test_analyzer.py`, `tests/test_collector.py`
- **Lines:** ~300
- **Description:** Unit tests for core optimization logic
- **Coverage Target:** ≥85% for critical modules

---

### Phase 4B: Configuration & Advanced CLI (Priority 2)

**Goal:** Add configuration file support and remaining CLI options  
**Effort:** ~200 lines of code

#### Tasks

**4B.1: Configuration File Parser Module**
- **File:** [`src/ceph_primary_balancer/config.py`](../src/ceph_primary_balancer/config.py) (NEW)
- **Lines:** ~80
- **Description:** Parse YAML/JSON configuration files
- **Dependencies:** Use stdlib only (no external dependencies)
- **Implementation:**
  ```python
  import json
  from typing import Dict, Any, Optional
  
  class Config:
      def __init__(self, config_path: Optional[str] = None):
          self.settings = self._load_defaults()
          if config_path:
              self._load_file(config_path)
      
      def _load_defaults(self) -> Dict[str, Any]:
          return {
              'optimization': {'target_cv': 0.10, 'max_changes': None},
              'scoring': {'weights': {'osd': 0.5, 'host': 0.3, 'pool': 0.2}},
              'output': {'directory': './', 'json_export': False},
              'script': {'batch_size': 50, 'health_check': True}
          }
      
      def _load_file(self, path: str):
          # JSON only for v1.0 (YAML requires external dependency)
          with open(path) as f:
              user_settings = json.load(f)
          self._merge_settings(user_settings)
  ```

**4B.2: Integrate Config with CLI**
- **File:** [`cli.py`](../src/ceph_primary_balancer/cli.py)
- **Lines:** ~15
- **Description:** Add `--config` option, merge with CLI args
- **Implementation:**
  ```python
  parser.add_argument('--config', type=str, help='Load configuration from JSON file')
  
  # After arg parsing:
  if args.config:
      config = Config(args.config)
      # CLI args override config file
      args.target_cv = args.target_cv or config.get('optimization.target_cv')
  ```

**4B.3: Implement `--output-dir` Option**
- **File:** [`cli.py`](../src/ceph_primary_balancer/cli.py)
- **Lines:** ~25
- **Description:** Organize outputs in directory structure
- **Implementation:**
  ```python
  parser.add_argument('--output-dir', help='Output directory for all files')
  
  if args.output_dir:
      os.makedirs(args.output_dir, exist_ok=True)
      timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
      script_path = os.path.join(args.output_dir, f'rebalance_{timestamp}.sh')
      json_path = os.path.join(args.output_dir, f'analysis_{timestamp}.json')
      report_path = os.path.join(args.output_dir, f'report_{timestamp}.md')
  ```

**4B.4: Implement `--verbose` and `--quiet` Modes**
- **File:** [`cli.py`](../src/ceph_primary_balancer/cli.py)
- **Lines:** ~20
- **Description:** Control output verbosity
- **Implementation:**
  ```python
  parser.add_argument('--verbose', action='store_true', help='Verbose output')
  parser.add_argument('--quiet', action='store_true', help='Minimal output')
  
  def vprint(msg):
      if args.verbose and not args.quiet:
          print(msg)
  ```

**4B.5: Pool-Organized Batching**
- **File:** [`script_generator.py`](../src/ceph_primary_balancer/script_generator.py)
- **Lines:** ~20
- **Description:** Organize script commands by pool
- **Implementation:** Group swaps by pool_id before generating script

---

### Phase 4C: Testing & Documentation (Priority 3)

**Goal:** Complete test suite and update all documentation  
**Effort:** ~500 lines (tests) + documentation updates

#### Tasks

**4C.1: Comprehensive Unit Test Suite**
- **Files:** Multiple new test files
- **Lines:** ~500
- **Description:** Unit tests for all untested modules
- **Breakdown:**
  - `tests/test_models.py`: ~100 lines
  - `tests/test_collector.py`: ~150 lines
  - `tests/test_analyzer.py`: ~150 lines
  - `tests/test_script_generator.py`: ~100 lines

**4C.2: Update README.md**
- **File:** [`README.md`](../README.md)
- **Description:** Update with v1.0 features, fix broken links
- **Changes:**
  - Update Quick Start for v1.0
  - Fix reference to non-existent `docs/DESIGN.md`
  - Add Phase 1-4 feature highlights
  - Update usage examples

**4C.3: Update USAGE.md**
- **File:** [`docs/USAGE.md`](../docs/USAGE.md)
- **Description:** Complete usage guide with all Phase 1-4 features
- **Sections:**
  - Phase 1: Host-level balancing examples
  - Phase 2: Pool-level balancing examples
  - Phase 3: JSON export and reporting
  - Phase 4: Configuration files, advanced options
  - Real-world workflows

**4C.4: Create Advanced Usage Guide**
- **File:** `docs/ADVANCED-USAGE.md` (NEW)
- **Description:** Deep dive into advanced features
- **Sections:**
  - Configuration file reference
  - Weight tuning strategies
  - Batch execution workflows
  - Rollback procedures
  - Performance optimization tips

**4C.5: Create Configuration File Guide**
- **File:** `docs/CONFIGURATION.md` (NEW)
- **Description:** Complete configuration file reference
- **Content:**
  - All configuration options
  - Example configurations for different scenarios
  - CLI vs config file precedence
  - JSON schema reference

**4C.6: Update CHANGELOG.md**
- **File:** [`CHANGELOG.md`](../CHANGELOG.md)
- **Description:** Add v1.0.0 / Phase 4 entry
- **Content:** All Phase 4 features and changes

---

## Effort Estimation

### Code Changes

| Component | New Lines | Modified Lines | Total Effort |
|-----------|-----------|----------------|--------------|
| CLI enhancements | ~80 | ~40 | Small |
| Script generation | ~150 | ~30 | Medium |
| Config module (new) | ~80 | 0 | Small-Medium |
| Unit tests (new) | ~500 | 0 | Large |
| **Total Production Code** | **~310** | **~70** | **~380 lines** |
| **Total Test Code** | **~500** | 0 | **~500 lines** |

### Documentation Changes

| Document | Effort | Priority |
|----------|--------|----------|
| README.md | Small | High |
| USAGE.md | Medium | High |
| ADVANCED-USAGE.md (new) | Medium | Medium |
| CONFIGURATION.md (new) | Small | Medium |
| CHANGELOG.md | Small | High |
| **Total Documentation** | **~400 lines** | |

### Total Phase 4 Effort

- **Production Code:** ~380 lines (new + modified)
- **Test Code:** ~500 lines
- **Documentation:** ~400 lines
- **Total:** ~1,280 lines

---

## Success Criteria for v1.0.0 Release

### Functional Requirements

- [x] Phase 1 features complete (host-level balancing)
- [x] Phase 2 features complete (pool-level balancing)
- [x] Phase 3 features complete (JSON export, reporting)
- [ ] **`--max-changes` limits swap count**
- [ ] **`--output-dir` organizes outputs**
- [ ] **`--config` loads JSON configuration file**
- [ ] **`--verbose/--quiet` control output**
- [ ] **Script includes health checks**
- [ ] **Script generates rollback script**
- [ ] **Script supports batch execution**
- [ ] **Pool-organized batching works**

### Quality Requirements

- [x] Phase 1-3 integration tests pass
- [ ] **≥80% overall test coverage**
- [ ] **≥90% coverage for optimizer, scorer, analyzer**
- [ ] **All unit tests pass**
- [ ] **No pylint errors**
- [ ] **Type hints on all public APIs**

### Documentation Requirements

- [ ] **README.md updated and accurate**
- [ ] **USAGE.md includes Phase 1-4 features**
- [ ] **ADVANCED-USAGE.md created**
- [ ] **CONFIGURATION.md created**
- [ ] **CHANGELOG.md has v1.0.0 entry**
- [ ] **All broken links fixed**

### Non-Functional Requirements

- [ ] **Performance: <10s for 10k PGs (Phase 4 features active)**
- [ ] **Memory: <1GB for 100k PGs**
- [ ] **Zero new external dependencies**
- [ ] **Backward compatible with v0.4.0**

---

## Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Config parsing breaks existing workflows | Low | High | Config is optional, CLI args work standalone |
| Batch execution adds complexity | Medium | Medium | Keep batch size configurable, default=1 (no batching) |
| Test suite maintenance burden | High | Low | Focus on critical paths, accept 80% coverage |
| Performance regression | Low | Medium | Profile before/after, optimize hot paths |

### Project Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Scope creep beyond Phase 4 | Medium | Medium | Strict adherence to roadmap, defer features to v1.1 |
| Documentation lag | High | Low | Update docs alongside code, not after |
| Insufficient testing of edge cases | Medium | Medium | Focus on unit tests for edge cases |

---

## Deferred to v1.1+ (Out of Scope)

Features explicitly deferred from roadmap:

- [ ] Prometheus/Grafana metrics integration
- [ ] Web UI for analysis
- [ ] Real-time incremental rebalancing
- [ ] CRUSH topology awareness (rack, datacenter)
- [ ] Weight-proportional balancing
- [ ] Simulated annealing optimization
- [ ] Daemon mode
- [ ] Historical trend analysis
- [ ] YAML configuration support (requires external dependency)

---

## Recommended Implementation Order

### Sprint 1: Critical Production Safety (Week 1)
1. Implement `--max-changes` (4A.1)
2. Add health checks to scripts (4A.2)
3. Add rollback script generation (4A.3)
4. Write unit tests for optimizer (4A.5)

### Sprint 2: Advanced Features (Week 2)
1. Implement batch execution (4A.4)
2. Create config.py module (4B.1)
3. Add `--config` CLI option (4B.2)
4. Implement `--output-dir` (4B.3)
5. Write unit tests for analyzer and collector (4A.5)

### Sprint 3: Testing & Polish (Week 3)
1. Complete unit test suite (4C.1)
2. Implement `--verbose/--quiet` (4B.4)
3. Add pool-organized batching (4B.5)
4. Update README.md (4C.2)
5. Update USAGE.md (4C.3)

### Sprint 4: Documentation & Release (Week 4)
1. Create ADVANCED-USAGE.md (4C.4)
2. Create CONFIGURATION.md (4C.5)
3. Update CHANGELOG.md (4C.6)
4. Final testing and bug fixes
5. Release v1.0.0

---

## Conclusion

Phase 4 represents the final 15% of work to complete the Ceph Primary PG Balancer project. The implementation is well-structured and ~85% complete with solid foundations from Phases 1-3. The remaining work focuses on:

1. **Production safety** (health checks, rollbacks, limits)
2. **Usability** (configuration files, output organization)
3. **Quality** (comprehensive unit tests)
4. **Documentation** (complete user guides)

**Estimated effort:** 4 weeks at current pace  
**Code to write:** ~880 lines (production + tests)  
**Documentation:** ~400 lines

All features align with the original [`technical-specification.md`](../docs/technical-specification.md) and [`completion-roadmap.md`](completion-roadmap.md). No scope creep or architectural changes needed.

---

## References

- [Completion Roadmap](completion-roadmap.md)
- [Technical Specification](../docs/technical-specification.md)
- [Phase 1 Summary](../docs/PHASE1-SUMMARY.md)
- [Phase 3 Summary](../docs/PHASE3-SUMMARY.md)
- [CHANGELOG](../CHANGELOG.md)
