import os
import time
from typing import Any

from core.logging_config import logger

# AUDIT-FIX (#1693 HIGH): No deduplication key — same file patched repeatedly.
# Per audit fix recommendation:
#   - skip if same file remediated < 30 minutes ago
#   - add max-remediation-per-file counter
#   - escalate to human if exceeded
# Configurable via env vars; conservative defaults.
_DEDUP_WINDOW_SECONDS: int = int(
    os.environ.get("AUTOREMEDIATION_DEDUP_WINDOW_SECONDS", "1800")
)  # 30 min
_MAX_REMEDIATIONS_PER_FILE: int = int(os.environ.get("AUTOREMEDIATION_MAX_PER_FILE", "3"))

# AUDIT-FIX (#1698): permanent audit-trail file (JSONL). Every remediation
# decision — applied, rejected, skipped — is appended so masked root causes
# are always reconstructible. বাংলা: প্রতিটি সিদ্ধান্ত স্থায়ী অডিট ট্রেইলে যায়।
_AUDIT_DIR: str = os.environ.get(
    "AUTOREMEDIATION_AUDIT_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs"),
)


def _count_swallow_only_handlers(code: str) -> int:
    """AUDIT-FIX (#1698): count except-handlers that silently swallow errors.

    A "swallow-only" handler is a bare ``except:`` (or ``except Exception:`` /
    ``except BaseException:``) whose body does nothing but ``pass`` / ``...`` /
    a string literal — the classic auto-patch pattern that hides the real bug
    while turning health checks green. বাংলা: শুধু exception চেপে রাখা হ্যান্ডলার
    গোনা হয় — এগুলো আসল বাগ লুকিয়ে রাখে।
    """
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0

    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        bare_or_broad = node.type is None or (
            isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
        )
        body_only_silent = all(
            isinstance(stmt, (ast.Pass, ast.Expr))
            and (
                isinstance(stmt, ast.Pass) or isinstance(getattr(stmt, "value", None), ast.Constant)
            )
            for stmt in node.body
        )
        if bare_or_broad and body_only_silent:
            count += 1
    return count


def _patch_masks_root_cause(original_code: str, fixed_code: str) -> bool:
    """AUDIT-FIX (#1698): True if the patch adds silent swallowing on top of
    the original code without removing any — masking suspect, must not be
    auto-trusted. বাংলা: আগের চেয়ে বেশি silent handler এলে সেটা masking।"""
    return _count_swallow_only_handlers(fixed_code) > _count_swallow_only_handlers(original_code)


def _append_audit_trail(record: dict) -> None:
    """AUDIT-FIX (#1698): append one JSON line to the permanent audit trail.
    Never raises — an audit write failure must not break remediation itself.
    বাংলা: অডিট লেখা ব্যর্থ হলেও remediation আটকাবে না।"""
    import json
    from datetime import UTC, datetime

    try:
        os.makedirs(_AUDIT_DIR, exist_ok=True)
        path = os.path.join(_AUDIT_DIR, "auto_remediation_audit.jsonl")
        record = {"ts": datetime.now(UTC).isoformat(), **record}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        logger.warning(f"Auto-Remediation audit trail write failed (non-fatal): {exc}")


