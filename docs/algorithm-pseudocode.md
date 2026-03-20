# Core Balancing Algorithm — Pseudocode

Pseudocode for the primary PG balancing algorithm. Covers only the core
balancing logic: data model, scoring, donor/receiver identification,
swap search, and the optimization loop. No CLI, config, offline mode,
JSON export, reporting, or optional features.

This document is intended to enable cleanroom reimplementation in any
language (C++, Rust, Python, etc.).

---

## Data Model

```
PG:
    pgid: string              # e.g. "3.a1"
    pool_id: int
    acting: list[int]         # OSD IDs; acting[0] is always the primary

OSD:
    osd_id: int
    host: string
    primary_count: int        # number of PGs where this OSD is primary

Host:
    hostname: string
    osd_ids: list[int]
    primary_count: int        # sum of primary_count across all OSDs on host

Pool:
    pool_id: int
    pool_name: string
    pg_count: int
    primary_counts: map[int, int]   # osd_id -> primary count in this pool
    participating_osds: set[int]    # all OSDs appearing in any acting set for this pool

ClusterState:
    pgs: map[string, PG]
    osds: map[int, OSD]
    hosts: map[string, Host]
    pools: map[int, Pool]

SwapProposal:
    pgid: string
    old_primary: int
    new_primary: int
    score_improvement: float
```

## Scoring

The composite score is a weighted sum of coefficient of variation (CV)
across three dimensions. CV = std_dev / mean, which is scale-invariant
and makes dimensions comparable.

```
Score = w_osd * OSD_CV + w_host * Host_CV + w_pool * Pool_CV

where:
    OSD_CV  = CV of primary_count across all OSDs
    Host_CV = CV of primary_count across all hosts
    Pool_CV = PG-weighted average of per-pool CVs (see below)
```

Default weights: `w_osd=0.50, w_host=0.30, w_pool=0.20`.

### Pool CV calculation

```
function pool_cv_floor(num_pgs, num_participating_osds):
    # Theoretical minimum CV given integer primary counts
    k = num_pgs
    n = num_participating_osds
    if n <= 1 or k <= 0: return 0
    if k < n:
        return sqrt((n - k) / k)
    mean = k / n
    frac = mean - floor(mean)
    return sqrt(frac * (1 - frac)) / mean

UNBALANCEABLE_CV_FLOOR = 0.50

function weighted_avg_pool_cv(state):
    weighted_sum = 0
    total_weight = 0
    for each pool in state.pools:
        n = len(pool.participating_osds)

        # Skip pools too sparse to balance — they'd dominate the average
        if pool_cv_floor(pool.pg_count, n) > UNBALANCEABLE_CV_FLOOR:
            continue

        # Build count vector including zeros for participating OSDs
        # without primaries — critical for correct variance
        counts = [pool.primary_counts.get(osd_id, 0)
                  for osd_id in pool.participating_osds]
        cv = std_dev(counts) / mean(counts) if mean(counts) > 0 else 0

        w = max(pool.pg_count, 1)
        weighted_sum += cv * w
        total_weight += w

    return weighted_sum / total_weight if total_weight > 0 else 0
```

### O(1) delta scoring

Swap evaluation must be O(1), not O(N). Mean doesn't change during a
swap (total count is conserved), so we only need the variance delta.

