"""This module implements a robust feedback collection and aggregation mechanism for the SupremeAI ecosystem. It defines the `FeedbackLoop` class, which serves as a central component for recording various types of user interactions and system events, such as code edits, AI suggestion feedback (acceptances/rejections), and error reports. The collected data is used to generate performance metrics and event logs, crucial for monitoring agent behavior, identifying areas for improvement, and facilitating continuous learning and refinement of the AI models.

Key Components:
- `FeedbackLoop`: Manages the collection, storage, and retrieval of various feedback events and aggregated metrics.
- `record_edit()`: Records an event indicating a user-made edit to a file, including a summary of the changes.
- `record_suggestion_feedback()`: Records user feedback on an AI-generated suggestion, noting whether it was accepted or rejected.
- `record_error_report()`: Records details about an error encountered within the system, including its message and context.
- `metrics()`: Returns the current aggregated performance metrics, such as counts of edits, accepts, rejects, and errors.
- `events()`: Returns a list of all recorded feedback events, with an option to filter by event type.
- `record_correction()`: Records a user correction event with free-form detail text.
- `record_issue_report()`: Records a user-filed issue report (title + detail), distinct from system error reports.
- `handle_feedback()`: A central dispatcher that processes incoming generic feedback payloads and routes them to the appropriate internal recording methods.

Dependencies:
- `logging`: For logging debug information about recorded events.
- `time`: For generating timestamps for each recorded event.
- `typing`: For type hinting to improve code readability and maintainability."""

from __future__ import annotations

import time
from typing import Any

from core.logging_config import logger


class FeedbackLoop:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._metrics: dict[str, Any] = {
            "edits": 0,
            "accepts": 0,
            "rejects": 0,
            "errors_reported": 0,
            "corrections": 0,
            "issue_reports": 0,
        }

    def record_edit(self, file_path: str, diff_summary: str) -> dict[str, Any]:
        event = {
            "type": "edit",
            "file": file_path,
            "diff": diff_summary,
            "timestamp": time.time(),
        }
        self._events.append(event)
        self._metrics["edits"] = self._metrics.get("edits", 0) + 1
        logger.debug("Recorded edit event: %s", file_path)
        return event

    def record_suggestion_feedback(
        self, accepted: bool, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        event = {
            "type": "suggestion_feedback",
            "accepted": accepted,
            "context": context or {},
            "timestamp": time.time(),
        }
        self._events.append(event)
        if accepted:
            self._metrics["accepts"] = self._metrics.get("accepts", 0) + 1
        else:
            self._metrics["rejects"] = self._metrics.get("rejects", 0) + 1
        logger.debug("Recorded suggestion feedback: accepted=%s", accepted)
        return event

    def record_error_report(self, error: Exception, context: dict[str, Any]) -> dict[str, Any]:
        event = {
            "type": "error",
            "message": str(error),
            "context": context,
            "timestamp": time.time(),
        }
        self._events.append(event)
        self._metrics["errors_reported"] = self._metrics.get("errors_reported", 0) + 1
        logger.debug("Recorded error report: %s", error)
        return event

    def record_correction(self, detail: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "type": "correction",
            "detail": detail,
            "context": context or {},
            "timestamp": time.time(),
        }
        self._events.append(event)
        self._metrics["corrections"] = self._metrics.get("corrections", 0) + 1
        logger.debug("Recorded correction event")
        return event

    def record_issue_report(
        self, title: str, detail: str = "", context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        event = {
            "type": "issue_report",
            "title": title,
            "detail": detail,
            "context": context or {},
            "timestamp": time.time(),
        }
        self._events.append(event)
        self._metrics["issue_reports"] = self._metrics.get("issue_reports", 0) + 1
        logger.debug("Recorded issue report: %s", title)
        return event

    def metrics(self) -> dict[str, Any]:
        return dict(self._metrics)

    def events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e.get("type") == event_type]

    def handle_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        feedback_type = (payload or {}).get("type")
        if feedback_type == "suggestion_feedback":
            accepted = bool(payload.get("accepted"))
            context = payload.get("context") or {}
            event = self.record_suggestion_feedback(accepted=accepted, context=context)
            if not accepted:
                error = (
                    payload.get("error")
                    or payload.get("message")
                    or Exception("Suggestion feedback rejected")
                )
                context = dict(context)
                context.setdefault("payload", payload)
                self.record_error_report(error=error, context=context)
            return {"stored": True, "event": event}
        if feedback_type == "edit":
            file_path = payload.get("file") or payload.get("file_path") or ""
            diff_summary = payload.get("diff") or payload.get("diff_summary") or ""
            event = self.record_edit(file_path=file_path, diff_summary=diff_summary)
            return {"stored": True, "event": event}
        if feedback_type == "error":
            error = Exception(payload.get("message") or "Unknown error")
            context = payload.get("context") or payload
            event = self.record_error_report(error=error, context=context)
            return {"stored": True, "event": event}
        # User-feedback taxonomy (#1363 contract item 1): the route's
        # learning-store mapper already declares thumbs_up/thumbs_down/
        # correction, but the loop rejected them at the door (400), so
        # user ratings and reports never persisted. Thumbs map onto the
        # existing accepts/rejects aggregation; the wire type is kept in
        # context for downstream triage. Unknown types still fail closed.
        if feedback_type in ("thumbs_up", "thumbs_down"):
            context = dict(payload.get("context") or payload)
            context.setdefault("wire_type", feedback_type)
            event = self.record_suggestion_feedback(
                accepted=feedback_type == "thumbs_up", context=context
            )
            return {"stored": True, "event": event}
        if feedback_type == "correction":
            detail = str(payload.get("detail") or payload.get("message") or "")
            event = self.record_correction(detail=detail, context=payload)
            return {"stored": True, "event": event}
        if feedback_type == "issue_report":
            title = str(payload.get("title") or payload.get("message") or "Issue report")
            detail = str(payload.get("detail") or "")
            event = self.record_issue_report(title=title, detail=detail, context=payload)
            return {"stored": True, "event": event}
        return {
            "stored": False,
            "reason": f"Unsupported feedback type: {feedback_type}",
        }
