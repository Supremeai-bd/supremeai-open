--- a/tests/test_render_build_minute_window.py
+++ b/tests/test_render_build_minute_window.py
@@ -214,7 +214,20 @@ class BudgetGuardWindow(unittest.TestCase):
                 for page in pages:
                     yield page
 
-        with mock.patch.object(budget, "RenderClient", FakeClient):
+        # Pin the clock: the budget guard derives month_start from
+        # datetime.now() (no month_start param, unlike the quota guard), so a
+        # wall-clock call silently crossed the 2026-11-01 month boundary and
+        # every pinned-October fixture read as pre-month (0.0 != 122.5).
+        # Month-boundary time-bomb family (#4376, datum 2); pinning keeps this
+        # battery deterministic as its own docstring promises.
+        class _PinnedOctober(datetime):
+            @classmethod
+            def now(cls, tz=None):
+                return datetime(2026, 10, 15, tzinfo=timezone.utc)
+
+        with mock.patch.object(budget, "RenderClient", FakeClient), \
+                mock.patch.object(budget, "datetime", _PinnedOctober):
             minutes = budget.calculate_monthly_build_minutes("key", "srv-x")
         self.assertEqual(calls["page_size"], 100)
         self.assertIn("/deploys", calls["path"])