```
function score_after_swap(state, components, old_primary, new_primary, pool_id):
    # components = cached {var, mean, cv} per dimension from last full calculation
    delta = 0

    # --- OSD dimension ---
    n = len(state.osds)
    if n > 1 and components.osd_mean > 0:
        old_count = state.osds[old_primary].primary_count
        new_count = state.osds[new_primary].primary_count
        # Variance delta when one element decreases by 1 and another increases by 1:
        # Δvar = 2 * (new_count - old_count + 1) / (n - 1)
        delta_var = 2 * (new_count - old_count + 1) / (n - 1)
        new_var = max(0, components.osd_var + delta_var)
        new_cv = sqrt(new_var) / components.osd_mean
        delta += w_osd * (new_cv - components.osd_cv)

    # --- Host dimension (only if different hosts) ---
    old_host = state.osds[old_primary].host
    new_host = state.osds[new_primary].host
    if old_host != new_host:
        n = len(state.hosts)
        if n > 1 and components.host_mean > 0:
            old_host_count = state.hosts[old_host].primary_count
            new_host_count = state.hosts[new_host].primary_count
            delta_var = 2 * (new_host_count - old_host_count + 1) / (n - 1)
            new_var = max(0, components.host_var + delta_var)
            new_cv = sqrt(new_var) / components.host_mean
            delta += w_host * (new_cv - components.host_cv)

    # --- Pool dimension (only for the affected pool) ---
    if pool_id not in excluded_pools:
        a = pool.primary_counts.get(old_primary, 0)
        b = pool.primary_counts.get(new_primary, 0)
        # sum-of-squares delta: old_primary goes a→a-1, new_primary goes b→b+1
        new_ss = components.pool_sum_sq[pool_id] + 2 * (b - a + 1)
        s = components.pool_total[pool_id]       # sum unchanged
        n = components.pool_n[pool_id]            # participating count unchanged
        if n > 1:
            new_var = (new_ss - s*s/n) / (n - 1)
            new_cv = sqrt(max(0, new_var)) / components.pool_mean[pool_id]
        else:
            new_cv = 0
        old_cv = components.pool_cv[pool_id]
        # Update weighted average: only this pool's CV changed
        delta += w_pool * pool_pg_weight[pool_id] * (new_cv - old_cv) / total_pool_pg_weight

    return components.total + delta
```

### Variance delta derivation

When element `i` changes from `x_i` to `x_i + d` in a sample of size `n`:

```
new_var = old_var + d * (2*x_i + d) / (n - 1)
```

A primary swap decreases `old_primary` by 1 and increases `new_primary` by 1.
Combined effect on variance:

```
Δvar = [(-1)(2*old_count - 1) + (+1)(2*new_count + 1)] / (n - 1)
     = 2 * (new_count - old_count + 1) / (n - 1)
```

This is exact for sample variance. Mean is unchanged because total count
is conserved.


## Donor/Receiver Identification

### OSD-level

```
function identify_donors(osds, threshold_pct=0.10):
    mean = average(osd.primary_count for osd in osds)
    return [osd_id for osd_id, osd in osds
            if osd.primary_count > mean * (1 + threshold_pct)]

function identify_receivers(osds, threshold_pct=0.10):
    mean = average(osd.primary_count for osd in osds)
    return [osd_id for osd_id, osd in osds
            if osd.primary_count < mean * (1 - threshold_pct)]
```

### Per-pool

```
function identify_pool_donors_receivers(state, threshold_pct=0.10):
    pool_donors = {}
    pool_receivers = {}

    for each pool in state.pools:
        participating = pool.participating_osds
        if len(participating) < 2: continue

        total = sum(pool.primary_counts.values())
        mean = total / len(participating)
        if mean == 0: continue

        # Adaptive threshold for small pools: absolute ±1 prevents
        # dead zones where no OSD qualifies
        if 1 <= mean < 10:
            hi = mean + 1
            lo = mean - 1
        else:
            hi = mean * (1 + threshold_pct)
            lo = mean * (1 - threshold_pct)

        for osd_id in participating:
            count = pool.primary_counts.get(osd_id, 0)
            if count > hi: pool_donors[pool_id].add(osd_id)
            if count < lo: pool_receivers[pool_id].add(osd_id)

    return pool_donors, pool_receivers
```


## Swap Search

Three search tiers, each progressively broader:

### Tier 1: Donor/receiver filtered search

```
function find_best_swap(state, donors, receivers, scorer,
                        pool_donors, pool_receivers, components):
    current_score = components.total
    best_swap = None
    best_improvement = 0

    for each pg in state.pgs:
        # Primary must be a donor at OSD-level OR pool-level for this pool
        if pg.primary not in donors
           and pg.primary not in pool_donors.get(pg.pool_id, {}):
            continue

        for candidate in pg.acting[1:]:  # non-primary members of acting set
            # Candidate must be a receiver at OSD-level OR pool-level
            if candidate not in receivers
               and candidate not in pool_receivers.get(pg.pool_id, {}):
                continue

            new_score = score_after_swap(state, components,
                                         pg.primary, candidate, pg.pool_id)
            improvement = current_score - new_score

            # Tie-breaker: 1% bonus for cross-host swaps (only when improving)
            if improvement > 0 and osds are on different hosts:
                improvement *= 1.01

            if improvement > best_improvement:
                best_improvement = improvement
                best_swap = {pg, pg.primary, candidate, improvement}

    return best_swap
```

