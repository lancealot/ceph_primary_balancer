"""
Tests for base optimizer interface and registry.

Tests the OptimizerBase abstract class, OptimizerRegistry, and OptimizerStats
to ensure the Phase 7 architecture is working correctly.
"""

import unittest
from typing import List

from src.ceph_primary_balancer.optimizers.base import (
    OptimizerBase,
    OptimizerRegistry,
    OptimizerStats
)
from src.ceph_primary_balancer.models import ClusterState, SwapProposal
from src.ceph_primary_balancer.scorer import Scorer


class DummyOptimizer(OptimizerBase):
    """Dummy optimizer for testing base class functionality."""
    
    @property
    def algorithm_name(self) -> str:
        return "Dummy Test Optimizer"
    
    @property
    def is_deterministic(self) -> bool:
        return True
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """Simple dummy optimization that does nothing."""
        self._start_timer()
        self._record_iteration(state)
        self._stop_timer()
        return []


class NonDeterministicDummyOptimizer(OptimizerBase):
    """Non-deterministic dummy optimizer for testing."""
    
    @property
    def algorithm_name(self) -> str:
        return "Non-Deterministic Dummy"
    
    @property
    def is_deterministic(self) -> bool:
        return False
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        return []


class TestOptimizerStats(unittest.TestCase):
    """Test OptimizerStats dataclass."""
    
    def test_stats_initialization(self):
        """Test OptimizerStats initializes with correct defaults."""
        stats = OptimizerStats()
        
        self.assertEqual(stats.iterations, 0)
        self.assertEqual(stats.swaps_evaluated, 0)
        self.assertEqual(stats.swaps_applied, 0)
        self.assertEqual(stats.score_trajectory, [])
        self.assertEqual(stats.cv_trajectory, [])
        self.assertEqual(stats.execution_time, 0.0)
        self.assertEqual(stats.algorithm_specific, {})
    
    def test_stats_to_dict(self):
        """Test OptimizerStats conversion to dictionary."""
        stats = OptimizerStats(
            iterations=100,
            swaps_evaluated=500,
            swaps_applied=95,
            execution_time=2.5
        )
        
        result = stats.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['iterations'], 100)
        self.assertEqual(result['swaps_evaluated'], 500)
        self.assertEqual(result['swaps_applied'], 95)
        self.assertEqual(result['execution_time'], 2.5)


