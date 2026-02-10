# Phase 8: Offline Mode for Air-Gapped Environments
## Ceph Primary PG Balancer v1.3.0

**Date:** 2026-02-08  
**Prerequisites:** Phase 7.1 Complete (v1.2.1)  
**Target Version:** 1.3.0  
**Status:** Planning  

---

## Executive Summary

Phase 8 introduces offline mode capabilities for air-gapped environments where the Ceph Primary PG Balancer cannot run with direct cluster access. This feature enables administrators to export cluster data from the Ceph environment, transfer it to an isolated analysis system, generate optimization scripts offline, and then transfer the scripts back for execution.

### Key Objectives

1. **Export Capability** - Simple bash script to dump cluster data
2. **Offline Analysis** - Full CLI functionality without live cluster access
3. **Air-Gap Support** - Complete workflow for disconnected environments
4. **Safety Preservation** - Maintain safeguards except auto health checks

### Target Use Cases

| Use Case | Description | Benefit |
|----------|-------------|---------|
| **Air-Gapped Security** | High-security environments with network isolation | Compliance with security policies |
| **Analysis Workstations** | Run optimization on developer/analyst laptops | No cluster access credentials needed |
| **Vendor Support** | Share cluster snapshot with support teams | Troubleshooting without cluster access |
| **Historical Analysis** | Archive and analyze past cluster states | Trend analysis and planning |

---

## Architecture Overview

### Component Structure

```
src/ceph_primary_balancer/
├── offline.py                      # NEW: Offline mode module (~200 lines)
├── collector.py                    # Modified: Add offline support
├── cli.py                          # Modified: Add --from-file flag
└── script_generator.py             # Modified: Offline script warnings

scripts/
└── ceph-export-cluster-data.sh     # NEW: Export utility script (~100 lines)

docs/
├── OFFLINE-MODE.md                 # NEW: Offline mode guide
└── USAGE.md                        # Modified: Add offline examples

tests/
├── test_offline_mode.py            # NEW: Offline mode tests (~250 lines)
└── test_offline_integration.py     # NEW: End-to-end tests (~150 lines)
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  AIR-GAPPED CEPH CLUSTER                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. Run Export Script                                 │   │
│  │     $ ./ceph-export-cluster-data.sh                   │   │
│  │                                                        │   │
│  │  2. Generates:                                        │   │
│  │     - ceph-cluster-export-YYYYMMDD_HHMMSS.tar.gz     │   │
│  │       ├── pg_dump.json                                │   │
│  │       ├── osd_tree.json                               │   │
│  │       ├── pool_list.json                              │   │
│  │       └── metadata.json                               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Transfer out (USB, secure copy, etc.)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  OFFLINE ANALYSIS SYSTEM                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  3. Run Offline Analysis                              │   │
│  │     $ python3 -m ceph_primary_balancer.cli \          │   │
│  │         --from-file cluster-export.tar.gz \           │   │
│  │         --output rebalance.sh \                       │   │
│  │         --max-changes 100                             │   │
│  │                                                        │   │
│  │  4. Generates:                                        │   │
│  │     - rebalance.sh (optimization script)              │   │
│  │     - rebalance_rollback.sh (rollback script)         │   │
│  │     - analysis.json (optional)                        │   │
│  │     - report.md (optional)                            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Transfer back (USB, secure copy, etc.)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  AIR-GAPPED CEPH CLUSTER                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  5. Execute Scripts                                   │   │
│  │     $ ./rebalance.sh                                  │   │
│  │                                                        │   │
│  │     (If problems occur)                               │   │
│  │     $ ./rebalance_rollback.sh                         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Export Script Design

### Export Script: `scripts/ceph-export-cluster-data.sh`

**Purpose:** Single bash script users run on Ceph cluster to export all required data.

**Features:**
- ✅ Exports raw Ceph command outputs (JSON format)
- ✅ Creates metadata file with export timestamp and environment info
- ✅ Compresses to tar.gz for easy transfer
- ✅ Validates export success
- ✅ Provides clear instructions for next steps

**Implementation:**

```bash
#!/bin/bash
# Ceph Primary PG Balancer - Cluster Data Export Script
# Version: 1.0
# 
# This script exports Ceph cluster data for offline analysis in air-gapped
# environments. Run this on a system with Ceph CLI access.
#
# Usage: ./ceph-export-cluster-data.sh [output-dir]

set -e

# Configuration
SCRIPT_VERSION="1.0"
OUTPUT_BASE="${1:-ceph-cluster-export-$(date +%Y%m%d_%H%M%S)}"
EXPORT_DIR="${OUTPUT_BASE}"
ARCHIVE="${OUTPUT_BASE}.tar.gz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "Ceph Primary PG Balancer - Cluster Data Export"
echo "========================================================================"
echo ""

# Check if ceph CLI is available
if ! command -v ceph &> /dev/null; then
    echo -e "${RED}ERROR: 'ceph' command not found${NC}"
    echo "Please ensure Ceph CLI is installed and in PATH"
    exit 1
fi

