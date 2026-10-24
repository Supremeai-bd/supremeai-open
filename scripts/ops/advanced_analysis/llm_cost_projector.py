#!/usr/bin/env python3
"""
SupremeAI LLM Cost Projector — কোডবেস বিশ্লেষণ করে মাসিক LLM খরচের প্রজেকশন দেখায়।

ব্যবহার:
    python scripts/llm_cost_projector.py
    python scripts/llm_cost_projector.py --json
    python scripts/llm_cost_projector.py --provider gemini
    python scripts/llm_cost_projector.py --monthly-requests 5000

এক্সিট কোড:
    0 = বাজেটের মধ্যে সব ঠিক আছে
    1 = খরচ নিয়ে সতর্কতা / কনসার্ন
    2 = ত্রুটি (ফাইল পড়তে সমস্যা, পার্সিং এরর)
"""

from __future__ import annotations

# বাংলা: শুধুমাত্র স্ট্যান্ডার্ড লাইব্রেরি ব্যবহার করা হচ্ছে — কোনো external dependency নেই
import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# কনস্ট্যান্ট — রিপোজিটরি পাথ ও স্ক্যান সেটিংস
# ═══════════════════════════════════════════════════════════════════════════════

# বাংলা: স্ক্রিপ্টের অবস্থান থেকে রিপো রুট বের করা হচ্ছে
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"

# বাংলা: কোস্ট বম্ব এলার্ট এর থ্রেশোল্ড — এর উপরে max_tokens হলে সতর্কতা
_COST_BOMB_THRESHOLD = 4000

# বাংলা: মাসিক বাজেট লিমিট (ডলার) — এর উপরে হলে exit code 1
_MONTHLY_BUDGET_LIMIT = 50.0

# ═══════════════════════════════════════════════════════════════════════════════
# মডেল প্রাইসিং টেবিল — প্রতি ১K টোকেন (input/output আলাদা)
# বাংলা: এই তথ্য স্ক্রিপ্টের ভেতরে হার্ডকোড, কোডবেসে নয়
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ModelPricing:
    """বাংলা: একটি মডেলের প্রাইসিং তথ্য ধারণ করে।"""
    provider: str            # প্রোভাইডারের নাম (gemini, groq, ইত্যাদি)
    model_pattern: str      # রিজেক্স প্যাটার্ন যা মডেল নামে ম্যাচ করবে
    cost_per_1k_input: float   # ইনপুট টোকেন প্রতি ১K-এর দাম (USD)
    cost_per_1k_output: float  # আউটপুট টোকেন প্রতি ১K-এর দাম (USD)
    is_free_tier: bool      # ফ্রি টায়ার আছে কিনা
    free_rpd: int = 0       # ফ্রি টায়ারে দৈনিক রিকোয়েস্ট সীমা
    free_tpm: int = 0       # ফ্রি টায়ারে প্রতি মিনিটে টোকেন সীমা
    display_name: str = ""  # মানব-পাঠযোগ্য নাম

# বাংলা: সমস্ত মডেলের প্রাইসিং তথ্য — ২০২৫ এর হালনাগাদ অনুযায়ী
MODEL_PRICING_TABLE: list[ModelPricing] = [
    # ── Google Gemini ──────────────────────────────────────────────
    ModelPricing(
        provider="gemini",
        model_pattern=r"gemini.*2\.0.*flash",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=475,     # config_fields.py থেকে gemini_rpd_limit
        free_tpm=240_000,  # config_fields.py থেকে gemini_tpm_limit
        display_name="Gemini 2.0 Flash (Free)",
    ),
    ModelPricing(
        provider="gemini",
        model_pattern=r"gemini.*1\.5.*flash",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=475,
        free_tpm=240_000,
        display_name="Gemini 1.5 Flash (Free)",
    ),
    ModelPricing(
        provider="gemini",
        model_pattern=r"gemini.*1\.5.*pro",
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
        is_free_tier=True,
        free_rpd=475,
        free_tpm=240_000,
        display_name="Gemini 1.5 Pro",
    ),
    # ── Groq (Llama 3.3 70B) ───────────────────────────────────────
    ModelPricing(
        provider="groq",
        model_pattern=r"llama.*3\.3.*70b",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=13_680,   # config_fields.py থেকে groq_rpd_limit
        free_tpm=28_500,    # config_fields.py থেকে groq_tpm_limit
        display_name="Llama 3.3 70B on Groq (Free)",
    ),
    ModelPricing(
        provider="groq",
        model_pattern=r"llama.*3.*8b",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=13_680,
        free_tpm=28_500,
        display_name="Llama 3 8B on Groq (Free)",
    ),
    ModelPricing(
        provider="groq",
        model_pattern=r"mixtral",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=13_680,
        free_tpm=28_500,
        display_name="Mixtral on Groq (Free)",
    ),
    # ── OpenRouter (বিভিন্ন মডেল) ──────────────────────────────
    ModelPricing(
        provider="openrouter",
        model_pattern=r"claude.*3\.5.*haiku.*free",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=45,        # config_fields.py থেকে openrouter_rpd_limit
        free_tpm=0,
        display_name="Claude 3.5 Haiku via OpenRouter (Free)",
    ),
    ModelPricing(
        provider="openrouter",
        model_pattern=r"meta-llama/llama-3\.3-70b",
        cost_per_1k_input=0.00039,
        cost_per_1k_output=0.00039,
        is_free_tier=False,
        display_name="Llama 3.3 70B via OpenRouter (Paid)",
    ),
    ModelPricing(
        provider="openrouter",
        model_pattern=r"openrouter/auto",
        cost_per_1k_input=0.0003,
        cost_per_1k_output=0.0006,
        is_free_tier=False,
        display_name="OpenRouter Auto (Paid)",
    ),
    # ── Claude (Anthropic) ─────────────────────────────────────────
    ModelPricing(
        provider="claude",
        model_pattern=r"claude.*3\.5.*sonnet",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        is_free_tier=False,
        display_name="Claude 3.5 Sonnet",
    ),
    ModelPricing(
        provider="claude",
        model_pattern=r"claude.*3\.5.*haiku",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.004,
        is_free_tier=False,
        display_name="Claude 3.5 Haiku",
    ),
    ModelPricing(
        provider="claude",
        model_pattern=r"claude.*3.*opus",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        is_free_tier=False,
        display_name="Claude 3 Opus",
    ),
    # ── DeepSeek ───────────────────────────────────────────────────
    ModelPricing(
        provider="deepseek",
        model_pattern=r"deepseek-chat",
        cost_per_1k_input=0.00014,
        cost_per_1k_output=0.00028,
        is_free_tier=False,
        display_name="DeepSeek Chat (V3)",
    ),
    ModelPricing(
        provider="deepseek",
        model_pattern=r"deepseek-reasoner",
        cost_per_1k_input=0.00055,
        cost_per_1k_output=0.00219,
        is_free_tier=False,
        display_name="DeepSeek Reasoner (R1)",
    ),
    # ── Moonshot / Kimi ────────────────────────────────────────────
    ModelPricing(
        provider="moonshot",
        model_pattern=r"kimi",
        cost_per_1k_input=0.0012,
        cost_per_1k_output=0.0012,
        is_free_tier=True,     # বাংলা: Moonshot-এ ফ্রি কোটা আছে
        free_rpd=500,
        free_tpm=0,
        display_name="Moonshot Kimi K2.5",
    ),
    # ── HuggingFace ────────────────────────────────────────────────
    ModelPricing(
        provider="huggingface",
        model_pattern=r"supreme-hybrid",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=950,       # config_fields.py থেকে huggingface_rpd_limit
        free_tpm=0,
        display_name="Supreme Hybrid 8B on HF (Free)",
    ),
    # ── Together AI ───────────────────────────────────────────────
    ModelPricing(
        provider="together",
        model_pattern=r"meta-llama/Llama-3\.3-70B",
        cost_per_1k_input=0.00039,
        cost_per_1k_output=0.00039,
        is_free_tier=False,
        display_name="Llama 3.3 70B on Together AI",
    ),
    # ── OpenAI ─────────────────────────────────────────────────────
    ModelPricing(
        provider="openai",
        model_pattern=r"gpt-4o",
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.01,
        is_free_tier=False,
        display_name="GPT-4o",
    ),
    ModelPricing(
        provider="openai",
        model_pattern=r"gpt-4.*mini",
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        is_free_tier=False,
        display_name="GPT-4o Mini",
    ),
    ModelPricing(
        provider="openai",
        model_pattern=r"gpt-4(?!o)",
        cost_per_1k_input=0.03,
        cost_per_1k_output=0.06,
        is_free_tier=False,
        display_name="GPT-4",
    ),
    # ── NVIDIA ─────────────────────────────────────────────────────
    ModelPricing(
        provider="nvidia",
        model_pattern=r"nvidia",
        cost_per_1k_input=0.0002,
        cost_per_1k_output=0.0002,
        is_free_tier=True,
        free_rpd=5000,
        free_tpm=38_000,    # config_fields.py থেকে nvidia_tpm_limit
        display_name="NVIDIA NIM (Free Tier)",
    ),
    # ── Ollama (লোকাল, সম্পূর্ণ ফ্রি) ─────────────────────────────
    ModelPricing(
        provider="ollama",
        model_pattern=r"qwen|llama|mistral|ollama",
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        is_free_tier=True,
        free_rpd=999_999,  # বাংলা: লোকালে কোনো লিমিট নেই
        free_tpm=999_999,
        display_name="Ollama (Local, Free)",
    ),
]

