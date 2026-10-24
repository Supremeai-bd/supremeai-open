#!/usr/bin/env python3
"""Mutation Lease — controlled remote mutation guard (#4200 §6/§7, #4207 distributed).

বাংলা সারসংক্ষেপ:
------------------
#4200 §6: Agents can work locally in parallel, but remote mutation must remain
controlled। This module provides a mutation lease:

  FREE → RESERVED → MUTATING → VERIFYING → RELEASED

NOT a fixed-duration lock — timeout is only a stale-lock recovery fallback।
Primary mechanism: freshness check + CAS (git-push-as-atomic)।

#4207 DISTRIBUTION UPGRADE (root-fix):
আগে lease state একটি machine-local ফাইলে (/tmp) থাকত — runner-1-এর এজেন্ট
runner-2-এর এজেন্টকে দেখত না, দুজনেই নিজেকে MUTATING ভাবত। এখন ২টি backend:

  * "git" (default): lease = শেয়ার্ড রিপোর ভেতরের একটি protocol-ref
    (`refs/leases/<branch>`)। Create = non-force `git push <sha>:<ref>` —
    ref বিদ্যমান হলে git নিজেই reject করে এবং git-receive-pack প্রতি-ref
    সিরিয়ালাইজ করে → এটি সত্যিকারের distributed compare-and-swap। Stale-হাইজ
    ছাড়া কোনো পথেই force নয়। কোনো নতুন infra নেই (Redis/DB নয় —
    reuse-before-create); git protocol-ই হলো লক।
  * "local": পুরনো এক-ফাইল স্টোর (dev/tests-এর জন্য explicit opt-in)।
    এটি আর কোনো প্রোডাকশন default নয় — cross-machine অদৃশ্যতা-ই #4207-র
    মূল বাগ ছিল।

FAIL-CLOSED চুক্তি: distributed store-এর অপ্রাপ্যতা মানে acquire deny —
নীরবে local fallback নয় (local fallback-ই ভুল নিরাপত্তা-অনুভূতি জন্মায়)।

Usage:
  from scripts.ci.mutation_lease import MutationLease

  lease = MutationLease(branch="agent/4200-persistent-branch")
  if lease.acquire():
      try:
          lease.check_freshness()  # raises if stale
          lease.push()            # git push (atomic)
      finally:
          lease.release()
  else:
      print("Another agent is mutating — wait or work locally")
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_TIMEOUT = 300  # 5 min — stale-lock recovery fallback only

# বাংলা: legacy local store — কেবল backend="local"-এ ব্যবহৃত (dev/tests);
# এটি আর sole coordination store নয় (#4207)।
LEASE_FILE = Path(os.environ.get("SUPREMEAI_LEASE_STORE", "/tmp/supremeai_mutation_leases.json"))

LEASE_REF_PREFIX = "refs/leases/"
# বাংলা: খাঁটি empty tree-এর স্থায়ী sha — lease commit শুধু metadata বহন করে।
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
GIT_BACKEND = "git"
LOCAL_BACKEND = "local"
_BACKENDS = (GIT_BACKEND, LOCAL_BACKEND)


class LeaseUnavailable(RuntimeError):
    """Distributed lease store-এ পৌঁছানো যায়নি — fail-closed deny (#4207)।

    বাংলা: network/token ব্যর্থতা মানে "জানি না কে ধরে আছে" — আর জানি না
    বললেই নিরাপদ; কখনোই নীরবে machine-local store-এ পাল্টানো হবে না।
    """


def resolve_backend() -> str:
    """Backend নির্বাচন — SUPREMEAI_LEASE_BACKEND env ("git" default | "local")।

    বাংলা: default হলো distributed git-ref CAS; local হলো explicit opt-in।
    Unknown মানে স্পষ্ট ব্যর্থতা (ValueError) — নীরবে local পাল্টানো fail-open
    হতো, আর local-নীরব-পাল্টানোই #4207-র মূল বাগ-শ্রেণি।
    """
    raw = os.environ.get("SUPREMEAI_LEASE_BACKEND", GIT_BACKEND).strip().lower()
    if raw == "":
        return GIT_BACKEND
    if raw not in _BACKENDS:
        raise ValueError(
            f"unknown SUPREMEAI_LEASE_BACKEND {raw!r} — valid: {sorted(_BACKENDS)}"
        )
    return raw


def _lease_ref(branch: str) -> str:
    """Branch name → lease ref name (validated)।"""
    return f"{LEASE_REF_PREFIX}{branch}"


def validate_branch_name(branch: str) -> str:
    """Validate branch name via git check-ref-format (ref-injection guard)।

    বাংলা: branch নাম ref-name হয়ে যায় — "..", "@{", শুরুর '/' ইত্যাদি
    বিপজ্জনক নাম এখানেই বাদ (git নিজেই arbiter)।
    """
    res = subprocess.run(
        ["git", "check-ref-format", f"{LEASE_REF_PREFIX}{branch}"],
        capture_output=True, text=True, timeout=10,
    )
    if res.returncode != 0:
        raise ValueError(f"invalid branch name for lease ref: {branch!r}")
    return branch


class LeaseRefStore:
    """Distributed lease store: `refs/leases/<branch>` in the shared repo (#4207)।

    বাংলা: এক branch = এক ref = এক lease। Atomicity git protocol থেকেই আসে —
    দুটি এজেন্ট একসাথে create করতে গেলে non-force push-এর একটি reject হবে।
    """

    def __init__(self, branch: str, remote: str = "origin"):
        self.branch = validate_branch_name(branch)
        self.remote = remote

    @staticmethod
    def _git(*args: str, timeout: int = 30, env: dict | None = None) -> subprocess.CompletedProcess:
        # বাংলা: সব git call এই এক choke-point দিয়ে — timeout/env/mocking এক জায়গায়।
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=timeout, env=env,
        )

    def _local_mirror_ref(self) -> str:
        # বাংলা: shared checkout-এ দুই প্রসেস একই mirror ref পড়বে — content একই
        # (remote truth), তাই race-নিরাপদ।
        return f"refs/leases-mirror/{self.branch}"

    def _lease_commit(self, agent_id: str, state: str, acquired_at: float) -> str:
        """Create a standalone metadata commit (empty tree) for the lease।"""
        payload = json.dumps(
            {"agent_id": agent_id, "branch": self.branch,
             "acquired_at": acquired_at, "state": state},
            sort_keys=True,
        )
        env = dict(os.environ)
        env.setdefault("GIT_AUTHOR_NAME", "supremeai-lease")
        env.setdefault("GIT_AUTHOR_EMAIL", "lease@supremeai.invalid")
        env.setdefault("GIT_COMMITTER_NAME", "supremeai-lease")
        env.setdefault("GIT_COMMITTER_EMAIL", "lease@supremeai.invalid")
        res = self._git("commit-tree", EMPTY_TREE_SHA, "-m", payload, timeout=15, env=env)
        if res.returncode != 0:
            raise LeaseUnavailable(f"commit-tree failed: {res.stderr[:120]}")
        return res.stdout.strip()

    def read_lease(self) -> dict | None:
        """Read the current lease; None = free; LeaseUnavailable = network fail।

        বাংলা: ls-remote খালি → free; network ব্যর্থতা → exception (fail-closed
        — "না-পড়তে-পারা" কখনো "খালি" নয়, এটিই #4204-ঘরানার fail-open বাদ)।
        """
        ref = _lease_ref(self.branch)
        ls = self._git("ls-remote", self.remote, ref, timeout=30)
        if ls.returncode != 0:
            raise LeaseUnavailable(f"ls-remote failed: {ls.stderr.strip()[:120]}")
        if not ls.stdout.strip():
            return None
        sha = ls.stdout.split()[0]
        fetch = self._git(
            "fetch", "--no-tags", "--depth", "1", self.remote,
            f"+{ref}:{self._local_mirror_ref()}", timeout=30,
        )
        if fetch.returncode != 0:
            raise LeaseUnavailable(f"lease-ref fetch failed: {fetch.stderr.strip()[:120]}")
        show = self._git("show", "-s", "--format=%ct%n%B", self._local_mirror_ref(), timeout=10)
        if show.returncode != 0:
            raise LeaseUnavailable(f"lease-ref read failed: {show.stderr.strip()[:120]}")
        lines = show.stdout.split("\n", 1)
        commit_ts = float(lines[0].strip() or 0)
        try:
            lease = json.loads(lines[1].strip() or "{}")
        except json.JSONDecodeError:
            lease = {}
        lease.setdefault("acquired_at", commit_ts)
        lease.setdefault("state", "RESERVED")
        lease["commit_sha"] = sha
        return lease

    def acquire(self, agent_id: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, dict | None]:
        """Atomic acquire via non-force ref-create CAS।

        বাংলা: (True, lease) = আমি ধরেছি (অথবা আগেই আমি-ই ছিলাম — re-entrant);
        (False, holder) = সতেজ foreign lease; (False, None/..) = CAS-হার (অন্য
        এজেন্ট আগে ঢুকেছে)। Stale foreign lease → force-steal।
        """
        existing = self.read_lease()  # ব্যর্থ হলে LeaseUnavailable — acquire deny
        if existing:
            if existing.get("agent_id") == agent_id:
                return True, existing  # re-entrant (idempotent) — ref churn নেই
            age = time.time() - float(existing.get("acquired_at", 0) or 0)
            if age < timeout:
                return False, existing  # সতেজ foreign lease — deny
            # stale → steal: force এখানেই ন্যায্য (হোল্ডার মৃত ধরে নেওয়া হয়েছে)
            sha = self._lease_commit(agent_id, state="RESERVED", acquired_at=time.time())
            steal = self._git("push", "--force", self.remote, f"{sha}:{_lease_ref(self.branch)}", timeout=60)
            if steal.returncode == 0:
                return True, existing
            return False, self.read_lease()
        sha = self._lease_commit(agent_id, state="RESERVED", acquired_at=time.time())
        create = self._git("push", self.remote, f"{sha}:{_lease_ref(self.branch)}", timeout=60)
        if create.returncode == 0:
            return True, None  # CAS won — ref নতুন সৃষ্ট
        return False, self.read_lease()  # CAS lost — কেউ একজন আগে ঢুকেছে

    def update_state(self, agent_id: str, state: str) -> bool:
        """Holder-only state transition (RESERVED→MUTATING→VERIFYING)।

        বাংলা: শুধু হোল্ডার-ই স্টেট বদলাতে পারে; acquired_at অক্ষত রাখা হয়
        (state-update stale-টাইমআউট রিসেট করে না — freshness আলাদা চুক্তি)।
        """
        existing = self.read_lease()
        if not existing or existing.get("agent_id") != agent_id:
            return False
        sha = self._lease_commit(
            agent_id, state=state, acquired_at=float(existing.get("acquired_at", 0) or 0),
        )
        upd = self._git("push", "--force", self.remote, f"{sha}:{_lease_ref(self.branch)}", timeout=60)
        return upd.returncode == 0

    def release(self, agent_id: str) -> bool:
        """Holder-only release (delete ref); idempotent on already-free।"""
        existing = self.read_lease()
        if existing is None:
            return True  # ইতিমধ্যে ফ্রি — idempotent
        if existing.get("agent_id") != agent_id:
            return False  # আমি হোল্ডার নই — অন্যের lease মুছব না
        dele = self._git("push", self.remote, f":{_lease_ref(self.branch)}", timeout=60)
        if dele.returncode == 0:
            return True
        # ref ইতিমধ্যে মুছে-গেছে (প্রতিবেশী steal/release) → সেটিও release-ই
        return self.read_lease() is None


class MutationLease:
    """Lightweight mutation lease for controlled git push (#4200 §6, #4207)।

    বাংলা: public API অপরিবর্তিত (acquire/check_freshness/push/release) —
    শুধু coordination store distributed হলো। backend="git" default;
    backend="local" পুরনো single-machine ধারা (explicit opt-in)।
    """

    def __init__(self, branch: str, agent_id: str = "", timeout: int = DEFAULT_TIMEOUT,
                 backend: str | None = None):
        self.branch = branch
        self.agent_id = agent_id or os.environ.get("AGENT_NAME", "unknown")
        self.timeout = timeout
        self.acquired = False
        self.backend = backend or resolve_backend()
        self._ref_store: LeaseRefStore | None = None

    # ── legacy local-store methods (backend="local") — kept for dev/tests/rollback ──

    def _load_leases(self) -> dict:
        if not LEASE_FILE.exists():
            return {}
        try:
            return json.loads(LEASE_FILE.read_text())
        except Exception:
            return {}

    def _save_leases(self, leases: dict) -> None:
        LEASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEASE_FILE.write_text(json.dumps(leases, indent=2))

    def _local_acquire(self) -> bool:
        """বাংলা: machine-local acquire — একই মেশিনের মধ্যে সঠিক, ক্রস-মেশিনে নয়।"""
        leases = self._load_leases()
        existing = leases.get(self.branch)
        if existing:
            age = time.time() - existing.get("acquired_at", 0)
            if age < self.timeout and existing.get("agent_id") != self.agent_id:
                return False  # Another agent holds a fresh lease (same machine)
        leases[self.branch] = {
            "agent_id": self.agent_id,
            "acquired_at": time.time(),
            "state": "RESERVED",
        }
        self._save_leases(leases)
        return True

    def _local_release(self) -> None:
        leases = self._load_leases()
        if self.branch in leases:
            del leases[self.branch]
            self._save_leases(leases)

    # ── distributed backend ──

    def _git_store(self) -> LeaseRefStore:
        if self._ref_store is None:
            self._ref_store = LeaseRefStore(self.branch)
        return self._ref_store

    # ── public API (unchanged contract) ──

    def acquire(self) -> bool:
        """Acquire mutation lease for this branch (distributed CAS by default)।

        বাংলা: FREE → RESERVED। Distributed store অপ্রাপ্য হলে deny
        (fail-closed — #4207 চুক্তি; নীরব local fallback নিষিদ্ধ)।
        """
        if self.backend == GIT_BACKEND:
            try:
                ok, _holder = self._git_store().acquire(self.agent_id, self.timeout)
            except (LeaseUnavailable, subprocess.SubprocessError, ValueError) as err:
                print(
                    f"❌ MUTATION GATE fail-closed: distributed lease unavailable ({err}) — "
                    f"acquire DENIED for {self.branch} (#4207)",
                    file=sys.stderr,
                )
                return False
            self.acquired = ok
            return ok
        self.acquired = self._local_acquire()
        return self.acquired

    def check_freshness(self) -> bool:
        """Check if branch is fresh relative to main (#4200 §7)।

        বাংলা: latest main observe → stale check → sync/rebase if needed।
        Returns True if fresh, False if stale (should sync before push)।
        """
        try:
            # Fetch latest
            subprocess.run(["git", "fetch", "origin", "main"], check=True, timeout=30)

            # Check if behind
            result = subprocess.run(
                ["git", "rev-list", "--count", f"origin/main..{self.branch}"],
                capture_output=True, text=True, timeout=10,
            )
            behind = int(result.stdout.strip()) if result.returncode == 0 else 0

            # Check if main is ahead
            result = subprocess.run(
                ["git", "rev-list", "--count", f"{self.branch}..origin/main"],
                capture_output=True, text=True, timeout=10,
            )
            ahead = int(result.stdout.strip()) if result.returncode == 0 else 0

            if ahead > 0:
                print(f"⚠️ Branch is {ahead} commits behind main — sync needed before push", file=sys.stderr)
                return False

            return True
        except Exception as e:
            print(f"Freshness check failed: {e}", file=sys.stderr)
            return False

    def push(self, force: bool = False) -> bool:
        """Push branch to remote (atomic git push) with lease-state tracking।

        বাংলা: MUTATING → push → VERIFYING। Git protocol is itself atomic।
        State-update best-effort — lease না থাকলে push মোটেই হবে না।
        """
        if not self.acquired:
            print("ERROR: push without acquire — call acquire() first", file=sys.stderr)
            return False

        if self.backend == GIT_BACKEND:
            try:
                self._git_store().update_state(self.agent_id, "MUTATING")
            except Exception as err:
                print(f"⚠️ lease state→MUTATING failed (advisory, continuing): {err}", file=sys.stderr)

        try:
            cmd = ["git", "push", "origin", self.branch]
            if force:
                cmd.append("--force")
            result = subprocess.run(cmd, check=False, timeout=60)
            if result.returncode != 0:
                print(f"git push failed (rc={result.returncode})", file=sys.stderr)
                return False

            if self.backend == GIT_BACKEND:
                try:
                    self._git_store().update_state(self.agent_id, "VERIFYING")
                except Exception as err:
                    print(f"⚠️ lease state→VERIFYING failed (advisory): {err}", file=sys.stderr)
            else:
                leases = self._load_leases()
                if self.branch in leases:
                    leases[self.branch]["state"] = "VERIFYING"
                    leases[self.branch]["pushed_at"] = time.time()
                    self._save_leases(leases)

            return True
        except Exception as e:
            print(f"Push failed: {e}", file=sys.stderr)
            return False

    def release(self) -> None:
        """Release the mutation lease (holder-only, idempotent, fail-soft)।

        বাংলা: VERIFYING → RELEASED → FREE। Distributed store ব্যর্থ হলেও
        local acquired-flag মুছে যায় — release কখনো কাজ আটকায় না।
        """
        if not self.acquired:
            return

        if self.backend == GIT_BACKEND:
            try:
                if self._git_store().release(self.agent_id):
                    print(f"🔓 Mutation lease released for {self.branch}")
                else:
                    print(
                        f"⚠️ Lease release refused (holder mismatch or delete failed) "
                        f"for {self.branch} — local flag cleared; ref remains for audit",
                        file=sys.stderr,
                    )
            except Exception as err:
                print(f"⚠️ Lease release failed (fail-soft): {err}", file=sys.stderr)
        else:
            self._local_release()
            print(f"🔓 Mutation lease released for {self.branch}")

        self.acquired = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Could not acquire mutation lease for {self.branch}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
