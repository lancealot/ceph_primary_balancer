"""
Data collection module for the Ceph Primary PG Balancer.

This module is responsible for fetching data from the Ceph cluster via CLI commands
and constructing ClusterState objects. It executes Ceph commands, parses JSON output,
and populates data models with PG and OSD information.

Functions:
    run_ceph_command: Execute Ceph CLI commands and parse JSON output
    collect_pg_data: Fetch all placement group information
    collect_osd_data: Collect OSD metadata and host topology from the cluster
    collect_pool_data: Fetch pool information and metadata from the cluster (Phase 2)
    build_cluster_state: Combine PG, OSD, host, and pool data into a complete ClusterState
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple, Optional

from .models import PGInfo, OSDInfo, HostInfo, PoolInfo, ClusterState


def run_ceph_command(cmd: List[str]) -> dict:
    """
    Execute a Ceph command and return parsed JSON output.
    
    Args:
        cmd: Command to execute as a list of strings (e.g., ['ceph', 'pg', 'dump'])
    
    Returns:
        dict: Parsed JSON output from the command
    
    Raises:
        SystemExit: Exits with code 1 if command fails or output is invalid
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    
    except FileNotFoundError:
        print(f"Error: Ceph command not found. Is 'ceph' installed and in PATH?")
        print(f"Attempted command: {' '.join(cmd)}")
        sys.exit(1)
    
    except subprocess.CalledProcessError as e:
        print(f"Error: Ceph command execution failed with exit code {e.returncode}")
        print(f"Command: {' '.join(cmd)}")
        print(f"Error output: {e.stderr}")
        sys.exit(1)
    
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON output from Ceph command")
        print(f"Command: {' '.join(cmd)}")
        print(f"JSON error: {e}")
        sys.exit(1)


def collect_pg_data() -> Dict[str, PGInfo]:
    """
    Fetch all placement group information from the cluster.
    
    Executes 'ceph pg dump pgs -f json' and extracts PG metadata including
    PG ID, pool ID, and acting set for each placement group.
    
    Returns:
        Dict[str, PGInfo]: Dictionary mapping pgid to PGInfo objects
    
    Raises:
        SystemExit: Exits with code 1 if no PGs are found in the cluster
    """
    cmd = ['ceph', 'pg', 'dump', 'pgs', '-f', 'json']
    data = run_ceph_command(cmd)
    
    # Validate that we have PG data
    pg_stats = data.get('pg_stats', [])
    if not pg_stats:
        print("Error: No placement groups found in cluster")
        print("The cluster may be unhealthy or not properly initialized")
        sys.exit(1)
    
    pgs = {}
    for pg_stat in pg_stats:
        pgid = pg_stat['pgid']
        # Extract pool_id from pgid (e.g., "3.a1" -> 3)
        pool_id = int(pgid.split('.')[0])
        acting = pg_stat['acting']
        
        pgs[pgid] = PGInfo(
            pgid=pgid,
            pool_id=pool_id,
            acting=acting
        )
    
    return pgs


def collect_osd_data() -> Tuple[Dict[int, OSDInfo], Dict[str, HostInfo]]:
    """
    Get list of all OSDs and extract host topology from the cluster.
    
    Executes 'ceph osd tree -f json' and extracts:
    - OSD nodes with their parent host information
    - Host nodes with their children OSDs
    
    Initializes OSDInfo and HostInfo objects with zero counts
    (will be calculated later in build_cluster_state).
    
    Returns:
        Tuple containing:
        - Dict[int, OSDInfo]: Dictionary mapping osd_id to OSDInfo objects
        - Dict[str, HostInfo]: Dictionary mapping hostname to HostInfo objects
    
    Raises:
        SystemExit: Exits with code 1 if no OSDs are found in the cluster
    """
    cmd = ['ceph', 'osd', 'tree', '-f', 'json']
    data = run_ceph_command(cmd)
    
    # Validate that we have node data
    nodes = data.get('nodes', [])
    if not nodes:
        print("Error: No nodes found in OSD tree")
        print("The cluster may be unhealthy or not properly initialized")
        sys.exit(1)
    
    # Build a map of node_id -> node for lookups
    node_map = {node['id']: node for node in nodes}
    
    # Build parent-child relationship map from children arrays
    # (some Ceph versions don't have 'parent' field on nodes)
    osd_to_host = {}
    for node in nodes:
        if node.get('type') == 'host':
            host_name = node['name']
            # Map all children OSDs to this host
            for child_id in node.get('children', []):
                if child_id in node_map and node_map[child_id].get('type') == 'osd':
                    osd_to_host[child_id] = host_name
    
    # First pass: collect hosts
    hosts = {}
    for node in nodes:
        if node.get('type') == 'host':
            hostname = node['name']
            hosts[hostname] = HostInfo(
                hostname=hostname,
                osd_ids=[],
                primary_count=0,
                total_pg_count=0
            )
    
    # Second pass: collect OSDs and link to hosts
    osds = {}
    for node in nodes:
        if node.get('type') == 'osd':
            osd_id = node['id']
            
            # Get host from our mapping (built from children arrays)
            # Fall back to parent field traversal if available
            host_name = osd_to_host.get(osd_id)
            
            if not host_name:
                # Fallback: try parent field if it exists
                current_id = node.get('parent')
                while current_id is not None and current_id in node_map:
                    parent_node = node_map[current_id]
                    if parent_node.get('type') == 'host':
                        host_name = parent_node['name']
                        break
                    current_id = parent_node.get('parent')
            
            # Create OSDInfo with host linkage
            osds[osd_id] = OSDInfo(
                osd_id=osd_id,
                host=host_name,
                primary_count=0,
                total_pg_count=0
            )
            
            # Add OSD to host's osd_ids list
            if host_name and host_name in hosts:
                hosts[host_name].osd_ids.append(osd_id)
    
    # Validate that we found at least one OSD
    if not osds:
        print("Error: No OSDs found in cluster")
        print("The cluster may not have any OSDs configured")
        sys.exit(1)
    
    return osds, hosts