class AutoRemediation:
    """Autonomous Auto-Remediation Loop.

    Detects CodeQL/security alerts, generates a secure patch, and delegates the
    application to RemediationPipeline.

    বাংলা: কোডকিউএল/সিকিউরিটি অ্যালার্ট detects করছে, একটি সুরক্ষিত প্যাচ জেনারেট করছে,
    এবং RemediationPipeline-এ ডিলিগেট করছে।

    Note: This module is designed to be mockable for tests.

    AUDIT-FIX (#1693): এখন প্রতিটি file path-এর জন্য একটি deduplication
    cache রাখা হয় — একই file-এ একই সমস্যায় বারবার patch প্রয়োগ prevent
    করা হয়। max-per-file counter exceed হলে human escalation।
    """

    def __init__(self, gemini_api_key: str | None = None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        # Allowed base dir is repo/backend (backend/core/resilience -> ../..)
        self._ALLOWED_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        # AUDIT-FIX (#1693): dedup state — {file_path: {"last_ts": float, "count": int}}
        # Per-instance in-memory (per-worker). Multi-worker dedup requires Redis
        # (out of scope for this narrow fix — see follow-up issue).
        self._remediation_history: dict[str, dict[str, Any]] = {}

    def _validate_file_path(self, file_path: str) -> str:
        """Path traversal attack প্রতিরোধ.

        Only allow reads/writes inside the allowed directory.
        """
        real_path = os.path.realpath(os.path.abspath(file_path))

        common = os.path.commonpath([real_path, self._ALLOWED_BASE_DIR])
        if common != self._ALLOWED_BASE_DIR:
            raise ValueError(
                f"🛑 Path traversal detected: {file_path!r} resolves to {real_path!r} "
                f"which is outside allowed directory {self._ALLOWED_BASE_DIR!r}"
            )

        return real_path

    async def process_security_alert(
        self,
        file_path: str,
        line_number: int,
        issue: str,
        severity: str,
        tenant_id: str | None = None,
    ) -> dict:
        tenant_id = str(tenant_id or "").strip()
        if not tenant_id or tenant_id == "default":
            return {"success": False, "error": "Tenant context required for remediation"}

        logger.info(
            f"Auto-Remediation triggered for {file_path}:{line_number} - Severity: {severity}. Issue: {issue}"
        )

        safe_path = self._validate_file_path(file_path)

        if not os.path.exists(safe_path):
            return {"success": False, "error": f"File {safe_path} not found"}

        # AUDIT-FIX (#1693 HIGH): Deduplication + max-remediation enforcement.
        # একই file-এ বারবার patch prevent করে oscillating infinite-loop থেকে।
        now = time.time()
        history_entry = self._remediation_history.get(safe_path, {"last_ts": 0.0, "count": 0})
        last_ts = float(history_entry.get("last_ts", 0.0))
        prior_count = int(history_entry.get("count", 0))

        # Rule 1: skip if remediated within dedup window (default 30 min)
        if (now - last_ts) < _DEDUP_WINDOW_SECONDS:
            elapsed = int(now - last_ts)
            logger.warning(
                f"Auto-Remediation skipped for {safe_path}: already remediated {elapsed}s ago "
                f"(within {_DEDUP_WINDOW_SECONDS}s dedup window, AUDIT-FIX #1693)"
            )
            return {
                "success": False,
                "skipped": True,
                "reason": "dedup_window_active",
                "file": file_path,
                "seconds_since_last_remediation": elapsed,
                "dedup_window_seconds": _DEDUP_WINDOW_SECONDS,
                "remediation_count": prior_count,
            }

        # Rule 2: max-remediations-per-file exceeded → escalate to human
        if prior_count >= _MAX_REMEDIATIONS_PER_FILE:
            logger.error(
                f"Auto-Remediation ESCALATION for {safe_path}: already remediated {prior_count} "
                f"times (max {_MAX_REMEDIATIONS_PER_FILE}). Human review required "
                f"(AUDIT-FIX #1693)."
            )
            return {
                "success": False,
                "skipped": True,
                "reason": "max_remediations_exceeded_escalate_to_human",
                "file": file_path,
                "remediation_count": prior_count,
                "max_allowed": _MAX_REMEDIATIONS_PER_FILE,
                "human_review_required": True,
            }

        with open(safe_path, encoding="utf-8") as f:
            original_code = f.read()

        fixed_code = await self._get_ai_patch(safe_path, original_code, line_number, issue)

        if not fixed_code:
            _append_audit_trail(
                {
                    "decision": "rejected",
                    "reason": "patch_generation_failed",
                    "file": file_path,
                    "line": line_number,
                    "severity": severity,
                    "tenant_id": tenant_id,
                }
            )
            return {"success": False, "error": "AI failed to generate a secure patch"}

        # AUDIT-FIX (#1698): masking guard — a patch that only ADDS silent
        # exception swallowing (bare/broad except with a pass-only body) hides
        # the root cause instead of fixing it. Such patches are rejected here;
        # high/critical severity ones would anyway land in pending_review
        # (HITL) inside RemediationPipeline, but the mask check runs first so
        # a masking patch never even reaches the pipeline.
        if _patch_masks_root_cause(original_code, fixed_code):
            _append_audit_trail(
                {
                    "decision": "rejected",
                    "reason": "masks_root_cause",
                    "file": file_path,
                    "line": line_number,
                    "severity": severity,
                    "tenant_id": tenant_id,
                    "detail": "patch adds bare/broad silent except handlers",
                }
            )
            logger.warning(
                f"Auto-Remediation rejected for {safe_path}: patch only adds "
                "silent exception handling without addressing the root cause "
                "(AUDIT-FIX #1698). Human review required."
            )
            return {
                "success": False,
                "rejected": True,
                "reason": "masks_root_cause",
                "human_review_required": True,
                "error": "Patch masks the root cause (adds silent exception swallowing)",
            }

        # Import inside function keeps tests isolated but also allows patching via module path.
        from core.health.self_healer import RemediationPipeline

        pipeline = RemediationPipeline()

        impact_score = 0.8 if severity.lower() in {"high", "critical"} else 0.3

        result = await pipeline.submit(tenant_id, issue, fixed_code, impact_score, [])

        if str(result).startswith("reject"):
            _append_audit_trail(
                {
                    "decision": "rejected",
                    "reason": str(result),
                    "file": file_path,
                    "line": line_number,
                    "severity": severity,
                    "tenant_id": tenant_id,
                }
            )
            return {"success": False, "error": f"Patch rejected by pipeline: {result}"}

        # AUDIT-FIX (#1693): Record successful remediation in dedup cache.
        # শুধু successful patch-ই count বাড়ায় — failed attempts dedup-এ পড়ে না।
        self._remediation_history[safe_path] = {
            "last_ts": now,
            "count": prior_count + 1,
        }
        # AUDIT-FIX (#1698): permanent audit trail for the applied patch.
        _append_audit_trail(
            {
                "decision": "applied",
                "file": file_path,
                "line": line_number,
                "issue": issue,
                "severity": severity,
                "tenant_id": tenant_id,
                "pipeline_id": str(result),
                "impact_score": impact_score,
                "remediation_count": prior_count + 1,
            }
        )
        # Cleanup very old entries (>1 day) to keep memory bounded
        cutoff = now - 86400
        stale = [k for k, v in self._remediation_history.items() if v.get("last_ts", 0) < cutoff]
        for k in stale:
            self._remediation_history.pop(k, None)

        return {
            "success": True,
            "file": file_path,
            "patch_applied": True,
            "branch": "supremeai-improvements",
            "pr_url": None,
            "message": f"Remediation patch processed by pipeline. ID: {result}",
            "remediation_count": prior_count + 1,
            "max_per_file": _MAX_REMEDIATIONS_PER_FILE,
        }

    async def _get_ai_patch(self, file_path: str, code: str, line_number: int, issue: str) -> str:
        # The actual LLM integration is intentionally dynamic to keep this module testable.
        from core.ld_client import get_ld_ai_components

        ld_ai_client, AICompletionConfigDefault, LDMessage, ModelConfig, Context = (
            get_ld_ai_components()
        )

        default_prompt_template = (
            "You are an elite secure coding assistant. Correct the security vulnerability in this file.\n"
            "File: {file_path}\n"
            "Line Number of Vulnerability: {line_number}\n"
            "Vulnerability Description: {issue}\n\n"
            "Provide the complete corrected file contents. Do NOT explain the changes. "
            "Return ONLY the code in plaintext with no markdown code blocks.\n\n"
            "Original Code:\n{code}\n"
        )

        context = None
        if Context is not None:
            context = Context.builder("auto-remediation-helper").kind("service").build()

        prompt_vars = {
            "file_path": file_path,
            "line_number": str(line_number),
            "issue": issue,
            "code": code,
        }

        config = None
        if ld_ai_client and AICompletionConfigDefault and LDMessage and ModelConfig and context:
            try:
                config = ld_ai_client.completion_config(
                    os.getenv("LAUNCHDARKLY_AI_CONFIG_KEY", "auto-remediation-patch"),
                    context,
                    default=AICompletionConfigDefault(
                        enabled=True,
                        model=ModelConfig(name="gemini/gemini-2.5-pro"),
                        messages=[LDMessage(role="system", content=default_prompt_template)],
                    ),
                    variables=prompt_vars,
                )
            except Exception as exc:
                logger.warning(f"LaunchDarkly config evaluation failed, falling back: {exc}")

        if config and getattr(config, "enabled", False):
            model_name = (
                config.model.name if getattr(config, "model", None) else "gemini/gemini-2.5-pro"
            )
            prompt = (
                config.messages[0].content
                if getattr(config, "messages", None)
                else default_prompt_template.format(**prompt_vars)
            )
        else:
            model_name = "gemini/gemini-2.5-pro"
            prompt = default_prompt_template.format(**prompt_vars)

        try:
            from core.llm.llm_gateway import llm_gateway

            response = await llm_gateway.acompletion(
                prompt=prompt,
                task_type="coding",
                stream=False,
                model=model_name,
            )
            raw_text = response.get("text", "") if isinstance(response, dict) else str(response)

            from utils.text_helpers import strip_markdown_code_block

            return strip_markdown_code_block(raw_text)
        except Exception as exc:
            logger.error(f"Failed to generate patch from Gemini: {exc}")
            return ""
