"""
Unit Tests for SupremeAI Infrastructure Guardian
Validates multi-satellite watchdog, quota monitor thresholds, and DR rollback automations.
"""

import unittest

from infra.dr.automated_rollback import AutomatedRollback, RollbackStatus
from infra.ops.health_watchdog import (
    DEFAULT_ENDPOINTS,
    FederationWatchdog,
)
from infra.ops.quota_monitor import QuotaMonitor


class TestInfraWatchdog(unittest.TestCase):
    """Test suite for FederationWatchdog."""

    def test_watchdog_init_default_endpoints(self):
        watchdog = FederationWatchdog()
        self.assertEqual(len(watchdog.endpoints), len(DEFAULT_ENDPOINTS))
        self.assertIn("mcp-tower-health", watchdog.endpoints)
        self.assertIn("gateway-models", watchdog.endpoints)
        self.assertIn("studio-dashboard", watchdog.endpoints)

    def test_watchdog_healthy_probes(self):
        # Mock probe returning 200 OK
        mock_probe = lambda url: (True, 200, 15.2, None)
        watchdog = FederationWatchdog(probe_fn=mock_probe)

        statuses = watchdog.probe_all()
        for status in statuses.values():
            self.assertTrue(status.healthy)
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.consecutive_failures, 0)
        self.assertEqual(len(watchdog.alerts), 0)

    def test_watchdog_consecutive_failures_triggers_alert(self):
        # Mock probe returning 503 Service Unavailable
        mock_probe = lambda url: (False, 503, 105.0, "Service Unavailable")
        watchdog = FederationWatchdog(failure_threshold=3, probe_fn=mock_probe)

        # Probes 1 and 2: failures increment, no alert yet
        watchdog.probe_endpoint("mcp-tower-health")
        self.assertEqual(watchdog.statuses["mcp-tower-health"].consecutive_failures, 1)
        self.assertEqual(len(watchdog.alerts), 0)

        watchdog.probe_endpoint("mcp-tower-health")
        self.assertEqual(watchdog.statuses["mcp-tower-health"].consecutive_failures, 2)
        self.assertEqual(len(watchdog.alerts), 0)

        # Probe 3: threshold reached, triggers alert
        watchdog.probe_endpoint("mcp-tower-health")
        self.assertEqual(watchdog.statuses["mcp-tower-health"].consecutive_failures, 3)
        self.assertEqual(len(watchdog.alerts), 1)

        alert = watchdog.alerts[0]
        self.assertEqual(alert.satellite_name, "mcp-tower-health")
        self.assertEqual(alert.severity, "HIGH")
        self.assertIn("[SATELLITE_DOWN]", alert.title)

    def test_watchdog_recovery_resets_failure_count(self):
        calls = 0

        def alternating_probe(url):
            nonlocal calls
            calls += 1
            if calls <= 2:
                return (False, 500, 50.0, "Internal Server Error")
            return (True, 200, 10.0, None)

        watchdog = FederationWatchdog(probe_fn=alternating_probe)
        watchdog.probe_endpoint("gateway-models")
        self.assertEqual(watchdog.statuses["gateway-models"].consecutive_failures, 1)

        watchdog.probe_endpoint("gateway-models")
        self.assertEqual(watchdog.statuses["gateway-models"].consecutive_failures, 2)

        # Third probe recovers
        watchdog.probe_endpoint("gateway-models")
        self.assertEqual(watchdog.statuses["gateway-models"].consecutive_failures, 0)
        self.assertTrue(watchdog.statuses["gateway-models"].healthy)

    def test_watchdog_incident_report_generation(self):
        mock_probe = lambda url: (False, 502, 20.0, "Bad Gateway")
        watchdog = FederationWatchdog(failure_threshold=1, probe_fn=mock_probe)
        watchdog.probe_endpoint("studio-dashboard")

        report = watchdog.build_incident_report()
        self.assertIn("Infrastructure Guardian Incident Report", report)
        self.assertIn("studio-dashboard", report)
        self.assertIn("502", report)


