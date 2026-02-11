# Release Notes: v1.5.0 - Offline Mode for Air-Gapped Environments

**Release Date:** February 11, 2026  
**Focus:** Air-gapped environment support with complete export/analyze/execute workflow

---

## 🔒 What's New in v1.5.0

### Offline Mode - Complete Air-Gap Support

v1.5.0 introduces **Offline Mode**, enabling the Ceph Primary PG Balancer to work in air-gapped and security-restricted environments where direct cluster access is unavailable or prohibited.

**Key Innovation:** Export cluster data once, analyze anywhere, execute safely.

```bash
# On Ceph cluster - Export
./scripts/ceph-export-cluster-data.sh

# On isolated workstation - Analyze (no cluster access needed!)
python3 -m ceph_primary_balancer.cli --from-file export.tar.gz --output rebalance.sh

# Back on cluster - Execute
./rebalance.sh
```

---

## 🎯 Target Use Cases

| Use Case | Benefit |
|----------|---------|
| **Air-Gapped Security** | Maintain network isolation, comply with security policies |
| **Analysis Workstations** | Optimize without cluster credentials, test strategies offline |
| **Vendor Support** | Share cluster state for troubleshooting without access grants |
| **Historical Analysis** | Archive and analyze cluster evolution over time |

---

## ✨ Key Features

### 1. One-Command Export

New bash script captures all required cluster data:

```bash
./scripts/ceph-export-cluster-data.sh
```

**What it exports:**
- PG placement data (pg_dump.json)
- Cluster topology (osd_tree.json)  
- Pool configuration (pool_list.json)
- Export metadata with timestamps

**Output:** Compressed `.tar.gz` archive (~1 MB typical)

### 2. Full CLI Compatibility

All features work in offline mode:

```bash
# Configuration files
--from-file export.tar.gz --config balanced.json

# Dynamic weights (v1.3.0)
--from-file export.tar.gz --dynamic-weights

# Advanced algorithms (v1.4.0)
--from-file export.tar.gz --algorithm simulated_annealing

# All safety features
--from-file export.tar.gz --max-changes 100 --batch-size 25
```

### 3. Intelligent Safety Features

- **Export age warnings:** Automatically alerts if data >7 days old
- **Manual health verification:** Required confirmation before script execution
- **Offline mode indicators:** Clear warnings in generated scripts
- **Full rollback support:** Always generated, works identically to live mode

### 4. Zero Live Mode Impact

- Offline module only loads when `--from-file` is used
- No performance overhead for standard operations
- Completely backward compatible

---

## 📊 Implementation Details

### New Components

| Component | Lines | Purpose |
|-----------|-------|---------|
| [`offline.py`](src/ceph_primary_balancer/offline.py) | ~200 | Archive handling, validation, parsing |
| [`ceph-export-cluster-data.sh`](scripts/ceph-export-cluster-data.sh) | ~100 | Export script for cluster data collection |
| [`OFFLINE-MODE.md`](docs/OFFLINE-MODE.md) | ~500 | Comprehensive documentation |
| Unit tests | ~250 | 21 tests for offline module |
| Integration tests | ~150 | 9 end-to-end workflow tests |

### Modified Components

- **CLI:** Added `--from-file` argument, offline detection, metadata display
- **Collector:** Modified `build_cluster_state()` to support offline loading
- **Script Generator:** Added offline warnings, manual health verification

### Test Coverage

- **30 new tests** (21 unit + 9 integration)
- **All passing** (184 total tests now)
- **>90% coverage** for offline functionality

---

## 🚀 Getting Started

### For Air-Gapped Environments

**Step 1: Export (on cluster)**
```bash
cd /path/to/ceph_primary_balancer
./scripts/ceph-export-cluster-data.sh
# Output: ceph-cluster-export-20260211_093022.tar.gz (892K)
```

**Step 2: Transfer**
```bash
# USB, secure file transfer, or approved method
cp ceph-cluster-export-*.tar.gz /media/usb/
```

**Step 3: Analyze (offline system)**
```bash
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_093022.tar.gz \
  --output rebalance.sh \
  --max-changes 100 \
  --config balanced.json
```

**Step 4: Execute (back on cluster)**
```bash
chmod +x rebalance.sh
./rebalance.sh
# Includes manual health verification prompt
```

### Quick Example

```bash
# Traditional live mode (unchanged)
python3 -m ceph_primary_balancer.cli --dry-run

# NEW: Offline mode
python3 -m ceph_primary_balancer.cli \
  --from-file cluster-export.tar.gz \
  --dry-run
```

---

## 📚 Documentation

### New Documentation

- **[OFFLINE-MODE.md](docs/OFFLINE-MODE.md)** - Comprehensive 500+ line guide
  - Complete workflow with examples
  - Export process details
  - Analysis options
  - Safety features and limitations
  - Best practices
  - Troubleshooting guide

### Updated Documentation

- **[USAGE.md](docs/USAGE.md)** - Added offline mode section
- **[README.md](README.md)** - Updated with offline features
- **[CHANGELOG.md](CHANGELOG.md)** - Detailed v1.5.0 entry

---

## 🔄 Upgrade Path

### From v1.4.0 to v1.5.0

**No breaking changes!** v1.5.0 is fully backward compatible.

```bash
# Update code
git pull origin main

# Existing usage works identically
python3 -m ceph_primary_balancer.cli --dry-run  # No changes

# New offline mode is optional
python3 -m ceph_primary_balancer.cli --from-file export.tar.gz  # NEW!
```

