"""
Multi-dimensional scoring module for the Ceph Primary PG Balancer.

This module implements composite scoring across multiple dimensions:
- OSD-level variance (prevents individual OSD hotspots)
- Host-level variance (prevents network/node bottlenecks)
- Pool-level variance (ensures per-pool balance)

The scorer allows configurable weights to prioritize different optimization goals.
Phase 2 complete: Three-dimensional scoring fully implemented.
"""

from typing import Dict
from .models import ClusterState, Statistics
from .analyzer import calculate_statistics, calculate_average_pool_variance


class Scorer:
    """
    Multi-dimensional scoring engine for evaluating cluster balance.
    
    The scorer calculates a composite score based on variance across different
    dimensions. Lower scores indicate better balance. Weights control the
    relative importance of each dimension.
    
    Attributes:
        w_osd: Weight for OSD-level variance (default: 0.5)
        w_host: Weight for host-level variance (default: 0.3)
        w_pool: Weight for pool-level variance (default: 0.2)
    """
    
    def __init__(self, w_osd: float = 0.5, w_host: float = 0.3, w_pool: float = 0.2):
        """
        Initialize the scorer with dimension weights.
        
        Phase 2 defaults: 50% OSD, 30% Host, 20% Pool for balanced optimization.
        
        Args:
            w_osd: Weight for OSD-level variance (0.0 to 1.0)
            w_host: Weight for host-level variance (0.0 to 1.0)
            w_pool: Weight for pool-level variance (0.0 to 1.0)
        
        Raises:
            ValueError: If weights are negative or don't sum to approximately 1.0
        """
        if w_osd < 0 or w_host < 0 or w_pool < 0:
            raise ValueError("Weights must be non-negative")
        
        total = w_osd + w_host + w_pool
        if abs(total - 1.0) > 0.001:  # Allow small floating point error
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        
        self.w_osd = w_osd
        self.w_host = w_host
        self.w_pool = w_pool
    
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
        
        The score is a weighted sum of variances across dimensions.
        Lower scores indicate better overall balance.
        
        Score = (w_osd × OSD_variance) + (w_host × Host_variance) + (w_pool × Pool_variance)
        
        Args:
            state: Current cluster state
        
        Returns:
            float: Composite score (lower is better)
        """
        osd_var = self.calculate_osd_variance(state)
        host_var = self.calculate_host_variance(state)
        pool_var = self.calculate_pool_variance(state)
        
        score = (self.w_osd * osd_var) + (self.w_host * host_var) + (self.w_pool * pool_var)
        return score
    
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
