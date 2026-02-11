"""
Script generation module for Ceph Primary PG Balancer.

This module generates executable bash scripts that apply primary reassignments
using `ceph osd pg-upmap-primary` commands. The generated scripts include
safety features like confirmation prompts, progress tracking, and error handling.

Also includes rollback script generation for safely reversing changes.
"""

import os
import sys
from datetime import datetime
from typing import List, Optional, Dict

from .models import SwapProposal


def generate_script(
    swaps: List[SwapProposal],
    output_path: str,
    batch_size: int = 50,
    offline_mode: bool = False,
    export_metadata: Optional[Dict] = None
):
    """
    Generate an executable bash script that applies primary reassignments.
    
    The generated script includes:
    - Safety confirmation prompt before execution
    - Cluster health check (v1.0.0+) - verifies HEALTH_OK or HEALTH_WARN
    - Batched execution with configurable batch sizes (v0.7.0+)
    - Progress tracking with formatted output per batch
    - Error handling and failure counting
    - Summary of successful and failed operations
    - Offline mode warnings and manual verification (v1.5.0+)
    
    Args:
        swaps: List of SwapProposal objects containing primary reassignments
        output_path: Path where the script should be written
        batch_size: Number of commands to execute per batch (default: 50)
        offline_mode: True if generated from offline export (adds warnings, v1.5.0)
        export_metadata: Metadata from offline export (if offline_mode=True, v1.5.0)
    
    Raises:
        SystemExit: Exits with code 1 if swaps list is empty or file write fails
        
    Example:
        >>> swaps = [SwapProposal("3.a1", 12, 45, 0.5)]
        >>> generate_script(swaps, "rebalance.sh", batch_size=50)
        # Creates executable script with batched execution at rebalance.sh
    """
    # Validate input
    if not swaps:
        print("Error: No swaps to generate script for")
        print("The cluster may already be balanced or no valid swaps were found")
        sys.exit(1)
    
    # Validate output path directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        print(f"Error: Output directory does not exist: {output_dir}")
        print("Please ensure the directory exists before generating the script")
        sys.exit(1)
    
    # Generate timestamp
    timestamp = datetime.now().isoformat()
    total_commands = len(swaps)
    num_batches = (total_commands + batch_size - 1) // batch_size  # Ceiling division
    
    # Build script header with shebang and metadata
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
'''.format(total_commands=total_commands, num_batches=num_batches, batch_size=batch_size)
    
    # Add health check or manual verification prompt based on mode
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
    
    script_content += '''

TOTAL={total_commands}
BATCH_SIZE={batch_size}
COUNT=0
FAILED=0

apply_mapping() {{
    local pgid=$1
    local new_primary=$2
    ((COUNT++))
    
    if ceph osd pg-upmap-primary "$pgid" "$new_primary" 2>/dev/null; then
        printf "[%3d/%d] %-12s -> OSD.%-4d OK\\n" "$COUNT" "$TOTAL" "$pgid" "$new_primary"
    else
        printf "[%3d/%d] %-12s -> OSD.%-4d FAILED\\n" "$COUNT" "$TOTAL" "$pgid" "$new_primary"
        ((FAILED++))
    fi
}}

'''
    
    # Group swaps into batches and generate commands
    for batch_num in range(num_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_commands)
        batch = swaps[start_idx:end_idx]
        batch_count = end_idx - start_idx
        
        # Add batch header
        script_content += f'''
# ==================== Batch {batch_num + 1}/{num_batches} ====================
echo ""
echo "=== Batch {batch_num + 1}/{num_batches}: Commands {start_idx + 1}-{end_idx} ({batch_count} commands) ==="
echo ""

'''
        
        # Add command calls for this batch
        for swap in batch:
            script_content += f'apply_mapping "{swap.pgid}" {swap.new_primary}\n'
        
        # Add pause between batches (except after last batch)
        if batch_num < num_batches - 1:
            script_content += f'''
echo ""
echo "Batch {batch_num + 1}/{num_batches} complete. Progress: $COUNT/$TOTAL commands ($FAILED failed)"
read -p "Continue to next batch? [Y/n] " continue_batch
[[ "$continue_batch" =~ ^[Nn]$ ]] && echo "Stopped by user" && exit 0
'''
    
    # Add summary footer
    script_content += f'''
