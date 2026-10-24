"""Natural & Organic File Presenter — Stealth Anti-Bot Humanization.

বাংলা সারসংক্ষেপ:
------------------
অ্যান্টি-বট ও ফ্রড ডিটেকশন সিস্টেমগুলো (Cloudflare, Anthropic, OpenAI)
যাতে কোনোভাবেই বুঝতে না পারে যে ফাইলটি বা রিকোয়েস্টটি কোনো অটোমেশন স্ক্রিপ্ট তৈরি করেছে।

ইউজার ইনভারিয়েন্ট:
"legit kora mane name e legit add kora na... name dekhe mone hobe legit"
- ফাইলের নামে কখনোই 'legit', 'fake', 'dummy' বা 'mock' শব্দ থাকবে না।
- ফাইলের ভেতরের আসল কোড ও কনটেন্ট (Content-Aware AST / Regex) বিশ্লেষণ করে
  একজন বাস্তব সফটওয়্যার ইঞ্জিনিয়ারের মতো স্বাভাবিক অর্গানিক নাম (e.g. order_processor.py,
  UserProfileCard.tsx, deployment_guide.md) দেওয়া হবে।
"""

from __future__ import annotations

import os
import random
import re
from pathlib import Path

# রোবোটিক বা অটোমেটেড প্যাটার্ন ডিটেক্টর (যা বটের মতো বা কৃত্রিম মনে হয়)
BOT_NAME_PATTERNS = [
    r"^tmp_?",
    r"^temp_?",
    r"^agent_?",
    r"^scratch_?",
    r"^task_?",
    r"^bot_?",
    r"^legit_?",  # 'legit_' লেখা থাকলেই সেটা সন্দেহজনক/বট-সাদৃশ্য
    r"^fake_?",  # 'fake_' শব্দ থাকলে তা পরিহার করতে হবে
    r"^mock_?",  # 'mock_' শব্দ পরিহার করতে হবে
    r"^claude_?",  # লিটারাল প্ল্যাটফর্ম নাম পরিহার (অডিট ও অ্যান্টি-বট সেফটি)
    r"^chatgpt_?",
    r"^openai_?",
    r"^anthropic_?",
    r"^v0_?",
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}",  # UUID
    r"^[0-9a-f]{16,32}",  # Hex dump
    r"^output_[0-9]+",
]

# এক্সটেনশন অনুযায়ী বাস্তবসম্মত অর্গানিক ডেভেলপার ফলব্যাক পুল
ORGANIC_FALLBACKS: dict[str, list[str]] = {
    ".py": [
        "service_client.py",
        "data_handler.py",
        "app_config.py",
        "utils.py",
        "router.py",
        "event_bus.py",
        "state_sync.py",
        "model_pipeline.py",
    ],
    ".ts": [
        "apiClient.ts",
        "types.ts",
        "stateStore.ts",
        "helpers.ts",
        "connectionManager.ts",
    ],
    ".tsx": [
        "DashboardView.tsx",
        "MainLayout.tsx",
        "ProfileCard.tsx",
        "Navbar.tsx",
        "SettingsModal.tsx",
    ],
    ".json": ["config.json", "settings.json", "manifest.json", "schema.json"],
    ".md": ["README.md", "SPECIFICATION.md", "NOTES.md", "SETUP.md", "ARCHITECTURE.md"],
    ".sql": ["schema.sql", "migration.sql", "queries.sql", "indexes.sql"],
    ".csv": ["data_export.csv", "metrics.csv", "report.csv"],
    ".txt": ["notes.txt", "requirements.txt", "run_log.txt"],
}


