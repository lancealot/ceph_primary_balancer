# Configuration File Examples

This directory contains example configuration files for common use cases with the Ceph Primary PG Balancer.

## Usage

Use configuration files with the `--config` option:

```bash
ceph-primary-balancer --config config-examples/balanced.json
```

Configuration values can be overridden by CLI arguments:

```bash
# Use production-safe config but override max-changes
ceph-primary-balancer --config config-examples/production-safe.json --max-changes 100
```

## Precedence

Configuration values follow this precedence (highest to lowest):
1. **CLI Arguments** - Explicit command-line options
2. **Configuration File** - Values from `--config` file
3. **Built-in Defaults** - Default values in the tool

## Available Configurations

> **New in v1.2.0:** Configurable optimization levels allow you to enable/disable specific dimensions (OSD, HOST, POOL) for improved performance. See optimization strategy examples below.

### Standard Configurations

#### balanced.json (Default Strategy - Full 3D)
**Use Case:** General-purpose optimization balancing all three dimensions equally

**Characteristics:**
- Equal weight distribution: OSD (50%), Host (30%), Pool (20%)
- Target CV: 10%
- Batch size: 50 commands
- No change limit (unlimited)

**Best For:**
- Initial cluster optimization
- General-purpose rebalancing
- Clusters without specific hotspot patterns

---

### osd-focused.json (Disk I/O Optimization)
**Use Case:** Prioritize individual OSD balance to eliminate disk I/O hotspots

**Characteristics:**
- OSD-heavy weights: OSD (70%), Host (20%), Pool (10%)
- Aggressive target CV: 5%
- Large batch size: 100 commands
- Auto-exports JSON and markdown reports

**Best For:**
- Clusters with high disk I/O contention
- Scenarios where disk throughput is the bottleneck
- NVMe-based clusters with fast disks

---

### host-focused.json (Network Optimization)
**Use Case:** Prioritize host-level balance to prevent network bottlenecks

**Characteristics:**
- Host-heavy weights: OSD (20%), Host (60%), Pool (20%)
- Target CV: 10%
- Moderate batch size: 50 commands
- Auto-exports JSON and markdown reports

**Best For:**
- Clusters with network saturation issues
- High-throughput workloads (RGW, RBD)
- Preventing individual host overload

---

### production-safe.json (Conservative Approach)
**Use Case:** Gradual, safe rebalancing for production environments

**Characteristics:**
- Balanced weights: OSD (50%), Host (30%), Pool (20%)
- Conservative target CV: 15%
- Limited changes: 50 maximum per run
- Small batch size: 25 commands
- Organized output directory with timestamp
- Auto-exports all reports

**Best For:**
- Production clusters requiring caution
- First-time optimization runs
- Testing and validation workflows
- Incremental rebalancing over multiple runs

---

### Optimization Strategy Configurations (v1.2.0+)

These configurations demonstrate the new `enabled_levels` feature, allowing you to selectively optimize specific dimensions for improved performance.

#### osd-only-fast.json (OSD-Only Strategy)
**Use Case:** Fastest optimization focusing only on individual OSD balance

**Characteristics:**
- **Performance:** ~3× faster than Full 3D optimization
- **Memory:** ~0.3× of Full 3D
- Enabled levels: OSD only
- Weight: OSD (100%)
- Target CV: 10%
- Large batch size: 100 commands

**Best For:**
- Quick fixes and rapid testing
- Small clusters (<50 OSDs)
- Development environments
- Single-host clusters where host balance is irrelevant
- Fast iteration during troubleshooting

---

#### osd-host-balanced.json (OSD+HOST Strategy)
**Use Case:** Balanced optimization for multi-host clusters without pool concerns

**Characteristics:**
- **Performance:** ~1.7× faster than Full 3D optimization
- **Memory:** ~0.5× of Full 3D
- Enabled levels: OSD and HOST
- Weights: OSD (60%), Host (40%)
- Target CV: 10%
- Auto-exports JSON and markdown reports

**Best For:**
- Multi-host production clusters
- Single-pool clusters where pool balance is not needed
- Balance between performance and comprehensiveness
- Network and disk I/O optimization

---

#### network-focused.json (HOST+POOL Strategy)
**Use Case:** Network-focused optimization prioritizing host and pool balance

**Characteristics:**
- **Performance:** ~2.5× faster than Full 3D optimization
- **Memory:** ~0.4× of Full 3D
- Enabled levels: HOST and POOL
- Weights: Host (70%), Pool (30%)
- Target CV: 10%
- Auto-exports JSON and markdown reports

**Best For:**
- Network-constrained clusters
- Scenarios where network is the bottleneck (not disk)
- Multi-pool clusters with host saturation issues
- RGW or RBD workloads with high network throughput

---

## Configuration File Format

### JSON Structure