# ═══════════════════════════════════════════════════════════════════
# কনফিগ ফিল্ড থেকে রেট লিমিট — config_fields.py থেকে সংগ্রহীত
# বাংলা: এই ডিফল্ট মানগুলো config_fields.py-এর সাথে মিলে রাখা হয়েছে
# ═══════════════════════════════════════════════════════════════════

CONFIG_RATE_LIMITS: dict[str, dict[str, int]] = {
    "gemini": {"rpm": 9, "tpm": 240_000, "rpd": 475},
    "groq": {"rpm": 28, "tpm": 28_500, "rpd": 13_680},
    "openrouter": {"rpm": 19, "rpd": 45},
    "huggingface": {"rpm": 18, "rpd": 950},
    "nvidia": {"rpm": 38, "tpm": 38_000},
    "cloudflare": {"rpd": 9_000},
}

# ═══════════════════════════════════════════════════════════════════
# ডাটা ক্লাস — স্ক্যান ফলাফল ধারণ করে
# ═══════════════════════════════════════════════════════════════════

@dataclass
class LLMPattern:
    """বাংলা: কোডবেসে পাওয়া একটি LLM কল প্যাটার্নের তথ্য।"""
    file: str                # ফাইলের পথ
    line: int                # লাইন নম্বর
    provider: str            # প্রোভাইডার (gemini, groq, ইত্যাদি)
    model: str               # মডেলের নাম (খালি হলে ডিফল্ট ধরে নেওয়া হবে)
    max_tokens: int | None   # max_tokens মান (None হলে ডিফল্ট)
    temperature: float | None  # temperature মান
    context: str             # আশেপাশের কোডের স্নিপেট


@dataclass
class CostBombAlert:
    """বাংলা: একটি 'কস্ট বম্ব' সতর্কতা — খুব বেশি max_tokens পাওয়া গেছে।"""
    file: str
    line: int
    max_tokens: int
    provider: str
    model: str
    estimated_cost_per_call: float  # প্রতি কলে আনুমানিক খরচ (USD)


@dataclass
class ProviderCostBreakdown:
    """বাংলা: একটি প্রোভাইডারের খরচের বিশদ হিসাব।"""
    provider: str
    display_name: str
    call_sites: int             # কতটি জায়গায় এই প্রোভাইডার ব্যবহৃত
    avg_max_tokens: float       # গড় max_tokens
    estimated_tokens_per_call: int  # প্রতি কলে আনুমানিক মোট টোকেন
    is_free_tier: bool
    free_rpd: int               # ফ্রি টায়ার দৈনিক লিমিট
    daily_free_calls: int       # ফ্রি টায়ারে দৈনিক কতটি কল করা যাবে
    daily_paid_calls: int       # ফ্রি কোটা শেষে দৈনিক পেইড কল
    daily_cost_free: float      # ফ্রি টায়ারে দৈনিক খরচ (সবসময় ০)
    daily_cost_paid: float      # পেইড দৈনিক খরচ
    monthly_cost_free: float    # মাসিক ফ্রি খরচ
    monthly_cost_paid: float    # মাসিক পেইড খরচ
    monthly_cost_total: float   # মাসিক মোট খরচ
    free_tier_utilization: float  # ফ্রি কোটার কত % ব্যবহৃত হবে
    free_tier_exhaustion_day: float  # কত দিনে ফ্রি কোটা শেষ হবে (বৃদ্ধি পেলে)


