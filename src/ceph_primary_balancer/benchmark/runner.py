"""
Benchmark orchestration and execution.

This module provides the main benchmark runner that orchestrates
execution of performance, quality, scalability, and stability tests.
"""

import json
import copy
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

from .generator import generate_synthetic_cluster, generate_ec_pool, generate_multi_pool_scenario
from .profiler import (
    profile_optimization,
    benchmark_scalability,
    PerformanceMetrics,
    MemoryMetrics,
    ScalabilityMetrics
)
from .quality_analyzer import (
    analyze_balance_quality,
    analyze_convergence,
    BalanceQualityMetrics,
    ConvergenceMetrics,
    StabilityMetrics
)
from .scenarios import (
    PERFORMANCE_SCENARIOS,
    QUALITY_SCENARIOS,
    PRODUCTION_SCENARIOS,
    SCALABILITY_SCENARIOS,
    STABILITY_SCENARIOS,
    get_scenario_by_name
)
from ..scorer import Scorer


@dataclass
class BenchmarkResults:
    """Complete benchmark results."""
    performance: Dict[str, Tuple[PerformanceMetrics, MemoryMetrics]]
    quality: Dict[str, Dict[str, Any]]
    scalability: List[ScalabilityMetrics]
    stability: Dict[str, StabilityMetrics]
    metadata: Dict[str, Any]


@dataclass
class Regression:
    """Detected performance regression."""
    metric_name: str
    baseline_value: float
    current_value: float
    change_pct: float
    threshold_pct: float
    severity: str  # 'minor', 'moderate', 'severe'


