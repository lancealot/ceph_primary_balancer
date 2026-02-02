# Troubleshooting

## "No valid swaps found"

**Cause:** Overloaded OSDs don't share any PGs with underloaded OSDs.

**Solution:** This is a constraint of the acting sets. Consider:
- Running the standard upmap balancer first
- Using primary-affinity as a supplementary approach

## "Permission denied" running Ceph commands

**Cause:** Missing Ceph admin credentials.

**Solution:**
​```bash
export CEPH_CONF=/etc/ceph/ceph.conf
export CEPH_KEYRING=/etc/ceph/ceph.client.admin.keyring
​```

## Script fails mid-execution

**Cause:** PG state changed between analysis and execution.

**Solution:** Re-run the analysis tool to generate a fresh script.

## High memory usage

**Cause:** Very large cluster (10,000+ PGs).

**Solution:** Process pools individually using `--pool` filter (future feature).
