# Installation Guide

> **🤖 AI-Generated Project:** This project was designed, implemented, and documented by Claude Sonnet 4.5, an AI assistant by Anthropic.

## Prerequisites

- **Python 3.8 or higher**
- Access to a Ceph cluster with admin credentials
- `ceph` CLI configured and working

## Verify Prerequisites

### 1. Check Python Version

```bash
python3 --version
# Should show Python 3.8.x or higher
```

### 2. Verify Ceph Access

```bash
ceph -s
ceph osd tree
ceph pg dump pgs -f json | head
```

## Install from Source

```bash
# Clone the repository
git clone https://github.com/yourorg/ceph-primary-pg-balancer.git
cd ceph-primary-pg-balancer

# Install dependencies (Python stdlib only - no external packages)
pip install -r requirements.txt
```

## Install via pip (Future - Not Yet Available)

```bash
# This will be available in a future release
pip install ceph-primary-pg-balancer
```

## Verify Installation

The tool runs as a Python module:

```bash
# Display help and verify installation
python3 -m ceph_primary_balancer.cli --help

# Should show all available options including:
# --dry-run, --target-cv, --weight-osd, --weight-host,
# --weight-pool, --pool, --json-output, --report-output
```

## Troubleshooting Installation

### "No module named ceph_primary_balancer"

**Cause:** Python can't find the module

**Solution:**
```bash
# Make sure you're in the project root directory
cd /path/to/ceph-primary-pg-balancer

# Run with the src directory in the path
PYTHONPATH=src python3 -m ceph_primary_balancer.cli --help

# Or install in development mode (future feature)
```

### "ceph: command not found"

**Cause:** Ceph CLI is not installed or not in PATH

**Solution:**
```bash
# On Debian/Ubuntu
apt-get install ceph-common

# On RHEL/CentOS
yum install ceph-common

# Verify
which ceph
```

## Next Steps

Once installed, see the [Usage Guide](USAGE.md) for command examples and workflows.
