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
