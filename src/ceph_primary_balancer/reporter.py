"""
Enhanced Reporting Module for Ceph Primary PG Balancer.

This module provides comprehensive reporting capabilities including:
- Terminal reports with formatted tables
- Markdown report generation
- Before/after comparisons at all levels (OSD, Host, Pool)
- Top N donors/receivers identification
- Visual formatting elements

Phase 3 Feature: Complete reporting with markdown export.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime

from .models import ClusterState, SwapProposal, Statistics
from .analyzer import calculate_statistics, get_pool_statistics_summary


class Reporter:
    """
    Generate comprehensive analysis reports in multiple formats.
    
    Supports:
    - Enhanced terminal output with tables
    - Markdown report generation
    - Before/after comparison tables
    - Multi-dimensional analysis (OSD, Host, Pool)
    """
    
    def __init__(self, top_n: int = 10):
        """
        Initialize Reporter.
        
        Args:
            top_n: Number of top donors/receivers to show (default: 10)
        """
        self.top_n = top_n
    
    def generate_terminal_report(
        self,
        current: ClusterState,
        proposed: ClusterState,
        swaps: List[SwapProposal]
    ) -> str:
        """
        Generate comprehensive terminal output with formatted tables.
        
        Args:
            current: ClusterState before optimization
            proposed: ClusterState after optimization
            swaps: List of proposed swap operations
        
        Returns:
            Formatted string for terminal display
        """
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append("CEPH PRIMARY BALANCER - COMPREHENSIVE ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        # Summary statistics
        lines.append(self._generate_summary_section(current, proposed, swaps))
        lines.append("")
        
        # OSD-level comparison
        lines.append(self._generate_osd_comparison(current, proposed))
        lines.append("")
        
        # Host-level comparison (if available)
        if current.hosts and proposed.hosts:
            lines.append(self._generate_host_comparison(current, proposed))
            lines.append("")
        
        # Pool-level comparison (if available)
        if current.pools and proposed.pools:
            lines.append(self._generate_pool_comparison(current, proposed))
            lines.append("")
        
        # Top movers
        lines.append(self._generate_top_movers_section(current, proposed))
        lines.append("")
        
        # Change summary
        lines.append(self._generate_change_summary(swaps, current))
        
        return "\n".join(lines)
    
    def generate_markdown_report(
        self,
        current: ClusterState,
        proposed: ClusterState,
        swaps: List[SwapProposal],
        output_path: str
    ):
        """
        Generate detailed markdown analysis report.
        
        Args:
            current: ClusterState before optimization
            proposed: ClusterState after optimization
            swaps: List of proposed swap operations
            output_path: Path to save markdown report
        """
        lines = []
        
        # Title and metadata
        lines.append("# Ceph Primary Balancer Analysis Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(self._generate_markdown_summary(current, proposed, swaps))
        lines.append("")
        
        # OSD-Level Analysis
        lines.append("## OSD-Level Analysis")
        lines.append("")
        lines.append(self._generate_markdown_comparison_table(
            current, proposed, "OSD"
        ))
        lines.append("")
        
        # Host-Level Analysis
        if current.hosts and proposed.hosts:
            lines.append("## Host-Level Analysis")
            lines.append("")
            lines.append(self._generate_markdown_comparison_table(
                current, proposed, "Host"
            ))
            lines.append("")
        
        # Pool-Level Analysis
        if current.pools and proposed.pools:
            lines.append("## Pool-Level Analysis")
            lines.append("")
            lines.append(self._generate_markdown_pool_table(current, proposed))
            lines.append("")
        
        # Top Donors and Receivers
        lines.append("## Top Donors and Receivers")
        lines.append("")
        lines.append(self._generate_markdown_top_movers(current, proposed))
        lines.append("")
        
        # Proposed Changes
        lines.append("## Proposed Changes")
        lines.append("")
        lines.append(f"Total swap operations: **{len(swaps)}**")
        lines.append("")
        lines.append(self._generate_markdown_changes_table(swaps, current))
        lines.append("")
        
        # Recommendations
        lines.append("## Recommendations")
        lines.append("")
        lines.append(self._generate_recommendations(current, proposed, swaps))
        lines.append("")
        
        # Write to file
        with open(output_path, 'w') as f:
            f.write("\n".join(lines))
    
    def generate_comparison_table(
        self,
        before_stats: Statistics,
        after_stats: Statistics,
        level: str
    ) -> str:
        """
        Generate before/after comparison table.
        
        Args:
            before_stats: Statistics before optimization
            after_stats: Statistics after optimization
            level: Level name (e.g., "OSD", "Host", "Pool")
        
        Returns:
            Formatted comparison table string
        """
        lines = []
        lines.append(f"{level} Level Comparison")
        lines.append("-" * 60)
        lines.append(f"{'Metric':<20} {'Before':>15} {'After':>15} {'Change':>10}")
        lines.append("-" * 60)
        
        # Mean
        lines.append(f"{'Mean':<20} {before_stats.mean:>15.2f} {after_stats.mean:>15.2f} {self._format_change(before_stats.mean, after_stats.mean):>10}")
        
        # Std Dev
        lines.append(f"{'Std Dev':<20} {before_stats.std_dev:>15.2f} {after_stats.std_dev:>15.2f} {self._format_change(before_stats.std_dev, after_stats.std_dev):>10}")
        
        # CV
        cv_change = self._calculate_percentage_change(before_stats.cv, after_stats.cv)
        lines.append(f"{'CV':<20} {before_stats.cv:>15.2%} {after_stats.cv:>15.2%} {cv_change:>10}")
        
        # Range
        before_range = f"[{before_stats.min_val}-{before_stats.max_val}]"
        after_range = f"[{after_stats.min_val}-{after_stats.max_val}]"
        lines.append(f"{'Range':<20} {before_range:>15} {after_range:>15} {'':>10}")
        
        # Median
        lines.append(f"{'Median (p50)':<20} {before_stats.p50:>15.2f} {after_stats.p50:>15.2f} {self._format_change(before_stats.p50, after_stats.p50):>10}")
        
        lines.append("-" * 60)
        
        return "\n".join(lines)
    
    def _generate_summary_section(
        self,
        current: ClusterState,
        proposed: ClusterState,
        swaps: List[SwapProposal]
    ) -> str:
        """Generate summary section for terminal report."""
        lines = []
        lines.append("CLUSTER OVERVIEW")
        lines.append("-" * 80)
        lines.append(f"Total PGs:     {len(current.pgs):>8}")
        lines.append(f"Total OSDs:    {len(current.osds):>8}")
        lines.append(f"Total Hosts:   {len(current.hosts):>8}")
        lines.append(f"Total Pools:   {len(current.pools):>8}")
        lines.append(f"Proposed Swaps: {len(swaps):>7}")
        lines.append("-" * 80)
        
        return "\n".join(lines)
    
    def _generate_osd_comparison(
        self,
        current: ClusterState,
        proposed: ClusterState
    ) -> str:
        """Generate OSD-level comparison."""
        current_stats = calculate_statistics(
            [osd.primary_count for osd in current.osds.values()]
        )
        proposed_stats = calculate_statistics(
            [osd.primary_count for osd in proposed.osds.values()]
        )
        
        return self.generate_comparison_table(current_stats, proposed_stats, "OSD")
    
    def _generate_host_comparison(
        self,
        current: ClusterState,
        proposed: ClusterState
    ) -> str:
        """Generate host-level comparison."""
        current_stats = calculate_statistics(
            [host.primary_count for host in current.hosts.values()]
        )
        proposed_stats = calculate_statistics(
            [host.primary_count for host in proposed.hosts.values()]
        )
        
        return self.generate_comparison_table(current_stats, proposed_stats, "Host")
    
    def _generate_pool_comparison(
        self,
        current: ClusterState,
        proposed: ClusterState
    ) -> str:
        """Generate pool-level comparison."""
        lines = []
        lines.append("Pool Level Comparison")
        lines.append("-" * 80)
        
        current_pool_stats = get_pool_statistics_summary(current)
        proposed_pool_stats = get_pool_statistics_summary(proposed)
        
        if current_pool_stats:
            from .scorer import _pool_cv_floor, UNBALANCEABLE_CV_FLOOR

            # Classify pools as balanceable or not
            excluded_pids = set()
            for pid in current_pool_stats:
                pool = current.pools.get(pid)
                if pool is not None:
                    n_part = len(pool.participating_osds) if pool.participating_osds else len(pool.primary_counts)
                    if _pool_cv_floor(pool.pg_count, n_part) > UNBALANCEABLE_CV_FLOOR:
                        excluded_pids.add(pid)

            # PG-weighted average CVs (balanceable pools only)
            def _weighted_avg(stats_dict, pools, exclude=None):
                ws, tw = 0.0, 0
                for pid, ps in stats_dict.items():
                    if exclude and pid in exclude:
                        continue
                    w = max(pools[pid].pg_count, 1) if pid in pools else 1
                    ws += ps.cv * w
                    tw += w
                return ws / tw if tw > 0 else 0.0
            current_avg_cv = _weighted_avg(current_pool_stats, current.pools, excluded_pids)
            proposed_avg_cv = _weighted_avg(proposed_pool_stats, proposed.pools, excluded_pids)

            lines.append(f"Average Pool CV (balanceable): {current_avg_cv:.2%} -> {proposed_avg_cv:.2%}")
            if excluded_pids:
                lines.append(f"  ({len(excluded_pids)} sparse pools excluded — too few PGs to balance)")
            lines.append("")
            lines.append(f"{'Pool':<20} {'Before CV':>12} {'After CV':>12} {'Improvement':>12}")
            lines.append("-" * 80)

            for pool_id in sorted(current_pool_stats.keys()):
                pool = current.pools[pool_id]
                curr_cv = current_pool_stats[pool_id].cv
                prop_cv = proposed_pool_stats.get(pool_id, current_pool_stats[pool_id]).cv
                improvement = self._calculate_percentage_change(curr_cv, prop_cv)

                pool_display = f"{pool_id}:{pool.pool_name}"[:20]
                sparse_tag = " [sparse]" if pool_id in excluded_pids else ""
                lines.append(f"{pool_display:<20} {curr_cv:>12.2%} {prop_cv:>12.2%} {improvement:>12}{sparse_tag}")
        
        lines.append("-" * 80)
        return "\n".join(lines)
    
    def _generate_top_movers_section(
        self,
        current: ClusterState,
        proposed: ClusterState
    ) -> str:
        """Generate top donors and receivers section."""
        lines = []
        lines.append("TOP DONORS AND RECEIVERS")
        lines.append("-" * 80)
        
        # Calculate changes per OSD
        osd_changes: Dict[int, int] = {}
        for osd_id in current.osds:
            current_count = current.osds[osd_id].primary_count
            proposed_count = proposed.osds[osd_id].primary_count
            change = proposed_count - current_count
            if change != 0:
                osd_changes[osd_id] = change
        
        # Sort by change (donors = negative, receivers = positive)
        sorted_changes = sorted(osd_changes.items(), key=lambda x: x[1])
        
        # Top donors (giving away primaries)
        lines.append(f"\nTop {self.top_n} Donors (reducing primaries):")
        lines.append(f"{'OSD':<8} {'Before':>8} {'After':>8} {'Change':>8} {'Host':<20}")
        lines.append("-" * 60)
        for osd_id, change in sorted_changes[:self.top_n]:
            osd_curr = current.osds[osd_id]
            osd_prop = proposed.osds[osd_id]
            host = osd_curr.host or "unknown"
            lines.append(f"{osd_id:<8} {osd_curr.primary_count:>8} {osd_prop.primary_count:>8} {change:>8} {host:<20}")
        
        # Top receivers (receiving primaries)
        lines.append(f"\nTop {self.top_n} Receivers (increasing primaries):")
        lines.append(f"{'OSD':<8} {'Before':>8} {'After':>8} {'Change':>8} {'Host':<20}")
        lines.append("-" * 60)
        for osd_id, change in reversed(sorted_changes[-self.top_n:]):
            osd_curr = current.osds[osd_id]
            osd_prop = proposed.osds[osd_id]
            host = osd_curr.host or "unknown"
            lines.append(f"{osd_id:<8} {osd_curr.primary_count:>8} {osd_prop.primary_count:>8} {change:>8} {host:<20}")
        
        lines.append("-" * 80)
        return "\n".join(lines)
    
    def _generate_change_summary(
        self,
        swaps: List[SwapProposal],
        state: ClusterState
    ) -> str:
        """Generate change summary section."""
        lines = []
        lines.append("CHANGE SUMMARY")
        lines.append("-" * 80)
        
        # Count affected entities
        affected_osds = set()
        affected_hosts = set()
        affected_pools = set()
        
        for swap in swaps:
            affected_osds.add(swap.old_primary)
            affected_osds.add(swap.new_primary)
            
            pg = state.pgs.get(swap.pgid)
            if pg:
                affected_pools.add(pg.pool_id)
            
            old_osd = state.osds.get(swap.old_primary)
            new_osd = state.osds.get(swap.new_primary)
            
            if old_osd and old_osd.host:
                affected_hosts.add(old_osd.host)
            if new_osd and new_osd.host:
                affected_hosts.add(new_osd.host)
        
        lines.append(f"Total swap operations:  {len(swaps)}")
        lines.append(f"Affected OSDs:          {len(affected_osds)}")
        lines.append(f"Affected Hosts:         {len(affected_hosts)}")
        lines.append(f"Affected Pools:         {len(affected_pools)}")
        lines.append("-" * 80)
        
        return "\n".join(lines)
    
    def _generate_markdown_summary(
        self,
        current: ClusterState,
        proposed: ClusterState,
        swaps: List[SwapProposal]
    ) -> str:
        """Generate executive summary for markdown."""
        lines = []
        
        # Calculate key metrics
        current_stats = calculate_statistics([osd.primary_count for osd in current.osds.values()])
        proposed_stats = calculate_statistics([osd.primary_count for osd in proposed.osds.values()])
        cv_improvement = self._calculate_percentage_change(current_stats.cv, proposed_stats.cv)
        
        lines.append(f"This report analyzes the current primary PG distribution and proposes "
                    f"**{len(swaps)} swap operations** to improve balance across the cluster.")
        lines.append("")
        lines.append("**Key Improvements:**")
        lines.append(f"- OSD-level CV improvement: {current_stats.cv:.2%} → {proposed_stats.cv:.2%} ({cv_improvement})")
        lines.append(f"- Total OSDs affected: {len(set(s.old_primary for s in swaps) | set(s.new_primary for s in swaps))}")
        lines.append(f"- Cluster size: {len(current.pgs)} PGs across {len(current.osds)} OSDs on {len(current.hosts)} hosts")
        
        return "\n".join(lines)
    
    def _generate_markdown_comparison_table(
        self,
        current: ClusterState,
        proposed: ClusterState,
        level: str
    ) -> str:
        """Generate markdown comparison table."""
        lines = []
        
        if level == "OSD":
            current_stats = calculate_statistics([osd.primary_count for osd in current.osds.values()])
            proposed_stats = calculate_statistics([osd.primary_count for osd in proposed.osds.values()])
        elif level == "Host":
            current_stats = calculate_statistics([host.primary_count for host in current.hosts.values()])
            proposed_stats = calculate_statistics([host.primary_count for host in proposed.hosts.values()])
        else:
            return ""
        
        lines.append("| Metric | Before | After | Improvement |")
        lines.append("|--------|--------|-------|-------------|")
        lines.append(f"| Mean | {current_stats.mean:.2f} | {proposed_stats.mean:.2f} | {self._format_change(current_stats.mean, proposed_stats.mean)} |")
        lines.append(f"| Std Dev | {current_stats.std_dev:.2f} | {proposed_stats.std_dev:.2f} | {self._format_change(current_stats.std_dev, proposed_stats.std_dev)} |")
        lines.append(f"| CV | {current_stats.cv:.2%} | {proposed_stats.cv:.2%} | {self._calculate_percentage_change(current_stats.cv, proposed_stats.cv)} |")
        lines.append(f"| Range | [{current_stats.min_val}-{current_stats.max_val}] | [{proposed_stats.min_val}-{proposed_stats.max_val}] | - |")
        lines.append(f"| Median | {current_stats.p50:.2f} | {proposed_stats.p50:.2f} | {self._format_change(current_stats.p50, proposed_stats.p50)} |")
        
        return "\n".join(lines)
    
    def _generate_markdown_pool_table(
        self,
        current: ClusterState,
        proposed: ClusterState
    ) -> str:
        """Generate markdown pool comparison table."""
        lines = []
        
        current_pool_stats = get_pool_statistics_summary(current)
        proposed_pool_stats = get_pool_statistics_summary(proposed)
        
        if not current_pool_stats:
            return "No pool-level statistics available."
        
        lines.append("| Pool ID | Pool Name | Before CV | After CV | Improvement |")
        lines.append("|---------|-----------|-----------|----------|-------------|")
        
        for pool_id in sorted(current_pool_stats.keys()):
            pool = current.pools[pool_id]
            curr_cv = current_pool_stats[pool_id].cv
            prop_cv = proposed_pool_stats.get(pool_id, current_pool_stats[pool_id]).cv
            improvement = self._calculate_percentage_change(curr_cv, prop_cv)
            
            lines.append(f"| {pool_id} | {pool.pool_name} | {curr_cv:.2%} | {prop_cv:.2%} | {improvement} |")
        
        return "\n".join(lines)
    
    def _generate_markdown_top_movers(
        self,
        current: ClusterState,
        proposed: ClusterState
    ) -> str:
        """Generate markdown top movers section."""
        lines = []
        
        # Calculate changes per OSD
        osd_changes: Dict[int, int] = {}
        for osd_id in current.osds:
            change = proposed.osds[osd_id].primary_count - current.osds[osd_id].primary_count
            if change != 0:
                osd_changes[osd_id] = change
        
        sorted_changes = sorted(osd_changes.items(), key=lambda x: x[1])
        
        # Top donors
        lines.append(f"### Top {min(self.top_n, len(sorted_changes))} Donors")
        lines.append("")
        lines.append("| OSD | Before | After | Change | Host |")
        lines.append("|-----|--------|-------|--------|------|")
        for osd_id, change in sorted_changes[:self.top_n]:
            osd_curr = current.osds[osd_id]
            osd_prop = proposed.osds[osd_id]
            host = osd_curr.host or "unknown"
            lines.append(f"| {osd_id} | {osd_curr.primary_count} | {osd_prop.primary_count} | {change} | {host} |")
        
        lines.append("")
        
        # Top receivers
        lines.append(f"### Top {min(self.top_n, len(sorted_changes))} Receivers")
        lines.append("")
        lines.append("| OSD | Before | After | Change | Host |")
        lines.append("|-----|--------|-------|--------|------|")
        for osd_id, change in reversed(sorted_changes[-self.top_n:]):
            osd_curr = current.osds[osd_id]
            osd_prop = proposed.osds[osd_id]
            host = osd_curr.host or "unknown"
            lines.append(f"| {osd_id} | {osd_curr.primary_count} | {osd_prop.primary_count} | {change} | {host} |")
        
        return "\n".join(lines)
    
    def _generate_markdown_changes_table(
        self,
        swaps: List[SwapProposal],
        state: ClusterState
    ) -> str:
        """Generate markdown changes table (first 20 swaps)."""
        lines = []
        
        if not swaps:
            return "No changes proposed."
        
        lines.append("### Sample Changes (first 20)")
        lines.append("")
        lines.append("| PG ID | Old Primary | New Primary | Old Host | New Host | Pool | Score Improvement |")
        lines.append("|-------|-------------|-------------|----------|----------|------|-------------------|")
        
        for swap in swaps[:20]:
            pg = state.pgs.get(swap.pgid)
            pool_name = state.pools[pg.pool_id].pool_name if pg and pg.pool_id in state.pools else "unknown"
            
            old_host = state.osds[swap.old_primary].host if swap.old_primary in state.osds else "unknown"
            new_host = state.osds[swap.new_primary].host if swap.new_primary in state.osds else "unknown"
            
            lines.append(f"| {swap.pgid} | {swap.old_primary} | {swap.new_primary} | "
                        f"{old_host or 'unknown'} | {new_host or 'unknown'} | {pool_name} | {swap.score_improvement:.4f} |")
        
        if len(swaps) > 20:
            lines.append("")
            lines.append(f"*... and {len(swaps) - 20} more changes*")
        
        return "\n".join(lines)
    
    def _generate_recommendations(
        self,
        current: ClusterState,
        proposed: ClusterState,
        swaps: List[SwapProposal]
    ) -> str:
        """Generate recommendations section."""
        lines = []
        
        current_stats = calculate_statistics([osd.primary_count for osd in current.osds.values()])
        proposed_stats = calculate_statistics([osd.primary_count for osd in proposed.osds.values()])
        
        lines.append("### Implementation Steps")
        lines.append("")
        lines.append("1. Review the proposed changes carefully")
        lines.append("2. Execute the generated rebalancing script during a maintenance window")
        lines.append("3. Monitor cluster performance during and after execution")
        lines.append("4. Validate that CV has improved as expected")
        lines.append("")
        lines.append("### Expected Outcomes")
        lines.append("")
        lines.append(f"- Reduced OSD-level variance: {current_stats.std_dev:.2f} → {proposed_stats.std_dev:.2f}")
        lines.append(f"- Improved balance metric (CV): {current_stats.cv:.2%} → {proposed_stats.cv:.2%}")
        lines.append(f"- More evenly distributed primary load across {len(swaps)} PG reassignments")
        
        if current.hosts:
            current_host_stats = calculate_statistics([h.primary_count for h in current.hosts.values()])
            proposed_host_stats = calculate_statistics([h.primary_count for h in proposed.hosts.values()])
            lines.append(f"- Improved host-level balance: {current_host_stats.cv:.2%} → {proposed_host_stats.cv:.2%}")
        
        return "\n".join(lines)
    
    def _format_change(self, before: float, after: float) -> str:
        """Format numeric change with sign."""
        change = after - before
        if abs(change) < 0.01:
            return "~0"
        return f"{change:+.2f}"
    
    def _calculate_percentage_change(self, before: float, after: float) -> str:
        """Calculate percentage change."""
        if before == 0:
            return "N/A"
        pct_change = ((after - before) / before) * 100
        return f"{pct_change:+.1f}%"
