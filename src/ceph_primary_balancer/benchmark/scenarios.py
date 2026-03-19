"""
Standard test scenarios for benchmarking.

This module defines standard benchmark scenarios covering different
cluster configurations, scales, and imbalance patterns.
"""

from typing import Dict, List, Any



# Production-realistic scenario modeled after a real HDD cluster:
# ~840 OSDs across 60 hosts, ~28 pools sharing the same OSD set,
# mix of EC size-20 and replicated size-3/5 pools, PG counts from 16 to 2048.
# Key characteristics this captures that other scenarios miss:
#   - Sparse PGs/OSD ratio (~6 vs benchmark typical ~100)
#   - Wildly varying pool sizes (16 vs 2048)
#   - EC pools with 20 OSDs per PG (many candidates for primary swap)
#   - All pools share the same OSD set (cross-pool interference)
PRODUCTION_REALISTIC_POOLS = [
    # Large EC pools (bulk storage) — EC 16+4, size 20
    {'name': 'bulk-ec-1', 'pgs': 2048, 'replication': 20, 'imbalance_cv': 0.25, 'pattern': 'random'},
    {'name': 'bulk-ec-2', 'pgs': 2048, 'replication': 20, 'imbalance_cv': 0.30, 'pattern': 'random'},
    {'name': 'bulk-ec-3', 'pgs': 2048, 'replication': 20, 'imbalance_cv': 0.20, 'pattern': 'random'},
    # Medium replicated pools (higher durability workloads) — size 5
    {'name': 'replicated-5a', 'pgs': 512, 'replication': 5, 'imbalance_cv': 0.35, 'pattern': 'random'},
    {'name': 'replicated-5b', 'pgs': 256, 'replication': 5, 'imbalance_cv': 0.30, 'pattern': 'random'},
    {'name': 'replicated-5c', 'pgs': 256, 'replication': 5, 'imbalance_cv': 0.25, 'pattern': 'random'},
    # Small replicated pools (rgw index, meta, etc.) — size 3
    {'name': 'rgw-index-1', 'pgs': 64, 'replication': 3, 'imbalance_cv': 0.40, 'pattern': 'random'},
    {'name': 'rgw-index-2', 'pgs': 64, 'replication': 3, 'imbalance_cv': 0.35, 'pattern': 'random'},
    {'name': 'rgw-data-1', 'pgs': 128, 'replication': 3, 'imbalance_cv': 0.30, 'pattern': 'random'},
    {'name': 'rgw-data-2', 'pgs': 128, 'replication': 3, 'imbalance_cv': 0.25, 'pattern': 'random'},
    {'name': 'meta-1', 'pgs': 32, 'replication': 3, 'imbalance_cv': 0.45, 'pattern': 'concentrated'},
    {'name': 'meta-2', 'pgs': 32, 'replication': 3, 'imbalance_cv': 0.40, 'pattern': 'concentrated'},
    {'name': 'meta-3', 'pgs': 16, 'replication': 3, 'imbalance_cv': 0.50, 'pattern': 'concentrated'},
    {'name': 'meta-4', 'pgs': 16, 'replication': 3, 'imbalance_cv': 0.45, 'pattern': 'concentrated'},
    # Additional medium pools
    {'name': 'project-1', 'pgs': 512, 'replication': 3, 'imbalance_cv': 0.30, 'pattern': 'random'},
    {'name': 'project-2', 'pgs': 256, 'replication': 3, 'imbalance_cv': 0.25, 'pattern': 'random'},
    {'name': 'project-3', 'pgs': 128, 'replication': 3, 'imbalance_cv': 0.35, 'pattern': 'random'},
    {'name': 'scratch', 'pgs': 1024, 'replication': 3, 'imbalance_cv': 0.20, 'pattern': 'random'},
    # Tiny pools (cephfs meta, rgw meta)
    {'name': 'cephfs-meta-1', 'pgs': 16, 'replication': 3, 'imbalance_cv': 0.50, 'pattern': 'random'},
    {'name': 'cephfs-meta-2', 'pgs': 16, 'replication': 3, 'imbalance_cv': 0.45, 'pattern': 'random'},
    {'name': 'rgw-meta-1', 'pgs': 32, 'replication': 3, 'imbalance_cv': 0.40, 'pattern': 'random'},
    {'name': 'rgw-meta-2', 'pgs': 32, 'replication': 3, 'imbalance_cv': 0.35, 'pattern': 'random'},
    {'name': 'rgw-log', 'pgs': 32, 'replication': 3, 'imbalance_cv': 0.30, 'pattern': 'random'},
    {'name': 'misc-1', 'pgs': 64, 'replication': 3, 'imbalance_cv': 0.30, 'pattern': 'random'},
    {'name': 'misc-2', 'pgs': 64, 'replication': 3, 'imbalance_cv': 0.25, 'pattern': 'random'},
    {'name': 'misc-3', 'pgs': 32, 'replication': 3, 'imbalance_cv': 0.35, 'pattern': 'random'},
    {'name': 'misc-4', 'pgs': 16, 'replication': 3, 'imbalance_cv': 0.40, 'pattern': 'random'},
    {'name': 'misc-5', 'pgs': 16, 'replication': 3, 'imbalance_cv': 0.45, 'pattern': 'random'},
]


