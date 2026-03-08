"""
Multi-dimensional scoring module for the Ceph Primary PG Balancer.

This module implements composite scoring across multiple dimensions:
- OSD-level variance (prevents individual OSD hotspots)
- Host-level variance (prevents network/node bottlenecks)
- Pool-level variance (ensures per-pool balance)

The scorer allows configurable weights to prioritize different optimization goals.
"""

import statistics as stats_module
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .models import ClusterState, Statistics
from .analyzer import calculate_statistics, calculate_average_pool_variance


@dataclass
class ScoreComponents:
    """Cached score components for O(1) delta scoring."""
    osd_var: float = 0.0
    host_var: float = 0.0
    pool_vars: Dict[int, float] = field(default_factory=dict)  # pool_id -> variance
    avg_pool_var: float = 0.0
    total: float = 0.0


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
        Calculate composite balance score for the cluster state.
        
        The score is a weighted sum of variances across enabled dimensions only.
        Disabled dimensions are completely skipped (not just weighted to 0).
        Lower scores indicate better overall balance.
        
        Phase 6.5: Only calculates variance for enabled dimensions, providing
        performance optimization by skipping unnecessary computations.
        
        Score = Σ(weight × variance) for enabled dimensions only
        
        Args:
            state: Current cluster state
        
        Returns:
            float: Composite score (lower is better)
        """
        score = 0.0
        
        # Only calculate if enabled (skip computation for disabled dimensions)
        if 'osd' in self.enabled_levels:
            osd_var = self.calculate_osd_variance(state)
            score += self.w_osd * osd_var
        
        if 'host' in self.enabled_levels:
            host_var = self.calculate_host_variance(state)
            score += self.w_host * host_var
        
        if 'pool' in self.enabled_levels:
            pool_var = self.calculate_pool_variance(state)
            score += self.w_pool * pool_var
        
        return score
    
    def calculate_score_with_components(self, state: ClusterState) -> ScoreComponents:
        """Calculate score and cache individual variance components for delta scoring."""
        components = ScoreComponents()

        if 'osd' in self.enabled_levels:
            components.osd_var = self.calculate_osd_variance(state)

        if 'host' in self.enabled_levels:
            components.host_var = self.calculate_host_variance(state)

        if 'pool' in self.enabled_levels and state.pools:
            from .analyzer import calculate_pool_statistics
            for pool in state.pools.values():
                if pool.primary_counts:
                    try:
                        ps = calculate_pool_statistics(pool, state.osds)
                        components.pool_vars[pool.pool_id] = ps.std_dev ** 2
                    except ValueError:
                        continue
            if components.pool_vars:
                components.avg_pool_var = sum(components.pool_vars.values()) / len(components.pool_vars)

        components.total = (
            self.w_osd * components.osd_var
            + self.w_host * components.host_var
            + self.w_pool * components.avg_pool_var
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
        Compute score delta for a proposed swap in O(1) for OSD/host, O(p) for pool.

        Returns the NEW score (components.total + delta). Lower is better.
        """
        delta = 0.0

        # OSD dimension: delta_var = 2*(new_count - old_count + 1) / (n-1)
        if 'osd' in self.enabled_levels:
            n = len(state.osds)
            if n > 1:
                old_count = state.osds[old_primary].primary_count
                new_count = state.osds[new_primary].primary_count
                delta_osd_var = 2.0 * (new_count - old_count + 1) / (n - 1)
                delta += self.w_osd * delta_osd_var

        # Host dimension: same formula, but only if different hosts
        if 'host' in self.enabled_levels and state.hosts:
            old_host = state.osds[old_primary].host
            new_host = state.osds[new_primary].host
            if old_host and new_host and old_host != new_host:
                n = len(state.hosts)
                if n > 1:
                    old_host_count = state.hosts[old_host].primary_count
                    new_host_count = state.hosts[new_host].primary_count
                    delta_host_var = 2.0 * (new_host_count - old_host_count + 1) / (n - 1)
                    delta += self.w_host * delta_host_var

        # Pool dimension: recompute just the affected pool's variance
        if 'pool' in self.enabled_levels and state.pools and pool_id in state.pools:
            pool = state.pools[pool_id]
            old_pool_var = components.pool_vars.get(pool_id, 0.0)

            # Build simulated counts for this pool only
            sim_counts = dict(pool.primary_counts)
            # Decrement old primary
            if old_primary in sim_counts:
                sim_counts[old_primary] -= 1
                if sim_counts[old_primary] == 0:
                    del sim_counts[old_primary]
            # Increment new primary
            sim_counts[new_primary] = sim_counts.get(new_primary, 0) + 1

            # Compute new variance for this pool (sample variance to match stdev²)
            counts_list = list(sim_counts.values())
            if len(counts_list) > 1:
                new_pool_var = stats_module.variance(counts_list)
            else:
                new_pool_var = 0.0

            # Delta to avg pool var: replace this pool's contribution
            num_pools = len(components.pool_vars) if components.pool_vars else 1
            # Handle case where pool wasn't in pool_vars before
            if pool_id not in components.pool_vars and counts_list:
                # Pool is being added
                num_pools_new = num_pools + 1
                delta_avg = (sum(components.pool_vars.values()) + new_pool_var) / num_pools_new - components.avg_pool_var
            elif num_pools > 0:
                delta_avg = (new_pool_var - old_pool_var) / num_pools
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
