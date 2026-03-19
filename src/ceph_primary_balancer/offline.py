"""Load ClusterState from offline export archives."""

import json
import tarfile
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Tuple
from datetime import datetime, timezone

from .models import ClusterState
from .collector import parse_pg_data, parse_osd_tree, parse_pool_data, populate_counts


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
    
    pgs = parse_pg_data(pg_dump_data)
    osds, hosts = parse_osd_tree(osd_tree_data)
    pools = parse_pool_data(pool_list_data)
    populate_counts(pgs, osds, hosts, pools)
    return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)
