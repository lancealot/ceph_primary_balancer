# ⚠️ HISTORICAL DOCUMENT - MVP Usage Guide (v0.1.0)

> **⚠️ WARNING: This document describes the original MVP (v0.1.0) from January 2026.**
> **Current Version: v0.4.0**
>
> **Many features listed as "NOT Included" below have since been implemented:**
> - ✅ **Host-level optimization** - Implemented in v0.2.0
> - ✅ **Pool-level optimization** - Implemented in v0.3.0
> - ✅ **JSON export** - Implemented in v0.4.0
> - ✅ **Weighted optimization** - Implemented in v0.2.0
>
> **For current usage documentation, see:** [`USAGE.md`](USAGE.md)
> **For current features, see:** [`README.md`](../README.md)
>
> This document is kept for historical reference only.

---

# Ceph Primary PG Balancer - MVP Usage Guide (v0.1.0)

## Introduction

The Ceph Primary PG Balancer MVP is a command-line tool that analyzes and optimizes the distribution of primary placement groups (PGs) across OSDs in your Ceph cluster. While Ceph's built-in upmap balancer distributes total PGs evenly, it doesn't consider primary assignment, which can lead to I/O hotspots. This tool addresses that gap.

**For the complete technical specification, see:** [`docs/technical-specification.md`](technical-specification.md)

---

## MVP Limitations (v0.1.0 - January 2026)

### ✅ What WAS Included in MVP (v0.1.0)

- **OSD-level primary balancing** - Optimizes primary distribution across all OSDs
- **Statistical analysis** - Calculates mean, standard deviation, and coefficient of variation (CV)
- **Dry-run mode** - Analyze cluster without making changes
- **Script generation** - Creates executable bash scripts for applying changes
- **Safety features** - Confirmation prompts and progress tracking
- **Smart optimization** - Greedy algorithm that only makes beneficial swaps

### ❌ What was NOT Included in MVP (Many Now Implemented!)

- **Host-level optimization** - Balancing primaries across physical hosts ✅ **IMPLEMENTED in v0.2.0**
- **Pool-level optimization** - Per-pool balancing strategies ✅ **IMPLEMENTED in v0.3.0**
- **JSON export** - Machine-readable output format ✅ **IMPLEMENTED in v0.4.0**
- **Weighted optimization** - Custom weights for different optimization goals ✅ **IMPLEMENTED in v0.2.0**
- **Max changes limit** - Hard cap on number of swaps per run ⏳ **Planned for v1.0.0**
- **Package installation** - Currently runs from source only ⏳ **Future release**

**See:** [`plans/mvp-implementation-plan.md`](../plans/mvp-implementation-plan.md) for the complete roadmap.

---

## Prerequisites

Before using this tool, ensure you have:

1. **Python 3.8 or higher**
   ```bash
   python3 --version  # Should show 3.8.x or higher
   ```

2. **Ceph cluster access with admin privileges**
   - The `ceph` CLI command must be available in your PATH
   - You must have permissions to run `ceph osd dump`, `ceph osd tree`, and `ceph osd pg-upmap-primary`

3. **Required permissions**
   - Read access: `ceph osd dump` and `ceph osd tree`
   - Write access: `ceph osd pg-upmap-primary` (only when applying changes)

4. **Network access**
   - Ability to connect to the Ceph cluster from your machine

---

## Installation

The MVP version runs directly from source (no pip install yet).

### Step 1: Clone or Download the Repository

