"""
Ceph Primary PG Balancer

Balance primary PG assignments across Ceph OSDs, hosts, and pools using
ceph osd pg-upmap-primary. Zero data movement.

This entire codebase — architecture, algorithms, tests, and documentation —
was designed and written by Claude, an AI assistant by Anthropic.
Human developers provide direction and review.
"""

__version__ = "1.5.0"

# Package-level imports will be added as modules are implemented
__all__ = ["__version__"]