class BenchmarkSuite:
    """Main benchmark orchestration."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize benchmark suite.
        
        Args:
            config: Configuration dict (None = use defaults)
        """
        self.config = config or self._default_config()
        self.results: Optional[BenchmarkResults] = None
    
    def _default_config(self) -> Dict:
        """Get default configuration."""
        return {
            'target_cv': 0.10,
            'seed': 42,
            'output_dir': './benchmark_results',
            'save_datasets': False,
            'performance_scenarios': ['small_quick', 'medium_standard'],
            'quality_scenarios': ['replicated_3_moderate', 'multi_pool_complex'],
            'run_scalability': True,
            'run_stability': False,  # Slower, disabled by default
            'stability_runs': 10,
            'max_iterations': 1000  # Reasonable limit for benchmarking
        }
    
    def run_all_benchmarks(self) -> BenchmarkResults:
        """
        Run complete benchmark suite.
        
        Returns:
            BenchmarkResults with all test results
        """
        print("=" * 60)
        print("BENCHMARK SUITE EXECUTION")
        print("=" * 60)
        
        results = {
            'performance': {},
            'quality': {},
            'scalability': [],
            'stability': {},
            'metadata': {
                'config': self.config,
                'version': '1.1.0-dev'
            }
        }
        
        # Run performance benchmarks
        print("\n[1/4] Running performance benchmarks...")
        results['performance'] = self.run_performance_benchmarks()
        
        # Run quality benchmarks
        print("\n[2/4] Running quality benchmarks...")
        results['quality'] = self.run_quality_benchmarks()
        
        # Run scalability benchmarks
        if self.config.get('run_scalability', True):
            print("\n[3/4] Running scalability benchmarks...")
            results['scalability'] = self.run_scalability_benchmarks()
        else:
            print("\n[3/4] Skipping scalability benchmarks (disabled)")
        
        # Run stability benchmarks
        if self.config.get('run_stability', False):
            print("\n[4/4] Running stability benchmarks...")
            results['stability'] = self.run_stability_benchmarks()
        else:
            print("\n[4/4] Skipping stability benchmarks (disabled)")
        
        print("\n" + "=" * 60)
        print("BENCHMARK SUITE COMPLETE")
        print("=" * 60)
        
        self.results = BenchmarkResults(**results)
        return self.results
    
    def run_performance_benchmarks(self) -> Dict[str, Tuple[PerformanceMetrics, MemoryMetrics]]:
        """
        Run performance benchmarks on standard scenarios.
        
        Returns:
            Dict mapping scenario name to (PerformanceMetrics, MemoryMetrics)
        """
        results = {}
        scenario_names = self.config.get('performance_scenarios', ['small_quick'])
        
        for idx, scenario_name in enumerate(scenario_names, 1):
            try:
                print(f"  [{idx}/{len(scenario_names)}] Running: {scenario_name}...", end=' ', flush=True)
                scenario = get_scenario_by_name(scenario_name)
                
                # Generate cluster
                params = scenario.get('params', {})
                num_osds = params.get('num_osds', 10)
                if 'pools_config' in params:
                    num_pgs = sum(p.get('pgs', 512) for p in params['pools_config'])
                else:
                    num_pgs = params.get('pgs_per_pool', 100) * params.get('num_pools', 1)
                print(f"({num_osds} OSDs, {num_pgs} PGs)...", end=' ', flush=True)

                state = self._generate_cluster_from_scenario(scenario)

                # Profile optimization
                perf, mem = profile_optimization(
                    state=state,
                    target_cv=self.config.get('target_cv', 0.10),
                    max_iterations=self.config.get('max_iterations', 1000)
                )
                
                results[scenario_name] = (perf, mem)
                print(f"✓ ({perf.execution_time_total:.2f}s, {mem.peak_memory_mb:.1f}MB)")
                
            except Exception as e:
                print(f"✗ Error: {e}")
                continue
        
        return results
    
    def run_quality_benchmarks(self) -> Dict[str, Dict[str, Any]]:
        """
        Run quality benchmarks across different cluster types.
        
        Returns:
            Dict mapping scenario name to quality metrics
        """
        results = {}
        scenario_names = self.config.get('quality_scenarios', ['replicated_3_moderate'])
        
        for idx, scenario_name in enumerate(scenario_names, 1):
            try:
                print(f"  [{idx}/{len(scenario_names)}] Running: {scenario_name}...", end=' ', flush=True)
                scenario = get_scenario_by_name(scenario_name)
                
                # Generate cluster
                params = scenario.get('params', {})
                num_osds = params.get('num_osds', 10)
                if 'pools_config' in params:
                    num_pgs = sum(p.get('pgs', 512) for p in params['pools_config'])
                else:
                    num_pgs = params.get('pgs_per_pool', 100) * params.get('num_pools', 1)
                print(f"({num_osds} OSDs, {num_pgs} PGs)...", end=' ', flush=True)

                original_state = self._generate_cluster_from_scenario(scenario)
                optimized_state = copy.deepcopy(original_state)
                
                # Create scorer
                scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
                
                # Optimize
                from ..optimizers.greedy import GreedyOptimizer
                swaps = GreedyOptimizer(
                    target_cv=self.config.get('target_cv', 0.10),
                    max_iterations=self.config.get('max_iterations', 1000),
                    scorer=scorer,
                ).optimize(optimized_state)
                
                # Analyze quality
                quality = analyze_balance_quality(original_state, optimized_state, swaps)
                convergence = analyze_convergence(
                    original_state,
                    target_cv=self.config.get('target_cv', 0.10),
                    scorer=scorer,
                    max_iterations=self.config.get('max_iterations', 1000)
                )
                
                results[scenario_name] = {
                    'quality': asdict(quality),
                    'convergence': asdict(convergence)
                }
                
                print(f"✓ (CV: {quality.osd_cv_before:.1%} → {quality.osd_cv_after:.1%})")
                
            except Exception as e:
                print(f"✗ Error: {e}")
                continue
        
        return results
    
    def run_scalability_benchmarks(self) -> List[ScalabilityMetrics]:
        """
        Test performance across different scales.
        
        Returns:
            List of ScalabilityMetrics
        """
        print("  - Running scalability tests...")
        
        results = benchmark_scalability(
            target_cv=self.config.get('target_cv', 0.10),
            seed=self.config.get('seed', 42),
            max_iterations=self.config.get('max_iterations', 1000)
        )
        
        for metric in results:
            print(f"    Scale {metric.scale_factor}: "
                  f"{metric.num_osds} OSDs, {metric.num_pgs} PGs → "
                  f"{metric.execution_time:.2f}s, "
                  f"{metric.peak_memory_mb:.1f} MB")
        
        return results
    
    def _generate_cluster_from_scenario(self, scenario: Dict) -> Any:
        """
        Generate cluster state from scenario definition.
        
        Args:
            scenario: Scenario dict
            
        Returns:
            ClusterState
        """
        params = scenario.get('params', scenario)
        seed = self.config.get('seed', 42)

        # Check scenario type
        scenario_type = scenario.get('type', params.get('type', ''))

        if scenario_type == 'multi_pool' or 'pools_config' in params:
            # Mixed pool scenario with per-pool configurations
            return generate_multi_pool_scenario(
                num_pools=len(params['pools_config']),
                pools_config=params['pools_config'],
                num_osds=params.get('num_osds', 100),
                num_hosts=params.get('num_hosts', 10),
                seed=seed
            )
        elif scenario_type == 'ec' or 'k' in params:
            return generate_ec_pool(
                k=params.get('k', 8),
                m=params.get('m', 3),
                num_pgs=params.get('num_pgs', 2048),
                num_osds=params.get('num_osds', 100),
                num_hosts=params.get('num_hosts', 10),
                imbalance_type=params.get('imbalance_type', 'random'),
                imbalance_cv=params.get('imbalance_cv', 0.30),
                seed=seed
            )
        else:
            return generate_synthetic_cluster(
                num_osds=params.get('num_osds', 100),
                num_hosts=params.get('num_hosts', 10),
                num_pools=params.get('num_pools', 5),
                pgs_per_pool=params.get('pgs_per_pool', 1024),
                replication_factor=params.get('replication_factor', 3),
                imbalance_cv=params.get('imbalance_cv', 0.30),
                imbalance_pattern=params.get('imbalance_pattern', 'random'),
                seed=seed
            )
    
    def save_results(self, filepath: str):
        """
        Save benchmark results to JSON file.
        
        Args:
            filepath: Output file path
        """
        if self.results is None:
            raise ValueError("No results to save. Run benchmarks first.")
        
        # Convert dataclasses to dicts
        data = {
            'performance': {
                name: {
                    'perf': asdict(perf),
                    'mem': asdict(mem)
                }
                for name, (perf, mem) in self.results.performance.items()
            },
            'quality': self.results.quality,
            'scalability': [asdict(m) for m in self.results.scalability],
            'stability': {
                name: asdict(metrics)
                for name, metrics in self.results.stability.items()
            },
            'metadata': self.results.metadata
        }
        
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nResults saved to: {filepath}")