```bash
cd /path/to/your/workspace
# If using git:
git clone <repository-url> ceph_primary_balancer
cd ceph_primary_balancer
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

Or if you prefer using Python 3 explicitly:

```bash
pip3 install -r requirements.txt
```

### Step 3: Verify Installation

```bash
python3 -m ceph_primary_balancer.cli --help
```

You should see the help output with available options.

### Step 4: Verify Ceph Access

```bash
ceph osd tree  # Should display your OSD tree
ceph osd dump  # Should display cluster PG information
```

---

## Basic Usage

### Complete Workflow

The typical workflow consists of four steps:

#### 1. Dry Run Analysis

First, analyze your cluster without making any changes:

```bash
python3 -m ceph_primary_balancer.cli --dry-run
```

**What this does:**
- Collects current cluster state from Ceph
- Calculates current primary distribution statistics
- Determines if optimization is needed
- Proposes optimal primary reassignments
- Does NOT generate a script (analysis only)

#### 2. Generate Rebalancing Script

If the dry run shows improvement is possible, generate the script:

```bash
python3 -m ceph_primary_balancer.cli --output ./rebalance_primaries.sh
```

**What this does:**
- Performs the same analysis as dry-run
- Generates an executable bash script with all necessary commands
- Saves the script to the specified path (default: `./rebalance_primaries.sh`)

#### 3. Review the Generated Script

Before applying changes, review what will be executed:

```bash
cat ./rebalance_primaries.sh
# or
less ./rebalance_primaries.sh
```

**What to look for:**
- Number of `pg-upmap-primary` commands
- Which PGs are being reassigned
- Which OSDs are receiving new primaries

#### 4. Apply Changes to Cluster

Execute the script to apply the changes:

```bash
./rebalance_primaries.sh
```

**What happens:**
- You'll be prompted for confirmation: `Continue? [y/N]`
- Type `y` and press Enter to proceed
- Each command executes with progress tracking
- Shows success/failure for each reassignment
- Displays summary at the end

---

## Command-Line Options

### `--dry-run`

**Purpose:** Analyze cluster without generating a script

**Example:**
```bash
python3 -m ceph_primary_balancer.cli --dry-run
```

**Use when:**
- You want to understand current distribution
- Checking if balancing is needed
- Testing the tool on a new cluster

### `--target-cv`

**Purpose:** Set the target coefficient of variation (default: 0.10)

**Example:**
```bash
python3 -m ceph_primary_balancer.cli --target-cv 0.05 --output ./rebalance.sh
```

**Explanation:**
- CV (coefficient of variation) = standard deviation / mean
- Lower CV = more uniform distribution
- Default 0.10 (10%) is a good balance between optimization and number of changes
- For more aggressive balancing, use 0.05 (5%)
- For minimal changes, use 0.15 (15%)

### `--output`

**Purpose:** Specify the output script path (default: `./rebalance_primaries.sh`)

**Example:**
```bash
python3 -m ceph_primary_balancer.cli --output /tmp/my_rebalance.sh
```

**Notes:**
- The output directory must exist
- Script will be made executable automatically (chmod 755)

---

## What to Expect

### Execution Times

| Phase | Typical Duration | Notes |
|-------|-----------------|-------|
| Collecting cluster data | 5-30 seconds | Depends on cluster size and network latency |
| Statistical analysis | < 1 second | Instant for most clusters |
| Optimization | 1-10 seconds | Depends on cluster size and imbalance severity |
| Script generation | < 1 second | Instant |
| Applying each command | < 1 second | Metadata-only operation, very fast |

**For a large cluster (1000+ PGs, 50+ OSDs):**
- Total analysis time: ~30 seconds
- Script generation: instant
- Execution time: 1-5 minutes (depends on number of swaps)

### Example Output

#### Dry Run Output

```
Collecting cluster data...

Current State:

Cluster Primary Distribution Analysis
==================================================
Total PGs:  384
Total OSDs: 12

Current Statistics:
  Mean:        32.0 primaries/OSD
  Std Dev:     8.5
  CV:          26.6%
  Range:       18 - 48
  Median:      31.0

Top 5 Donors (most primaries):
  OSD.3: 48 primaries
  OSD.7: 45 primaries
  OSD.1: 42 primaries
  OSD.9: 38 primaries
  OSD.5: 35 primaries

Top 5 Receivers (fewest primaries):
  OSD.10: 18 primaries
  OSD.2: 22 primaries
  OSD.8: 24 primaries
  OSD.6: 28 primaries
  OSD.4: 29 primaries

Optimizing (target CV = 10.0%)...

Proposed 45 primary reassignments
Improvement: 26.6% -> 8.7%

Dry run mode - no script generated
```

#### Script Generation Output

```
Collecting cluster data...
[... same analysis as above ...]

Proposed 45 primary reassignments
Improvement: 26.6% -> 8.7%

Script written to: ./rebalance_primaries.sh
```

#### Script Execution Output

```bash
$ ./rebalance_primaries.sh
This script will execute 45 pg-upmap-primary commands.
Continue? [y/N] y
[  1/45] 3.a1         -> OSD.10   OK
[  2/45] 3.b2         -> OSD.2    OK
[  3/45] 5.1c         -> OSD.8    OK
[  4/45] 7.3e         -> OSD.6    OK
...
[ 45/45] 12.7a        -> OSD.4    OK

