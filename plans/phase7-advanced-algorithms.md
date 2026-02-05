# Phase 6: Advanced Optimization Algorithms Implementation Plan
## Ceph Primary PG Balancer v1.2.0

**Date:** 2026-02-04  
**Prerequisites:** Phase 5 Complete (v1.1.0)  
**Target Version:** 1.2.0  
**Status:** Planning  

---

## Executive Summary

Phase 6 introduces advanced optimization algorithms to provide users with options beyond the current greedy algorithm. These algorithms offer different trade-offs between speed, quality, and determinism, allowing users to choose the best approach for their specific cluster needs.

### Key Objectives

1. **Simulated Annealing** - For users requiring absolute optimal balance
2. **Batch Greedy** - For faster convergence without sacrificing determinism
3. **Tabu Search** - For better-than-greedy balance while maintaining predictability
4. **Algorithm Comparison Framework** - Built on Phase 5 benchmarking infrastructure

### Why These Algorithms?

| User Scenario | Recommended Algorithm | Benefit |
|---------------|----------------------|---------|
| Critical cluster, best balance needed | Simulated Annealing | 2-5% better CV, global optimum |
| Large cluster, time-constrained | Batch Greedy | 20-40% faster convergence |
| Important cluster, predictable results | Tabu Search | 10-15% better balance, deterministic |
| Standard production cluster | Greedy (existing) | Fast, proven, good enough |

---

## Algorithm Comparison Matrix

| Algorithm | Speed | Quality | Deterministic | Complexity | Use Case |
|-----------|-------|---------|---------------|------------|----------|
| **Greedy (v1.0)** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Yes | Low | Default, proven |
| **Batch Greedy (NEW)** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Yes | Low | Faster greedy |
| **Tabu Search (NEW)** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ Yes | Medium | Better balance |
| **Simulated Annealing (NEW)** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ No | Medium | Best balance |

---

## Architecture Overview

### Module Structure

```
src/ceph_primary_balancer/
├── optimizer.py                    # Existing greedy algorithm
├── optimizers/                     # NEW: Algorithm package
│   ├── __init__.py                 # Algorithm registry
│   ├── base.py                     # Base optimizer interface (~150 lines)
│   ├── greedy.py                   # Refactored greedy (~250 lines)
│   ├── batch_greedy.py             # Batch greedy implementation (~300 lines)
│   ├── tabu_search.py              # Tabu search implementation (~350 lines)
│   ├── simulated_annealing.py      # Simulated annealing (~350 lines)
│   └── hybrid.py                   # Hybrid algorithms (~200 lines)
└── cli.py                          # Enhanced with --algorithm flag

tests/optimizers/
├── test_base.py                    # Base interface tests (~100 lines)
├── test_batch_greedy.py            # Batch greedy tests (~150 lines)
├── test_tabu_search.py             # Tabu search tests (~150 lines)
├── test_simulated_annealing.py     # SA tests (~150 lines)
├── test_algorithm_comparison.py    # Comparison tests (~200 lines)
└── test_integration.py             # End-to-end tests (~150 lines)

docs/
├── algorithms/                     # NEW: Algorithm documentation
│   ├── README.md                   # Algorithm overview
│   ├── batch-greedy.md            # Batch greedy guide
│   ├── tabu-search.md             # Tabu search guide
│   ├── simulated-annealing.md     # SA guide
│   └── comparison.md              # Algorithm comparison guide
```

### Total Effort Estimate

- **Production Code:** ~1,600 lines
- **Test Code:** ~900 lines
- **Documentation:** ~500 lines
- **Total:** ~3,000 lines

---

## Component Details

### 1. Base Optimizer Interface (`base.py`)

**Purpose:** Provide common interface for all optimization algorithms

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..models import ClusterState, SwapProposal
from ..scorer import Scorer