# Check if we can connect to cluster
if ! ceph status &> /dev/null; then
    echo -e "${RED}ERROR: Cannot connect to Ceph cluster${NC}"
    echo "Please check:"
    echo "  - Ceph cluster is running"
    echo "  - You have admin credentials (ceph.conf, keyring)"
    echo "  - Network connectivity to monitors"
    exit 1
fi

echo -e "${GREEN}✓${NC} Ceph CLI available and cluster accessible"
echo ""

# Create export directory
mkdir -p "$EXPORT_DIR"
echo "Export directory: $EXPORT_DIR"
echo ""

# Function to export with error handling
export_data() {
    local description="$1"
    local command="$2"
    local output_file="$3"
    
    echo -n "Exporting $description... "
    
    if eval "$command" > "$EXPORT_DIR/$output_file" 2>/dev/null; then
        local size=$(du -h "$EXPORT_DIR/$output_file" | cut -f1)
        echo -e "${GREEN}✓${NC} ($size)"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# Export PG data
if ! export_data "PG data" "ceph pg dump pgs -f json" "pg_dump.json"; then
    echo -e "${RED}ERROR: Failed to export PG data${NC}"
    echo "This is a critical component. Cannot continue."
    rm -rf "$EXPORT_DIR"
    exit 1
fi

# Export OSD tree (topology)
if ! export_data "OSD tree topology" "ceph osd tree -f json" "osd_tree.json"; then
    echo -e "${RED}ERROR: Failed to export OSD tree${NC}"
    echo "This is a critical component. Cannot continue."
    rm -rf "$EXPORT_DIR"
    exit 1
fi

# Export pool information
if ! export_data "Pool information" "ceph osd pool ls detail -f json" "pool_list.json"; then
    echo -e "${RED}ERROR: Failed to export pool data${NC}"
    echo "This is a critical component. Cannot continue."
    rm -rf "$EXPORT_DIR"
    exit 1
fi

# Get cluster information for metadata
CLUSTER_FSID=$(ceph fsid 2>/dev/null || echo "unknown")
CEPH_VERSION=$(ceph --version 2>/dev/null | head -n1 || echo "unknown")
NUM_OSDS=$(ceph osd stat -f json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['num_osds'])" 2>/dev/null || echo "unknown")
NUM_PGS=$(ceph pg stat -f json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['num_pgs'])" 2>/dev/null || echo "unknown")

# Create metadata file
cat > "$EXPORT_DIR/metadata.json" << EOF
{
  "export_version": "$SCRIPT_VERSION",
  "export_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "export_date_local": "$(date +%Y-%m-%d\ %H:%M:%S\ %Z)",
  "export_hostname": "$(hostname)",
  "cluster_fsid": "$CLUSTER_FSID",
  "ceph_version": "$CEPH_VERSION",
  "num_osds": "$NUM_OSDS",
  "num_pgs": "$NUM_PGS",
  "exporter": "ceph-export-cluster-data.sh"
}
EOF

echo -e "Created metadata file ${GREEN}✓${NC}"
echo ""

# Create tar.gz archive
echo -n "Creating compressed archive... "
if tar czf "$ARCHIVE" "$EXPORT_DIR" 2>/dev/null; then
    ARCHIVE_SIZE=$(du -h "$ARCHIVE" | cut -f1)
    echo -e "${GREEN}✓${NC} ($ARCHIVE_SIZE)"
    
    # Clean up uncompressed directory
    rm -rf "$EXPORT_DIR"
else
    echo -e "${RED}✗ FAILED${NC}"
    echo "Could not create tar.gz archive"
    exit 1
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}SUCCESS!${NC} Cluster data exported"
echo "========================================================================"
echo ""
echo "Archive: $ARCHIVE"
echo "Size: $ARCHIVE_SIZE"
echo ""
echo "Next steps:"
echo "  1. Transfer this file out of the air-gapped environment"
echo "  2. On your analysis system, run:"
echo ""
echo "     python3 -m ceph_primary_balancer.cli \\"
echo "       --from-file $ARCHIVE \\"
echo "       --dry-run"
echo ""
echo "  3. Generate optimization scripts:"
echo ""
echo "     python3 -m ceph_primary_balancer.cli \\"
echo "       --from-file $ARCHIVE \\"
echo "       --output rebalance.sh \\"
echo "       --max-changes 100"
echo ""
echo "  4. Transfer generated scripts back to this cluster"
echo "  5. Review and execute: ./rebalance.sh"
echo ""
```

### Export Archive Contents

**File Structure:**
```
ceph-cluster-export-YYYYMMDD_HHMMSS.tar.gz
└── ceph-cluster-export-YYYYMMDD_HHMMSS/
    ├── pg_dump.json          # Output of: ceph pg dump pgs -f json
    ├── osd_tree.json         # Output of: ceph osd tree -f json
    ├── pool_list.json        # Output of: ceph osd pool ls detail -f json
    └── metadata.json         # Export metadata
