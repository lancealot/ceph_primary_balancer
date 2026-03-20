"""
Ceph Primary PG Balancer

Balance primary PG assignments across Ceph OSDs, hosts, and pools using
ceph osd pg-upmap-primary. Zero data movement.
"""

__version__ = "1.5.0"

__all__ = ["__version__"]
