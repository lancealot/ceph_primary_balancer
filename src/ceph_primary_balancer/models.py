"""
Data models for the Ceph Primary PG Balancer.

This module defines the core data structures used throughout the balancer:
- PGInfo: Represents placement groups and their acting sets
- OSDInfo: Tracks primary and total PG counts per OSD
- HostInfo: Represents a host with aggregated OSD statistics
- PoolInfo: Represents a pool with per-OSD primary distribution
- ClusterState: Complete snapshot of cluster state
- SwapProposal: Proposed primary reassignment operations
- Statistics: Statistical metrics for primary distribution analysis
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class PGInfo:
    """Represents a single Placement Group with its configuration."""
    pgid: str              # PG identifier (e.g., "3.a1")
    pool_id: int           # Pool ID (e.g., 3)
    acting: List[int]      # List of OSD IDs in acting set (e.g., [12, 45, 78])
    
    @property
    def primary(self) -> int:
        """
        Return the primary OSD for this PG.
        
        The first OSD in the acting set is always the primary.
        
        Returns:
            int: OSD ID of the primary OSD
        """
        return self.acting[0]


@dataclass
class OSDInfo:
    """Represents an OSD with primary and total PG counts."""
    osd_id: int                 # OSD identifier
    host: Optional[str] = None  # Host name where OSD resides (None if unknown)
    primary_count: int = 0      # Number of PGs where this OSD is primary
    total_pg_count: int = 0     # Total PGs (primary + replica)


@dataclass
class HostInfo:
    """
    Represents a host with aggregated statistics from its OSDs.
    
    Host-level balancing prevents network/node bottlenecks by ensuring
    no single host becomes a primary hotspot.
    """
    hostname: str                           # Host identifier
    osd_ids: List[int] = field(default_factory=list)  # OSDs on this host
    primary_count: int = 0                  # Total primaries across all OSDs on host
    total_pg_count: int = 0                 # Total PGs across all OSDs on host


@dataclass
class PoolInfo:
    """
    Represents a pool with per-OSD primary distribution.

    Pool-level balancing ensures that primary distribution is balanced
    within each pool independently, which is important for workload-specific
    optimization and isolation.

    participating_osds tracks every OSD that appears in any acting set for
    this pool.  This is critical for correct CV calculation: OSDs with 0
    primaries in the pool must be included in variance/mean — otherwise
    the denominator (n) is too small and pool CV is underestimated.
    """
    pool_id: int                                            # Pool identifier
    pool_name: str                                          # Human-readable pool name
    pg_count: int                                           # Total number of PGs in this pool
    primary_counts: Dict[int, int] = field(default_factory=dict)  # osd_id -> primary count for this pool
    participating_osds: set = field(default_factory=set)    # All OSDs in any acting set for this pool


@dataclass
class ClusterState:
    """Complete cluster state snapshot containing all PGs, OSDs, hosts, and pools."""
    pgs: Dict[str, PGInfo]           # Dictionary mapping pgid to PGInfo
    osds: Dict[int, OSDInfo]         # Dictionary mapping osd_id to OSDInfo
    hosts: Dict[str, HostInfo] = field(default_factory=dict)  # Dictionary mapping hostname to HostInfo
    pools: Dict[int, PoolInfo] = field(default_factory=dict)  # Dictionary mapping pool_id to PoolInfo


@dataclass
class SwapProposal:
    """Proposed primary reassignment for balancing."""
    pgid: str                       # PG to modify
    old_primary: int                # Current primary OSD
    new_primary: int                # Proposed new primary OSD
    score_improvement: float        # Expected score improvement (variance reduction or composite)


@dataclass
class Statistics:
    """Statistical metrics for primary count distribution."""
    mean: float          # Average primary count across entities
    std_dev: float       # Standard deviation of primary counts
    cv: float            # Coefficient of variation (std_dev/mean)
    min_val: int         # Minimum primary count among entities
    max_val: int         # Maximum primary count among entities
    p50: float           # Median primary count