class OptimizerBase(ABC):
    """
    Base class for all optimization algorithms.
    
    All optimizers must implement the optimize() method and return
    a list of SwapProposal objects representing the optimization path.
    """
    
    def __init__(
        self,
        target_cv: float = 0.10,
        max_iterations: int = 1000,
        scorer: Optional[Scorer] = None,
        verbose: bool = False,
        **kwargs
    ):
        """
        Initialize optimizer with common parameters.
        
        Args:
            target_cv: Target coefficient of variation
            max_iterations: Maximum optimization iterations
            scorer: Scorer instance for multi-dimensional scoring
            verbose: Enable progress output
            **kwargs: Algorithm-specific parameters
        """
        self.target_cv = target_cv
        self.max_iterations = max_iterations
        self.scorer = scorer or Scorer(w_osd=0.5, w_host=0.3, w_pool=0.2)
        self.verbose = verbose
        self.stats = OptimizerStats()
    
    @abstractmethod
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """
        Optimize the cluster state and return list of swaps.
        
        Args:
            state: ClusterState to optimize (modified in place)
            
        Returns:
            List of SwapProposal objects applied during optimization
        """
        pass
    
    @property
    @abstractmethod
    def algorithm_name(self) -> str:
        """Return human-readable algorithm name."""
        pass
    
    @property
    @abstractmethod
    def is_deterministic(self) -> bool:
        """Return True if algorithm produces deterministic results."""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Return optimization statistics."""
        return self.stats.to_dict()
    
    def _check_termination(self, state: ClusterState, iteration: int) -> bool:
        """Check if optimization should terminate."""
        # Common termination logic
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = calculate_statistics(primary_counts)
        
        if stats.cv <= self.target_cv:
            return True
        if iteration >= self.max_iterations:
            return True
        
        return False

@dataclass
class OptimizerStats:
    """Statistics collected during optimization."""
    iterations: int = 0
    swaps_evaluated: int = 0
    swaps_applied: int = 0
    score_trajectory: List[float] = field(default_factory=list)
    cv_trajectory: List[float] = field(default_factory=list)
    execution_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class OptimizerRegistry:
    """Registry for available optimization algorithms."""
    
    _algorithms: Dict[str, type] = {}
    
    @classmethod
    def register(cls, name: str):
        """Decorator to register an optimizer."""
        def decorator(optimizer_class):
            cls._algorithms[name] = optimizer_class
            return optimizer_class
        return decorator
    
    @classmethod
    def get_optimizer(cls, name: str, **kwargs) -> OptimizerBase:
        """Get optimizer instance by name."""
        if name not in cls._algorithms:
            raise ValueError(f"Unknown algorithm: {name}. Available: {list(cls._algorithms.keys())}")
        return cls._algorithms[name](**kwargs)
    
    @classmethod
    def list_algorithms(cls) -> List[str]:
        """List all registered algorithms."""
        return list(cls._algorithms.keys())
```

---

### 2. Batch Greedy Optimizer (`batch_greedy.py`)

**Purpose:** Apply multiple non-conflicting swaps per iteration for faster convergence

**Algorithm Overview:**

```
1. Identify donors and receivers
2. Find top N beneficial swaps (e.g., N=10)
3. Detect conflicts:
   - Same PG in multiple swaps
   - Same OSD as donor/receiver in multiple swaps
4. Apply all non-conflicting swaps simultaneously
5. Repeat until target achieved
```

**Implementation:**

```python
from typing import List, Set, Tuple
from .base import OptimizerBase, OptimizerRegistry
from ..models import ClusterState, SwapProposal

@OptimizerRegistry.register('batch_greedy')
class BatchGreedyOptimizer(OptimizerBase):
    """
    Batch Greedy Optimizer - applies multiple non-conflicting swaps per iteration.
    
    Benefits:
    - 20-40% faster convergence than standard greedy
    - Still deterministic
    - Low implementation complexity
    
    Trade-offs:
    - Slightly more complex conflict detection
    - May miss some swap synergies
    """
    
    def __init__(
        self,
        batch_size: int = 10,
        conflict_detection: str = 'strict',
        **kwargs
    ):
        """
        Initialize Batch Greedy optimizer.
        
        Args:
            batch_size: Number of top swaps to consider per iteration
            conflict_detection: 'strict' or 'relaxed'
                strict: No PG or OSD can appear in multiple swaps
                relaxed: Allow same OSD if different PGs
            **kwargs: Base optimizer parameters
        """
        super().__init__(**kwargs)
        self.batch_size = batch_size
        self.conflict_detection = conflict_detection
    
    @property
    def algorithm_name(self) -> str:
        return f"Batch Greedy (batch_size={self.batch_size})"
    
    @property
    def is_deterministic(self) -> bool:
        return True
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """Run batch greedy optimization."""
        swaps_applied = []
        
        for iteration in range(self.max_iterations):
            if self._check_termination(state, iteration):
                break
            
            # Find top N beneficial swaps
            candidates = self._find_top_swaps(state, self.batch_size)
            
            if not candidates:
                break
            
            # Select non-conflicting subset
            batch = self._select_non_conflicting_batch(candidates)
            
            if not batch:
                break
            
            # Apply all swaps in batch
            for swap in batch:
                self._apply_swap(state, swap)
                swaps_applied.append(swap)
                self.stats.swaps_applied += 1
            
            self.stats.iterations += 1
            
            if self.verbose and iteration % 10 == 0:
                self._print_progress(state, iteration, len(swaps_applied))
        
        return swaps_applied
    
    def _find_top_swaps(
        self,
        state: ClusterState,
        count: int
    ) -> List[SwapProposal]:
        """
        Find top N beneficial swaps.
        
        Similar to standard greedy but collects multiple candidates
        instead of just the best one.
        """
        from ..analyzer import identify_donors, identify_receivers
        
        donors = identify_donors(state.osds)
        receivers = identify_receivers(state.osds)
        
        if not donors or not receivers:
            return []
        
        current_score = self.scorer.calculate_score(state)
        candidates = []
        
        # Evaluate all possible swaps
        for pg in state.pgs.values():
            if pg.primary not in donors:
                continue
            
            for candidate_osd in pg.acting[1:]:
                if candidate_osd not in receivers:
                    continue
                
                # Simulate swap
                new_score = self._simulate_swap_score(state, pg.pgid, candidate_osd)
                improvement = current_score - new_score
                
                if improvement > 0:
                    swap = SwapProposal(
                        pgid=pg.pgid,
                        old_primary=pg.primary,
                        new_primary=candidate_osd,
                        score_improvement=improvement
                    )
                    candidates.append(swap)
                    self.stats.swaps_evaluated += 1
        
        # Sort by improvement and return top N
        candidates.sort(key=lambda s: s.score_improvement, reverse=True)
        return candidates[:count]
    
    def _select_non_conflicting_batch(
        self,
        candidates: List[SwapProposal]
    ) -> List[SwapProposal]:
        """
        Select maximum non-conflicting subset from candidates.
        
        Uses greedy approach: start with best swap, add next best
        that doesn't conflict, repeat.
        """
        if not candidates:
            return []
        
        batch = [candidates[0]]
        used_pgs = {candidates[0].pgid}
        used_osds = {candidates[0].old_primary, candidates[0].new_primary}
        
        for swap in candidates[1:]:
            # Check for conflicts
            if self.conflict_detection == 'strict':
                # No PG or OSD overlap allowed
                if swap.pgid in used_pgs:
                    continue
                if swap.old_primary in used_osds or swap.new_primary in used_osds:
                    continue
            else:  # relaxed
                # Only PG overlap forbidden
                if swap.pgid in used_pgs:
                    continue
            
            # No conflict, add to batch
            batch.append(swap)
            used_pgs.add(swap.pgid)
            used_osds.add(swap.old_primary)
            used_osds.add(swap.new_primary)
        
        return batch
    
    def _simulate_swap_score(
        self,
        state: ClusterState,
        pgid: str,
        new_primary: int
    ) -> float:
        """Simulate swap and return resulting score."""
        from ..optimizer import simulate_swap_score
        return simulate_swap_score(state, pgid, new_primary, self.scorer)
    
    def _apply_swap(self, state: ClusterState, swap: SwapProposal):
        """Apply swap to state."""
        from ..optimizer import apply_swap
        apply_swap(state, swap)
    
    def _print_progress(self, state: ClusterState, iteration: int, total_swaps: int):
        """Print progress message."""
        from ..analyzer import calculate_statistics
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = calculate_statistics(primary_counts)
        print(f"Iteration {iteration}: CV = {stats.cv:.2%}, Total swaps = {total_swaps}")
```

**Configuration Examples:**

```python
# Fast mode - larger batches
optimizer = BatchGreedyOptimizer(batch_size=20, conflict_detection='relaxed')

# Conservative mode - smaller batches, strict conflict detection
optimizer = BatchGreedyOptimizer(batch_size=5, conflict_detection='strict')

# Default mode
optimizer = BatchGreedyOptimizer(batch_size=10, conflict_detection='strict')
```

---

### 3. Tabu Search Optimizer (`tabu_search.py`)

**Purpose:** Escape local optima using memory of recent moves

**Algorithm Overview:**

```
1. Start with greedy selection
2. Maintain "tabu list" of recently moved PGs
3. When selecting next swap:
   - Prefer non-tabu swaps
   - Allow tabu swaps only if they're significantly better (aspiration criteria)
4. Update tabu list (remove old, add new)
5. Repeat until target achieved
```

**Implementation:**

```python
from collections import deque
from typing import List, Optional, Set
from .base import OptimizerBase, OptimizerRegistry
from ..models import ClusterState, SwapProposal

@OptimizerRegistry.register('tabu_search')
class TabuSearchOptimizer(OptimizerBase):
    """
    Tabu Search Optimizer - escapes local optima using memory.
    
    Benefits:
    - 10-15% better balance than standard greedy
    - Still deterministic
    - Moderate complexity
    
    Trade-offs:
    - 1.5-3x slower than greedy
    - Requires tuning (tabu tenure)
    - Memory overhead for tabu list
    """
    
    def __init__(
        self,
        tabu_tenure: int = 50,
        aspiration_threshold: float = 0.1,
        diversification_enabled: bool = True,
        **kwargs
    ):
        """
        Initialize Tabu Search optimizer.
        
        Args:
            tabu_tenure: How many iterations a move stays tabu
            aspiration_threshold: Allow tabu moves if improvement > threshold
            diversification_enabled: Restart search if stuck
            **kwargs: Base optimizer parameters
        """
        super().__init__(**kwargs)
        self.tabu_tenure = tabu_tenure
        self.aspiration_threshold = aspiration_threshold
        self.diversification_enabled = diversification_enabled
        
        # Tabu list: recently moved PGs
        self.tabu_list: deque = deque(maxlen=tabu_tenure)
        
        # Best solution tracking
        self.best_score: float = float('inf')
        self.best_state: Optional[ClusterState] = None
        self.iterations_without_improvement = 0
    
    @property
    def algorithm_name(self) -> str:
        return f"Tabu Search (tenure={self.tabu_tenure})"
    
    @property
    def is_deterministic(self) -> bool:
        return True
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """Run tabu search optimization."""
        import copy
        
        swaps_applied = []
        self.best_score = self.scorer.calculate_score(state)
        self.best_state = copy.deepcopy(state)
        
        for iteration in range(self.max_iterations):
            if self._check_termination(state, iteration):
                break
            
            # Find best non-tabu swap (or aspiring tabu swap)
            swap = self._find_best_swap_with_tabu(state)
            
            if swap is None:
                if self.diversification_enabled and self.iterations_without_improvement > 100:
                    # Diversification: restart from best known solution
                    state = copy.deepcopy(self.best_state)
                    self.tabu_list.clear()
                    self.iterations_without_improvement = 0
                    continue
                else:
                    break
            
            # Apply swap
            self._apply_swap(state, swap)
            swaps_applied.append(swap)
            
            # Add to tabu list
            self.tabu_list.append(swap.pgid)
            
            # Update best solution
            current_score = self.scorer.calculate_score(state)
            if current_score < self.best_score:
                self.best_score = current_score
                self.best_state = copy.deepcopy(state)
                self.iterations_without_improvement = 0
            else:
                self.iterations_without_improvement += 1
            
            self.stats.iterations += 1
            self.stats.swaps_applied += 1
            
            if self.verbose and iteration % 10 == 0:
                self._print_progress(state, iteration, len(swaps_applied))
        
        # Ensure we return the best solution found
        if self.best_state is not None and self.best_score < self.scorer.calculate_score(state):
            # Restore best state and calculate swaps to get there
            # (In practice, we'd track this during optimization)
            pass
        
        return swaps_applied
    
    def _find_best_swap_with_tabu(
        self,
        state: ClusterState
    ) -> Optional[SwapProposal]:
        """
        Find best swap considering tabu restrictions.
        
        Returns:
        - Best non-tabu swap, OR
        - Tabu swap that meets aspiration criteria, OR
        - None if no valid swaps
        """
        from ..analyzer import identify_donors, identify_receivers
        
        donors = identify_donors(state.osds)
        receivers = identify_receivers(state.osds)
        
        if not donors or not receivers:
            return None
        
        current_score = self.scorer.calculate_score(state)
        best_swap = None
        best_improvement = 0
        best_tabu_swap = None
        best_tabu_improvement = 0
        
        tabu_set = set(self.tabu_list)
        
        # Evaluate all possible swaps
        for pg in state.pgs.values():
            if pg.primary not in donors:
                continue
            
            is_tabu = pg.pgid in tabu_set
            
            for candidate_osd in pg.acting[1:]:
                if candidate_osd not in receivers:
                    continue
                
                new_score = self._simulate_swap_score(state, pg.pgid, candidate_osd)
                improvement = current_score - new_score
                
                self.stats.swaps_evaluated += 1
                
                if is_tabu:
                    # Check aspiration criteria
                    if improvement > self.aspiration_threshold and improvement > best_tabu_improvement:
                        best_tabu_improvement = improvement
                        best_tabu_swap = SwapProposal(
                            pgid=pg.pgid,
                            old_primary=pg.primary,
                            new_primary=candidate_osd,
                            score_improvement=improvement
                        )
                else:
                    # Non-tabu swap
                    if improvement > best_improvement:
                        best_improvement = improvement
                        best_swap = SwapProposal(
                            pgid=pg.pgid,
                            old_primary=pg.primary,
                            new_primary=candidate_osd,
                            score_improvement=improvement
                        )
        
        # Return best non-tabu swap, or aspiring tabu swap if better
        if best_swap is not None:
            return best_swap
        elif best_tabu_swap is not None:
            return best_tabu_swap
        else:
            return None
    
    def _simulate_swap_score(
        self,
        state: ClusterState,
        pgid: str,
        new_primary: int
    ) -> float:
        """Simulate swap and return resulting score."""
        from ..optimizer import simulate_swap_score
        return simulate_swap_score(state, pgid, new_primary, self.scorer)
    
    def _apply_swap(self, state: ClusterState, swap: SwapProposal):
        """Apply swap to state."""
        from ..optimizer import apply_swap
        apply_swap(state, swap)
    
    def _print_progress(self, state: ClusterState, iteration: int, total_swaps: int):
        """Print progress message."""
        from ..analyzer import calculate_statistics
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = calculate_statistics(primary_counts)
        print(f"Iteration {iteration}: CV = {stats.cv:.2%}, Best = {self.best_score:.2f}, "
              f"Tabu size = {len(self.tabu_list)}, Swaps = {total_swaps}")
```

**Configuration Examples:**

```python
# Aggressive exploration - long memory
optimizer = TabuSearchOptimizer(tabu_tenure=100, aspiration_threshold=0.05)

# Conservative - short memory
optimizer = TabuSearchOptimizer(tabu_tenure=25, aspiration_threshold=0.15)

# With diversification (restart if stuck)
optimizer = TabuSearchOptimizer(
    tabu_tenure=50,
    aspiration_threshold=0.1,
    diversification_enabled=True
)
```

---

### 4. Simulated Annealing Optimizer (`simulated_annealing.py`)

**Purpose:** Find global optimum by accepting worse moves with decreasing probability

**Algorithm Overview:**

```
1. Start with high "temperature"
2. At each iteration:
   - Find a random valid swap
   - If improvement: accept
   - If worse: accept with probability exp(delta / temperature)
3. Gradually decrease temperature (cooling)
4. Repeat until temperature near zero or target achieved
```

**Implementation:**

```python
import random
import math
from typing import List, Optional
from .base import OptimizerBase, OptimizerRegistry
from ..models import ClusterState, SwapProposal

@OptimizerRegistry.register('simulated_annealing')
class SimulatedAnnealingOptimizer(OptimizerBase):
    """
    Simulated Annealing Optimizer - finds global optimum through probabilistic acceptance.
    
    Benefits:
    - Can find global optimum (best possible balance)
    - Escapes local optima effectively
    - 2-5% better CV than greedy in benchmarks
    
    Trade-offs:
    - Non-deterministic (different runs give different results)
    - 2-5x slower than greedy
    - Requires careful tuning
    """
    
    def __init__(
        self,
        initial_temperature: float = 100.0,
        cooling_rate: float = 0.995,
        min_temperature: float = 0.01,
        reheat_enabled: bool = False,
        seed: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize Simulated Annealing optimizer.
        
        Args:
            initial_temperature: Starting temperature (higher = more exploration)
            cooling_rate: Temperature multiplier per iteration (0.99-0.999)
            min_temperature: Stop when temperature drops below this
            reheat_enabled: Reheat temperature if stuck
            seed: Random seed for reproducibility (None = random)
            **kwargs: Base optimizer parameters
        """
        super().__init__(**kwargs)
        self.initial_temperature = initial_temperature
        self.cooling_rate = cooling_rate
        self.min_temperature = min_temperature
        self.reheat_enabled = reheat_enabled
        
        if seed is not None:
            random.seed(seed)
        
        self.temperature = initial_temperature
        self.accepted_swaps = 0
        self.rejected_swaps = 0
    
    @property
    def algorithm_name(self) -> str:
        return f"Simulated Annealing (T₀={self.initial_temperature})"
    
    @property
    def is_deterministic(self) -> bool:
        return False  # Due to random acceptance
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """Run simulated annealing optimization."""
        swaps_applied = []
        self.temperature = self.initial_temperature
        
        for iteration in range(self.max_iterations):
            if self._check_termination(state, iteration):
                break
            
            if self.temperature < self.min_temperature:
                break
            
            # Find a random valid swap
            swap = self._find_random_swap(state)
            
            if swap is None:
                # No valid swaps found - try reheating if enabled
                if self.reheat_enabled and iteration > 100:
                    self.temperature = self.initial_temperature * 0.5
                    continue
                else:
                    break
            
            # Decide whether to accept the swap
            if self._accept_swap(swap.score_improvement):
                self._apply_swap(state, swap)
                swaps_applied.append(swap)
                self.stats.swaps_applied += 1
                self.accepted_swaps += 1
            else:
                self.rejected_swaps += 1
            
            # Cool down
            self.temperature *= self.cooling_rate
            
            self.stats.iterations += 1
            
            if self.verbose and iteration % 10 == 0:
                self._print_progress(state, iteration, len(swaps_applied))
        
        return swaps_applied
    
    def _find_random_swap(
        self,
        state: ClusterState
    ) -> Optional[SwapProposal]:
        """
        Find a random valid swap.
        
        Randomly selects a donor and attempts to find a receiver
        in one of its PG's acting sets.
        """
        from ..analyzer import identify_donors, identify_receivers
        
        donors = identify_donors(state.osds)
        receivers = identify_receivers(state.osds)
        
        if not donors or not receivers:
            return None
        
        current_score = self.scorer.calculate_score(state)
        
        # Try up to 100 random attempts to find a valid swap
        for _ in range(100):
            # Random donor
            donor = random.choice(donors)
            
            # Find PGs where this donor is primary
            donor_pgs = [pg for pg in state.pgs.values() if pg.primary == donor]
            if not donor_pgs:
                continue
            
            # Random PG
            pg = random.choice(donor_pgs)
            
            # Find receivers in acting set
            receivers_in_acting = [osd for osd in pg.acting[1:] if osd in receivers]
            if not receivers_in_acting:
                continue
            
            # Random receiver
            new_primary = random.choice(receivers_in_acting)
            
            # Calculate improvement
            new_score = self._simulate_swap_score(state, pg.pgid, new_primary)
            improvement = current_score - new_score
            
            self.stats.swaps_evaluated += 1
            
            return SwapProposal(
                pgid=pg.pgid,
                old_primary=pg.primary,
                new_primary=new_primary,
                score_improvement=improvement
            )
        
        return None
    
    def _accept_swap(self, improvement: float) -> bool:
        """
        Decide whether to accept a swap using Metropolis criterion.
        
        - Always accept if improvement > 0
        - Accept worse swaps with probability exp(improvement / temperature)
        
        Args:
            improvement: Score improvement (positive = better)
        
        Returns:
            True if swap should be accepted
        """
        if improvement > 0:
            return True
        
        # Calculate acceptance probability for worse swap
        # improvement is negative here, so this gives a value between 0 and 1
        acceptance_probability = math.exp(improvement / self.temperature)
        
        return random.random() < acceptance_probability
    
    def _simulate_swap_score(
        self,
        state: ClusterState,
        pgid: str,
        new_primary: int
    ) -> float:
        """Simulate swap and return resulting score."""
        from ..optimizer import simulate_swap_score
        return simulate_swap_score(state, pgid, new_primary, self.scorer)
    
    def _apply_swap(self, state: ClusterState, swap: SwapProposal):
        """Apply swap to state."""
        from ..optimizer import apply_swap
        apply_swap(state, swap)
    
    def _print_progress(self, state: ClusterState, iteration: int, total_swaps: int):
        """Print progress message."""
        from ..analyzer import calculate_statistics
        primary_counts = [osd.primary_count for osd in state.osds.values()]
        stats = calculate_statistics(primary_counts)
        accept_rate = self.accepted_swaps / (self.accepted_swaps + self.rejected_swaps) if (self.accepted_swaps + self.rejected_swaps) > 0 else 0
        print(f"Iteration {iteration}: CV = {stats.cv:.2%}, T = {self.temperature:.2f}, "
              f"Accept rate = {accept_rate:.1%}, Swaps = {total_swaps}")
    
    def get_stats(self) -> dict:
        """Return extended statistics."""
        stats = super().get_stats()
        stats.update({
            'final_temperature': self.temperature,
            'accepted_swaps': self.accepted_swaps,
            'rejected_swaps': self.rejected_swaps,
            'acceptance_rate': self.accepted_swaps / (self.accepted_swaps + self.rejected_swaps)
                if (self.accepted_swaps + self.rejected_swaps) > 0 else 0
        })
        return stats