class TestOptimizerBase(unittest.TestCase):
    """Test OptimizerBase abstract class."""
    
    def test_cannot_instantiate_abstract_base(self):
        """Test that OptimizerBase cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            OptimizerBase()
    
    def test_dummy_optimizer_instantiation(self):
        """Test that concrete implementation can be instantiated."""
        optimizer = DummyOptimizer()
        
        self.assertIsNotNone(optimizer)
        self.assertEqual(optimizer.target_cv, 0.10)
        self.assertEqual(optimizer.max_iterations, 1000)
        self.assertIsInstance(optimizer.stats, OptimizerStats)
    
    def test_optimizer_with_custom_parameters(self):
        """Test optimizer initialization with custom parameters."""
        optimizer = DummyOptimizer(
            target_cv=0.05,
            max_iterations=500,
            verbose=True
        )
        
        self.assertEqual(optimizer.target_cv, 0.05)
        self.assertEqual(optimizer.max_iterations, 500)
        self.assertTrue(optimizer.verbose)
    
    def test_optimizer_creates_default_scorer(self):
        """Test that optimizer creates default scorer if none provided."""
        optimizer = DummyOptimizer()
        
        self.assertIsNotNone(optimizer.scorer)
        self.assertIsInstance(optimizer.scorer, Scorer)
        self.assertEqual(optimizer.scorer.w_osd, 0.5)
        self.assertEqual(optimizer.scorer.w_host, 0.3)
        self.assertEqual(optimizer.scorer.w_pool, 0.2)
    
    def test_optimizer_accepts_custom_scorer(self):
        """Test that optimizer accepts custom scorer."""
        custom_scorer = Scorer(w_osd=0.7, w_host=0.2, w_pool=0.1)
        optimizer = DummyOptimizer(scorer=custom_scorer)
        
        self.assertIs(optimizer.scorer, custom_scorer)
        self.assertEqual(optimizer.scorer.w_osd, 0.7)
    
    def test_optimizer_with_enabled_levels(self):
        """Test optimizer with enabled_levels parameter."""
        optimizer = DummyOptimizer(enabled_levels=['osd', 'host'])
        
        # Should create scorer with adjusted weights
        self.assertIsNotNone(optimizer.scorer)
        self.assertEqual(optimizer.scorer.w_osd, 0.5)
        self.assertEqual(optimizer.scorer.w_host, 0.5)
        self.assertEqual(optimizer.scorer.w_pool, 0.0)
    
    def test_optimizer_with_dynamic_weights(self):
        """Test optimizer with dynamic weights enabled."""
        optimizer = DummyOptimizer(
            dynamic_weights=True,
            dynamic_strategy='target_distance'
        )
        
        # Should create DynamicScorer
        from src.ceph_primary_balancer.dynamic_scorer import DynamicScorer
        self.assertIsInstance(optimizer.scorer, DynamicScorer)
    
    def test_algorithm_name_property(self):
        """Test algorithm_name property."""
        optimizer = DummyOptimizer()
        self.assertEqual(optimizer.algorithm_name, "Dummy Test Optimizer")
    
    def test_is_deterministic_property(self):
        """Test is_deterministic property."""
        det_optimizer = DummyOptimizer()
        non_det_optimizer = NonDeterministicDummyOptimizer()
        
        self.assertTrue(det_optimizer.is_deterministic)
        self.assertFalse(non_det_optimizer.is_deterministic)
    
    def test_get_stats(self):
        """Test get_stats method returns dictionary."""
        optimizer = DummyOptimizer()
        stats = optimizer.get_stats()
        
        self.assertIsInstance(stats, dict)
        self.assertIn('iterations', stats)
        self.assertIn('swaps_evaluated', stats)
        self.assertIn('swaps_applied', stats)


class TestOptimizerRegistry(unittest.TestCase):
    """Test OptimizerRegistry."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Clear registry before each test
        OptimizerRegistry._algorithms.clear()
    
    def tearDown(self):
        """Clean up after tests."""
        # Clear registry after each test
        OptimizerRegistry._algorithms.clear()
    
    def test_register_optimizer(self):
        """Test registering an optimizer."""
        OptimizerRegistry.register('dummy', DummyOptimizer)
        
        self.assertIn('dummy', OptimizerRegistry._algorithms)
        self.assertEqual(OptimizerRegistry._algorithms['dummy'], DummyOptimizer)
    
    def test_register_non_optimizer_raises_error(self):
        """Test that registering non-optimizer class raises error."""
        class NotAnOptimizer:
            pass
        
        with self.assertRaises(TypeError):
            OptimizerRegistry.register('bad', NotAnOptimizer)
    
    def test_get_optimizer(self):
        """Test getting optimizer instance from registry."""
        OptimizerRegistry.register('dummy', DummyOptimizer)
        
        optimizer = OptimizerRegistry.get_optimizer('dummy', target_cv=0.08)
        
        self.assertIsInstance(optimizer, DummyOptimizer)
        self.assertEqual(optimizer.target_cv, 0.08)
    
    def test_get_unknown_optimizer_raises_error(self):
        """Test that getting unknown optimizer raises error."""
        with self.assertRaises(ValueError) as context:
            OptimizerRegistry.get_optimizer('unknown')
        
        self.assertIn('Unknown algorithm', str(context.exception))
        self.assertIn('unknown', str(context.exception))
    
    def test_list_algorithms(self):
        """Test listing registered algorithms."""
        OptimizerRegistry.register('dummy1', DummyOptimizer)
        OptimizerRegistry.register('dummy2', NonDeterministicDummyOptimizer)
        
        algorithms = OptimizerRegistry.list_algorithms()
        
        self.assertIsInstance(algorithms, list)
        self.assertEqual(len(algorithms), 2)
        self.assertIn('dummy1', algorithms)
        self.assertIn('dummy2', algorithms)
        # Should be sorted
        self.assertEqual(algorithms, sorted(algorithms))
    
    def test_list_algorithms_empty(self):
        """Test listing algorithms when registry is empty."""
        algorithms = OptimizerRegistry.list_algorithms()
        
        self.assertIsInstance(algorithms, list)
        self.assertEqual(len(algorithms), 0)
    
    def test_get_algorithm_info(self):
        """Test getting algorithm information."""
        OptimizerRegistry.register('dummy', DummyOptimizer)
        
        info = OptimizerRegistry.get_algorithm_info('dummy')
        
        self.assertIsInstance(info, dict)
        self.assertEqual(info['name'], 'dummy')
        self.assertEqual(info['class'], 'DummyOptimizer')
        self.assertEqual(info['algorithm_name'], 'Dummy Test Optimizer')
        self.assertTrue(info['is_deterministic'])
    
    def test_get_algorithm_info_unknown_raises_error(self):
        """Test that getting info for unknown algorithm raises error."""
        with self.assertRaises(ValueError):
            OptimizerRegistry.get_algorithm_info('unknown')
    
    def test_registry_is_class_level(self):
        """Test that registry is shared at class level."""
        OptimizerRegistry.register('dummy', DummyOptimizer)
        
        # Should be accessible from different calls
        self.assertIn('dummy', OptimizerRegistry._algorithms)
        self.assertEqual(len(OptimizerRegistry.list_algorithms()), 1)


