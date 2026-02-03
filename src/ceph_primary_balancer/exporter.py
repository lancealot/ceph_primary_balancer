"""
JSON Export Module for Ceph Primary PG Balancer.

This module provides functionality to export comprehensive cluster state,
analysis results, and proposed changes to JSON format for:
- Automation integration
- External analysis tools
- Historical tracking
- Data persistence

Phase 3 Feature: Complete JSON export with schema versioning.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .models import ClusterState, SwapProposal, Statistics, OSDInfo, HostInfo, PoolInfo
from .analyzer import calculate_statistics, get_pool_statistics_summary


class JSONExporter:
    """
    Export cluster analysis results to structured JSON format.
    
    Produces schema-compliant JSON output containing:
    - Metadata (timestamp, version, cluster info)
    - Current state (OSD, Host, Pool level statistics)
    - Proposed state (optimized statistics)
    - Changes (list of swap proposals)
    - Improvements (reduction metrics)
    """
    
    SCHEMA_VERSION = "2.0"
    
    def __init__(self, tool_version: str = "0.4.0"):
        """
        Initialize JSONExporter.
        
        Args:
            tool_version: Version of the ceph-primary-balancer tool
        """
        self.tool_version = tool_version
    
    def export_analysis(
        self,
        current_state: ClusterState,
        proposed_state: ClusterState,
        swaps: List[SwapProposal],
        cluster_fsid: Optional[str] = None,
        analysis_type: str = "full"
    ) -> Dict[str, Any]:
        """
        Export complete analysis to JSON-serializable dictionary.
        
        Args:
            current_state: ClusterState before optimization
            proposed_state: ClusterState after optimization
            swaps: List of proposed swap operations
            cluster_fsid: Optional Ceph cluster FSID
            analysis_type: Type of analysis performed (default: "full")
        
        Returns:
            Dictionary containing complete analysis in schema-compliant format
        """
        # Calculate statistics for all dimensions
        current_stats_osd = self._calculate_osd_stats(current_state)
        proposed_stats_osd = self._calculate_osd_stats(proposed_state)
        
        current_stats_host = self._calculate_host_stats(current_state)
        proposed_stats_host = self._calculate_host_stats(proposed_state)
        
        current_pool_stats = get_pool_statistics_summary(current_state)
        proposed_pool_stats = get_pool_statistics_summary(proposed_state)
        
        # Build JSON structure
        result = {
            "schema_version": self.SCHEMA_VERSION,
            "metadata": self._build_metadata(current_state, cluster_fsid, analysis_type),
            "current_state": self._build_state_section(
                current_state, 
                current_stats_osd,
                current_stats_host,
                current_pool_stats
            ),
            "proposed_state": self._build_state_section(
                proposed_state,
                proposed_stats_osd,
                proposed_stats_host,
                proposed_pool_stats
            ),
            "changes": self._build_changes_section(swaps, current_state),
            "improvements": self._build_improvements_section(
                current_stats_osd,
                proposed_stats_osd,
                current_stats_host,
                proposed_stats_host,
                swaps,
                current_state
            )
        }
        
        return result
    
    def export_to_file(
        self,
        current_state: ClusterState,
        proposed_state: ClusterState,
        swaps: List[SwapProposal],
        output_path: str,
        cluster_fsid: Optional[str] = None,
        analysis_type: str = "full"
    ):
        """
        Export analysis to JSON file.
        
        Args:
            current_state: ClusterState before optimization
            proposed_state: ClusterState after optimization
            swaps: List of proposed swap operations
            output_path: Path to output JSON file
            cluster_fsid: Optional Ceph cluster FSID
            analysis_type: Type of analysis performed
        """
        data = self.export_analysis(
            current_state,
            proposed_state,
            swaps,
            cluster_fsid,
            analysis_type
        )
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _build_metadata(
        self,
        state: ClusterState,
        cluster_fsid: Optional[str],
        analysis_type: str
    ) -> Dict[str, Any]:
        """Build metadata section."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_version": self.tool_version,
            "cluster_fsid": cluster_fsid or "unknown",
            "analysis_type": analysis_type
        }
    
    def _build_state_section(
        self,
        state: ClusterState,
        stats_osd: Statistics,
        stats_host: Optional[Statistics],
        pool_stats: Dict[int, Statistics]
    ) -> Dict[str, Any]:
        """Build current_state or proposed_state section."""
        result = {
            "totals": {
                "pgs": len(state.pgs),
                "osds": len(state.osds),
                "hosts": len(state.hosts),
                "pools": len(state.pools)
            },
            "osd_level": self._stats_to_dict(stats_osd, include_details=True),
            "host_level": {},
            "pool_level": {}
        }
        
        # Add OSD details
        result["osd_level"]["osd_details"] = [
            {
                "osd_id": osd_id,
                "host": osd.host or "unknown",
                "primary_count": osd.primary_count,
                "total_pgs": osd.total_pg_count
            }
            for osd_id, osd in sorted(state.osds.items())
        ]
        
        # Add host-level data if available
        if stats_host:
            result["host_level"] = self._stats_to_dict(stats_host, include_details=True)
            result["host_level"]["host_details"] = [
                {
                    "hostname": hostname,
                    "osd_count": len(host.osd_ids),
                    "primary_count": host.primary_count,
                    "total_pgs": host.total_pg_count
                }
                for hostname, host in sorted(state.hosts.items())
            ]
        
        # Add pool-level data if available
        if pool_stats:
            result["pool_level"]["pools"] = [
                {
                    "pool_id": pool_id,
                    "pool_name": state.pools[pool_id].pool_name,
                    "pg_count": state.pools[pool_id].pg_count,
                    "cv": pool_stats[pool_id].cv,
                    "mean": pool_stats[pool_id].mean,
                    "std_dev": pool_stats[pool_id].std_dev,
                    "min": pool_stats[pool_id].min_val,
                    "max": pool_stats[pool_id].max_val,
                    "per_osd_distribution": state.pools[pool_id].primary_counts
                }
                for pool_id in sorted(pool_stats.keys())
            ]
        
        return result
    
    def _build_changes_section(
        self,
        swaps: List[SwapProposal],
        state: ClusterState
    ) -> List[Dict[str, Any]]:
        """Build changes section with swap proposals."""
        changes = []
        
        for swap in swaps:
            # Find pool name and host info
            pg = state.pgs.get(swap.pgid)
            pool_name = "unknown"
            old_host = "unknown"
            new_host = "unknown"
            
            if pg:
                pool = state.pools.get(pg.pool_id)
                if pool:
                    pool_name = pool.pool_name
            
            old_osd = state.osds.get(swap.old_primary)
            if old_osd and old_osd.host:
                old_host = old_osd.host
            
            new_osd = state.osds.get(swap.new_primary)
            if new_osd and new_osd.host:
                new_host = new_osd.host
            
            changes.append({
                "pgid": swap.pgid,
                "old_primary": swap.old_primary,
                "new_primary": swap.new_primary,
                "old_host": old_host,
                "new_host": new_host,
                "pool_name": pool_name,
                "score_improvement": round(swap.score_improvement, 6)
            })
        
        return changes
    
    def _build_improvements_section(
        self,
        current_osd: Statistics,
        proposed_osd: Statistics,
        current_host: Optional[Statistics],
        proposed_host: Optional[Statistics],
        swaps: List[SwapProposal],
        state: ClusterState
    ) -> Dict[str, Any]:
        """Build improvements section with reduction metrics."""
        # Calculate CV reduction percentages
        osd_cv_reduction = 0.0
        if current_osd.cv > 0:
            osd_cv_reduction = ((current_osd.cv - proposed_osd.cv) / current_osd.cv) * 100
        
        host_cv_reduction = 0.0
        if current_host and proposed_host and current_host.cv > 0:
            host_cv_reduction = ((current_host.cv - proposed_host.cv) / current_host.cv) * 100
        
        # Count affected OSDs and hosts
        affected_osds = set()
        affected_hosts = set()
        
        for swap in swaps:
            affected_osds.add(swap.old_primary)
            affected_osds.add(swap.new_primary)
            
            old_osd = state.osds.get(swap.old_primary)
            new_osd = state.osds.get(swap.new_primary)
            
            if old_osd and old_osd.host:
                affected_hosts.add(old_osd.host)
            if new_osd and new_osd.host:
                affected_hosts.add(new_osd.host)
        
        return {
            "osd_cv_reduction_pct": round(osd_cv_reduction, 2),
            "host_cv_reduction_pct": round(host_cv_reduction, 2),
            "total_changes": len(swaps),
            "osds_affected": len(affected_osds),
            "hosts_affected": len(affected_hosts)
        }
    
    def _stats_to_dict(
        self,
        stats: Statistics,
        include_details: bool = False
    ) -> Dict[str, Any]:
        """Convert Statistics object to dictionary."""
        result = {
            "mean": round(stats.mean, 2),
            "std_dev": round(stats.std_dev, 2),
            "cv": round(stats.cv, 4),
            "min": stats.min_val,
            "max": stats.max_val,
            "p50": round(stats.p50, 2)
        }
        
        # Add percentiles if detailed
        if include_details:
            result["p5"] = None  # Can be calculated if needed
            result["p95"] = None  # Can be calculated if needed
        
        return result
    
    def _calculate_osd_stats(self, state: ClusterState) -> Statistics:
        """Calculate OSD-level statistics."""
        counts = [osd.primary_count for osd in state.osds.values()]
        return calculate_statistics(counts)
    
    def _calculate_host_stats(self, state: ClusterState) -> Optional[Statistics]:
        """Calculate host-level statistics if hosts available."""
        if not state.hosts:
            return None
        counts = [host.primary_count for host in state.hosts.values()]
        return calculate_statistics(counts)
