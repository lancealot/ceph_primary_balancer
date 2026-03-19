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


def parse_pg_data(data: dict) -> Dict[str, PGInfo]:
    """Parse raw PG dump JSON into PGInfo objects."""
    pgs = {}
    for pg_stat in data.get('pg_stats', []):
        pgid = pg_stat['pgid']
        pool_id = int(pgid.split('.')[0])
        pgs[pgid] = PGInfo(pgid=pgid, pool_id=pool_id, acting=pg_stat['acting'])
    return pgs


def parse_osd_tree(data: dict) -> Tuple[Dict[int, OSDInfo], Dict[str, HostInfo]]:
    """Parse raw OSD tree JSON into OSDInfo/HostInfo objects.

    Skips down OSDs — they can't serve primaries and would skew
    statistics with phantom 0-primary entries.
    """
    nodes = data.get('nodes', [])
    node_map = {node['id']: node for node in nodes}

    # Build OSD → host mapping from children arrays
    osd_to_host = {}
    for node in nodes:
        if node.get('type') == 'host':
            for child_id in node.get('children', []):
                if child_id in node_map and node_map[child_id].get('type') == 'osd':
                    osd_to_host[child_id] = node['name']

    hosts = {}
    for node in nodes:
        if node.get('type') == 'host':
            hosts[node['name']] = HostInfo(
                hostname=node['name'], osd_ids=[],
                primary_count=0, total_pg_count=0,
            )

    osds = {}
    for node in nodes:
        if node.get('type') == 'osd':
            if node.get('status', 'up') != 'up':
                continue
            osd_id = node['id']
            host_name = osd_to_host.get(osd_id)
            if not host_name:
                current_id = node.get('parent')
                while current_id is not None and current_id in node_map:
                    parent_node = node_map[current_id]
                    if parent_node.get('type') == 'host':
                        host_name = parent_node['name']
                        break
                    current_id = parent_node.get('parent')
            osds[osd_id] = OSDInfo(
                osd_id=osd_id, host=host_name,
                primary_count=0, total_pg_count=0,
            )
            if host_name and host_name in hosts:
                hosts[host_name].osd_ids.append(osd_id)

    return osds, hosts


def parse_pool_data(data: list) -> Dict[int, PoolInfo]:
    """Parse raw pool list JSON into PoolInfo objects."""
    pools = {}
    for entry in data:
        pool_id = entry.get('pool') or entry.get('pool_id')
        pools[pool_id] = PoolInfo(
            pool_id=pool_id, pool_name=entry['pool_name'],
            pg_count=0, primary_counts={},
        )
    return pools


def populate_counts(
    pgs: Dict[str, PGInfo],
    osds: Dict[int, OSDInfo],
    hosts: Dict[str, HostInfo],
    pools: Dict[int, PoolInfo],
) -> None:
    """Populate primary/PG counts on OSDs, hosts, and pools from PG data."""
    for pg in pgs.values():
        primary = pg.primary
        if primary in osds:
            osds[primary].primary_count += 1
        for osd_id in pg.acting:
            if osd_id in osds:
                osds[osd_id].total_pg_count += 1
        pool_id = pg.pool_id
        if pool_id in pools:
            pools[pool_id].pg_count += 1
            pools[pool_id].participating_osds.update(
                oid for oid in pg.acting if oid in osds
            )
            pools[pool_id].primary_counts[primary] = (
                pools[pool_id].primary_counts.get(primary, 0) + 1
            )
    for osd in osds.values():
        if osd.host and osd.host in hosts:
            hosts[osd.host].primary_count += osd.primary_count
            hosts[osd.host].total_pg_count += osd.total_pg_count


def collect_pg_data() -> Dict[str, PGInfo]:
    """Fetch PG data from a live Ceph cluster."""
    data = run_ceph_command(['ceph', 'pg', 'dump', 'pgs', '-f', 'json'])
    if not data.get('pg_stats'):
        print("Error: No placement groups found in cluster")
        sys.exit(1)
    return parse_pg_data(data)


def collect_osd_data() -> Tuple[Dict[int, OSDInfo], Dict[str, HostInfo]]:
    """Fetch OSD/host data from a live Ceph cluster."""
    data = run_ceph_command(['ceph', 'osd', 'tree', '-f', 'json'])
    if not data.get('nodes'):
        print("Error: No nodes found in OSD tree")
        sys.exit(1)
    osds, hosts = parse_osd_tree(data)
    if not osds:
        print("Error: No OSDs found in cluster")
        sys.exit(1)
    return osds, hosts


def collect_pool_data() -> Dict[int, PoolInfo]:
    """Fetch pool data from a live Ceph cluster."""
    data = run_ceph_command(['ceph', 'osd', 'pool', 'ls', 'detail', '-f', 'json'])
    return parse_pool_data(data)


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
        pgs = collect_pg_data()
        osds, hosts = collect_osd_data()
        pools = collect_pool_data()
        populate_counts(pgs, osds, hosts, pools)
        return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)
