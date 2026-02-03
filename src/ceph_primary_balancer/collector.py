"""
Data collection module for the Ceph Primary PG Balancer.

This module is responsible for fetching data from the Ceph cluster via CLI commands
and constructing ClusterState objects. It executes Ceph commands, parses JSON output,
and populates data models with PG and OSD information.

Functions:
    run_ceph_command: Execute Ceph CLI commands and parse JSON output
    collect_pg_data: Fetch all placement group information
    collect_osd_data: Collect OSD metadata from the cluster
    build_cluster_state: Combine PG and OSD data into a complete ClusterState
"""

import subprocess
import json
import sys
from typing import Dict, List

from .models import PGInfo, OSDInfo, ClusterState


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


def collect_osd_data() -> Dict[int, OSDInfo]:
    """
    Get list of all OSDs in the cluster.
    
    Executes 'ceph osd tree -f json' and extracts all OSD nodes.
    Initializes OSDInfo objects with zero counts (will be calculated later).
    
    Returns:
        Dict[int, OSDInfo]: Dictionary mapping osd_id to OSDInfo objects
    
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
    
    osds = {}
    for node in nodes:
        if node.get('type') == 'osd':
            osd_id = node['id']
            osds[osd_id] = OSDInfo(
                osd_id=osd_id,
                primary_count=0,
                total_pg_count=0
            )
    
    # Validate that we found at least one OSD
    if not osds:
        print("Error: No OSDs found in cluster")
        print("The cluster may not have any OSDs configured")
        sys.exit(1)
    
    return osds


def build_cluster_state() -> ClusterState:
    """
    Combine PG and OSD data into a complete ClusterState.
    
    Collects all PG and OSD information, then calculates:
    - primary_count: Number of PGs where each OSD is primary
    - total_pg_count: Total number of PGs in each OSD's acting sets
    
    Returns:
        ClusterState: Complete cluster state with populated counts
    """
    pgs = collect_pg_data()
    osds = collect_osd_data()
    
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
    
    return ClusterState(pgs=pgs, osds=osds)
