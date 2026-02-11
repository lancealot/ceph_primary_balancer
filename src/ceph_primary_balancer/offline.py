"""Offline mode support for air-gapped environments.

This module provides functionality to extract and load Ceph cluster data
from offline exports, enabling analysis without direct cluster access.

Functions:
    extract_export_archive: Extract tar.gz export archive to temporary directory
    validate_export_files: Validate that all required files exist and are valid JSON
    load_metadata: Load and return export metadata
    calculate_export_age: Calculate human-readable age of export
    load_from_export_files: Load ClusterState from raw Ceph command output files
    _parse_pg_data: Parse PG dump JSON data
    _parse_osd_tree: Parse OSD tree JSON data
    _parse_pool_data: Parse pool list JSON data
"""

import json
import tarfile
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

from .models import PGInfo, OSDInfo, HostInfo, PoolInfo, ClusterState


class OfflineExportError(Exception):
    """Raised when offline export is invalid or cannot be loaded."""
    pass


def extract_export_archive(archive_path: str) -> str:
    """
    Extract tar.gz export archive to temporary directory.
    
    Args:
        archive_path: Path to .tar.gz export file
        
    Returns:
        Path to extracted directory (in temp location)
        
    Raises:
        OfflineExportError: If archive is invalid or extraction fails
    """
    archive_file = Path(archive_path)
    
    if not archive_file.exists():
        raise OfflineExportError(f"Export file not found: {archive_path}")
    
    if not archive_file.suffix == '.gz' or not archive_path.endswith('.tar.gz'):
        raise OfflineExportError(
            f"Invalid export format: {archive_path}\n"
            "Expected .tar.gz file from ceph-export-cluster-data.sh"
        )
    
    # Create temporary directory for extraction
    temp_dir = tempfile.mkdtemp(prefix='ceph_offline_')
    
    try:
        # Extract archive
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(temp_dir)
        
        # Find the extracted directory (should be only one)
        extracted_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
        
        if len(extracted_dirs) != 1:
            raise OfflineExportError(
                f"Expected single directory in archive, found {len(extracted_dirs)}"
            )
        
        return str(extracted_dirs[0])
        
    except tarfile.TarError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise OfflineExportError(f"Failed to extract archive: {e}")
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise OfflineExportError(f"Unexpected error extracting archive: {e}")


