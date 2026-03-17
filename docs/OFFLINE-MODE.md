# Offline Mode for Air-Gapped Environments

**Ceph Primary PG Balancer v1.5.0**

This guide explains how to use the Ceph Primary PG Balancer in offline mode for air-gapped and security-restricted environments where direct cluster access is unavailable.

---

## Table of Contents

- [Overview](#overview)
- [Use Cases](#use-cases)
- [Requirements](#requirements)
- [Complete Workflow](#complete-workflow)
- [Export Process](#export-process)
- [Analysis Process](#analysis-process)
- [Execution Process](#execution-process)
- [Limitations](#limitations)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

Offline mode enables you to analyze and optimize Ceph cluster primary placement without requiring direct cluster access. This three-step workflow allows you to:

1. **Export** cluster data from the Ceph environment
2. **Analyze** and generate optimization scripts on an isolated system
3. **Execute** the generated scripts back on the cluster

### Workflow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  AIR-GAPPED CEPH CLUSTER                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. Export Cluster Data                               │   │
│  │     $ ./scripts/ceph-export-cluster-data.sh           │   │
│  │                                                        │   │
│  │  2. Output: ceph-cluster-export-YYYYMMDD_HHMMSS.tar.gz│   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
                             │ Transfer Out (USB, secure copy)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  OFFLINE ANALYSIS SYSTEM                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  3. Analyze Offline                                   │   │
│  │     $ python3 -m ceph_primary_balancer.cli \          │   │
│  │         --from-file cluster-export.tar.gz \           │   │
│  │         --output rebalance.sh \                       │   │
│  │         --max-changes 100                             │   │
│  │                                                        │   │
│  │  4. Generated Scripts:                                │   │
│  │     - rebalance.sh                                    │   │
│  │     - rebalance_rollback.sh                           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
                             │ Transfer Back (USB, secure copy)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  AIR-GAPPED CEPH CLUSTER                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  5. Execute Scripts                                   │   │
│  │     $ ./rebalance.sh                                  │   │
│  │                                                        │   │
│  │     (Manual health verification required)             │   │
│  │     (Rollback available if needed)                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Use Cases

### 1. Air-Gapped Security Environments

High-security environments where cluster networks are completely isolated from external systems.

**Benefits:**
- Maintain network isolation policies
- Comply with security regulations
- Enable optimization without breaching air-gap

### 2. Analysis Workstations

Run optimization analysis on developer or analyst laptops without requiring cluster credentials.

**Benefits:**
- No cluster access credentials needed
- Test different optimization strategies
- Collaborate on optimization plans

### 3. Vendor Support

Share cluster state with support teams for troubleshooting without granting cluster access.

**Benefits:**
- Enable vendor assistance
- Protect cluster credentials
- Facilitate remote troubleshooting

### 4. Historical Analysis

Archive cluster states over time for trend analysis and capacity planning.

**Benefits:**
- Track primary distribution evolution
- Analyze optimization effectiveness
- Plan future changes based on trends

---

## Requirements

### On Ceph Cluster (Export System)

- Ceph CLI (`ceph` command) installed and accessible
- Admin credentials (ceph.conf, keyring)
- Network connectivity to cluster monitors
- Bash shell
- `tar` and `gzip` utilities
- Python 3 (for JSON parsing in metadata)

### On Analysis System (Offline System)

- Python 3.8 or higher
- Ceph Primary PG Balancer v1.5.0+
- No Ceph installation required
- No cluster access required

### Transfer Mechanism

- USB drive, secure file copy, or approved transfer method
- Sufficient storage for export archive (typically <10 MB)

---

## Complete Workflow

### Step 1: Export Cluster Data

On your Ceph cluster, run the export script:

```bash
cd /path/to/ceph_primary_balancer
./scripts/ceph-export-cluster-data.sh
```

**Output:**
```
========================================================================
Ceph Primary PG Balancer - Cluster Data Export
========================================================================

✓ Ceph CLI available and cluster accessible

Export directory: ceph-cluster-export-20260211_093022

Exporting PG data... ✓ (1.2M)
Exporting OSD tree topology... ✓ (45K)
Exporting Pool information... ✓ (12K)
Created metadata file ✓

Creating compressed archive... ✓ (892K)

========================================================================
SUCCESS! Cluster data exported
========================================================================

Archive: ceph-cluster-export-20260211_093022.tar.gz
Size: 892K

Next steps:
  1. Transfer this file out of the air-gapped environment
  2. On your analysis system, run:

     python3 -m ceph_primary_balancer.cli \
       --from-file ceph-cluster-export-20260211_093022.tar.gz \
       --dry-run
```

### Step 2: Transfer Export

Transfer the `.tar.gz` file to your analysis system using your approved method:

```bash
# Example: USB transfer
cp ceph-cluster-export-20260211_093022.tar.gz /media/usb/

# Example: Secure copy (if allowed)
scp ceph-cluster-export-20260211_093022.tar.gz analyst@laptop:~/
```

### Step 3: Analyze Offline

On your analysis system (no cluster access needed):

```bash
# Dry run analysis
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_093022.tar.gz \
  --dry-run

# Generate optimization scripts
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_093022.tar.gz \
  --output rebalance.sh \
  --max-changes 100 \
  --config balanced.json
```

**Output:**
```
============================================================
OFFLINE MODE
============================================================
Loading cluster data from: ceph-cluster-export-20260211_093022.tar.gz

Export Information:
  Export Date: 2026-02-11 09:30:22 EST
  Export Age: 2 hours old
  Source Host: ceph-mon-01
  Ceph Version: ceph version 17.2.6 (pacific)
  Cluster FSID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

Loading cluster state from offline export...
Found 840 OSDs, 42 hosts, 5 pools, 5120 PGs

... (normal analysis output) ...

Script generation complete!
  rebalance.sh (100 commands)
  rebalance_rollback.sh (100 rollback commands)
```

### Step 4: Transfer Scripts Back

Transfer the generated scripts back to the cluster:

```bash
# Example: USB transfer
cp rebalance*.sh /media/usb/

# Example: Secure copy
scp rebalance*.sh admin@ceph-mon-01:~/
```

### Step 5: Execute on Cluster

Back on your Ceph cluster:

```bash
# Review the scripts
cat rebalance.sh
cat rebalance_rollback.sh

# Execute (includes manual health verification)
chmod +x rebalance.sh
./rebalance.sh
```

**Execution Prompt:**
```
⚠️  OFFLINE MODE: Manual health verification required

This script was generated from an offline export.
Please verify the cluster is healthy and in the expected state:

  1. Run: ceph health
  2. Run: ceph -s
  3. Verify OSDs match the export (check OSD count and IDs)
  4. Verify PGs are active+clean

Cluster is healthy and matches export snapshot? [y/N]
```

---

## Export Process

### Export Script Details

The export script [`scripts/ceph-export-cluster-data.sh`](../scripts/ceph-export-cluster-data.sh) collects:

1. **PG data** (`pg_dump.json`) - Placement group mappings
2. **OSD tree** (`osd_tree.json`) - Cluster topology
3. **Pool list** (`pool_list.json`) - Pool configuration
4. **Metadata** (`metadata.json`) - Export information

### Export Archive Contents

```
ceph-cluster-export-YYYYMMDD_HHMMSS.tar.gz
└── ceph-cluster-export-YYYYMMDD_HHMMSS/
    ├── pg_dump.json          # Output: ceph pg dump pgs -f json
    ├── osd_tree.json         # Output: ceph osd tree -f json
    ├── pool_list.json        # Output: ceph osd pool ls detail -f json
    └── metadata.json         # Export metadata with timestamps
```

### Metadata Schema

```json
{
  "export_version": "1.0",
  "export_date": "2026-02-11T14:30:22Z",
  "export_date_local": "2026-02-11 09:30:22 EST",
  "export_hostname": "ceph-mon-01",
  "cluster_fsid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "ceph_version": "ceph version 17.2.6 (pacific)",
  "num_osds": "840",
  "num_pgs": "5120",
  "exporter": "ceph-export-cluster-data.sh"
}
```

---

## Analysis Process

### CLI Usage

All normal CLI options work in offline mode:

```bash
# Basic analysis
python3 -m ceph_primary_balancer.cli --from-file export.tar.gz --dry-run

# With configuration
python3 -m ceph_primary_balancer.cli \
  --from-file export.tar.gz \
  --output rebalance.sh \
  --config production-safe.json

# With custom weights
python3 -m ceph_primary_balancer.cli \
  --from-file export.tar.gz \
  --output rebalance.sh \
  --weight-osd 0.7 \
  --weight-host 0.3 \
  --max-changes 50

# With specific optimization levels
python3 -m ceph_primary_balancer.cli \
  --from-file export.tar.gz \
  --output rebalance.sh \
  --optimization-levels osd,host

# With dynamic weights
python3 -m ceph_primary_balancer.cli \
  --from-file export.tar.gz \
  --output rebalance.sh \
  --dynamic-weights \
  --dynamic-strategy target_distance

# With tabu search algorithm
python3 -m ceph_primary_balancer.cli \
  --from-file export.tar.gz \
  --output rebalance.sh \
  --algorithm tabu_search
```

### Export Age Warnings

The CLI automatically warns about stale exports:

- **< 1 day**: No warning
- **1-7 days**: Warning displayed
- **> 7 days**: Strong warning + confirmation required

Example warning:
```
⚠️  WARNING: Export is more than 7 days old
   Cluster state may have changed significantly
```

---

## Execution Process

### Generated Script Features

Scripts generated in offline mode include:

1. **Offline mode warning header** - Clear indication of offline generation
2. **Export metadata** - Source and date information
3. **Manual health verification** - Required confirmation before execution
4. **Batch execution** - Safe, incremental changes
5. **Progress tracking** - Clear feedback during execution
6. **Error handling** - Graceful failure recovery

### Manual Verification Steps

Before executing, verify:

1. **Cluster health**: `ceph health` returns OK or WARN
2. **Cluster status**: `ceph -s` shows expected state
3. **OSD count**: Matches export (check `num_osds` in metadata)
4. **PG state**: Most PGs are active+clean
5. **No major changes**: OSDs not added/removed since export

### Rollback Procedure

If issues occur during execution:

```bash
# Stop the rebalance script (Ctrl+C if running)

# Execute rollback
chmod +x rebalance_rollback.sh
./rebalance_rollback.sh

# Verify cluster recovered
ceph -s
ceph pg stat
```

---

## Limitations

### No Automatic Health Checks

Offline mode cannot perform automatic health checks. You must manually verify cluster health before execution.

**Mitigation:** Scripts require manual confirmation after health verification.

### Snapshot-in-Time Nature

Exports capture a point-in-time snapshot. Cluster changes after export are not reflected.

**Mitigation:** 
- Keep exports fresh (< 1 day old preferred)
- Verify cluster state before execution
- Use `--max-changes` to limit risk

### Potential Command Failures

If cluster state changed since export, some commands may fail (e.g., PG no longer exists, OSD removed).

**Mitigation:**
- Scripts continue on error
- Failure count reported at end
- Rollback script always available

### No Live Validation

Cannot validate proposed changes against current cluster state.

**Mitigation:**
- Start with `--max-changes` limit
- Test in development first
- Monitor during execution

---

## Best Practices

### Export Frequency

| Cluster Type | Recommended Frequency | Max Age |
|--------------|----------------------|---------|
| Production | Daily | 1 day |
| Development | Weekly | 7 days |
| Historical analysis | As needed | Any |

### Validation Workflow

1. **Export** cluster data during maintenance window
2. **Analyze** immediately or within 24 hours
3. **Review** generated scripts thoroughly
4. **Verify** cluster state hasn't changed
5. **Execute** during next maintenance window
6. **Monitor** cluster during and after execution

### Testing Strategy

1. Test in development environment first
2. Use `--dry-run` to review analysis without generating scripts
3. Start with small `--max-changes` values (10-50)
4. Gradually increase if successful
5. Always keep rollback script ready

### Security Considerations

- **Data sensitivity**: Exports contain cluster topology (not data)
- **Access control**: Protect export files appropriately
- **Transfer security**: Use encrypted transfer if required
- **Audit trail**: Keep exports for compliance/audit

---

## Troubleshooting

### Export Script Fails

**Problem:** `ceph` command not found

**Solution:**
```bash
# Ensure ceph CLI is in PATH
which ceph

# Or specify full path
/usr/bin/ceph status
```

**Problem:** Cannot connect to cluster

**Solution:**
```bash
# Verify ceph.conf and keyring
ls -l /etc/ceph/ceph.conf
ls -l /etc/ceph/ceph.client.admin.keyring

# Test connection
ceph status
```

### Invalid Export Archive

**Problem:** "Invalid export format" error

**Solution:**
- Ensure file is `.tar.gz` format
- Re-run export script
- Verify file not corrupted during transfer

**Problem:** "Missing required file" error

**Solution:**
- Export may be incomplete
- Re-run export script with verbose output
- Check disk space during export

### CLI Analysis Fails

**Problem:** "Cannot load export files"

**Solution:**
```bash
# Extract archive manually to inspect
tar -tzf export.tar.gz  # List contents
tar -xzf export.tar.gz  # Extract

# Verify JSON files are valid
python3 -m json.tool pg_dump.json
```

**Problem:** "Cluster state may have changed" warning

**Solution:**
- This is informational for old exports
- Verify cluster state manually before execution
- Generate fresh export if concerned

### Execution Issues

**Problem:** Commands fail during execution

**Solution:**
- Stop script (Ctrl+C)
- Review failures: `grep FAILED rebalance_output.log`
- Execute rollback if needed
- Investigate cluster state changes

**Problem:** "PG not found" errors

**Solution:**
- Cluster state changed since export
- PGs may have been removed/merged
- Generate fresh export and re-analyze

---

## Examples

### Example 1: First-Time Offline Analysis

```bash
# On cluster
./scripts/ceph-export-cluster-data.sh
# Creates: ceph-cluster-export-20260211_143022.tar.gz

# Transfer to laptop
scp ceph-cluster-export-20260211_143022.tar.gz analyst@laptop:~/

# On laptop (no cluster access)
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_143022.tar.gz \
  --dry-run

# Looks good, generate scripts
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260211_143022.tar.gz \
  --output rebalance.sh \
  --max-changes 100 \
  --config balanced.json

# Transfer back
scp rebalance*.sh admin@ceph-cluster:~/

# On cluster, review and execute
./rebalance.sh
```

### Example 2: Vendor Support Scenario

```bash
# Customer exports cluster state
./scripts/ceph-export-cluster-data.sh

# Customer sends export to vendor (redact if needed)
# Vendor analyzes offline
python3 -m ceph_primary_balancer.cli \
  --from-file customer-export.tar.gz \
  --dry-run \
  --verbose

# Vendor generates recommendations
python3 -m ceph_primary_balancer.cli \
  --from-file customer-export.tar.gz \
  --output vendor-recommended.sh \
  --config vendor-tuned.json

# Vendor sends scripts back to customer
# Customer reviews and executes
```

### Example 3: Historical Trend Analysis

```bash
# Archive monthly exports
./scripts/ceph-export-cluster-data.sh export-2026-01
./scripts/ceph-export-cluster-data.sh export-2026-02
./scripts/ceph-export-cluster-data.sh export-2026-03

# Analyze trend
for export in export-*.tar.gz; do
  echo "=== $export ==="
  python3 -m ceph_primary_balancer.cli \
    --from-file $export \
    --dry-run | grep "Coefficient of Variation"
done
```

---

## Additional Resources

- [Main Usage Guide](USAGE.md)
- [Installation Guide](INSTALLATION.md)
- [Configuration Guide](../config-examples/README.md)
- [Troubleshooting](TROUBLESHOOTING.md)

---

**Version:** 1.5.0  
**Last Updated:** 2026-02-11
