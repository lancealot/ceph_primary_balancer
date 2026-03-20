# Troubleshooting Guide

This guide covers common issues and solutions for the Ceph Primary PG Balancer.

---

## Installation & Setup Issues

### "No module named ceph_primary_balancer"

**Cause:** Python can't find the module in the Python path.

**Solution:**
```bash
# Make sure you're in the project root directory
cd /path/to/ceph-primary-pg-balancer

# Run with the src directory in the path
PYTHONPATH=src python3 -m ceph_primary_balancer.cli --help

# Or add src to PYTHONPATH permanently
export PYTHONPATH=/path/to/ceph-primary-pg-balancer/src:$PYTHONPATH
```

### "ceph: command not found"

**Cause:** Ceph CLI is not installed or not in PATH.

**Solution:**
```bash
# On Debian/Ubuntu
apt-get install ceph-common

# On RHEL/CentOS
yum install ceph-common

# Verify installation
which ceph
ceph --version
```

### "Permission denied" running Ceph commands

**Cause:** Missing Ceph admin credentials or insufficient permissions.

**Solution:**
```bash
# Set Ceph configuration environment variables
export CEPH_CONF=/etc/ceph/ceph.conf
export CEPH_KEYRING=/etc/ceph/ceph.client.admin.keyring

# Or specify in the command
ceph -c /etc/ceph/ceph.conf -k /etc/ceph/ceph.client.admin.keyring osd tree

# Check current authentication
ceph auth list | grep client.admin

# Verify you have the necessary permissions
ceph osd tree
ceph osd dump
```

---

## Data Collection Issues

### "Error collecting cluster data"

**Cause:** Network connectivity issues, cluster problems, or JSON parsing errors.

**Debugging Steps:**
```bash
# 1. Test basic connectivity
ceph health
ceph status

# 2. Test the specific commands the tool uses
ceph osd dump --format=json
ceph osd tree --format=json
ceph pg dump pgs --format=json

# 3. Check for JSON validity
ceph osd dump --format=json | python3 -m json.tool

# 4. Check cluster health
ceph -s
```

**Common Causes:**
- Cluster is down or unhealthy
- Network latency or timeouts
- Malformed JSON output from Ceph CLI
- Insufficient permissions

### "Error parsing pool information"

**Cause:** Unexpected format from `ceph osd pool ls detail` command.

**Solution:**
```bash
# Check pool list output
ceph osd pool ls detail

# Verify pools exist
ceph osd lspools

# If specific pool is missing
ceph osd pool ls | grep <pool_name>
```

---

## Optimization Issues

### "No valid swaps found"

**Cause:** Overloaded OSDs don't share any PGs with underloaded OSDs, or placement constraints prevent optimization.

**Solution:**
```bash
# 1. Check current distribution
python3 -m ceph_primary_balancer.cli --dry-run

# 2. Review PG acting sets
ceph pg dump pgs | less

# 3. Run the standard upmap balancer first to improve PG distribution
ceph osd set-require-min-compat-client luminous
ceph balancer mode upmap
ceph balancer on

# Wait for balancing to complete, then retry
python3 -m ceph_primary_balancer.cli --dry-run
```

