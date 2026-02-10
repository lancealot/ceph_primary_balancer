#!/bin/bash
# Advanced Dynamic Weight Optimization Examples
# Phase 7.1: Dynamic Weight Optimization
#
# This script demonstrates advanced usage of dynamic weight optimization,
# including all three strategies, custom parameters, and production workflows.

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
        echo -e "${GREEN}✅ Example complete!${NC}"
    else
        echo "Skipped."
    fi
}

# Example 1: Compare all three strategies
run_example \
    "Compare All Three Strategies" \
    "Run dry-run with each strategy to see how they differ.
This helps you understand which strategy works best for your cluster." \
    "echo '--- Proportional Strategy ---' && \
python3 -m ceph_primary_balancer.cli --dynamic-weights --dynamic-strategy proportional --dry-run && \
echo '' && echo '--- Target Distance Strategy (Default) ---' && \
python3 -m ceph_primary_balancer.cli --dynamic-weights --dynamic-strategy target_distance --dry-run && \
echo '' && echo '--- Adaptive Hybrid Strategy ---' && \
python3 -m ceph_primary_balancer.cli --dynamic-weights --dynamic-strategy adaptive_hybrid --dry-run"

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

# Example 5: Dynamic weights + pool filter
run_example \
    "Pool-Specific Dynamic Optimization" \
    "Optimize a specific pool with dynamic weights.
Useful for multi-pool clusters with uneven imbalances." \
    "python3 -m ceph_primary_balancer.cli \
  --dynamic-weights \
  --pool 3 \
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

# Example 9: Adaptive hybrid with custom parameters
run_example \
    "Adaptive Hybrid with Custom Config" \
    "Use adaptive hybrid strategy with custom-tuned parameters.
Shows how to use the example config file with overrides." \
    "python3 -m ceph_primary_balancer.cli \
  --config examples/dynamic_weights_config.json \
  --dry-run"

echo ""
echo "=============================================="
echo "Advanced Examples Complete!"
echo "=============================================="
echo ""
echo -e "${GREEN}Summary of Strategies:${NC}"
echo ""
echo "1. Proportional (simple):"
echo "   - Weights proportional to CV values"
echo "   - Predictable, easy to understand"
echo "   - Best for evenly imbalanced clusters"
echo ""
echo "2. Target Distance (recommended):"
echo "   - Focuses on dimensions above target"
echo "   - Ignores already-balanced dimensions"
echo "   - Best overall performance in most cases"
echo ""
echo "3. Adaptive Hybrid (advanced):"
echo "   - Tracks improvement rates"
echo "   - Boosts slow-improving dimensions"
echo "   - Exponential smoothing prevents oscillation"
echo "   - Best for complex or stuck optimizations"
echo ""
echo -e "${GREEN}Performance Expectations:${NC}"
echo "  ✅ 15-25% faster convergence"
echo "  ✅ 6-8% better final balance"
echo "  ✅ <1% overhead"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Choose the strategy that fits your cluster"
echo "  2. Test with --dry-run first"
echo "  3. Generate script for production use"
echo "  4. Monitor results and adjust if needed"
echo ""
echo "Full documentation: docs/DYNAMIC-WEIGHTS.md"
echo "Config examples: config-examples/dynamic-weights.json"
echo "                 examples/dynamic_weights_config.json"