class RegressionDetector:
    """Detect performance regressions."""
    
    def __init__(self, threshold: float = 0.10):
        """
        Initialize regression detector.
        
        Args:
            threshold: Regression threshold (0.10 = 10% degradation)
        """
        self.threshold = threshold
    
    def detect_regressions(
        self,
        baseline_path: str,
        current_results: BenchmarkResults
    ) -> List[Regression]:
        """
        Detect performance regressions.
        
        Args:
            baseline_path: Path to baseline results JSON
            current_results: Current benchmark results
            
        Returns:
            List of detected regressions
        """
        # Load baseline
        with open(baseline_path, 'r') as f:
            baseline = json.load(f)
        
        regressions = []
        
        # Check performance metrics
        for scenario_name, (perf, mem) in current_results.performance.items():
            if scenario_name in baseline.get('performance', {}):
                baseline_perf = baseline['performance'][scenario_name]['perf']
                
                # Check execution time regression
                time_change = ((perf.execution_time_total - baseline_perf['execution_time_total']) 
                              / baseline_perf['execution_time_total'])
                
                if time_change > self.threshold:
                    severity = self._classify_severity(time_change)
                    regressions.append(Regression(
                        metric_name=f"{scenario_name}/execution_time",
                        baseline_value=baseline_perf['execution_time_total'],
                        current_value=perf.execution_time_total,
                        change_pct=time_change * 100,
                        threshold_pct=self.threshold * 100,
                        severity=severity
                    ))
                
                # Check memory regression
                baseline_mem = baseline['performance'][scenario_name]['mem']
                mem_change = ((mem.peak_memory_mb - baseline_mem['peak_memory_mb']) 
                             / baseline_mem['peak_memory_mb'])
                
                if mem_change > self.threshold:
                    severity = self._classify_severity(mem_change)
                    regressions.append(Regression(
                        metric_name=f"{scenario_name}/peak_memory",
                        baseline_value=baseline_mem['peak_memory_mb'],
                        current_value=mem.peak_memory_mb,
                        change_pct=mem_change * 100,
                        threshold_pct=self.threshold * 100,
                        severity=severity
                    ))
        
        return regressions
    
    def _classify_severity(self, change_ratio: float) -> str:
        """
        Classify regression severity.
        
        Args:
            change_ratio: Ratio of change (e.g., 0.15 = 15% worse)
            
        Returns:
            Severity: 'minor', 'moderate', or 'severe'
        """
        if change_ratio < 0.20:
            return 'minor'
        elif change_ratio < 0.50:
            return 'moderate'
        else:
            return 'severe'
    
    def generate_report(self, regressions: List[Regression]) -> str:
        """
        Generate human-readable regression report.
        
        Args:
            regressions: List of detected regressions
            
        Returns:
            Formatted report string
        """
        if not regressions:
            return "✓ No performance regressions detected.\n"
        
        report = []
        report.append("⚠ PERFORMANCE REGRESSIONS DETECTED")
        report.append("=" * 60)
        report.append(f"Found {len(regressions)} regression(s):\n")
        
        for reg in sorted(regressions, key=lambda r: r.change_pct, reverse=True):
            severity_icon = {
                'minor': '⚠',
                'moderate': '⚠⚠',
                'severe': '🔴'
            }.get(reg.severity, '⚠')
            
            report.append(f"{severity_icon} {reg.metric_name}")
            report.append(f"  Baseline: {reg.baseline_value:.3f}")
            report.append(f"  Current:  {reg.current_value:.3f}")
            report.append(f"  Change:   {reg.change_pct:+.1f}% (threshold: {reg.threshold_pct:.1f}%)")
            report.append(f"  Severity: {reg.severity.upper()}")
            report.append("")
        
        return "\n".join(report)
