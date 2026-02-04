"""
Benchmark results reporting in multiple formats.

This module provides formatted output of benchmark results in
terminal, JSON, and HTML formats.
"""

import json
from typing import Dict, List, Any, Tuple
from pathlib import Path
from dataclasses import asdict

from .profiler import PerformanceMetrics, MemoryMetrics, ScalabilityMetrics
from .quality_analyzer import BalanceQualityMetrics, ConvergenceMetrics, StabilityMetrics
from .runner import BenchmarkResults


class TerminalReporter:
    """Generate terminal-based reports."""
    
    @staticmethod
    def generate_summary(results: BenchmarkResults) -> str:
        """
        Generate concise terminal summary.
        
        Args:
            results: BenchmarkResults to summarize
            
        Returns:
            Formatted summary string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("BENCHMARK RESULTS SUMMARY")
        lines.append("=" * 70)
        
        # Performance summary
        if results.performance:
            lines.append("\n📊 PERFORMANCE BENCHMARKS")
            lines.append("-" * 70)
            for name, (perf, mem) in results.performance.items():
                lines.append(f"  {name}:")
                lines.append(f"    Time:   {perf.execution_time_total:.3f}s")
                lines.append(f"    Memory: {mem.peak_memory_mb:.1f} MB")
                lines.append(f"    Swaps:  {perf.swaps_applied} ({perf.swaps_per_second:.1f}/s)")
        
        # Quality summary
        if results.quality:
            lines.append("\n✨ QUALITY BENCHMARKS")
            lines.append("-" * 70)
            for name, metrics in results.quality.items():
                quality = metrics['quality']
                lines.append(f"  {name}:")
                lines.append(f"    OSD CV:  {quality['osd_cv_before']:.1%} → {quality['osd_cv_after']:.1%} "
                           f"({quality['osd_cv_improvement_pct']:+.1f}%)")
                lines.append(f"    Score:   {quality['balance_score']:.1f}/100")
                lines.append(f"    Swaps:   {quality['num_swaps']}")
        
        # Scalability summary
        if results.scalability:
            lines.append("\n📈 SCALABILITY BENCHMARKS")
            lines.append("-" * 70)
            lines.append(f"  {'Scale':<8} {'OSDs':<8} {'PGs':<10} {'Time (s)':<12} {'Memory (MB)':<12}")
            lines.append("  " + "-" * 66)
            for metric in results.scalability:
                lines.append(f"  {metric.scale_factor:<8} {metric.num_osds:<8} "
                           f"{metric.num_pgs:<10} {metric.execution_time:<12.3f} "
                           f"{metric.peak_memory_mb:<12.1f}")
        
        # Stability summary
        if results.stability:
            lines.append("\n🔒 STABILITY BENCHMARKS")
            lines.append("-" * 70)
            for name, metrics in results.stability.items():
                lines.append(f"  {name}:")
                lines.append(f"    Runs:        {metrics.runs_count}")
                lines.append(f"    Mean CV Imp: {metrics.cv_improvement_mean:.1f}% ± {metrics.cv_improvement_std:.1f}%")
                lines.append(f"    Determinism: {metrics.determinism_score:.1f}/100")
        
        lines.append("\n" + "=" * 70)
        
        return "\n".join(lines)
    
    @staticmethod
    def generate_detailed_report(results: BenchmarkResults) -> str:
        """
        Generate detailed terminal report with tables.
        
        Args:
            results: BenchmarkResults to report
            
        Returns:
            Formatted detailed report string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("DETAILED BENCHMARK REPORT")
        lines.append("=" * 80)
        
        # Performance details
        if results.performance:
            lines.append("\n" + "=" * 80)
            lines.append("PERFORMANCE BENCHMARKS")
            lines.append("=" * 80)
            
            for name, (perf, mem) in results.performance.items():
                lines.append(f"\n{name}")
                lines.append("-" * 80)
                lines.append("Timing:")
                lines.append(f"  Total execution:     {perf.execution_time_total:.3f}s")
                lines.append(f"  Optimization:        {perf.execution_time_optimize:.3f}s")
                lines.append(f"  Scoring (estimated): {perf.execution_time_scoring:.3f}s")
                lines.append("\nThroughput:")
                lines.append(f"  Iterations:          {perf.iterations_count}")
                lines.append(f"  Iterations/sec:      {perf.iterations_per_second:.1f}")
                lines.append(f"  Time/iteration:      {perf.time_per_iteration:.2f}ms")
                lines.append(f"  Swaps evaluated:     {perf.swaps_evaluated}")
                lines.append(f"  Swaps applied:       {perf.swaps_applied}")
                lines.append(f"  Swaps/sec:           {perf.swaps_per_second:.1f}")
                lines.append("\nMemory:")
                lines.append(f"  Peak:                {mem.peak_memory_mb:.2f} MB")
                lines.append(f"  Start:               {mem.memory_start_mb:.2f} MB")
                lines.append(f"  End:                 {mem.memory_end_mb:.2f} MB")
                lines.append(f"  Delta:               {mem.memory_delta_mb:+.2f} MB")
                lines.append(f"  Per PG:              {mem.memory_per_pg_kb:.2f} KB")
                lines.append(f"  Per OSD:             {mem.memory_per_osd_kb:.2f} KB")
                lines.append(f"  State size:          {mem.state_size_mb:.2f} MB")
        
        # Quality details
        if results.quality:
            lines.append("\n" + "=" * 80)
            lines.append("QUALITY BENCHMARKS")
            lines.append("=" * 80)
            
            for name, metrics in results.quality.items():
                quality = metrics['quality']
                convergence = metrics['convergence']
                
                lines.append(f"\n{name}")
                lines.append("-" * 80)
                lines.append("Balance Quality:")
                lines.append(f"  OSD-level:")
                lines.append(f"    CV before:         {quality['osd_cv_before']:.4f} ({quality['osd_cv_before']*100:.2f}%)")
                lines.append(f"    CV after:          {quality['osd_cv_after']:.4f} ({quality['osd_cv_after']*100:.2f}%)")
                lines.append(f"    Improvement:       {quality['osd_cv_improvement_pct']:+.2f}%")
                lines.append(f"    Variance reduction:{quality['osd_variance_reduction_pct']:+.2f}%")
                lines.append(f"    Range reduction:   {quality['osd_range_reduction']} primaries")
                
                lines.append(f"  Host-level:")
                lines.append(f"    CV before:         {quality['host_cv_before']:.4f}")
                lines.append(f"    CV after:          {quality['host_cv_after']:.4f}")
                lines.append(f"    Improvement:       {quality['host_cv_improvement_pct']:+.2f}%")
                
                lines.append(f"  Pool-level:")
                lines.append(f"    Avg CV before:     {quality['avg_pool_cv_before']:.4f}")
                lines.append(f"    Avg CV after:      {quality['avg_pool_cv_after']:.4f}")
                lines.append(f"    Improvement:       {quality['pool_cv_improvement_pct']:+.2f}%")
                
                lines.append(f"  Overall:")
                lines.append(f"    Composite improvement: {quality['composite_improvement']:.2f}%")
                lines.append(f"    Fairness index:        {quality['fairness_index']:.4f}")
                lines.append(f"    Balance score:         {quality['balance_score']:.1f}/100")
                lines.append(f"    Swaps applied:         {quality['num_swaps']}")
                lines.append(f"    Swaps per OSD:         {quality['swaps_per_osd']:.2f}")
                
                lines.append("\nConvergence:")
                lines.append(f"  Initial CV:        {convergence['initial_cv']:.4f}")
                lines.append(f"  Final CV:          {convergence['final_cv']:.4f}")
                lines.append(f"  Total improvement: {convergence['total_improvement_pct']:.2f}%")
                lines.append(f"  Iterations:        {convergence['iterations_total']}")
                lines.append(f"  To target:         {convergence['iterations_to_target']}")
                lines.append(f"  Convergence rate:  {convergence['convergence_rate']:.6f} CV/iteration")
                lines.append(f"  Pattern:           {convergence['convergence_pattern']}")
                lines.append(f"  Efficiency:        {convergence['convergence_efficiency']:.4f}% improvement/iteration")
        
        # Scalability details
        if results.scalability:
            lines.append("\n" + "=" * 80)
            lines.append("SCALABILITY BENCHMARKS")
            lines.append("=" * 80)
            lines.append(f"\n{'Scale':<8} {'OSDs':<8} {'PGs':<10} {'Time (s)':<12} "
                        f"{'Memory (MB)':<14} {'PGs/s':<12} {'OSDs/s':<10}")
            lines.append("-" * 80)
            
            for metric in results.scalability:
                lines.append(f"{metric.scale_factor:<8} {metric.num_osds:<8} "
                           f"{metric.num_pgs:<10} {metric.execution_time:<12.3f} "
                           f"{metric.peak_memory_mb:<14.1f} {metric.pgs_per_second:<12.1f} "
                           f"{metric.osds_per_second:<10.1f}")
            
            # Complexity analysis
            if len(results.scalability) >= 3:
                from .profiler import estimate_complexity
                complexity = estimate_complexity(results.scalability)
                lines.append("\nComplexity Analysis:")
                lines.append(f"  Time complexity:   {complexity['time_complexity']}")
                lines.append(f"  Memory complexity: {complexity['memory_complexity']}")
                if 'scale_ratio' in complexity:
                    lines.append(f"  Scale ratio:       {complexity['scale_ratio']:.2f}x")
                    lines.append(f"  Time ratio:        {complexity['time_ratio']:.2f}x")
                    lines.append(f"  Memory ratio:      {complexity['memory_ratio']:.2f}x")
        
        # Stability details
        if results.stability:
            lines.append("\n" + "=" * 80)
            lines.append("STABILITY BENCHMARKS")
            lines.append("=" * 80)
            
            for name, metrics in results.stability.items():
                lines.append(f"\n{name}")
                lines.append("-" * 80)
                lines.append(f"  Runs:                    {metrics.runs_count}")
                lines.append(f"  Mean CV improvement:     {metrics.cv_improvement_mean:.2f}%")
                lines.append(f"  Std dev CV improvement:  {metrics.cv_improvement_std:.2f}%")
                lines.append(f"  Mean swap count:         {metrics.swaps_count_mean:.1f}")
                lines.append(f"  Std dev swap count:      {metrics.swaps_count_std:.1f}")
                lines.append(f"  Determinism score:       {metrics.determinism_score:.1f}/100")
                
                # Interpretation
                if metrics.determinism_score >= 95:
                    interpretation = "Excellent (highly deterministic)"
                elif metrics.determinism_score >= 80:
                    interpretation = "Good (mostly deterministic)"
                elif metrics.determinism_score >= 60:
                    interpretation = "Fair (moderate variability)"
                else:
                    interpretation = "Poor (high variability)"
                lines.append(f"  Interpretation:          {interpretation}")
        
        lines.append("\n" + "=" * 80)
        
        return "\n".join(lines)