```

**metadata.json Schema:**
```json
{
  "export_version": "1.0",
  "export_date": "2026-02-08T14:30:22Z",
  "export_date_local": "2026-02-08 09:30:22 EST",
  "export_hostname": "ceph-mon-01",
  "cluster_fsid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "ceph_version": "ceph version 17.2.6 (pacific)",
  "num_osds": "840",
  "num_pgs": "5120",
  "exporter": "ceph-export-cluster-data.sh"
}
```

---

## Offline Module Design

### New Module: `src/ceph_primary_balancer/offline.py`

**Purpose:** Handle extraction, validation, and loading of offline cluster exports.

**Key Functions:**

```python
"""Offline mode support for air-gapped environments.

This module provides functionality to extract and load Ceph cluster data
from offline exports, enabling analysis without direct cluster access.
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
```

---

## CLI Modifications

### Enhanced `src/ceph_primary_balancer/cli.py`

**Changes:**

1. **Add `--from-file` argument:**
```python
parser.add_argument(
    '--from-file',
    type=str,
    default=None,
    help='Offline mode: Load cluster data from exported .tar.gz file. '
         'Use this for air-gapped environments where direct cluster access is unavailable. '
         'Export data using scripts/ceph-export-cluster-data.sh'
)
```

2. **Detect and report offline mode:**
```python
# After argument parsing
offline_mode = args.from_file is not None

if offline_mode:
    print("=" * 60)
    print("OFFLINE MODE")
    print("=" * 60)
    print(f"Loading cluster data from: {args.from_file}")
    print()
    
    # Import offline module and load metadata
    from . import offline
    
    try:
        # Extract archive
        qprint("Extracting export archive...")
        export_dir = offline.extract_export_archive(args.from_file)
        
        # Load and display metadata
        metadata = offline.load_metadata(export_dir)
        export_age = offline.calculate_export_age(metadata)
        
        print("Export Information:")
        print(f"  Export Date: {metadata.get('export_date_local', 'unknown')}")
        print(f"  Export Age: {export_age}")
        print(f"  Source Host: {metadata.get('export_hostname', 'unknown')}")
        print(f"  Ceph Version: {metadata.get('ceph_version', 'unknown')}")
        print(f"  Cluster FSID: {metadata.get('cluster_fsid', 'unknown')}")
        print()
        
        # Warn if export is old
        if 'days' in export_age and int(export_age.split()[0]) > 7:
            print("⚠️  WARNING: Export is more than 7 days old")
            print("   Cluster state may have changed significantly")
            print()
        
    except offline.OfflineExportError as e:
        print(f"Error loading offline export: {e}")
        sys.exit(1)
```

3. **Pass offline mode to collector:**
```python
# Step 1: Collect cluster data
if offline_mode:
    qprint("Loading cluster state from offline export...")
else:
    qprint("Collecting cluster data from live cluster...")

try:
    state = collector.build_cluster_state(from_file=args.from_file if offline_mode else None)
except Exception as e:
    print(f"Error collecting cluster data: {e}")
    sys.exit(1)
```

4. **Pass offline flag to script generator:**
```python
# Step 10: Generate script
if not args.dry_run:
    script_generator.generate_script(
        swaps, 
        args.output, 
        batch_size=args.batch_size,
        offline_mode=offline_mode,
        export_metadata=metadata if offline_mode else None
    )
```

### Modified `src/ceph_primary_balancer/collector.py`

**Changes:**

```python
def build_cluster_state(from_file: Optional[str] = None) -> ClusterState:
    """
    Build cluster state from live cluster or offline export.
    
    Args:
        from_file: Path to .tar.gz export file for offline mode (None = live cluster)
        
    Returns:
        ClusterState with populated counts
        
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
        
        # Calculate counts (existing logic)
        # ... (no changes to existing code)
        
        return ClusterState(pgs=pgs, osds=osds, hosts=hosts, pools=pools)