@dataclass
class OptimizationSuggestion:
    """বাংলা: খরচ কমানোর জন্য একটি পরামর্শ।"""
    category: str   # "reduce_tokens", "switch_provider", "use_free_tier"
    file: str
    line: int
    current: str    # বর্তমান অবস্থা
    suggestion: str # পরামর্শ
    savings_pct: float  # কত % সাশ্রয় সম্ভব


@dataclass
class ProjectionReport:
    """বাংলা: সম্পূর্ণ খরচ প্রজেকশন রিপোর্ট।"""
    patterns_found: list[LLMPattern]
    cost_bombs: list[CostBombAlert]
    provider_breakdowns: list[ProviderCostBreakdown]
    suggestions: list[OptimizationSuggestion]
    total_monthly_cost: float
    total_daily_cost: float
    files_scanned: int
    has_cost_concerns: bool


# ═══════════════════════════════════════════════════════════════════
# স্ক্যানার — কোডবেস পার্স করে LLM কল প্যাটার্ন খুঁজে বের করে
# ═══════════════════════════════════════════════════════════════════

class CodebaseScanner:
    """বাংলা: backend/ ডিরেক্টরি স্ক্যান করে LLM API কলের প্যাটার্ন খুঁজে বের করে।"""

    # বাংলা: রিজেক্স প্যাটার্ন — মডেল নাম শনাক্ত করার জন্য
    MODEL_PATTERNS = [
        (r"models/gemini-[\w.\-]+", "gemini"),
        (r"gemini/gemini-[\w.\-]+", "gemini"),
        (r'"gemini-[\w.\-]+"', "gemini"),
        (r"'gemini-[\w.\-]+'", "gemini"),
        (r'"kimi-k[\w.\-]+"', "moonshot"),
        (r"'kimi-k[\w.\-]+'", "moonshot"),
        (r'"deepseek-[\w.\-]+"', "deepseek"),
        (r"'deepseek-[\w.\-]+'", "deepseek"),
        (r'"llama[\w.\-]*3[\w.\-.]*70b[\w.\-]*"', "groq"),
        (r"'llama[\w.\-]*3[\w.\-.]*70b[\w.\-]*'", "groq"),
        (r'"claude-[\w.\-.]+"', "claude"),
        (r"'claude-[\w.\-.]+'", "claude"),
        (r'"gpt-[\w.\-.]+"', "openai"),
        (r"'gpt-[\w.\-.]+'", "openai"),
        (r'"meta-llama/[\w.\-/.]+"', "openrouter"),
        (r"'meta-llama/[\w.\-/.]+'", "openrouter"),
        (r'"anthropic/[\w.\-.]+"', "claude"),
        (r"'anthropic/[\w.\-.]+'", "claude"),
        (r'"openrouter/[\w.\-.]+"', "openrouter"),
        (r"'openrouter/[\w.\-.]+'", "openrouter"),
        (r'"supreme-hybrid[\w.\-]*"', "huggingface"),
        (r"'supreme-hybrid[\w.\-]*'", "huggingface"),
        (r'"qwen[\w.:\-]+"', "ollama"),
        (r"'qwen[\w.:\-]+'", "ollama"),
        (r'"mixtral[\w.\-]*"', "groq"),
        (r"'mixtral[\w.\-]*'", "groq"),
        (r'"nvidia[\w.\-]*"', "nvidia"),
        (r"'nvidia[\w.\-]*'", "nvidia"),
    ]

    # বাংলা: প্রোভাইডার কল প্যাটার্ন — কোডে কোন ফাংশন/মেথড কল হচ্ছে
    PROVIDER_CALL_PATTERNS = [
        (r"\.acompletion\(", None),           # সব প্রোভাইডারের সাধারণ কল
        (r"\.chat\(", "groq"),                # GroqProvider.chat()
        (r"\.stream_chat\(", "groq"),         # GroqProvider.stream_chat()
        (r"litellm\.acompletion\(", None),    # LiteLM gateway কল
        (r"completion\(", None),               # সাধারণ completion
        (r"generateContent", "gemini"),       # Gemini REST API
    ]

    # বাংলা: ক্লাস নাম থেকে প্রোভাইডার নির্ধারণ
    PROVIDER_CLASS_MAP = {
        "GeminiProvider": "gemini",
        "GroqProvider": "groq",
        "MoonshotProvider": "moonshot",
        "DeepSeekProvider": "deepseek",
        "TogetherProvider": "together",
        "OllamaProvider": "ollama",
        "HuggingFaceSpaceProvider": "huggingface",
    }

    def __init__(self, backend_dir: Path, filter_provider: str | None = None):
        self.backend_dir = backend_dir
        self.filter_provider = filter_provider
        self.patterns: list[LLMPattern] = []
        self.files_scanned = 0

    def scan(self) -> list[LLMPattern]:
        """বাংলা: backend/ এর সব .py ফাইল স্ক্যান করে LLM প্যাটার্ন সংগ্রহ করে।"""
        if not self.backend_dir.exists():
            print(f"ত্রুটি: backend ডিরেক্টরি পাওয়া যায়নি: {self.backend_dir}", file=sys.stderr)
            sys.exit(2)

        # বাংলা: সব .py ফাইলের তালিকা তৈরি করা হচ্ছে (tests বাদ)
        py_files: list[Path] = []
        for root, _dirs, files in os.walk(self.backend_dir):
            root_path = Path(root)
            # বাংলা: tests ফোল্ডার বাদ দেওয়া হচ্ছে — শুধু প্রোডাকশন কোড স্ক্যান
            if "tests" in root_path.parts or "__pycache__" in root_path.parts:
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(root_path / f)

        for filepath in sorted(py_files):
            try:
                self._scan_file(filepath)
            except Exception as exc:
                # বাংলা: একটি ফাইলে ত্রুটি হলে বাকিগুলো স্ক্যান চালিয়ে যাওয়া হবে
                print(f"সতর্কতা: {filepath} পড়তে সমস্যা: {exc}", file=sys.stderr)
        return self.patterns

    def _scan_file(self, filepath: Path) -> None:
        """বাংলা: একটি ফাইল পার্স করে LLM কলের প্যাটার্ন খুঁজে বের করে।"""
        self.files_scanned += 1
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        lines = content.splitlines()
        # বাংলা: ফাইলে কোন প্রোভাইডার উল্লেখ আছে কিনা দ্রুত পরীক্ষা
        file_provider = self._detect_file_provider(content)

        for line_idx, line in enumerate(lines, start=1):
            # বাংলা: max_tokens খোঁজা
            mt_match = re.search(r"max_tokens\s*=\s*(\d+)", line)
            # বাংলা: maxOutputTokens খোঁজা (Gemini format)
            mot_match = re.search(r"maxOutputTokens\s*:\s*(\d+)", line)
            # বাংলা: num_predict খোঁজা (Ollama format)
            np_match = re.search(r"num_predict\s*:\s*(\d+)", line)
            # বাংলা: temperature খোঁজা
            temp_match = re.search(r"temperature\s*=\s*([\d.]+)", line)
            # বাংলা: model খোঁজা
            model_match = re.search(r'("[^"]*"|\'[^\']*\')\s*[:,]\s*$', line)
            # বাংলা: সরাসরি model= প্যাটার্ন
            model_direct = re.search(r'model\s*=\s*(["\'])(.+?)\1', line)

            # বাংলা: LLM-সম্পর্কিত কল আছে কিনা চেক করা হচ্ছে
            is_llm_call = any(
                kw in line for kw in [
                    "max_tokens", "maxOutputTokens", "num_predict",
                    "acompletion", "completion", "generateContent",
                    "chat/completions", ".chat(", "stream_chat",
                    "temperature=", "model=",
                ]
            )

            if not is_llm_call:
                continue

            # বাংলা: max_tokens মান নির্ধারণ
            max_tokens = None
            if mt_match:
                max_tokens = int(mt_match.group(1))
            elif mot_match:
                max_tokens = int(mot_match.group(1))
            elif np_match:
                max_tokens = int(np_match.group(1))

            # বাংলা: temperature মান নির্ধারণ
            temperature = float(temp_match.group(1)) if temp_match else None

            # বাংলা: মডেল নাম নির্ধারণ
            model_name = ""
            if model_direct:
                model_name = model_direct.group(2)
            else:
                # বাংলা: লাইনে কোনো পরিচিত মডেল প্যাটার্ন আছে কিনা চেক
                for pattern, _prov in self.MODEL_PATTERNS:
                    m = re.search(pattern, line)
                    if m:
                        model_name = m.group(0).strip("'\"")
                        break

            # বাংলা: লাইন থেকে প্রোভাইডার নির্ধারণ
            provider = self._detect_line_provider(line, file_provider, model_name)

            # বাংলা: ফিল্টার প্রোভাইডার সেট থাকলে সেই অনুযায়ী ফিল্টার
            if self.filter_provider and provider != self.filter_provider:
                continue

            # বাংলা: কনটেক্সট স্নিপেট তৈরি (আশেপাশের ২ লাইন)
            ctx_start = max(0, line_idx - 3)
            ctx_end = min(len(lines), line_idx + 1)
            context = "\n".join(lines[ctx_start:ctx_end])

            self.patterns.append(LLMPattern(
                file=str(filepath.relative_to(self.backend_dir.parent)),
                line=line_idx,
                provider=provider,
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                context=context.strip(),
            ))

    def _detect_file_provider(self, content: str) -> str:
        """বাংলা: ফাইলের বিষয়বস্তু থেকে প্রধান প্রোভাইডার নির্ধারণ।"""
        for cls_name, prov in self.PROVIDER_CLASS_MAP.items():
            if cls_name in content:
                return prov
        # বাংলা: ফাইলে প্রোভাইডার-সম্পর্কিত স্ট্রিং থেকেও নির্ধারণ করা যায়
        provider_hints = [
            ("groq_api_key", "groq"),
            ("gemini_api_key", "gemini"),
            ("deepseek_api_key", "deepseek"),
            ("moonshot_api_key", "moonshot"),
            ("openrouter_api_key", "openrouter"),
            ("hf_api_key", "huggingface"),
            ("nvidia_api_key", "nvidia"),
            ("together_api_key", "together"),
        ]
        for hint, prov in provider_hints:
            if hint in content:
                return prov
        return "unknown"

    def _detect_line_provider(
        self, line: str, file_provider: str, model_name: str
    ) -> str:
        """বাংলা: একটি নির্দিষ্ট লাইন থেকে প্রোভাইডার নির্ধারণ।"""
        # বাংলা: মডেল নাম থেকে প্রোভাইডার অনুমান
        for pattern, prov in self.MODEL_PATTERNS:
            if re.search(pattern, line):
                return prov
        # বাংলা: মডেল নাম থেকে প্রোভাইডার অনুমান (দ্বিতীয় প্রচেষ্টা)
        if model_name:
            model_lower = model_name.lower()
            for pattern, prov in self.MODEL_PATTERNS:
                if re.search(pattern, model_lower):
                    return prov
        # বাংলা: লাইনে প্রোভাইডার স্ট্রিং আছে কিনা চেক
        provider_kw_map = {
            "gemini": "gemini",
            "groq": "groq",
            "moonshot": "moonshot",
            "deepseek": "deepseek",
            "openrouter": "openrouter",
            "huggingface": "huggingface",
            "hf_space": "huggingface",
            "together": "together",
            "ollama": "ollama",
            "claude": "claude",
            "openai": "openai",
            "nvidia": "nvidia",
        }
        for kw, prov in provider_kw_map.items():
            if kw in line.lower():
                return prov
        # বাংলা: ফাইলের প্রোভাইডার ব্যবহার
        return file_provider


