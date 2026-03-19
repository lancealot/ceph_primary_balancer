#!/bin/bash
# Advanced Dynamic Weight Optimization Examples
#
# This script demonstrates advanced usage of dynamic weight optimization,
# including both strategies, custom parameters, and production workflows.

set -e

echo "=============================================="
echo "Dynamic Weight Optimization - Advanced Usage"
echo "=============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to run example
run_example() {
    local title="$1"
    local description="$2"
    local command="$3"

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Example: $title${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "$description"
    echo ""
    echo -e "${YELLOW}Command:${NC}"
    echo "$command"
    echo ""

    read -p "Run this example? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        eval "$command"
        echo ""
        echo -e "${GREEN}Example complete!${NC}"
    else
        echo "Skipped."
    fi
}

# Example 1: Compare both strategies
run_example \
    "Compare Both Strategies" \
    "Run dry-run with each strategy to see how they differ.
This helps you understand which strategy works best for your cluster." \
    "echo '--- Target Distance Strategy (Default) ---' && \
python3 -m ceph_primary_balancer.cli --dynamic-weights --dynamic-strategy target_distance --dry-run && \
echo '' && echo '--- Two Phase Strategy ---' && \
python3 -m ceph_primary_balancer.cli --dynamic-weights --dynamic-strategy two_phase --dry-run"

# Example 2: Verbose output to see weight evolution
run_example \
    "Verbose Mode - Watch Weights Adapt" \
    "Use verbose mode to see detailed weight evolution during optimization.
Shows weight updates and CV changes at each iteration." \
    "python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --dynamic-strategy target_distance \
  --verbose \
  --dry-run"

# Example 3: Fast convergence with frequent updates
run_example \
    "Fast Convergence (5-Iteration Updates)" \
    "Update weights more frequently (every 5 iterations) for faster adaptation.
Best for large clusters or when rapid convergence is important." \
    "python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --dynamic-strategy target_distance \
  --weight-update-interval 5 \
  --dry-run"

# Example 4: Stable optimization with less frequent updates
run_example \
    "Stable Optimization (20-Iteration Updates)" \
    "Update weights less frequently (every 20 iterations) for more stable behavior.
Best for debugging or when you want predictable weight changes." \
    "python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --dynamic-strategy target_distance \
  --weight-update-interval 20 \
  --dry-run"

# Example 5: Two-phase strategy for pool-heavy clusters
run_example \
    "Two-Phase Strategy for Pool Convergence" \
    "Uses target_distance weights initially, then hard-switches to pool-focused
weights once OSD and host CV drop below threshold. Best for clusters where
pool CV is the hardest dimension to converge." \
    "python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --dynamic-strategy two_phase \
  --dry-run"

# Example 6: Dynamic weights + max changes limit
run_example \
    "Production-Safe with Change Limit" \
    "Combine dynamic weights with max changes for safe production use.
Limits the number of swaps while optimizing their selection." \
    "python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --max-changes 100 \
  --dry-run"

# Example 7: Full production workflow
run_example \
    "Complete Production Workflow" \
    "Full production workflow with all safety features:
- Dynamic weights for efficiency
- Limited changes for safety
- Batch execution for control
- All outputs for documentation" \
    "OUTPUT_DIR=\"./rebalance-\$(date +%Y%m%d_%H%M%S)\" && \
python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --dynamic-strategy target_distance \
  --max-changes 150 \
  --batch-size 25 \
  --output-dir \"\$OUTPUT_DIR\" \
  --json-output \"\$OUTPUT_DIR/analysis.json\" \
  --report-output \"\$OUTPUT_DIR/report.md\" && \
echo '' && \
echo 'Generated files:' && \
ls -lh \"\$OUTPUT_DIR\""

# Example 8: Using configuration file
run_example \
    "Configuration File Workflow" \
    "Use pre-configured settings from config file.
Most convenient for repeated operations." \
    "python3 -m ceph_primary_balancer.cli \
  --config config-examples/dynamic-weights.json \
  --dry-run"

echo ""
echo "=============================================="
echo "Advanced Examples Complete!"
echo "=============================================="
echo ""
echo -e "${GREEN}Summary of Strategies:${NC}"
echo ""
echo "1. Target Distance (recommended):"
echo "   - Focuses on dimensions above target"
echo "   - Ignores already-balanced dimensions"
echo "   - Best overall performance in most cases"
echo ""
echo "2. Two Phase:"
echo "   - Uses target_distance initially"
echo "   - Switches to pool-focused weights once OSD/host converge"
echo "   - Best for clusters where pool CV is hardest to reduce"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Choose the strategy that fits your cluster"
echo "  2. Test with --dry-run first"
echo "  3. Generate script for production use"
echo "  4. Monitor results and adjust if needed"
echo ""
echo "Config examples: config-examples/dynamic-weights.json"
