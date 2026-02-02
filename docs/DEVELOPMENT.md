# Development Guide

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

1. Update DESIGN.md with specification
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
│   ├── DESIGN.md                  # ← Rename your spec to this
│   ├── INSTALLATION.md
│   ├── USAGE.md
│   ├── TROUBLESHOOTING.md
│   └── DEVELOPMENT.md
│
├── src/
│   └── ceph_primary_balancer/
│       ├── __init__.py
│       ├── main.py
│       └── ...
│
├── tests/
│   ├── fixtures/                  # Sample Ceph JSON outputs
│   └── ...
│
└── examples/
    ├── sample_output.txt
    └── sample_script.sh
