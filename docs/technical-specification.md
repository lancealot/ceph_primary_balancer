# Ceph Primary PG Balancer - Technical Specification

## Document Purpose

This specification defines a Python tool for analyzing and optimizing primary Placement Group (PG) distribution across a Ceph cluster. The tool will identify hotspots, calculate optimal primary assignments, and generate executable scripts to rebalance the cluster.

---

## 1. Problem Statement

### 1.1 Background

In Ceph, each Placement Group (PG) has an **acting set** of OSDs that store replicas of the data. The first OSD in the acting set is the **primary**, which:

- Handles all client read operations (in default configuration)
- Coordinates all write operations
- Manages peering and recovery for that PG

The built-in `upmap` balancer optimizes for **total PG distribution** (ensuring each OSD has roughly equal total PGs), but it does **not** optimize for **primary PG distribution**. This can result in:

- Some OSDs handling disproportionately more client I/O
- Network hotspots at the host level
- Uneven latency across the cluster

### 1.2 Observed Problem

Analysis of production clusters revealed significant primary PG imbalance:

| Metric | Cluster A | Cluster B |
|--------|-----------|-----------|
| OSD Std Deviation | 4.06 | 2.45 |
| OSD Coefficient of Variation | 51.00% | 38.00% |
| Host Std Deviation | 14.87 | 16.30 |
| Host Coefficient of Variation | 6.00% | 9.00% |

A coefficient of variation above 20% at the OSD level indicates significant imbalance requiring correction.

### 1.3 Key Constraint

**The new primary must already be in the PG's acting set.** You cannot arbitrarily assign any OSD as primary—only OSDs that already hold a replica of that PG are valid candidates.

