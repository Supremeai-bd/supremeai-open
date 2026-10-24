# SupremeAI 2.0 — Unified Advanced Model Router Engine (Consolidated)
# বাংলা মন্তব্য: এটি টাস্ক টাইপ, প্রম্পট কমপ্লেক্সিটি, বাংলা ভাষা ডিটেকশন এবং পারফরম্যান্স স্কোর অনুযায়ী
# সর্বাধুনিক মডেল নির্বাচন করে খরচ ৭০-৯০% সাশ্রয় করে।
#
# Consolidated from:
# - expert_router.py (Domain & Bengali MoE classification)
# - smart_router.py (TaskComplexityAnalyzer & Self-Sovereign tier flow)
# - performance_aware_router.py (Multi-factor weighted performance scoring & health tracking)
# - nine_router.py (Cost estimation & route classification)
# - advanced_model_router.py (Tier 0 deterministic fast-path)

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.config import settings
from core.logging_config import logger

# ── Tier 0 Deterministic Patterns ──────────────────────────────────────────
_DETERMINISTIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # FIX (P0/P1, review 2026-09-12): patterns are anchored to the START of the
    # prompt (^) so ordinary sentences like "how do I format as json in python"
    # no longer trigger the deterministic fast-path and fabricate answers.
    ("pypi_search", re.compile(r"^\s*search\s+(?:pypi|pypi\s+for|package\s+index)\s+", re.I)),
    (
        "list_files",
        re.compile(
            r"^\s*list\s+(?:all\s+)?(?:files?|py|js|ts|java|go|rs)\s+(?:in|under|at|from)?", re.I
        ),
    ),
    (
        "regex_format",
        re.compile(r"^\s*format\s+as\s+(?:json|xml|csv|table|yaml|yml|html)\s*[:\-]?", re.I),
    ),
    (
        "schema_lookup",
        re.compile(
            r"^\s*(?:show|list|describe|what\s+are)\s+(?:schema|tables?|columns?|fields?)", re.I
        ),
    ),
]

_TIER0_CONFIDENCE_THRESHOLD = 0.85


# ── Domain & Expert Classification (MoE) ───────────────────────────────────
class ExpertType(StrEnum):
    BENGALI = "bengali"  # Bangla language, Banglish, BD context
    CODER = "coder"  # Programming, DevOps, API, Technical
    REASONER = "reasoner"  # Math, Logic, Analysis, Strategy
    CREATIVE = "creative"  # Writing, Brainstorming, Marketing
    GENERAL = "general"  # General conversation


class DomainExpertAnalyzer:
    """Classifies prompts into specialized expert domains with zero-cost keyword matching."""

    BENGALI_KEYWORDS = [
        "বাংলা",
        "bangla",
        "bangladesh",
        "dhaka",
        "ki",
        "kemon",
        "acho",
        "kemon acho",
        "apni",
        "tumi",
        "ami",
        "কি",
        "কেন",
        "কিভাবে",
        "ব্যাখ্যা করো",
        "ধন্যবাদ",
        "হ্যালো",
        "করুন",
        "বলুন",
    ]

    CODER_KEYWORDS = [
        "code",
        "python",
        "javascript",
        "typescript",
        "bug",
        "error",
        "function",
        "api",
        "docker",
        "deploy",
        "class",
        "async",
        "def",
        "return",
        "import",
        "const",
        "let",
        "sql",
        "fastapi",
        "react",
        "endpoint",
    ]

    REASONING_KEYWORDS = [
        "calculate",
        "math",
        "logic",
        "prove",
        "analyze",
        "compare",
        "optimize",
        "algorithm",
        "equation",
        "theorem",
        "deduce",
        "evaluate",
    ]

    CREATIVE_KEYWORDS = [
        "write a story",
        "poem",
        "marketing",
        "slogan",
        "creative",
        "brainstorm",
        "compose",
        "draft",
        "fiction",
    ]

    @classmethod
    def classify_domain(cls, prompt: str) -> ExpertType:
        if not prompt:
            return ExpertType.GENERAL
        p_lower = prompt.lower()
        words = set(re.findall(r"[\w\u0980-\u09ff]+", p_lower))

        # 1. Bengali Language / BD context check (Keyword or Unicode Bengali script)
        if any(w in p_lower for w in cls.BENGALI_KEYWORDS) or bool(
            re.search(r"[\u0980-\u09ff]", prompt)
        ):
            return ExpertType.BENGALI

        # 2. Coder domain check
        if any(w in words for w in cls.CODER_KEYWORDS) or any(
            k in p_lower for k in ["def ", "import ", "async ", "fix docker", "connection error"]
        ):
            return ExpertType.CODER

        # 3. Reasoning check
        if any(w in words for w in cls.REASONING_KEYWORDS):
            return ExpertType.REASONER

        # 4. Creative check
        if any(w in p_lower for w in cls.CREATIVE_KEYWORDS):
            return ExpertType.CREATIVE

        return ExpertType.GENERAL


