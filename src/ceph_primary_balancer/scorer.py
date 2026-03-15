"""
Multi-dimensional scoring module for the Ceph Primary PG Balancer.

This module implements composite scoring across multiple dimensions:
- OSD-level variance (prevents individual OSD hotspots)
- Host-level variance (prevents network/node bottlenecks)
- Pool-level variance (ensures per-pool balance)

The scorer allows configurable weights to prioritize different optimization goals.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .models import ClusterState, Statistics
from .analyzer import calculate_statistics, calculate_average_pool_variance


@dataclass
class ScoreComponents:
    """Cached score components for O(1) delta scoring.

    Stores both variance and CV for each dimension. The score uses CV
    (coefficient of variation = std/mean) which is scale-invariant, making
    dimensions comparable regardless of their absolute magnitude. Variance
    and mean are cached so delta scoring can compute new CV in O(1).
    """
    osd_var: float = 0.0
    osd_mean: float = 0.0
    osd_cv: float = 0.0
    host_var: float = 0.0
    host_mean: float = 0.0
    host_cv: float = 0.0
    pool_vars: Dict[int, float] = field(default_factory=dict)  # pool_id -> variance
    pool_means: Dict[int, float] = field(default_factory=dict)  # pool_id -> mean
    pool_cvs: Dict[int, float] = field(default_factory=dict)    # pool_id -> CV
    avg_pool_cv: float = 0.0
    total: float = 0.0
    # Per-pool cached values for O(1) pool variance delta
    pool_sum_sq: Dict[int, int] = field(default_factory=dict)   # pool_id -> sum of squared counts
    pool_total: Dict[int, int] = field(default_factory=dict)    # pool_id -> sum of counts
    pool_n: Dict[int, int] = field(default_factory=dict)        # pool_id -> number of OSDs with primaries


class Scorer:
    """
    Multi-dimensional scoring engine for evaluating cluster balance.
    
    The scorer calculates a composite score based on variance across different
    dimensions. Lower scores indicate better balance. Weights control the
    relative importance of each dimension.
    
    Phase 6.5: Supports configurable optimization levels to enable/disable
    specific dimensions, allowing for performance optimization and targeted
    balancing strategies.
    
    Attributes:
        w_osd: Weight for OSD-level variance (default: 0.5)
        w_host: Weight for host-level variance (default: 0.3)
        w_pool: Weight for pool-level variance (default: 0.2)
        enabled_levels: Set of enabled optimization levels
    """
    
    def __init__(
        self,
        w_osd: float = 0.5,
        w_host: float = 0.3,
        w_pool: float = 0.2,
        enabled_levels: Optional[List[str]] = None
    ):
        """
        Initialize the scorer with dimension weights and enabled levels.
        
        Phase 2 defaults: 50% OSD, 30% Host, 20% Pool for balanced optimization.
        Phase 6.5: Supports selective dimension enabling via enabled_levels.
        
        Args:
            w_osd: Weight for OSD-level variance (0.0 to 1.0)
            w_host: Weight for host-level variance (0.0 to 1.0)
            w_pool: Weight for pool-level variance (0.0 to 1.0)
            enabled_levels: List of enabled levels (None = all enabled).
                          Valid values: 'osd', 'host', 'pool'
        
        Raises:
            ValueError: If weights are negative, validation fails, or no levels enabled
        """
        # Determine enabled levels
        if enabled_levels is None:
            enabled_levels = ['osd', 'host', 'pool']
        
        self.enabled_levels = set(enabled_levels)
        
        # Validate at least one level is enabled
        if not self.enabled_levels:
            raise ValueError("At least one optimization level must be enabled")
        
        # Validate level names
        valid_levels = {'osd', 'host', 'pool'}
        for level in self.enabled_levels:
            if level not in valid_levels:
                raise ValueError(
                    f"Invalid optimization level '{level}'. "
                    f"Valid levels: {', '.join(sorted(valid_levels))}"
                )
        
        # Collect weights for enabled levels only
        if w_osd < 0 or w_host < 0 or w_pool < 0:
            raise ValueError("Weights must be non-negative")
        
        weights = {}
        if 'osd' in self.enabled_levels:
            weights['osd'] = w_osd
        if 'host' in self.enabled_levels:
            weights['host'] = w_host
        if 'pool' in self.enabled_levels:
            weights['pool'] = w_pool
        
        total = sum(weights.values())
        if total == 0:
            raise ValueError("Total weight of enabled levels cannot be zero")
        
        # Normalize to sum to 1.0 for enabled levels only
        self.w_osd = weights.get('osd', 0.0) / total if 'osd' in self.enabled_levels else 0.0
        self.w_host = weights.get('host', 0.0) / total if 'host' in self.enabled_levels else 0.0
        self.w_pool = weights.get('pool', 0.0) / total if 'pool' in self.enabled_levels else 0.0
    
    def calculate_osd_variance(self, state: ClusterState) -> float:
        """
        Calculate variance of primary counts across all OSDs.
        
        Args:
            state: Current cluster state
        
        Returns:
            float: Variance (squared standard deviation) of OSD primary counts
        """
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        if not primary_counts:
            return 0.0
        
        # Calculate variance = std_dev^2
        stats = calculate_statistics(primary_counts)
        return stats.std_dev ** 2
    
    def calculate_host_variance(self, state: ClusterState) -> float:
        """
        Calculate variance of primary counts across all hosts.
        
        Args:
            state: Current cluster state
        
        Returns:
            float: Variance (squared standard deviation) of host primary counts
        """
        if not state.hosts:
            return 0.0
        
        primary_counts = [host.primary_count for host in state.hosts.values()]
        if not primary_counts:
            return 0.0
        
        # Calculate variance = std_dev^2
        stats = calculate_statistics(primary_counts)
        return stats.std_dev ** 2
    
    def calculate_pool_variance(self, state: ClusterState) -> float:
        """
        Calculate average variance of primary counts across all pools.
        
        For each pool, calculates the variance of primary distribution across
        OSDs that have PGs from that pool. Returns the average of these variances.
        
        This metric ensures that primaries are balanced within each pool independently,
        which is important for workload isolation and per-pool performance.
        
        Args:
            state: Current cluster state
        
        Returns:
            float: Average variance across all pools (0.0 if no pools)
        """
        return calculate_average_pool_variance(state)
    
    def calculate_score(self, state: ClusterState) -> float:
        """
        Calculate composite balance score using CV (coefficient of variation).

        Uses CV = std_dev / mean for each dimension, which is scale-invariant.
        This makes dimensions comparable regardless of their absolute magnitude
        (e.g., 100 OSDs with small counts vs 10 hosts with large counts).

        Score = Σ(weight × CV) for enabled dimensions only.
        Lower scores indicate better overall balance.

        Args:
            state: Current cluster state

        Returns:
            float: Composite score (lower is better)
        """
        import math
        score = 0.0

        if 'osd' in self.enabled_levels:
            osd_var = self.calculate_osd_variance(state)
            primary_counts = [osd.primary_count for osd in state.osds.values()]
            mean = sum(primary_counts) / len(primary_counts) if primary_counts else 0.0
            osd_cv = math.sqrt(osd_var) / mean if mean > 0 else 0.0
            score += self.w_osd * osd_cv

        if 'host' in self.enabled_levels:
            host_var = self.calculate_host_variance(state)
            if state.hosts:
                host_counts = [h.primary_count for h in state.hosts.values()]
                mean = sum(host_counts) / len(host_counts) if host_counts else 0.0
                host_cv = math.sqrt(host_var) / mean if mean > 0 else 0.0
            else:
                host_cv = 0.0
            score += self.w_host * host_cv

        if 'pool' in self.enabled_levels:
            pool_cvs = []
            if state.pools:
                for pool in state.pools.values():
                    counts = [c for oid, c in pool.primary_counts.items() if oid in state.osds]
                    if len(counts) > 1:
                        stats = calculate_statistics(counts)
                        pool_cvs.append(stats.cv)
                    elif len(counts) == 1:
                        pool_cvs.append(0.0)
            avg_pool_cv = sum(pool_cvs) / len(pool_cvs) if pool_cvs else 0.0
            score += self.w_pool * avg_pool_cv

        return score
    
    def calculate_score_with_components(self, state: ClusterState) -> ScoreComponents:
        """Calculate CV-based score and cache variance/mean for O(1) delta scoring."""
        import math
        components = ScoreComponents()

        if 'osd' in self.enabled_levels:
            components.osd_var = self.calculate_osd_variance(state)
            primary_counts = [osd.primary_count for osd in state.osds.values()]
            components.osd_mean = sum(primary_counts) / len(primary_counts) if primary_counts else 0.0
            components.osd_cv = math.sqrt(components.osd_var) / components.osd_mean if components.osd_mean > 0 else 0.0

        if 'host' in self.enabled_levels:
            components.host_var = self.calculate_host_variance(state)
            if state.hosts:
                host_counts = [h.primary_count for h in state.hosts.values()]
                components.host_mean = sum(host_counts) / len(host_counts) if host_counts else 0.0
                components.host_cv = math.sqrt(components.host_var) / components.host_mean if components.host_mean > 0 else 0.0

        if 'pool' in self.enabled_levels and state.pools:
            for pool in state.pools.values():
                counts = [c for osd_id, c in pool.primary_counts.items() if osd_id in state.osds]
                n = len(counts)
                if n > 1:
                    s = sum(counts)
                    ss = sum(c * c for c in counts)
                    var = (ss - s * s / n) / (n - 1)
                    mean = s / n
                    components.pool_vars[pool.pool_id] = var
                    components.pool_means[pool.pool_id] = mean
                    components.pool_cvs[pool.pool_id] = math.sqrt(var) / mean if mean > 0 else 0.0
                    components.pool_sum_sq[pool.pool_id] = ss
                    components.pool_total[pool.pool_id] = s
                    components.pool_n[pool.pool_id] = n
                elif n == 1:
                    components.pool_vars[pool.pool_id] = 0.0
                    components.pool_means[pool.pool_id] = float(counts[0])
                    components.pool_cvs[pool.pool_id] = 0.0
                    components.pool_sum_sq[pool.pool_id] = counts[0] * counts[0]
                    components.pool_total[pool.pool_id] = counts[0]
                    components.pool_n[pool.pool_id] = 1
            if components.pool_cvs:
                components.avg_pool_cv = sum(components.pool_cvs.values()) / len(components.pool_cvs)

        components.total = (
            self.w_osd * components.osd_cv
            + self.w_host * components.host_cv
            + self.w_pool * components.avg_pool_cv
        )
        return components

    def calculate_swap_delta(
        self,
        state: ClusterState,
        components: ScoreComponents,
        old_primary: int,
        new_primary: int,
        pool_id: int,
    ) -> float:
        """
        Compute CV-based score delta for a proposed swap in O(1).

        Mean doesn't change during a swap (total count unchanged per dimension),
        so new_cv = sqrt(max(0, old_var + delta_var)) / mean.

        Returns the NEW score. Lower is better.
        """
        import math
        delta = 0.0

        # OSD dimension: compute new CV from variance delta
        if 'osd' in self.enabled_levels:
            n = len(state.osds)
            if n > 1 and components.osd_mean > 0:
                old_count = state.osds[old_primary].primary_count
                new_count = state.osds[new_primary].primary_count
                delta_osd_var = 2.0 * (new_count - old_count + 1) / (n - 1)
                new_osd_var = max(0.0, components.osd_var + delta_osd_var)
                new_osd_cv = math.sqrt(new_osd_var) / components.osd_mean
                delta += self.w_osd * (new_osd_cv - components.osd_cv)

        # Host dimension: same approach, but only if different hosts
        if 'host' in self.enabled_levels and state.hosts:
            old_host = state.osds[old_primary].host
            new_host = state.osds[new_primary].host
            if old_host and new_host and old_host != new_host:
                n = len(state.hosts)
                if n > 1 and components.host_mean > 0:
                    old_host_count = state.hosts[old_host].primary_count
                    new_host_count = state.hosts[new_host].primary_count
                    delta_host_var = 2.0 * (new_host_count - old_host_count + 1) / (n - 1)
                    new_host_var = max(0.0, components.host_var + delta_host_var)
                    new_host_cv = math.sqrt(new_host_var) / components.host_mean
                    delta += self.w_host * (new_host_cv - components.host_cv)

        # Pool dimension: compute new per-pool CV from variance delta
        if 'pool' in self.enabled_levels and state.pools and pool_id in state.pools:
            pool = state.pools[pool_id]
            old_pool_cv = components.pool_cvs.get(pool_id, 0.0)

            a = pool.primary_counts.get(old_primary, 0)
            b = pool.primary_counts.get(new_primary, 0)

            ss = components.pool_sum_sq.get(pool_id, 0)
            s = components.pool_total.get(pool_id, 0)
            n = components.pool_n.get(pool_id, 0)
            pool_mean = components.pool_means.get(pool_id, 0.0)

            # After swap: old_primary goes a->a-1, new_primary goes b->b+1
            new_ss = ss + 2 * (b - a + 1)
            new_n = n
            if a == 1:
                new_n -= 1
            if b == 0:
                new_n += 1

            if new_n > 1:
                new_pool_var = (new_ss - s * s / new_n) / (new_n - 1)
                # Mean changes if n changes (same total, different count)
                new_pool_mean = s / new_n if new_n > 0 else 0.0
                new_pool_cv = math.sqrt(max(0.0, new_pool_var)) / new_pool_mean if new_pool_mean > 0 else 0.0
            else:
                new_pool_cv = 0.0

            num_pools = len(components.pool_cvs) if components.pool_cvs else 1
            if pool_id not in components.pool_cvs:
                num_pools_new = num_pools + 1
                delta_avg = (sum(components.pool_cvs.values()) + new_pool_cv) / num_pools_new - components.avg_pool_cv
            elif num_pools > 0:
                delta_avg = (new_pool_cv - old_pool_cv) / num_pools
            else:
                delta_avg = 0.0
            delta += self.w_pool * delta_avg

        return components.total + delta

    def is_level_enabled(self, level: str) -> bool:
        """Check if a specific optimization level is enabled.
        
        Args:
            level: Level name ('osd', 'host', or 'pool')
        
        Returns:
            bool: True if level is enabled, False otherwise
        """
        return level in self.enabled_levels
    
    def get_enabled_levels(self) -> List[str]:
        """Get list of enabled optimization levels.
        
        Returns:
            List[str]: Sorted list of enabled level names
        """
        return sorted(self.enabled_levels)
    
    def get_statistics_multi_level(self, state: ClusterState) -> Dict[str, Statistics]:
        """
        Calculate statistics at all dimensions for reporting.
        
        Returns detailed statistics for OSD-level, host-level, and pool-level
        distributions. Useful for comprehensive reporting and analysis.
        
        Args:
            state: Current cluster state
        
        Returns:
            Dict mapping dimension name to Statistics object:
            - 'osd': OSD-level primary distribution statistics
            - 'host': Host-level primary distribution statistics
            - 'pool': Pool-level statistics (Phase 2, empty for Phase 1)
        """
        stats = {}
        
        # OSD-level statistics
        osd_counts = [osd.primary_count for osd in state.osds.values()]
        if osd_counts:
            stats['osd'] = calculate_statistics(osd_counts)
        
        # Host-level statistics
        if state.hosts:
            host_counts = [host.primary_count for host in state.hosts.values()]
            if host_counts:
                stats['host'] = calculate_statistics(host_counts)
        
        # Pool-level statistics
        if state.pools:
            from .analyzer import get_pool_statistics_summary
            pool_stats_dict = get_pool_statistics_summary(state)
            if pool_stats_dict:
                # Calculate average CV across all pools for summary
                pool_cvs = [ps.cv for ps in pool_stats_dict.values()]
                if pool_cvs:
                    avg_pool_cv = sum(pool_cvs) / len(pool_cvs)
                    avg_pool_std = sum(ps.std_dev for ps in pool_stats_dict.values()) / len(pool_stats_dict)
                    # Create a summary Statistics object for pool level
                    stats['pool'] = Statistics(
                        mean=avg_pool_std,  # Use avg std_dev as a proxy for mean variance
                        std_dev=avg_pool_std,
                        cv=avg_pool_cv,
                        min_val=0,
                        max_val=0,
                        p50=0.0
                    )
        
        return stats
