"""
Unit tests for benchmark profiler module.

Tests cover:
- Performance metrics calculation
- Memory metrics tracking
- Scalability benchmarking
- Profile optimization functionality
"""

import unittest
from src.ceph_primary_balancer.benchmark.profiler import (
    profile_optimization,
    benchmark_scalability,
    estimate_complexity,
    quick_benchmark,
    PerformanceMetrics,
    MemoryMetrics,
    ScalabilityMetrics
)
from src.ceph_primary_balancer.benchmark.generator import generate_synthetic_cluster
from src.ceph_primary_balancer.scorer import Scorer


class TestPerformanceMetrics(unittest.TestCase):
    """Test PerformanceMetrics dataclass."""
    
    def test_metrics_creation(self):
        """Test creating PerformanceMetrics instance."""
        metrics = PerformanceMetrics(
            execution_time_total=1.5,
            execution_time_optimize=1.2,
            execution_time_scoring=0.3,
            iterations_count=10,
            swaps_evaluated=1000,
            swaps_applied=50,
            swaps_per_second=33.3,
            iterations_per_second=6.67,
            time_per_iteration=150.0
        )
        
        self.assertEqual(metrics.execution_time_total, 1.5)
        self.assertEqual(metrics.iterations_count, 10)
        self.assertEqual(metrics.swaps_applied, 50)
        self.assertAlmostEqual(metrics.swaps_per_second, 33.3, places=1)
    
    def test_throughput_calculation(self):
        """Test throughput metrics are reasonable."""
        metrics = PerformanceMetrics(
            execution_time_total=2.0,
            execution_time_optimize=1.8,
            execution_time_scoring=0.2,
            iterations_count=20,
            swaps_evaluated=2000,
            swaps_applied=100,
            swaps_per_second=50.0,  # 100 swaps / 2.0 seconds
            iterations_per_second=10.0,  # 20 iterations / 2.0 seconds
            time_per_iteration=100.0  # 2000ms / 20 iterations
        )
        
        # Verify calculations
        calculated_swaps_per_sec = metrics.swaps_applied / metrics.execution_time_total
        self.assertAlmostEqual(calculated_swaps_per_sec, metrics.swaps_per_second, places=1)
        
        calculated_iter_per_sec = metrics.iterations_count / metrics.execution_time_total
        self.assertAlmostEqual(calculated_iter_per_sec, metrics.iterations_per_second, places=1)


class TestMemoryMetrics(unittest.TestCase):
    """Test MemoryMetrics dataclass."""
    
    def test_memory_metrics_creation(self):
        """Test creating MemoryMetrics instance."""
        metrics = MemoryMetrics(
            peak_memory_mb=150.5,
            memory_per_pg_kb=1.5,
            memory_per_osd_kb=15.0,
            state_size_mb=10.0,
            memory_start_mb=100.0,
            memory_end_mb=120.0,
            memory_delta_mb=20.0
        )
        
        self.assertEqual(metrics.peak_memory_mb, 150.5)
        self.assertEqual(metrics.memory_delta_mb, 20.0)
    
    def test_memory_delta_calculation(self):
        """Test memory delta equals end - start."""
        metrics = MemoryMetrics(
            peak_memory_mb=150.0,
            memory_per_pg_kb=1.0,
            memory_per_osd_kb=10.0,
            state_size_mb=5.0,
            memory_start_mb=100.0,
            memory_end_mb=125.0,
            memory_delta_mb=25.0
        )
        
        calculated_delta = metrics.memory_end_mb - metrics.memory_start_mb
        self.assertEqual(calculated_delta, metrics.memory_delta_mb)
    
    def test_efficiency_metrics(self):
        """Test per-PG and per-OSD efficiency calculations."""
        # If we have 1000 PGs and use 100 MB, that's 100 KB per PG
        metrics = MemoryMetrics(
            peak_memory_mb=100.0,
            memory_per_pg_kb=102.4,  # 100 MB / 1000 PGs ≈ 102.4 KB
            memory_per_osd_kb=1024.0,  # 100 MB / 100 OSDs = 1024 KB
            state_size_mb=80.0,
            memory_start_mb=50.0,
            memory_end_mb=70.0,
            memory_delta_mb=20.0
        )
        
        self.assertGreater(metrics.memory_per_osd_kb, 0)
        self.assertGreater(metrics.memory_per_pg_kb, 0)