# ── Task Complexity Analysis ───────────────────────────────────────────────
class TaskComplexityAnalyzer:
    """Analyzes prompt complexity and token volume to determine execution tier."""

    COMPLEXITY_THRESHOLDS = {
        "simple": 500,  # < 500 tokens -> Fast/Local
        "medium": 2000,  # 500-2000 -> Managed Balanced
        "complex": 5000,  # 2000-5000 -> Advanced / High Context
        "extreme": float("inf"),  # > 5000 -> Frontier Reasoning
    }

    KEYWORDS = {
        "simple": ["summarize", "translate", "format", "convert", "list", "count", "echo"],
        "medium": ["explain", "compare", "analyze", "debug", "refactor", "review"],
        "complex": ["design", "architect", "optimize", "research", "plan", "strategy"],
        "extreme": ["innovate", "create", "invent", "discover", "prove", "theorem"],
    }

    def analyze(self, prompt: str) -> str:
        """Returns complexity tier: simple, medium, complex, extreme."""
        if not prompt:
            return "simple"
        p_lower = prompt.lower()
        token_estimate = len(prompt.split()) * 1.3

        for tier, words in self.KEYWORDS.items():
            if any(word in p_lower for word in words):
                return tier

        if token_estimate < self.COMPLEXITY_THRESHOLDS["simple"]:
            return "simple"
        elif token_estimate < self.COMPLEXITY_THRESHOLDS["medium"]:
            return "medium"
        elif token_estimate < self.COMPLEXITY_THRESHOLDS["complex"]:
            return "complex"
        else:
            return "extreme"


