"""
Test suite for Phase 1: Host-Level Balancing functionality.

This module tests the new host-aware optimization features including:
- Host topology extraction
- Host-level statistics calculation
- Multi-dimensional scoring
- Host-aware swap prioritization
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ceph_primary_balancer.models import PGInfo, OSDInfo, HostInfo, ClusterState, SwapProposal
from ceph_primary_balancer.scorer import Scorer
from ceph_primary_balancer.optimizers.greedy import simulate_swap_score, apply_swap
from ceph_primary_balancer.analyzer import calculate_statistics


def test_host_info_creation():
    """Test that HostInfo objects are created correctly."""
    host = HostInfo(
        hostname="host1",
        osd_ids=[0, 1, 2],
        primary_count=150,
        total_pg_count=450
    )
    
    assert host.hostname == "host1"
    assert len(host.osd_ids) == 3
    assert host.primary_count == 150
    assert host.total_pg_count == 450
    print("✓ HostInfo creation test passed")


def test_osd_host_linkage():
    """Test that OSDs are correctly linked to their host."""
    osd = OSDInfo(osd_id=0, host="host1", primary_count=50, total_pg_count=150)
    
    assert osd.osd_id == 0
    assert osd.host == "host1"
    assert osd.primary_count == 50
    print("✓ OSD-Host linkage test passed")


def test_cluster_state_with_hosts():
    """Test ClusterState with host topology."""
    # Create test data
    pgs = {
        "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 1, 2]),
        "1.1": PGInfo(pgid="1.1", pool_id=1, acting=[3, 4, 5]),
    }
    
    osds = {
        0: OSDInfo(osd_id=0, host="host1", primary_count=1, total_pg_count=1),
        1: OSDInfo(osd_id=1, host="host1", primary_count=0, total_pg_count=1),
        2: OSDInfo(osd_id=2, host="host1", primary_count=0, total_pg_count=1),
        3: OSDInfo(osd_id=3, host="host2", primary_count=1, total_pg_count=1),
        4: OSDInfo(osd_id=4, host="host2", primary_count=0, total_pg_count=1),
        5: OSDInfo(osd_id=5, host="host2", primary_count=0, total_pg_count=1),
    }
    
    hosts = {
        "host1": HostInfo(hostname="host1", osd_ids=[0, 1, 2], primary_count=1, total_pg_count=3),
        "host2": HostInfo(hostname="host2", osd_ids=[3, 4, 5], primary_count=1, total_pg_count=3),
    }
    
    state = ClusterState(pgs=pgs, osds=osds, hosts=hosts)
    
    assert len(state.hosts) == 2
    assert "host1" in state.hosts
    assert "host2" in state.hosts
    assert state.hosts["host1"].primary_count == 1
    assert state.hosts["host2"].primary_count == 1
    print("✓ ClusterState with hosts test passed")


def test_scorer_initialization():
    """Test Scorer initialization and weight validation."""
    # Valid scorer
    scorer = Scorer(w_osd=0.7, w_host=0.3, w_pool=0.0)
    assert scorer.w_osd == 0.7
    assert scorer.w_host == 0.3
    assert scorer.w_pool == 0.0
    
    # Test weight validation
    try:
        invalid_scorer = Scorer(w_osd=0.5, w_host=0.3, w_pool=0.0)  # Sum != 1.0
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "sum to 1.0" in str(e)
    
    print("✓ Scorer initialization test passed")


def test_scorer_variance_calculation():
    """Test OSD and host variance calculation."""
    # Create simple cluster state
    osds = {
        0: OSDInfo(osd_id=0, host="host1", primary_count=100, total_pg_count=300),
        1: OSDInfo(osd_id=1, host="host1", primary_count=110, total_pg_count=300),
        2: OSDInfo(osd_id=2, host="host2", primary_count=90, total_pg_count=300),
        3: OSDInfo(osd_id=3, host="host2", primary_count=100, total_pg_count=300),
    }
    
    hosts = {
        "host1": HostInfo(hostname="host1", osd_ids=[0, 1], primary_count=210, total_pg_count=600),
        "host2": HostInfo(hostname="host2", osd_ids=[2, 3], primary_count=190, total_pg_count=600),
    }
    
    state = ClusterState(pgs={}, osds=osds, hosts=hosts)
    
    scorer = Scorer(w_osd=0.7, w_host=0.3, w_pool=0.0)
    
    # Calculate variances
    osd_var = scorer.calculate_osd_variance(state)
    host_var = scorer.calculate_host_variance(state)
    
    assert osd_var > 0, "OSD variance should be positive"
    assert host_var > 0, "Host variance should be positive"
    
    # Calculate composite score
    score = scorer.calculate_score(state)
    expected_score = (0.7 * osd_var) + (0.3 * host_var)
    assert abs(score - expected_score) < 0.01, f"Score {score} != expected {expected_score}"
    
    print("✓ Scorer variance calculation test passed")


def test_host_count_updates_on_swap():
    """Test that host primary counts are updated correctly when swaps are applied."""
    # Create test cluster
    pgs = {
        "1.0": PGInfo(pgid="1.0", pool_id=1, acting=[0, 2]),  # host1 -> host2
    }
    
    osds = {
        0: OSDInfo(osd_id=0, host="host1", primary_count=1, total_pg_count=1),
        2: OSDInfo(osd_id=2, host="host2", primary_count=0, total_pg_count=1),
    }
    
    hosts = {
        "host1": HostInfo(hostname="host1", osd_ids=[0], primary_count=1, total_pg_count=1),
        "host2": HostInfo(hostname="host2", osd_ids=[2], primary_count=0, total_pg_count=1),
    }
    
    state = ClusterState(pgs=pgs, osds=osds, hosts=hosts)
    
    # Create and apply swap
    swap = SwapProposal(
        pgid="1.0",
        old_primary=0,
        new_primary=2,
        score_improvement=0.5
    )
    
    apply_swap(state, swap)
    
    # Verify OSD counts
    assert state.osds[0].primary_count == 0, "Old primary should have 0 primaries"
    assert state.osds[2].primary_count == 1, "New primary should have 1 primary"
    
    # Verify host counts
    assert state.hosts["host1"].primary_count == 0, "host1 should have 0 primaries"
    assert state.hosts["host2"].primary_count == 1, "host2 should have 1 primary"
    
    # Verify PG acting set
    assert state.pgs["1.0"].primary == 2, "PG primary should be OSD 2"
    
    print("✓ Host count updates on swap test passed")


def test_multi_dimensional_scoring():
    """Test that multi-dimensional scoring considers both OSD and host levels."""
    # Create imbalanced cluster (balanced at OSD level but not host level)
    osds = {
        0: OSDInfo(osd_id=0, host="host1", primary_count=100, total_pg_count=300),
        1: OSDInfo(osd_id=1, host="host1", primary_count=100, total_pg_count=300),
        2: OSDInfo(osd_id=2, host="host2", primary_count=100, total_pg_count=300),
        3: OSDInfo(osd_id=3, host="host3", primary_count=100, total_pg_count=300),
    }
    
    hosts = {
        "host1": HostInfo(hostname="host1", osd_ids=[0, 1], primary_count=200, total_pg_count=600),
        "host2": HostInfo(hostname="host2", osd_ids=[2], primary_count=100, total_pg_count=300),
        "host3": HostInfo(hostname="host3", osd_ids=[3], primary_count=100, total_pg_count=300),
    }
    
    state = ClusterState(pgs={}, osds=osds, hosts=hosts)
    
    # Calculate statistics
    osd_stats = calculate_statistics([osd.primary_count for osd in osds.values()])
    host_stats = calculate_statistics([host.primary_count for host in hosts.values()])
    
    # OSDs are perfectly balanced
    assert osd_stats.cv < 0.01, "OSDs should be perfectly balanced"
    
    # Hosts are imbalanced
    assert host_stats.cv > 0.2, "Hosts should be imbalanced"
    
    # Scorer should detect imbalance
    scorer = Scorer(w_osd=0.5, w_host=0.5, w_pool=0.0)
    score = scorer.calculate_score(state)
    
    # Score should be dominated by host variance
    host_var = scorer.calculate_host_variance(state)
    assert score > (0.4 * host_var), "Score should reflect host imbalance"
    
    print("✓ Multi-dimensional scoring test passed")


def test_swap_proposal_backward_compatibility():
    """Test that SwapProposal maintains backward compatibility with variance_improvement."""
    swap = SwapProposal(
        pgid="1.0",
        old_primary=0,
        new_primary=1,
        score_improvement=10.5
    )
    
    # Test backward compatibility property
    assert swap.variance_improvement == 10.5, "variance_improvement should alias score_improvement"
    assert swap.score_improvement == 10.5
    
    print("✓ SwapProposal backward compatibility test passed")


def run_all_tests():
    """Run all Phase 1 host balancing tests."""
    print("\n" + "="*60)
    print("Running Phase 1: Host-Level Balancing Tests")
    print("="*60 + "\n")
    
    test_host_info_creation()
    test_osd_host_linkage()
    test_cluster_state_with_hosts()
    test_scorer_initialization()
    test_scorer_variance_calculation()
    test_host_count_updates_on_swap()
    test_multi_dimensional_scoring()
    test_swap_proposal_backward_compatibility()
    
    print("\n" + "="*60)
    print("All Phase 1 tests passed! ✓")
    print("="*60)


if __name__ == "__main__":
    run_all_tests()
