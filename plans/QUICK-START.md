# MVP Quick Start Guide

## What We're Building

A minimal viable product (MVP) of the Ceph Primary PG Balancer that:
- Analyzes OSD-level primary PG distribution
- Identifies imbalanced OSDs
- Generates executable rebalancing scripts
- Focuses on core functionality only

## Project Structure

```
ceph_primary_balancer/
├── src/ceph_primary_balancer/
│   ├── models.py            # Data classes (PGInfo, OSDInfo, etc.)
│   ├── collector.py         # Fetch data from Ceph CLI
│   ├── analyzer.py          # Calculate statistics
│   ├── optimizer.py         # Greedy balancing algorithm
│   ├── script_generator.py  # Generate bash scripts
│   └── cli.py               # Command-line interface
├── tests/
│   ├── fixtures/            # Mock Ceph data
│   └── test_integration.py  # Integration test
├── requirements.txt         # Python dependencies
├── .gitignore
└── docs/
    └── MVP-USAGE.md
```

## Implementation Order

1. **Setup** → Create project structure, `.gitignore`, `requirements.txt`
2. **Models** → Define data classes in `models.py`
3. **Collection** → Implement Ceph data fetching in `collector.py`
4. **Analysis** → Build statistics functions in `analyzer.py`
5. **Optimization** → Develop greedy algorithm in `optimizer.py`
6. **Script Gen** → Create bash script generator in `script_generator.py`
7. **CLI** → Wire everything together in `cli.py`
8. **Testing** → Create mock data and integration test
9. **Error Handling** → Add basic validation
10. **Documentation** → Write MVP usage guide

## Key Decisions

| Aspect | MVP Choice | Why |
|--------|-----------|-----|
| Scope | OSD-level balancing only | Simplest, most valuable feature |
| Algorithm | Greedy variance reduction | Fast, predictable, good enough |
| Dependencies | Python stdlib only | Minimize complexity |
| Testing | Integration test with mocks | Validate end-to-end behavior |
| Output | Terminal + bash script | Sufficient for v1 |

## Success Criteria

✅ MVP is complete when:
- Tool analyzes real Ceph cluster
- Generates valid `pg-upmap-primary` commands
- Demonstrably reduces OSD variance
- Script executes without errors
- Basic documentation exists

## Estimated Effort

- **Total Lines of Code:** ~590
- **Number of Files:** 12
- **Core Modules:** 6 Python files
- **Dependencies:** None (stdlib only)

## After MVP

Future enhancements:
- Host-level balancing
- Pool-level balancing  
- Multi-dimensional scoring
- JSON export
- Advanced CLI options
- Comprehensive test suite
- PyPI packaging

## Getting Started

1. Review [`mvp-implementation-plan.md`](mvp-implementation-plan.md) for detailed specs
2. Check [`mvp-architecture.md`](mvp-architecture.md) for system design
3. Implement modules in order (1-10 above)
4. Test with mock data, then real cluster
5. Validate improvement and document limitations

## Commands to Run

```bash
# During development
python -m ceph_primary_balancer.cli --dry-run

# Generate script
python -m ceph_primary_balancer.cli --output ./rebalance.sh

# Apply changes
./rebalance.sh
```