### Tier 2: Per-pool exhaustive search

Targets pools with CV above target. No donor/receiver filter — catches
swaps that tier 1 misses for small/imbalanced pools.

```
function find_best_pool_swap(state, scorer, target_cv, pool_pgs, components):
    best_swap = None
    best_improvement = 0

    for pool_id, pool_cv in components.pool_cvs:
        if pool_cv <= target_cv: continue

        # Skip pools at their theoretical CV floor (within 2% margin)
        n = len(pool.participating_osds)
        floor = pool_cv_floor(pool.pg_count, n)
        if floor > 0 and pool_cv <= floor * 1.02: continue

        for pg in pool_pgs[pool_id]:
            for candidate in pg.acting[1:]:
                new_score = score_after_swap(state, components,
                                             pg.primary, candidate, pg.pool_id)
                improvement = current_score - new_score
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_swap = {pg, pg.primary, candidate, improvement}

    return best_swap
```

### Tier 3: Focused fallback (local minima escape)

When tiers 1+2 find nothing, targets the single worst dimension.
Accepts bounded composite regression.

```
function find_best_focused_swap(state, scorer, target_cv,
                                max_regression=0.001, components):
    # Find dimension furthest above target
    gaps = []
    if osd_cv > target_cv:  gaps.append(("osd", osd_cv - target_cv))
    if host_cv > target_cv: gaps.append(("host", host_cv - target_cv))
    if pool_cv > target_cv: gaps.append(("pool", pool_cv - target_cv))
    if not gaps: return None

    focus_dim = dimension with largest gap

    # Create single-dimension scorer for focused search
    focused_scorer = Scorer(weight=1.0 only for focus_dim)
    focused_components = focused_scorer.calculate_components(state)

    best_swap = None
    best_focused_improvement = 0

    for each pg in state.pgs:
        for candidate in pg.acting[1:]:
            # Must improve the focused dimension
            focused_improvement = focused_score - focused_scorer.delta(...)
            if focused_improvement <= 0: continue

            # Composite regression must be bounded
            composite_delta = scorer.delta(...) - current_score
            if composite_delta > max_regression: continue

            if focused_improvement > best_focused_improvement:
                best_focused_improvement = focused_improvement
                best_swap = {pg, pg.primary, candidate, -composite_delta}

    return best_swap
```

## Applying a Swap

```
function apply_swap(state, swap):
    pg = state.pgs[swap.pgid]

    # Update acting set: move new_primary to position 0
    pg.acting.remove(swap.new_primary)
    pg.acting.insert(0, swap.new_primary)

    # Update OSD primary counts
    state.osds[swap.old_primary].primary_count -= 1
    state.osds[swap.new_primary].primary_count += 1

    # Update host primary counts
    state.hosts[old_osd.host].primary_count -= 1
    state.hosts[new_osd.host].primary_count += 1

    # Update pool primary counts
    pool = state.pools[pg.pool_id]
    pool.primary_counts[swap.old_primary] -= 1
    if pool.primary_counts[swap.old_primary] == 0:
        delete pool.primary_counts[swap.old_primary]
    pool.primary_counts[swap.new_primary] += 1  # default 0 if absent
```


## Dynamic Weights (Two-Phase Strategy)

Periodically recalculate scoring weights based on current CVs. The
two-phase strategy hard-switches to pool-focused weights once OSD and
host are "good enough".

