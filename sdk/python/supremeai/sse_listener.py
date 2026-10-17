"""SSE parsing primitives shared by the sync and async SupremeAI clients.

Implements the text/event-stream grammar: ``event``/``data``/``id``/
``retry`` fields, multi-line ``data`` continuation, CRLF or LF endings,
comment lines, and the ``[DONE]`` sentinel.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class StreamEvent:
    """One completed server-sent event."""

    event: str
    data: str
    id: Optional[str] = None
    parsed: Any = None
    is_done: bool = False


class SSEListener:
    """Incremental parser: feed raw chunks, receive completed events."""

    def __init__(self) -> None:
        self._buffer = ""
        self._data_lines: List[str] = []
        self._event_name = ""
        self._event_id: Optional[str] = None

    def feed(self, chunk: str) -> List[StreamEvent]:
        """Consume raw text and return every event it completes."""
        self._buffer += chunk
        events: List[StreamEvent] = []
        while True:
            match_index = -1
            separator_length = 0
            for i in range(len(self._buffer)):
                if self._buffer.startswith("\r\n", i):
                    match_index, separator_length = i, 2
                    break
                if self._buffer[i] == "\n":
                    match_index, separator_length = i, 1
                    break
                if self._buffer[i] == "\r":
                    match_index, separator_length = i, 1
                    break
            if match_index == -1:
                break
            line = self._buffer[:match_index]
            self._buffer = self._buffer[match_index + separator_length :]
            event = self._consume_line(line)
            if event is not None:
                events.append(event)
        return events

    def finish(self) -> List[StreamEvent]:
        """Flush trailing state at end-of-stream."""
        event = self._flush_event()
        self._buffer = ""
        return [event] if event is not None else []

    def _consume_line(self, line: str) -> Optional[StreamEvent]:
        if line == "":
            return self._flush_event()
        if line.startswith(":"):
            return None
        if ":" in line:
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
        else:
            field, value = line, ""
        if field == "data":
            self._data_lines.append(value)
        elif field == "event":
            self._event_name = value
        elif field == "id":
            self._event_id = value
        return None

    def _flush_event(self) -> Optional[StreamEvent]:
        if not self._data_lines and not self._event_name:
            return None
        data = "\n".join(self._data_lines)
        event = StreamEvent(
            event=self._event_name or "message",
            data=data,
            id=self._event_id,
            is_done=(data == "[DONE]"),
        )
        if data and not event.is_done:
            try:
                event.parsed = json.loads(data)
            except ValueError:
                event.parsed = None
        self._data_lines = []
        self._event_name = ""
        self._event_id = None
        return event