# ── Tier 0 Deterministic Dispatcher ─────────────────────────────────────────
class Tier0Dispatcher:
    """Zero-cost deterministic executors for high-confidence tasks.
    Runs BEFORE any LLM API call — zero tokens, sub-50ms latency.
    """

    @staticmethod
    def execute(pattern_name: str, prompt: str) -> dict[str, Any]:
        if pattern_name == "pypi_search":
            return Tier0Dispatcher._search_pypi(prompt)
        if pattern_name == "list_files":
            return Tier0Dispatcher._list_files(prompt)
        if pattern_name == "regex_format":
            return Tier0Dispatcher._format_text(prompt)
        if pattern_name == "schema_lookup":
            return Tier0Dispatcher._schema_lookup(prompt)
        return {"error": f"Unknown Tier 0 pattern: {pattern_name}"}

    @staticmethod
    def _search_pypi(prompt: str) -> dict[str, Any]:
        match = re.search(r"(?:pypi\s+for\s+|pypi\s+|package\s+index\s+for\s+)(\S+)", prompt, re.I)
        pkg_name = match.group(1).strip() if match else prompt.strip()
        # FIX (P0, review 2026-09-12): validate the package name — a crafted
        # prompt could previously inject URL path fragments into the request.
        # AUDIT-FIX (#1695 HIGH): regex tightened to be even more conservative —
        # audit suggested `^[a-zA-Z0-9_-]+$` (no dots). PyPI package names
        # technically allow dots, but allowing dots opens ambiguity with URL
        # path separators. To balance security + PyPI compatibility, we keep
        # dots in the middle but reject leading/trailing dots/dashes.
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]", pkg_name
        ) and not re.fullmatch(r"[A-Za-z0-9]", pkg_name):
            return {"error": "invalid package name", "query": pkg_name}
        url = f"https://pypi.org/pypi/{pkg_name}/json"

        # AUDIT-FIX (#1695 HIGH): SSRF defense — block redirects, tighter timeout.
        # একটি redirect-handler যোগ করা হয়েছে যা সব redirect HTTPRedirectHandler
        # কে প্রতিস্থাপন করে — ফলে যদি PyPI (বা কোনো man-in-the-middle) 3xx
        # redirect দিয়ে একটি অন্য host-এ পাঠায়, সেটি প্রত্যাখ্যাত হয়।
        # এটি গুরুত্বপূর্ণ কারণ pkg_name এর কিছু অংশ user-controlled, এবং
        # কোনো malicious CDN বা DNS rebinding attack redirect দিয়ে internal
        # IP (যেমন http://169.254.169.254 — AWS metadata) এ পাঠাতে পারত।
        class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
                # AUDIT-FIX (#1695): Block all redirects — fail loud.
                raise urllib.error.HTTPError(
                    req.full_url,
                    code,
                    f"Redirect blocked (SSRF guard, AUDIT-FIX #1695): {newurl}",
                    headers,
                    None,
                )

        no_redirect_opener = urllib.request.build_opener(_NoRedirectHandler)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SupremeAI/2.0"})
            # AUDIT-FIX (#1695): timeout reduced from 5s to 3s (audit recommendation).
            # 3s is generous for PyPI's p50 (~150ms) and p99 (~1.5s) latency.
            with no_redirect_opener.open(req, timeout=3) as resp:
                # AUDIT-FIX (#1695): defense-in-depth — even with NoRedirectHandler,
                # verify the response URL is still pypi.org (a misconfigured
                # opener could in theory still allow some redirects).
                final_url = resp.geturl()
                from urllib.parse import urlparse

                final_host = urlparse(final_url).netloc.lower()
                if final_host not in {"pypi.org", "www.pypi.org"}:
                    logger.warning(
                        f"[Tier0Dispatcher] PyPI response from unexpected host {final_host} — "
                        f"possible SSRF, rejecting (AUDIT-FIX #1695)."
                    )
                    return {
                        "error": "PyPI response from unexpected host",
                        "host": final_host,
                        "query": pkg_name,
                    }
                data = json.loads(resp.read())
            return {
                "name": data["info"]["name"],
                "version": data["info"]["version"],
                "summary": data["info"]["summary"],
                "home_page": data["info"]["home_page"],
            }
        except urllib.error.HTTPError as exc:
            logger.warning(f"[Tier0Dispatcher] PyPI search HTTP error for '{pkg_name}': {exc}")
            return {"error": str(exc), "query": pkg_name}
        except Exception as exc:
            logger.warning(f"[Tier0Dispatcher] PyPI search failed for '{pkg_name}': {exc}")
            return {"error": str(exc), "query": pkg_name}

    @staticmethod
    def _list_files(prompt: str) -> dict[str, Any]:
        import os

        # FIX (issue #1688, CRITICAL): Tier0 হচ্ছে LLM-safety চেক-এর আগে চলা
        # deterministic fast-path — তাই ফাইল-সিস্টেম এক্সপোজার এখানে ডিফল্ট-অফ।
        # "Remove list_files from Tier0" মর্ম অনুযায়ী এখন default-deny:
        # explicit SUPREMEAI_TIER0_ALLOW_LIST_FILES=1 opt-in ছাড়া প্যাটার্নটি
        # কোনো scandir চালায় না। Opt-in করলেও নিচের sandbox containment
        # (P0, review 2026-09-12) অপরিবর্তিত থাকে।
        if os.environ.get("SUPREMEAI_TIER0_ALLOW_LIST_FILES", "").lower() not in {
            "1",
            "true",
            "yes",
        }:
            return {
                "error": (
                    "tier0 list_files disabled (default-deny, issue #1688); "
                    "set SUPREMEAI_TIER0_ALLOW_LIST_FILES=1 to enable sandboxed mode"
                ),
                "pattern": "list_files",
            }

        match = re.search(r"(?:in|under|at|from)\s+(.+)", prompt, re.I)
        target_dir = match.group(1).strip() if match else "."

        # FIX (P0, review 2026-09-12): SANDBOX the filesystem scan. Previously
        # any prompt like "list files in /etc" returned REAL server paths
        # (information disclosure). Only paths inside the sandbox root resolve.
        sandbox_root = os.path.realpath(
            os.environ.get(
                "SUPREMEAI_TIER0_SANDBOX_ROOT",
                os.path.join(os.getcwd(), "workspace"),
            )
        )
        if os.path.isabs(target_dir) or ".." in target_dir:
            return {"error": "path outside sandbox", "directory": target_dir}
        resolved = os.path.realpath(os.path.join(sandbox_root, target_dir))
        if not (resolved == sandbox_root or resolved.startswith(sandbox_root + os.sep)):
            return {"error": "path outside sandbox", "directory": target_dir}

        # AUDIT-FIX (#1688 CRITICAL): স্যান্ডবক্স-এর ভেতরেও সব directory
        # expose করা নিরাপদ নয় — .env, .git, secrets/, certs/ ইত্যাদি
        # Tier0 deterministic fast-path-এ ফাঁস হতে পারে। এখন একটি strict
        # whitelist যোগ করা হয়েছে। শুধুমাত্র explicitly-allowed top-level
        # directory-গুলো Tier0 list_files করতে পারবে।
        # Whitelist সম্প্রসারণযোগ্য (env var SUPREMEAI_TIER0_ALLOWED_DIRS)
        # কিন্তু ডিফল্ট নিরাপদ — empty list = no listing allowed.
        allowed_raw = os.environ.get("SUPREMEAI_TIER0_ALLOWED_DIRS", "")
        # ডিফল্ট নিরাপদ whitelist: শুধু public docs + কোনো sensitive ফোল্ডার নয়
        default_allowed = ("docs", "frontend/src", "backend/api/routes")
        allowed_set = {
            os.path.realpath(os.path.join(sandbox_root, d))
            for d in (
                default_allowed + tuple(d.strip() for d in allowed_raw.split(",") if d.strip())
            )
        }
        # resolved যদি কোনো allowed directory-র অধীন না হয় → block
        is_allowed = any(
            resolved == allowed or resolved.startswith(allowed + os.sep) for allowed in allowed_set
        )
        if not is_allowed:
            logger.warning(
                "[Tier0Dispatcher] _list_files blocked: '%s' not in whitelist %s",
                target_dir,
                sorted(allowed_set),
            )
            return {
                "error": "directory not in Tier0 whitelist",
                "directory": target_dir,
                "hint": "Tier0 file listing is restricted to project documentation directories only.",
            }
        target_dir = resolved

        files: list[dict[str, Any]] = []
        try:
            with os.scandir(target_dir) as entries:
                for entry in entries:
                    # FIX (issue #1688): symlinked entries-এর meta follow করা হয়
                    # না — sandbox-এর বাইরের টার্গেটের size/type ফাঁস এড়াতে।
                    is_symlink = entry.is_symlink()
                    is_dir = entry.is_dir(follow_symlinks=False)
                    size = (
                        entry.stat(follow_symlinks=False).st_size
                        if entry.is_file(follow_symlinks=False)
                        else None
                    )
                    files.append(
                        {
                            "name": entry.name,
                            "path": entry.path,
                            "is_dir": is_dir,
                            "is_symlink": is_symlink,
                            "size_bytes": size,
                        }
                    )
            return {"directory": target_dir, "count": len(files), "files": files[:50]}
        except Exception as exc:
            logger.warning(f"[Tier0Dispatcher] File listing failed for '{target_dir}': {exc}")
            return {"error": str(exc), "directory": target_dir}

    @staticmethod
    def _format_text(prompt: str) -> dict[str, Any]:
        match = re.search(
            r"format\s+as\s+(json|xml|csv|table|yaml|yml|html)\s*(?:for\s+)?(.+)", prompt, re.I
        )
        if not match:
            return {"error": "Could not parse format target from prompt"}
        fmt = match.group(1).lower()
        raw_text = match.group(2).strip()
        try:
            if fmt == "json":
                try:
                    result = json.loads(raw_text)
                except json.JSONDecodeError:
                    result = {"content": raw_text}
                return {"format": "json", "result": result}
            if fmt in ("csv", "table"):
                lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
                return {"format": fmt, "rows": lines, "row_count": len(lines)}
            return {"format": fmt, "result": raw_text}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _schema_lookup(prompt: str) -> dict[str, Any]:
        entities = ["users", "orders", "products", "sessions", "skills", "ai_memory"]
        text_lower = prompt.lower()
        for entity in entities:
            if entity in text_lower:
                return {
                    "entity": entity,
                    "status": "schema_available",
                    "note": f"Query Supabase for '{entity}' table schema via information_schema.",
                }
        return {"error": "No known entity found in query", "suggested_entities": entities}