Complete: 45 successful, 0 failed
```

---

## Understanding the Output

### Statistical Metrics Explained

#### Mean
Average number of primaries per OSD. In a perfectly balanced cluster, all OSDs would have exactly this number.

**Example:** If you have 384 PGs and 12 OSDs, the mean is 32.0 primaries per OSD.

#### Standard Deviation (Std Dev)
Measures how spread out the distribution is from the mean. Lower is better.

**Interpretation:**
- 0-5: Very tight distribution (excellent)
- 5-10: Reasonable distribution (good)
- 10+: Wide distribution (needs balancing)

#### Coefficient of Variation (CV)
The key metric for assessing balance. It's the standard deviation divided by the mean, expressed as a percentage.

**CV Thresholds:**
- **< 10%**: Excellent balance - cluster is well-optimized
- **10-20%**: Acceptable balance - optimization optional
- **20-30%**: Poor balance - optimization recommended
- **> 30%**: Severe imbalance - optimization strongly recommended

**Why CV matters:** Unlike standard deviation, CV is normalized, making it easy to compare clusters of different sizes.

#### Range (Min - Max)
The spread between the OSD with the fewest and most primaries.

**Example:** "Range: 18 - 48" means one OSD has only 18 primaries while another has 48.

#### Median (P50)
The middle value when all OSD primary counts are sorted. Half of OSDs have more primaries, half have fewer.

### Donors and Receivers

**Donors** are OSDs with significantly more primaries than average (> 10% above mean). These OSDs will give up some primaries.

**Receivers** are OSDs with significantly fewer primaries than average (> 10% below mean). These OSDs will receive additional primaries.

---

## Safety Considerations

### 1. Confirmation Prompt

Every generated script includes a confirmation prompt before executing any commands:

```bash
This script will execute 45 pg-upmap-primary commands.
Continue? [y/N]
```

Press `y` to continue or `n` (or any other key) to abort.

### 2. Progress Tracking

Each command displays its progress:
- Command number (e.g., `[23/45]`)
- PG ID being reassigned
- New primary OSD
- Success or failure status

### 3. Reviewable Commands

The generated script is plain bash - you can review every command before execution:

```bash
cat ./rebalance_primaries.sh | grep "apply_mapping"
```

### 4. No Data Movement

**Critical safety feature:** The `pg-upmap-primary` command only changes primary designation. It does NOT move any data between OSDs.

**What this means:**
- No network traffic for data replication
- No additional disk I/O for data movement
- Changes take effect instantly (metadata only)
- Safe to run on production clusters

### 5. Performance Impact

**During execution:**
- Very minimal cluster load (metadata operations only)
- No data is moved or replicated
- Client I/O may briefly reconnect to new primaries
- Total execution time: seconds to minutes (not hours)

**After execution:**
- I/O becomes more evenly distributed
- Reduced risk of hotspots
- Better overall cluster performance

### 6. Rollback Capability

If needed, you can manually reverse changes using:

```bash
ceph osd rm-pg-upmap-primary <pgid>
```

This returns the PG to its automatic primary selection.

---

## Troubleshooting Common Issues

### Issue: "ceph command not found"

**Cause:** The `ceph` CLI is not in your PATH or not installed.

**Solution:**
```bash
# Check if ceph is installed
which ceph

# If not installed, install the ceph-common package
# On Debian/Ubuntu:
apt-get install ceph-common

# On RHEL/CentOS:
yum install ceph-common

# If installed but not in PATH, add it:
export PATH=$PATH:/usr/bin
```

### Issue: "Cluster already balanced"

**Output:**
```
Cluster already balanced (CV = 8.5%)
Target CV of 10.0% already achieved - no optimization needed
```

**Cause:** Your cluster is already well-balanced.

**What to do:**
- This is good news! No action needed.
- If you want even tighter balance, use a lower `--target-cv`:
  ```bash
  python3 -m ceph_primary_balancer.cli --target-cv 0.05 --dry-run
  ```

### Issue: "No optimization swaps found"

**Output:**
```
No optimization swaps found
The cluster may already be optimally balanced or no valid swaps exist
```

**Cause:** The optimizer couldn't find any beneficial swaps that improve the CV.

**Possible reasons:**
1. Cluster is already balanced
2. PG placement constraints prevent beneficial swaps
3. Very small cluster with limited swap opportunities

**What to do:**
- Review your current CV - if it's already low (<15%), you're fine
- Check your PG count - very few PGs limit optimization potential
- Consider increasing PG count if it's very low

### Issue: "Permission denied" errors

**Cause:** Insufficient privileges to run Ceph commands or write to output directory.

**Solution for Ceph access:**
```bash
# Ensure you have the correct Ceph keyring
ceph auth list | grep client.admin

# Test permissions
ceph osd tree
ceph osd dump
```

**Solution for file writing:**
```bash
# Use a directory you own
python3 -m ceph_primary_balancer.cli --output ~/rebalance.sh

# Or create the directory first
mkdir -p ./output
python3 -m ceph_primary_balancer.cli --output ./output/rebalance.sh
```

### Issue: "Error collecting cluster data"

**Possible causes:**
- Network connectivity to cluster
- Ceph cluster is down or unhealthy
- JSON parsing errors

**Debugging steps:**
```bash
# Test basic connectivity
ceph health

# Test the specific commands the tool uses
ceph osd dump --format=json
ceph osd tree --format=json

