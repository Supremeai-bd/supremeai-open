"""Tests for SupremeAI reply branding badge."""
import importlib
import os
import sys

# Repo root on sys.path, canonical module identity (drift class F-K: importing
# the bare service.* form forks a second module object and splits singletons).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    branding = importlib.import_module("gateway.service.branding")
except ImportError:  # satellite layout: repo root IS the gateway package dir
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    branding = importlib.import_module("service.branding")


def test_webhook_gemini_is_turbo():
    b = branding.build_brand("w", "gemini", "gemini-web-relay")
    assert b == {"channel": "w", "engine": "ge", "tier": "Turbo", "label": "SupremeAI w.ge Turbo"}


def test_api_grok_free_and_pro():
    assert branding.build_brand("a", "grok", "grok-2")["label"] == "SupremeAI a.gr Free"
    assert branding.build_brand("a", "grok", "grok-2", paid=True)["tier"] == "Pro"


def test_api_reasoning_is_ultra():
    assert branding.build_brand("a", "anthropic", "claude-opus")["label"] == "SupremeAI a.cl Ultra"


def test_unknown_engine_and_channel_safe():
    b = branding.build_brand("zz", None, None)
    assert b["label"] == "SupremeAI w.xx Turbo"
