# --- Merged from generate_modular_audits.py ---

"""
SupremeAI 2.0 — Elite Modular Audit Generator (v2.1)
======================================================
Generates 14 + 1 hyper-focused, self-contained audit markdown files into
`docs/autogen/modular_audits/` that ANY AI auditor (GPT-4o, Claude 3.5,
Gemini 1.5 Pro, etc.) can use to give their absolute BEST review.

SCRIPT-INTELLIGENCE v9: auto-discovers targets via scripts/lib/auto_discovery.py — no hardcoded file inventories.

Target resolution per audit part (in order):
  1. literal seed path exists on disk      -> used as-is (backward compatible)
  2. literal seed missing                  -> unique-basename relocation search
                                              anywhere in the repo (renames/moves)
  3. part ``discover_globs`` patterns      -> role-based auto-tracking, so new or
                                              moved modules are picked up without
                                              editing this script
  4. still missing                         -> skipped with a
                                              "[discovery] skipping missing <name>"
                                              note (never silently green)

Key upgrades over v2.0:
  - Stale audit targets (e.g. backend/core/auto_healer_service.py,
    backend/core/resilience/rollback_monitor.py) no longer produce phantom
    inventory rows — they are skipped with an explicit note and their
    successors are found by role patterns
  - Coverage sweep: backend python files claimed by no audit part are
    reported in INDEX.md so new modules can never be silently unaudited
  - CLI: --output-dir / --list-targets / --dry-run (env: SUPREMEAI_AUDIT_OUTPUT_DIR)
  - All v2.0 features retained: no file-count cap, AI-optimized prompts,
    per-file metadata, token budgets, smart skips, master INDEX.md

বাংলা মন্তব্য: এই স্ক্রিপ্টটি যেকোনো AI কে সর্বোচ্চ মানের অডিট দেওয়ার জন্য
একটি সম্পূর্ণ, স্বনির্ভর (self-contained) কনটেক্সট প্যাকেজ তৈরি করে।
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# SCRIPT-INTELLIGENCE v9: make the shared discovery lib importable from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> scripts/
from lib.auto_discovery import (  # noqa: E402
    DiscoveryError,
    discover_files,
    discover_py_files,
    existing_paths,
    get_layout,
    require,
)

# ─────────────────────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: স্কিপ করা এক্সটেনশন — বাইনারি, ক্যাশ, বা অপ্রয়োজনীয় ফাইল
# ─────────────────────────────────────────────────────────────────────────────
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pdf", ".docx", ".xlsx", ".zip", ".gz", ".tar", ".whl",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".ogg", ".avi",
    ".lock",  # poetry.lock, package-lock.json — too large
    ".map",   # JS source maps
}

# বাংলা মন্তব্য: এই ডিরেক্টরিগুলো সম্পূর্ণ স্কিপ করা হবে
SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv", ".env",
    "dist", "build", ".next", ".turbo", ".cache", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "autogen",  # skip own output dir
}

# বাংলা মন্তব্য: ফাইল এক্সটেনশন থেকে markdown code fence ভাষা নির্ধারণ
EXT_TO_LANG: dict[str, str] = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
    ".jsx": "jsx", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".md": "markdown", ".sh": "bash", ".bash": "bash",
    ".env": "bash", ".tf": "hcl", ".hcl": "hcl", ".sql": "sql",
    ".dart": "dart", ".go": "go", ".rs": "rust", ".html": "html",
    ".css": "css", ".scss": "scss", ".xml": "xml", ".proto": "protobuf",
    ".graphql": "graphql", ".dockerfile": "dockerfile",
}

# Max file size to embed (skip files larger than this — e.g. large test fixtures)
MAX_FILE_BYTES = 150_000  # 150 KB

# ─────────────────────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: ১৪টি মডিউলার অডিট পার্টের সংজ্ঞা
#
# ``target_paths``   — legacy seed paths (kept for backward compatibility).
#                      Missing seeds are auto-skipped with a discovery note.
# ``discover_globs`` — SCRIPT-INTELLIGENCE v9 role patterns (relative to repo
#                      root).  These survive renames/moves: any file matching
#                      the role is audited even if no seed names it anymore.
# ─────────────────────────────────────────────────────────────────────────────
AUDIT_PARTS: dict[str, dict] = {
    "PART_01_LLM_GATEWAY_ROUTER.md": {
        "title": "Part 1: LLM Gateway, Predictive Router & Quota Governor",
        "description": "Multi-provider AI routing, predictive free-tier quota governor, and gateway fallback logic.",
        "focus_areas": [
            "Provider selection & fallback chain correctness",
            "Quota enforcement & Redis-based token budget atomicity",
            "Circuit breaker open/close logic under concurrent load",
            "Rate limit tracking accuracy across providers",
        ],
        "target_paths": [
            "backend/core/llm_router.py",
            "backend/core/llm/free_tier_tracker.py",
            "backend/core/llm/distributed_budget.py",
            "backend/core/autonoguard_engine.py",
        ],
    },
    "PART_02_SECURITY_GUARDRAILS.md": {
        "title": "Part 2: Security Guardrails, Prompt Firewall & RBAC",
        "description": "Prompt firewall, anti-hacking middleware, rate limiters, honeypot, and RBAC authentication.",
        "focus_areas": [
            "Prompt injection & jailbreak detection coverage",
            "CORS origin validation bypass risks",
            "RBAC role escalation vectors",
            "Rate limiter bypass under distributed load",
            "Honeypot fingerprinting effectiveness",
        ],
        "target_paths": ["backend/core/security/"],
    },
    "PART_03_MULTI_DB_OUTBOX.md": {
        "title": "Part 3: Multi-DB Architecture & Transactional Outbox",
        "description": "Transactional outbox pattern, Supabase, Cloudflare D1, Upstash Redis, and code_to_db_sync daemon.",
        "focus_areas": [
            "Outbox event delivery guarantees (at-least-once vs exactly-once)",
            "Multi-DB router fail-closed correctness under all circuit breaker states",
            "Feature flag percentage rollout determinism",
            "Write-behind batcher flush atomicity",
        ],
        "target_paths": [
            "backend/database/multi_db_router.py",
            "backend/pipelines/code_to_db_sync.py",
            "backend/core/persistence/write_behind.py",
            "backend/database/supabase_client.py",
        ],
    },
    "PART_04_TIER8_SELF_EVOLUTION.md": {
        "title": "Part 4: Tier 8 Self-Evolution Engine & Auto-Healer",
        "description": "Error fingerprinting, mutation depth guardrails, model training, and auto-git-revert triggers.",
        "focus_areas": [
            "Mutation depth <= 3 guardrail enforcement",
            "Fingerprint collision risk in failure_fingerprint.py",
            "Rollback monitor gcloud dependency failure handling",
            "Model trainer status fabrication prevention",
        ],
        "target_paths": [
            "backend/core/auto_healer_service.py",
            "backend/core/failure_fingerprint.py",
            "backend/tools/learning/model_trainer.py",
            "backend/core/resilience/rollback_monitor.py",
        ],
        # SCRIPT-INTELLIGENCE v9: the two legacy seeds above rotted away; these
        # role patterns auto-track their successors (backend/core/resilience/*,
        # backend/services/auto_healer.py) and any future renames/moves.
        "discover_globs": [
            "backend/core/resilience/*.py",
            "backend/**/auto_heal*.py",
            "backend/**/failure_fingerprint*.py",
            "backend/**/model_trainer*.py",
        ],
    },
    "PART_05_SWARM_WEBSOCKETS.md": {
        "title": "Part 5: Swarm Real-Time WebSockets & Telemetry Buffer",
        "description": "250ms sliding window ring-buffer streaming, Redis pubsub, and HITL escalation channels.",
        "focus_areas": [
            "PubSub message delivery ordering & backpressure",
            "Oversized broadcast payload handling",
            "Wall-clock timer flush correctness in buffered_subscribe",
            "Admin route authentication coverage completeness",
        ],
        "target_paths": [
            "backend/core/swarm_pubsub.py",
            "backend/api/routes/admin_routes.py",
        ],
    },
    "PART_06_P2P_COMPUTE_MESH.md": {
        "title": "Part 6: P2P Compute Mesh & Zero-Trust Sandboxing",
        "description": "Zero-trust MicroVM sandbox execution, hardware resource broker, and crypto proof-of-work credit system.",
        "focus_areas": [
            "Resource broker race conditions under concurrent allocation",
            "MicroVM escape vectors (filesystem, network, process)",
            "Credit deduction atomicity & refund guarantees",
            "Firecracker/gVisor payload injection security",
        ],
        "target_paths": [
            "backend/p2p/resource_broker.py",
            "backend/p2p/credit_system.py",
            "backend/core/microvm_sandbox.py",
        ],
    },
    "PART_07_BACKEND_API_ROUTERS.md": {
        "title": "Part 7: Backend API Routers, Middleware & Core App Builder",
        "description": "FastAPI application entrypoints, middleware stack, dependencies, and v1 API routers.",
        "focus_areas": [
            "Middleware ordering & dependency injection safety",
            "Unauthenticated endpoint exposure",
            "Request validation & schema enforcement gaps",
            "CORS, HTTPS, and security header configuration",
        ],
        "target_paths": [
            "backend/api/",
            "backend/core/app.py",
            "backend/core/app_builder.py",
        ],
    },
    "PART_08_BACKEND_AI_AGENT_TOOLS.md": {
        "title": "Part 8: Backend AI Agents, MCP Tools & Orchestration Services",
        "description": "Autonomous AI agent tools, MCP server integrations, checkpointing, and execution tools.",
        "focus_areas": [
            "Agent loop infinite recursion risks",
            "MCP tool permission scope creep",
            "Checkpoint state integrity under concurrent agents",
            "External tool execution sandboxing completeness",
        ],
        "target_paths": ["backend/tools/"],
    },
    "PART_09_REACT_STUDIO_CLIENT.md": {
        "title": "Part 9: React/Vite Studio Client Web Application",
        "description": "React Studio Client frontend app, Admin Console UI components, and state management hooks.",
        "focus_areas": [
            "XSS vectors in rendered user/AI content",
            "Auth token storage & expiry handling in zustand stores",
            "Error boundary completeness & telemetry reporting",
            "Sensitive data leakage in frontend error messages",
        ],
        # SCRIPT-INTELLIGENCE v9: legacy monorepo path kept as a seed (skipped
        # with a note when absent); the studio client now lives in frontend/
        # (package name "supremeai-studio-client") and is picked up because
        # existing_paths() filters the candidate list to what really exists.
        "target_paths": [
            "apps/studio-client/src/",
            "frontend/src/",
        ],
    },
    "PART_10_FLUTTER_MOBILE_APP.md": {
        "title": "Part 10: Flutter Mobile Cross-Platform Application",
        "description": "Flutter Mobile application source code, state management, and mobile API services.",
        "focus_areas": [
            "API key storage security (Keychain/Keystore vs plain storage)",
            "Certificate pinning implementation",
            "Deep link validation & open redirect risks",
            "Biometric auth bypass vectors",
        ],
        # SCRIPT-INTELLIGENCE v9: the apps/mobile/ tree no longer exists; the
        # Flutter/Dart artifacts that DO exist are added as discovery seeds.
        "target_paths": [
            "apps/mobile/",
            "packages/design-tokens/outputs/flutter/",
            "packages/shared-types/src/dart/",
        ],
    },
    "PART_11_PACKAGES_SHARED_TYPES.md": {
        "title": "Part 11: Shared Monorepo Packages & TypeScript Interfaces",
        "description": "Monorepo shared TypeScript types, design tokens, and reusable UI components.",
        "focus_areas": [
            "Type safety gaps that could mask runtime errors",
            "Shared secret / credential handling in shared packages",
            "Circular dependency risks",
        ],
        "target_paths": ["packages/"],
    },
    "PART_12_TEST_SUITE_PYTEST.md": {
        "title": "Part 12: Pytest Test Suite & Integration Tests",
        "description": "Backend pytest test suite, API integration test cases, and resilience coverage.",
        "focus_areas": [
            "Test coverage gaps in security-critical paths",
            "Mocking correctness (wrong module paths, incomplete mocks)",
            "Async test isolation & event loop leaks",
            "Integration test environment variable dependency risks",
        ],
        "target_paths": ["backend/tests/"],
    },
    "PART_13_CICD_DEV_WORKFLOWS.md": {
        "title": "Part 13: GitHub Actions CI/CD & DevOps Scripts",
        "description": "Monorepo GitHub Actions workflows, maintenance automation pipelines, and CI scripts.",
        "focus_areas": [
            "Secret exposure in workflow logs (echo, env printing)",
            "Workflow trigger scope (pull_request vs push)",
            "Third-party action pinning (SHA vs tag)",
            "Script injection via untrusted PR data",
        ],
        "target_paths": [
            ".github/workflows/",
            "scripts/ci/",
            "scripts/devops/",
        ],
    },
    "PART_14_CLOUD_INFRASTRUCTURE.md": {
        "title": "Part 14: Cloud Infrastructure, Edge Workers & Docker Prod",
        "description": "Terraform, Cloudflare Worker JS, Firebase Functions, Docker Prod, and deployment specs.",
        "focus_areas": [
            "Docker image hardening (non-root user, read-only FS)",
            "Terraform state file secret exposure",
            "Cloudflare Worker secret binding completeness",
            "Network exposure of internal services",
        ],
        "target_paths": [
            "infrastructure/",
            "cloudflare-worker/",
            "Dockerfile",
            "render.yaml",
            "vercel.json",
        ],
        # SCRIPT-INTELLIGENCE v9: root-level Dockerfile/render.yaml/vercel.json
        # rotted away; these patterns auto-track where docker/render config
        # actually lives now (backend/, frontend/, infrastructure/).
        "discover_globs": [
            "backend/Dockerfile",
            "frontend/Dockerfile",
            "infrastructure/**/Dockerfile",
            "**/render.y*ml",
            "docker-compose*.yml",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: SCRIPT-INTELLIGENCE v9 — অডিট টার্গেট অটো-ডিসকভারি লেয়ার
# ─────────────────────────────────────────────────────────────────────────────

def _relocate_target(root_path: Path, seed: str) -> tuple[Path | None, str]:
    """Try to re-find a missing seed by unique basename anywhere in the repo.

    বাংলা মন্তব্য: হারানো টার্গেট ফাইল/ডিরেক্টরি রিপোর অন্য কোথাও একক ম্যাচ
    হলে সেখানে স্থানান্তর (relocate) করা হয়; একাধিক ম্যাচ হলে অস্পষ্টতার কারণে বাদ।
    """
    name = Path(seed.rstrip("/")).name
    if seed.endswith("/"):
        hits = sorted(
            p for p in root_path.glob(f"**/{name}")
            if p.is_dir() and not any(part in SKIP_DIRS for part in p.parts)
        )
    else:
        hits = discover_files(root_path, (f"**/{name}",))
    if len(hits) == 1:
        return hits[0], "relocated"
    if len(hits) > 1:
        preview = ", ".join(str(h) for h in hits[:3])
        return None, f"ambiguous — {len(hits)} candidates ({preview}, ...)"
    return None, "no basename match in repo"


def _resolve_part_targets(
    root_path: Path,
    part_name: str,
    meta: dict,
    verbose: bool = True,
) -> tuple[list[Path], list[tuple[str, str]]]:
    """Resolve one audit part's targets through the discovery ladder.

    Returns (resolved_targets, events) where events is a list of
    (seed, status) pairs for the INDEX.md discovery-coverage section.
    """
    seeds: list[str] = list(meta.get("target_paths", []))
    resolved: list[Path] = []
    seen: set[Path] = set()
    events: list[tuple[str, str]] = []

    def _add(p: Path) -> bool:
        rp = p.resolve()
        if rp in seen:
            return False
        seen.add(rp)
        resolved.append(p)
        return True

    # 1+2. literal seeds — kept if they exist, else relocation attempt
    existing = existing_paths(seeds, relative_to=root_path)
    existing_set = {p.resolve() for p in existing}
    for seed in seeds:
        cand = root_path / seed
        if cand.resolve() in existing_set:
            if _add(cand) and verbose:
                print(f"    [discovery] seed ok: {seed}")
            events.append((seed, "ok"))
            continue
        relocated, why = _relocate_target(root_path, seed)
        if relocated is not None:
            rel = relocated.relative_to(root_path) if relocated.is_relative_to(root_path) else relocated
            if verbose:
                print(f"    [discovery] relocated {seed} -> {rel}")
            events.append((seed, f"relocated -> {rel}"))
            _add(relocated)
        else:
            print(f"    [discovery] skipping missing {seed} ({why})")
            events.append((seed, f"skipped ({why})"))

    # 3. role-based auto-tracking globs
    for pat in meta.get("discover_globs", []):
        hits = [h for h in discover_files(root_path, (pat,)) if h.resolve() not in seen]
        for h in hits:
            _add(h)
        if verbose:
            print(f"    [discovery] pattern {pat}: {len(hits)} file(s)")

    return resolved, events


def discover_audit_targets(project_root: str | Path | None = None) -> dict[str, list[Path]]:
    """Resolve every audit part's targets via discovery (public API for tests).

    বাংলা মন্তব্য: সব পার্টের চূড়ান্ত টার্গেট তালিকা — কোনো হার্ডকোডেড ইনভেন্টরি নেই।
    """
    root_path = Path(project_root).resolve() if project_root else get_layout().root
    return {
        fname: _resolve_part_targets(root_path, fname, meta, verbose=False)[0]
        for fname, meta in AUDIT_PARTS.items()
    }


def discover_uncovered_core(root_path: Path, covered: set[Path]) -> list[Path]:
    """Top-level ``backend/core/*.py`` modules claimed by NO audit part.

    বাংলা মন্তব্য: কভারেজ সুইপ — নতুন কোর মডিউল যেন নীরবে অ-অডিটেড থাকতে না পারে।
    """
    core_dir = root_path / "backend" / "core"
    if not core_dir.is_dir():
        return []
    covered_rel: set[str] = set()
    for p in covered:
        try:
            covered_rel.add(p.resolve().relative_to(root_path).as_posix())
        except ValueError:
            continue
    out: list[Path] = []
    for py in sorted(core_dir.glob("*.py")):
        rel = py.resolve().relative_to(root_path).as_posix()
        if rel not in covered_rel:
            out.append(py)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: helper ফাংশন — ফাইল সংগ্রহ করে metadata সহ
# ─────────────────────────────────────────────────────────────────────────────

def _should_skip(path: Path) -> bool:
    """বাংলা মন্তব্য: ফাইলটি স্কিপ করা উচিত কিনা তা নির্ধারণ করে।"""
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return True
    if path.name.startswith("."):
        return True
    if path.stat().st_size > MAX_FILE_BYTES:
        return False  # Still embed, but truncated
    return False


def _collect_files(root_path: Path, target: Path | str) -> list[Path]:
    """বাংলা মন্তব্য: একটি target path থেকে সমস্ত eligible ফাইল সংগ্রহ করে।"""
    full_target = Path(target)
    if not full_target.is_absolute():
        full_target = root_path / full_target
    if not full_target.exists():
        return []

    if full_target.is_file():
        return [full_target]

    # Directory — recursively collect, skip forbidden dirs
    collected: list[Path] = []
    for child in sorted(full_target.rglob("*")):
        if not child.is_file():
            continue
        # Check if any parent dir is in SKIP_DIRS
        if any(part in SKIP_DIRS for part in child.parts):
            continue
        if child.suffix.lower() in SKIP_EXTENSIONS:
            continue
        if child.name.startswith("."):
            continue
        collected.append(child)
    return collected


def _get_git_log(filepath: Path, root_path: Path) -> str:
    """বাংলা মন্তব্য: ফাইলের সর্বশেষ ৩টি git commit সংক্ষিপ্তভাবে দেখায়।"""
    try:
        rel = str(filepath.relative_to(root_path)).replace("\\", "/")
        result = subprocess.run(
            ["git", "log", "--oneline", "-3", "--", rel],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root_path, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return "\n".join(f"  - `{ln}`" for ln in lines)
        return "  - *(no commits yet)*"
    except Exception:  # noqa: BLE001
        return "  - *(git log unavailable)*"


def _estimate_tokens(text: str) -> int:
    """বাংলা মন্তব্য: Rough token estimate (1 token ≈ 4 chars for English code)."""
    return max(1, len(text) // 4)


def _embed_file(filepath: Path, rel_path: str, root_path: Path) -> tuple[str, dict]:
    """বাংলা মন্তব্য: একটি ফাইলের সম্পূর্ণ content markdown codeblock-এ embed করে।"""
    ext = filepath.suffix.lower()
    lang = EXT_TO_LANG.get(ext, ext.lstrip(".") or "text")
    # Special case: Dockerfile
    if filepath.name.lower() == "dockerfile":
        lang = "dockerfile"

    size_bytes = filepath.stat().st_size
    try:
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        mtime = "unknown"

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        content = f"# Error reading file: {exc}"

    line_count = content.count("\n") + 1
    truncated = ""
    if size_bytes > MAX_FILE_BYTES:
        # Embed first 120 lines + last 20 lines with a note
        lines = content.splitlines()
        head = "\n".join(lines[:120])
        tail = "\n".join(lines[-20:])
        content = f"{head}\n\n# ... [{line_count - 140} lines truncated — file too large] ...\n\n{tail}"
        truncated = " ⚠️ *truncated*"

    git_log = _get_git_log(filepath, root_path)

    block = (
        f"### 📄 `{rel_path}`{truncated}\n\n"
        f"> **Size:** `{size_bytes:,} bytes` | "
        f"**Lines:** `{line_count:,}` | "
        f"**Modified:** `{mtime}`\n>\n"
        f"> **Recent commits:**\n{git_log}\n\n"
        f"```{lang}\n{content}\n```\n"
    )
    meta = {
        "path": rel_path,
        "size_bytes": size_bytes,
        "lines": line_count,
        "tokens": _estimate_tokens(content),
    }
    return block, meta


# ─────────────────────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: AI-optimized audit prompt — যেকোনো AI সর্বোচ্চ মানের রিভিউ দিতে পারবে
# ─────────────────────────────────────────────────────────────────────────────

def _build_ai_audit_prompt(title: str, description: str, focus_areas: list[str]) -> str:
    areas_md = "\n".join(f"  - {a}" for a in focus_areas)
    return f"""## 🤖 AI Audit Instructions

> **You are acting as a Senior Security & Code Quality Auditor.**
> This document is **100% self-contained** — all source code is embedded below.
> You do NOT need access to any external repository or file system.

### Your Mission
Perform a **deep, exhaustive audit** of the **{title}** subsystem.
Your audit must be production-grade — do not give vague or generic feedback.

### Mandatory Focus Areas for This Module
{areas_md}

### Required Output Format
For every issue found, provide **exactly**:
1. **🔴 Severity:** `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `INFO`
2. **📁 File + Line:** e.g. `backend/core/llm_router.py:L142`
3. **🐛 Issue Title:** One-line summary
4. **📖 Description:** What is wrong and why it matters
5. **🛠️ Delta Patch:** Exact code fix (before/after diff)
6. **✅ Test Suggestion:** How to verify the fix

### Quality Gates (you must meet ALL of these)
- [ ] Zero hallucinations — only cite actual code lines visible in Section 3
- [ ] Every CRITICAL/HIGH issue must have a working patch
- [ ] Do not repeat pre-existing comments as issues
- [ ] Check for Bangla comments (`# বাংলা মন্তব্য`) — verify they match the code logic
- [ ] Flag any `# TODO`, `pass`, or `NotImplemented` left in production paths

---"""


# ─────────────────────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: মূল generation ফাংশন
# ─────────────────────────────────────────────────────────────────────────────

def generate_audit_markdowns(
    project_root: str | Path | None = ".",
    output_dir: str | Path | None = None,
    dry_run: bool = False,
) -> None:
    """
    বাংলা মন্তব্য: সম্পূর্ণ monorepo স্ক্যান করে ১৪টি AI-optimized audit ফাইল তৈরি করে।
    সব ফাইল docs/autogen/modular_audits/ ফোল্ডারে যাবে।

    SCRIPT-INTELLIGENCE v9: ``project_root=None`` auto-discovers the repo root
    via scripts/lib/auto_discovery.py; audit targets are resolved per part by
    the discovery ladder (seed -> relocate -> discover_globs -> skip-with-note).
    """
    if project_root is None:
        root_path = get_layout().root
    else:
        root_path = Path(project_root).resolve()

    if output_dir is not None:
        output_dir = Path(output_dir)
    else:
        env_dir = os.getenv("SUPREMEAI_AUDIT_OUTPUT_DIR")
        output_dir = Path(env_dir) if env_dir else root_path / "docs" / "autogen" / "modular_audits"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n{'='*70}")
    print("  SupremeAI 2.0 — Elite Modular Audit Generator v2.1 (discovery-driven)")
    print(f"  Repo    : {root_path}")
    print(f"  Output  : {output_dir}")
    print(f"  Started : {timestamp}")
    print(f"{'='*70}\n")

    tracked_py = discover_py_files()
    print(f"[discovery] {len(tracked_py)} tracked python files indexed for the coverage sweep")

    # ── Resolve every part's targets through the discovery ladder ────────────
    part_targets: dict[str, list[Path]] = {}
    part_events: dict[str, list[tuple[str, str]]] = {}
    for filename, meta in AUDIT_PARTS.items():
        print(f"[discovery] resolving targets for {filename}")
        resolved, events = _resolve_part_targets(root_path, filename, meta)
        part_targets[filename] = resolved
        part_events[filename] = events

    total_targets = sum(len(t) for t in part_targets.values())
    try:
        require(total_targets, "audit part targets across all 14 parts")
    except DiscoveryError as exc:
        print(f"\n[FATAL] {exc}")
        raise

    index_rows: list[str] = []
    grand_total_files = 0
    grand_total_bytes = 0
    grand_total_tokens = 0
    all_covered: set[Path] = set()

    for filename, meta in AUDIT_PARTS.items():
        filepath = output_dir / filename
        title = meta["title"]
        description = meta["description"]
        focus_areas = meta.get("focus_areas", [])

        print(f"  [>] Generating {filename} ...", end="", flush=True)

        # ── Collect all files from the DISCOVERED targets ──────────────────
        all_files: list[Path] = []
        for target in part_targets[filename]:
            all_files.extend(_collect_files(root_path, target))

        # De-duplicate (in case of overlapping target paths)
        seen: set[Path] = set()
        unique_files: list[Path] = []
        for f in all_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        all_covered.update(unique_files)

        # ── Build inventory + embedded blocks ─────────────────────────────
        inventory_lines: list[str] = []
        embedded_blocks: list[str] = []
        part_files = 0
        part_bytes = 0
        part_tokens = 0

        for child in unique_files:
            rel = str(child.relative_to(root_path)).replace("\\", "/")
            size = child.stat().st_size
            block, file_meta = _embed_file(child, rel, root_path)
            inventory_lines.append(
                f"| `{rel}` | {size:,} B | {file_meta['lines']:,} | ~{file_meta['tokens']:,} |"
            )
            embedded_blocks.append(block)
            part_files += 1
            part_bytes += size
            part_tokens += file_meta["tokens"]

        grand_total_files += part_files
        grand_total_bytes += part_bytes
        grand_total_tokens += part_tokens

        inventory_md = "\n".join(inventory_lines) if inventory_lines else "*(no files found)*"
        source_dump = "\n---\n".join(embedded_blocks) if embedded_blocks else "*(no source files)*"
        ai_prompt = _build_ai_audit_prompt(title, description, focus_areas)

        # ── Write part file ────────────────────────────────────────────────
        content = f"""# {title}

> **Audit Generated:** `{timestamp}`
> **Description:** {description}
> **Files:** `{part_files}` | **Total Size:** `{part_bytes:,} bytes` | **Est. Tokens:** `~{part_tokens:,}`
> **Status:** `SELF_CONTAINED — READY FOR AI AUDIT`

---

{ai_prompt}

---

## 2. 📁 File Inventory

| File Path | Size | Lines | Est. Tokens |
|-----------|------|-------|-------------|
{inventory_md}

**Totals:** `{part_files}` files · `{part_bytes:,}` bytes · `~{part_tokens:,}` tokens

---

## 3. 📦 Complete Source Code

> **Instructions for AI:** Read ALL code below before writing any findings.
> Line numbers in your output must match the actual code shown here.

{source_dump}

---

## 4. 🔴 Identified Vulnerabilities & Issues

*Populate this section by feeding Section 2 + Section 3 into your AI auditor.*

<!-- AUDIT_START -->
<!-- AUDIT_END -->

---

## 5. 🛠️ Recommended Delta Patches

*Each patch must be in unified diff format with file path and line numbers.*

---

## 6. ✅ Verification Checklist

- [ ] All CRITICAL/HIGH patches applied and tested
- [ ] Regression tests pass for changed files
- [ ] Bangla comments updated to reflect changes
- [ ] No new `# TODO` or `pass` introduced in production paths

---
*Generated by SupremeAI 2.0 Elite Audit Generator v2.1*
"""
        if dry_run:
            size_kb = len(content) / 1024
            print(f" [DRY-RUN] ({part_files} files, {size_kb:.0f} KB, ~{part_tokens:,} tokens — not written)")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            size_kb = len(content) / 1024
            print(f" [OK] ({part_files} files, {size_kb:.0f} KB, ~{part_tokens:,} tokens)")

        # Index entry
        index_rows.append(
            f"| [{filename}](./{filename}) | {part_files} | {part_bytes:,} B | ~{part_tokens:,} |"
        )

    # ── Coverage sweep: core modules claimed by no part ────────────────────
    uncovered_core = discover_uncovered_core(root_path, all_covered)
    uncovered_md = (
        "\n".join(f"- `{p.resolve().relative_to(root_path).as_posix()}`" for p in uncovered_core)
        if uncovered_core else "*(none — every top-level core module is claimed by a part)*"
    )

    # ── Stale-seed event table for INDEX ───────────────────────────────────
    event_rows: list[str] = []
    for filename, events in part_events.items():
        for seed, status in events:
            if status != "ok":
                event_rows.append(f"| `{seed}` | {filename.replace('.md', '')} | {status} |")
    events_md = "\n".join(event_rows) if event_rows else "*(none — every seed resolved)*"

    # ── Generate master INDEX.md ───────────────────────────────────────────
    index_path = output_dir / "INDEX.md"
    index_table = "\n".join(index_rows)
    index_content = f"""# SupremeAI 2.0 — Modular Audit Index

> **Generated:** `{timestamp}`
> **Total Files Covered:** `{grand_total_files}`
> **Total Codebase Size:** `{grand_total_bytes:,} bytes`
> **Total Estimated Tokens:** `~{grand_total_tokens:,}`

---

## How to Use These Audits

1. **Pick a Part** from the table below based on what you want audited.
2. **Open the Part file** — it contains everything (instructions, code, checklist).
3. **Paste the full Part file** into your AI assistant (GPT-4o / Claude / Gemini).
4. **The AI will self-audit** using the embedded instructions and source code.
5. **Paste the AI's output** back into Section 4 (Vulnerabilities) of the Part file.

> **Tip:** For maximum audit quality, use a model with **128K+ context window**
> and instruct it to read ALL of Section 3 before answering.

---

## Part Index

| Part File | Files | Size | Est. Tokens |
|-----------|-------|------|-------------|
{index_table}

---

## Audit Coverage Map

```
SupremeAI 2.0 Monorepo
├── backend/
│   ├── core/llm*           → PART_01 (LLM Gateway)
│   ├── core/security/      → PART_02 (Security Guardrails)
│   ├── database/           → PART_03 (Multi-DB Outbox)
│   ├── core/auto_heal*     → PART_04 (Self-Evolution)
│   ├── core/resilience/    → PART_04 (Self-Evolution, discovered)
│   ├── core/swarm_*        → PART_05 (WebSockets)
│   ├── api/routes/admin_routes* → PART_05 (Admin Auth)
│   ├── p2p/                → PART_06 (P2P Compute)
│   ├── core/microvm*       → PART_06 (Sandboxing)
│   ├── api/                → PART_07 (API Routers)
│   └── tools/              → PART_08 (AI Agent Tools)
├── frontend/src/           → PART_09 (React Studio Client, discovered)
├── packages/               → PART_11 (Shared Types)
├── backend/tests/          → PART_12 (Test Suite)
├── .github/workflows/      → PART_13 (CI/CD)
├── scripts/                → PART_13 (DevOps Scripts)
└── infrastructure/         → PART_14 (Cloud Infra)
```

---

## 🔍 Discovery Coverage (SCRIPT-INTELLIGENCE v9)

> Audit targets are auto-discovered via `scripts/lib/auto_discovery.py` — stale
> seeds are skipped with a note (never phantom rows) and role patterns track
> successors across renames/moves.

**Stale/rotted seeds handled by discovery:**

| Seed | Part | Discovery outcome |
|------|------|-------------------|
{events_md}

**Uncovered top-level `backend/core/*.py`** (visible to discovery, claimed by no part — review grouping):

{uncovered_md}

---
*SupremeAI 2.0 Elite Audit Generator v2.1*
"""
    if dry_run:
        print(f"\n[DRY-RUN] INDEX.md ({len(index_content)} chars) not written")
        print(f"[DRY-RUN] coverage sweep: {len(uncovered_core)} uncovered backend/core top-level modules")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        index_path.write_text(index_content, encoding="utf-8")

    print(f"\n{'='*70}")
    if dry_run:
        print("  [DRY-RUN] Nothing written (part files + INDEX.md built in memory only)")
    else:
        print(f"  [OK] INDEX.md generated: {index_path}")
    print(f"  [+]  Grand Total: {grand_total_files} files · "
          f"{grand_total_bytes:,} bytes · ~{grand_total_tokens:,} tokens")
    print(f"  [i]  Discovery: {total_targets} targets resolved across 14 parts · "
          f"{len(uncovered_core)} uncovered core modules reported")
    print(f"  [/]  Output: {output_dir}")
    print(f"{'='*70}\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (SCRIPT-INTELLIGENCE v9)."""
    parser = argparse.ArgumentParser(
        prog="generate_modular_audits.py",
        description="Elite Modular Audit Generator — discovery-driven (SCRIPT-INTELLIGENCE v9)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Target discovery ladder (per audit part):
  1. literal seed exists on disk       -> used as-is
  2. seed missing                      -> unique-basename relocation anywhere in repo
  3. part 'discover_globs' patterns    -> role-based auto-tracking (survives renames)
  4. still missing                     -> skipped with "[discovery] skipping missing" note

Env overrides:
  SUPREMEAI_AUDIT_OUTPUT_DIR   pin the output directory
  SUPREMEAI_REPO_ROOT          pin the repo root (see scripts/lib/auto_discovery.py)

Examples:
  %(prog)s --list-targets                  # show resolved targets per part, write nothing
  %(prog)s --dry-run                       # full generation pass, no files written
  %(prog)s --output-dir /tmp/audits        # generate somewhere else
""")
    parser.add_argument(
        "--project-root", default=None,
        help="Repo root (default: auto-discovered via scripts/lib/auto_discovery.py)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: <root>/docs/autogen/modular_audits, env SUPREMEAI_AUDIT_OUTPUT_DIR)",
    )
    parser.add_argument(
        "--list-targets", action="store_true",
        help="Print the discovered audit targets per part and exit (no files written)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Resolve discovery and build every part in memory; write nothing",
    )
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve() if args.project_root else get_layout().root

    if args.list_targets:
        print(f"[discovery] repo root: {root}")
        grand = 0
        for fname, meta in AUDIT_PARTS.items():
            print(f"\n{fname} — {meta['title']}")
            targets, _events = _resolve_part_targets(root, fname, meta)
            grand += len(targets)
        print(f"\n[discovery] TOTAL: {grand} resolved targets across {len(AUDIT_PARTS)} parts")
        return 0

    generate_audit_markdowns(
        project_root=root,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