```
every N iterations:
    osd_cv, host_cv, pool_cv = current CVs

    # Subtract OSD's integer floor so strategy sees only improvable gap
    osd_floor = osd_cv_floor(mean_primaries_per_osd)
    effective_osd_cv = max(0, osd_cv - osd_floor)

    threshold = max(2 * target_cv, 0.15)

    if effective_osd_cv <= threshold and host_cv <= threshold:
        # Pool-focused phase: OSD/host already converged
        weights = (0.10, 0.05, 0.85)
    else:
        # Convergence phase: proportional to distance from target
        osd_dist  = max(0, effective_osd_cv - target_cv)
        host_dist = max(0, host_cv - target_cv)
        pool_dist = max(0, pool_cv - target_cv)
        total = osd_dist + host_dist + pool_dist
        weights = (osd_dist/total, host_dist/total, pool_dist/total)
        # Enforce minimum weight floor (0.05) to prevent dimension neglect
```


## Main Optimization Loop

```
function optimize(state):
    swaps = []

    # Cache pool→PG index (pool membership never changes across swaps)
    pool_pgs = group state.pgs by pool_id

    # Stall detection state
    fallback_window = []              # rolling window of was-focused-fallback flags
    fallback_dim_cvs_at_start = None

    # Stagnation detection state
    stagnation_cvs_at_start = None
    stagnation_window_iter = 0

    for iteration in 0..max_iterations:

        # --- Termination: all enabled dimensions at or below target ---
        if all_dimensions_below_target(state):
            break

        # --- Identify donors/receivers ---
        donors = identify_donors(state.osds, threshold=10%)
        receivers = identify_receivers(state.osds, threshold=10%)
        pool_donors, pool_receivers = identify_pool_donors_receivers(state)

        # --- Compute score components once for this iteration ---
        components = scorer.calculate_components(state)

        # --- Three-tier swap search ---

        # Tier 1: donor/receiver filtered
        swap = find_best_swap(state, donors, receivers, scorer,
                              pool_donors, pool_receivers, components)

        # If tier 1 fails, retry with relaxed threshold (0%)
        if swap is None:
            relaxed_donors = identify_donors(state.osds, threshold=0%)
            relaxed_receivers = identify_receivers(state.osds, threshold=0%)
            relaxed_pool_d, relaxed_pool_r = identify_pool_donors_receivers(state, 0%)
            swap = find_best_swap(state, relaxed_donors, relaxed_receivers,
                                  scorer, relaxed_pool_d, relaxed_pool_r, components)

        # Tier 2: per-pool exhaustive (compare with tier 1 result)
        pool_swap = find_best_pool_swap(state, scorer, target_cv,
                                        pool_pgs, components)
        if pool_swap is not None:
            if swap is None or pool_swap.improvement > swap.improvement:
                swap = pool_swap

        # Tier 3: focused fallback (only if tiers 1+2 found nothing)
        used_focused_fallback = false
        if swap is None:
            swap = find_best_focused_swap(state, scorer, target_cv,
                                          max_regression=0.001, components)
            if swap is not None:
                used_focused_fallback = true

        # No swap found anywhere — done
        if swap is None:
            break

        # --- Stall detection (focused fallback churning) ---
        fallback_window.append(used_focused_fallback)
        if len(fallback_window) > 20: fallback_window.pop(0)

        if count(true in fallback_window) >= 10:
            if no dimension above target improved >= 1% since window start:
                break  # stalled
            else:
                reset window

        # --- Apply swap ---
        apply_swap(state, swap)
        swaps.append(swap)

        # --- Stagnation detection (rolling 50-iteration window) ---
        post_components = scorer.calculate_components(state)
        current_cvs = {osd: post_components.osd_cv,
                       host: post_components.host_cv,
                       pool: post_components.avg_pool_cv}

        if stagnation_cvs_at_start is None:
            stagnation_cvs_at_start = current_cvs
            stagnation_window_iter = iteration
        elif iteration - stagnation_window_iter >= 50:
            if no dimension above target improved >= 1%:
                break  # stagnated
            else:
                reset stagnation window

    return swaps
```

## Output

For each swap in the result list, emit:

```bash
ceph osd pg-upmap-primary <pgid> <new_primary>
```

This changes which OSD in the acting set serves as primary for that PG.
No data movement occurs — all OSDs in the acting set already hold the data.