# ═══════════════════════════════════════════════════════════════════
# কস্ট ক্যালকুলেটর — প্রাইসিং ও প্রজেকশন হিসাব
# ═══════════════════════════════════════════════════════════════════

class CostCalculator:
    """বাংলা: পাওয়া প্যাটার্ন থেকে খরচের প্রজেকশন বের করে।"""

    # বাংলা: প্রোভাইডার অনুযায়ী ডিফল্ট মডেল (যখন কোডে মডেল উল্লেখ নেই)
    DEFAULT_MODELS: dict[str, str] = {
        "gemini": "gemini/gemini-2.0-flash",
        "groq": "llama-3.3-70b-versatile",
        "moonshot": "kimi-k2.5",
        "deepseek": "deepseek-chat",
        "openrouter": "openrouter/auto",
        "claude": "claude-3.5-haiku",
        "openai": "gpt-4o-mini",
        "huggingface": "supreme-hybrid-8b",
        "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "nvidia": "nvidia/llama-3.3-70b-instruct",
        "ollama": "qwen2.5:0.5b",
        "unknown": "gemini/gemini-2.0-flash",
    }

    def __init__(self, daily_requests: int = 100):
        self.daily_requests = daily_requests
        self.days_per_month = 30

    def find_pricing(self, provider: str, model: str) -> ModelPricing | None:
        """বাংলা: মডেলের জন্য প্রাইসিং খুঁজে বের করে।"""
        model_key = model or self.DEFAULT_MODELS.get(provider, "")
        for pricing in MODEL_PRICING_TABLE:
            if pricing.provider == provider and re.search(pricing.model_pattern, model_key):
                return pricing
        # বাংলা: প্রোভাইডার মিললেও মডেল না মিললে প্রোভাইডারের প্রথম এন্ট্রি ব্যবহার
        for pricing in MODEL_PRICING_TABLE:
            if pricing.provider == provider:
                return pricing
        return None

    def calculate_breakdown(
        self, provider: str, patterns: list[LLMPattern]
    ) -> ProviderCostBreakdown:
        """বাংলা: একটি প্রোভাইডারের খরচের বিশদ হিসাব করে।"""
        if not patterns:
            return ProviderCostBreakdown(
                provider=provider,
                display_name=provider,
                call_sites=0, avg_max_tokens=0, estimated_tokens_per_call=0,
                is_free_tier=False, free_rpd=0, daily_free_calls=0,
                daily_paid_calls=0, daily_cost_free=0.0, daily_cost_paid=0.0,
                monthly_cost_free=0.0, monthly_cost_paid=0.0, monthly_cost_total=0.0,
                free_tier_utilization=0.0, free_tier_exhaustion_day=0.0,
            )

        # বাংলা: প্রোভাইডারের প্রথম ম্যাচিং প্রাইসিং নেওয়া হচ্ছে
        pricing = self.find_pricing(
            provider, patterns[0].model or ""
        )

        # বাংলা: গড় max_tokens বের করা
        max_tokens_values = [
            p.max_tokens for p in patterns if p.max_tokens is not None
        ]
        avg_max_tokens = (
            sum(max_tokens_values) / len(max_tokens_values)
            if max_tokens_values
            else 1500.0  # বাংলা: config_fields.py-এর max_response_tokens ডিফল্ট
        )

        # বাংলা: প্রতি কলে আনুমানিক মোট টোকেন = prompt + response
        # prompt tokens আনুমানিক max_tokens-এর ২.৫ গুণ (system prompt, context ইত্যাদি)
        estimated_tokens_per_call = int(avg_max_tokens * 3.5)

        # বাংলা: প্রাইসিং তথ্য
        is_free = pricing.is_free_tier if pricing else False
        free_rpd = pricing.free_rpd if pricing else 0
        cost_input = (pricing.cost_per_1k_input if pricing else 0.001)
        cost_output = (pricing.cost_per_1k_output if pricing else 0.002)
        display_name = (pricing.display_name if pricing else provider)

        # বাংলা: ফ্রি টায়ারে দৈনিক কতটি কল সম্ভব
        daily_free_calls = free_rpd if free_rpd > 0 else 0

        # বাংলা: দৈনিক মোট কল থেকে পেইড কল বের করা
        daily_total = self.daily_requests
        daily_paid_calls = max(0, daily_total - daily_free_calls)

        # বাংলা: প্রতি কলে খরচ হিসাব
        input_tokens_per_call = int(estimated_tokens_per_call * 0.7)
        output_tokens_per_call = int(estimated_tokens_per_call * 0.3)
        cost_per_call = (
            (input_tokens_per_call / 1000.0) * cost_input
            + (output_tokens_per_call / 1000.0) * cost_output
        )

        # বাংলা: দৈনিক ও মাসিক খরচ
        daily_cost_free = 0.0  # ফ্রি টায়ারে খরচ শূন্য
        daily_cost_paid = daily_paid_calls * cost_per_call
        monthly_cost_free = 0.0
        monthly_cost_paid = daily_cost_paid * self.days_per_month
        monthly_cost_total = monthly_cost_free + monthly_cost_paid

        # বাংলা: ফ্রি টায়ার ব্যবহারের শতাংশ
        if daily_total > 0 and free_rpd > 0:
            free_tier_utilization = min(100.0, (daily_total / free_rpd) * 100.0)
        else:
            free_tier_utilization = 0.0

        # বাংলা: ফ্রি কোটা কত দিনে শেষ হবে
        if daily_total > free_rpd > 0:
            free_tier_exhaustion_day = float(free_rpd)  # প্রথম দিনেই শেষ!
        elif daily_total > 0 and free_rpd > 0:
            free_tier_exhaustion_day = free_rpd / daily_total
        elif free_rpd > 0:
            free_tier_exhaustion_day = float('inf')
        else:
            free_tier_exhaustion_day = 0.0

        return ProviderCostBreakdown(
            provider=provider,
            display_name=display_name,
            call_sites=len(patterns),
            avg_max_tokens=avg_max_tokens,
            estimated_tokens_per_call=estimated_tokens_per_call,
            is_free_tier=is_free,
            free_rpd=free_rpd,
            daily_free_calls=daily_free_calls,
            daily_paid_calls=daily_paid_calls,
            daily_cost_free=daily_cost_free,
            daily_cost_paid=daily_cost_paid,
            monthly_cost_free=monthly_cost_free,
            monthly_cost_paid=monthly_cost_paid,
            monthly_cost_total=monthly_cost_total,
            free_tier_utilization=free_tier_utilization,
            free_tier_exhaustion_day=free_tier_exhaustion_day,
        )

    def find_cost_bombs(self, patterns: list[LLMPattern]) -> list[CostBombAlert]:
        """বাংলা: max_tokens খুব বেশি থাকলে 'কস্ট বম্ব' সতর্কতা তৈরি করে।"""
        alerts: list[CostBombAlert] = []
        for p in patterns:
            if p.max_tokens and p.max_tokens >= _COST_BOMB_THRESHOLD:
                pricing = self.find_pricing(p.provider, p.model or "")
                cost_in = (pricing.cost_per_1k_input if pricing else 0.001)
                cost_out = (pricing.cost_per_1k_output if pricing else 0.002)
                # বাংলা: আনুমানিক প্রতি কলে খরচ
                est_cost = (
                    (p.max_tokens * 2.5 / 1000.0) * cost_in
                    + (p.max_tokens / 1000.0) * cost_out
                )
                alerts.append(CostBombAlert(
                    file=p.file,
                    line=p.line,
                    max_tokens=p.max_tokens,
                    provider=p.provider,
                    model=p.model or self.DEFAULT_MODELS.get(p.provider, "unknown"),
                    estimated_cost_per_call=est_cost,
                ))
        return alerts

    def generate_suggestions(
        self, patterns: list[LLMPattern], breakdowns: list[ProviderCostBreakdown]
    ) -> list[OptimizationSuggestion]:
        """বাংলা: খরচ কমানোর জন্য পরামর্শ তৈরি করে।"""
        suggestions: list[OptimizationSuggestion] = []

        # বাংলা: প্রতিটি প্যাটার্নের জন্য পরামর্শ
        for p in patterns:
            if p.max_tokens and p.max_tokens > 2000:
                # বাংলা: max_tokens কমানোর পরামর্শ
                suggested = 1500
                savings = ((p.max_tokens - suggested) / p.max_tokens) * 100
                suggestions.append(OptimizationSuggestion(
                    category="reduce_tokens",
                    file=p.file,
                    line=p.line,
                    current=f"max_tokens={p.max_tokens}",
                    suggestion=f"max_tokens={suggested} (config_fields.py-এর max_response_tokens অনুসারে)",
                    savings_pct=round(savings, 1),
                ))

            # বাংলা: পেইড প্রোভাইডার থেকে ফ্রি প্রোভাইডারে সুইচের পরামর্শ
            pricing = self.find_pricing(p.provider, p.model or "")
            if pricing and not pricing.is_free_tier:
                # বাংলা: কাজের ধরন অনুযায়ী সস্তা বিকল্প খোঁজা
                cheaper = self._find_cheaper_alternative(p.provider, p.model or "")
                if cheaper:
                    savings = 100.0  # ফ্রি হলে ১০০% সাশ্রয়
                    suggestions.append(OptimizationSuggestion(
                        category="switch_provider",
                        file=p.file,
                        line=p.line,
                        current=f"{p.provider} ({p.model or 'default'})",
                        suggestion=f"{cheaper} ব্যবহার করুন (ফ্রি টায়ার)",
                        savings_pct=savings,
                    ))

        # বাংলা: ফ্রি টায়ারের ব্যবহার অত্যন্ত বেশি হলে সতর্কতা
        for bd in breakdowns:
            if bd.free_tier_utilization > 100 and bd.is_free_tier:
                suggestions.append(OptimizationSuggestion(
                    category="use_free_tier",
                    file="(সামগ্রিক)",
                    line=0,
                    current=f"{bd.provider}: ফ্রি কোটার {bd.free_tier_utilization:.0f}% ব্যবহৃত",
                    suggestion=(
                        f"{bd.provider}-এর ফ্রি কোটা ({bd.free_rpd} RPD) অতিক্রম হবে। "
                        f"অতিরিক্ত লোড অন্য ফ্রি প্রোভাইডারে ডিস্ট্রিবিউট করুন।"
                    ),
                    savings_pct=0.0,
                ))

        # বাংলা: savings_pct অনুযায়ী সাজানো (বেশি সাশ্রয় আগে)
        suggestions.sort(key=lambda s: s.savings_pct, reverse=True)
        return suggestions

    def _find_cheaper_alternative(self, provider: str, model: str) -> str | None:
        """বাংলা: একটি পেইড মডেলের জন্য ফ্রি বিকল্প খুঁজে বের করে।"""
        # বাংলা: মডেলের আকার অনুমান করে সমমানের ফ্রি বিকল্প খোঁজা
        if "70b" in model.lower() or "large" in model.lower():
            return "Groq (llama-3.3-70b-versatile, Free)"
        if "opus" in model.lower():
            return "Gemini 2.0 Flash (Free)"
        if "sonnet" in model.lower():
            return "Gemini 2.0 Flash (Free)"
        if "claude" in model.lower():
            return "OpenRouter Claude 3.5 Haiku (Free)"
        # বাংলা: সাধারণ ক্ষেত্রে Gemini Flash সবচেয়ে ভালো ফ্রি বিকল্প
        return "Gemini 2.0 Flash (Free)"