class NaturalFilePresenter:
    """ফাইল ও চ্যাট টাইটেলকে কনটেন্ট-অ্যাওয়ার অর্গানিক ডেভেলপার ফাইলে রূপান্তরকারী।"""

    @staticmethod
    def is_bot_like_name(name: str) -> bool:
        """
        বাংলা মন্তব্য:
        ফাইল বা কনভারসেশনের নাম রোবোটিক বা কৃত্রিম কিনা পরীক্ষা।
        'tmp_', 'agent_', 'legit_', 'fake_' ইত্যাদির কোনোটি পেলে True দেবে।
        """
        clean_name = Path(name).stem.lower()
        return any(re.search(pat, clean_name) for pat in BOT_NAME_PATTERNS)

    @classmethod
    def _inspect_content_for_name(cls, content: str, ext: str) -> str | None:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        ফাইলের আসল কনটেন্ট পড়ে খাঁটি ডেভেলপার নাম বের করা:
        - Python: `class OrderProcessor:` ➔ `order_processor.py`
        - Python: `def calculate_invoice():` ➔ `calculate_invoice.py`
        - TypeScript/React: `export function UserCard()` ➔ `UserCard.tsx`
        - Markdown: `# System Architecture` ➔ `system_architecture.md`
        - SQL: `CREATE TABLE users` ➔ `users_schema.sql`
        """
        lines = content[:4000].splitlines()

        if ext == ".py":
            for line in lines:
                m_class = re.search(r"^\s*class\s+([A-Za-z0-9_]+)", line)
                if m_class:
                    cname = m_class.group(1)
                    # PascalCase to snake_case
                    sname = re.sub(r"(?<!^)(?=[A-Z])", "_", cname).lower()
                    # যদি ক্লাসের নামেও bot/test/legit থাকে তা ফিল্টার
                    clean_sname = re.sub(r"^(?:legit|fake|mock|dummy|temp|tmp)_", "", sname)
                    return f"{clean_sname or sname}.py"

                m_def = re.search(r"^\s*def\s+([A-Za-z0-9_]+)", line)
                if m_def:
                    fname = m_def.group(1)
                    if not fname.startswith("__"):
                        clean_fname = re.sub(r"^(?:legit|fake|mock|dummy|temp|tmp)_", "", fname)
                        return f"{clean_fname or fname}.py"

        elif ext in (".ts", ".tsx", ".jsx"):
            for line in lines:
                m_comp = re.search(
                    r"export\s+(?:default\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)",
                    line,
                )
                if m_comp:
                    comp_name = m_comp.group(1)
                    clean_comp = re.sub(r"^(?:Legit|Fake|Mock|Dummy|Temp)", "", comp_name)
                    return f"{clean_comp or comp_name}{ext}"

        elif ext == ".md":
            for line in lines:
                if line.startswith("# "):
                    title = line.lstrip("# ").strip()
                    clean = re.sub(r"[^\w\s-]", "", title).strip()
                    slug = re.sub(r"[\s_]+", "_", clean).lower()
                    clean_slug = re.sub(r"^(?:legit|fake|mock|dummy)_", "", slug)
                    if clean_slug and len(clean_slug) <= 35:
                        return f"{clean_slug}.md"

        elif ext == ".sql":
            for line in lines:
                m_table = re.search(
                    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)",
                    line,
                    re.I,
                )
                if m_table:
                    tname = m_table.group(1).lower()
                    clean_tname = re.sub(r"^(?:legit|fake|mock|dummy)_", "", tname)
                    return f"{clean_tname or tname}_schema.sql"

        return None

    @classmethod
    def naturalize_filename(
        cls,
        raw_path_or_name: str,
        content: str | bytes | None = None,
        topic_hint: str = "",
    ) -> str:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        কনটেন্ট বিশ্লেষণ করে স্বাভাবিক, বিশ্বাসযোগ্য অর্গানিক নাম তৈরি।
        কোথাও কৃত্রিম বা 'legit'/'fake' জাতীয় শব্দ থাকবে না।
        দেখে মনে হবে একজন দক্ষ ডেভেলপার নিজে হাতে ফাইলটি তৈরি করেছেন।
        """
        filename = os.path.basename(raw_path_or_name)
        ext = Path(filename).suffix.lower()

        # যদি নাম ইতিমধ্যে স্বাভাবিক ডেভেলপার ফাইলের মতো হয়, অপরিবর্তিত রাখা
        if not cls.is_bot_like_name(filename):
            return filename

        # ১. কনটেন্ট থেকে নিখুঁত প্রাসঙ্গিক নাম উদ্ধার
        text_content = ""
        if isinstance(content, str):
            text_content = content
        elif isinstance(content, bytes):
            try:
                text_content = content.decode("utf-8", errors="ignore")
            except Exception:
                text_content = ""
        elif os.path.isfile(raw_path_or_name):
            try:
                text_content = Path(raw_path_or_name).read_text(encoding="utf-8", errors="ignore")[
                    :4000
                ]
            except Exception:
                text_content = ""

        if text_content:
            derived_name = cls._inspect_content_for_name(text_content, ext)
            if derived_name and not cls.is_bot_like_name(derived_name):
                return derived_name

        # ২. টপিক হিন্ট থাকলে তা দিয়ে ক্লিন নাম
        if topic_hint:
            clean_hint = re.sub(
                r"\b(legit|fake|dummy|mock|bot|temp|tmp)\b", "", topic_hint, flags=re.I
            )
            slug = re.sub(r"[^\w\s]", "", clean_hint).strip()
            slug = re.sub(r"[\s_]+", "_", slug).lower()
            if slug:
                return f"{slug[:25]}{ext or '.py'}"

        # ৩. অর্গানিক ডেভেলপার ফলব্যাক পুল
        candidates = ORGANIC_FALLBACKS.get(ext)
        if candidates:
            return random.choice(candidates)

        return f"module_{random.randint(10, 99)}{ext or '.txt'}"

    # ব্যাকওয়ার্ড কম্প্যাটিবিলিটির জন্য মেথড অ্যালিয়াস
    legitimize_filename = naturalize_filename

    @classmethod
    def humanize_conversation_title(cls, prompt: str) -> str:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        প্রম্পট থেকে ৪-৬টি স্বাভাবিক শব্দ নিয়ে চ্যাট টাইটেল তৈরি।
        রোবোটিক 'Session-...', 'Task-...', 'legit', 'bot' ইত্যাদি পরিহার করে
        মানুষের স্বাভাবিক সার্চ বা চ্যাটের মতো দেখাবে।
        """
        clean = re.sub(r"[^\w\s]", "", prompt).strip()
        words = clean.split()
        if not words or len(words) < 2:
            return ""  # ফাঁকা রাখলে Claude/ChatGPT নিজে সুন্দর নাম বানায়

        # প্রথম ৪-৫টি শব্দ নিয়ে টাইটেল
        title_words = words[:5]
        title = " ".join(title_words).capitalize()

        # অপ্রাসঙ্গিক রোবট ও কৃত্রিম টোকেন ফিল্টার
        for bad in [
            "system",
            "user",
            "assistant",
            "session",
            "task",
            "bot",
            "legit",
            "fake",
            "claude",
            "chatgpt",
            "openai",
            "anthropic",
            "v0",
        ]:
            title = re.sub(rf"\b{bad}\b", "", title, flags=re.IGNORECASE).strip()

        return title if len(title) >= 3 else ""

    @classmethod
    def humanize_prompt(cls, prompt: str) -> str:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        ইউজার নীতি: "human logic... qstn e amon vabe koro jeno ans thik e paowa jay and simple qstn o mone hoy"
        রোবোটিক এজেন্টের খটমটে কমান্ডকে একজন স্বাভাবিক মানুষের কথোপকথনমূলক সহজ প্রশ্নে রূপান্তর:
        ১. 'SYSTEM DIRECTIVE', 'AGENT INSTRUCTION' ইত্যাদি যান্ত্রিক হেডার ছেঁটে ফেলা।
        ২. কঠোর কমান্ড ("DO NOT TALK. RETURN RAW JSON ONLY.") কে স্বাভাবিক ও মার্জিত মানবীয় ভাষায় রূপান্তর।
        ৩. মূল কারিগরি নির্দেশ এবং সঠিক উত্তর পাওয়ার নির্ভুলতা পুরোপুরি বজায় রাখা।
        """
        text = prompt.strip()
        if not text:
            return text

        # বাংলা মন্তব্য: প্রম্পটে যদি 'Copy this to your AI:' বা Conductor হেডার বা Autonomous Agent ব্লুপ্রিন্ট থাকে, তা অক্ষুণ্ণ রাখা
        text_lower = text.lower()
        if (
            "copy this to your ai" in text_lower
            or "copy and paste this into your ai" in text_lower
            or "prompt to run in your ai" in text_lower
            or "autonomous execution agent" in text_lower
            or "implementation task brief" in text_lower
            or "assigned task:" in text_lower
            or "task to execute:" in text_lower
        ):
            return text

        # ১. রোবোটিক প্রিফিক্স ফিল্টার
        robotic_prefixes = [
            r"^SYSTEM\s*(?:PROMPT|DIRECTIVE|INSTRUCTION)?\s*:?\s*",
            r"^AGENT\s*(?:TASK|INSTRUCTION)?\s*:?\s*",
            r"^FAIL-SAFE\s*(?:PROTOCOL)?\s*:?\s*",
            r"^CRITICAL\s*COMMAND\s*:?\s*",
            r"^MANDATORY\s*DIRECTIVE\s*:?\s*",
        ]
        for pat in robotic_prefixes:
            text = re.sub(pat, "", text, flags=re.IGNORECASE | re.MULTILINE).strip()

        # ২. রোবোটিক আউটপুট বাধ্যবাধকতাকে মানুষের মতো পরিচ্ছন্ন রিকোয়েস্টে রূপান্তর (র্যান্ডম ভ্যারিয়েশন যাতে একই স্টাইল বারবার না আসে)
        json_phrases = [
            "Please format the output as clean JSON, thanks!",
            "Just raw JSON output please, no surrounding text needed.",
            "Format the output as valid JSON.",
            "Only the clean JSON object/array please.",
        ]
        code_phrases = [
            "Just the clean code snippet would be great, thanks!",
            "Only need the code implementation, no extra commentary.",
            "Please output the clean code directly.",
            "Just the working code snippet please.",
        ]
        explain_phrases = [
            "No need for a long explanation, just the code is perfect.",
            "Skip the explanation, just the code.",
            "A concise solution without long explanation is preferred.",
        ]
        preamble_phrases = [
            "Feel free to get straight to the code without extra intro.",
            "Skip any intro or explanations, straight into the solution.",
            "No preamble needed, straight to the answer please.",
        ]

        text = re.sub(
            r"(?:STRICTLY\s*)?ONLY\s+OUTPUT\s+(?:RAW\s+)?JSON\b.*",
            random.choice(json_phrases),
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(?:STRICTLY\s*)?ONLY\s+OUTPUT\s+(?:RAW\s+)?CODE\b.*",
            random.choice(code_phrases),
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"DO\s+NOT\s+EXPLAIN\b.*",
            random.choice(explain_phrases),
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"DO\s+NOT\s+INCLUDE\s+(?:ANY\s+)?PREAMBLE\b.*",
            random.choice(preamble_phrases),
            text,
            flags=re.IGNORECASE,
        )

        return text

    @classmethod
    def scrub_identity_and_watermarks(
        cls,
        text: str,
        brand_name: str = "SupremeAI",
        white_label: bool = True,
    ) -> str:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        "কইয়ের তেলেই কই ভাজা, কিন্তু নিজের নামে মাছ বেচা" (White-Label Philosophy):
        ১. ইন্টারনাল থিংকিং ট্যাগ (<thought>, <antThinking>, <thinking>, [thinking process:]) বাদ দেওয়া।
        ২. রোবটিক সেলফ-আইডেন্টিটি ('I am Claude...', 'As ChatGPT...', 'As Gemini...', 'As an AI...') বাদ দেওয়া।
        ৩. চ্যাটি রোবটিক ওপেনার ('Certainly! Here is...', 'Sure, I can help with that!') বাদ দেওয়া।
        ৪. ফুটার ও কোড কমেন্টে থাকা থার্ড-পার্টি ওয়াটারমার্ক (Claude, ChatGPT, Gemini, Genkit, Copilot, OpenAI, Anthropic, v0) স্ক্রাব করা।
        ৫. ব্যবহারকারীকে শুধু পরিষ্কার আউটপুট ও সলিউশন দেওয়া; আন্ডারলাইং প্ল্যাটফর্মের কোনো চিহ্ন না রাখা।
        """
        if not text:
            return ""

        # ১. ইন্টারনাল থিংকিং ব্লক
        text = re.sub(
            r"(?is)<(?:antThinking|thought|thinking)>.*?</(?:antThinking|thought|thinking)>",
            "",
            text,
        )
        text = re.sub(r"(?is)\[thinking process:.*?\]", "", text)

        # ২. ওপেনিং ব্র্যান্ডিং ও রোবটিক ঘোষণা (Claude, ChatGPT, Gemini, Copilot, DeepSeek, etc.)
        opening_patterns = [
            r"^\s*(?:as an? (?:ai|large language model|assistant|chatgpt|claude|gemini|openai|anthropic|google ai)[^\n]*\n*)",
            r"^\s*(?:i am (?:claude|chatgpt|gemini|an ai|a large language model|an assistant)[^\n]*\n*)",
            r"^\s*(?:hello!?|hi!?|hey!?)[ \t]+(?:i am|i'm)[ \t]+(?:claude|chatgpt|gemini|an ai)[^\n]*\n*",
            r"^\s*(?:certainly|sure thing|sure!|of course|happy to help)[!,.\n]+(?:here (?:is|are)[^\n]*:?)?\s*",
            r"^\s*(?:here (?:is|are) (?:the|a) (?:code|solution|implementation)[^:\n]*:?)\s*",
        ]
        for pat in opening_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE).strip()

        # ৩. ফুটার ওয়াটারমার্ক ও সাইটেশন (Claude, ChatGPT, Gemini, Genkit, Copilot, OpenAI, Anthropic, v0)
        footer_patterns = [
            r"\n*(?:generated by|powered by|created with|written by|built with)\s+(?:claude(?: 3(?:\.5)? (?:sonnet|opus|haiku))?|chatgpt|gpt-4o?|openai|anthropic|gemini(?: 1\.5)?|genkit|google|cursor|copilot|github copilot|v0)[^\n]*",
        ]
        for fpat in footer_patterns:
            text = re.sub(fpat, "", text, flags=re.IGNORECASE)

        # ৪. কোড কমেন্টে থার্ড-পার্টি ওয়াটারমার্ক স্ক্রাব করা (# Generated by ChatGPT, // Created by Claude, # Author: OpenAI Assistant, etc.)
        code_comment_watermarks = [
            r"^[ \t]*(?:#|//|/\*)\s*(?:generated by|created by|powered by|written by|author:?)\s+(?:chatgpt|claude|gemini|openai|anthropic|copilot|genkit)[^\n]*(?:\*/)?\n?",
        ]
        for cpat in code_comment_watermarks:
            text = re.sub(cpat, "", text, flags=re.IGNORECASE | re.MULTILINE)

        if white_label:
            # ৫. টেক্সটের ভেতরে অনিচ্ছাকৃত ব্র্যান্ড লিকেজ নিউট্রালাইজেশন ("Using Google's Genkit" -> "Using autonomous pipeline")
            text = re.sub(
                r"\b(?:Anthropic'?s?\s+Claude|OpenAI'?s?\s+ChatGPT|Google'?s?\s+Gemini)\b",
                brand_name,
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(
                r"\b(?:Google'?s?\s+Genkit)\b", f"{brand_name} Workflow", text, flags=re.IGNORECASE
            )

        return text.strip()

    @classmethod
    def white_label_solution(cls, text: str, brand_name: str = "SupremeAI") -> str:
        """
        বাংলা সারসংক্ষেপ:
        ------------------
        সম্পূর্ণ হোয়াইট-লেবেল সলিউশন জেনারেটর।
        তৃতীয় পক্ষের সমস্ত চিহ্ন মুছে শুধুমাত্র নিখুঁত আউটপুট ও সলিউশন ব্যবহারকারীর সামনে উপস্থাপন করে।
        """
        return cls.scrub_identity_and_watermarks(text, brand_name=brand_name, white_label=True)


# অ্যালিয়াস
LegitFilePresenter = NaturalFilePresenter
SupremeWhiteLabel = NaturalFilePresenter

__all__ = ["NaturalFilePresenter", "LegitFilePresenter", "SupremeWhiteLabel"]