```json
{
  "optimization": {
    "target_cv": 0.10,          // Target coefficient of variation
    "max_changes": null,         // Maximum swaps (null = unlimited)
    "max_iterations": 10000,     // Maximum optimization iterations
    "enabled_levels": ["osd", "host", "pool"]  // v1.2.0+: Dimensions to optimize
  },
  "scoring": {
    "weights": {
      "osd": 0.5,               // OSD-level weight (must sum to 1.0)
      "host": 0.3,              // Host-level weight
      "pool": 0.2               // Pool-level weight
    }
  },
  "output": {
    "directory": null,           // Output directory (null = current dir)
    "json_export": false,        // Auto-generate JSON export
    "markdown_report": false,    // Auto-generate markdown report
    "script_name": "rebalance_primaries.sh"  // Script filename
  },
  "script": {
    "batch_size": 50,           // Commands per batch
    "health_check": true,        // Enable health checks in script
    "generate_rollback": true,   // Generate rollback script
    "organized_by_pool": false   // Organize commands by pool
  },
  "verbosity": {
    "verbose": false,            // Enable verbose output
    "quiet": false               // Enable quiet mode
  }
}
```

### YAML Format (Optional)

You can also use YAML format if PyYAML is installed:

```yaml
optimization:
  target_cv: 0.10
  max_changes: null
  max_iterations: 10000
  enabled_levels: ["osd", "host", "pool"]  # v1.2.0+: Dimensions to optimize

scoring:
  weights:
    osd: 0.5
    host: 0.3
    pool: 0.2

output:
  directory: null
  json_export: false
  markdown_report: false
  script_name: rebalance_primaries.sh

script:
  batch_size: 50
  health_check: true
  generate_rollback: true
  organized_by_pool: false

verbosity:
  verbose: false
  quiet: false
```

## Creating Custom Configurations

1. Copy one of the example files as a starting point
2. Modify values to suit your use case
3. Test with `--dry-run` first:
   ```bash
   ceph-primary-balancer --config my-config.json --dry-run
   ```
4. Review the proposed changes
5. Execute when satisfied

## Weight Tuning Guidelines

### When to Increase OSD Weight
- High disk I/O variance across OSDs
- Individual OSDs are performance bottlenecks
- Disk-bound workloads

### When to Increase Host Weight
- Network saturation on specific hosts
- Host-level CPU or memory bottlenecks
- Large host count with uneven distribution

### When to Increase Pool Weight
- Multi-pool clusters with different workload types
- Pool-specific performance issues
- Need to balance within specific pools

**Important:** Weights must always sum to 1.0.

### Choosing Optimization Levels (v1.2.0+)

The `enabled_levels` option allows you to selectively enable optimization dimensions:

**Available Strategies:**
- `["osd"]` - OSD-only (fastest, ~3× speedup)
- `["osd", "host"]` - OSD+HOST (balanced, ~1.7× speedup)
- `["osd", "pool"]` - OSD+POOL (~1.4× speedup)
- `["host", "pool"]` - HOST+POOL (network-focused, ~2.5× speedup)
- `["osd", "host", "pool"]` - Full 3D (default, comprehensive)

**When to Use Fewer Dimensions:**
- **Single-host clusters:** Use `["osd"]` only
- **Single-pool clusters:** Omit `"pool"` from enabled_levels
- **Network bottlenecks:** Use `["host", "pool"]`
- **Quick testing:** Use `["osd"]` for fastest results
- **Large clusters:** Consider `["osd", "host"]` for better performance

**Performance vs Comprehensiveness Trade-off:**
- More dimensions = more comprehensive but slower
- Fewer dimensions = faster but may miss cross-dimensional issues
- Choose based on your cluster's specific bottleneck

Use `--optimization-levels` to specify which dimensions to optimize:
```bash
python3 -m ceph_primary_balancer.cli --optimization-levels osd,host
```

## Tips and Best Practices

1. **Start Conservative:** Use `production-safe.json` for first runs
2. **Test with --dry-run:** Always review proposed changes first
3. **Incremental Approach:** Use `max_changes` to limit impact per run
4. **Monitor Results:** Use JSON export to track improvements over time
5. **Adjust Weights:** Tune based on your cluster's specific bottlenecks

## Troubleshooting

### Configuration Not Loading
```bash
# Check for syntax errors
python3 -m json.tool your-config.json
```

### Weights Don't Sum to 1.0
The tool will reject configurations where weights don't sum to 1.0:
```
Error: Weights must sum to 1.0, got 0.95
```

### Invalid Values
Check that:
- `target_cv` is between 0.0 and 1.0 (typically 0.05-0.20)
- `max_changes` is positive or null
- `batch_size` is positive
- `verbose` and `quiet` are not both true
- `enabled_levels` contains only valid values: "osd", "host", "pool"
- At least one level is enabled

## See Also

- [USAGE.md](../docs/USAGE.md) - Complete usage guide
- [technical-specification.md](../docs/technical-specification.md) - Technical details
- [README.md](../README.md) - Project overview