def validate_export_files(export_dir: str) -> Tuple[bool, str]:
    """
    Validate that all required files exist and are valid JSON.
    
    Args:
        export_dir: Path to extracted export directory
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    export_path = Path(export_dir)
    required_files = ['pg_dump.json', 'osd_tree.json', 'pool_list.json', 'metadata.json']
    
    # Check all required files exist
    for filename in required_files:
        file_path = export_path / filename
        if not file_path.exists():
            return False, f"Missing required file: {filename}"
        
        # Validate JSON format
        try:
            with open(file_path, 'r') as f:
                json.load(f)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON in {filename}: {e}"
        except Exception as e:
            return False, f"Cannot read {filename}: {e}"
    
    return True, ""


def load_metadata(export_dir: str) -> Dict:
    """
    Load and return export metadata.
    
    Args:
        export_dir: Path to extracted export directory
        
    Returns:
        Metadata dictionary
    """
    metadata_path = Path(export_dir) / 'metadata.json'
    with open(metadata_path, 'r') as f:
        return json.load(f)


def calculate_export_age(metadata: Dict) -> str:
    """
    Calculate human-readable age of export.
    
    Args:
        metadata: Metadata dictionary with export_date
        
    Returns:
        Human-readable age string (e.g., "3 days old")
    """
    try:
        export_date_str = metadata.get('export_date')
        if not export_date_str:
            return "unknown age"
        
        export_date = datetime.fromisoformat(export_date_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age_delta = now - export_date
        
        if age_delta.days > 0:
            return f"{age_delta.days} day{'s' if age_delta.days != 1 else ''} old"
        elif age_delta.seconds >= 3600:
            hours = age_delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} old"
        elif age_delta.seconds >= 60:
            minutes = age_delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} old"
        else:
            return "less than 1 minute old"
            
    except Exception:
        return "unknown age"


def load_from_export_files(export_dir: str) -> ClusterState:
    """
    Load ClusterState from raw Ceph command output files.
    
    This function reads the JSON files produced by Ceph commands and
    constructs a ClusterState object identical to what would be built
    from a live cluster connection.
    
    Args:
        export_dir: Path to extracted export directory
        
    Returns:
        ClusterState populated from export files
        
    Raises:
        OfflineExportError: If files are invalid or cannot be parsed
    """
    export_path = Path(export_dir)
    
    # Validate files first
    is_valid, error_msg = validate_export_files(export_dir)
    if not is_valid:
        raise OfflineExportError(f"Invalid export: {error_msg}")
    
    try:
        # Load PG data
        with open(export_path / 'pg_dump.json', 'r') as f:
            pg_dump_data = json.load(f)
        
        # Load OSD tree
        with open(export_path / 'osd_tree.json', 'r') as f:
            osd_tree_data = json.load(f)
        
        # Load pool data
        with open(export_path / 'pool_list.json', 'r') as f:
            pool_list_data = json.load(f)
        
    except Exception as e:
        raise OfflineExportError(f"Failed to load export files: {e}")
    
    # Parse data using same logic as collector.py
    pgs = _parse_pg_data(pg_dump_data)
    osds, hosts = _parse_osd_tree(osd_tree_data)
    pools = _parse_pool_data(pool_list_data)
    
    # Calculate counts (same as collector.build_cluster_state)
    for pg_info in pgs.values():
        primary_osd = pg_info.primary
        if primary_osd in osds:
            osds[primary_osd].primary_count += 1
        
        for osd_id in pg_info.acting:
            if osd_id in osds:
                osds[osd_id].total_pg_count += 1
        
        pool_id = pg_info.pool_id
        if pool_id in pools:
            pools[pool_id].pg_count += 1
            if primary_osd not in pools[pool_id].primary_counts:
                pools[pool_id].primary_counts[primary_osd] = 0
            pools[pool_id].primary_counts[primary_osd] += 1
    
    # Aggregate host counts
    for osd_info in osds.values():
        if osd_info.host and osd_info.host in hosts:
            hosts[osd_info.host].primary_count += osd_info.primary_count
            hosts[osd_info.host].total_pg_count += osd_info.total_pg_count
    
    return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)


def _parse_pg_data(data: Dict) -> Dict[str, PGInfo]:
    """Parse PG dump JSON data (same format as collector.collect_pg_data)."""
    pgs = {}
    pg_stats = data.get('pg_stats', [])
    
    for pg_stat in pg_stats:
        pgid = pg_stat['pgid']
        pool_id = int(pgid.split('.')[0])
        acting = pg_stat['acting']
        
        pgs[pgid] = PGInfo(
            pgid=pgid,
            pool_id=pool_id,
            acting=acting
        )
    
    return pgs


def _parse_osd_tree(data: Dict) -> Tuple[Dict[int, OSDInfo], Dict[str, HostInfo]]:
    """Parse OSD tree JSON data (same format as collector.collect_osd_data)."""
    nodes = data.get('nodes', [])
    node_map = {node['id']: node for node in nodes}
    
    # Build OSD to host mapping
    osd_to_host = {}
    for node in nodes:
        if node.get('type') == 'host':
            host_name = node['name']
            for child_id in node.get('children', []):
                if child_id in node_map and node_map[child_id].get('type') == 'osd':
                    osd_to_host[child_id] = host_name
    
    # Build hosts
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
    
    # Build OSDs
    osds = {}
    for node in nodes:
        if node.get('type') == 'osd':
            osd_id = node['id']
            host_name = osd_to_host.get(osd_id)
            
            # Fallback: try parent field
            if not host_name:
                current_id = node.get('parent')
                while current_id is not None and current_id in node_map:
                    parent_node = node_map[current_id]
                    if parent_node.get('type') == 'host':
                        host_name = parent_node['name']
                        break
                    current_id = parent_node.get('parent')
            
            osds[osd_id] = OSDInfo(
                osd_id=osd_id,
                host=host_name,
                primary_count=0,
                total_pg_count=0
            )
            
            if host_name and host_name in hosts:
                hosts[host_name].osd_ids.append(osd_id)
    
    return osds, hosts


def _parse_pool_data(data: list) -> Dict[int, PoolInfo]:
    """Parse pool list JSON data (same format as collector.collect_pool_data)."""
    pools = {}
    
    for pool_entry in data:
        pool_id = pool_entry.get('pool') or pool_entry.get('pool_id')
        pool_name = pool_entry['pool_name']
        
        pools[pool_id] = PoolInfo(
            pool_id=pool_id,
            pool_name=pool_name,
            pg_count=0,
            primary_counts={}
        )
    
    return pools
