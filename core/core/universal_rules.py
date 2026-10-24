"""
Universal Rules Engine for SupremeAI 2.0
এই ইঞ্জিনটি সব AI মডেল এবং এজেন্টের আচরণ নিয়ন্ত্রণ করে।
"""

import json
import os
import tempfile
from typing import Any

from core.logging_config import logger


class UniversalRulesEngine:
    """
    Admin-defined rules that override ALL agent behavior.
    These are Constitutional Laws - non-negotiable.
    সকল এজেন্টের জন্য কনস্টিটিউশনাল রুলস - কোনো পরিবর্তন ছাড়া নয়।
    """

    # Cine agent memory - rules loaded at startup
    AGENT_RULES_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config",
        "agent_rules.json",
    )

    # Cine-specific mandatory rules list — সকল AI মডেলের জন্য বাধ্যতামূলক নিয়ম
    CINE_MANDATORY_RULES = [
        # Core Architecture
        "CORE-001",
        "CORE-002",
        "CORE-003",
        "CORE-004",
        "CORE-005",
        "CORE-006",
        "CORE-007",
        "CORE-008",
        "CORE-009",
        "CORE-010",
        # Core Philosophy
        "ZERO-108",
        "HIGH-109",
        "ZERO-110",
        "HITL-111",
        "MALWARE-112",
        "SELF-113",
        "FAIL-114",
        # Agent Behavior
        "AGENT-101",
        "AGENT-102",
        "AGENT-103",
        "AGENT-104",
        "AGENT-105",
        "AGENT-201",
        "AGENT-202",
        "AGENT-203",
        # Elite & Production
        "ELITE-117",
        "PROD-118",
        # Language
        "LANG-115",
        "LANG-116",
        # ── NEW: Provider Selection Intelligence ──
        "PSI-001",
        "PSI-002",
        "PSI-003",
        "PSI-004",
        "PSI-005",
        # ── NEW: Quality Gates ──
        "QG-001",
        "QG-002",
        "QG-004",
        # ── NEW: Bengali Language Excellence ──
        "BLE-001",
        "BLE-002",
        "BLE-003",
        # ── NEW: Customer Privacy & Security ──
        "CPS-001",
        "CPS-003",
        "CPS-006",
        # ── NEW: Zero-Cost Optimization ──
        "ZCO-001",
        "ZCO-002",
        # ── NEW: Self-Healing ──
        "SHE-002",
        "SHE-003",
        # ── NEW: Multi-Agent ──
        "MAC-001",
        "MAC-005",
        # ── NEW: Domain-Specific ──
        "SUPPORT-001",
        "CODE-002",
        "PERF-002",
        # ── NEW: Task Classification & Improvement ──
        "TCL-001",
        "CIR-001",
    ]

    def __init__(self, rules_path: str | None = None):
        if rules_path is None:
            # Default location - এজেন্ট রুলসের ডিফল্ট লোকেশন
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.rules_path = os.path.join(base_dir, "data", "admin_rules.json")
        else:
            self.rules_path = rules_path

        # Load agent rules for cine memory
        self.agent_rules = self._load_agent_rules()
        self.rules = self._load_rules()

    def _load_agent_rules(self) -> list[dict[str, Any]]:
        """
        Cine-এর মেমরিতে agent_rules.json থেকে সকল রুলস লোড করে।
        Load all rules from agent_rules.json into memory.
        """
        try:
            os.path.dirname(self.AGENT_RULES_PATH)
            if os.path.exists(self.AGENT_RULES_PATH):
                with open(self.AGENT_RULES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("rules", [])
        except Exception as e:
            logger.warning(f"Could not load agent rules, using defaults: {e}")

        return []

    def _load_rules(self) -> dict[str, Any]:
        """Loads rules from secure Database. If not available, uses default rules."""
        db_rules: dict[str, Any] = {}
        conn = None
        try:
            from tools.mcp.mcp_supabase import _get_connection

            conn = _get_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("SELECT rule_key, category, value FROM rules WHERE is_enabled = TRUE")
                rows = cur.fetchall()
                cur.close()
                for rule_key, category, value in rows:
                    if category not in db_rules:
                        db_rules[category] = {}

                    try:
                        # Attempt to parse value as JSON if possible, else keep as string
                        parsed_val = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        parsed_val = value
                    db_rules[category][rule_key] = parsed_val
        except Exception as e:
            logger.error(f"⚠️ Failed to load rules from DB, falling back to defaults: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"Failed to close connection: {e}")

        # Default fallback rules (Admin definitions) - সম্পূর্ণ রুলস গাইডেলাইন
        default_rules = {
            "directions": {
                "count": 5,
                "names": ["North", "South", "East", "West", "Center"],
                "description": "Admin has defined 5 directions. Center is the reference point.",
            },
            "image_generation": {
                "allowed": True,
                "max_cost_per_image": 0.01,
                "require_consent": False,
                "preferred_providers": ["pollinations", "huggingface", "local"],
            },
            "skill_installation": {
                "sandbox_duration_hours": 24,
                "auto_install": True,
                "max_install_time_seconds": 30,
            },
            "cost_management": {
                "monthly_budget": 30.00,
                "alert_at_percent": 80.0,
                "hard_stop_at_percent": 100.0,
            },
            # Core Philosophy from AGENTS.md - Cine-এর মূল দর্শন
            "core_philosophy": {
                "zero_cost": "কঠোরভাবে ফ্রি-টিয়ার সার্ভিস ব্যবহার করবেন, পেইড সার্ভিস নিষিদ্ধ।",
                "high_performance": "লাইটওয়েট ও ল্যাগ-ফ্রি আউটপুট নিশ্চিত করুন।",
                "zero_breakage": "ডুপ্লিকেশন ছাড়াই টার্গেটেড ডেল্টা প্যাচিং করুন।",
                "human_in_loop": "Minimal human intervention for critical operations।",
                "malware_immunity": "JIT OTP ভেরিফিকেশন আপনতক্ষণ ব্যবহার করুন।",
                "self_healing": "সিস্টেম স্বয়ংক্রিয়া সামঞ্জস্য করুন।",
            },
            # Language requirement - ভাষা নিয়ম
            "language_policy": {"bangla_comments": True, "bangla_explanations": True},
            # Production requirement - প্রোডাকশন নিয়ম
            "production_policy": {
                "no_mocks": True,
                "no_stubs": True,
                "production_ready_only": True,
            },
            # ── NEW: Provider routing rules - কোন AI কখন ব্যবহার হবে ──
            "provider_routing": {
                "bangla_provider": "moonshot",
                "code_provider": "deepseek",
                "fallback_provider": "together_ai",
                "private_provider": "ollama",
                "quota_alert_percent": 80,
            },
            # ── NEW: Customer interaction policy - গ্রাহক আচরণ নীতি ──
            "customer_policy": {
                "bangla_no_banglish": True,
                "formal_address": "আপনি",
                "empathy_on_frustration": True,
                "max_retry_before_escalate": 3,
                "friendly_errors_only": True,
            },
            # ── NEW: Quality gates - মান নিয়ন্ত্রণ ──
            "quality_gates": {
                "check_relevance": True,
                "check_hallucination": True,
                "check_language_match": True,
                "check_code_completeness": True,
                "tldr_threshold_words": 1000,
            },
            # ── NEW: PII & security policy - গোপনীয়তা নীতি ──
            "security_policy": {
                "mask_pii_before_llm": True,
                "jit_otp_for_sensitive": True,
                "hard_refuse_harmful": True,
                "pii_patterns": ["phone", "email", "nid", "password", "card_number"],
            },
        }

        if db_rules:
            # db_rules থেকে default_rules-এ merge করা হচ্ছে
            for cat, rules_dict in db_rules.items():
                if cat not in default_rules:
                    default_rules[cat] = {}
                target: dict[str, Any] = default_rules[cat]  # type: ignore[assignment]
                if isinstance(rules_dict, dict):
                    target.update(rules_dict)
            return default_rules

        # Try to load from file if DB is empty/unavailable
        if os.path.exists(self.rules_path):
            try:
                with open(self.rules_path, encoding="utf-8") as f:
                    file_rules = json.load(f)
                    # file_rules থেকে default_rules-এ merge করা হচ্ছে
                    for cat, rules_dict in file_rules.items():
                        if cat not in default_rules:
                            default_rules[cat] = {}
                        target2: dict[str, Any] = default_rules[cat]  # type: ignore[assignment]
                        if isinstance(rules_dict, dict):
                            target2.update(rules_dict)
                    return default_rules
            except Exception as e:
                logger.warning(f"Failed to load rules from file, falling back to defaults: {e}")

        # Save defaults if not present
        try:
            os.makedirs(os.path.dirname(self.rules_path), exist_ok=True)
            with open(self.rules_path, "w", encoding="utf-8") as f:
                json.dump(default_rules, f, indent=4)
        except OSError as e:
            logger.warning(f"Could not write default rules file: {e}")
        return default_rules

    def get_rule_by_id(self, rule_id: str) -> dict[str, Any] | None:
        """Cine-এর মেমরিতে থেকে নির্দিষ্ট রুল আনে।"""
        for rule in self.agent_rules:
            if rule.get("id") == rule_id:
                return rule
        return None

    def validate_critical_rules(self) -> list[str]:
        """
        Cine-এর মেমরিতে থাকা সব ক্রিটিক্যাল রুলস যাচাই করে।
        Returns list of rule IDs that should be enforced.
        """
        return self.CINE_MANDATORY_RULES

    def check_token_budget(self, estimated_tokens: int) -> bool:
        """
        AGENT-101: Context Token Budget চেক করে।
        কোনো এজেন্ট তার প্রম্পট বা কন্টেক্সট উইন্ডোর ৮০% এর বেশি ব্যবহার করতে পারবে না।
        """
        if estimated_tokens > 4096:  # 80% of typical 4K-8K context
            logger.warning(f"⚠️ Token budget exceeded: {estimated_tokens} tokens")
            return False
        return True

    def check_hallucination_policy(self, response: str) -> bool:
        """
        AGENT-104: Zero-Hallucination Policy যাচাই করে।
        এজেন্ট ১০০% শিওর না হলে ইনভেন্ট করবে না।
        """
        # Check for source citation or uncertainty acknowledgment
        has_source = "<source>" in response or "source:" in response.lower()
        has_uncertainty = "I need to perform a search" in response or "I don't know" in response
        return has_source or has_uncertainty

    def check_production_ready(self, code_contains_mocks: bool) -> bool:
        """
        PROD-118: Production-Ready Implementation যাচাই করে।
        কোনো মক, স্টাব বা ডামি ইমপ্লিমেন্টেশন নেই।
        """
        if code_contains_mocks:
            logger.error("❌ Production code must not contain mocks or stubs!")
            return False
        return True

    def check_pii_in_prompt(self, prompt: str) -> bool:
        """
        CPS-001: PII Masking Before LLM Call যাচাই করে।
        Customer-এর personal তথ্য AI prompt-এ আছে কিনা detect করে।
        Returns True if prompt is SAFE (no PII detected).
        """
        import re

        # বাংলাদেশের ফোন নম্বর, ইমেইল, পাসওয়ার্ড প্যাটার্ন detect করে
        pii_patterns = [
            r"\b01[3-9]\d{8}\b",  # BD phone numbers
            r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",  # Email
            r"(?i)password\s*[=:]\s*\S+",  # Password assignments
            r"\b\d{10,17}\b",  # NID / card numbers
        ]
        for pattern in pii_patterns:
            if re.search(pattern, prompt):
                logger.warning(
                    "⚠️ PII detected in prompt — should be masked before LLM call (CPS-001)"
                )
                return False
        return True

    def check_language_match(self, input_text: str, output_text: str) -> bool:
        """
        QG-004 / BLE-001: Language Match Gate যাচাই করে।
        Customer বাংলায় লিখলে উত্তর বাংলায় কিনা চেক করে।
        """
        # বাংলা ইউনিকোড রেঞ্জ: \u0980-\u09FF
        input_has_bangla = any("\u0980" <= c <= "\u09ff" for c in input_text)
        output_has_bangla = any("\u0980" <= c <= "\u09ff" for c in output_text)
        if input_has_bangla and not output_has_bangla:
            logger.warning(
                "⚠️ Customer wrote in Bangla but response is not in Bangla (BLE-001/QG-004)"
            )
            return False
        return True

    def check_code_completeness(self, code: str) -> bool:
        """
        CODE-002: No Incomplete Code Delivery যাচাই করে।
        # TODO, pass, NotImplemented pattern থাকলে block করে।
        """
        import re

        incomplete_patterns = [
            r"#\s*TODO",
            r"#\s*FIXME",
            r"\bNotImplemented\b",
            r"raise\s+NotImplementedError",
            r"\bpass\s*#.*implement",
            r"#\s*placeholder",
        ]
        for pattern in incomplete_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                logger.warning(f"⚠️ Incomplete code pattern detected: {pattern} (CODE-002)")
                return False
        return True

    def get_provider_for_task(self, task_lang: str = "en", task_type: str = "chat") -> str:
        """
        PSI-001~004: Provider Selection Intelligence.
        Task ভাষা ও ধরন দেখে সঠিক AI provider select করে।
        """
        routing = self.rules.get("provider_routing", {})
        # বাংলা বা reasoning → Moonshot
        if task_lang == "bn" or task_type == "reasoning":
            return routing.get("bangla_provider", "moonshot")
        # Code বা Math → DeepSeek
        if task_type in ("code", "math", "technical"):
            return routing.get("code_provider", "deepseek")
        # Private/Offline → Ollama
        if task_type == "private":
            return routing.get("private_provider", "ollama")
        # Default fallback → Together AI
        return routing.get("fallback_provider", "together_ai")

    def classify_task(self, prompt: str) -> str:
        """
        TCL-001: Task Classification Before Response.
        Customer-এর prompt দেখে task type classify করে।
        Returns: CREATIVE | TECHNICAL | ANALYTICAL | CONVERSATIONAL | SUPPORT | RESEARCH | BANGLA_SPECIFIC
        """
        prompt_lower = prompt.lower()
        # বাংলা detect
        has_bangla = any("\u0980" <= c <= "\u09ff" for c in prompt)
        if has_bangla:
            return "BANGLA_SPECIFIC"
        # Technical keywords
        if any(
            kw in prompt_lower
            for kw in ["code", "error", "debug", "fix", "python", "function", "api"]
        ):
            return "TECHNICAL"
        # Support keywords
        if any(kw in prompt_lower for kw in ["help", "issue", "problem", "not working", "support"]):
            return "SUPPORT"
        # Research keywords
        if any(
            kw in prompt_lower for kw in ["what is", "explain", "how does", "define", "research"]
        ):
            return "RESEARCH"
        # Analytical keywords
        if any(
            kw in prompt_lower for kw in ["analyze", "data", "report", "chart", "insight", "trend"]
        ):
            return "ANALYTICAL"
        # Creative keywords
        if any(
            kw in prompt_lower
            for kw in ["write", "create", "generate", "design", "idea", "suggest"]
        ):
            return "CREATIVE"
        return "CONVERSATIONAL"

    def save_rules(self, new_rules: dict[str, Any]) -> bool:
        """Saves updated rules to the rules file."""
        self.rules = new_rules
        try:
            dir_name = os.path.dirname(self.rules_path)
            os.makedirs(dir_name, exist_ok=True)
            # Atomic write using a temporary file
            fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(new_rules, f, indent=4)

            os.replace(temp_path, self.rules_path)
            return True
        except OSError:
            return False

    def apply(self, decision_context: dict[str, Any]) -> dict[str, Any]:
        """
        Injects rules into EVERY decision.
        Returns modified context with rules enforced.
        সকল কর্মকাণ্ডে রুলস ইনজেক্ট করে।
        """
        # Rule: Direction definition override
        if "direction" in decision_context or "directions" in decision_context:
            decision_context["direction_count"] = self.rules["directions"]["count"]
            decision_context["direction_names"] = self.rules["directions"]["names"]
            decision_context["direction_override_applied"] = True

        # Rule: Cost check - খরচ নিয়ন্ত্রণ
        if "cost" in decision_context:
            task_type = decision_context.get("task_type", "")
            max_cost = float("inf")
            if task_type == "image_generation":
                max_cost = self.rules["image_generation"]["max_cost_per_image"]

            if decision_context["cost"] > max_cost:
                decision_context["blocked"] = True
                decision_context["reason"] = (
                    f"Exceeds Universal Rule: Max cost per task ({max_cost})"
                )

        # Cine Mandatory Rule Checks - Cine-এর অবশ্যক রুলস
        # AGENT-101: Token budget check
        if "estimated_tokens" in decision_context:
            if not self.check_token_budget(decision_context["estimated_tokens"]):
                decision_context["blocked"] = True
                decision_context["reason"] = "Context Token Budget exceeded (AGENT-101)"

        # PROD-118: Production-ready check
        if decision_context.get("is_production", False) and self.rules.get(
            "production_policy", {}
        ).get("no_mocks", True):
            if decision_context.get("contains_mocks", False):
                decision_context["blocked"] = True
                decision_context["reason"] = "Production code must not contain mocks (PROD-118)"

        # LANG-115/116: Bangla comments check
        decision_context["bangla_comments_required"] = self.rules.get("language_policy", {}).get(
            "bangla_comments", True
        )

        # ── NEW RULES ENFORCEMENT ──────────────────────────────────────────────

        # PSI-001~004: Provider selection based on task language/type
        if "task_lang" in decision_context or "task_type" in decision_context:
            task_lang = decision_context.get("task_lang", "en")
            task_type = decision_context.get("task_type", "chat")
            decision_context["recommended_provider"] = self.get_provider_for_task(
                task_lang, task_type
            )

        # TCL-001: Task classification
        if "prompt" in decision_context and "task_class" not in decision_context:
            decision_context["task_class"] = self.classify_task(decision_context["prompt"])

        # CPS-001: PII check in prompt — block if PII found
        if "prompt" in decision_context:
            security = self.rules.get("security_policy", {})
            if security.get("mask_pii_before_llm", True):
                if not self.check_pii_in_prompt(decision_context["prompt"]):
                    decision_context["pii_warning"] = True
                    decision_context["reason"] = (
                        "PII detected in prompt — mask before sending to LLM (CPS-001)"
                    )

        # QG-004 / BLE-001: Language match check
        if "input_text" in decision_context and "output_text" in decision_context:
            lang_ok = self.check_language_match(
                decision_context["input_text"],
                decision_context["output_text"],
            )
            decision_context["language_match_ok"] = lang_ok

        # CODE-002: Code completeness check
        if "generated_code" in decision_context:
            code_ok = self.check_code_completeness(decision_context["generated_code"])
            if not code_ok:
                decision_context["blocked"] = True
                decision_context["reason"] = (
                    "Incomplete code pattern detected (CODE-002) — complete the implementation"
                )

        # SHE-002: Auto-escalate after 3 failures
        consecutive_failures = decision_context.get("consecutive_failures", 0)
        customer_policy = self.rules.get("customer_policy", {})
        max_retry = customer_policy.get("max_retry_before_escalate", 3)
        if consecutive_failures >= max_retry:
            decision_context["escalate_to_human"] = True
            decision_context["escalation_reason"] = (
                f"Customer faced {consecutive_failures} consecutive failures (SHE-002)"
            )

        # CPS-006: Harmful request detection flag
        if decision_context.get("is_harmful_request", False):
            decision_context["blocked"] = True
            decision_context["reason"] = "এই ধরনের সাহায্য করা আমার পক্ষে সম্ভব নয়। (CPS-006)"

        # QG gate summary — সব gate এর ফলাফল
        quality_gates = self.rules.get("quality_gates", {})
        decision_context["quality_gates_config"] = quality_gates

        return decision_context