class TestProfileOptimization(unittest.TestCase):
    """Test profile_optimization function."""
    
    def test_profile_small_cluster(self):
        """Test profiling a small cluster."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            imbalance_cv=0.30,
            seed=42
        )
        
        perf, mem = profile_optimization(
            state=state,
            target_cv=0.10,
            max_iterations=100
        )
        
        self.assertIsInstance(perf, PerformanceMetrics)
        self.assertIsInstance(mem, MemoryMetrics)
    
    def test_profile_returns_both_metrics(self):
        """Test that profile returns both performance and memory metrics."""
        state = generate_synthetic_cluster(
            num_osds=5,
            num_hosts=1,
            num_pools=1,
            pgs_per_pool=20,
            replication_factor=3,
            imbalance_cv=0.25,
            seed=42
        )
        
        result = profile_optimization(state)
        
        self.assertEqual(len(result), 2, "Should return tuple of (perf, mem)")
        perf, mem = result
        self.assertIsInstance(perf, PerformanceMetrics)
        self.assertIsInstance(mem, MemoryMetrics)
    
    def test_execution_time_recorded(self):
        """Test that execution time is recorded and positive."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            imbalance_cv=0.30,
            seed=42
        )
        
        perf, mem = profile_optimization(state, target_cv=0.10)
        
        self.assertGreater(perf.execution_time_total, 0,
                          "Execution time should be positive")
        self.assertGreater(perf.execution_time_optimize, 0,
                          "Optimization time should be positive")
    
    def test_iterations_counted(self):
        """Test that iterations are counted."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            imbalance_cv=0.30,
            seed=42
        )
        
        perf, mem = profile_optimization(state, target_cv=0.10, max_iterations=50)
        
        self.assertGreater(perf.iterations_count, 0, "Should have iterations")
        self.assertLessEqual(perf.iterations_count, 50, 
                            "Should not exceed max_iterations")
    
    def test_memory_tracking(self):
        """Test that memory is tracked."""
        state = generate_synthetic_cluster(
            num_osds=10,
            num_hosts=2,
            num_pools=1,
            pgs_per_pool=50,
            replication_factor=3,
            imbalance_cv=0.30,
            seed=42
        )
        
        perf, mem = profile_optimization(state)
        
        self.assertGreater(mem.peak_memory_mb, 0, "Peak memory should be positive")
        self.assertGreaterEqual(mem.peak_memory_mb, mem.memory_start_mb,
                               "Peak should be >= start")
        self.assertGreaterEqual(mem.peak_memory_mb, mem.memory_end_mb,
                               "Peak should be >= end")


class TestScalabilityBenchmark(unittest.TestCase):
    """Test scalability benchmarking."""
    
    def test_scalability_multiple_scales(self):
        """Test running scalability tests at multiple scales."""
        results = benchmark_scalability(
            scales=[(10, 50), (20, 100)],
            target_cv=0.10,
            imbalance_cv=0.30,
            seed=42
        )
        
        self.assertEqual(len(results), 2, "Should have results for 2 scales")
        for result in results:
            self.assertIsInstance(result, ScalabilityMetrics)
    
    def test_scalability_results_ordered(self):
        """Test that results match input scale order."""
        scales = [(5, 25), (10, 50), (20, 100)]
        results = benchmark_scalability(
            scales=scales,
            target_cv=0.10,
            imbalance_cv=0.30,
            seed=42
        )
        
        self.assertEqual(len(results), len(scales))
        # Verify OSDs and PGs match
        for i, result in enumerate(results):
            self.assertEqual(result.num_osds, scales[i][0])
            self.assertEqual(result.num_pgs, scales[i][1])
    
    def test_scalability_increasing_resources(self):
        """Test that larger scales have more resources."""
        results = benchmark_scalability(
            scales=[(10, 50), (20, 100)],
            target_cv=0.10,
            imbalance_cv=0.30,
            seed=42
        )
        
        # Second scale should have 2x resources
        self.assertEqual(results[1].num_osds, results[0].num_osds * 2)
        self.assertEqual(results[1].num_pgs, results[0].num_pgs * 2)
    
    def test_complexity_estimation(self):
        """Test complexity estimation from scalability results."""
        results = benchmark_scalability(
            scales=[(5, 25), (10, 50), (20, 100)],
            target_cv=0.10,
            imbalance_cv=0.30,
            seed=42
        )
        
        complexity = estimate_complexity(results)
        
        # Should return a dict with complexity analysis
        self.assertIsInstance(complexity, dict)
        self.assertIn('time_complexity', complexity)
        self.assertIn('O(', complexity['time_complexity'],
                     "Time complexity should be in Big-O notation")


class TestQuickBenchmark(unittest.TestCase):
    """Test quick_benchmark convenience function."""
    
    def test_quick_benchmark_execution(self):
        """Test quick benchmark runs successfully."""
        perf, mem = quick_benchmark(
            num_osds=10,
            num_pgs=50,
            imbalance_cv=0.30
        )
        
        self.assertIsInstance(perf, PerformanceMetrics)
        self.assertIsInstance(mem, MemoryMetrics)
        self.assertGreater(perf.execution_time_total, 0)
    
    def test_quick_benchmark_with_custom_params(self):
        """Test quick benchmark with custom parameters."""
        perf, mem = quick_benchmark(
            num_osds=20,
            num_pgs=100,
            imbalance_cv=0.40
        )
        
        self.assertIsInstance(perf, PerformanceMetrics)
        self.assertIsInstance(mem, MemoryMetrics)


class TestScalabilityMetrics(unittest.TestCase):
    """Test ScalabilityMetrics dataclass."""
    
    def test_scalability_metrics_creation(self):
        """Test creating ScalabilityMetrics instance."""
        metrics = ScalabilityMetrics(
            scale_factor=2,
            num_osds=20,
            num_pgs=100,
            execution_time=1.5,
            peak_memory_mb=50.0,
            pgs_per_second=66.7,
            osds_per_second=13.3
        )
        
        self.assertEqual(metrics.scale_factor, 2)
        self.assertEqual(metrics.num_osds, 20)
        self.assertEqual(metrics.num_pgs, 100)
        self.assertAlmostEqual(metrics.execution_time, 1.5, places=1)
    
    def test_throughput_metrics(self):
        """Test throughput metrics calculation."""
        metrics = ScalabilityMetrics(
            scale_factor=1,
            num_osds=10,
            num_pgs=100,
            execution_time=2.0,
            peak_memory_mb=30.0,
            pgs_per_second=50.0,  # 100 PGs / 2.0 sec
            osds_per_second=5.0   # 10 OSDs / 2.0 sec
        )
        
        # Verify calculations
        calculated_pgs_per_sec = metrics.num_pgs / metrics.execution_time
        self.assertAlmostEqual(calculated_pgs_per_sec, metrics.pgs_per_second, places=1)
        
        calculated_osds_per_sec = metrics.num_osds / metrics.execution_time
        self.assertAlmostEqual(calculated_osds_per_sec, metrics.osds_per_second, places=1)


if __name__ == '__main__':
    unittest.main()
