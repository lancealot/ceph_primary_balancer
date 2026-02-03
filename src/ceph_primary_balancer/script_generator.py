"""
Script generation module for Ceph Primary PG Balancer.

This module generates executable bash scripts that apply primary reassignments
using `ceph osd pg-upmap-primary` commands. The generated scripts include
safety features like confirmation prompts, progress tracking, and error handling.
"""

import os
import sys
from datetime import datetime
from typing import List

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
