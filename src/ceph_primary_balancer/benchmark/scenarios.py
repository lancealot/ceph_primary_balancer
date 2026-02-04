"""
Standard test scenarios for benchmarking.

This module defines standard benchmark scenarios covering different
cluster configurations, scales, and imbalance patterns.
"""

from typing import Dict, List, Any


# Standard dataset definitions
DATASET_SMALL_BALANCED = {
    'name': 'small_balanced',
    'description': 'Small balanced cluster for quick testing',
    'num_osds': 10,
    'num_hosts': 2,
    'num_pools': 1,
    'pgs_per_pool': 100,
    'replication_factor': 3,
    'imbalance_cv': 0.05,
    'imbalance_pattern': 'balanced'
}

DATASET_SMALL_IMBALANCED = {
    'name': 'small_imbalanced',
    'description': 'Small imbalanced cluster',
    'num_osds': 10,
    'num_hosts': 2,
    'num_pools': 1,
    'pgs_per_pool': 100,
    'replication_factor': 3,
    'imbalance_cv': 0.35,
    'imbalance_pattern': 'random'
}

DATASET_MEDIUM_REPLICATED = {
    'name': 'medium_replicated',
    'description': 'Medium-scale replicated pool',
    'num_osds': 100,
    'num_hosts': 10,
    'num_pools': 3,
    'pgs_per_pool': 1024,
    'replication_factor': 3,
    'imbalance_cv': 0.25,
    'imbalance_pattern': 'random'
}

DATASET_MEDIUM_EC = {
    'name': 'medium_ec',
    'description': 'Medium-scale erasure-coded pool (8+3)',
    'type': 'ec',
    'k': 8,
    'm': 3,
    'num_pgs': 2048,
    'num_osds': 100,
    'num_hosts': 10,
    'imbalance_type': 'concentrated',
    'imbalance_cv': 0.30
}

DATASET_LARGE_MULTI_POOL = {
    'name': 'large_multi_pool',
    'description': 'Large-scale multi-pool configuration',
    'num_osds': 500,
    'num_hosts': 50,
    'num_pools': 10,
    'pgs_per_pool': 5000,
    'replication_factor': 3,
    'imbalance_cv': 0.30,
    'imbalance_pattern': 'random'
}

DATASET_XLARGE_STRESS = {
    'name': 'xlarge_stress',
    'description': 'Extra-large cluster for stress testing',
    'num_osds': 1000,
    'num_hosts': 100,
    'num_pools': 20,
    'pgs_per_pool': 5000,
    'replication_factor': 3,
    'imbalance_cv': 0.35,
    'imbalance_pattern': 'random'
}


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


# Edge case scenarios
EDGE_CASE_SCENARIOS = [
    {
        'name': 'minimal_cluster',
        'description': 'Minimal viable cluster (3 OSDs)',
        'params': {
            'num_osds': 3,
            'num_hosts': 1,
            'num_pools': 1,
            'pgs_per_pool': 10,
            'replication_factor': 3,
            'imbalance_cv': 0.30
        }
    },
    {
        'name': 'single_host',
        'description': 'All OSDs on single host',
        'params': {
            'num_osds': 20,
            'num_hosts': 1,
            'num_pools': 2,
            'pgs_per_pool': 100,
            'replication_factor': 3,
            'imbalance_cv': 0.30
        }
    },
    {
        'name': 'worst_case_imbalance',
        'description': 'Extreme worst-case imbalance',
        'params': {
            'num_osds': 50,
            'num_hosts': 5,
            'num_pools': 1,
            'pgs_per_pool': 500,
            'replication_factor': 3,
            'imbalance_cv': 0.50,
            'imbalance_pattern': 'worst_case'
        }
    },
    {
        'name': 'already_balanced',
        'description': 'Already well-balanced cluster',
        'params': {
            'num_osds': 100,
            'num_hosts': 10,
            'num_pools': 3,
            'pgs_per_pool': 1000,
            'replication_factor': 3,
            'imbalance_cv': 0.05,
            'imbalance_pattern': 'balanced'
        }
    }
]


def get_all_scenarios() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all available benchmark scenarios organized by category.
    
    Returns:
        Dict mapping category name to list of scenarios
    """
    return {
        'performance': PERFORMANCE_SCENARIOS,
        'quality': QUALITY_SCENARIOS,
        'scalability': SCALABILITY_SCENARIOS,
        'stability': STABILITY_SCENARIOS,
        'edge_cases': EDGE_CASE_SCENARIOS
    }


def get_scenario_by_name(name: str) -> Dict[str, Any]:
    """
    Get a specific scenario by name.
    
    Args:
        name: Scenario name
        
    Returns:
        Scenario dict
        
    Raises:
        ValueError: If scenario name not found
    """
    all_scenarios = get_all_scenarios()
    
    for category_scenarios in all_scenarios.values():
        for scenario in category_scenarios:
            if scenario['name'] == name:
                return scenario
    
    raise ValueError(f"Scenario '{name}' not found")


def get_quick_suite() -> List[Dict[str, Any]]:
    """
    Get a quick benchmark suite for rapid testing.
    
    Returns:
        List of scenarios (small/fast only)
    """
    return [
        PERFORMANCE_SCENARIOS[0],  # tiny_smoke
        PERFORMANCE_SCENARIOS[1],  # small_quick
        QUALITY_SCENARIOS[0],      # replicated_3_moderate
    ]


def get_standard_suite() -> List[Dict[str, Any]]:
    """
    Get standard benchmark suite for regular testing.
    
    Returns:
        List of scenarios (balanced coverage)
    """
    return [
        PERFORMANCE_SCENARIOS[1],  # small_quick
        PERFORMANCE_SCENARIOS[2],  # medium_standard
        QUALITY_SCENARIOS[0],      # replicated_3_moderate
        QUALITY_SCENARIOS[1],      # replicated_3_severe
        QUALITY_SCENARIOS[3],      # multi_pool_complex
    ]


def get_comprehensive_suite() -> List[Dict[str, Any]]:
    """
    Get comprehensive benchmark suite (all scenarios).
    
    Returns:
        List of all scenarios
    """
    all_scenarios = get_all_scenarios()
    suite = []
    
    for category_scenarios in all_scenarios.values():
        suite.extend(category_scenarios)
    
    return suite
