#!/usr/bin/env python3
"""FeedbackLoop user-feedback taxonomy (#1363 contract item 1).

The route's learning-store mapper already declares thumbs_up/thumbs_down/
correction, but handle_feedback rejected them at the door (400), so user
ratings and reports never persisted (the feedback_loop table holds only
its seed row). These tests pin the widened dispatcher: the four user
types store and aggregate, legacy types stay untouched, and unknown
types still fail closed.
"""
from __future__ import annotations

import unittest

from core.feedback_loop import FeedbackLoop


class TestUserFeedbackTypes(unittest.TestCase):
    def test_thumbs_up_stores_and_aggregates_accepts(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback({"type": "thumbs_up", "session_id": "s1"})
        self.assertTrue(out["stored"])
        self.assertEqual(out["event"]["type"], "suggestion_feedback")
        self.assertEqual(out["event"]["context"].get("wire_type"), "thumbs_up")
        self.assertEqual(loop.metrics()["accepts"], 1)

    def test_thumbs_down_stores_and_aggregates_rejects(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback({"type": "thumbs_down", "message": "wrong answer"})
        self.assertTrue(out["stored"])
        self.assertEqual(loop.metrics()["rejects"], 1)
        self.assertEqual(out["event"]["context"].get("wire_type"), "thumbs_down")
        # Thumbs are user ratings, not system errors: no error-report cascade.
        self.assertEqual(loop.metrics()["errors_reported"], 0)

    def test_correction_stores_with_dedicated_metric(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback({"type": "correction", "detail": "use metric units"})
        self.assertTrue(out["stored"])
        self.assertEqual(out["event"]["type"], "correction")
        self.assertEqual(out["event"]["detail"], "use metric units")
        self.assertEqual(loop.metrics()["corrections"], 1)

    def test_correction_falls_back_to_message_field(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback({"type": "correction", "message": "fix the header"})
        self.assertTrue(out["stored"])
        self.assertEqual(out["event"]["detail"], "fix the header")

    def test_issue_report_stores_with_dedicated_metric(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback(
            {"type": "issue_report", "title": "login broken", "detail": "405 on passkey"}
        )
        self.assertTrue(out["stored"])
        self.assertEqual(out["event"]["type"], "issue_report")
        self.assertEqual(out["event"]["title"], "login broken")
        self.assertEqual(loop.metrics()["issue_reports"], 1)

    def test_issue_report_defaults_title(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback({"type": "issue_report", "detail": "something odd"})
        self.assertTrue(out["stored"])
        self.assertEqual(out["event"]["title"], "Issue report")

    def test_legacy_types_unchanged(self):
        loop = FeedbackLoop()
        self.assertTrue(
            loop.handle_feedback({"type": "edit", "file": "a.py", "diff": "x"})["stored"]
        )
        self.assertTrue(
            loop.handle_feedback({"type": "suggestion_feedback", "accepted": True})["stored"]
        )
        self.assertTrue(loop.handle_feedback({"type": "error", "message": "boom"})["stored"])
        m = loop.metrics()
        self.assertEqual((m["edits"], m["accepts"], m["errors_reported"]), (1, 1, 1))

    def test_unknown_type_still_fails_closed(self):
        loop = FeedbackLoop()
        out = loop.handle_feedback({"type": "haiku"})
        self.assertFalse(out["stored"])
        self.assertIn("Unsupported", out["reason"])

    def test_events_filter_by_new_types(self):
        loop = FeedbackLoop()
        loop.handle_feedback({"type": "correction", "detail": "d1"})
        loop.handle_feedback({"type": "issue_report", "title": "t1"})
        self.assertEqual(len(loop.events("correction")), 1)
        self.assertEqual(len(loop.events("issue_report")), 1)
        self.assertEqual(len(loop.events()), 2)


if __name__ == "__main__":
    unittest.main()