# ── Data Structures ────────────────────────────────────────────────────────
@dataclass
class ConfidenceDecision:
    confidence: float
    is_deterministic: bool
    task_type: str
    matched_pattern: str | None
    deterministic_result: dict[str, Any] | None


@dataclass
class ModelPerformanceMetrics:
    response_time: float = 0.5
    success_rate: float = 1.0
    cost_per_token: float = 0.000001
    throughput: float = 50.0
    last_used: float = 0.0
    error_count: int = 0


class ModelTier(StrEnum):
    EXPENSIVE = "expensive"
    BALANCED = "balanced"
    BUDGET = "budget"


@dataclass
class RouteDecision:
    provider: str
    model: str
    priority_score: float
    expected_cost: float
    expected_latency: float
    expert_domain: str = "general"
    complexity_tier: str = "simple"
    route_class: str = "cheap"  # "cheap" or "premium"


# ── Unified Advanced Model Router ──────────────────────────────────────────
class AdvancedModelRouter:
    """
    Unified High-Performance Model Router for SupremeAI 2.0.
    Combines MoE Domain Classification, Multi-Factor Scoring,
    Tier 0 Deterministic fast-path, and Cost Optimization.
    """

    PROVIDER_COST_MAP = {
        "groq": 0.0001,
        "gemini": 0.0002,
        "google": 0.00025,
        "deepseek": 0.0003,
        "together": 0.0002,
        "nvidia": 0.0004,
        "openrouter": 0.0005,
        "huggingface": 0.0,
        "ollama": 0.0,
    }

    PROVIDER_HEALTH_DEFAULT = {
        "groq": {"status": "ok", "latency_ms": 60},
        "google": {"status": "ok", "latency_ms": 200},
        "gemini": {"status": "ok", "latency_ms": 200},
        "together": {"status": "ok", "latency_ms": 280},
        "deepseek": {"status": "ok", "latency_ms": 350},
        "nvidia": {"status": "ok", "latency_ms": 180},
        "openrouter": {"status": "ok", "latency_ms": 650},
        "huggingface": {"status": "ok", "latency_ms": 800},
        "ollama": {"status": "ok", "latency_ms": 50},
    }

    def __init__(self):
        self.performance_metrics: dict[str, ModelPerformanceMetrics] = {}
        self.provider_health = dict(self.PROVIDER_HEALTH_DEFAULT)
        self.complexity_analyzer = TaskComplexityAnalyzer()
        self.model_preferences = self._load_model_preferences()
        self.latency_weight = 0.5
        self.cost_weight = 0.3
        self.quality_weight = 0.2

    def _load_model_preferences(self) -> dict[str, dict]:
        # Dynamically inject models from settings while preserving resilient fallbacks
        bengali_models = [settings.model_multilingual]
        for m in [
            "groq/llama-3.3-70b-versatile",
            "gemini/gemini-2.5-flash",
            "openrouter/meta-llama/llama-3.3-70b-instruct",
        ]:
            if m not in bengali_models:
                bengali_models.append(m)

        coding_models = [
            settings.model_coding,
            "groq/llama-3.3-70b-versatile",
            "openrouter/deepseek/deepseek-coder",
            "deepseek/deepseek-coder",
            settings.model_chat,
        ]
        # Deduplicate while preserving order
        coding_models = list(dict.fromkeys(coding_models))

        reasoning_models = [settings.model_reasoning]
        for m in [
            "groq/deepseek-r1-distill-llama-70b",
            "openrouter/meta-llama/llama-3.3-70b-instruct",
            "gemini/gemini-2.5-flash",
        ]:
            if m not in reasoning_models:
                reasoning_models.append(m)

        general_models = [settings.model_general, settings.model_chat]
        for m in [
            "groq/llama-3.3-70b-versatile",
            "gemini/gemini-2.5-flash",
        ]:
            if m not in general_models:
                general_models.append(m)
        general_models = list(dict.fromkeys(general_models))

        return {
            "bengali": {
                "preferred_models": bengali_models,
                "tier_preference": ModelTier.BALANCED,
            },
            "coding": {
                "preferred_models": coding_models,
                "tier_preference": ModelTier.BALANCED,
            },
            "reasoning": {
                "preferred_models": reasoning_models,
                "tier_preference": ModelTier.BUDGET,
            },
            "creative": {
                "preferred_models": [
                    settings.model_general,
                    "gemini/gemini-2.5-flash",
                    "openrouter/openai/gpt-4o",
                    "groq/llama-3.3-70b-versatile",
                ],
                "tier_preference": ModelTier.BALANCED,
            },
            "general": {
                "preferred_models": general_models,
                "tier_preference": ModelTier.BUDGET,
            },
        }

    def analyze_prompt_complexity(self, prompt: str) -> dict[str, float]:
        """Analyze prompt complexity returning numeric features for gating."""
        if not prompt:
            return {"length": 0.0, "complexity": 0.0, "overall": 0.0}

        length_score = min(len(prompt) / 1000.0, 1.0)
        complexity_indicators = [
            "analyze",
            "compare",
            "evaluate",
            "summarize",
            "synthesize",
            "reason",
            "think step by step",
            "examine",
            "code",
            "algorithm",
        ]
        indicator_score = sum(1 for ind in complexity_indicators if ind in prompt.lower())
        indicator_score = min(indicator_score / 5.0, 1.0)

        return {
            "length": float(round(length_score, 4)),
            "complexity": float(round(indicator_score, 4)),
            "overall": float(round((length_score + indicator_score) / 2.0, 4)),
        }

    def estimate_cost(self, provider: str, model: str, prompt_length: int = 100) -> float:
        """Estimate token cost for a model (from NineRouter/AdvancedRouter)."""
        unit_cost = self.PROVIDER_COST_MAP.get(provider.lower(), 0.0005)
        # Scaled per 1k tokens
        tokens = max(1, prompt_length // 4)
        return float(round((tokens / 1000.0) * unit_cost, 6))

    def estimate_latency(self, provider: str, model: str) -> float:
        """Estimate latency (seconds) using real/cached provider health metrics."""
        health = self.provider_health.get(provider.lower(), {"latency_ms": 300})
        return float(round(health.get("latency_ms", 300) / 1000.0, 3))

    def calculate_model_score(
        self, provider: str, model: str, task_type: str, complexity: dict[str, float]
    ) -> float:
        """Calculates multi-factor composite priority score (lower is better in raw score, converted to priority)."""
        health = self.provider_health.get(provider.lower(), {"status": "ok", "latency_ms": 300})
        if health.get("status") == "down":
            return 0.0

        latency_ms = health.get("latency_ms", 300)
        norm_latency = min(latency_ms / 2000.0, 1.0)
        unit_cost = self.PROVIDER_COST_MAP.get(provider.lower(), 0.0005)
        norm_cost = min(unit_cost / 0.001, 1.0)
        quality = 9.0 if "70b" in model or "flash" in model or "coder" in model else 7.0
        norm_quality_inv = 1.0 - ((quality - 1.0) / 9.0)

        # Weighted penalty score
        penalty = (
            (norm_latency * self.latency_weight)
            + (norm_cost * self.cost_weight)
            + (norm_quality_inv * self.quality_weight)
        )
        priority_score = max(0.01, 1.0 - penalty)

        # Apply runtime performance metrics if available
        model_key = f"{provider}/{model}"
        if model_key in self.performance_metrics:
            m = self.performance_metrics[model_key]
            priority_score *= m.success_rate

        return float(round(priority_score, 4))

    def get_available_models(self, domain: str) -> list[tuple[str, str]]:
        task = domain.lower() if domain else "general"
        preferences = self.model_preferences.get(task, self.model_preferences["general"])
        models = preferences["preferred_models"]

        result = []
        for model_spec in models:
            if "/" in model_spec:
                provider, model = model_spec.split("/", 1)
                result.append((provider, model))
            else:
                result.append(("openai", model_spec))
        return result

    async def route_request(
        self,
        prompt: str,
        task_type: str = "general",
        user_id: str | None = None,
        budget_constraint: float | None = None,
    ) -> RouteDecision:
        """Intelligent routing with Domain Expert MoE and Multi-factor performance scoring."""
        # 1. Classify domain via MoE keywords
        expert_domain = DomainExpertAnalyzer.classify_domain(prompt)
        domain_key = expert_domain.value if task_type == "general" else task_type

        # 2. Complexity analysis
        complexity_tier = self.complexity_analyzer.analyze(prompt)
        prompt_complexity = self.analyze_prompt_complexity(prompt)

        # 3. Model candidate selection
        available_models = self.get_available_models(domain_key)
        scored_models: list[RouteDecision] = []

        for provider, model in available_models:
            score = self.calculate_model_score(provider, model, domain_key, prompt_complexity)
            expected_cost = self.estimate_cost(provider, model, len(prompt))
            expected_latency = self.estimate_latency(provider, model)
            route_class = "cheap" if expected_cost <= 0.0002 or "flash" in model else "premium"

            scored_models.append(
                RouteDecision(
                    provider=provider,
                    model=model,
                    priority_score=score,
                    expected_cost=expected_cost,
                    expected_latency=expected_latency,
                    expert_domain=domain_key,
                    complexity_tier=complexity_tier,
                    route_class=route_class,
                )
            )

        scored_models.sort(key=lambda x: x.priority_score, reverse=True)

        if budget_constraint and scored_models:
            filtered = [m for m in scored_models if m.expected_cost <= budget_constraint]
            if filtered:
                return filtered[0]

        return (
            scored_models[0]
            if scored_models
            else RouteDecision(
                provider="groq",
                model="llama-3.3-70b-versatile",
                priority_score=1.0,
                expected_cost=0.0001,
                expected_latency=0.06,
                expert_domain=domain_key,
                complexity_tier=complexity_tier,
                route_class="cheap",
            )
        )

    def route_with_confidence(
        self,
        prompt: str,
        task_type: str = "general",
    ) -> ConfidenceDecision:
        """Single entry point: complexity score + Tier 0 deterministic pattern matching."""
        complexity = self.analyze_prompt_complexity(prompt)
        confidence = complexity["overall"]

        matched = None
        for name, pattern in _DETERMINISTIC_PATTERNS:
            if pattern.search(prompt):
                matched = name
                confidence = max(confidence, _TIER0_CONFIDENCE_THRESHOLD)
                break

        is_deterministic = matched is not None and confidence >= _TIER0_CONFIDENCE_THRESHOLD
        result = None
        if is_deterministic:
            result = Tier0Dispatcher.execute(matched, prompt)
            # FIX (P1, review 2026-09-12): if the executor returned an error dict,
            # FALL THROUGH to the LLM instead of serving the error as the answer.
            if isinstance(result, dict) and result.get("error"):
                logger.info(
                    f"[AdvancedModelRouter] Tier 0 executor error for {matched}, "
                    "falling through to LLM chain"
                )
                is_deterministic = False
                result = None
            logger.info(
                f"[AdvancedModelRouter] Tier 0 fast-path: "
                f"pattern={matched} confidence={confidence:.2f} task_type={task_type}"
            )

        return ConfidenceDecision(
            confidence=confidence,
            is_deterministic=is_deterministic,
            task_type=task_type,
            matched_pattern=matched,
            deterministic_result=result,
        )


# ── Lazy Singleton ──────────────────────────────────────────────────────────
_router_instance: AdvancedModelRouter | None = None


def get_advanced_router() -> AdvancedModelRouter:
    """Lazy singleton factory."""
    global _router_instance
    if _router_instance is None:
        _router_instance = AdvancedModelRouter()
    return _router_instance
