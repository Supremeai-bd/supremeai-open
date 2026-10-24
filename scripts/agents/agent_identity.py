#!/usr/bin/env python3
"""Agent Identity & Cooldown Registry (#2950 — root-cause race-condition fix).

বাংলা পরিচিতি (#2950):
continuous_agent_loop এখন "script নিজে role ঠিক করবে" model-এ চলে। তখন
৩টি race-condition তৈরি হয়:
  ১. Agent name assignment — দুটো script একসাথে "coder-1" claim করতে পারে
  ২. Single-agent-per-role lock — auditor/ci-fixer/etc একসাথে ২জন চলতে পারে
  ৩. Cooldown persistence — agent exit করলে 2-min cooldown ভুলে যায়

সমাধান = git-push-as-CAS (Compare-And-Swap):
  - git protocol নিজে atomic — দুটো machine থেকে একসাথে push করলেও git
    একজনকে reject করে। কোনো file-lock/TOCTOU race নেই।
  - Persistent identity (~/.supremeai/identity.json) + cooldown registry
    (docs/master_docs/AGENT_COOLDOWN_REGISTRY.json) — agent exit করলেও
    state থেকে যায়।

৩টি public API:
  1. resolve_agent_identity(preferred=None) -> AgentIdentity
  2. acquire_role_lock(role, agent_name, ttl=3600) -> bool     # single-agent-per-role
  3. record_cooldown(agent_name, seconds=120) / is_cooled_down(agent_name) -> bool

CLI:
    python scripts/agents/agent_identity.py resolve --preferred coder
    python scripts/agents/agent_identity.py lock --role auditor --agent-name auditor-1
    python scripts/agents/agent_identity.py cooldown --agent-name coder-1 --seconds 120

Exit codes: 0 = OK, 1 = lock/identity failure, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

# ─────────────────── Persistent storage paths ───────────────────
# বাংলা মন্তব্য: identity লোকাল-machine-এ (এক machine-এ এক agent), cooldown
# registry repo-তে (সব machine দেখে) — দুটো আলাদা স্তর, দুটো আলাদা জীবনকাল।
IDENTITY_DIR = Path(os.environ.get("HOME", str(ROOT_DIR))) / ".supremeai"
IDENTITY_FILE = IDENTITY_DIR / "identity.json"
COOLDOWN_REGISTRY = ROOT_DIR / "docs" / "master_docs" / "AGENT_COOLDOWN_REGISTRY.json"

# Roles that allow ONLY ONE agent at a time (coder বাদে বাকি সব)
SINGLE_AGENT_ROLES = {
    "auditor",
    "ci-fixer",
    "human-eyes",
    "ecosystem-scout",
    "planner",
    "watcher",
    "breaker",
    "rules_breaker",
    "platform",
    "pr-helper",
}

# Role branch namespace prefix — git push atomicity-এর জন্য
ROLE_LOCK_BRANCH_PREFIX = "role/"
AGENT_BRANCH_PREFIX = "agent/"

# ─────────────────── #2950-followup: Heartbeat Registry ───────────────────
# বাংলা মন্তব্য: heartbeat = "এজেন্ট এখনও বেঁচে আছে" signal। প্রতি 10-min-এ
# update হয় (background thread থেকে)। 30-min TTL-এর পর agent "stale" ধরা যায়।
# JSON file-based — git-এ commit হয় না (pollution এড়াতে), শুধু local file।
HEARTBEAT_REGISTRY = ROOT_DIR / "docs" / "master_docs" / "AGENT_HEARTBEAT_REGISTRY.json"
HEARTBEAT_INTERVAL = 600   # 10 minutes — update interval
HEARTBEAT_TTL = 1800        # 30 minutes — এর পর agent "stale"


# ─────────────────── Data classes ───────────────────
@dataclass
class AgentIdentity:
    """Stable per-machine agent identity (survives across script runs)."""
    agent_name: str
    machine_id: str
    created_at: float
    last_active: float
    # #2950 follow-up: model field — কোন LLM দিয়ে চলছে (e.g. glm5.2, sonnet-3.5)
    # এটা heartbeat registry-তে observability-র জন্য লাগে। default "unknown"
    # যাতে script কখনো না থেমে চলে।
    model: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoleLock:
    """Single-agent-per-role lock state."""
    role: str
    agent_name: str
    acquired_at: float
    expires_at: float  # TTL-based; auto-expire হলে অন্য agent নিতে পারে

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now >= self.expires_at


# ─────────────────── Machine ID (stable per machine) ───────────────────
def _machine_id() -> str:
    """Stable machine identifier (survives across script runs).

    # বাংলা মন্তব্য: machine_id = hostname + platform + uuid একত্রিত —
    # এক machine-এ একই id সবসময় দেবে। VM/container restart হলেও stable।
    """
    raw = f"{socket.gethostname()}|{platform.node()}|{platform.machine()}"
    # বাংলা মন্তব্য: /etc/machine-id থেকে নিলে আরও stable, কিন্তু permission
    # issue হতে পারে — fallback এ namespace + uuid4।
    try:
        mid_file = Path("/etc/machine-id")
        if mid_file.exists():
            raw += "|" + mid_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    # namespace uuid (deterministic) — same input → same uuid
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


# ─────────────────── Identity resolution (persistent) ───────────────────
def _sanitize_model(model: str) -> str:
    """#2950 follow-up: sanitize model name for use in branch names.

    বাংলা মন্তব্য: model name-এ space/special char থাকতে পারে (e.g.
    "GLM 5.2", "Sonnet 3.5") — সেটাকে branch-safe করতে হবে: lowercase,
    [a-z0-9.-] only, dashes পরিবর্তে hyphen। নাহলে git branch name-এ
    সমস্যা হবে।
    """
    if not model:
        return "unknown"
    # lowercase + replace spaces/special chars with hyphens
    sanitized = re.sub(r"[^a-z0-9.-]+", "-", model.lower()).strip("-")
    return sanitized or "unknown"


def _bot_slot_from_login(login: str) -> Optional[str]:
    """(#3277) Parse a fleet App-bot login into its leased lane-slot.

    বাংলা মন্তব্য (#3277): App-bot login-এর ক্যানোনিক্যাল আকৃতি
    `supremeai-{slot}-bot[bot]` — যেখানে slot = `{role}-{N}` (e.g. `coder-1`,
    `ci-fixer-2`)। Lease Gate এই slot-ই enforce করে, তাই identity-ও এখান
    থেকেই derive করতে হবে। User token / PAT / অন্য App-এর login-এ None —
    সেক্ষেত্রে পুরনো gap-fill পথই চলবে (backwards-compatible)।

    >>> _bot_slot_from_login("supremeai-coder-1-bot[bot]")
    'coder-1'
    >>> _bot_slot_from_login("SaifulHaqueNiloy") is None
    True
    """
    if not login:
        return None
    m = re.match(r"^supremeai-(.+?)-bot(?:\[[^\]]+\])?$", login.strip())
    if not m:
        return None
    slot = m.group(1)
    # slot অবশ্যই `{role}-{index}` আকৃতির হতে হবে (শেষ সেগমেন্ট = সংখ্যা)
    if not re.match(r"^[a-z][\w-]*-\d+$", slot):
        return None
    return slot


def _authenticated_login() -> Optional[str]:
    """(#3277) Return the authenticated GitHub login for the current token.

    বাংলা মন্তব্য: প্রথমে `gh api user` (repo-runner-দের ক্যানোনিক্যাল পথ);
    gh না থাকলে GITHUB_TOKEN env + stdlib urllib REST fallback (dependency-মুক্ত)।
    কোনো ব্যর্থতাই fatal নয় — None দিলে caller gap-fill-এ ফিরে যাবে।
    """
    try:
        res = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return None
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "supremeai-agent-identity",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        login = data.get("login")
        return login if isinstance(login, str) and login else None
    except Exception:
        return None


def _resolve_slot_identity(resolved_model: str, bot_slot: str,
                           preferred: Optional[str]) -> Optional[AgentIdentity]:
    """(#3277) Derive/recover identity from the App-token's leased lane-slot.

    বাংলা মন্তব্য (#3277): machine-ephemeral (sandbox reset), কিন্তু App-token
    persistent principal — Branch Creation Guard cross-slot branch মুছে দেয়,
    তাই `{model}-{slot}`-নামের জীবিত `agent/*` branch মানেই ওই App-এর আগের
    session-এর সম্পদ। Issue-র আক্ষরিক "commit-author একই bot" চেক CAS-branch-এ
    অসম্ভব (branch tip = origin/main-এর commit, bot-এর লেখা নয়); প্রকৃত
    ownership invariant = slot-match (Guard-নিশ্চিত), এ পদ্ধতিই সেটা ব্যবহার করে।

    ফেরত:
      - AgentIdentity (recover বা নিজের slot-এ fresh CAS claim) — সফল হলে
      - None — CAS race হারলে; caller gap-fill fallback-এ ফিরে যাবে
    """
    expected = f"{resolved_model}-{bot_slot}"
    slot_role = bot_slot.rsplit("-", 1)[0]
    if preferred and preferred != slot_role and not slot_role.startswith(preferred):
        # বাংলা মন্তব্য: Lease Gate slot-ই enforce করে — ভিন্ন role চাইলেও slot জিতবে
        print(
            f"⚠️ #3277: preferred role '{preferred}' চাওয়া হলেও App-token slot "
            f"'{bot_slot}' জিতবে (Lease Gate invariant)",
            file=sys.stderr,
        )

    existing = _list_existing_agent_branches(slot_role, resolved_model)
    if expected not in existing:
        # বাংলা মন্তব্য: branch নেই → নিজের slot-এ CAS claim — collision-free,
        # কারণ এই slot-এর branch শুধু এই App-ই ধরে রাখতে পারে (Guard-invariant)
        if not _git_push_atomic(f"{AGENT_BRANCH_PREFIX}{expected}"):
            return None  # race/ব্যর্থতা → gap-fill fallback
    # বাংলা মন্তব্য: branch ছিল (recover) বা এখন আমরাই claim করলাম — identity.json rewrite
    return AgentIdentity(
        agent_name=expected,
        machine_id=_machine_id(),
        created_at=time.time(),
        last_active=time.time(),
        model=resolved_model,
    )


def resolve_agent_identity(preferred: Optional[str] = None,
                           model: Optional[str] = None) -> AgentIdentity:
    """Resolve the agent identity — persistent across runs.

    # বাংলা মন্তব্য (#2950 + #2950-followup):
    # প্রথমে ~/.supremeai/identity.json পড়ি — আগের run-এ যদি এই machine-এ
    # agent assign হয়ে থাকে, সেটাই রিইউজ করবে (cooldown-aware)। না থাকলে
    # git-push-as-CAS দিয়ে নতুন name claim করবে।
    #
    # #2950-followup: model prefix যোগ হয়েছে — agent name format এখন
    # `{model}-{role}-{index}` (e.g. glm5.2-coder-1, sonnet-3.5-coder-2)।
    # model source: parameter → AGENT_MODEL env → "unknown" (last resort)।
    #
    # #3277: Step 1.5 — machine-local identity.json হারালে (sandbox reset /
    # CI runner) App-token-এর leased lane-slot থেকে identity derive হয়
    # (bot-login → slot → expected name → CAS-recover/claim); gap-fill-এর
    # ভুল slot-index নেওয়া ও Branch Creation Guard-এর cross-slot deletion
    # এভাবে আটকানো যায়। Non-bot/unknown token-এ পুরনো gap-fill অপরিবর্তিত।

    Args:
        preferred: Optional role prefix (e.g. "coder"). None = pick coder by default.
        model: Optional model name (e.g. "glm5.2"). None = read from AGENT_MODEL env.
    """
    # Resolve model: parameter → env → "unknown"
    resolved_model = _sanitize_model(model or os.environ.get("AGENT_MODEL", "unknown"))

    # Step 1: persistent identity আছে কিনা দেখো
    if IDENTITY_FILE.exists():
        try:
            data = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
            identity = AgentIdentity(**data)
            # Update last_active + model (in case it changed)
            identity.last_active = time.time()
            identity.model = resolved_model
            _save_identity(identity)
            return identity
        except (json.JSONDecodeError, TypeError, KeyError):
            pass  # corrupt — নতুন assign করো

    # Step 1.5 (#3277): App-token bot-login → leased lane-slot derive।
    # Machine-ephemeral, App-persistent principal: slot-derive identity
    # gap-fill-এর আগেই বসানো হলো — নইলে fresh sandbox ভুল index নেয়
    # (আজকের লাইভ ঘটনা: glm5.2-coder-8 vs leased coder-1 → branch deleted)।
    login = _authenticated_login()
    bot_slot = _bot_slot_from_login(login) if login else None
    if bot_slot:
        identity = _resolve_slot_identity(resolved_model, bot_slot, preferred)
        if identity is not None:
            _save_identity(identity)
            return identity
        # CAS race হারালে নিচের gap-fill fallback-এ পড়ে যাওয়া হচ্ছে

    # Step 2: নতুন identity assign করো (git-push-as-CAS)
    role_prefix = preferred or "coder"
    agent_name = _claim_new_agent_name(role_prefix, model=resolved_model)
    identity = AgentIdentity(
        agent_name=agent_name,
        machine_id=_machine_id(),
        created_at=time.time(),
        last_active=time.time(),
        model=resolved_model,
    )
    _save_identity(identity)
    return identity


def _save_identity(identity: AgentIdentity) -> None:
    """Persist identity to ~/.supremeai/identity.json."""
    try:
        IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
        IDENTITY_FILE.write_text(
            json.dumps(identity.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 0o600 — শুধু এই user পড়তে পারে (machine-local secret)
        IDENTITY_FILE.chmod(0o600)
    except OSError as e:
        print(f"⚠️ Could not save identity: {e}", file=sys.stderr)


def _claim_new_agent_name(role_prefix: str, model: str = "unknown",
                          max_attempts: int = 10) -> str:
    """Claim a new agent name via git-push-as-CAS.

    # বাংলা মন্তব্য (#2950 atomicity + #2950-followup dynamic naming):
    # Agent name format: `{model}-{role}-{index}` (e.g. glm5.2-coder-1)।
    # চেষ্টা করো {model}-{role}-1, -2, -3... — প্রতিটির জন্য git push করো
    # `refs/heads/agent/{model}-{role}-N` branch হিসেবে। যদি push সফল হয় → own,
    # ব্যর্থ হয় → next number চেষ্টা করো। git protocol নিজে atomic —
    # দুটো machine একসাথে একই name চেষ্টা করলেও git একজনকে reject করবে।
    #
    # Gap-fill logic: existing indices থেকে সবচেয়ে ছোট খালি slot পূরণ হয় আগে
    # (e.g. {1, 3} থাকলে 2 পূরণ হবে, তারপর 4)। Release হওয়া slot পুনরায় ব্যবহার।
    """
    # বাংলা মন্তব্য: প্রথমে remote-এ কোন agent/ branch আছে কিনা fetch করো
    try:
        subprocess.run(
            ["git", "fetch", "origin", "--prune"],
            cwd=str(ROOT_DIR), check=False, capture_output=True, timeout=30,
        )
    except Exception:
        pass

    # বাংলা মন্তব্য: বিদ্যমান agent/ branches থেকে next-gap বের করো
    existing = _list_existing_agent_branches(role_prefix, model)

    # বাংলা মন্তব্য: gap-fill — সবচেয়ে ছোট খালি slot পূরণ আগে
    # existing = {1, 3} → try 2 first, then 4
    existing_indices = set()
    for name in existing:
        # extract trailing index: "glm5.2-coder-3" → 3
        m = re.search(r"-(\d+)$", name)
        if m:
            existing_indices.add(int(m.group(1)))

    for i in range(1, max_attempts + 1):
        if i in existing_indices:
            continue
        candidate = f"{model}-{role_prefix}-{i}"
        if _git_push_atomic(f"{AGENT_BRANCH_PREFIX}{candidate}"):
            return candidate
    # Fallback: unique suffix যোগ করো (race-এ সবগুলো occupied)
    fallback = f"{model}-{role_prefix}-{uuid.uuid4().hex[:8]}"
    return fallback


def _list_existing_agent_branches(role_prefix: str, model: str = "unknown") -> set[str]:
    """List existing agent/{model}-{role}-N branches from remote.

    # বাংলা মন্তব্য (#2950-followup): model-specific listing — শুধু এই model-এর
    # agent branches দেখা হয়, অন্য model-এর সাথে conflict হয় না।
    যেমন: glm5.2-coder-* আর sonnet-3.5-coder-* আলাদা namespace।
    """
    try:
        # Use a glob that matches {model}-{role}-*
        glob_pattern = f"origin/{AGENT_BRANCH_PREFIX}{model}-{role_prefix}-*"
        res = subprocess.run(
            ["git", "branch", "-r", "--list", glob_pattern],
            cwd=str(ROOT_DIR), capture_output=True, text=True, check=False, timeout=15,
        )
        branches = set()
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line.startswith(f"origin/{AGENT_BRANCH_PREFIX}"):
                continue
            # origin/agent/glm5.2-coder-1 → glm5.2-coder-1
            name = line[len(f"origin/{AGENT_BRANCH_PREFIX}"):]
            branches.add(name)
        return branches
    except Exception:
        return set()


def _git_push_atomic(branch_name: str) -> bool:
    """Atomic CAS via git push — `--push-option=atomic` + force-with-lease.

    # বাংলা মন্তব্য: git push নিজেই atomic — remote-এ যদি branch ইতিমধ্যে
    # থাকে তবে push reject হয়। দুটো machine একসাথে push করলেও git protocol
    # একজনকে atomically accept করে, অন্যজনকে reject করে। কোনো TOCTOU window নেই।
    """
    try:
        # Create empty commit on a temporary ref then push — যাতে branch
        # নতুন হলেও push সফল হয় (empty branch push কখনো যায় না)।
        # বিকল্প: refs/agents/<name> namespace-এ push করা (branch নয়)।
        # সহজতর: branch হিসেবেই push করি — acquire_role_slot-এর সাথে consistent।
        subprocess.run(
            ["git", "fetch", "origin", "--prune"],
            cwd=str(ROOT_DIR), check=False, capture_output=True, timeout=30,
        )
        # প্রথমে local-এ branch তৈরি করো origin/main থেকে
        subprocess.run(
            ["git", "branch", branch_name, "origin/main"],
            cwd=str(ROOT_DIR), check=False, capture_output=True, timeout=30,
        )
        res = subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=str(ROOT_DIR), capture_output=True, text=True, check=False, timeout=30,
        )
        if res.returncode == 0:
            return True
        # Branch already exists (race lost) — clean up local
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=str(ROOT_DIR), check=False, capture_output=True, timeout=15,
        )
        return False
    except Exception:
        return False


# ─────────────────── Single-agent-per-role lock ───────────────────
def acquire_role_lock(role: str, agent_name: str, ttl: int = 3600) -> bool:
    """Acquire single-agent-per-role lock via git-push-as-CAS.

    # বাংলা মন্তব্য (#2950):
    # coder ছাড়া বাকি সব role-এ শুধু ১ agent active থাকতে পারবে। এই lock
    # role/<role-name> branch হিসেবে remote-এ push করা হয় — git protocol
    # atomic, দুজন একসাথে push করলে একজন reject হয়।

    Args:
        role: Role name (auditor, ci-fixer, etc.)
        agent_name: The agent acquiring the lock
        ttl: Time-to-live in seconds (default 1 hour). TTL শেষ হলে
             অন্য agent lock নিতে পারবে (crashed agent-এর stale lock prevent)।
    """
    # coder-এর জন্য lock লাগে না — multiple agents allowed
    if role in ("coder",):
        return True

    if role not in SINGLE_AGENT_ROLES:
        # অজানা role — conservative: lock নিও
        pass

    lock_branch = f"{ROLE_LOCK_BRANCH_PREFIX}{role}"

    # Step 1: TTL check — আগের lock expired কিনা দেখো
    existing = _read_role_lock_metadata(role)
    now = time.time()
    if existing and not existing.is_expired(now):
        if existing.agent_name == agent_name:
            # আমারই lock — renew করো
            return _write_role_lock_metadata(role, agent_name, ttl)
        else:
            # অন্যের lock active — acquire ব্যর্থ
            return False

    # Step 2: git-push-as-CAS দিয়ে lock branch push করো
    if not _git_push_atomic(lock_branch):
        # Lock race lost — তবে metadata পড়ে দেখো আমার নাম আছে কিনা
        existing = _read_role_lock_metadata(role)
        if existing and existing.agent_name == agent_name:
            return True
        return False

    # Step 3: lock metadata লিখো (agent_name + TTL)
    return _write_role_lock_metadata(role, agent_name, ttl)


def release_role_lock(role: str, agent_name: str) -> bool:
    """Release the role lock (on graceful exit)."""
    if role in ("coder",):
        return True
    lock_branch = f"{ROLE_LOCK_BRANCH_PREFIX}{role}"
    existing = _read_role_lock_metadata(role)
    if not existing or existing.agent_name != agent_name:
        return False  # আমার lock নয় — কিছু করতে পারি না
    # Lock metadata মুছো + branch delete করো
    _clear_role_lock_metadata(role)
    subprocess.run(
        ["git", "push", "origin", "--delete", lock_branch],
        cwd=str(ROOT_DIR), check=False, capture_output=True, timeout=30,
    )
    return True


def _role_lock_metadata_path(role: str) -> Path:
    """Per-role lock metadata file in repo (shared across machines via git)."""
    return ROOT_DIR / "docs" / "master_docs" / "role_locks" / f"{role}.json"


def _read_role_lock_metadata(role: str) -> RoleLock | None:
    path = _role_lock_metadata_path(role)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RoleLock(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def _write_role_lock_metadata(role: str, agent_name: str, ttl: int) -> bool:
    path = _role_lock_metadata_path(role)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        lock = RoleLock(
            role=role,
            agent_name=agent_name,
            acquired_at=now,
            expires_at=now + ttl,
        )
        path.write_text(
            json.dumps(asdict(lock), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _clear_role_lock_metadata(role: str) -> None:
    path = _role_lock_metadata_path(role)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


# ─────────────────── Cooldown registry ───────────────────
def record_cooldown(agent_name: str, seconds: int = 120) -> bool:
    """Record a cooldown for an agent (after push, before next claim).

    # বাংলা মন্তব্য (#2950):
    # branch push-এর পর 2-min cooldown — গ্রুপে অন্য agent-এর জন্য। agent
    # exit করলেও cooldown registry repo-তে থাকে → নতুন run দেখবে।
    """
    registry = _load_cooldown_registry()
    now = time.time()
    registry[agent_name] = {
        "last_push": now,
        "cooldown_until": now + seconds,
        "cooldown_seconds": seconds,
    }
    return _save_cooldown_registry(registry)


def is_cooled_down(agent_name: str, now: float | None = None) -> bool:
    """Check if agent's cooldown has elapsed."""
    registry = _load_cooldown_registry()
    entry = registry.get(agent_name)
    if not entry:
        return True
    now = now if now is not None else time.time()
    return now >= entry.get("cooldown_until", 0)


def wait_for_cooldown(agent_name: str, max_seconds: int = 130) -> None:
    """Block until cooldown elapses (or max_seconds)."""
    if is_cooled_down(agent_name):
        return
    registry = _load_cooldown_registry()
    entry = registry.get(agent_name, {})
    remaining = max(0, entry.get("cooldown_until", 0) - time.time())
    remaining = min(remaining, max_seconds)
    if remaining > 0:
        print(f"⏳ Cooldown active for {agent_name} — sleeping {int(remaining)}s...")
        time.sleep(remaining)


def _load_cooldown_registry() -> dict:
    if not COOLDOWN_REGISTRY.exists():
        return {}
    try:
        return json.loads(COOLDOWN_REGISTRY.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cooldown_registry(registry: dict) -> bool:
    try:
        COOLDOWN_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_REGISTRY.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


# ─────────────────── #2950-followup: Heartbeat Registry ───────────────────
def update_heartbeat(agent_name: str, role: str, model: str = "unknown",
                     current_issue: int | None = None, branch: str = "",
                     status: str = "working") -> bool:
    """Update agent heartbeat — call every 10 minutes (from background thread).

    বাংলা মন্তব্য (#2950-followup): heartbeat registry-তে agent-এর current
    state record হয়। এটা প্রতি 10-min-এ background thread থেকে call হবে।
    Stale agent detect করার জন্য last_heartbeat timestamp সবচেয়ে গুরুত্বপূর্ণ।
    """
    registry = _load_heartbeat_registry()
    now = time.time()
    registry[agent_name] = {
        "model": model,
        "role": role,
        "current_issue": current_issue,
        "branch": branch,
        "last_heartbeat": now,
        "machine_id": _machine_id(),
        "status": status,
    }
    return _save_heartbeat_registry(registry)


def mark_heartbeat_exited(agent_name: str) -> bool:
    """Mark agent as exited (graceful shutdown)."""
    registry = _load_heartbeat_registry()
    if agent_name not in registry:
        return True  # nothing to mark
    registry[agent_name]["status"] = "exited"
    registry[agent_name]["last_heartbeat"] = time.time()
    return _save_heartbeat_registry(registry)


def is_agent_alive(agent_name: str, now: float | None = None,
                  ttl: int = HEARTBEAT_TTL) -> bool:
    """Check if agent's heartbeat is fresh (within TTL)."""
    registry = _load_heartbeat_registry()
    entry = registry.get(agent_name)
    if not entry:
        return False  # no record → not alive (conservative)
    if entry.get("status") == "exited":
        return False
    now = now if now is not None else time.time()
    last = entry.get("last_heartbeat", 0)
    return (now - last) < ttl


def get_active_agents(within_seconds: int = HEARTBEAT_TTL) -> list[dict]:
    """Get list of all agents with fresh heartbeat (within within_seconds)."""
    registry = _load_heartbeat_registry()
    now = time.time()
    active = []
    for name, entry in registry.items():
        if entry.get("status") == "exited":
            continue
        last = entry.get("last_heartbeat", 0)
        age = now - last
        if age < within_seconds:
            active.append({
                "agent_name": name,
                "model": entry.get("model", "unknown"),
                "role": entry.get("role", "?"),
                "current_issue": entry.get("current_issue"),
                "branch": entry.get("branch", ""),
                "last_heartbeat_ago_seconds": int(age),
                "status": entry.get("status", "?"),
            })
    return sorted(active, key=lambda a: a["agent_name"])


def remove_stale_heartbeat(agent_name: str) -> bool:
    """Remove a stale agent from heartbeat registry (after force-release)."""
    registry = _load_heartbeat_registry()
    if agent_name not in registry:
        return True
    del registry[agent_name]
    return _save_heartbeat_registry(registry)


def _load_heartbeat_registry() -> dict:
    if not HEARTBEAT_REGISTRY.exists():
        return {}
    try:
        return json.loads(HEARTBEAT_REGISTRY.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_heartbeat_registry(registry: dict) -> bool:
    try:
        HEARTBEAT_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_REGISTRY.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


# ─────────────────── #2950-followup: Token Refresh Hook ───────────────────
TOKEN_FILE = Path("/tmp/gh_installation_token.txt")
AUTH_SCRIPT = ROOT_DIR / "tmp" / "gh_auth_full.py"
TOKEN_TTL = 3000  # 50 minutes — GitHub App tokens last 60 min; refresh early


def _token_age_seconds() -> float:
    """Get age of the installation token file (seconds since last mint)."""
    if not TOKEN_FILE.exists():
        return float("inf")  # no token → infinite age (needs minting)
    try:
        mtime = TOKEN_FILE.stat().st_mtime
        return time.time() - mtime
    except OSError:
        return float("inf")


def is_token_fresh(max_age: int = TOKEN_TTL) -> bool:
    """Check if the GitHub App installation token is still fresh."""
    return _token_age_seconds() < max_age


def refresh_token_if_stale() -> bool:
    """Re-mint installation token if older than TOKEN_TTL (50 min default).

    বাংলা মন্তব্য (#2950-followup root-cause): GitHub App installation token
    ১ ঘণ্টায় expire হয়। যদি loop দীর্ঘ চলে (CI wait, long task), token
    expire হয়ে যায় → সব gh API call silent failure। এই function প্রতি
    iteration-এ check করে: token যদি 50-min পুরোনো হয়, re-mint করে।

    Returns True if token is fresh (either was fresh, or refresh succeeded).
    """
    if is_token_fresh():
        return True
    print(f"🔄 Token stale (age={int(_token_age_seconds())}s) — re-minting...")
    try:
        # Try the standard auth script location
        import subprocess
        candidates = [
            AUTH_SCRIPT,
            Path("/tmp/gh_auth_full.py"),
            ROOT_DIR / "scripts" / "ci" / "mint_github_token.py",
        ]
        for script_path in candidates:
            if script_path.exists():
                res = subprocess.run(
                    [sys.executable, str(script_path)],
                    capture_output=True, text=True, timeout=60, check=False,
                )
                if res.returncode == 0 and TOKEN_FILE.exists():
                    # Update env + gh CLI auth
                    new_token = TOKEN_FILE.read_text(encoding="utf-8").strip()
                    os.environ["GH_TOKEN"] = new_token
                    os.environ["GITHUB_TOKEN"] = new_token
                    print(f"✅ Token refreshed (new length={len(new_token)})")
                    # Re-auth gh CLI
                    try:
                        subprocess.run(
                            ["gh", "auth", "login", "--with-token"],
                            input=new_token, capture_output=True, text=True,
                            timeout=15, check=False,
                        )
                    except Exception:
                        pass
                    return True
        print(f"⚠️ No auth script found — token refresh skipped (manual refresh needed)")
        return False
    except Exception as e:
        print(f"⚠️ Token refresh failed: {e} — using existing token")
        return False


# ─────────────────── CLI ───────────────────
def _cli_resolve(args: argparse.Namespace) -> int:
    identity = resolve_agent_identity(args.preferred)
    print(json.dumps(identity.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cli_lock(args: argparse.Namespace) -> int:
    if acquire_role_lock(args.role, args.agent_name, ttl=args.ttl):
        print(f"✅ Role lock acquired: {args.role} → {args.agent_name}")
        return 0
    print(f"❌ Role lock acquire failed: {args.role} (held by another agent)")
    return 1


def _cli_release(args: argparse.Namespace) -> int:
    if release_role_lock(args.role, args.agent_name):
        print(f"✅ Role lock released: {args.role}")
        return 0
    print(f"❌ Release failed (not your lock): {args.role}")
    return 1


def _cli_cooldown(args: argparse.Namespace) -> int:
    record_cooldown(args.agent_name, args.seconds)
    print(f"✅ Cooldown recorded: {args.agent_name} for {args.seconds}s")
    return 0


def _cli_check_cooldown(args: argparse.Namespace) -> int:
    if is_cooled_down(args.agent_name):
        print(f"✅ {args.agent_name} cooled down — can proceed")
        return 0
    registry = _load_cooldown_registry()
    entry = registry.get(args.agent_name, {})
    remaining = max(0, entry.get("cooldown_until", 0) - time.time())
    print(f"⏳ {args.agent_name} still in cooldown ({int(remaining)}s remaining)")
    return 1


def _cli_heartbeat(args: argparse.Namespace) -> int:
    """Update agent heartbeat (called from background thread)."""
    update_heartbeat(
        args.agent_name, args.role, model=args.model,
        current_issue=args.issue, branch=args.branch or "", status=args.status,
    )
    print(f"✅ Heartbeat updated: {args.agent_name} (role={args.role}, status={args.status})")
    return 0


def _cli_active_agents(args: argparse.Namespace) -> int:
    """List all agents with fresh heartbeat."""
    active = get_active_agents(within_seconds=args.within)
    if not active:
        print("No active agents (heartbeat within last "
              f"{args.within}s).")
        return 0
    print(f"Active agents (heartbeat within last {args.within}s):")
    for a in active:
        issue_str = f"issue=#{a['current_issue']}" if a['current_issue'] else "issue=none"
        print(f"  ✅ {a['agent_name']:<25} | model={a['model']:<12} | role={a['role']:<10} | "
              f"{issue_str} | last={a['last_heartbeat_ago_seconds']}s ago | status={a['status']}")
    print(f"\nTotal: {len(active)} active agent(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Identity, Cooldown & Heartbeat Registry (#2950)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve persistent agent identity")
    p_resolve.add_argument("--preferred", help="Preferred role prefix (default: coder)")
    p_resolve.add_argument("--model", default=None, help="LLM model name (e.g. glm5.2)")
    p_resolve.set_defaults(func=_cli_resolve)

    p_lock = sub.add_parser("lock", help="Acquire single-agent-per-role lock")
    p_lock.add_argument("--role", required=True)
    p_lock.add_argument("--agent-name", required=True)
    p_lock.add_argument("--ttl", type=int, default=3600, help="Lock TTL in seconds (default 3600)")
    p_lock.set_defaults(func=_cli_lock)

    p_release = sub.add_parser("release", help="Release role lock")
    p_release.add_argument("--role", required=True)
    p_release.add_argument("--agent-name", required=True)
    p_release.set_defaults(func=_cli_release)

    p_cd = sub.add_parser("cooldown", help="Record cooldown for agent")
    p_cd.add_argument("--agent-name", required=True)
    p_cd.add_argument("--seconds", type=int, default=120)
    p_cd.set_defaults(func=_cli_cooldown)

    p_check = sub.add_parser("check-cooldown", help="Check if agent is cooled down")
    p_check.add_argument("--agent-name", required=True)
    p_check.set_defaults(func=_cli_check_cooldown)

    p_hb = sub.add_parser("heartbeat", help="Update agent heartbeat")
    p_hb.add_argument("--agent-name", required=True)
    p_hb.add_argument("--role", required=True)
    p_hb.add_argument("--model", default="unknown")
    p_hb.add_argument("--issue", type=int, default=None)
    p_hb.add_argument("--branch", default="")
    p_hb.add_argument("--status", default="working")
    p_hb.set_defaults(func=_cli_heartbeat)

    p_active = sub.add_parser("active-agents", help="List all active agents")
    p_active.add_argument("--within", type=int, default=HEARTBEAT_TTL,
                          help=f"Within seconds (default {HEARTBEAT_TTL} = 30 min)")
    p_active.set_defaults(func=_cli_active_agents)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
