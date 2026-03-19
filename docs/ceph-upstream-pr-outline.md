# Upstream Ceph PR Outline: Multi-Dimensional Read Balancer

Outline for contributing host-aware, cross-pool read balancing to
Ceph's built-in balancer. This would extend `balance_primaries()` in
`OSDMap.cc` and the Python balancer module in `src/pybind/mgr/balancer/`.

---

## Problem Statement

Ceph's current read balancer (`balance_primaries()` in `OSDMap.cc`)
optimizes each pool independently at the OSD level. Three gaps:

1. **No host-level awareness.** Tracker #42321 notes persistent
   inter-host imbalances even after OSD-level balancing. Hosts with
   more OSDs accumulate more primaries proportionally.

2. **No cross-pool coordination.** Balancing pool A can worsen global
   OSD load if it shifts primaries onto already-overloaded OSDs.

3. **Sparse pool dead zone.** The `(prim_score - potential_score) > 1`
   guard prevents swaps in pools where most OSDs have 0–1 primaries.

## Scope

Three independent, incrementally-shippable changes. Each can be a
separate PR, or all three in a single feature branch.

---

## PR 1: Host-Aware Scoring

**Goal:** Add failure-domain-level (host/rack) primary balance as a
consideration in `balance_primaries()`.

### What changes

#### `src/osd/OSDMap.h`

- Extend `read_balance_info_t` with host-level fields:
  ```cpp
  // Host-level balance metrics
  float host_score = 1.0;        // max_host_primaries / avg_host_primaries
  float host_score_optimal = 1.0;
  ```

- Add a host primary count tracking structure (or compute on the fly
  from the CRUSH map):
  ```cpp
  // Map host -> total primaries across all OSDs on that host
  std::map<int, int> host_primary_counts;  // bucket_id -> count
  ```

#### `src/osd/OSDMap.cc`

- In `balance_primaries()`, after computing per-OSD desired counts,
  aggregate to the host level using the CRUSH hierarchy:
  ```cpp
  // CRUSH tree is already in OSDMap — use get_parent_of_type()
  // to find the host bucket for each OSD
  for (auto osd : pool_osds) {
      int host_id = crush->get_parent_of_type(osd, host_type, -1);
      host_primary_counts[host_id] += actual_primaries[osd];
  }
  ```

- Modify swap selection to add a host-awareness tie-breaker: when two
  swaps have similar OSD-level improvement, prefer the one that also
  improves host-level balance. This is a conservative change — it
  doesn't change the primary selection criterion, just the tie-breaking.

  Alternatively, a stronger version: reject swaps that would worsen
  host-level balance beyond a configurable threshold.

#### `src/pybind/mgr/balancer/module.py`

- Expose host-level metrics in `balancer status detail` output.
- Add config option `balancer_read_host_aware` (default: true).

### CRUSH topology access

The CRUSH map is embedded in the OSDMap. `OSDMap::crush` gives access
to `CrushWrapper` which provides:
- `get_parent_of_type(osd, type, -1)` — finds the host/rack/etc bucket
- `get_type_id("host")` — gets the bucket type ID for hosts
- `get_item_name(bucket_id)` — human-readable name

No new data collection needed — the topology is already there.

### Testing

- Unit test in `src/test/osd/TestOSDMap.cc`: construct a pool with
  known acting sets spanning 3 hosts, verify that host-aware scoring
  prefers cross-host swaps.
- Integration test via `qa/workunits/`: run `ceph balancer eval` before
  and after, verify host-level deviation decreases.

---

## PR 2: Cross-Pool Global OSD Tracking

**Goal:** Track total primary load per OSD across all pools and prevent
balancing one pool from overloading an OSD globally.

### What changes

#### `src/pybind/mgr/balancer/module.py`

The Python module already iterates pools sequentially. The change:

1. Before iterating pools, compute `global_osd_primaries[osd]` = total
   primaries across all pools.
2. Pass this to the C++ `balance_primaries()` call (or recompute from
   OSDMap inside C++).
3. After balancing each pool, update `global_osd_primaries` with the
   new primary assignments before moving to the next pool.

#### `src/osd/OSDMap.cc`

- Add an optional `global_osd_load` parameter to `balance_primaries()`.
  Current signature:
  ```cpp
  int OSDMap::balance_primaries(
      CephContext *cct,
      int64_t pid,
      Incremental *pending_inc,
      OSDMap& tmp_osd_map,
      const std::optional<rb_policy>& rbp = std::nullopt) const;
  ```
  Proposed addition:
  ```cpp
  int OSDMap::balance_primaries(
      CephContext *cct,
      int64_t pid,
      Incremental *pending_inc,
      OSDMap& tmp_osd_map,
      const std::optional<rb_policy>& rbp = std::nullopt,
      std::optional<std::map<int,int>> global_osd_load = std::nullopt) const;
  ```