**Why this happens:**
- PG placement constraints limit which OSDs can be primaries
- Small clusters with limited PG overlap
- Recent cluster expansion (new OSDs don't share PGs with old ones yet)

### "Cluster already balanced"

**Output Example:**
```
Cluster already balanced (CV = 8.5%)
Target CV of 10.0% already achieved - no optimization needed
```

**This is good!** Your cluster is already well-balanced.

**If you want even tighter balance:**
```bash
# Use a more aggressive target CV
python3 -m ceph_primary_balancer.cli --target-cv 0.05 --dry-run
```

**Understanding CV thresholds:**
- < 10%: Excellent balance (current goal)
- 10-20%: Acceptable balance
- 20-30%: Poor balance
- > 30%: Severe imbalance

### "Weights must sum to 1.0"

**Cause:** Invalid weight configuration for multi-dimensional optimization.

**Error Example:**
```
Error: Weights must sum to 1.0 (got 1.2)
```

**Solution:**
```bash
# Correct: weights sum to 1.0
python3 -m ceph_primary_balancer.cli \
  --weight-osd 0.5 \
  --weight-host 0.3 \
  --weight-pool 0.2

# Incorrect: weights sum to 1.2
python3 -m ceph_primary_balancer.cli \
  --weight-osd 0.6 \
  --weight-host 0.4 \
  --weight-pool 0.2
```

---

## Script Execution Issues

### Script fails mid-execution

**Cause:** PG state changed between analysis and execution, or OSDs went down.

**Output Example:**
```
[ 42/45] 8.3f         -> OSD.15   FAILED
```

**Solution:**
```bash
# 1. Check the failed PG
ceph pg dump | grep 8.3f

# 2. Check OSD status
ceph osd tree | grep -E "(down|out)"

# 3. Regenerate the script with current state
python3 -m ceph_primary_balancer.cli --output ./rebalance_new.sh

# 4. A few failures out of many is usually acceptable
```

**When to worry:**
- Many failures (>10%)
- Same OSD failing repeatedly
- Cluster health degrading

**When it's okay:**
- A few isolated failures (<5%)
- Failures on OSDs that recently went down
- PGs that are currently peering/recovering

### "Error: Invalid pool ID"

**Cause:** Specified pool doesn't exist or ID is incorrect.

**Solution:**
```bash
# List all pools with IDs
ceph osd pool ls detail

# Or get pool ID by name
ceph osd lspools | grep <pool_name>

# Use correct pool ID
python3 -m ceph_primary_balancer.cli --pool 3 --dry-run
```

---

## JSON Export Issues
### "Error writing JSON output"

**Cause:** Insufficient permissions, invalid path, or disk full.

**Solution:**
```bash
# Check disk space
df -h .

# Check directory permissions
ls -la /path/to/output/

# Use a directory you own
python3 -m ceph_primary_balancer.cli \
  --json-output ~/analysis.json

# Or create the directory first
mkdir -p ./output
python3 -m ceph_primary_balancer.cli \
  --json-output ./output/analysis.json
```

### "JSON file is empty or invalid"

**Cause:** Script was interrupted or encountered an error during export.

**Solution:**
```bash
# Validate JSON file
python3 -m json.tool < analysis.json

# Check file size
ls -lh analysis.json

# Re-run with verbose error output
python3 -m ceph_primary_balancer.cli \
  --json-output ./analysis.json 2>&1 | tee output.log
```

### "Cannot parse JSON output"

**Cause:** Trying to parse JSON from a different schema version or corrupted file.

**Solution:**
```bash
# Check schema version
cat analysis.json | python3 -c "import json, sys; print(json.load(sys.stdin)['metadata']['schema_version'])"

# Expected: "2.0"

# If schema mismatch, regenerate with current version
python3 -m ceph_primary_balancer.cli \
  --json-output ./analysis_new.json
```

---

## Markdown Report Issues
### "Report file not generated"

**Cause:** Missing `--report-output` argument or permission issues.

**Solution:**
```bash
# Ensure you specify output path
python3 -m ceph_primary_balancer.cli \
  --report-output ./report.md

# Check permissions
ls -la . | grep report.md

# Try alternative location
python3 -m ceph_primary_balancer.cli \
  --report-output ~/report.md
```

### "Markdown formatting issues"

**Cause:** Report viewers may render markdown differently.

**Solution:**
- Use a proper markdown viewer (not plain text editor)
- Try GitHub-flavored markdown viewers
- Convert to HTML if needed:
  ```bash
  # Using pandoc (if installed)
  pandoc report.md -o report.html
  ```

---

## Performance Issues

### High memory usage

**Cause:** Very large cluster (10,000+ PGs).

**Solution:**
```bash
# Process pools individually to reduce memory footprint
for pool_id in $(ceph osd lspools | awk '{print $1}'); do
  python3 -m ceph_primary_balancer.cli \
    --pool $pool_id \
    --output ./rebalance_pool${pool_id}.sh
done
```

**Memory usage guidelines:**
- <1000 PGs: <50 MB
- 1000-5000 PGs: 50-200 MB
- 5000-10000 PGs: 200-500 MB
- >10000 PGs: 500 MB+ (use pool filtering)

### Slow optimization

**Cause:** Large clusters or complex optimization scenarios.

**Factors affecting speed:**
- Number of PGs
- Number of OSDs
- Degree of imbalance
- Number of optimization dimensions

**Solutions:**
```bash
# 1. Use less aggressive target CV (fewer iterations)
python3 -m ceph_primary_balancer.cli --target-cv 0.15

# 2. Optimize pools individually
python3 -m ceph_primary_balancer.cli --pool 3

# 3. Simplify optimization (OSD-only)
python3 -m ceph_primary_balancer.cli \
  --weight-osd 1.0 \
  --weight-host 0.0 \
  --weight-pool 0.0
```

**Typical optimization times:**
- Small cluster (<500 PGs): <10 seconds
- Medium cluster (500-2000 PGs): 10-60 seconds
- Large cluster (2000-10000 PGs): 1-5 minutes
- Very large cluster (>10000 PGs): 5-15 minutes

---

## Module Import Errors

### "ImportError: cannot import name 'JSONExporter'"

**Cause:** Running older version or corrupted installation.

**Solution:**
```bash
# Check version
python3 -c "from ceph_primary_balancer import __version__; print(__version__)"

# Verify all modules exist
ls -la src/ceph_primary_balancer/*.py
```

### "ModuleNotFoundError: No module named 'ceph_primary_balancer.reporter'"

**Cause:** Incomplete installation or outdated code.

**Solution:**
```bash
# Update to latest version
git pull

# Verify reporter module exists
ls -la src/ceph_primary_balancer/reporter.py
```

---

## Pool Filtering Issues
### "Pool not found"

**Cause:** Invalid pool ID or pool was deleted.

**Solution:**
```bash
# List all pools
ceph osd lspools

# Get detailed pool information
ceph osd pool ls detail

# Use correct pool ID (not name)
python3 -m ceph_primary_balancer.cli --pool 3  # Correct (ID)
# NOT: --pool rbd  # Incorrect (name not supported)
```

### "No PGs in specified pool"

**Cause:** Pool exists but has no PGs (empty pool).

**Solution:**
```bash
# Check PG count for pool
ceph osd pool get <pool_name> pg_num

# If pg_num is 0, pool is empty
# Either add data to pool or optimize a different pool
```

---

## Weight Configuration Issues
### "Unexpected optimization results"

**Cause:** Weight configuration doesn't match your optimization goals.

**Understanding weights:**
```bash
# Default (balanced three-dimensional)
--weight-osd 0.5 --weight-host 0.3 --weight-pool 0.2

# OSD-focused (minimize disk hotspots)
--weight-osd 0.7 --weight-host 0.2 --weight-pool 0.1

# Host-focused (minimize network bottlenecks)
--weight-osd 0.2 --weight-host 0.6 --weight-pool 0.2

# Pool-focused (workload-specific balance)
--weight-osd 0.2 --weight-host 0.2 --weight-pool 0.6

# OSD-only (like MVP, ignore hosts and pools)
--weight-osd 1.0 --weight-host 0.0 --weight-pool 0.0
```

**Recommendation:** Start with defaults and adjust based on your specific needs.

---

## Common Error Messages

### "EPERM: Operation not permitted"

**Solution:** Run with proper Ceph admin credentials.

### "EINVAL: Invalid argument"

**Solution:** Check command syntax and argument values.

### "Connection refused"

**Solution:** Verify Ceph monitor connectivity.

### "Timeout waiting for response"

**Solution:** Check network latency to Ceph cluster.

---

## Debug Mode & Logging

### Enable verbose output (future feature)

Currently, detailed logging is not available. For debugging:

```bash
# Capture all output
python3 -m ceph_primary_balancer.cli --dry-run 2>&1 | tee debug.log

# Use JSON output for detailed analysis
python3 -m ceph_primary_balancer.cli \
  --json-output analysis.json \
  2>&1 | tee debug.log

# Examine JSON for detailed state
python3 -m json.tool < analysis.json | less
```

---

## Getting Help

### Before reporting an issue:

1. **Check this guide** for known issues
2. **Verify your version:**
   ```bash
   python3 -c "from ceph_primary_balancer import __version__; print(__version__)"
   ```
3. **Test basic Ceph access:**
   ```bash
   ceph -s
   ceph osd tree
   ceph pg dump pgs -f json | head
   ```
4. **Try a dry run:**
   ```bash
   python3 -m ceph_primary_balancer.cli --dry-run
   ```

### Information to include in bug reports:

- Tool version
- Ceph version (`ceph --version`)
- Cluster size (number of OSDs, PGs)
- Command that failed
- Complete error message
- Output of `ceph -s`

### Related Documentation:

- [Installation Guide](INSTALLATION.md)
- [Usage Guide](USAGE.md)