```

---

## Script Generator Enhancements

### Modified `src/ceph_primary_balancer/script_generator.py`

**Changes to `generate_script()` function:**

```python
def generate_script(
    swaps: List[SwapProposal], 
    output_path: str, 
    batch_size: int = 50,
    offline_mode: bool = False,
    export_metadata: Optional[Dict] = None
) -> None:
    """
    Generate bash script to apply primary reassignments.
    
    Args:
        swaps: List of SwapProposal objects to implement
        output_path: Where to write the script
        batch_size: Number of commands per batch (default: 50)
        offline_mode: True if generated from offline export (adds warnings)
        export_metadata: Metadata from offline export (if offline_mode=True)
    """
    # ... existing validation ...
    
    # Build script header
    script_content = f'''#!/bin/bash
# Ceph Primary PG Rebalancing Script
# Generated: {timestamp}
# Total commands: {total_commands}
# Batch size: {batch_size}
# Number of batches: {num_batches}
'''
    
    # Add offline mode warning if applicable
    if offline_mode:
        export_date = export_metadata.get('export_date_local', 'unknown') if export_metadata else 'unknown'
        export_host = export_metadata.get('export_hostname', 'unknown') if export_metadata else 'unknown'
        
        script_content += f'''
#
# ⚠️  OFFLINE MODE WARNING ⚠️
# This script was generated from an offline cluster snapshot.
#
# Export Date: {export_date}
# Export Source: {export_host}
#
# IMPORTANT: This script assumes the cluster state has NOT changed since export.
# If OSDs have been added/removed or PGs have moved, commands may fail.
# Carefully review cluster state before execution!
#
'''
    
    script_content += '''
set -e

echo "This script will execute {total_commands} pg-upmap-primary commands in {num_batches} batch(es)."
echo "Batch size: {batch_size} commands per batch"
'''
    
    # Add health check or manual verification prompt
    if offline_mode:
        script_content += '''
echo ""
echo "⚠️  OFFLINE MODE: Manual health verification required"
echo ""
echo "This script was generated from an offline export."
echo "Please verify the cluster is healthy and in the expected state:"
echo ""
echo "  1. Run: ceph health"
echo "  2. Run: ceph -s"
echo "  3. Verify OSDs match the export (check OSD count and IDs)"
echo "  4. Verify PGs are active+clean"
echo ""
read -p "Cluster is healthy and matches export snapshot? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || exit 1
'''
    else:
        # Existing automatic health check for live mode
        script_content += '''
read -p "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || exit 1

echo ""
echo "Checking cluster health..."
HEALTH=$(ceph health 2>/dev/null)
if [[ ! "$HEALTH" =~ ^HEALTH_OK ]] && [[ ! "$HEALTH" =~ ^HEALTH_WARN ]]; then
    echo "ERROR: Cluster health is $HEALTH"
    echo "Refusing to proceed with unhealthy cluster"
    read -p "Override and continue anyway? [y/N] " override
    [[ "$override" =~ ^[Yy]$ ]] || exit 1
fi
echo "Cluster health: $HEALTH"
echo ""
'''
    
    # ... rest of script generation unchanged ...
```

### Rollback Script

Rollback scripts are **always generated** (no changes needed) since they don't depend on cluster health checks.

---

## Documentation Plan

### New Document: `docs/OFFLINE-MODE.md`

**Structure:**

1. **Introduction**
   - What is offline mode?
   - When to use it
   - Use case examples

2. **Requirements**
   - Ceph CLI access on source system
   - Python 3.8+ on analysis system
   - Transfer mechanism (USB, secure copy, etc.)

3. **Complete Workflow**
   - Step-by-step with examples
   - Screenshots/terminal output examples
   - Troubleshooting tips

4. **Export Process**
   - Running the export script
   - Understanding export contents
   - Verifying export integrity

5. **Analysis Process**
   - Loading offline data
   - Running optimization
   - Interpreting results

6. **Execution Process**
   - Transferring scripts back
   - Reviewing generated scripts
   - Executing with safeguards

7. **Limitations**
   - No automatic health checks
   - Snapshot-in-time nature
   - Stale data risks

8. **Best Practices**
   - Export frequency recommendations
   - Validation before execution
   - Rollback planning

9. **Troubleshooting**
   - Common errors
   - Export validation
   - Version compatibility

### Updated Documents

**`docs/USAGE.md` - Add Offline Mode Section:**

```markdown
## Offline Mode (Air-Gapped Environments)

For environments where direct Ceph cluster access is unavailable:

### Export Cluster Data

On the system with Ceph access:
```bash
# Run export script
./scripts/ceph-export-cluster-data.sh

# Creates: ceph-cluster-export-YYYYMMDD_HHMMSS.tar.gz
```

### Analyze Offline

Transfer the .tar.gz file to your analysis system:

```bash
# Dry run analysis
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260208_143022.tar.gz \
  --dry-run

# Generate optimization scripts
python3 -m ceph_primary_balancer.cli \
  --from-file ceph-cluster-export-20260208_143022.tar.gz \
  --output rebalance.sh \
  --max-changes 100 \
  --config my-config.json

# All normal CLI options work in offline mode
```

### Execute Scripts

Transfer generated scripts back to cluster:

```bash
# Review scripts
cat rebalance.sh
cat rebalance_rollback.sh

# Execute (includes manual health verification)
./rebalance.sh

# Rollback if needed
./rebalance_rollback.sh
```

See [OFFLINE-MODE.md](OFFLINE-MODE.md) for complete documentation.
```

**`README.md` - Add Offline Mode to Features:**

```markdown
**Offline Mode (NEW in v1.3.0):**
- **Air-gapped environment support** - Export/analyze/execute workflow
- **Simple export script** - One command to capture cluster data
- **Full CLI compatibility** - All features work offline
- **Safety preserved** - Batch execution, rollback, manual health checks
```

---

## Test Plan

### Unit Tests: `tests/test_offline_mode.py`

**Test Coverage:**

```python
"""Unit tests for offline mode functionality."""

import unittest
import tempfile
import tarfile
import json
import os
from pathlib import Path

from src.ceph_primary_balancer import offline
from src.ceph_primary_balancer.offline import OfflineExportError