```

**Configuration Examples:**

```python
# High exploration - good for severely imbalanced clusters
optimizer = SimulatedAnnealingOptimizer(
    initial_temperature=200.0,
    cooling_rate=0.998,
    min_temperature=0.01
)

# Fast convergence - for moderately imbalanced clusters
optimizer = SimulatedAnnealingOptimizer(
    initial_temperature=50.0,
    cooling_rate=0.99,
    min_temperature=0.1
)

# Reproducible - with seed
optimizer = SimulatedAnnealingOptimizer(
    initial_temperature=100.0,
    cooling_rate=0.995,
    seed=42  # Same results every run
)

# With reheating - restart if stuck
optimizer = SimulatedAnnealingOptimizer(
    initial_temperature=100.0,
    cooling_rate=0.995,
    reheat_enabled=True
)
```

---

### 5. Hybrid Algorithms (`hybrid.py`)

**Purpose:** Combine algorithms for best of both worlds

```python
from typing import List
from .base import OptimizerBase, OptimizerRegistry
from ..models import ClusterState, SwapProposal

@OptimizerRegistry.register('hybrid_greedy_annealing')
class HybridGreedyAnnealingOptimizer(OptimizerBase):
    """
    Hybrid: Fast greedy to get close, then annealing for refinement.
    
    Strategy:
    1. Phase 1: Greedy optimization to 1.2× target CV (fast)
    2. Phase 2: Simulated annealing for final refinement (quality)
    
    Benefits:
    - Fast initial convergence from greedy
    - High-quality final result from annealing
    - Best of both worlds
    """
    
    def __init__(
        self,
        phase1_target_multiplier: float = 1.2,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.phase1_target_multiplier = phase1_target_multiplier
    
    @property
    def algorithm_name(self) -> str:
        return "Hybrid (Greedy + SA)"
    
    @property
    def is_deterministic(self) -> bool:
        return False  # Due to SA phase
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """Run hybrid optimization."""
        from .greedy import GreedyOptimizer
        from .simulated_annealing import SimulatedAnnealingOptimizer
        
        # Phase 1: Greedy to get most of the way there
        phase1_target = self.target_cv * self.phase1_target_multiplier
        greedy = GreedyOptimizer(
            target_cv=phase1_target,
            max_iterations=self.max_iterations // 2,
            scorer=self.scorer,
            verbose=self.verbose
        )
        
        if self.verbose:
            print(f"Phase 1: Greedy optimization to CV = {phase1_target:.2%}")
        
        swaps_phase1 = greedy.optimize(state)
        
        # Phase 2: Simulated annealing for refinement
        if self.verbose:
            print(f"Phase 2: Simulated annealing refinement to CV = {self.target_cv:.2%}")
        
        sa = SimulatedAnnealingOptimizer(
            target_cv=self.target_cv,
            max_iterations=self.max_iterations // 2,
            scorer=self.scorer,
            verbose=self.verbose,
            initial_temperature=50.0,  # Lower temp for refinement
            cooling_rate=0.99
        )
        
        swaps_phase2 = sa.optimize(state)
        
        # Combine swaps
        return swaps_phase1 + swaps_phase2


@OptimizerRegistry.register('hybrid_batch_tabu')
class HybridBatchTabuOptimizer(OptimizerBase):
    """
    Hybrid: Batch greedy for speed, tabu search for quality.
    
    Fast and deterministic with better quality than pure greedy.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def algorithm_name(self) -> str:
        return "Hybrid (Batch + Tabu)"
    
    @property
    def is_deterministic(self) -> bool:
        return True
    
    def optimize(self, state: ClusterState) -> List[SwapProposal]:
        """Run hybrid optimization."""
        from .batch_greedy import BatchGreedyOptimizer
        from .tabu_search import TabuSearchOptimizer
        
        # Phase 1: Batch greedy (fast)
        batch = BatchGreedyOptimizer(
            target_cv=self.target_cv * 1.15,
            max_iterations=self.max_iterations // 2,
            scorer=self.scorer,
            verbose=self.verbose,
            batch_size=15
        )
        
        swaps_phase1 = batch.optimize(state)
        
        # Phase 2: Tabu search (quality)
        tabu = TabuSearchOptimizer(
            target_cv=self.target_cv,
            max_iterations=self.max_iterations // 2,
            scorer=self.scorer,
            verbose=self.verbose
        )
        
        swaps_phase2 = tabu.optimize(state)
        
        return swaps_phase1 + swaps_phase2
```

---

## CLI Integration

### Enhanced CLI with Algorithm Selection

```python
# In cli.py - add new arguments

parser.add_argument(
    '--algorithm',
    type=str,
    default='greedy',
    choices=['greedy', 'batch_greedy', 'tabu_search', 'simulated_annealing', 
             'hybrid_greedy_annealing', 'hybrid_batch_tabu'],
    help='Optimization algorithm (default: greedy)'
)

parser.add_argument(
    '--algorithm-params',
    type=str,
    help='Algorithm-specific parameters as JSON (e.g., {"batch_size": 15})'
)

parser.add_argument(
    '--list-algorithms',
    action='store_true',
    help='List all available algorithms and exit'
)

# Usage examples:

# Default greedy
python3 -m ceph_primary_balancer.cli --dry-run

# Batch greedy for faster convergence
python3 -m ceph_primary_balancer.cli \
    --algorithm batch_greedy \
    --algorithm-params '{"batch_size": 20}' \
    --output rebalance.sh

# Tabu search for better quality
python3 -m ceph_primary_balancer.cli \
    --algorithm tabu_search \
    --algorithm-params '{"tabu_tenure": 75}' \
    --output rebalance.sh

# Simulated annealing for best quality
python3 -m ceph_primary_balancer.cli \
    --algorithm simulated_annealing \
    --algorithm-params '{"initial_temperature": 150.0, "cooling_rate": 0.997}' \
    --output rebalance.sh

# Hybrid for best of both worlds
python3 -m ceph_primary_balancer.cli \
    --algorithm hybrid_greedy_annealing \
    --output rebalance.sh

# List all algorithms
python3 -m ceph_primary_balancer.cli --list-algorithms
```

### Configuration File Support

```json
{
  "optimization": {
    "target_cv": 0.10,
    "max_iterations": 1000,
    "algorithm": "batch_greedy",
    "algorithm_params": {
      "batch_size": 15,
      "conflict_detection": "strict"
    }
  },
  "scoring": {
    "weight_osd": 0.5,
    "weight_host": 0.3,
    "weight_pool": 0.2
  }
}
```

---

## Benchmark Integration

### Algorithm Comparison Benchmarks

```python
# New benchmark scenarios for algorithm comparison

ALGORITHM_COMPARISON_SCENARIOS = [
    {
        'name': 'comparison_small',
        'description': 'Small cluster for quick comparison',
        'params': {
            'num_osds': 50,
            'num_pgs': 1000,
            'imbalance_cv': 0.30
        },
        'algorithms': ['greedy', 'batch_greedy', 'tabu_search', 'simulated_annealing']
    },
    {
        'name': 'comparison_medium',
        'description': 'Medium cluster for comprehensive comparison',
        'params': {
            'num_osds': 100,
            'num_pgs': 5000,
            'imbalance_cv': 0.35
        },
        'algorithms': ['greedy', 'batch_greedy', 'tabu_search', 'simulated_annealing']
    },
    {
        'name': 'comparison_severe_imbalance',
        'description': 'Severely imbalanced cluster',
        'params': {
            'num_osds': 100,
            'num_pgs': 5000,
            'imbalance_cv': 0.60,
            'imbalance_pattern': 'concentrated'
        },
        'algorithms': ['greedy', 'tabu_search', 'simulated_annealing']
    }
]
```

### Benchmark CLI Commands

```bash
# Compare all algorithms on standard scenarios
python3 -m ceph_primary_balancer.benchmark_cli compare-algorithms \
    --scenarios standard \
    --output comparison.json \
    --html-output comparison.html

# Compare specific algorithms
python3 -m ceph_primary_balancer.benchmark_cli compare-algorithms \
    --algorithms greedy,batch_greedy,tabu_search \
    --scenarios quick \
    --output comparison.json

# Benchmark specific algorithm
python3 -m ceph_primary_balancer.benchmark_cli run \
    --algorithm simulated_annealing \
    --suite performance \
    --output sa_benchmark.json
```

---

## Implementation Sprints

### Sprint 6A: Foundation & Batch Greedy (Week 1)

**Tasks:**
1. Create `optimizers/` package structure
2. Implement `OptimizerBase` interface
3. Implement `OptimizerRegistry`
4. Refactor existing greedy into new structure
5. Implement Batch Greedy algorithm
6. Unit tests for base and batch greedy

**Deliverables:**
- Working optimizer framework
- Batch Greedy implementation
- Test coverage ≥85%

**Success Criteria:**
- Batch Greedy is 20-40% faster than greedy
- All tests pass
- CLI integration working

---

### Sprint 6B: Tabu Search (Week 2)

**Tasks:**
1. Implement Tabu Search algorithm
2. Implement tabu list management
3. Implement aspiration criteria
4. Add diversification (restart) logic
5. Unit tests for tabu search
6. Integration tests

**Deliverables:**
- Working Tabu Search implementation
- Test coverage ≥85%
- Documentation

**Success Criteria:**
- Tabu achieves 10-15% better CV than greedy
- Deterministic results
- All tests pass

---

### Sprint 6C: Simulated Annealing (Week 3)

**Tasks:**
1. Implement Simulated Annealing algorithm
2. Implement cooling schedule
3. Implement acceptance criteria
4. Add optional reheating
5. Unit tests for SA
6. Performance tuning

**Deliverables:**
- Working Simulated Annealing implementation
- Test coverage ≥85%
- Parameter tuning guide

**Success Criteria:**
- SA achieves 2-5% better CV than greedy
- Reasonable runtime (2-5x greedy)
- Reproducible with seed

---

### Sprint 6D: Hybrid & Benchmarks (Week 4)

**Tasks:**
1. Implement hybrid algorithms
2. Integrate with benchmark framework
3. Add algorithm comparison benchmarks
4. Generate comparison reports
5. Performance tuning
6. Integration testing

**Deliverables:**
- Hybrid algorithms working
- Algorithm comparison benchmarks
- Comprehensive comparison report

**Success Criteria:**
- Hybrid algorithms show expected characteristics
- Benchmarks complete in reasonable time
- Clear winner for different scenarios

---

### Sprint 6E: CLI & Documentation (Week 5)

**Tasks:**
1. Enhance CLI with algorithm selection
2. Add `--list-algorithms` command
3. Update all documentation
4. Create algorithm selection guide
5. Add usage examples
6. Final testing and release

**Deliverables:**
- Complete CLI integration
- Comprehensive documentation
- Algorithm selection guide
- v1.2.0 release

**Success Criteria:**
- Users can easily switch algorithms
- Clear guidance on algorithm selection
- All documentation complete

---

## Testing Strategy

### Unit Tests

**Test Coverage Goals:**
- `base.py`: 100% (interface contracts)
- `batch_greedy.py`: ≥90%
- `tabu_search.py`: ≥90%
- `simulated_annealing.py`: ≥85% (randomness makes 100% difficult)
- `hybrid.py`: ≥85%

**Test Categories:**

```python
# 1. Algorithm correctness tests
def test_batch_greedy_finds_multiple_swaps()
def test_tabu_list_prevents_recent_moves()
def test_simulated_annealing_accepts_worse_moves()

# 2. Determinism tests
def test_greedy_is_deterministic()
def test_batch_greedy_is_deterministic()
def test_tabu_is_deterministic()
def test_simulated_annealing_with_seed_is_reproducible()

# 3. Termination tests
def test_terminates_at_target_cv()
def test_terminates_at_max_iterations()
def test_terminates_when_no_swaps_available()

# 4. Quality tests
def test_batch_greedy_improves_balance()
def test_tabu_reaches_better_solution_than_greedy()
def test_simulated_annealing_reaches_best_solution()

# 5. Edge cases
def test_already_balanced_cluster()
def test_single_osd_cluster()
def test_no_valid_swaps_cluster()
```

### Integration Tests

```python
def test_end_to_end_batch_greedy():
    """Test complete optimization with batch greedy."""
    state = generate_synthetic_cluster(num_osds=50, imbalance_cv=0.30)
    optimizer = BatchGreedyOptimizer(target_cv=0.10)
    swaps = optimizer.optimize(state)
    
    # Verify improvement
    assert optimizer.get_final_cv() < 0.10
    assert len(swaps) > 0

def test_algorithm_comparison():
    """Test that all algorithms work on same cluster."""
    state = generate_synthetic_cluster(num_osds=100, imbalance_cv=0.35)
    
    results = {}
    for algo in ['greedy', 'batch_greedy', 'tabu_search', 'simulated_annealing']:
        state_copy = copy.deepcopy(state)
        optimizer = OptimizerRegistry.get_optimizer(algo, target_cv=0.10)
        swaps = optimizer.optimize(state_copy)
        results[algo] = {
            'final_cv': optimizer.get_final_cv(),
            'swaps': len(swaps),
            'time': optimizer.get_stats()['execution_time']
        }
    
    # Verify all improved the cluster
    for algo, result in results.items():
        assert result['final_cv'] < 0.35
```

---

## Performance Targets

### Expected Performance Characteristics

| Algorithm | Time vs Greedy | Quality vs Greedy | Deterministic |
|-----------|----------------|-------------------|---------------|
| Greedy (baseline) | 1.0× | 100% | ✅ Yes |
| Batch Greedy | 0.6-0.8× | 100-102% | ✅ Yes |
| Tabu Search | 1.5-3.0× | 110-115% | ✅ Yes |
| Simulated Annealing | 2.0-5.0× | 115-120% | ❌ No |
| Hybrid Greedy+SA | 1.5-3.0× | 112-118% | ❌ No |

**Quality measurement:** % improvement in final CV compared to greedy

### Benchmark Scenarios

```python
# Quick comparison (5-10 minutes)
QUICK_COMPARISON = {
    'scenarios': ['small_balanced', 'small_imbalanced'],
    'algorithms': ['greedy', 'batch_greedy', 'tabu_search'],
    'iterations': 3
}

# Standard comparison (30-60 minutes)
STANDARD_COMPARISON = {
    'scenarios': ['medium_replicated', 'medium_ec', 'multi_pool'],
    'algorithms': ['greedy', 'batch_greedy', 'tabu_search', 'simulated_annealing'],
    'iterations': 5
}

# Comprehensive comparison (2-4 hours)
COMPREHENSIVE_COMPARISON = {
    'scenarios': ['small', 'medium', 'large', 'severe_imbalance'],
    'algorithms': ['all'],
    'iterations': 10
}
```

---

## Documentation Requirements

### User-Facing Documentation

1. **Algorithm Overview** (`docs/algorithms/README.md`)
   - What each algorithm does
   - When to use each
   - Trade-offs comparison

2. **Algorithm-Specific Guides**
   - `docs/algorithms/batch-greedy.md`
   - `docs/algorithms/tabu-search.md`
   - `docs/algorithms/simulated-annealing.md`

3. **Algorithm Selection Guide** (`docs/algorithms/selection-guide.md`)
   - Decision tree for algorithm selection
   - Parameter tuning guidelines
   - Performance expectations

4. **Updated Usage Guide**
   - Add `--algorithm` examples
   - Update best practices
   - Add troubleshooting for new algorithms

### Developer Documentation

1. **Optimizer API Reference**
   - `OptimizerBase` interface
   - `OptimizerRegistry` usage
   - Creating custom algorithms

2. **Algorithm Implementation Guide**
   - Design patterns
   - Testing requirements
   - Benchmarking integration

3. **Performance Tuning Guide**
   - Profiling techniques
   - Optimization tips
   - Memory management

---

## Success Criteria

### Functional Requirements

✅ All algorithms implement `OptimizerBase` interface  
✅ Algorithm registry allows dynamic selection  
✅ CLI supports `--algorithm` flag  
✅ Configuration files support algorithm selection  
✅ All algorithms improve cluster balance  
✅ Deterministic algorithms produce consistent results  
✅ Non-deterministic algorithms support seeding  

### Performance Requirements

✅ Batch Greedy: 20-40% faster than greedy  
✅ Tabu Search: 10-15% better CV than greedy  
✅ Simulated Annealing: 2-5% better CV than greedy  
✅ No algorithm slower than 10× greedy  
✅ Memory usage remains <2 MB per 1000 PGs  

### Quality Requirements

✅ Test coverage ≥85% for all algorithms  
✅ All algorithms pass integration tests  
✅ Benchmark comparison report generated  
✅ Documentation complete and accurate  
✅ User guide includes selection guidance  

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Algorithms too slow | High | Implement batch greedy first (faster), make SA optional |
| Poor convergence | Medium | Extensive parameter tuning, provide presets |
| Complex parameter tuning | Medium | Provide good defaults, auto-tuning in future |
| Non-determinism confusion | Low | Clear documentation, seed support |
| Regression in greedy | High | Keep greedy as-is, only refactor wrapper |
| Integration complexity | Medium | Use Phase 5 framework, incremental testing |

---

## Dependencies

**Zero New External Dependencies** (maintaining project policy)

Using Python stdlib:
- `random` for simulated annealing
- `math` for acceptance probability
- `collections.deque` for tabu list
- `copy` for state snapshots

---

## Future Enhancements (v1.3+)

### Adaptive Algorithms
- Auto-tuning parameters based on cluster characteristics
- Dynamic algorithm selection during optimization
- Learning optimal weights from history

### Parallel Algorithms
- Multi-threaded batch processing
- Distributed tabu search
- Population-based methods (genetic algorithms)

### Machine Learning Integration
- Predict best algorithm for cluster
- Learn optimal parameters
- Reinforcement learning for optimization

### Advanced Hybrid Strategies
- Three-phase optimization (batch → tabu → SA)
- Adaptive phase switching
- Portfolio approach (run multiple, pick best)

---

## Version History & Roadmap

### v1.0.0 (Released)
✅ Production-ready greedy algorithm  
✅ Multi-dimensional scoring  
✅ Configuration management  

### v1.1.0 (Released)
✅ Comprehensive benchmark framework  
✅ Performance profiling  
✅ Quality analysis  

### v1.2.0 (This Phase)
🎯 Batch Greedy algorithm  
🎯 Tabu Search algorithm  
🎯 Simulated Annealing algorithm  
🎯 Algorithm comparison framework  
🎯 Enhanced CLI  

### v1.3.0 (Future)
⏳ Auto-tuning framework  
⏳ Adaptive algorithms  
⏳ Machine learning integration  

### v2.0.0 (Future)
⏳ Parallel optimization  
⏳ Distributed algorithms  
⏳ Real-time balancing daemon  

---

## Conclusion

Phase 6 transforms the Ceph Primary PG Balancer from a single-algorithm tool into a flexible optimization framework. By providing multiple algorithms with different trade-offs, users can choose the best approach for their specific needs:

- **Need speed?** Use Batch Greedy
- **Need quality?** Use Simulated Annealing
- **Need balance?** Use Tabu Search or Hybrid
- **Need proven reliability?** Keep using Greedy

The modular architecture makes it easy to add new algorithms in the future, and the benchmark framework ensures we can objectively compare their performance.

**Target Release:** v1.2.0 - Approximately 5 weeks from start of Phase 6

---

**Document Status:** Planning Complete  
**Next Step:** Begin Sprint 6A - Foundation & Batch Greedy  
**Approval Required:** Architecture review before implementation