class TestQuotaMonitor(unittest.TestCase):
    """Test suite for QuotaMonitor."""

    def setUp(self):
        self.monitor = QuotaMonitor(monthly_budget_minutes=2000.0)

    def test_quota_healthy_usage(self):
        # 100 minutes used over 5 days -> 20 min/day -> 600 min/mo projected
        eval_res = self.monitor.evaluate_usage(
            used_minutes=100.0, days_elapsed=5, days_in_month=30
        )
        self.assertEqual(eval_res.status, "HEALTHY")
        self.assertEqual(eval_res.remaining_minutes, 1900.0)
        self.assertEqual(eval_res.daily_burn_rate, 20.0)
        self.assertEqual(eval_res.projected_month_end_minutes, 600.0)
        self.assertIsNone(eval_res.alert_message)

    def test_quota_warning_and_critical_thresholds(self):
        # Warning threshold (75% of 2000 = 1500)
        warn_eval = self.monitor.evaluate_usage(used_minutes=1550.0, days_elapsed=20)
        self.assertEqual(warn_eval.status, "WARNING")
        self.assertIsNotNone(warn_eval.alert_message)

        # Critical threshold (90% of 2000 = 1800)
        crit_eval = self.monitor.evaluate_usage(used_minutes=1850.0, days_elapsed=20)
        self.assertEqual(crit_eval.status, "CRITICAL")
        self.assertIn("CRITICAL:", crit_eval.alert_message)

        # Exhausted threshold (>= 2000)
        exhaust_eval = self.monitor.evaluate_usage(used_minutes=2050.0, days_elapsed=20)
        self.assertEqual(exhaust_eval.status, "EXHAUSTED")
        self.assertIn("EMERGENCY:", exhaust_eval.alert_message)

    def test_quota_runaway_job_detection(self):
        # Normal runtime (< 600s)
        normal_job = self.monitor.check_job_runtime(
            "matrix-py311", duration_seconds=120.0
        )
        self.assertFalse(normal_job.is_runaway)
        self.assertEqual(normal_job.status, "NORMAL")
        self.assertIsNone(normal_job.recommendation)

        # Runaway runtime (> 600s)
        runaway_job = self.monitor.check_job_runtime(
            "hanging-integration-test", duration_seconds=750.0
        )
        self.assertTrue(runaway_job.is_runaway)
        self.assertEqual(runaway_job.status, "RUNAWAY")
        self.assertIn("exceeded timeout threshold", runaway_job.recommendation)


class TestDisasterRecoveryRollback(unittest.TestCase):
    """Test suite for AutomatedRollback."""

    def test_rollback_successful_deployment(self):
        engine = AutomatedRollback()
        status = engine.deploy_and_verify(
            deployment_id="dep-101",
            target_version="v2.1.0",
            last_stable_version="v2.0.0",
            verification_fn=lambda: True,
        )
        self.assertEqual(status, RollbackStatus.STABLE)
        self.assertEqual(len(engine.history), 0)

    def test_rollback_on_failed_verification(self):
        revert_invoked = False

        def mock_revert(dep_id, version):
            nonlocal revert_invoked
            revert_invoked = True
            return True

        engine = AutomatedRollback(revert_action=mock_revert)
        status = engine.deploy_and_verify(
            deployment_id="dep-102",
            target_version="v2.2.0-broken",
            last_stable_version="v2.1.0",
            verification_fn=lambda: False,
        )

        self.assertEqual(status, RollbackStatus.ROLLED_BACK)
        self.assertTrue(revert_invoked)
        self.assertEqual(len(engine.history), 1)

        event = engine.get_latest_event()
        self.assertIsNotNone(event)
        self.assertEqual(event.deployment_id, "dep-102")
        self.assertEqual(event.rollback_version, "v2.1.0")
        self.assertIn(
            "Post-deployment health verification check failed", event.trigger_reason
        )


if __name__ == "__main__":
    unittest.main()
