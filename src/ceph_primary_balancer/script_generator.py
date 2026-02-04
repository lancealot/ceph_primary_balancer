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
from typing import List, Optional

from .models import SwapProposal


def generate_script(swaps: List[SwapProposal], output_path: str):
    """
    Generate an executable bash script that applies primary reassignments.
    
    The generated script includes:
    - Safety confirmation prompt before execution
    - Cluster health check (v1.0.0+) - verifies HEALTH_OK or HEALTH_WARN
    - Progress tracking with formatted output
    - Error handling and failure counting
    - Summary of successful and failed operations
    
    Args:
        swaps: List of SwapProposal objects containing primary reassignments
        output_path: Path where the script should be written
    
    Raises:
        SystemExit: Exits with code 1 if swaps list is empty or file write fails
        
    Example:
        >>> swaps = [SwapProposal("3.a1", 12, 45, 0.5)]
        >>> generate_script(swaps, "rebalance.sh")
        # Creates executable script at rebalance.sh
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
    
    # Build script header with shebang and metadata
    script_content = f'''#!/bin/bash
# Ceph Primary PG Rebalancing Script
# Generated: {timestamp}
# Total commands: {total_commands}

set -e

echo "This script will execute {total_commands} pg-upmap-primary commands."
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

TOTAL={total_commands}
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
    
    # Add command calls for each swap
    for swap in swaps:
        script_content += f'apply_mapping "{swap.pgid}" {swap.new_primary}\n'
    
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