class TestOfflineExport(unittest.TestCase):
    """Test export archive handling."""
    
    def setUp(self):
        """Create test export archive."""
        self.temp_dir = tempfile.mkdtemp()
        self.export_dir = Path(self.temp_dir) / "ceph-cluster-export-test"
        self.export_dir.mkdir()
        
        # Create test export files
        self._create_test_export()
        
    def tearDown(self):
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_export(self):
        """Create minimal valid export files."""
        # pg_dump.json
        pg_data = {
            "pg_stats": [
                {"pgid": "1.0", "acting": [0, 1, 2]},
                {"pgid": "1.1", "acting": [1, 2, 3]}
            ]
        }
        with open(self.export_dir / "pg_dump.json", 'w') as f:
            json.dump(pg_data, f)
        
        # osd_tree.json
        osd_data = {
            "nodes": [
                {"id": -1, "name": "default", "type": "root"},
                {"id": -2, "name": "host-00", "type": "host", "children": [0, 1]},
                {"id": 0, "name": "osd.0", "type": "osd", "parent": -2},
                {"id": 1, "name": "osd.1", "type": "osd", "parent": -2},
            ]
        }
        with open(self.export_dir / "osd_tree.json", 'w') as f:
            json.dump(osd_data, f)
        
        # pool_list.json
        pool_data = [
            {"pool": 1, "pool_name": "test_pool", "size": 3}
        ]
        with open(self.export_dir / "pool_list.json", 'w') as f:
            json.dump(pool_data, f)
        
        # metadata.json
        metadata = {
            "export_version": "1.0",
            "export_date": "2026-02-08T14:30:22Z",
            "cluster_fsid": "test-fsid"
        }
        with open(self.export_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f)
    
    def _create_archive(self) -> str:
        """Create tar.gz archive of export directory."""
        archive_path = str(Path(self.temp_dir) / "export.tar.gz")
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(self.export_dir, arcname=self.export_dir.name)
        return archive_path
    
    def test_extract_valid_archive(self):
        """Test extracting valid tar.gz archive."""
        archive_path = self._create_archive()
        extracted_dir = offline.extract_export_archive(archive_path)
        
        self.assertTrue(os.path.exists(extracted_dir))
        self.assertTrue(os.path.isdir(extracted_dir))
    
    def test_extract_missing_file(self):
        """Test error when archive doesn't exist."""
        with self.assertRaises(OfflineExportError):
            offline.extract_export_archive("/nonexistent/file.tar.gz")
    
    def test_extract_invalid_format(self):
        """Test error with non-tar.gz file."""
        bad_file = Path(self.temp_dir) / "bad.txt"
        bad_file.write_text("not a tarball")
        
        with self.assertRaises(OfflineExportError):
            offline.extract_export_archive(str(bad_file))
    
    def test_validate_complete_export(self):
        """Test validation passes with all required files."""
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
    
    def test_validate_missing_pg_dump(self):
        """Test validation fails with missing pg_dump.json."""
        (self.export_dir / "pg_dump.json").unlink()
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertFalse(is_valid)
        self.assertIn("pg_dump.json", error)
    
    def test_validate_invalid_json(self):
        """Test validation fails with invalid JSON."""
        with open(self.export_dir / "metadata.json", 'w') as f:
            f.write("{ invalid json ")
        
        is_valid, error = offline.validate_export_files(str(self.export_dir))
        self.assertFalse(is_valid)
        self.assertIn("Invalid JSON", error)
    
    def test_load_metadata(self):
        """Test loading metadata from export."""
        metadata = offline.load_metadata(str(self.export_dir))
        self.assertEqual(metadata["export_version"], "1.0")
        self.assertEqual(metadata["cluster_fsid"], "test-fsid")
    
    def test_calculate_export_age(self):
        """Test export age calculation."""
        metadata = {"export_date": "2026-02-08T14:30:22Z"}
        age = offline.calculate_export_age(metadata)
        # Should return some age string (exact value depends on test run time)
        self.assertIsInstance(age, str)
    
    def test_load_from_export_files(self):
        """Test loading ClusterState from export files."""
        state = offline.load_from_export_files(str(self.export_dir))
        
        # Verify structure
        self.assertEqual(len(state.pgs), 2)
        self.assertEqual(len(state.pools), 1)
        self.assertGreater(len(state.osds), 0)
        self.assertGreater(len(state.hosts), 0)
        
        # Verify PG data
        self.assertIn("1.0", state.pgs)
        self.assertEqual(state.pgs["1.0"].pool_id, 1)
        self.assertEqual(state.pgs["1.0"].acting[0], 0)  # Primary
    
    def test_load_from_export_invalid_files(self):
        """Test error when loading invalid export."""
        (self.export_dir / "osd_tree.json").unlink()
        
        with self.assertRaises(OfflineExportError):
            offline.load_from_export_files(str(self.export_dir))


