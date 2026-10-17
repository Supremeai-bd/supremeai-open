#!/usr/bin/env python3
"""Offline contract tests for the single active claim quota (#479, S06).

Asserts the work.claim concurrency guard the TS handler + onboarding
test must satisfy: the spec trio (GRANT_NEW / reject / different-agent
grant), the exact AGENT_CONCURRENCY_LIMIT_REACHED envelope, release
semantics (expired lease, closed issue, submitted-and-verified WO),
renewal bypass, deterministic blocking anchor, fail-closed paths.

Pure stdlib. Run: python3 -m unittest test_s06_claim_quota -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tower"))

import claim_quota_reference as cref  # noqa: E402


def ts(text):
    return cref.parse_ts(text)


NOW = ts("2026-10-17T06:10:00Z")       # 10 minutes after the seeded claims
LATE = ts("2026-10-17T06:31:00Z")      # past the 30-minute lease


def marker(num, agent, at="2026-10-17T06:00:00Z", ttl="30m"):
    return {"ts": at, "body":
            f"<!-- atomic-claim:issue={num},agent={agent},ts={at},ttl={ttl} -->"}


def issue(num, agent=None, state="open", claimed_label=True, wo_verified=False,
          comments=None, label_claimed_at=None, label_claimed_agent=None):
    labels = ["status:claimed"] if claimed_label else []
    row = {"number": num, "state": state, "labels": labels,
           "wo_verified": wo_verified, "label_claimed_at": label_claimed_at,
           "label_claimed_agent": label_claimed_agent, "comments": comments or []}
    if agent:
        row["comments"] = [marker(num, agent)]
    return row


def board(*rows):
    return {"issues": list(rows)}


class SpecTrio(unittest.TestCase):
    """The three tests mandated by task #479 section 3."""

    def test_01_spec_test1_single_agent_first_claim_grants(self):
        d = cref.enforce_quota(board(issue(900, claimed_label=False)),
                               900, "agent-a", NOW)
        self.assertTrue(d.granted)
        self.assertEqual(d.code, "GRANT_NEW")
        self.assertEqual(d.active_claims, ())

    def test_02_spec_test2_same_agent_second_claim_rejected(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 901, "agent-a", NOW)
        self.assertFalse(d.granted)
        self.assertEqual(d.code, cref.AGENT_CONCURRENCY_LIMIT_REACHED)
        self.assertEqual(d.blocking_issue, 900)
        self.assertEqual(d.active_claims, (900,))

    def test_03_spec_test3_different_agent_claim_grants(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 901, "agent-b", NOW)
        self.assertTrue(d.granted)
        self.assertEqual(d.code, "GRANT_NEW")


class RejectionEnvelope(unittest.TestCase):
    def test_04_exact_envelope_shape(self):
        p = cref.rejection_payload("zai-web:web-26454b1b", 900)
        self.assertEqual(p, {"isError": True,
                             "code": "AGENT_CONCURRENCY_LIMIT_REACHED",
                             "message": cref.MESSAGE_TEMPLATE.format(
                                 agent="zai-web:web-26454b1b", issue=900)})

    def test_05_message_template_wording(self):
        self.assertEqual(
            cref.MESSAGE_TEMPLATE.format(agent="a", issue=7),
            "Agent 'a' already holds active claim on Issue #7. "
            "Submit patch or release before claiming new work.")

    def test_06_decision_carries_same_message(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 901, "agent-a", NOW)
        self.assertEqual(d.message, cref.MESSAGE_TEMPLATE.format(agent="agent-a", issue=900))


class ReleaseSemantics(unittest.TestCase):
    def test_07_expired_lease_frees_slot(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 901, "agent-a", LATE)
        self.assertTrue(d.granted)
        self.assertEqual(d.active_claims, ())

    def test_08_exactly_ttl_is_still_live(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 901, "agent-a", ts("2026-10-17T06:30:00Z"))
        self.assertFalse(d.granted)

    def test_09_closed_issue_frees_slot(self):
        b = board(issue(900, "agent-a", state="closed"), issue(901, claimed_label=False))
        self.assertTrue(cref.enforce_quota(b, 901, "agent-a", NOW).granted)

    def test_10_wo_verified_frees_slot(self):
        b = board(issue(900, "agent-a", wo_verified=True), issue(901, claimed_label=False))
        self.assertTrue(cref.enforce_quota(b, 901, "agent-a", NOW).granted)

    def test_11_queued_wo_does_not_free_slot(self):
        b = board(issue(900, "agent-a", wo_verified=False), issue(901, claimed_label=False))
        self.assertFalse(cref.enforce_quota(b, 901, "agent-a", NOW).granted)