- In the swap evaluation, add a penalty for swaps that would increase
  the new primary's global load above the global mean + threshold:
  ```cpp
  if (global_osd_load) {
      int new_global = (*global_osd_load)[new_primary] + 1;
      int global_mean = total_primaries / num_osds;
      if (new_global > global_mean * 1.1) {
          // Skip or penalize this swap
          continue;
      }
  }
  ```

### Testing

- Unit test: two pools, each with 32 PGs across 10 OSDs. Balance pool 1,
  then pool 2. With cross-pool tracking, OSD global load should be more
  balanced than without.

---

## PR 3: Sparse Pool Improvements

**Goal:** Improve balancing for pools with few PGs relative to OSD count.

### What changes

#### `src/osd/OSDMap.cc`

- Lower the swap guard from `> 1` to `> 0` (or a configurable threshold):
  ```cpp
  // Current: (prim_score - potential_score) > 1
  // Proposed: (prim_score - potential_score) > sparse_threshold
  float sparse_threshold = (mean_primaries < 2.0) ? 0.0 : 1.0;
  ```

  For sparse pools where mean primaries per OSD is < 2, the `> 1` guard
  prevents nearly all swaps. Lowering to `> 0` enables any improving
  swap. For dense pools, the `> 1` guard is still useful to avoid
  micro-optimization churn.

- Add a theoretical floor calculation (same as `pool_cv_floor`):
  ```cpp
  float optimal_cv(int num_pgs, int num_osds) {
      if (num_osds <= 1) return 0;
      float mean = (float)num_pgs / num_osds;
      float frac = mean - floor(mean);
      return sqrt(frac * (1.0 - frac)) / mean;
  }
  ```

  Skip optimization for pools already at their floor — no amount of
  swapping can improve them further.

### Testing

- Unit test: 32 PGs across 100 OSDs (sparse). With the current `> 1`
  guard, verify 0 swaps. With the new threshold, verify some swaps
  occur and the distribution improves.

---

## Implementation Strategy

### Order of PRs

1. **PR 3 (sparse pools)** first — smallest change, most contained,
   fixes a measurable gap. Good first contribution to establish context.

2. **PR 1 (host awareness)** second — moderate complexity, high impact.
   This is the feature most requested in tracker #42321.

3. **PR 2 (cross-pool)** third — requires changes to the Python/C++
   interface. Most architectural impact.

### Style and process notes

- Ceph uses the DCO (Developer Certificate of Origin) — all commits
  need `Signed-off-by` lines.
- C++ code follows Ceph style (no tabs, 2-space indent in some files,
  mixed conventions — match surrounding code).
- Python mgr modules follow PEP 8 loosely.
- PRs need a tracker issue. Reference the existing #42321 for
  host-awareness.
- Tests are expected. `make check` must pass. The `qa/` integration
  tests use teuthology.
- Functional tests live in `qa/standalone/mgr/balancer.sh`.
  Unit tests for OSDMap in `src/test/osd/TestOSDMap.cc`.

### Risk assessment

- **PR 3** is low risk — the sparse threshold is a local change in the
  swap loop. Worst case: a few extra swaps in sparse pools (which is
  the desired behavior).

- **PR 1** is moderate risk — host-level scoring is additive. If the
  host-aware tie-breaker makes suboptimal OSD-level choices, the safety
  net (discard all if score didn't improve) catches it.

- **PR 2** is highest risk — cross-pool tracking changes the Python/C++
  interface and the module's pool iteration logic. Needs careful review
  from the balancer maintainers (Laura Flores, Josh Salomon).

### Relationship to ceph_primary_balancer

This tool validates the algorithmic ideas outside the Ceph codebase.
The upstream PRs would implement a subset of these ideas in C++ within
Ceph's existing architecture:

| Feature | ceph_primary_balancer | Upstream PR |
|---|---|---|
| CV-based composite scoring | Full 3D composite | Per-dimension metrics, not composite |
| Host awareness | Host CV dimension | Host-aware tie-breaking or penalty |
| Cross-pool | Simultaneous optimization | Sequential with global load tracking |
| Sparse pools | Adaptive thresholds + CV floor | Lowered swap guard + floor estimation |
| Dynamic weights | Two-phase + target_distance | Not proposed (too complex for first contribution) |
| Focused fallback | Single-dimension escape | Not proposed |
| Stagnation detection | Rolling window | Not proposed |

The upstream contributions would be intentionally conservative — simpler
versions of ideas proven in this tool, compatible with Ceph's existing
architecture and safety nets.