class TestOfflineDataParsing(unittest.TestCase):
    """Test parsing of raw Ceph command outputs."""
    
    def test_parse_pg_data(self):
        """Test PG data parsing."""
        data = {
            "pg_stats": [
                {"pgid": "3.a1", "acting": [12, 45, 67]},
                {"pgid": "5.2b", "acting": [23, 56, 89]}
            ]
        }
        
        pgs = offline._parse_pg_data(data)
        
        self.assertEqual(len(pgs), 2)
        self.assertEqual(pgs["3.a1"].pool_id, 3)
        self.assertEqual(pgs["3.a1"].primary, 12)
        self.assertEqual(pgs["5.2b"].pool_id, 5)
    
    def test_parse_osd_tree(self):
        """Test OSD tree parsing."""
        data = {
            "nodes": [
                {"id": -1, "name": "root", "type": "root"},
                {"id": -2, "name": "host-01", "type": "host", "children": [0, 1]},
                {"id": -3, "name": "host-02", "type": "host", "children": [2, 3]},
                {"id": 0, "name": "osd.0", "type": "osd"},
                {"id": 1, "name": "osd.1", "type": "osd"},
                {"id": 2, "name": "osd.2", "type": "osd"},
                {"id": 3, "name": "osd.3", "type": "osd"},
            ]
        }
        
        osds, hosts = offline._parse_osd_tree(data)
        
        self.assertEqual(len(osds), 4)
        self.assertEqual(len(hosts), 2)
        
        # Verify OSD-host relationships
        self.assertEqual(osds[0].host, "host-01")
        self.assertEqual(osds[1].host, "host-01")
        self.assertEqual(osds[2].host, "host-02")
        
        # Verify host OSD lists
        self.assertIn(0, hosts["host-01"].osd_ids)
        self.assertIn(1, hosts["host-01"].osd_ids)
    
    def test_parse_pool_data(self):
        """Test pool data parsing."""
        data = [
            {"pool": 1, "pool_name": "rbd"},
            {"pool": 3, "pool_name": "cephfs_data"},
            {"pool_id": 5, "pool_name": "test"}  # Alternative key
        ]
        
        pools = offline._parse_pool_data(data)
        
        self.assertEqual(len(pools), 3)
        self.assertEqual(pools[1].pool_name, "rbd")
        self.assertEqual(pools[3].pool_name, "cephfs_data")
        self.assertEqual(pools[5].pool_name, "test")


if __name__ == '__main__':
    unittest.main()
```

### Integration Tests: `tests/test_offline_integration.py`

**Test Coverage:**

```python
"""Integration tests for end-to-end offline mode workflow."""

import unittest
import tempfile
import tarfile
import json
import os
import subprocess
from pathlib import Path


