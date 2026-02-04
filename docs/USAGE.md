# Usage Guide

**Tool Version:** v0.8.0
**Command:** `python3 -m ceph_primary_balancer.cli`

> **🤖 AI-Generated Project:** This project was designed, implemented, and documented by Claude Sonnet 4.5, an AI assistant by Anthropic.

> **📋 What's New in v0.8.0?** Comprehensive unit tests (57 tests), improved documentation, and validated production readiness.

> **📋 Phase 4 Sprint 1 Complete (v0.5.0-v0.7.0):** --max-changes, health checks, rollback scripts, and batch execution.

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

### Limit Number of Changes (v0.5.0+)

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

### Batch Execution (v0.7.0+)

Control how commands are grouped in generated scripts:

```bash
# Default: 50 commands per batch
python3 -m ceph_primary_balancer.cli --output ./rebalance.sh

# Smaller batches for more frequent safety pauses
python3 -m ceph_primary_balancer.cli --batch-size 25 --output ./rebalance.sh

# Larger batches for faster execution
python3 -m ceph_primary_balancer.cli --batch-size 100 --output ./rebalance.sh

# Combine with max-changes
python3 -m ceph_primary_balancer.cli --max-changes 150 --batch-size 25
```

**Benefits:**
- **Safety pauses**: Script pauses between batches for operator review
- **Progress tracking**: Clear visibility into which batch is executing
- **Abort capability**: Stop execution between batches if issues arise
- **Flexibility**: Continue or abort at each batch boundary

**Generated script structure:**
```bash
# Batch 1/3: Commands 1-50 (50 commands)
apply_mapping "3.a1" 12
# ... 49 more commands ...

Batch 1/3 complete. Progress: 50/150 commands (0 failed)
Continue to next batch? [Y/n]

# Batch 2/3: Commands 51-100 (50 commands)
# ... commands ...
```

**When to use different batch sizes:**
- **25-30**: High-value clusters, maximum caution, frequent checkpoints
- **50 (default)**: Balanced approach for most production clusters
- **75-100**: Development/test clusters, faster rebalancing

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

## Production Safety Features (v0.5.0-v0.7.0)

### Automatic Rollback Scripts (v0.6.0+)

Every generated rebalancing script automatically includes a rollback script:

```bash
# Generate rebalancing script
python3 -m ceph_primary_balancer.cli --output ./rebalance.sh

# Two scripts are created:
# - rebalance.sh (main script)
# - rebalance_rollback.sh (reverses all changes)
```

**Using the rollback script:**

```bash
# If something goes wrong after applying changes
./rebalance_rollback.sh

# The rollback script will:
# 1. Check cluster health
# 2. Warn about the operation
# 3. Ask for confirmation
# 4. Reverse all primary assignments
```

**When to use rollback:**
- Unexpected performance degradation after rebalancing
- Client errors or connectivity issues
- Need to return to previous state for troubleshooting

### Cluster Health Checks (v0.5.0+)

Generated scripts automatically include health verification:

```bash
# Health check runs before executing any commands
echo "Checking cluster health..."
HEALTH=$(ceph health 2>/dev/null)
if [[ ! "$HEALTH" =~ ^HEALTH_OK ]] && [[ ! "$HEALTH" =~ ^HEALTH_WARN ]]; then
    echo "ERROR: Cluster health is $HEALTH"
    echo "Refusing to proceed with unhealthy cluster"
    exit 1
fi
```

**Health check behavior:**
- ✅ **HEALTH_OK**: Proceeds automatically
- ⚠️ **HEALTH_WARN**: Proceeds with warning
- ❌ **HEALTH_ERR**: Blocks execution (override option available)

### Complete Production Workflow (v0.8.0)

```bash
# 1. Analyze and generate with safety features
python3 -m ceph_primary_balancer.cli \
  --max-changes 100 \
  --batch-size 25 \
  --output ./rebalance.sh \
  --json-output ./plan.json \
  --report-output ./plan.md

# Files created:
# - rebalance.sh (100 commands in 4 batches of 25)
# - rebalance_rollback.sh (reverses all 100 changes)
# - plan.json (detailed analysis)
# - plan.md (markdown report)

# 2. Review the plan
cat ./plan.md

# 3. Execute during maintenance window
./rebalance.sh
# - Health check runs first
# - Batch 1/4 executes (25 commands)
# - Pause for operator review
# - Continue or abort
# - Repeat for remaining batches

# 4. If issues occur, rollback immediately
./rebalance_rollback.sh
```

---

## Upcoming Features (v1.0.0)

Still planned for v1.0.0 release:

```bash
# Configuration file support
python3 -m ceph_primary_balancer.cli --config config.json

# Custom output directory
python3 -m ceph_primary_balancer.cli --output-dir ./output/

# Verbose/quiet modes
python3 -m ceph_primary_balancer.cli --verbose
```

See [phase4-implementation-tasks.md](../plans/phase4-implementation-tasks.md) for the implementation roadmap.

---

## Troubleshooting

For common issues and solutions, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For detailed technical information, see [technical-specification.md](technical-specification.md).