class JSONReporter:
    """Export results as structured JSON."""
    
    @staticmethod
    def export_results(
        results: BenchmarkResults,
        filepath: str
    ):
        """
        Export complete results as JSON.
        
        Args:
            results: BenchmarkResults to export
            filepath: Output file path
        """
        # Convert dataclasses to dicts
        data = {
            'performance': {
                name: {
                    'perf': asdict(perf),
                    'mem': asdict(mem)
                }
                for name, (perf, mem) in results.performance.items()
            },
            'quality': results.quality,
            'scalability': [asdict(m) for m in results.scalability],
            'stability': {
                name: asdict(metrics)
                for name, metrics in results.stability.items()
            },
            'metadata': results.metadata
        }
        
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def export_comparison(
        comparison: Dict[str, Any],
        filepath: str
    ):
        """
        Export comparison results as JSON.
        
        Args:
            comparison: Comparison data
            filepath: Output file path
        """
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(comparison, f, indent=2)


class SimpleHTMLReporter:
    """Generate simple HTML reports (no external dependencies)."""
    
    @staticmethod
    def generate_dashboard(
        results: BenchmarkResults,
        output_path: str
    ):
        """
        Generate simple HTML dashboard.
        
        Args:
            results: BenchmarkResults to visualize
            output_path: Output HTML file path
        """
        html = []
        html.append("<!DOCTYPE html>")
        html.append("<html>")
        html.append("<head>")
        html.append("  <meta charset='utf-8'>")
        html.append("  <title>Benchmark Results Dashboard</title>")
        html.append("  <style>")
        html.append("    body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }")
        html.append("    .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; }")
        html.append("    h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }")
        html.append("    h2 { color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px; }")
        html.append("    .metric-card { background: #f9f9f9; border-left: 4px solid #007bff; padding: 15px; margin: 10px 0; }")
        html.append("    .metric-card h3 { margin-top: 0; color: #007bff; }")
        html.append("    table { border-collapse: collapse; width: 100%; margin: 15px 0; }")
        html.append("    th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }")
        html.append("    th { background: #007bff; color: white; }")
        html.append("    tr:nth-child(even) { background: #f9f9f9; }")
        html.append("    .good { color: #28a745; font-weight: bold; }")
        html.append("    .warn { color: #ffc107; font-weight: bold; }")
        html.append("    .bad { color: #dc3545; font-weight: bold; }")
        html.append("  </style>")
        html.append("</head>")
        html.append("<body>")
        html.append("  <div class='container'>")
        html.append("    <h1>📊 Benchmark Results Dashboard</h1>")
        
        # Performance section
        if results.performance:
            html.append("    <h2>Performance Benchmarks</h2>")
            html.append("    <table>")
            html.append("      <tr><th>Scenario</th><th>Time (s)</th><th>Memory (MB)</th><th>Swaps</th><th>Throughput</th></tr>")
            
            for name, (perf, mem) in results.performance.items():
                html.append(f"      <tr>")
                html.append(f"        <td>{name}</td>")
                html.append(f"        <td>{perf.execution_time_total:.3f}</td>")
                html.append(f"        <td>{mem.peak_memory_mb:.1f}</td>")
                html.append(f"        <td>{perf.swaps_applied}</td>")
                html.append(f"        <td>{perf.swaps_per_second:.1f}/s</td>")
                html.append(f"      </tr>")
            
            html.append("    </table>")
        
        # Quality section
        if results.quality:
            html.append("    <h2>Quality Benchmarks</h2>")
            
            for name, metrics in results.quality.items():
                quality = metrics['quality']
                html.append(f"    <div class='metric-card'>")
                html.append(f"      <h3>{name}</h3>")
                html.append(f"      <p><strong>OSD CV:</strong> {quality['osd_cv_before']*100:.2f}% → "
                          f"{quality['osd_cv_after']*100:.2f}% "
                          f"(<span class='good'>{quality['osd_cv_improvement_pct']:+.1f}%</span>)</p>")
                html.append(f"      <p><strong>Balance Score:</strong> {quality['balance_score']:.1f}/100</p>")
                html.append(f"      <p><strong>Swaps Applied:</strong> {quality['num_swaps']}</p>")
                html.append(f"    </div>")
        
        # Scalability section
        if results.scalability:
            html.append("    <h2>Scalability Benchmarks</h2>")
            html.append("    <table>")
            html.append("      <tr><th>Scale</th><th>OSDs</th><th>PGs</th><th>Time (s)</th><th>Memory (MB)</th></tr>")
            
            for metric in results.scalability:
                html.append(f"      <tr>")
                html.append(f"        <td>{metric.scale_factor}</td>")
                html.append(f"        <td>{metric.num_osds}</td>")
                html.append(f"        <td>{metric.num_pgs}</td>")
                html.append(f"        <td>{metric.execution_time:.3f}</td>")
                html.append(f"        <td>{metric.peak_memory_mb:.1f}</td>")
                html.append(f"      </tr>")
            
            html.append("    </table>")
        
        html.append("  </div>")
        html.append("</body>")
        html.append("</html>")
        
        # Write to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            f.write("\n".join(html))
