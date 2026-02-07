#!/bin/bash
# Comprehensive optimization strategy comparison test
# Tests all meaningful combinations of optimization levels and weights

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

RESULTS_DIR="optimization_comparison_results"
mkdir -p "$RESULTS_DIR"

echo "================================================================================"
echo "COMPREHENSIVE OPTIMIZATION STRATEGY COMPARISON"
echo "================================================================================"
echo "Test cluster: 840 OSDs, 30 hosts, 30 pools, 5,232 PGs"
echo "Results directory: $RESULTS_DIR"
echo "Date: $(date)"
echo "================================================================================"
echo ""

# Function to run a test and capture results
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    local output_file="$RESULTS_DIR/${test_name}.txt"
    local time_file="$RESULTS_DIR/${test_name}_timing.txt"
    
    echo -e "${BLUE}[TEST]${NC} $test_name"
    echo "Command: $test_cmd"
    echo ""
    
    # Run with time measurement
    /usr/bin/time -p bash -c "$test_cmd" > "$output_file" 2> "$time_file"
    
    # Extract key metrics
    local iterations=$(grep -o "Iteration [0-9]*:" "$output_file" | tail -1 | grep -o "[0-9]*" || echo "0")
    local swaps=$(grep "Proposed swaps:" "$output_file" | grep -o "[0-9]*" || echo "0")
    local osd_cv_before=$(grep "CV.*40\." "$output_file" | head -1 | grep -o "[0-9]*\.[0-9]*%" | head -1 || echo "N/A")
    local osd_cv_after=$(grep "OSD CV Improvement:" "$output_file" | grep -o "[0-9]*\.[0-9]*%" | tail -1 || echo "N/A")
    local elapsed_time=$(grep "real" "$time_file" | awk '{print $2}' || echo "N/A")
    
    echo -e "${GREEN}[DONE]${NC} Completed in ${elapsed_time}s"
    echo "       Iterations: $iterations | Swaps: $swaps | OSD CV: $osd_cv_before → $osd_cv_after"
    echo ""
}

echo "================================================================================"
echo "SINGLE-DIMENSION OPTIMIZATIONS"
echo "================================================================================"
echo ""

# Test 1: OSD-Only
run_test "1_osd_only" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd"

# Test 2: HOST-Only
run_test "2_host_only" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels host"

# Test 3: POOL-Only
run_test "3_pool_only" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels pool"

echo "================================================================================"
echo "TWO-DIMENSION OPTIMIZATIONS"
echo "================================================================================"
echo ""

# Test 4: OSD+HOST
run_test "4_osd_host" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,host"

# Test 5: OSD+POOL
run_test "5_osd_pool" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,pool"

# Test 6: HOST+POOL
run_test "6_host_pool" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels host,pool"

echo "================================================================================"
echo "THREE-DIMENSION OPTIMIZATIONS (Different Weight Configurations)"
echo "================================================================================"
echo ""

# Test 7: Full 3D - Default weights (0.5/0.3/0.2)
run_test "7_full_3d_default" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,host,pool --weight-osd 0.5 --weight-host 0.3 --weight-pool 0.2"

# Test 8: Full 3D - OSD-Focused (0.7/0.1/0.2)
run_test "8_full_3d_osd_focused" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,host,pool --weight-osd 0.7 --weight-host 0.1 --weight-pool 0.2"

# Test 9: Full 3D - OSD-Heavy (0.8/0.1/0.1)
run_test "9_full_3d_osd_heavy" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,host,pool --weight-osd 0.8 --weight-host 0.1 --weight-pool 0.1"

# Test 10: Full 3D - POOL-Focused (0.4/0.2/0.4)
run_test "10_full_3d_pool_focused" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,host,pool --weight-osd 0.4 --weight-host 0.2 --weight-pool 0.4"

# Test 11: Full 3D - Balanced (0.33/0.33/0.34)
run_test "11_full_3d_balanced" \
    "python tests/run_production_optimization.py --dry-run --optimization-levels osd,host,pool --weight-osd 0.33 --weight-host 0.33 --weight-pool 0.34"

echo "================================================================================"
echo "GENERATING COMPARISON SUMMARY"
echo "================================================================================"
echo ""

# Generate summary report
summary_file="$RESULTS_DIR/SUMMARY.md"

cat > "$summary_file" << EOF
# Optimization Strategy Comparison Summary

**Test Date:** $(date)  
**Cluster:** 840 OSDs, 30 hosts, 30 pools, 5,232 PGs

## Results Table

| Test | Strategy | Weights (OSD/Host/Pool) | Time (s) | Iterations | Swaps | OSD CV Before | OSD CV After | Reduction |
|------|----------|-------------------------|----------|------------|-------|---------------|--------------|-----------|
EOF

