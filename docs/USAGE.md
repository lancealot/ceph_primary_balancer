# Usage Guide

**Tool Version:** v0.4.0
**Command:** `python3 -m ceph_primary_balancer.cli`

> **📋 New to v0.4.0?** See [RELEASE-NOTES-v0.4.0.md](../RELEASE-NOTES-v0.4.0.md) for what's new in this version.

This guide covers common usage patterns for the Ceph Primary PG Balancer.

---

## Basic Usage

### Dry Run Analysis (No Changes)

Analyze your cluster without making any changes:

```bash
python3 -m ceph_primary_balancer.cli --dry-run
```

This will:
- Collect current cluster data
- Calculate OSD, Host, and Pool-level statistics
- Show current imbalance (CV %)
- Propose optimal changes
- NOT generate any script

### Generate Rebalancing Script

Generate a bash script to apply the changes:

```bash
python3 -m ceph_primary_balancer.cli --output ./rebalance.sh
```

Then review and execute:

```bash
cat ./rebalance.sh  # Review what will happen
./rebalance.sh      # Execute (with confirmation prompt)
```

---

## Advanced Options

### Customize Optimization Weights (v0.2.0+)

Control how the optimizer balances across dimensions:

```bash
# Default: OSD=0.5, Host=0.3, Pool=0.2
python3 -m ceph_primary_balancer.cli --dry-run

# Prioritize host balance
python3 -m ceph_primary_balancer.cli --weight-osd 0.3 --weight-host 0.5 --weight-pool 0.2

# OSD-only optimization (like MVP)
python3 -m ceph_primary_balancer.cli --weight-osd 1.0 --weight-host 0.0 --weight-pool 0.0
```

**Note:** Weights must sum to 1.0

### Filter by Pool (v0.3.0+)

Optimize only a specific pool:

```bash
# Get pool IDs
ceph osd pool ls detail

# Optimize only pool 3
python3 -m ceph_primary_balancer.cli --pool 3 --output ./rebalance_pool3.sh
```

### Set Target CV

Control how aggressively to optimize:

```bash
# More aggressive (5% target)
python3 -m ceph_primary_balancer.cli --target-cv 0.05

# Less aggressive (15% target)
python3 -m ceph_primary_balancer.cli --target-cv 0.15

# Default is 10%
```

### Limit Number of Changes (v1.0.0+)

For production safety, limit the number of primary reassignments:

```bash
# Apply only 100 changes
python3 -m ceph_primary_balancer.cli --max-changes 100

# Combine with other options
python3 -m ceph_primary_balancer.cli --max-changes 50 --pool 3 --dry-run
```

This is useful for:
- **Incremental testing**: Apply a small number of changes first to verify behavior
- **Risk management**: Limit the scope of operations in production
- **Gradual rebalancing**: Apply changes in batches over time to minimize cluster impact

The tool will:
1. Find all optimal swaps through full optimization
2. Select the first N swaps (ordered by benefit, early swaps have higher impact)
3. Recalculate statistics based on only those N swaps
4. Generate a script with exactly N commands

**Example output:**
```
APPLYING SWAP LIMIT
============================================================
Optimization found 247 beneficial swaps
Limiting to 50 changes (--max-changes=50)

Recalculating proposed state with 50 swaps...
Proposed state recalculated with 50 swaps
```

---

## Export & Reporting (v0.4.0+)

### JSON Export for Automation

```bash
# Export analysis results to JSON
python3 -m ceph_primary_balancer.cli --json-output ./analysis.json

# JSON contains: current state, proposed state, all changes, improvements
```

Use in automation:

```python
import json

with open('analysis.json') as f:
    data = json.load(f)
    
current_cv = data['current_state']['osd_level']['cv']
proposed_cv = data['proposed_state']['osd_level']['cv']
improvement = data['improvements']['osd_cv_reduction_pct']
```

### Markdown Report Generation

```bash
# Generate professional markdown report
python3 -m ceph_primary_balancer.cli --report-output ./analysis.md
```

The report includes:
- Executive summary
- OSD, Host, and Pool-level comparisons
- Top donors and receivers
- Sample proposed changes
- Implementation recommendations

### Generate All Outputs

```bash
python3 -m ceph_primary_balancer.cli \
  --format all \
  --output ./rebalance.sh \
  --json-output ./analysis.json \
  --report-output ./report.md
```

---

## Common Workflows

### Workflow 1: Initial Assessment

```bash
# 1. Analyze current state
python3 -m ceph_primary_balancer.cli --dry-run

# 2. Export detailed report
python3 -m ceph_primary_balancer.cli \
  --json-output ./current_state.json \
  --report-output ./assessment.md
```

### Workflow 2: Targeted Pool Optimization

```bash
# 1. Check which pools need balancing
python3 -m ceph_primary_balancer.cli --dry-run | grep "Pool"

# 2. Optimize specific pool
python3 -m ceph_primary_balancer.cli \
  --pool 3 \
  --output ./rebalance_pool3.sh

# 3. Apply changes
./rebalance_pool3.sh
```

### Workflow 3: Production Cluster Optimization

```bash
# 1. Generate all documentation
python3 -m ceph_primary_balancer.cli \
  --format all \
  --output ./rebalance.sh \
  --json-output ./before.json \
  --report-output ./plan.md

# 2. Review the plan
cat ./plan.md

# 3. Apply during maintenance window
./rebalance.sh

# 4. Verify improvement
python3 -m ceph_primary_balancer.cli \
  --dry-run \
  --json-output ./after.json
```

---

## Interpreting Results

### Coefficient of Variation (CV)

CV measures distribution uniformity (lower is better):

| CV Range | Assessment | Action |
|----------|------------|--------|
| < 10% | Excellent balance | No action needed |
| 10-20% | Acceptable balance | Optional optimization |
| 20-30% | Poor balance | Optimization recommended |
| > 30% | Severe imbalance | Optimization strongly recommended |

### Reading the Output

```
Current Statistics:
  Mean:        32.0 primaries/OSD
  Std Dev:     8.5              ← How spread out
  CV:          26.6%            ← Key metric (std_dev / mean)
  Range:       18 - 48          ← Min and max
```

**Lower CV = more uniform distribution**

---

## Phase 4 Features (Coming Soon)

The following options are planned for v1.0.0 but not yet available:

```bash
# Limit number of changes (Phase 4)
python3 -m ceph_primary_balancer.cli --max-changes 100  # ⏳ Not yet available

# Custom output directory (Phase 4)
python3 -m ceph_primary_balancer.cli --output-dir ./output/  # ⏳ Not yet available
```

For current workarounds, see the [Phase 4 planning documents](../plans/phase4-implementation-tasks.md).

---

## Troubleshooting

For common issues and solutions, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For detailed technical information, see [technical-specification.md](technical-specification.md).
