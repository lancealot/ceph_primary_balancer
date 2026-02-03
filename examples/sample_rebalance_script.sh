#!/bin/bash
# Ceph Primary PG Rebalancing Script
# Generated: 2026-02-03T15:30:45.123456
# Tool Version: 0.4.0
# Total commands: 45
#
# This script will reassign primary PGs to optimize cluster balance
# across OSD, Host, and Pool dimensions.
#
# SAFETY NOTES:
# - This only changes primary assignment (metadata)
# - No data is moved between OSDs
# - Changes take effect immediately
# - Each command is fast (< 1 second)

set -e

echo "Ceph Primary PG Rebalancing Script"
echo "==================================="
echo ""
echo "This script will execute 45 pg-upmap-primary commands."
echo "Current state: OSD CV=29.1%, Host CV=15.3%, Pool CV=22.4%"
echo "Target state:  OSD CV=9.2%, Host CV=6.8%, Pool CV=8.5%"
echo ""
read -p "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }

TOTAL=45
COUNT=0
FAILED=0

apply_mapping() {
    local pg_id="$1"
    local new_primary="$2"
    local current_count=$((COUNT + 1))
    
    printf "[%3d/%3d] %-12s -> %-8s " "$current_count" "$TOTAL" "$pg_id" "OSD.$new_primary"
    
    if ceph osd pg-upmap-primary "$pg_id" "$new_primary" 2>/dev/null; then
        echo "OK"
        COUNT=$((COUNT + 1))
    else
        echo "FAILED"
        FAILED=$((FAILED + 1))
        COUNT=$((COUNT + 1))
    fi
}

# Swap 1: PG 3.0 (pool: rbd) -> OSD.12
apply_mapping "3.0" "12"

# Swap 2: PG 3.5 (pool: rbd) -> OSD.7
apply_mapping "3.5" "7"

# Swap 3: PG 5.2 (pool: cephfs_data) -> OSD.20
apply_mapping "5.2" "20"

# Swap 4: PG 5.7 (pool: cephfs_data) -> OSD.4
apply_mapping "5.7" "4"

# Swap 5: PG 1.1a (pool: rgw.buckets.data) -> OSD.11
apply_mapping "1.1a" "11"

# Swap 6: PG 1.2f (pool: rgw.buckets.data) -> OSD.17
apply_mapping "1.2f" "17"

# Swap 7: PG 1.38 (pool: rgw.buckets.data) -> OSD.2
apply_mapping "1.38" "2"

# Swap 8: PG 3.c (pool: rbd) -> OSD.9
apply_mapping "3.c" "9"

# Swap 9: PG 5.11 (pool: cephfs_data) -> OSD.13
apply_mapping "5.11" "13"

# Swap 10: PG 7.3 (pool: test) -> OSD.6
apply_mapping "7.3" "6"

# Swap 11: PG 2.15 (pool: volumes) -> OSD.18
apply_mapping "2.15" "18"

# Swap 12: PG 3.1b (pool: rbd) -> OSD.21
apply_mapping "3.1b" "21"

# Swap 13: PG 5.24 (pool: cephfs_data) -> OSD.10
apply_mapping "5.24" "10"

# Swap 14: PG 1.45 (pool: rgw.buckets.data) -> OSD.14
apply_mapping "1.45" "14"

# Swap 15: PG 3.22 (pool: rbd) -> OSD.5
apply_mapping "3.22" "5"

# Swap 16: PG 5.33 (pool: cephfs_data) -> OSD.16
apply_mapping "5.33" "16"

# Swap 17: PG 1.56 (pool: rgw.buckets.data) -> OSD.23
apply_mapping "1.56" "23"

# Swap 18: PG 7.8 (pool: test) -> OSD.1
apply_mapping "7.8" "1"

# Swap 19: PG 2.29 (pool: volumes) -> OSD.0
apply_mapping "2.29" "0"

# Swap 20: PG 3.3a (pool: rbd) -> OSD.20
apply_mapping "3.3a" "20"

# Swap 21: PG 5.47 (pool: cephfs_data) -> OSD.7
apply_mapping "5.47" "7"

# Swap 22: PG 1.68 (pool: rgw.buckets.data) -> OSD.12
apply_mapping "1.68" "12"

# Swap 23: PG 3.4d (pool: rbd) -> OSD.4
apply_mapping "3.4d" "4"

# Swap 24: PG 5.5e (pool: cephfs_data) -> OSD.11
apply_mapping "5.5e" "11"

# Swap 25: PG 1.7a (pool: rgw.buckets.data) -> OSD.17
apply_mapping "1.7a" "17"

# Swap 26: PG 7.f (pool: test) -> OSD.2
apply_mapping "7.f" "2"

# Swap 27: PG 2.3c (pool: volumes) -> OSD.9
apply_mapping "2.3c" "9"

# Swap 28: PG 3.58 (pool: rbd) -> OSD.13
apply_mapping "3.58" "13"

# Swap 29: PG 5.69 (pool: cephfs_data) -> OSD.6
apply_mapping "5.69" "6"

# Swap 30: PG 1.8b (pool: rgw.buckets.data) -> OSD.18
apply_mapping "1.8b" "18"

# Swap 31: PG 3.6c (pool: rbd) -> OSD.21
apply_mapping "3.6c" "21"

# Swap 32: PG 5.7d (pool: cephfs_data) -> OSD.10
apply_mapping "5.7d" "10"

# Swap 33: PG 1.9e (pool: rgw.buckets.data) -> OSD.14
apply_mapping "1.9e" "14"

# Swap 34: PG 7.12 (pool: test) -> OSD.5
apply_mapping "7.12" "5"

# Swap 35: PG 2.4f (pool: volumes) -> OSD.16
apply_mapping "2.4f" "16"

# Swap 36: PG 3.7a (pool: rbd) -> OSD.23
apply_mapping "3.7a" "23"

# Swap 37: PG 5.8b (pool: cephfs_data) -> OSD.1
apply_mapping "5.8b" "1"

# Swap 38: PG 1.ac (pool: rgw.buckets.data) -> OSD.0
apply_mapping "1.ac" "0"

# Swap 39: PG 3.8d (pool: rbd) -> OSD.20
apply_mapping "3.8d" "20"

# Swap 40: PG 5.9e (pool: cephfs_data) -> OSD.7
apply_mapping "5.9e" "7"

# Swap 41: PG 1.bf (pool: rgw.buckets.data) -> OSD.12
apply_mapping "1.bf" "12"

# Swap 42: PG 3.9a (pool: rbd) -> OSD.4
apply_mapping "3.9a" "4"

# Swap 43: PG 5.ab (pool: cephfs_data) -> OSD.11
apply_mapping "5.ab" "11"

# Swap 44: PG 1.cd (pool: rgw.buckets.data) -> OSD.17
apply_mapping "1.cd" "17"

# Swap 45: PG 7.1e (pool: test) -> OSD.2
apply_mapping "7.1e" "2"

echo ""
echo "========================================"
echo "Complete: $COUNT successful, $FAILED failed"
echo "========================================"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "Warning: $FAILED command(s) failed."
    echo "This is usually due to PG state changes since analysis."
    echo "Run the tool again to generate a fresh script if needed."
    exit 1
fi

echo ""
echo "Success! Primary PG distribution has been optimized."
echo ""
echo "Recommended next steps:"
echo "  1. Verify cluster health: ceph -s"
echo "  2. Check new distribution: python3 -m ceph_primary_balancer.cli --dry-run"
echo "  3. Monitor I/O distribution to confirm improvement"
