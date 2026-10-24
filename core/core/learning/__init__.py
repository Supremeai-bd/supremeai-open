"""Persistent Learning Store package (Sprints 2-4, Self-Evolution Zero-Cost plan).

Public surface:

    from core.learning import (
        get_learning_store,        # buffered durable-telemetry pipeline
        record_llm_event,          # fast enqueue of one LLM observation
        record_feedback,           # categorical user feedback
        aggregate_provider_metrics # pure (provider, model) rollup
        get_learning_loop_agent,   # Sprint 4: observe→aggregate→propose agent
        get_ratio,                 # Sprint 5: bounded token-ratio calibration
        update_ratio,              # fold one (estimated, actual) observation
    )

The LearningStore singleton is started by the app lifespan
(``core.startup.agents``) and stopped at shutdown (``core.shutdown``); direct
callers may also ``start()``/``stop()`` it manually.
"""

from __future__ import annotations

from .calibration import (
    MAX_RATIO,
    MAX_STEP,
    MIN_RATIO,
    MIN_SAMPLES,
    get_calibration_stats,
    get_ratio,
    reset_calibration,
    update_ratio,
)
from .loop import LearningLoopAgent, get_learning_loop_agent
from .store import (
    ALLOWED_FEEDBACK_TYPES,
    LEARNING_EVENT_FIELDS,
    LearningEvent,
    LearningStore,
    aggregate_provider_metrics,
    get_learning_store,
    record_feedback,
    record_llm_event,
    sanitize_metadata,
)

__all__ = [
    "ALLOWED_FEEDBACK_TYPES",
    "LEARNING_EVENT_FIELDS",
    "LearningEvent",
    "LearningLoopAgent",
    "LearningStore",
    "MAX_RATIO",
    "MAX_STEP",
    "MIN_RATIO",
    "MIN_SAMPLES",
    "aggregate_provider_metrics",
    "get_calibration_stats",
    "get_learning_loop_agent",
    "get_learning_store",
    "get_ratio",
    "record_feedback",
    "record_llm_event",
    "reset_calibration",
    "sanitize_metadata",
    "update_ratio",
]