# Function to extract and format metrics for summary
add_summary_row() {
    local test_num="$1"
    local test_name="$2"
    local strategy="$3"
    local weights="$4"
    local file_prefix="$RESULTS_DIR/${test_num}_${test_name}"
    
    if [ -f "${file_prefix}.txt" ]; then
        local time=$(grep "real" "${file_prefix}_timing.txt" 2>/dev/null | awk '{print $2}' || echo "N/A")
        local iterations=$(grep -o "Iteration [0-9]*:" "${file_prefix}.txt" 2>/dev/null | tail -1 | grep -o "[0-9]*" || echo "0")
        local swaps=$(grep "Proposed swaps:" "${file_prefix}.txt" 2>/dev/null | grep -o "[0-9]*" || echo "0")
        local cv_line=$(grep "OSD CV Improvement:" "${file_prefix}.txt" 2>/dev/null || echo "")
        local cv_before=$(echo "$cv_line" | grep -oE "[0-9]+\.[0-9]+%" | head -1 || echo "N/A")
        local cv_after=$(echo "$cv_line" | grep -oE "[0-9]+\.[0-9]+%" | tail -1 || echo "N/A")
        
        # Calculate reduction if both values exist
        local reduction="N/A"
        if [ "$cv_before" != "N/A" ] && [ "$cv_after" != "N/A" ]; then
            local before_num=$(echo "$cv_before" | sed 's/%//')
            local after_num=$(echo "$cv_after" | sed 's/%//')
            reduction=$(echo "scale=1; ($before_num - $after_num) / $before_num * 100" | bc 2>/dev/null || echo "N/A")
            if [ "$reduction" != "N/A" ]; then
                reduction="${reduction}%"
            fi
        fi
        
        echo "| $test_num | $strategy | $weights | $time | $iterations | $swaps | $cv_before | $cv_after | $reduction |" >> "$summary_file"
    fi
}

# Add all test results
add_summary_row "1" "osd_only" "OSD-Only" "1.0/0/0"
add_summary_row "2" "host_only" "HOST-Only" "0/1.0/0"
add_summary_row "3" "pool_only" "POOL-Only" "0/0/1.0"
add_summary_row "4" "osd_host" "OSD+HOST" "0.5/0.5/0"
add_summary_row "5" "osd_pool" "OSD+POOL" "0.5/0/0.5"
add_summary_row "6" "host_pool" "HOST+POOL" "0/0.5/0.5"
add_summary_row "7" "full_3d_default" "Full 3D Default" "0.5/0.3/0.2"
add_summary_row "8" "full_3d_osd_focused" "Full 3D OSD-Focused" "0.7/0.1/0.2"
add_summary_row "9" "full_3d_osd_heavy" "Full 3D OSD-Heavy" "0.8/0.1/0.1"
add_summary_row "10" "full_3d_pool_focused" "Full 3D POOL-Focused" "0.4/0.2/0.4"
add_summary_row "11" "full_3d_balanced" "Full 3D Balanced" "0.33/0.33/0.34"

cat >> "$summary_file" << 'EOF'

## Key Findings

Review the table above to identify:

- **Fastest Strategies:** Look for lowest execution times
- **Best OSD CV Reduction:** Look for highest reduction percentages
- **Most Swap-Efficient:** Compare swaps/reduction ratio

## Test Commands Reference

```bash
# Single-dimension
1. OSD-Only:  --optimization-levels osd
2. HOST-Only: --optimization-levels host
3. POOL-Only: --optimization-levels pool

# Two-dimension
4. OSD+HOST: --optimization-levels osd,host
5. OSD+POOL: --optimization-levels osd,pool
6. HOST+POOL: --optimization-levels host,pool

# Three-dimension with different weights
7. Default:      --weight-osd 0.5 --weight-host 0.3 --weight-pool 0.2
8. OSD-Focused:  --weight-osd 0.7 --weight-host 0.1 --weight-pool 0.2
9. OSD-Heavy:    --weight-osd 0.8 --weight-host 0.1 --weight-pool 0.1
10. POOL-Focused: --weight-osd 0.4 --weight-host 0.2 --weight-pool 0.4
11. Balanced:     --weight-osd 0.33 --weight-host 0.33 --weight-pool 0.34
```

## Detailed Results

Individual test outputs are available in the following files:

EOF

for f in "$RESULTS_DIR"/*_*.txt; do
    if [ -f "$f" ]; then
        local basename=$(basename "$f")
        local filesize=$(du -h "$f" | cut -f1)
        echo "- $basename ($filesize)" >> "$summary_file"
    fi
done

echo ""
echo -e "${GREEN}Summary report generated: $summary_file${NC}"
echo ""
echo "================================================================================"
echo "ALL TESTS COMPLETED"
echo "================================================================================"
echo ""
echo "Results saved to: $RESULTS_DIR/"
echo ""
echo "To view the summary:"
echo "  cat $summary_file"
echo ""
echo "To view individual test results:"
echo "  ls -lh $RESULTS_DIR/"
echo ""
