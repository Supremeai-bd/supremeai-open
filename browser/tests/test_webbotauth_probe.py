"""Web Bot Auth explorer-lane probe tests (offline, deterministic).

বাংলা: এই টেস্টগুলো প্রোবের অফলাইন স্টেজগুলো যাচাই করে — IETF
draft-ietf-webbotauth-httpsig-protocol-00-এর Ed25519 টেস্ট ভেক্টর (E.2.1
রিকোয়েস্ট সিগনেচার, E.2.3 সাইনড ডিরেক্টরি রেসপন্স) বাইট-ইক্যাক্ট পুনরুৎপাদন,
JWK থাম্বপ্রিন্ট (RFC 8037 A.3), keygen->directory->sign->verify লুপ।
নেটওয়ার্ক স্টেজ (`live`) ডিফল্টে বাদ — বাহ্যিক এন্ডপয়েন্টে CI নির্ভরতা
নিষিদ্ধ; SUPREMEAI_WBA_LIVE=1 দিলে চলে।

Runs against browser/scripts/webbotauth/probe.py with zero new dependencies
(`cryptography` is already a declared satellite dependency).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

PROBE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "webbotauth" / "probe.py"
)


def _load_probe():
    spec = importlib.util.spec_from_file_location("webbotauth_probe", PROBE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def probe():
    return _load_probe()


def test_probe_file_exists():
    assert PROBE_PATH.is_file(), f"probe missing at {PROBE_PATH}"


def test_jwk_thumbprint_matches_draft_keyid(probe):
    got = probe.jwk_thumbprint(probe.RFC9421_ED25519_TEST_KEY)
    assert got == probe.TEST_KEY_THUMBPRINT


def test_draft_e21_request_signature_vector(probe):
    """Byte-exact reproduction of draft E.2.1 (EdDSA request signature)."""
    out = probe.stage_selftest()
    by_name = {c["name"]: c for c in out["checks"]}
    base_check = by_name["draft E.2.1 signature base reconstruction"]
    assert base_check["pass"], base_check.get("base")
    sig_check = by_name["draft E.2.1 Ed25519 signature value"]
    assert sig_check["pass"]
    assert sig_check["actual"] == sig_check["expected"]
    verify_check = by_name["draft E.2.1 signature verifies under public x"]
    assert verify_check["pass"]


def test_draft_e23_directory_response_vector(probe):
    """Byte-exact reproduction of draft E.2.3 (signed directory response)."""
    out = probe.stage_selftest()
    by_name = {c["name"]: c for c in out["checks"]}
    assert by_name["draft E.2.3 Content-Digest over exact directory bytes"]["pass"]
    sig = by_name["draft E.2.3 signed directory response signature"]
    assert sig["pass"]
    assert sig["actual"] == sig["expected"]
    # and the normative all-string serialization round-trips too
    assert by_name["same proof under normative all-string serialization verifies"]["pass"]


def test_selftest_stage_passes(probe):
    out = probe.stage_selftest()
    assert out["pass"] is True
    assert out["network"] is False


def test_keygen_thumbprint_is_kid(probe):
    out = probe.stage_keygen()
    assert out["pass"] is True
    assert out["thumbprint_matches_kid"] is True
    # private key material must never appear in the report
    assert "d" not in out["jwk"]


def test_directory_possession_proof_roundtrip(probe):
    out = probe.stage_directory()
    assert out["pass"] is True
    assert out["possession_proof_verified"] is True
    assert out["content_digest"].startswith("sha-256=:")


def test_loopback_sign_verify(probe):
    out = probe.stage_loopback()
    assert out["pass"] is True
    assert out["verified"] is True
    assert "@authority" in out["covered_components"]
    assert "signature-agent" in out["covered_components"]


def test_base_tamper_flips_verification(probe):
    """Any single-byte change to the covered authority must break the signature."""
    probe_mod = probe
    now = 1_800_000_000
    priv, jwk = probe_mod.generate_keypair()
    component_ids = [("@authority", []), ("signature-agent", [("key", "sig1")])]
    base = probe_mod.request_signature_base(
        authority="target.example",
        signature_agent_member=probe_mod.sf_string("https://sa.test/dir"),
        component_ids=component_ids,
        created=now, keyid=jwk["kid"], expires=now + 300,
        nonce=probe_mod.generate_nonce(),
    )
    sig = probe_mod.sign_base(priv, base)
    assert probe_mod.verify_base(priv.public_key(), base, sig) is True
    tampered = base.replace("target.example", "target.examplf")
    assert probe_mod.verify_base(priv.public_key(), tampered, sig) is False


def test_live_stage_skipped_by_default(probe):
    """The network stage must not run implicitly; gate it behind an env flag."""
    if os.environ.get("SUPREMEAI_WBA_LIVE") != "1":
        pytest.skip("SUPREMEAI_WBA_LIVE != 1 — network stage is opt-in")
    out = probe.stage_live()
    assert out["pass"] is True
    verdicts = [a.get("verdict") for a in out.get("attempts", [])]
    assert "valid" in verdicts or out.get("verdict_body") == "valid"
