# Development Guide

> **🤖 AI-Generated Project:** This project was designed, implemented, and documented by Claude Sonnet 4.5, an AI assistant by Anthropic. All code, architecture, documentation, and tests were AI-generated through iterative collaboration with human guidance.

## Setup Development Environment

​```bash
git clone https://github.com/yourorg/ceph-primary-pg-balancer.git
cd ceph-primary-pg-balancer
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
​```

## Running Tests

​```bash
pytest tests/
pytest tests/ -v --cov=src/
​```

## Code Style

​```bash
black src/ tests/
flake8 src/ tests/
mypy src/
​```

## Adding New Features

1. Update technical-specification.md with specification
2. Write tests first
3. Implement feature
4. Update USAGE.md
5. Add entry to CHANGELOG.md

## Mock Data for Testing

Sample Ceph outputs are in `tests/fixtures/`.
```

---

## Summary: Recommended Structure
```
ceph-primary-pg-balancer/
├── README.md                      # Start here
├── LICENSE
├── CHANGELOG.md
├── requirements.txt
├── requirements-dev.txt
│
├── docs/
│   ├── technical-specification.md # Complete technical design
│   ├── INSTALLATION.md
│   ├── USAGE.md
│   ├── MVP-USAGE.md               # Historical (v0.1.0)
│   ├── TROUBLESHOOTING.md
│   ├── DEVELOPMENT.md
│   ├── PHASE1-SUMMARY.md          # v0.2.0
│   └── PHASE3-SUMMARY.md          # v0.4.0
│
├── src/
│   └── ceph_primary_balancer/
│       ├── __init__.py
│       ├── cli.py                 # Main entry point
│       ├── models.py
│       ├── collector.py
│       ├── analyzer.py
│       ├── optimizer.py
│       ├── scorer.py
│       ├── script_generator.py
│       ├── exporter.py            # v0.4.0
│       └── reporter.py            # v0.4.0
│
├── tests/
│   ├── fixtures/                  # Sample Ceph JSON outputs
│   └── ...
│
└── examples/
    ├── sample_output.txt
    └── sample_script.sh
