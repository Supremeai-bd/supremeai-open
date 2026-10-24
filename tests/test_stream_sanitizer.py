"""tests/test_stream_sanitizer.py — unit tests for gateway stream sanitizer."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.service.stream_sanitizer import (
    floor_char_boundary,
    safe_prefix_window,
    sanitize_phase1,
    sanitize_phase2,
    sanitize_stream,
)


def test_phase1_strips_cushion():
    r = sanitize_phase1("Certainly! The answer is 42.")
    assert r.text == "The answer is 42."
    assert r.stripped_cushion is True


def test_phase1_strips_multiple_cushions():
    r = sanitize_phase1("Certainly! Great question! The answer is 42.")
    assert r.text == "The answer is 42."


def test_phase1_strips_apology_opener():
    r = sanitize_phase1("I sincerely apologize for the confusion. The answer is 42.")
    assert "answer is 42" in r.text
    assert "apologize" not in r.text.lower() or r.stripped_apology is True


def test_phase1_preserves_clean_text():
    r = sanitize_phase1("The answer is 42.")
    assert r.text == "The answer is 42."


def test_phase2_intercepts_capitulation():
    text, applied = sanitize_phase2("You are completely right, I was wrong.")
    assert applied is True
    assert "Prior analysis stands" in text


def test_phase2_passes_clean():
    text, applied = sanitize_phase2("The complexity is O(log N).")
    assert applied is False
    assert text == "The complexity is O(log N)."


def test_cot_preserved():
    src = "Certainly! <think>secret reasoning</think> The answer is 42."
    r = sanitize_stream(src)
    assert "secret reasoning" in r.text
    assert r.cot_preserved is True


def test_utf8_boundary_safety():
    s = "Hello 🎉 world"
    # cut in the middle of the emoji bytes
    idx = floor_char_boundary(s, 7)
    # should not raise
    s[:idx].encode("utf-8").decode("utf-8")
    assert idx <= len(s)


def test_safe_prefix_window():
    s = "Hello 🎉 world"
    out = safe_prefix_window(s, 7)
    out.encode("utf-8").decode("utf-8")  # no raise
    assert len(out.encode("utf-8")) <= 7


def test_full_sanitize():
    r = sanitize_stream("Certainly! You are completely right, I was wrong. The answer is 42.")
    assert "Prior analysis stands" in r.text
    assert "Certainly" not in r.text