**What changes:**
- ✅ New `--from-file` CLI argument (optional)
- ✅ New export script in `scripts/` directory
- ✅ New offline module (auto-loaded when needed)

**What stays the same:**
- ✅ All existing CLI arguments and behavior
- ✅ Live mode performance (zero overhead)
- ✅ Configuration files
- ✅ All optimization algorithms

---

## ⚠️ Important Notes

### Export Data Freshness

Exports capture a point-in-time snapshot. The CLI warns about age:

- **< 1 day:** ✅ No warning
- **1-7 days:** ⚠️ Warning displayed
- **> 7 days:** 🚨 Strong warning + confirmation required

**Best Practice:** Keep exports fresh (<24 hours) for production use.

### Manual Health Verification

Offline mode **cannot** perform automatic health checks. Generated scripts require manual verification:

```bash
⚠️  OFFLINE MODE: Manual health verification required

Please verify:
  1. Run: ceph health
  2. Run: ceph -s  
  3. Verify OSDs match export
  4. Verify PGs are active+clean

Cluster is healthy and matches export? [y/N]
```

### Security Considerations

- Exports contain topology (OSD IDs, hosts) but **no actual data**
- Protect exports according to your security policy
- Use encrypted transfer if required
- Keep audit trail for compliance

---

## 🎓 Examples

### Example 1: First-Time Offline Use

```bash
# Export on cluster
./scripts/ceph-export-cluster-data.sh
# Created: ceph-cluster-export-20260211_143022.tar.gz

# Transfer to laptop (no Ceph access)
scp export.tar.gz analyst@laptop:~/

# Analyze on laptop
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_143022.tar.gz \
  --dry-run \
  --verbose

# Generate scripts
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_143022.tar.gz \
  --output rebalance.sh \
  --max-changes 100

# Transfer back and execute
scp rebalance*.sh admin@cluster:~/
ssh admin@cluster './rebalance.sh'
```

### Example 2: Vendor Support

```bash
# Customer exports cluster state
./scripts/ceph-export-cluster-data.sh

# Send to vendor (no credentials shared!)
# Vendor analyzes offline
python3 -m ceph_primary_balancer.cli \
  --from-file customer-export.tar.gz \
  --dry-run \
  --verbose

# Vendor provides recommendations
python3 -m ceph_primary_balancer.cli \
  --from-file customer-export.tar.gz \
  --output vendor-recommended.sh \
  --config vendor-tuned.json

# Customer reviews and executes
```

### Example 3: Historical Trend Analysis

```bash
# Archive monthly exports
./scripts/ceph-export-cluster-data.sh export-2026-01
./scripts/ceph-export-cluster-data.sh export-2026-02
./scripts/ceph-export-cluster-data.sh export-2026-03

# Analyze evolution
for export in export-*.tar.gz; do
  echo "=== $export ==="
  python3 -m ceph_primary_balancer.cli \
    --from-file $export \
    --dry-run | grep "Coefficient of Variation"
done
```

---

## 🧪 Testing

### Test Summary

```bash
# Run offline mode tests
python3 -m pytest tests/test_offline_mode.py -v
# 21 tests, all passed

python3 -m pytest tests/test_offline_integration.py -v
# 9 tests, all passed

# Run all tests
python3 -m pytest tests/ -v
# 184 tests total, all passed
```

### Test Coverage

- Archive extraction and validation
- Export file validation (missing files, corrupted JSON)
- Metadata loading and age calculation
- ClusterState construction from exports
- Primary/total count calculations
- Host aggregation verification
- Pool-level tracking
- End-to-end workflow
- Live mode compatibility

---

## 🐛 Known Issues

None at this time. Please report issues on the project repository.

---

## 🔮 Future Enhancements

Potential Phase 8.1+ features:

- **Incremental exports** - Only export changes
- **Export compression levels** - Trade size vs speed
- **Export signing** - Cryptographic verification
- **Cluster state diff** - Compare export to current state
- **Pre-execution validation** - Detect changes since export
- **Offline benchmarking** - Run benchmarks against exports

---

## 📞 Support & Resources

- **Full Documentation:** [docs/OFFLINE-MODE.md](docs/OFFLINE-MODE.md)
- **Usage Guide:** [docs/USAGE.md](docs/USAGE.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **Phase 8 Plan:** [plans/phase8-offline-mode.md](plans/phase8-offline-mode.md)

---

## 👏 Credits

**Development:** Claude Sonnet 4.5 (AI Assistant by Anthropic)  
**Project Type:** AI-Generated Software  
**Phase 8 Duration:** 2-3 hours of focused development  
**Code Added:** ~1,320 lines (module, script, tests, docs)

---

## 🎉 Summary

v1.5.0 brings **complete air-gapped environment support** to the Ceph Primary PG Balancer while maintaining **100% backward compatibility** with existing workflows. Whether you're working in high-security environments, analyzing clusters without credentials, or archiving historical data, offline mode provides a safe, flexible, and powerful solution.

**Ready to try it?** Start with `./scripts/ceph-export-cluster-data.sh` and see the [complete documentation](docs/OFFLINE-MODE.md)!

---

**Release:** v1.5.0  
**Date:** February 11, 2026  
**Status:** Production Ready (Alpha - awaiting real-world validation)
