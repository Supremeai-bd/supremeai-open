"""
Backward compatibility bridge: re-export all from multicloud_quota_monitor.
Preserves legacy imports for 'backend.agents.devops.cloud_watchman'.
"""

from agents.devops.multicloud_quota_monitor import (  # noqa: F401
    AlertManager,
    AnomalyDetector,
    AnomalyReport,
    CloudWatchman,
    FirebaseMonitor,
    GCPMonitor,
    MetricSnapshot,
    MultiCloudQuotaMonitor,
    MulticloudQuotaMonitor,
    VercelMonitor,
    main,
)

__all__ = [
    "AlertManager",
    "AnomalyDetector",
    "AnomalyReport",
    "CloudWatchman",
    "FirebaseMonitor",
    "GCPMonitor",
    "MetricSnapshot",
    "MultiCloudQuotaMonitor",
    "MulticloudQuotaMonitor",
    "VercelMonitor",
    "main",
]

if __name__ == "__main__":
    main()