For example, if PG `3.a1` has acting set `[12, 45, 78]`:
- OSD.12 is currently primary
- Valid new primaries: OSD.45 or OSD.78 only
- OSD.99 cannot become primary (it doesn't have the data)

### 1.4 Why This Is Low-Risk

The `pg-upmap-primary` command changes **only metadata** (an OSDMap entry). It does **not** move data:

| What Changes | What Does NOT Change |
|--------------|----------------------|
| OSDMap entry (bytes) | PG data location |
| Which OSD serves client I/O | Replica placement |
| Peering coordination | Recovery/backfill state |
| | CRUSH calculations |

Impact: Brief re-peering (typically sub-second), then the new primary immediately serves I/O.

---

## 2. Goals and Objectives

### 2.1 Primary Goals

1. **Analyze** current primary PG distribution across OSDs, hosts, and pools
2. **Calculate** an optimal primary assignment that minimizes variance at all levels
3. **Generate** a bash script containing `ceph osd pg-upmap-primary` commands
4. **Report** expected improvement metrics

### 2.2 Optimization Target

Balance primary PGs across three dimensions simultaneously:

| Dimension | Why It Matters |
|-----------|----------------|
| OSD-level | Prevents individual disk I/O hotspots |
| Host-level | Prevents network/node-level bottlenecks |
| Pool-level | Ensures workload-specific balance |

### 2.3 Non-Goals (Out of Scope)

- Moving actual PG data (that's the `upmap` balancer's job)
- Modifying CRUSH rules or weights
- Balancing total PGs (only primary assignment)
- Real-time continuous balancing (this is a point-in-time tool)

---

## 3. Algorithm Design

### 3.1 Approach: Greedy Donor-Receiver Swapping

The tool uses a greedy algorithm for fast, predictable results:

```
1. Identify "donor" OSDs (primary count > threshold above average)
2. Identify "receiver" OSDs (primary count < threshold below average)
3. For each PG where a donor is primary:
   a. Check if any receiver is in the acting set
   b. If yes, evaluate the swap using the scoring function
   c. If the swap improves the global score, record it
4. Repeat until no beneficial swaps remain or target variance achieved
```

### 3.2 Multi-Dimensional Scoring Function

Each potential swap is evaluated using a composite score:

```
score = (w_osd × OSD_variance) + (w_host × Host_variance) + (w_pool × Pool_variance)
```

**Default weights (configurable):**
- `w_osd = 0.5` (50% weight on OSD balance)
- `w_host = 0.3` (30% weight on host balance)
- `w_pool = 0.2` (20% weight on pool balance)

**Variance calculation:**
```
variance = Σ(count_i - target_i)² / n
```

Where `target_i` is the ideal primary count (total_primaries / n for equal distribution).

### 3.3 Swap Evaluation Logic

For each candidate swap, calculate:

```python
current_score = calculate_score(current_state)
proposed_score = calculate_score(state_after_swap)

if proposed_score < current_score:
    accept_swap()
else:
    reject_swap()
```

### 3.4 Host-Aware Prioritization

When multiple valid swaps exist, prioritize:

1. **Best:** Donor OSD on donor host → Receiver OSD on receiver host
   - Improves both OSD and host balance
2. **Good:** Donor OSD on balanced host → Receiver OSD on receiver host
   - Improves OSD balance, improves host balance
3. **Acceptable:** Donor OSD → Receiver OSD on same host
   - Improves OSD balance, host balance neutral
4. **Reject:** Any swap that improves OSD balance but worsens host balance

### 3.5 Termination Conditions

Stop optimization when any of the following are met:

1. Target coefficient of variation achieved (default: 10%)
2. No beneficial swaps remain (local optimum reached)
3. Maximum iterations reached (default: 10,000)
4. Maximum changes reached (configurable limit)

---

## 4. Data Structures

### 4.1 Core Data Model

```python
@dataclass
class PGInfo:
    pgid: str              # e.g., "3.a1"
    pool_id: int           # e.g., 3
    acting: List[int]      # e.g., [12, 45, 78]
    primary: int           # e.g., 12 (first in acting)
    
@dataclass
class OSDInfo:
    osd_id: int
    host: str
    crush_weight: float
    primary_count: int     # Current primary PG count
    total_pg_count: int    # Total PGs (primary + replica)

@dataclass
class HostInfo:
    hostname: str
    osd_ids: List[int]
    primary_count: int     # Sum of all OSD primary counts
    
@dataclass  
class PoolInfo:
    pool_id: int
    pool_name: str
    pg_count: int
    primary_counts: Dict[int, int]  # osd_id -> primary count for this pool

@dataclass
class ClusterState:
    pgs: Dict[str, PGInfo]
    osds: Dict[int, OSDInfo]
    hosts: Dict[str, HostInfo]
    pools: Dict[int, PoolInfo]
    
@dataclass
class SwapProposal:
    pgid: str
    old_primary: int
    new_primary: int
    score_improvement: float
```

### 4.2 Index Structures (for Performance)

```python
# Fast lookup: which PGs have this OSD as primary?
primary_pgs_by_osd: Dict[int, Set[str]]  # osd_id -> set of pgids

# Fast lookup: which PGs contain this OSD in acting set?
pgs_by_osd: Dict[int, Set[str]]  # osd_id -> set of pgids

# Fast lookup: which OSDs are on this host?
osds_by_host: Dict[str, Set[int]]  # hostname -> set of osd_ids
```

---

## 5. Input/Output Specification

### 5.1 Input: Ceph Cluster Data

The tool collects data via these Ceph commands:

| Command | Data Extracted |
|---------|----------------|
| `ceph pg dump pgs -f json` | PG IDs, acting sets, pool IDs |
| `ceph osd tree -f json` | OSD IDs, hostnames, topology |
| `ceph osd dump -f json` | OSD weights, status |
| `ceph osd pool ls detail -f json` | Pool names, IDs |

### 5.2 Output: Analysis Summary

```
=============================================================
CEPH PRIMARY PG DISTRIBUTION ANALYSIS
=============================================================
Timestamp: 2026-02-02 14:30:00 UTC
Cluster:   ceph-prod-01

-------------------------------------------------------------
CURRENT STATE
-------------------------------------------------------------
Total PGs:              8,192
Total OSDs:             832
Total Hosts:            52

OSD-Level Distribution:
  Average primaries/OSD:    9.85
  Standard Deviation:       4.06
  Coefficient of Variation: 51.00%
  Min:   2 (OSD.417)
  Max:  24 (OSD.612)
  P5:    4
  P50:   9
  P95:  18

Host-Level Distribution:
  Average primaries/host:   157.54
  Standard Deviation:       14.87
  Coefficient of Variation: 6.00%
  Min: 132 (host-23)
  Max: 189 (host-07)

Pool-Level Distribution:
  Pool 'rbd_ssd' (ID 1):     CV = 48.2%
  Pool 'rgw_data' (ID 2):    CV = 52.1%
  Pool 'cephfs_data' (ID 3): CV = 49.8%

-------------------------------------------------------------
PROPOSED STATE (after optimization)
-------------------------------------------------------------
OSD-Level Distribution:
  Average primaries/OSD:    9.85  (unchanged)
  Standard Deviation:       0.42
  Coefficient of Variation: 4.26%
  Min:   9 (OSD.203)
  Max:  11 (OSD.612)
  P5:    9
  P50:  10
  P95:  11

Host-Level Distribution:
  Average primaries/host:   157.54 (unchanged)
  Standard Deviation:       2.10
  Coefficient of Variation: 1.33%
  Min: 154 (host-41)
  Max: 162 (host-12)

Pool-Level Distribution:
  Pool 'rbd_ssd' (ID 1):     CV = 3.9%
  Pool 'rgw_data' (ID 2):    CV = 4.5%
  Pool 'cephfs_data' (ID 3): CV = 4.1%

-------------------------------------------------------------
IMPROVEMENT SUMMARY
-------------------------------------------------------------
                        Before      After       Improvement
OSD Std Deviation:      4.06        0.42        89.7% reduction
OSD Coeff of Var:       51.00%      4.26%       
Host Std Deviation:     14.87       2.10        85.9% reduction
Host Coeff of Var:      6.00%       1.33%       
Max OSD deviation:      +143%       +12%        

-------------------------------------------------------------
CHANGES REQUIRED
-------------------------------------------------------------
Total pg-upmap-primary commands: 347
PGs affected:                    347
OSDs affected (as donor):        142
OSDs affected (as receiver):     198
Hosts affected:                  48

Changes by pool:
  rbd_ssd (ID 1):     142 changes
  rgw_data (ID 2):    118 changes
  cephfs_data (ID 3):  87 changes

-------------------------------------------------------------
TOP 10 CURRENT HOTSPOTS (donors)
-------------------------------------------------------------
OSD      Host        Current    Target    After     Change
--------------------------------------------------------------
OSD.612  host-17     24         10        10        -14
OSD.508  host-12     22         10        10        -12
OSD.391  host-07     21         10        11        -10
OSD.744  host-31     20         10        10        -10
OSD.205  host-09     20         10        10        -10
OSD.623  host-22     19         10        10        -9
OSD.417  host-14     19         10        10        -9
OSD.182  host-05     18         10        10        -8
OSD.556  host-19     18         10        10        -8
OSD.301  host-11     18         10        11        -7

-------------------------------------------------------------
TOP 10 COLDEST OSDs (receivers)
-------------------------------------------------------------
OSD      Host        Current    Target    After     Change
--------------------------------------------------------------
OSD.127  host-04     2          10        10        +8
OSD.834  host-52     2          10        9         +7
OSD.456  host-15     3          10        10        +7
OSD.089  host-03     3          10        10        +7
OSD.672  host-26     3          10        10        +7
OSD.291  host-10     4          10        10        +6
OSD.518  host-18     4          10        10        +6
OSD.743  host-30     4          10        9         +5
OSD.165  host-06     4          10        10        +6
OSD.402  host-13     4          10        10        +6

-------------------------------------------------------------
OUTPUT FILES
-------------------------------------------------------------
Analysis JSON:  ./primary_pg_analysis_20260202_143000.json
Bash script:    ./apply_primary_rebalance_20260202_143000.sh

=============================================================
```

### 5.3 Output: Executable Bash Script

```bash
#!/bin/bash
# Ceph Primary PG Rebalancing Script
# Generated: 2026-02-02 14:30:00 UTC
# Total commands: 347
# Expected OSD CV improvement: 51.00% -> 4.26%

set -e

# Safety check
echo "This script will execute 347 pg-upmap-primary commands."
echo "This changes ONLY metadata (no data movement)."
echo "Estimated impact: brief re-peering per PG (sub-second each)"
echo ""
read -p "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || exit 1

# Verify cluster health
HEALTH=$(ceph health 2>/dev/null)
if [[ ! "$HEALTH" =~ ^HEALTH_OK ]] && [[ ! "$HEALTH" =~ ^HEALTH_WARN ]]; then
    echo "WARNING: Cluster health is $HEALTH"
    read -p "Continue anyway? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 1
fi

echo "Starting primary PG rebalancing..."
echo ""

TOTAL=347
COUNT=0
FAILED=0

# Function to apply a single mapping
apply_mapping() {
    local pgid=$1
    local new_primary=$2
    ((COUNT++))
    
    if ceph osd pg-upmap-primary "$pgid" "$new_primary" 2>/dev/null; then
        printf "[%3d/%d] %-12s -> OSD.%-4d OK\n" "$COUNT" "$TOTAL" "$pgid" "$new_primary"
    else
        printf "[%3d/%d] %-12s -> OSD.%-4d FAILED\n" "$COUNT" "$TOTAL" "$pgid" "$new_primary"
        ((FAILED++))
    fi
}

# Batch 1: Pool rbd_ssd (142 changes)
echo "=== Pool: rbd_ssd (142 changes) ==="
apply_mapping "1.a3" 45
apply_mapping "1.b7" 112
apply_mapping "1.2f" 78
# ... (remaining commands)

# Batch 2: Pool rgw_data (118 changes)
echo ""
echo "=== Pool: rgw_data (118 changes) ==="
apply_mapping "2.14" 201
apply_mapping "2.8c" 334
# ... (remaining commands)

# Batch 3: Pool cephfs_data (87 changes)
echo ""
echo "=== Pool: cephfs_data (87 changes) ==="
apply_mapping "3.05" 67
apply_mapping "3.f2" 89
# ... (remaining commands)

echo ""
echo "=============================================="
echo "COMPLETE"
echo "=============================================="
echo "Total attempted: $TOTAL"
echo "Successful:      $((TOTAL - FAILED))"
echo "Failed:          $FAILED"
echo ""
echo "Run the analysis tool again to verify improvement."
```

### 5.4 Output: JSON Data Export

```json
{
  "metadata": {
    "timestamp": "2026-02-02T14:30:00Z",
    "tool_version": "1.0.0",
    "cluster_fsid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  },
  "current_state": {
    "total_pgs": 8192,
    "total_osds": 832,
    "total_hosts": 52,
    "osd_stats": {
      "mean": 9.85,
      "std_dev": 4.06,
      "cv": 0.51,
      "min": 2,
      "max": 24,
      "p5": 4,
      "p50": 9,
      "p95": 18
    },
    "host_stats": {
      "mean": 157.54,
      "std_dev": 14.87,
      "cv": 0.06
    },
    "pool_stats": {
      "1": {"name": "rbd_ssd", "cv": 0.482},
      "2": {"name": "rgw_data", "cv": 0.521},
      "3": {"name": "cephfs_data", "cv": 0.498}
    },
    "osd_details": [
      {"osd_id": 0, "host": "host-01", "primary_count": 12, "total_pgs": 98},
      {"osd_id": 1, "host": "host-01", "primary_count": 8, "total_pgs": 102}
    ]
  },
  "proposed_state": {
    "osd_stats": {
      "mean": 9.85,
      "std_dev": 0.42,
      "cv": 0.0426
    },
    "host_stats": {
      "mean": 157.54,
      "std_dev": 2.10,
      "cv": 0.0133
    }
  },
  "changes": [
    {"pgid": "1.a3", "old_primary": 12, "new_primary": 45},
    {"pgid": "1.b7", "old_primary": 12, "new_primary": 112}
  ]
}
```

---

## 6. Implementation Details

### 6.1 Module Structure

```
ceph_primary_balancer/
├── __init__.py
├── main.py                 # Entry point, CLI argument parsing
├── collector.py            # Data collection from Ceph
├── analyzer.py             # Statistical analysis
├── optimizer.py            # Greedy optimization algorithm
├── scorer.py               # Multi-dimensional scoring function
├── reporter.py             # Output generation (terminal, JSON)
├── script_generator.py     # Bash script generation
└── models.py               # Data classes (PGInfo, OSDInfo, etc.)
```

### 6.2 Key Functions

```python
# collector.py
def collect_pg_data() -> Dict[str, PGInfo]:
    """Execute 'ceph pg dump pgs -f json' and parse results."""
    
def collect_osd_topology() -> Dict[int, OSDInfo]:
    """Execute 'ceph osd tree -f json' and build OSD->host mapping."""

def collect_pool_info() -> Dict[int, PoolInfo]:
    """Execute 'ceph osd pool ls detail -f json' and parse."""

# analyzer.py
def calculate_statistics(counts: List[int]) -> Stats:
    """Calculate mean, std_dev, cv, min, max, percentiles."""

def identify_donors(osds: Dict[int, OSDInfo], threshold_pct: float) -> List[int]:
    """Return OSD IDs with primary count > threshold above average."""

def identify_receivers(osds: Dict[int, OSDInfo], threshold_pct: float) -> List[int]:
    """Return OSD IDs with primary count < threshold below average."""

# optimizer.py
def find_optimal_swaps(
    state: ClusterState,
    scorer: Scorer,
    max_iterations: int,
    target_cv: float
) -> List[SwapProposal]:
    """Greedy algorithm to find beneficial primary swaps."""

def apply_swap_to_state(state: ClusterState, swap: SwapProposal) -> ClusterState:
    """Return new state with swap applied (immutable update)."""

# scorer.py
class Scorer:
    def __init__(self, w_osd: float, w_host: float, w_pool: float):
        self.weights = (w_osd, w_host, w_pool)
    
    def calculate_score(self, state: ClusterState) -> float:
        """Composite score: lower is better."""
        
    def evaluate_swap(self, state: ClusterState, swap: SwapProposal) -> float:
        """Return score improvement (positive = better)."""

# reporter.py
def generate_summary(
    current: ClusterState,
    proposed: ClusterState,
    swaps: List[SwapProposal]
) -> str:
    """Generate human-readable summary."""

def export_json(
    current: ClusterState,
    proposed: ClusterState,
    swaps: List[SwapProposal],
    path: str
) -> None:
    """Write analysis to JSON file."""

# script_generator.py
def generate_bash_script(
    swaps: List[SwapProposal],
    pools: Dict[int, PoolInfo],
    path: str
) -> None:
    """Generate executable bash script with all pg-upmap-primary commands."""
```

### 6.3 CLI Interface

```
usage: ceph_primary_balancer.py [-h] [--target-cv TARGET_CV]
                                 [--max-changes MAX_CHANGES]
                                 [--weight-osd W_OSD]
                                 [--weight-host W_HOST]
                                 [--weight-pool W_POOL]
                                 [--output-dir OUTPUT_DIR]
                                 [--dry-run]
                                 [--json-only]

Analyze and optimize Ceph primary PG distribution.

optional arguments:
  -h, --help              show this help message and exit
  --target-cv TARGET_CV   Target coefficient of variation (default: 0.10)
  --max-changes N         Maximum number of remappings (default: unlimited)
  --weight-osd W          OSD balance weight 0.0-1.0 (default: 0.5)
  --weight-host W         Host balance weight 0.0-1.0 (default: 0.3)
  --weight-pool W         Pool balance weight 0.0-1.0 (default: 0.2)
  --output-dir DIR        Output directory (default: current directory)
  --dry-run               Analyze only, don't generate script
  --json-only             Output JSON only, no terminal summary
```

### 6.4 Error Handling

| Scenario | Handling |
|----------|----------|
| Ceph commands fail | Exit with clear error message |
| No PGs found | Exit with warning |
| Already balanced (CV < target) | Report success, no script generated |
| No valid swaps possible | Report constraint limitations |
| JSON parsing error | Exit with details for debugging |

---

## 7. Testing Strategy

### 7.1 Unit Tests

- Scoring function correctness
- Statistics calculations (known inputs/outputs)
- Swap evaluation logic
- Data structure transformations

### 7.2 Integration Tests

- Mock Ceph command output
- End-to-end flow with sample data
- Script generation validation

### 7.3 Validation with Real Cluster

1. Run tool in `--dry-run` mode
2. Verify statistics match manual calculations
3. Spot-check proposed swaps for validity (new primary in acting set)
4. Apply small batch, verify improvement
5. Full execution

---

## 8. Future Enhancements (Out of Scope for v1)

- [ ] Incremental/batched execution with monitoring
- [ ] Simulated annealing for better optimization
- [ ] Weight-proportional balancing for heterogeneous OSDs
- [ ] CRUSH topology awareness (rack, datacenter)
- [ ] Before/after comparison mode
- [ ] Integration with Prometheus/Grafana metrics
- [ ] Daemon mode for continuous balancing

---

## 9. References

- Ceph Documentation: [PG Concepts](https://docs.ceph.com/en/latest/rados/operations/placement-groups/)
- Ceph Documentation: [pg-upmap-primary](https://docs.ceph.com/en/latest/rados/operations/upmap/)
- Ceph Source: [OSDMap.cc](https://github.com/ceph/ceph/blob/main/src/osd/OSDMap.cc)

---

## 10. Appendix

### A. Sample Ceph Command Outputs

#### A.1 ceph pg dump pgs -f json (truncated)

```json
{
  "pg_stats": [
    {
      "pgid": "1.0",
      "up": [45, 12, 78],
      "acting": [45, 12, 78],
      "state": "active+clean"
    },
    {
      "pgid": "1.1",
      "up": [23, 56, 89],
      "acting": [23, 56, 89],
      "state": "active+clean"
    }
  ]
}
```

#### A.2 ceph osd tree -f json (truncated)

```json
{
  "nodes": [
    {"id": -1, "name": "default", "type": "root", "children": [-2, -3]},
    {"id": -2, "name": "host-01", "type": "host", "children": [0, 1, 2]},
    {"id": 0, "name": "osd.0", "type": "osd", "crush_weight": 3.5},
    {"id": 1, "name": "osd.1", "type": "osd", "crush_weight": 3.5}
  ]
}
```

### B. Coefficient of Variation Reference

| CV Range | Interpretation |
|----------|----------------|
| < 10% | Excellent balance |
| 10-20% | Acceptable |
| 20-30% | Moderate imbalance |
| 30-50% | Significant imbalance |
| > 50% | Severe imbalance, action required |

### C. Glossary

| Term | Definition |
|------|------------|
| PG | Placement Group - logical collection of objects |
| OSD | Object Storage Daemon - represents a storage device |
| Acting Set | List of OSDs currently storing a PG's data |
| Primary | First OSD in acting set; handles client I/O |
| CV | Coefficient of Variation (std_dev / mean) |
| Donor | OSD with too many primaries |
| Receiver | OSD with too few primaries |