class RenewalAndGating(unittest.TestCase):
    def test_12_reclaiming_own_live_issue_not_blocked(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 900, "agent-a", NOW)
        self.assertTrue(d.granted)
        self.assertEqual(d.code, "GRANT_NEW")

    def test_13_noop_self_bypasses_scan(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        d = cref.enforce_quota(b, 901, "agent-a", NOW, target_decision="NOOP_SELF")
        self.assertTrue(d.granted)
        self.assertEqual(d.code, "NOOP_SELF")

    def test_14_grant_renew_is_gated_per_spec(self):
        b = board(issue(900, "agent-a"), issue(901, "agent-b"))
        d = cref.enforce_quota(b, 901, "agent-a", NOW, target_decision="GRANT_RENEW")
        self.assertFalse(d.granted)

    def test_15_takeover_gated_as_defense_in_depth(self):
        b = board(issue(900, "agent-a"), issue(901, "agent-b"))
        d = cref.enforce_quota(b, 901, "agent-a", NOW, target_decision="GRANT_TAKEOVER")
        self.assertFalse(d.granted)

    def test_16_quota_applies_to_constant(self):
        self.assertEqual(cref.QUOTA_APPLIES_TO,
                         frozenset({"GRANT_NEW", "GRANT_RENEW", "GRANT_TAKEOVER"}))

    def test_17_none_decision_runs_scan(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        self.assertFalse(cref.enforce_quota(b, 901, "agent-a", NOW).granted)


class DeterminismAndKnobs(unittest.TestCase):
    def test_18_blocks_on_lowest_issue_number(self):
        b = board(issue(910, "agent-a"), issue(905, "agent-a"),
                  issue(920, "agent-b", claimed_label=False))
        d = cref.enforce_quota(b, 920, "agent-a", NOW)
        self.assertEqual(d.blocking_issue, 905)
        self.assertEqual(d.active_claims, (905, 910))

    def test_19_active_claims_sorted_ascending(self):
        b = board(issue(910, "agent-a"), issue(905, "agent-a"), issue(902, "agent-a"))
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [902, 905, 910])

    def test_20_max_active_default_is_one(self):
        self.assertEqual(cref.MAX_ACTIVE_CLAIMS, 1)

    def test_21_max_active_knob_two_allows_second_blocks_third(self):
        held_two = board(issue(900, "agent-a"), issue(905, "agent-a"),
                         issue(902, claimed_label=False))
        self.assertFalse(
            cref.enforce_quota(held_two, 902, "agent-a", NOW, max_active=2).granted)
        held_one = board(issue(900, "agent-a"), issue(902, claimed_label=False))
        self.assertTrue(
            cref.enforce_quota(held_one, 902, "agent-a", NOW, max_active=2).granted)

    def test_22_max_active_knob_three_allows_second(self):
        b = board(issue(900, "agent-a"), issue(902, claimed_label=False))
        d = cref.enforce_quota(b, 902, "agent-a", NOW, max_active=3)
        self.assertTrue(d.granted)


class FailClosed(unittest.TestCase):
    def test_23_board_must_be_shaped(self):
        for bad in (None, {}, {"issues": "x"}, {"issues": None}, []):
            with self.assertRaises(ValueError):
                cref.scan_active_claims(bad, "agent-a", NOW)

    def test_24_bad_issue_numbers_rejected(self):
        for num in ("z", 0, -5, None):
            with self.assertRaises(ValueError):
                cref.scan_active_claims({"issues": [{"number": num}]}, "a", NOW)

    def test_25_clock_skew_rejected(self):
        b = board(issue(900, "agent-a"), issue(901, claimed_label=False))
        with self.assertRaises(ValueError):
            cref.enforce_quota(b, 901, "agent-a", ts("2026-10-17T05:59:00Z"))

    def test_26_naive_clock_rejected(self):
        import datetime as dt
        with self.assertRaises(ValueError):
            cref.scan_active_claims({"issues": []}, "a",
                                    dt.datetime(2026, 10, 17, 6, 10))

    def test_27_max_active_must_be_positive(self):
        b = board(issue(900, "agent-a"))
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                cref.enforce_quota(b, 901, "agent-a", NOW, max_active=bad)

    def test_28_unparseable_marker_timestamp_raises(self):
        b = board(issue(900, comments=[marker(900, "agent-a", at="not-a-time")]))
        with self.assertRaises(ValueError):
            cref.scan_active_claims(b, "agent-a", NOW)

    def test_29_malformed_markers_ignored(self):
        b = board(issue(900, comments=[
            {"ts": "2026-10-17T06:00:00Z", "body": "<!-- atomic-claim -->"},
            {"ts": "2026-10-17T06:00:00Z", "body": "plain text, no marker"},
        ]))
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [])

    def test_30_marker_issue_mismatch_is_garbage(self):
        b = board(issue(900, comments=[marker(999, "agent-a")]))
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [])

    def test_31_unattributable_label_claim_never_blocks(self):
        b = board(issue(900, comments=[]), issue(901, claimed_label=False))
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [])

    def test_32_label_claimed_at_fallback_honored(self):
        b = board(issue(900, comments=[], label_claimed_at="2026-10-17T06:00:00Z",
                        label_claimed_agent="agent-a"),
                  issue(901, claimed_label=False))
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [900])


class Timestamps(unittest.TestCase):
    def test_33_seconds_and_micro_formats(self):
        self.assertEqual(ts("2026-10-17T06:00:00Z").strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "2026-10-17T06:00:00Z")
        self.assertEqual(ts("2026-10-17T06:00:00.123456Z").strftime("%Sf")[:2], "00")

    def test_34_ttl_suffix_parsed(self):
        b = board(issue(900, comments=[marker(900, "agent-a", ttl="15m")]),
                  issue(901, claimed_label=False))
        # 06:00 + 15m = expires 06:15; at 06:10 still live, at 06:31 released
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [900])
        self.assertEqual(cref.scan_active_claims(b, "agent-a", LATE), [])

    def test_35_ttl_default_when_suffix_malformed(self):
        b = board(issue(900, comments=[marker(900, "agent-a", ttl="soon")]),
                  issue(901, claimed_label=False))
        self.assertEqual(cref.scan_active_claims(b, "agent-a", NOW), [900])


if __name__ == "__main__":
    unittest.main(verbosity=2)