# Performance benchmark scenarios
PERFORMANCE_SCENARIOS = [
    {
        'name': 'tiny_smoke',
        'description': 'Tiny cluster for smoke testing',
        'params': {
            'num_osds': 10,
            'num_hosts': 2,
            'num_pools': 1,
            'pgs_per_pool': 100,
            'imbalance_cv': 0.25
        }
    },
    {
        'name': 'small_quick',
        'description': 'Small cluster for quick benchmarks',
        'params': {
            'num_osds': 50,
            'num_hosts': 5,
            'num_pools': 2,
            'pgs_per_pool': 500,
            'imbalance_cv': 0.30
        }
    },
    {
        'name': 'medium_standard',
        'description': 'Medium cluster (standard benchmark)',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 5,
            'pgs_per_pool': 2000,
            'imbalance_cv': 0.30
        }
    },
    {
        'name': 'large_production',
        'description': 'Large production-like cluster',
        'params': {
            'num_osds': 500,
            'num_hosts': 50,
            'num_pools': 10,
            'pgs_per_pool': 5000,
            'imbalance_cv': 0.30
        }
    }
]


# Quality benchmark scenarios
QUALITY_SCENARIOS = [
    {
        'name': 'replicated_3_moderate',
        'description': 'Replicated pool with moderate imbalance',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 1,
            'pgs_per_pool': 1024,
            'replication_factor': 3,
            'imbalance_cv': 0.25,
            'imbalance_pattern': 'random'
        }
    },
    {
        'name': 'replicated_3_severe',
        'description': 'Replicated pool with severe imbalance',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 1,
            'pgs_per_pool': 1024,
            'replication_factor': 3,
            'imbalance_cv': 0.40,
            'imbalance_pattern': 'concentrated'
        }
    },
    {
        'name': 'ec_8_3_severe',
        'description': 'EC 8+3 pool with severe imbalance',
        'type': 'ec',
        'params': {
            'k': 8,
            'm': 3,
            'num_pgs': 2048,
            'num_osds': 100,
            'num_hosts': 10,
            'imbalance_type': 'concentrated',
            'imbalance_cv': 0.35
        }
    },
    {
        'name': 'multi_pool_complex',
        'description': 'Multiple pools with varied imbalance',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 5,
            'imbalance_cv': 0.30,
            'imbalance_pattern': 'random'
        }
    },
    {
        'name': 'gradual_imbalance',
        'description': 'Gradual linear imbalance pattern',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 3,
            'pgs_per_pool': 1024,
            'replication_factor': 3,
            'imbalance_cv': 0.30,
            'imbalance_pattern': 'gradual'
        }
    },
    {
        'name': 'bimodal_imbalance',
        'description': 'Bimodal distribution (two groups)',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 3,
            'pgs_per_pool': 1024,
            'replication_factor': 3,
            'imbalance_cv': 0.25,
            'imbalance_pattern': 'bimodal'
        }
    }
]


# Scalability benchmark scenarios
SCALABILITY_SCENARIOS = [
    {
        'name': 'scalability_suite',
        'description': 'Standard scalability test across multiple scales',
        'scales': [
            (10, 100),          # Tiny
            (50, 1000),         # Small
            (100, 5000),        # Medium
            (250, 12500),       # Large
            (500, 25000),       # X-Large
        ]
    }
]


# Stability benchmark scenarios
STABILITY_SCENARIOS = [
    {
        'name': 'stability_small',
        'description': 'Stability test on small cluster',
        'params': {
            'num_osds': 50,
            'num_hosts': 5,
            'num_pools': 2,
            'pgs_per_pool': 500,
            'imbalance_cv': 0.30
        },
        'num_runs': 10
    },
    {
        'name': 'stability_medium',
        'description': 'Stability test on medium cluster',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 5,
            'pgs_per_pool': 1000,
            'imbalance_cv': 0.30
        },
        'num_runs': 10
    }
]


# Production-realistic scenarios (modeled after real clusters)
PRODUCTION_SCENARIOS = [
    {
        'name': 'production_hdd_cluster',
        'description': 'Real-world HDD cluster: 840 OSDs, 28 mixed pools (EC size-20, rep size-3/5), sparse PGs/OSD',
        'type': 'multi_pool',
        'params': {
            'num_osds': 840,
            'num_hosts': 60,
            'pools_config': PRODUCTION_REALISTIC_POOLS,
        }
    },
]


def get_all_scenarios() -> Dict[str, List[Dict[str, Any]]]:
    """Get all available benchmark scenarios organized by category."""
    return {
        'performance': PERFORMANCE_SCENARIOS,
        'quality': QUALITY_SCENARIOS,
        'production': PRODUCTION_SCENARIOS,
        'scalability': SCALABILITY_SCENARIOS,
        'stability': STABILITY_SCENARIOS,
    }


def get_scenario_by_name(name: str) -> Dict[str, Any]:
    """Get a specific scenario by name."""
    for category_scenarios in get_all_scenarios().values():
        for scenario in category_scenarios:
            if scenario['name'] == name:
                return scenario
    raise ValueError(f"Scenario '{name}' not found")


def get_quick_suite() -> List[Dict[str, Any]]:
    """Quick benchmark suite for rapid testing."""
    return [
        PERFORMANCE_SCENARIOS[0],  # tiny_smoke
        PERFORMANCE_SCENARIOS[1],  # small_quick
        QUALITY_SCENARIOS[0],      # replicated_3_moderate
    ]


def get_standard_suite() -> List[Dict[str, Any]]:
    """Standard benchmark suite for regular testing."""
    return [
        PERFORMANCE_SCENARIOS[1],  # small_quick
        PERFORMANCE_SCENARIOS[2],  # medium_standard
        QUALITY_SCENARIOS[0],      # replicated_3_moderate
        QUALITY_SCENARIOS[1],      # replicated_3_severe
        QUALITY_SCENARIOS[3],      # multi_pool_complex
        PRODUCTION_SCENARIOS[0],   # production_hdd_cluster
    ]
