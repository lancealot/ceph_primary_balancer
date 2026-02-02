# Usage Guide

## Basic Analysis (Dry Run)

​```bash
python ceph_primary_balancer.py --dry-run
​```

## Generate Rebalancing Script

​```bash
python ceph_primary_balancer.py --output-dir ./output/
​```

## Customize Optimization Weights

Prioritize host balance over OSD balance:

​```bash
python ceph_primary_balancer.py --weight-osd 0.3 --weight-host 0.5 --weight-pool 0.2
​```

## Limit Number of Changes

​```bash
python ceph_primary_balancer.py --max-changes 100
​```

## Example Workflow

1. Run analysis to understand current state
2. Review proposed changes
3. Apply script in maintenance window
4. Re-run analysis to verify improvement

## Interpreting Results

| CV Range | Meaning |
|----------|---------|
| < 10%    | Excellent |
| 10-20%   | Acceptable |
| > 30%    | Needs attention |