def collect_pool_data() -> Dict[int, PoolInfo]:
    """
    Fetch pool information and metadata from the cluster.
    
    Executes 'ceph osd pool ls detail -f json' and extracts:
    - Pool ID and name
    - Pool size and configuration
    
    Note: PG counts and primary distributions are calculated later in
    build_cluster_state based on PG data.
    
    Returns:
        Dict[int, PoolInfo]: Dictionary mapping pool_id to PoolInfo objects
    """
    cmd = ['ceph', 'osd', 'pool', 'ls', 'detail', '-f', 'json']
    data = run_ceph_command(cmd)
    
    pools = {}
    for pool_entry in data:
        # Handle both 'pool' and 'pool_id' keys for compatibility
        pool_id = pool_entry.get('pool') or pool_entry.get('pool_id')
        pool_name = pool_entry['pool_name']
        
        # Initialize PoolInfo with empty primary_counts (will be populated later)
        pools[pool_id] = PoolInfo(
            pool_id=pool_id,
            pool_name=pool_name,
            pg_count=0,  # Will be calculated from PG data
            primary_counts={}
        )
    
    return pools


def build_cluster_state(from_file: Optional[str] = None) -> ClusterState:
    """
    Combine PG, OSD, host, and pool data into a complete ClusterState.
    
    Collects all PG, OSD, host topology, and pool information, then calculates:
    - OSD-level: primary_count and total_pg_count for each OSD
    - Host-level: Aggregated primary_count and total_pg_count for each host
    - Pool-level: Per-pool primary distribution across OSDs (Phase 2)
    
    Args:
        from_file: Path to .tar.gz export file for offline mode (None = live cluster)
        
    Returns:
        ClusterState: Complete cluster state with populated counts at all levels
        
    Raises:
        OfflineExportError: If offline export is invalid (offline mode only)
        SystemExit: If live cluster connection fails (live mode only)
    """
    if from_file:
        # Offline mode: Load from export files
        from . import offline
        
        # Extract if not already extracted
        if from_file.endswith('.tar.gz'):
            export_dir = offline.extract_export_archive(from_file)
        else:
            export_dir = from_file
        
        # Load and return cluster state
        return offline.load_from_export_files(export_dir)
    
    else:
        # Live mode: Existing collection logic
        pgs = collect_pg_data()
        osds, hosts = collect_osd_data()
        pools = collect_pool_data()
        
        # Calculate primary_count and total_pg_count for each OSD
        for pg_info in pgs.values():
            # Count primary assignments (first OSD in acting set)
            primary_osd = pg_info.primary
            if primary_osd in osds:
                osds[primary_osd].primary_count += 1
            
            # Count total PG assignments (all OSDs in acting set)
            for osd_id in pg_info.acting:
                if osd_id in osds:
                    osds[osd_id].total_pg_count += 1
            
            # Count per-pool primary assignments (Phase 2)
            pool_id = pg_info.pool_id
            if pool_id in pools:
                # Increment PG count for this pool
                pools[pool_id].pg_count += 1
                
                # Track primary count per OSD for this pool
                if primary_osd not in pools[pool_id].primary_counts:
                    pools[pool_id].primary_counts[primary_osd] = 0
                pools[pool_id].primary_counts[primary_osd] += 1
        
        # Aggregate counts at host level
        for osd_info in osds.values():
            if osd_info.host and osd_info.host in hosts:
                hosts[osd_info.host].primary_count += osd_info.primary_count
                hosts[osd_info.host].total_pg_count += osd_info.total_pg_count
        
        return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)