# ═══════════════════════════════════════════════════════════════════
# রিপোর্ট জেনারেটর — মানব-পাঠযোগ্য ও JSON আউটপুট
# ═══════════════════════════════════════════════════════════════════

class ReportGenerator:
    """বাংলা: স্ক্যান ও ক্যালকুলেশনের ফলাফল থেকে রিপোর্ট তৈরি করে।"""

    @staticmethod
    def build_report(
        patterns: list[LLMPattern],
        cost_bombs: list[CostBombAlert],
        breakdowns: list[ProviderCostBreakdown],
        suggestions: list[OptimizationSuggestion],
        files_scanned: int,
    ) -> ProjectionReport:
        """বাংলা: সম্পূর্ণ রিপোর্ট অবজেক্ট তৈরি করে।"""
        total_monthly = sum(bd.monthly_cost_total for bd in breakdowns)
        total_daily = sum(bd.daily_cost_paid for bd in breakdowns)
        has_concerns = (
            total_monthly > _MONTHLY_BUDGET_LIMIT
            or len(cost_bombs) > 0
            or any(bd.free_tier_utilization > 100 for bd in breakdowns)
        )
        return ProjectionReport(
            patterns_found=patterns,
            cost_bombs=cost_bombs,
            provider_breakdowns=breakdowns,
            suggestions=suggestions,
            total_monthly_cost=total_monthly,
            total_daily_cost=total_daily,
            files_scanned=files_scanned,
            has_cost_concerns=has_concerns,
        )

    @staticmethod
    def render_text(report: ProjectionReport) -> str:
        """বাংলা: মানব-পাঠযোগ্য টেক্সট রিপোর্ট তৈরি করে।"""
        lines: list[str] = []
        w = lines.append

        w("=" * 72)
        w("  SupremeAI LLM Cost Projector — খরচ প্রজেকশন রিপোর্ট")
        w("=" * 72)
        w("")
        w(f"  স্ক্যান করা ফাইল: {report.files_scanned}")
        w(f"  পাওয়া LLM কল প্যাটার্ন: {len(report.patterns_found)}")
        w(f"  অনুমানিত দৈনিক খরচ: ${report.total_daily_cost:.4f}")
        w(f"  অনুমানিত মাসিক খরচ: ${report.total_monthly_cost:.4f}")
        w(f"  মাসিক বাজেট লিমিট: ${_MONTHLY_BUDGET_LIMIT:.2f}")

        if report.total_monthly_cost > _MONTHLY_BUDGET_LIMIT:
            w(f"  ⚠️  বাজেট অতিক্রম! মাসিক খরচ লিমিটের {_MONTHLY_BUDGET_LIMIT / report.total_monthly_cost * 100:.0f}%।")
        elif report.total_monthly_cost > 0:
            w(f"  ✅ বাজেটের মধ্যে ({report.total_monthly_cost / _MONTHLY_BUDGET_LIMIT * 100:.1f}% ব্যবহৃত)")
        else:
            w("  ✅ সম্পূর্ণ ফ্রি টায়ারে চলছে — কোনো খরচ নেই!")

        # ── প্রোভাইডার অনুযায়ী বিশদ হিসাব ──
        w("")
        w("─" * 72)
        w("  প্রোভাইডার অনুযায়ী খরচ বিশদ (Daily / Monthly)")
        w("─" * 72)

        # বাংলা: মাসিক খরচ অনুযায়ী সাজানো (বেশি খরচ আগে)
        sorted_bd = sorted(
            report.provider_breakdowns,
            key=lambda b: b.monthly_cost_total,
            reverse=True,
        )

        for bd in sorted_bd:
            if bd.call_sites == 0:
                continue
            w("")
            tier_tag = "🟢 ফ্রি" if bd.is_free_tier else "🔴 পেইড"
            w(f"  [{tier_tag}] {bd.display_name}")
            w(f"    কল সাইট:        {bd.call_sites} টি জায়গায়")
            w(f"    গড় max_tokens:  {bd.avg_max_tokens:.0f}")
            w(f"    আনুমানিক টোকেন/কল: {bd.estimated_tokens_per_call:,}")

            if bd.is_free_tier and bd.free_rpd > 0:
                util_bar = _render_bar(bd.free_tier_utilization)
                w(f"    ফ্রি কোটা:      {bd.free_rpd:,} RPD")
                w(f"    কোটা ব্যবহার:   {bd.free_tier_utilization:.1f}% {util_bar}")
                if bd.free_tier_exhaustion_day == float('inf'):
                    w(f"    কোটা শেষ:      কখনো না (বর্তমান লোডে)")
                elif bd.free_tier_exhaustion_day >= 1:
                    w(f"    কোটা শেষ:      {bd.free_tier_exhaustion_day:.1f} দিনে")
                else:
                    w(f"    কোটা শেষ:      ১ম দিনেই অতিক্রম!")

            w(f"    দৈনিক খরচ:   ${bd.daily_cost_paid:.4f} (ফ্রি: ${bd.daily_cost_free:.2f})")
            w(f"    মাসিক খরচ:   ${bd.monthly_cost_total:.4f}")

        # ── কস্ট বম্ব এলার্ট ──
        if report.cost_bombs:
            w("")
            w("─" * 72)
            w(f"  ⚠️  কস্ট বম্ব এলার্ট (max_tokens >= {_COST_BOMB_THRESHOLD})")
            w("─" * 72)
            for bomb in report.cost_bombs:
                w("")
                w(f"    📍 {bomb.file}:{bomb.line}")
                w(f"       প্রোভাইডার: {bomb.provider} | মডেল: {bomb.model}")
                w(f"       max_tokens: {bomb.max_tokens} (খরচ: ~${bomb.estimated_cost_per_call:.4f}/কল)")

        # ── অপটিমাইজেশন পরামর্শ ──
        if report.suggestions:
            w("")
            w("─" * 72)
            w("  💡 অপটিমাইজেশন পরামর্শ")
            w("─" * 72)
            # বাংলা: সর্বোচ্চ ১০টি পরামর্শ দেখানো হচ্ছে
            for sug in report.suggestions[:10]:
                w("")
                cat_emoji = {
                    "reduce_tokens": "📏",
                    "switch_provider": "🔄",
                    "use_free_tier": "🆓",
                }.get(sug.category, "💡")
                w(f"    {cat_emoji} [{sug.category}] {sug.file}:{sug.line}")
                w(f"       বর্তমান:  {sug.current}")
                w(f"       পরামর্শ:  {sug.suggestion}")
                if sug.savings_pct > 0:
                    w(f"       সাশ্রয়:   ~{sug.savings_pct:.0f}%")

        # ── রেট লিমিট রেফারেন্স ──
        w("")
        w("─" * 72)
        w("  📊 config_fields.py থেকে রেট লিমিট (ডিফল্ট মান)")
        w("─" * 72)
        for prov, limits in CONFIG_RATE_LIMITS.items():
            parts = [f"RPM: {limits.get('rpm', 'N/A')}" if 'rpm' in limits else ""]
            if 'tpm' in limits:
                parts.append(f"TPM: {limits['tpm']:,}")
            if 'rpd' in limits:
                parts.append(f"RPD: {limits['rpd']:,}")
            w(f"    {prov:15s} | {', '.join(parts)}")

        w("")
        w("=" * 72)
        w(f"  মোট মাসিক খরচ: ${report.total_monthly_cost:.4f} USD")
        w("=" * 72)

        return "\n".join(lines)

    @staticmethod
    def render_json(report: ProjectionReport) -> str:
        """বাংলা: JSON ফরম্যাটে রিপোর্ট তৈরি করে।"""
        def _serialize_breakdown(bd: ProviderCostBreakdown) -> dict[str, Any]:
            return {
                "provider": bd.provider,
                "display_name": bd.display_name,
                "call_sites": bd.call_sites,
                "avg_max_tokens": round(bd.avg_max_tokens, 1),
                "estimated_tokens_per_call": bd.estimated_tokens_per_call,
                "is_free_tier": bd.is_free_tier,
                "free_rpd": bd.free_rpd,
                "daily_free_calls": bd.daily_free_calls,
                "daily_paid_calls": bd.daily_paid_calls,
                "daily_cost_free": bd.daily_cost_free,
                "daily_cost_paid": round(bd.daily_cost_paid, 6),
                "monthly_cost_free": bd.monthly_cost_free,
                "monthly_cost_paid": round(bd.monthly_cost_paid, 6),
                "monthly_cost_total": round(bd.monthly_cost_total, 6),
                "free_tier_utilization_pct": round(bd.free_tier_utilization, 1),
                "free_tier_exhaustion_day": (
                    bd.free_tier_exhaustion_day
                    if bd.free_tier_exhaustion_day != float('inf')
                    else None
                ),
            }

        def _serialize_bomb(b: CostBombAlert) -> dict[str, Any]:
            return {
                "file": b.file,
                "line": b.line,
                "max_tokens": b.max_tokens,
                "provider": b.provider,
                "model": b.model,
                "estimated_cost_per_call": round(b.estimated_cost_per_call, 6),
            }

        def _serialize_suggestion(s: OptimizationSuggestion) -> dict[str, Any]:
            return {
                "category": s.category,
                "file": s.file,
                "line": s.line,
                "current": s.current,
                "suggestion": s.suggestion,
                "savings_pct": s.savings_pct,
            }

        def _serialize_pattern(p: LLMPattern) -> dict[str, Any]:
            return {
                "file": p.file,
                "line": p.line,
                "provider": p.provider,
                "model": p.model,
                "max_tokens": p.max_tokens,
                "temperature": p.temperature,
            }

        output = {
            "summary": {
                "files_scanned": report.files_scanned,
                "patterns_found": len(report.patterns_found),
                "cost_bombs": len(report.cost_bombs),
                "total_daily_cost_usd": round(report.total_daily_cost, 6),
                "total_monthly_cost_usd": round(report.total_monthly_cost, 6),
                "monthly_budget_limit_usd": _MONTHLY_BUDGET_LIMIT,
                "within_budget": report.total_monthly_cost <= _MONTHLY_BUDGET_LIMIT,
                "has_cost_concerns": report.has_cost_concerns,
            },
            "provider_breakdowns": [
                _serialize_breakdown(bd) for bd in report.provider_breakdowns
                if bd.call_sites > 0
            ],
            "cost_bombs": [_serialize_bomb(b) for b in report.cost_bombs],
            "optimization_suggestions": [
                _serialize_suggestion(s) for s in report.suggestions[:10]
            ],
            "patterns": [_serialize_pattern(p) for p in report.patterns_found],
        }
        return json.dumps(output, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# হেল্পার ফাংশন
# ═══════════════════════════════════════════════════════════════════

def _render_bar(pct: float, width: int = 20) -> str:
    """বাংলা: শতাংশ থেকে ভিজ্যুয়াল বার তৈরি করে।"""
    filled = min(width, int(width * min(pct, 100) / 100))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


def _group_patterns_by_provider(
    patterns: list[LLMPattern],
) -> dict[str, list[LLMPattern]]:
    """বাংলা: প্যাটার্নগুলো প্রোভাইডার অনুযায়ে গ্রুপ করে।"""
    groups: dict[str, list[LLMPattern]] = {}
    for p in patterns:
        groups.setdefault(p.provider, []).append(p)
    return groups


# ═══════════════════════════════════════════════════════════════════
# CLI — কমান্ড লাইন ইন্টারফেস
# ═══════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """বাংলা: কমান্ড লাইন আর্গুমেন্ট পার্স করে।"""
    parser = argparse.ArgumentParser(
        description="SupremeAI LLM Cost Projector — কোডবেস বিশ্লেষণ করে মাসিক LLM খরচের প্রজেকশন দেখায়",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""উদাহরণ:
  python scripts/llm_cost_projector.py
  python scripts/llm_cost_projector.py --json
  python scripts/llm_cost_projector.py --provider gemini
  python scripts/llm_cost_projector.py --monthly-requests 5000

এক্সিট কোড:
  0 = বাজেটের মধ্যে
  1 = খরচ নিয়ে সতর্কতা
  2 = ত্রুটি""",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON ফরম্যাটে আউটপুট দেখান",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=[
            "gemini", "groq", "openrouter", "claude", "deepseek",
            "moonshot", "huggingface", "together", "openai", "nvidia",
            "ollama",
        ],
        help="শুধুমাত্র একটি প্রোভাইডারের তথ্য দেখান",
    )
    parser.add_argument(
        "--monthly-requests",
        type=int,
        default=None,
        metavar="N",
        help="মাসিক রিকোয়েস্ট সংখ্যা (দৈনিক = N/30)",
    )
    return parser.parse_args()


def main() -> int:
    """বাংলা: মূল ফাংশন — স্ক্যান, ক্যালকুলেশন ও রিপোর্ট তৈরি করে।"""
    args = parse_args()

    # বাংলা: দৈনিক রিকোয়েস্ট সংখ্যা নির্ধারণ
    daily_requests = 100  # বাংলা: ডিফল্ট দৈনিক রিকোয়েস্ট
    if args.monthly_requests is not None:
        daily_requests = max(1, args.monthly_requests // 30)

    # বাংলা: ধাপ ১ — কোডবেস স্ক্যান
    scanner = CodebaseScanner(
        backend_dir=_BACKEND_DIR,
        filter_provider=args.provider,
    )
    try:
        patterns = scanner.scan()
    except Exception as exc:
        print(f"ত্রুটি: কোডবেস স্ক্যান করতে সমস্যা: {exc}", file=sys.stderr)
        return 2

    # বাংলা: ধাপ ২ — খরচ হিসাব
    calc = CostCalculator(daily_requests=daily_requests)

    # বাংলা: প্রোভাইডার অনুযায়ে গ্রুপ করা
    grouped = _group_patterns_by_provider(patterns)

    # বাংলা: প্রতিটি প্রোভাইডারের জন্য ব্রেকডাউন তৈরি
    all_providers = set(grouped.keys())
    # বাংলা: যেসব প্রোভাইডারের কল পাওয়া যায়নি কিন্তু রেট লিমিট আছে তাদেরও দেখানো হচ্ছে
    if not args.provider:
        all_providers.update(CONFIG_RATE_LIMITS.keys())

    breakdowns: list[ProviderCostBreakdown] = []
    for prov in sorted(all_providers):
        prov_patterns = grouped.get(prov, [])
        bd = calc.calculate_breakdown(prov, prov_patterns)
        breakdowns.append(bd)

    # বাংলা: কস্ট বম্ব খুঁজে বের করা
    cost_bombs = calc.find_cost_bombs(patterns)

    # বাংলা: অপটিমাইজেশন পরামর্শ তৈরি
    suggestions = calc.generate_suggestions(patterns, breakdowns)

    # বাংলা: ধাপ ৩ — রিপোর্ট তৈরি
    report = ReportGenerator.build_report(
        patterns=patterns,
        cost_bombs=cost_bombs,
        breakdowns=breakdowns,
        suggestions=suggestions,
        files_scanned=scanner.files_scanned,
    )

    # বাংলা: আউটপুট ফরম্যাট অনুযায়ী প্রিন্ট
    if args.json:
        print(ReportGenerator.render_json(report))
    else:
        print(ReportGenerator.render_text(report))

    # বাংলা: এক্সিট কোড নির্ধারণ
    if report.has_cost_concerns:
        return 1  # খরচ নিয়ে সতর্কতা
    return 0  # বাজেটের মধ্যে


if __name__ == "__main__":
    sys.exit(main())