# Check for cluster health issues
ceph status
```

### Issue: Some commands fail during script execution

**Output:**
```
[ 42/45] 8.3f         -> OSD.15   FAILED
```

**Possible causes:**
- PG no longer exists (cluster changed since script generation)
- OSD is down or out
- Placement constraints prevent the mapping

**What to do:**
1. Check the failed PG: `ceph pg dump | grep 8.3f`
2. Check OSD status: `ceph osd tree`
3. Re-run the analysis to generate a fresh script
4. A few failures out of many changes is usually acceptable

---

## Example Workflow

Here's a complete example from start to finish:

### Step 1: Initial Analysis

```bash
$ python3 -m ceph_primary_balancer.cli --dry-run

Collecting cluster data...

Current State:

Cluster Primary Distribution Analysis
==================================================
Total PGs:  512
Total OSDs: 24

Current Statistics:
  Mean:        21.3 primaries/OSD
  Std Dev:     6.2
  CV:          29.1%
  Range:       10 - 35
  Median:      21.0

Top 5 Donors (most primaries):
  OSD.15: 35 primaries
  OSD.8: 32 primaries
  OSD.22: 31 primaries
  OSD.3: 29 primaries
  OSD.19: 28 primaries

Top 5 Receivers (fewest primaries):
  OSD.12: 10 primaries
  OSD.7: 13 primaries
  OSD.20: 14 primaries
  OSD.4: 16 primaries
  OSD.11: 16 primaries

Optimizing (target CV = 10.0%)...

Proposed 67 primary reassignments
Improvement: 29.1% -> 9.2%

Dry run mode - no script generated
```

**Observation:** CV of 29.1% indicates poor balance. Optimization is recommended.

### Step 2: Generate Script

```bash
$ python3 -m ceph_primary_balancer.cli --output ./rebalance_primaries.sh

[... same output as dry-run ...]

Script written to: ./rebalance_primaries.sh
```

### Step 3: Review Script

```bash
$ head -20 ./rebalance_primaries.sh

#!/bin/bash
# Ceph Primary PG Rebalancing Script
# Generated: 2026-02-03T10:30:45.123456
# Total commands: 67

set -e

echo "This script will execute 67 pg-upmap-primary commands."
read -p "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || exit 1

TOTAL=67
COUNT=0
FAILED=0
...
```

**Looks good!** Ready to apply.

### Step 4: Apply Changes

```bash
$ ./rebalance_primaries.sh

This script will execute 67 pg-upmap-primary commands.
Continue? [y/N] y
[  1/67] 3.0          -> OSD.12   OK
[  2/67] 3.5          -> OSD.7    OK
[  3/67] 5.2          -> OSD.20   OK
...
[ 67/67] 15.1a        -> OSD.11   OK

Complete: 67 successful, 0 failed
```

### Step 5: Verify Improvement

```bash
$ python3 -m ceph_primary_balancer.cli --dry-run

Collecting cluster data...

Current State:

Cluster Primary Distribution Analysis
==================================================
Total PGs:  512
Total OSDs: 24

Current Statistics:
  Mean:        21.3 primaries/OSD
  Std Dev:     2.0
  CV:          9.4%
  Range:       18 - 25
  Median:      21.0

...

Cluster already balanced (CV = 9.4%)
Target CV of 10.0% already achieved - no optimization needed
```

**Success!** CV improved from 29.1% to 9.4%.

---

## Next Steps After MVP

This MVP version focuses on core functionality and safety. Future versions will add:

### Planned for v2.0
- **Host-level optimization** - Balance primaries across physical hosts
- **Pool-level optimization** - Optimize each pool independently
- **JSON export** - Machine-readable output for integration
- **Weighted optimization** - Custom weights for different goals
- **Max changes limit** - Hard cap on swaps per run
- **Package installation** - `pip install ceph-primary-balancer`

### Planned for v3.0
- **Interactive mode** - Step-by-step guidance
- **Monitoring integration** - Prometheus metrics export
- **Multi-cluster support** - Manage multiple clusters
- **Automatic scheduling** - Periodic rebalancing

**For the complete roadmap, see:**
- [`plans/mvp-implementation-plan.md`](../plans/mvp-implementation-plan.md)
- [`docs/technical-specification.md`](technical-specification.md)

---

## Additional Resources

- **Quick Start Guide:** [`plans/QUICK-START.md`](../plans/QUICK-START.md)
- **Installation Guide:** [`docs/INSTALLATION.md`](INSTALLATION.md)
- **Troubleshooting:** [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md)
- **Development Guide:** [`docs/DEVELOPMENT.md`](DEVELOPMENT.md)
- **Technical Specification:** [`docs/technical-specification.md`](technical-specification.md)

---

## Feedback and Contributions

This is an MVP release. Your feedback is valuable:

- Report issues and bugs
- Suggest features for future versions
- Contribute improvements
- Share your use cases and results

**License:** Apache 2.0
