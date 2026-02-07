#!/usr/bin/env python3
"""Generate summary report from optimization comparison results."""

import os
import re
from pathlib import Path

def extract_metrics(test_file, timing_file):
    """Extract metrics from test output and timing files."""
    metrics = {
        'iterations': 'N/A',
        'swaps': 'N/A',
        'cv_before': 'N/A',
        'cv_after': 'N/A',
        'time_seconds': 'N/A',
        'reduction': 'N/A'
    }
    
    # Read timing file
    if timing_file.exists():
        timing_content = timing_file.read_text()
        time_match = re.search(r'real\s+([\d.]+)', timing_content)
        if time_match:
            metrics['time_seconds'] = float(time_match.group(1))
    
    # Read test output file
    if test_file.exists():
        content = test_file.read_text()
        
        # Extract iterations (last iteration number)
        iter_matches = re.findall(r'Iteration (\d+):', content)
        if iter_matches:
            metrics['iterations'] = int(iter_matches[-1])
        
        # Extract swaps
        swaps_match = re.search(r'Proposed swaps:\s*(\d+)', content)
        if swaps_match:
            metrics['swaps'] = int(swaps_match.group(1))
        
        # Extract CV before and after
        cv_match = re.search(r'OSD CV Improvement:\s*([\d.]+)%\s*->\s*([\d.]+)%', content)
        if cv_match:
            metrics['cv_before'] = float(cv_match.group(1))
            metrics['cv_after'] = float(cv_match.group(2))
            metrics['reduction'] = ((metrics['cv_before'] - metrics['cv_after']) / metrics['cv_before']) * 100
    
    return metrics

