# Installation

## Prerequisites

- Python 3.8 or higher
- Access to a Ceph cluster with admin credentials
- `ceph` CLI configured and working

## Verify Ceph Access

​```bash
ceph -s
ceph pg dump pgs -f json | head
​```

## Install from Source

​```bash
git clone https://github.com/yourorg/ceph-primary-pg-balancer.git
cd ceph-primary-pg-balancer
pip install -r requirements.txt
​```

## Install via pip (if published)

​```bash
pip install ceph-primary-pg-balancer
​```

## Verify Installation

​```bash
python ceph_primary_balancer.py --help
​```