echo ""
echo "Complete: $((TOTAL - FAILED)) successful, $FAILED failed"
'''
    
    # Write script to file with error handling
    try:
        with open(output_path, 'w') as f:
            f.write(script_content)
    except PermissionError:
        print(f"Error: Permission denied writing to: {output_path}")
        print("Check file permissions and try again")
        sys.exit(1)
    except OSError as e:
        print(f"Error: Failed to write script to {output_path}: {e}")
        sys.exit(1)
    
    # Make script executable (chmod 755)
    try:
        os.chmod(output_path, 0o755)
    except OSError as e:
        print(f"Warning: Could not make script executable: {e}")
        print(f"You may need to run: chmod +x {output_path}")


def generate_rollback_script(swaps: List[SwapProposal], output_path: str) -> Optional[str]:
    """
    Generate a rollback script that reverses all proposed primary reassignments.
    
    This function creates a bash script that undoes the changes made by the main
    rebalancing script. Each swap is reversed (old and new primaries are swapped).
    This provides a safety mechanism for quickly reverting changes if needed.
    
    Args:
        swaps: List of SwapProposal objects from the optimization
        output_path: Original script output path (rollback will be derived from this)
    
    Returns:
        Path to the generated rollback script, or None if generation failed
    
    Example:
        >>> swaps = [SwapProposal("3.a1", 12, 45, 0.5)]
        >>> rollback_path = generate_rollback_script(swaps, "rebalance.sh")
        >>> print(rollback_path)  # "rebalance_rollback.sh"
    """
    # Validate input
    if not swaps:
        print("Warning: No swaps to generate rollback script for")
        return None
    
    # Create reverse swaps (swap old and new primaries)
    reverse_swaps = [
        SwapProposal(
            pgid=swap.pgid,
            old_primary=swap.new_primary,  # Reversed
            new_primary=swap.old_primary,   # Reversed
            score_improvement=0.0  # Not relevant for rollback
        )
        for swap in swaps
    ]
    
    # Determine rollback script path
    if output_path.endswith('.sh'):
        rollback_path = output_path[:-3] + '_rollback.sh'
    else:
        rollback_path = output_path + '_rollback.sh'
    
    # Generate timestamp
    timestamp = datetime.now().isoformat()
    total_commands = len(reverse_swaps)
    
    # Build rollback script with clear warnings
    script_content = f'''#!/bin/bash
# Ceph Primary PG Rollback Script
# Generated: {timestamp}
# Total rollback commands: {total_commands}
#
# WARNING: This script reverses the primary assignments made by the
# corresponding rebalancing script. Use this only if you need to undo
# the changes made by the rebalancing operation.

set -e

echo "=========================================="
echo "  ROLLBACK SCRIPT"
echo "=========================================="
echo "This script will REVERSE {total_commands} primary assignments."
echo "This will restore primaries to their previous OSDs."
echo ""
read -p "Are you sure you want to rollback? [y/N] " confirm
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

TOTAL={total_commands}
COUNT=0
FAILED=0

apply_mapping() {{
    local pgid=$1
    local new_primary=$2
    ((COUNT++))
    
    if ceph osd pg-upmap-primary "$pgid" "$new_primary" 2>/dev/null; then
        printf "[%3d/%d] %-12s -> OSD.%-4d OK (ROLLED BACK)\\n" "$COUNT" "$TOTAL" "$pgid" "$new_primary"
    else
        printf "[%3d/%d] %-12s -> OSD.%-4d FAILED\\n" "$COUNT" "$TOTAL" "$pgid" "$new_primary"
        ((FAILED++))
    fi
}}

'''
    
    # Add rollback command calls (with reversed swaps)
    for swap in reverse_swaps:
        script_content += f'apply_mapping "{swap.pgid}" {swap.new_primary}\n'
    
    # Add summary footer
    script_content += f'''
echo ""
echo "Rollback Complete: $((TOTAL - FAILED)) successful, $FAILED failed"
'''
    
    # Write rollback script to file
    try:
        with open(rollback_path, 'w') as f:
            f.write(script_content)
    except (PermissionError, OSError) as e:
        print(f"Warning: Failed to write rollback script to {rollback_path}: {e}")
        return None
    
    # Make script executable
    try:
        os.chmod(rollback_path, 0o755)
    except OSError as e:
        print(f"Warning: Could not make rollback script executable: {e}")
        print(f"You may need to run: chmod +x {rollback_path}")
    
    return rollback_path