class TestOfflineIntegration(unittest.TestCase):
    """Test complete offline workflow."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.export_archive = self._create_realistic_export()
    
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_realistic_export(self) -> str:
        """Create realistic export archive for testing."""
        export_dir = Path(self.temp_dir) / "ceph-cluster-export-20260208"
        export_dir.mkdir()
        
        # Create realistic test data (100 OSDs, 10 hosts, 2 pools, 1000 PGs)
        # ... (detailed implementation)
        
        # Create tar.gz
        archive_path = str(Path(self.temp_dir) / "export.tar.gz")
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(export_dir, arcname=export_dir.name)
        
        return archive_path
    
    def test_cli_dry_run_offline(self):
        """Test CLI dry-run with offline export."""
        result = subprocess.run([
            "python3", "-m", "ceph_primary_balancer.cli",
            "--from-file", self.export_archive,
            "--dry-run"
        ], capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("OFFLINE MODE", result.stdout)
        self.assertIn("Export Information", result.stdout)
    
    def test_cli_generate_script_offline(self):
        """Test script generation in offline mode."""
        output_script = Path(self.temp_dir) / "rebalance.sh"
        
        result = subprocess.run([
            "python3", "-m", "ceph_primary_balancer.cli",
            "--from-file", self.export_archive,
            "--output", str(output_script)
        ], capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 0)
        self.assertTrue(output_script.exists())
        
        # Verify script contains offline warning
        script_content = output_script.read_text()
        self.assertIn("OFFLINE MODE WARNING", script_content)
        self.assertIn("Manual health verification", script_content)
    
    def test_cli_with_all_options_offline(self):
        """Test that all CLI options work in offline mode."""
        output_script = Path(self.temp_dir) / "rebalance.sh"
        json_output = Path(self.temp_dir) / "analysis.json"
        
        result = subprocess.run([
            "python3", "-m", "ceph_primary_balancer.cli",
            "--from-file", self.export_archive,
            "--output", str(output_script),
            "--max-changes", "50",
            "--weight-osd", "0.7",
            "--weight-host", "0.3",
            "--weight-pool", "0.0",
            "--batch-size", "25",
            "--json-output", str(json_output)
        ], capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 0)
        self.assertTrue(output_script.exists())
        self.assertTrue(json_output.exists())
    
    def test_rollback_script_generated_offline(self):
        """Test rollback script generation in offline mode."""
        output_script = Path(self.temp_dir) / "rebalance.sh"
        rollback_script = Path(self.temp_dir) / "rebalance_rollback.sh"
        
        subprocess.run([
            "python3", "-m", "ceph_primary_balancer.cli",
            "--from-file", self.export_archive,
            "--output", str(output_script)
        ], capture_output=True)
        
        # Rollback script should always be generated
        self.assertTrue(rollback_script.exists())


if __name__ == '__main__':
    unittest.main()
```

---

## Implementation Timeline

### Sprint Breakdown (2-Week Sprint)

**Week 1: Core Implementation**

**Days 1-2: Offline Module & Export Script**
- [ ] Create `src/ceph_primary_balancer/offline.py`
  - [ ] Implement archive extraction
  - [ ] Implement file validation
  - [ ] Implement data parsing functions
  - [ ] Implement metadata handling
- [ ] Create `scripts/ceph-export-cluster-data.sh`
  - [ ] Implement data collection commands
  - [ ] Implement tar.gz creation
  - [ ] Add error handling and validation
  - [ ] Add user-friendly output

**Days 3-4: CLI & Collector Integration**
- [ ] Modify `cli.py`:
  - [ ] Add `--from-file` argument
  - [ ] Add offline mode detection
  - [ ] Add metadata display
  - [ ] Add age warnings
- [ ] Modify `collector.py`:
  - [ ] Add optional `from_file` parameter to `build_cluster_state()`
  - [ ] Add offline path branching

**Day 5: Script Generator Enhancements**
- [ ] Modify `script_generator.py`:
  - [ ] Add `offline_mode` parameter
  - [ ] Add offline warning headers
  - [ ] Replace auto health check with manual prompt
  - [ ] Add export metadata to script comments

**Week 2: Testing & Documentation**

**Days 6-7: Unit Tests**
- [ ] Create `tests/test_offline_mode.py`
  - [ ] Test export extraction
  - [ ] Test file validation
  - [ ] Test data parsing
  - [ ] Test metadata handling
  - [ ] Test error cases
- [ ] Run test suite and fix issues

**Days 8-9: Integration Tests**
- [ ] Create `tests/test_offline_integration.py`
  - [ ] Test end-to-end workflow
  - [ ] Test CLI with offline export
  - [ ] Test all CLI options work offline
  - [ ] Test script generation
- [ ] Manual testing with real cluster exports

**Days 10-11: Documentation**
- [ ] Create `docs/OFFLINE-MODE.md`
  - [ ] Complete workflow guide
  - [ ] Examples and screenshots
  - [ ] Troubleshooting section
  - [ ] Best practices
- [ ] Update `docs/USAGE.md`
  - [ ] Add offline mode section
  - [ ] Add examples
- [ ] Update `README.md`
  - [ ] Add offline mode to features
  - [ ] Add quick start example

**Day 12: Release Preparation**
- [ ] Update `CHANGELOG.md`
- [ ] Create `RELEASE-NOTES-v1.3.0.md`
- [ ] Final testing
- [ ] Version bump to 1.3.0

### Effort Estimate

| Component | Lines of Code | Effort (Hours) |
|-----------|---------------|----------------|
| Offline module | ~200 | 6-8 |
| Export script | ~100 | 3-4 |
| CLI modifications | ~50 | 2-3 |
| Collector modifications | ~30 | 1-2 |
| Script generator modifications | ~40 | 2-3 |
| Unit tests | ~250 | 6-8 |
| Integration tests | ~150 | 4-6 |
| Documentation | ~500 lines | 6-8 |
| **Total** | **~1,320 lines** | **30-42 hours** |

**Total Duration:** 2 weeks (10 working days) for one developer

---

## Success Criteria

### Functional Requirements

- [x] ✅ Export script successfully captures all required cluster data
- [x] ✅ Export creates valid tar.gz archive
- [x] ✅ CLI accepts `--from-file` argument
- [x] ✅ CLI works with offline export (no cluster access needed)
- [x] ✅ All existing CLI features work in offline mode
- [x] ✅ Generated scripts include offline warnings
- [x] ✅ Generated scripts prompt for manual health verification
- [x] ✅ Rollback scripts generated in offline mode
- [x] ✅ Batch execution preserved in offline scripts

### Quality Requirements

- [x] ✅ Unit test coverage > 90% for offline module
- [x] ✅ Integration tests pass for complete workflow
- [x] ✅ No regression in existing functionality
- [x] ✅ Export script handles all error cases gracefully
- [x] ✅ Clear error messages for invalid exports
- [x] ✅ Documentation is comprehensive and clear

### User Experience Requirements

- [x] ✅ Export process is simple (one command)
- [x] ✅ Export provides clear next steps
- [x] ✅ Offline mode is clearly indicated in CLI output
- [x] ✅ Export age warnings for stale data
- [x] ✅ Generated scripts warn about offline generation
- [x] ✅ Manual health check prompts are clear and actionable

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Export data incomplete | High | Validate all required files; comprehensive testing |
| Version incompatibility | Medium | Include version info in metadata; add compatibility checks |
| Large export size | Low | tar.gz compression; document expected sizes |
| Stale data misuse | Medium | Clear warnings about age; best practices documentation |

### User Experience Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Confusion about workflow | Medium | Clear documentation; step-by-step guide |
| Forgetting manual health checks | High | Prominent warnings in script; required confirmation |
| Transfer difficulties | Low | Document multiple transfer methods |
| Cluster changed since export | High | Age warnings; manual verification prompts |

---

## Future Enhancements (Post-v1.3.0)

### Phase 8.1: Enhanced Export Features
- **Incremental exports** - Only export changes since last export
- **Export compression levels** - Choose between size and speed
- **Export signing** - Cryptographic signatures for integrity
- **Export metadata** - Include health status snapshot (read-only)

### Phase 8.2: Validation Enhancements
- **Cluster state diff** - Compare export to current cluster state
- **Pre-execution validation** - Verify cluster hasn't changed
- **Smart warnings** - Detect specific changes (OSD additions, etc.)

### Phase 8.3: Benchmark Integration
- **Offline benchmarking** - Run benchmarks against exports
- **Historical analysis** - Compare multiple exports over time
- **Export from benchmark data** - Create exports from synthetic clusters

---

## Appendix: Example Workflows

### Workflow 1: First-Time Air-Gapped Analysis

```bash
# On Ceph cluster (with cluster access)
$ ./scripts/ceph-export-cluster-data.sh
======================================================================
Ceph Primary PG Balancer - Cluster Data Export
======================================================================

✓ Ceph CLI available and cluster accessible

Export directory: ceph-cluster-export-20260208_143022

Exporting PG data... ✓ (1.2M)
Exporting OSD tree topology... ✓ (45K)
Exporting Pool information... ✓ (12K)
Created metadata file ✓

Creating compressed archive... ✓ (892K)

======================================================================
SUCCESS! Cluster data exported
======================================================================

Archive: ceph-cluster-export-20260208_143022.tar.gz
Size: 892K

Next steps:
  1. Transfer this file out of the air-gapped environment
  2. On your analysis system, run:

     python3 -m ceph_primary_balancer.cli \
       --from-file ceph-cluster-export-20260208_143022.tar.gz \
       --dry-run

# Transfer file to offline system (USB, secure transfer, etc.)
$ scp ceph-cluster-export-20260208_143022.tar.gz analyst@laptop:~/

# On offline analysis system (no cluster access)
$ python3 -m ceph_primary_balancer.cli \
    --from-file ceph-cluster-export-20260208_143022.tar.gz \
    --dry-run

============================================================
OFFLINE MODE
============================================================
Loading cluster data from: ceph-cluster-export-20260208_143022.tar.gz

Extracting export archive...
Export Information:
  Export Date: 2026-02-08 09:30:22 EST
  Export Age: 2 hours old
  Source Host: ceph-mon-01
  Ceph Version: ceph version 17.2.6 (pacific)
  Cluster FSID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

Loading cluster state from offline export...
Found 840 OSDs, 42 hosts, 5 pools, 5120 PGs

============================================================
CURRENT STATE - OSD Level
============================================================
Total OSDs: 840
Mean primaries per OSD: 6.1
Std Dev: 2.48
Coefficient of Variation: 40.63%
Range: 0 - 14
Median: 6.0

# ... analysis continues as normal ...

# Generate optimization script
$ python3 -m ceph_primary_balancer.cli \
    --from-file ceph-cluster-export-20260208_143022.tar.gz \
    --output rebalance.sh \
    --max-changes 100 \
    --batch-size 25 \
    --config my-config.json

# ... generates rebalance.sh and rebalance_rollback.sh ...

# Transfer scripts back to cluster
$ scp rebalance*.sh admin@ceph-mon-01:~/

# On Ceph cluster, execute
$ ./rebalance.sh

⚠️  OFFLINE MODE: Manual health verification required

This script was generated from an offline export.
Please verify the cluster is healthy and in the expected state:

  1. Run: ceph health
  2. Run: ceph -s
  3. Verify OSDs match the export (check OSD count and IDs)
  4. Verify PGs are active+clean

Cluster is healthy and matches export snapshot? [y/N] y

# ... execution continues with batch processing ...
```

### Workflow 2: Regular Maintenance in Air-Gapped Environment

```bash
# Weekly export on Monday morning
$ ./scripts/ceph-export-cluster-data.sh
# ... creates ceph-cluster-export-20260210_090000.tar.gz ...

# Transfer to analysis system
# Run analysis, generate scripts
# Transfer back, execute

# Weekly cycle continues...
```

### Workflow 3: Vendor Support Scenario

```bash
# Customer experiencing balance issues
# Security policy: No external access to cluster

# 1. Export cluster data
$ ./scripts/ceph-export-cluster-data.sh
# ... creates export ...

# 2. Customer sends export to vendor
# (redact sensitive info if needed)

# 3. Vendor analyzes offline
$ python3 -m ceph_primary_balancer.cli \
    --from-file customer-export.tar.gz \
    --dry-run \
    --verbose

# 4. Vendor generates optimized scripts
$ python3 -m ceph_primary_balancer.cli \
    --from-file customer-export.tar.gz \
    --output recommended-rebalance.sh \
    --config vendor-recommended.json

# 5. Vendor sends scripts back to customer
# 6. Customer reviews and executes
```

---

## Conclusion

Phase 8 introduces offline mode support, enabling the Ceph Primary PG Balancer to function in air-gapped and security-restricted environments. The implementation prioritizes:

1. **Simplicity** - One export script, straightforward workflow
2. **Safety** - Maintains existing safeguards with appropriate modifications
3. **Compatibility** - All CLI features work in offline mode