class TestOptimizerBaseHelpers(unittest.TestCase):
    """Test helper methods in OptimizerBase."""
    
    def setUp(self):
        """Set up test fixtures."""
        from src.ceph_primary_balancer.models import OSDInfo, PGInfo
        
        # Create simple test state
        # Note: primary is a property that returns acting[0], not an init parameter
        self.state = ClusterState(
            pgs={
                '1.0': PGInfo(pgid='1.0', pool_id=1, acting=[0, 1, 2]),
                '1.1': PGInfo(pgid='1.1', pool_id=1, acting=[1, 2, 3]),
            },
            osds={
                0: OSDInfo(osd_id=0, host='host1', primary_count=1, total_pg_count=1),
                1: OSDInfo(osd_id=1, host='host1', primary_count=1, total_pg_count=2),
                2: OSDInfo(osd_id=2, host='host2', primary_count=0, total_pg_count=2),
                3: OSDInfo(osd_id=3, host='host2', primary_count=0, total_pg_count=1),
            },
            hosts={},
            pools={}
        )
    
    def test_start_stop_timer(self):
        """Test timer methods."""
        optimizer = DummyOptimizer()
        
        optimizer._start_timer()
        import time
        time.sleep(0.01)  # Small delay
        optimizer._stop_timer()
        
        self.assertGreater(optimizer.stats.execution_time, 0)
        self.assertLess(optimizer.stats.execution_time, 1.0)  # Should be very short
    
    def test_record_iteration(self):
        """Test iteration recording."""
        optimizer = DummyOptimizer()
        
        optimizer._record_iteration(self.state)
        
        self.assertEqual(optimizer.stats.iterations, 1)
        self.assertEqual(len(optimizer.stats.score_trajectory), 1)
        self.assertEqual(len(optimizer.stats.cv_trajectory), 1)
        self.assertGreater(optimizer.stats.score_trajectory[0], 0)
    
    def test_check_termination_max_iterations(self):
        """Test termination check for max iterations."""
        optimizer = DummyOptimizer(max_iterations=10)
        
        # Should not terminate at iteration 5
        self.assertFalse(optimizer._check_termination(self.state, 5))
        
        # Should terminate at iteration 10
        self.assertTrue(optimizer._check_termination(self.state, 10))
    
    def test_check_termination_target_cv(self):
        """Test termination check for target CV."""
        from src.ceph_primary_balancer.models import OSDInfo, PGInfo
        
        # Create perfectly balanced state
        balanced_state = ClusterState(
            pgs={
                '1.0': PGInfo(pgid='1.0', pool_id=1, acting=[0, 1]),
                '1.1': PGInfo(pgid='1.1', pool_id=1, acting=[1, 0]),
            },
            osds={
                0: OSDInfo(osd_id=0, host='host1', primary_count=1, total_pg_count=2),
                1: OSDInfo(osd_id=1, host='host1', primary_count=1, total_pg_count=2),
            },
            hosts={},
            pools={}
        )
        
        optimizer = DummyOptimizer(target_cv=0.10)
        
        # Perfectly balanced state should terminate
        self.assertTrue(optimizer._check_termination(balanced_state, 0))


if __name__ == '__main__':
    unittest.main()
