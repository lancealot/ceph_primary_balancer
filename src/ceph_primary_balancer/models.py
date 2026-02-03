"""
Data models for the Ceph Primary PG Balancer.

This module defines the core data structures used throughout the balancer:
- PGInfo: Represents placement groups and their acting sets
- OSDInfo: Tracks primary and total PG counts per OSD
- ClusterState: Complete snapshot of cluster state
- SwapProposal: Proposed primary reassignment operations
- Statistics: Statistical metrics for primary distribution analysis
"""

from dataclasses import dataclass
from typing import List, Dict


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
    primary_count: int = 0      # Number of PGs where this OSD is primary
    total_pg_count: int = 0     # Total PGs (primary + replica)


@dataclass
class ClusterState:
    """Complete cluster state snapshot containing all PGs and OSDs."""
    pgs: Dict[str, PGInfo]      # Dictionary mapping pgid to PGInfo
    osds: Dict[int, OSDInfo]    # Dictionary mapping osd_id to OSDInfo


@dataclass
class SwapProposal:
    """Proposed primary reassignment for balancing."""
    pgid: str                       # PG to modify
    old_primary: int                # Current primary OSD
    new_primary: int                # Proposed new primary OSD
    variance_improvement: float     # Expected variance reduction


@dataclass
class Statistics:
    """Statistical metrics for primary count distribution."""
    mean: float          # Average primary count across OSDs
    std_dev: float       # Standard deviation of primary counts
    cv: float            # Coefficient of variation (std_dev/mean)
    min_val: int         # Minimum primary count among OSDs
    max_val: int         # Maximum primary count among OSDs
    p50: float           # Median primary count