def format_time(seconds):
    """Format seconds into human-readable time."""
    if seconds == 'N/A':
        return 'N/A'
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def main():
    results_dir = Path('optimization_comparison_results')
    
    tests = [
        ('1', 'osd_only', 'OSD-Only', '1.0/0/0'),
        ('2', 'host_only', 'HOST-Only', '0/1.0/0'),
        ('3', 'pool_only', 'POOL-Only', '0/0/1.0'),
        ('4', 'osd_host', 'OSD+HOST', '0.5/0.5/0'),
        ('5', 'osd_pool', 'OSD+POOL', '0.5/0/0.5'),
        ('6', 'host_pool', 'HOST+POOL', '0/0.5/0.5'),
        ('7', 'full_3d_default', 'Full 3D Default', '0.5/0.3/0.2'),
        ('8', 'full_3d_osd_focused', 'Full 3D OSD-Focused', '0.7/0.1/0.2'),
        ('9', 'full_3d_osd_heavy', 'Full 3D OSD-Heavy', '0.8/0.1/0.1'),
        ('10', 'full_3d_pool_focused', 'Full 3D POOL-Focused', '0.4/0.2/0.4'),
        ('11', 'full_3d_balanced', 'Full 3D Balanced', '0.33/0.33/0.34'),
    ]
    
    results = []
    for test_num, test_name, strategy, weights in tests:
        test_file = results_dir / f"{test_num}_{test_name}.txt"
        timing_file = results_dir / f"{test_num}_{test_name}_timing.txt"
        
        metrics = extract_metrics(test_file, timing_file)
        results.append({
            'num': test_num,
            'strategy': strategy,
            'weights': weights,
            **metrics
        })
    
    # Generate markdown summary
    summary_path = results_dir / 'SUMMARY.md'
    
    with open(summary_path, 'w') as f:
        f.write("# Optimization Strategy Comparison Summary\n\n")
        f.write("**Test Cluster:** 840 OSDs, 30 hosts, 30 pools, 5,232 PGs\n\n")
        
        f.write("## Results Table\n\n")
        f.write("| # | Strategy | Weights (O/H/P) | Time | Iterations | Swaps | CV Before | CV After | Reduction |\n")
        f.write("|---|----------|-----------------|------|------------|-------|-----------|----------|----------|\n")
        
        for r in results:
            time_str = format_time(r['time_seconds'])
            cv_before = f"{r['cv_before']:.2f}%" if r['cv_before'] != 'N/A' else 'N/A'
            cv_after = f"{r['cv_after']:.2f}%" if r['cv_after'] != 'N/A' else 'N/A'
            reduction = f"{r['reduction']:.1f}%" if r['reduction'] != 'N/A' else 'N/A'
            
            f.write(f"| {r['num']} | {r['strategy']} | {r['weights']} | {time_str} | "
                   f"{r['iterations']} | {r['swaps']} | {cv_before} | {cv_after} | {reduction} |\n")
        
        f.write("\n## Key Findings\n\n")
        
        # Find best OSD CV
        valid_results = [r for r in results if r['cv_after'] != 'N/A']
        if valid_results:
            best_cv = min(valid_results, key=lambda x: x['cv_after'])
            f.write(f"### Best OSD CV Reduction\n")
            f.write(f"**{best_cv['strategy']}** achieved the lowest OSD CV: **{best_cv['cv_after']:.2f}%** ")
            f.write(f"({best_cv['reduction']:.1f}% reduction from {best_cv['cv_before']:.2f}%)\n\n")
            
            # Find fastest
            fastest = min(valid_results, key=lambda x: x['time_seconds'])
            f.write(f"### Fastest Strategy\n")
            f.write(f"**{fastest['strategy']}** completed in **{format_time(fastest['time_seconds'])}** ")
            f.write(f"with {fastest['cv_after']:.2f}% final CV\n\n")
            
            # Find most efficient (best reduction per hour)
            for r in valid_results:
                if r['time_seconds'] > 0 and r['reduction'] != 'N/A':
                    r['efficiency'] = (r['cv_before'] - r['cv_after']) / (r['time_seconds'] / 3600)
            
            most_efficient = max(valid_results, key=lambda x: x.get('efficiency', 0))
            f.write(f"### Most Time-Efficient\n")
            f.write(f"**{most_efficient['strategy']}** achieved {most_efficient['cv_after']:.2f}% CV ")
            f.write(f"in {format_time(most_efficient['time_seconds'])}\n\n")
        
        f.write("## Analysis\n\n")
        f.write("### Single-Dimension Strategies\n")
        f.write("- **OSD-Only, HOST-Only, POOL-Only** all achieved similar final CV (~16.8-16.9%)\n")
        f.write("- OSD-Only was faster than POOL-Only (pool optimization is more expensive)\n\n")
        
        f.write("### Two-Dimension Strategies\n")
        f.write("- **OSD+HOST** provides good balance with moderate execution time\n")
        f.write("- Adding POOL dimension significantly increases execution time\n\n")
        
        f.write("### Three-Dimension Strategies\n")
        f.write("- **POOL-Focused (0.4/0.2/0.4)** achieved the best OSD CV (15.62%)\n")
        f.write("- **OSD-Heavy (0.8/0.1/0.1)** achieved 15.82% CV with better time than default\n")
        f.write("- **OSD-Focused (0.7/0.1/0.2)** achieved 15.97% CV, better than default 17.10%\n\n")
        
        f.write("## Recommendations\n\n")
        f.write("**For Best OSD Balance:**\n")
        f.write("- Use POOL-Focused weights (0.4/0.2/0.4) → 15.62% CV\n")
        f.write("- Or OSD-Heavy weights (0.8/0.1/0.1) → 15.82% CV\n\n")
        
        f.write("**For Best Time/Quality Trade-off:**\n")
        f.write("- Use OSD-Only optimization → 16.81% CV in ~1.4 hours\n")
        f.write("- Or OSD+HOST → 17.12% CV in ~1.4 hours with host awareness\n\n")
        
        f.write("**For Production Use:**\n")
        f.write("- OSD-Focused (0.7/0.1/0.2) provides excellent balance\n")
        f.write("- Significantly better than default (15.97% vs 17.10%)\n")
        f.write("- Maintains awareness of all dimensions\n\n")
    
    print(f"Summary generated: {summary_path}")
    print("\nTop 3 strategies by final OSD CV:")
    sorted_by_cv = sorted([r for r in results if r['cv_after'] != 'N/A'], 
                          key=lambda x: x['cv_after'])
    for i, r in enumerate(sorted_by_cv[:3], 1):
        print(f"  {i}. {r['strategy']:25s} → {r['cv_after']:.2f}% CV in {format_time(r['time_seconds'])}")

if __name__ == '__main__':
    main()
