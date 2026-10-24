#!/usr/bin/env python3
"""
PR Helper — Phase 2: AI Fix Generator (issue #1034)
====================================================
Phase 1-এর `ci_failures.json` থেকে failures read করে, প্রতিটি failure-এর
জন্য failing source file-এর content সহ Gemini API-কে prompt পাঠায়, এবং
AI-generated fixed code ফেরত পায়। Gemini quota শেষ হলে OpenAI-তে fallback।

Real implementation:
  - Gemini API: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=KEY
    (urllib — `google.generativeai` package optional, install করা না থাকলেও চলবে)
  - OpenAI API: POST https://api.openai.com/v1/chat/completions (urllib)

Safety (issue #1034 Phase 4 Safety Guarantees):
  - Scope limit: শুধু PR diff-এ থাকা ফাইলই fix করে (changed_files list check)
  - Confidence threshold: confidence < 0.8 (default, LD-controlled) → skip + escalate
  - Max retries: max_attempts (default 2, LD-controlled) — এর বেশি attempt নয়
  - Syntax validation: AI ফেরত দেওয়া code Python `ast.parse()` দিয়ে validate
  - Audit trail: প্রতিটি attempt log করে (model, prompt, response, confidence)

Output (ai_fixes.json):
  {
    "pr_number": 1234,
    "head_sha": "abc123",
    "generated_at": "...",
    "attempts": [
      {
        "failure_id": "tests/test_x.py::test_y",
        "model_used": "gemini-2.5-flash",
        "file_path": "backend/tests/test_x.py",
        "prompt_tokens": 1234,
        "response_text": "...",
        "fixed_code": "...",
        "confidence": 0.85,
        "syntax_valid": true,
        "in_diff_scope": true,
        "applied": true,
        "error": null
      }
    ],
    "summary": {
      "total_attempts": 3,
      "applied": 2,
      "skipped_low_confidence": 1,
      "skipped_out_of_scope": 0,
      "syntax_invalid": 0,
      "errors": 0
    }
  }

Usage:
  python ai_fix_generator.py \\
    --failures ci_failures.json \\
    --repo /path/to/repo \\
    --output-json ai_fixes.json \\
    --max-attempts 2 \\
    --confidence-threshold 0.8

GitHub Actions outputs (GITHUB_OUTPUT):
  fixes_applied = N
  fixes_skipped = M
  fixes_failed = K
  any_applied = true|false
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# --- Constants --------------------------------------------------------------

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_API_BASE = "https://api.openai.com/v1"

# Model defaults (LD flags থেকে override করা যায়)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# Confidence threshold (LD flag: ai-auto-fix-confidence-threshold)
DEFAULT_CONFIDENCE_THRESHOLD = 0.8

# Max retries per PR (LD flag: ai-auto-fix-max-retries)
DEFAULT_MAX_ATTEMPTS = 2

# প্রতিটি source file থেকে সর্বোচ্চ কত বাইট পড়বে (AI prompt-এ পাঠাবে)
MAX_SOURCE_BYTES = 16000

# PR Helper শুধু এই path-গুলোর ফাইল modify করতে পারে (defense in depth)
ALLOWED_PATH_PREFIXES = (
    "backend/",
    "tests/",
    "src/",
    "scripts/",
)

# এই path-গুলো AI auto-fix দিয়ে touch করবে না (governance)
PROTECTED_PATH_PREFIXES = (
    "backend/core/",
    ".github/",
    "docs/security/",
    "security/policies/",
)


# --- Prompt template --------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert Python developer. Fix the CI failure with the MINIMAL "
    "possible change. Return ONLY the complete fixed file content, no markdown "
    "fences, no explanation, no diff format."
)

USER_PROMPT_TEMPLATE = """Fix the following CI failure:

File: {file_path}
Error: {error_message}
Test: {test_name}
Failure type: {failure_type}

Source code:
```python
{source_code}
```

Constraints:
- Return ONLY the complete corrected file content.
- Do NOT add or remove imports unless the failure is an ImportError.
- Do NOT change function signatures unless the test failure requires it.
- Do NOT add comments or explanations.
- The fix must compile (Python 3.11).
"""


# --- Markdown stripping -----------------------------------------------------

_CODE_FENCE_RE = re.compile(r"^```(?:python)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_markdown_code_block(text: str) -> str:
    """AI যদি ```python ... ``` block-এ wrap করে ফেরত দেয়, সেটি unwrap করে।"""
    if not text:
        return ""
    text = text.strip()
    m = _CODE_FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    # কখনো কখনো শুরুর ``` আছে কিন্তু শেষের নেই — সে ক্ষেত্রে শুধু প্রথম লাইন বাদ দেই
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) > 1:
            return "\n".join(lines[1:]).rstrip("`").strip()
    return text


# --- HTTP helpers -----------------------------------------------------------


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 60) -> tuple[int, dict]:
    """Generic JSON POST. Returns (status, parsed_body)."""
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", "User-Agent": "supremeai-pr-helper/1.0"}
    req_headers.update(headers)
    req = urllib.request.Request(url, data=body, method="POST", headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        # Real urllib passes a file-like fp; tests may pass bytes directly.
        # Handle both — prefer .read(), fallback to bytes inspection.
        raw = b""
        try:
            raw = exc.read()
        except (AttributeError, TypeError, OSError):
            fp = getattr(exc, "fp", None)
            if isinstance(fp, (bytes, bytearray)):
                raw = bytes(fp)
            else:
                raw = b""
        status = exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return status, {
            "error": "non-JSON response",
            "raw": raw[:500].decode("utf-8", errors="replace"),
        }


# --- Gemini API (urllib — no google.generativeai dependency required) -------


def _call_gemini(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """Gemini generateContent API call.

    Returns (response_text, error_message, prompt_tokens).
    error_message empty হলে success.
    """
    if not api_key:
        return "", "GEMINI_API_KEY not set", 0

    url = (
        f"{GEMINI_API_BASE}/models/{urllib.parse.quote(model)}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,  # deterministic-ish — fix হওয়া দরকার
            "topP": 0.95,
            "maxOutputTokens": 8192,
        },
    }
    status, body = _post_json(url, {}, payload, timeout=timeout)
    if status != 200:
        err_msg = (
            body.get("error", {}).get("message") if isinstance(body, dict) else ""
        ) or f"HTTP {status}"
        # Quota exhaustion signature — caller কে fallback করতে হবে
        if status == 429 or "quota" in err_msg.lower() or "rate limit" in err_msg.lower():
            return "", f"QUOTA_EXHAUSTED: {err_msg}", 0
        return "", f"Gemini API error: {err_msg}", 0

    candidates = body.get("candidates", []) if isinstance(body, dict) else []
    if not candidates:
        return "", "Gemini: empty candidates", 0
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    usage = body.get("usageMetadata", {}) if isinstance(body, dict) else {}
    prompt_tokens = usage.get("promptTokenCount", 0)
    return text, "", prompt_tokens


# --- OpenAI API (urllib — fallback) -----------------------------------------


def _call_openai(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """OpenAI Chat Completions call (fallback)."""
    if not api_key:
        return "", "OPENAI_API_KEY not set", 0

    url = f"{OPENAI_API_BASE}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }
    status, body = _post_json(url, headers, payload, timeout=timeout)
    if status != 200:
        err_msg = (
            body.get("error", {}).get("message") if isinstance(body, dict) else ""
        ) or f"HTTP {status}"
        return "", f"OpenAI API error: {err_msg}", 0

    choices = body.get("choices", []) if isinstance(body, dict) else []
    if not choices:
        return "", "OpenAI: empty choices", 0
    text = choices[0].get("message", {}).get("content", "")
    usage = body.get("usage", {}) if isinstance(body, dict) else {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    return text, "", prompt_tokens


# --- Mistral API (urllib — final fallback, if both above fail) --------------


def _call_mistral(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """Mistral chat completions call (tertiary fallback)."""
    if not api_key:
        return "", "MISTRAL_API_KEY not set", 0

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model or "mistral-small-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }
    status, body = _post_json(url, headers, payload, timeout=timeout)
    if status != 200:
        err_msg = (
            body.get("error", {}).get("message") if isinstance(body, dict) else ""
        ) or f"HTTP {status}"
        return "", f"Mistral API error: {err_msg}", 0

    choices = body.get("choices", []) if isinstance(body, dict) else []
    if not choices:
        return "", "Mistral: empty choices", 0
    text = choices[0].get("message", {}).get("content", "")
    usage = body.get("usage", {}) if isinstance(body, dict) else {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    return text, "", prompt_tokens


# --- Model routing ----------------------------------------------------------


def call_model(
    model_choice: str,
    gemini_key: str,
    openai_key: str,
    mistral_key: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 60,
) -> tuple[str, str, int, str]:
    """LD-routed model call with fallback chain.

    model_choice:
      - "gemini"      → Gemini only (no fallback)
      - "openai"      → OpenAI only
      - "mistral"     → Mistral only
      - "auto"        → Gemini → OpenAI → Mistral (default)
      - "auto-fast"   → Gemini-flash → OpenAI-mini → Mistral-small

    Returns (text, error, prompt_tokens, model_used).
    """
    gemini_model = DEFAULT_GEMINI_MODEL
    openai_model = DEFAULT_OPENAI_MODEL
    mistral_model = "mistral-small-latest"

    if model_choice == "gemini":
        text, err, tokens = _call_gemini(
            gemini_key, gemini_model, system_prompt, user_prompt, timeout
        )
        return text, err, tokens, gemini_model if not err else ""
    if model_choice == "openai":
        text, err, tokens = _call_openai(
            openai_key, openai_model, system_prompt, user_prompt, timeout
        )
        return text, err, tokens, openai_model if not err else ""
    if model_choice == "mistral":
        text, err, tokens = _call_mistral(
            mistral_key, mistral_model, system_prompt, user_prompt, timeout
        )
        return text, err, tokens, mistral_model if not err else ""

    # auto / auto-fast → fallback chain
    chain = [
        ("gemini", gemini_key, gemini_model),
        ("openai", openai_key, openai_model),
        ("mistral", mistral_key, mistral_model),
    ]
    for provider, key, model in chain:
        if not key:
            continue
        if provider == "gemini":
            text, err, tokens = _call_gemini(key, model, system_prompt, user_prompt, timeout)
        elif provider == "openai":
            text, err, tokens = _call_openai(key, model, system_prompt, user_prompt, timeout)
        else:
            text, err, tokens = _call_mistral(key, model, system_prompt, user_prompt, timeout)
        if not err:
            return text, "", tokens, model
        # Quota exhausted → next provider; other errors → also try next
        if "QUOTA_EXHAUSTED" not in err and not key:
            # যদি key না থাকে সেটা next-এ try করার ইঙ্গিত দেয়
            pass
    return "", "All models failed (Gemini + OpenAI + Mistral)", 0, ""


# --- Confidence estimation --------------------------------------------------


# AI response-এর গুণমান থেকে confidence derive করি (LLM-গুলো explicit confidence দেয় না)
# Heuristic:
#   - syntax valid → +0.4
#   - file_path unchanged (প্রথম line একই comment/docstring ধরে রাখে) → +0.2
#   - response length reasonable (>50 chars, <source*3) → +0.2
#   - no leftover markdown → +0.1
#   - import count same ± 2 → +0.1
def _estimate_confidence(
    original_code: str,
    fixed_code: str,
    file_path: str,
    syntax_valid: bool,
) -> float:
    confidence = 0.0
    if syntax_valid:
        confidence += 0.4
    # Response length check
    if len(fixed_code) > 50 and len(fixed_code) < len(original_code) * 3 + 1000:
        confidence += 0.2
    # No leftover markdown fences
    if "```" not in fixed_code:
        confidence += 0.1
    # Import count similar (± 2)
    try:
        orig_imports = sum(
            1 for ln in original_code.splitlines() if ln.strip().startswith(("import ", "from "))
        )
        fix_imports = sum(
            1 for ln in fixed_code.splitlines() if ln.strip().startswith(("import ", "from "))
        )
        if abs(orig_imports - fix_imports) <= 2:
            confidence += 0.1
    except Exception:
        pass
    # First non-empty line preserved (docstring/module header) → behavioral similarity
    orig_first = next((ln for ln in original_code.splitlines() if ln.strip()), "")
    fix_first = next((ln for ln in fixed_code.splitlines() if ln.strip()), "")
    if orig_first and fix_first and orig_first[:60] == fix_first[:60]:
        confidence += 0.2
    return round(min(confidence, 1.0), 2)


def _is_syntax_valid(code: str) -> bool:
    """Python AST parse দিয়ে syntax check করে।"""
    if not code or not code.strip():
        return False
    try:
        ast.parse(code)
        return True
    except (SyntaxError, IndentationError, ValueError):
        return False


# --- Scope safety -----------------------------------------------------------


def _normalize_path(path: str) -> str:
    """leading './' strip করে normalized path দেয়।
    বাংলা: `./backend/x.py` → `backend/x.py`, `backend/x.py` → `backend/x.py`.
    `.lstrip("./")` ব্যবহার করলে `.github/x` → `github/x` হয়ে যায় (char-set strip)
    তাই এখানে explicit prefix removal ব্যবহার করা হয়েছে।
    """
    if not path:
        return ""
    while path.startswith("./"):
        path = path[2:]
    return path


def _is_in_diff_scope(file_path: str, changed_files: list[str]) -> bool:
    """file_path কি PR diff-এ আছে কিনা — শুধু সেই ফাইলই AI fix করতে পারবে।"""
    if not file_path:
        return False
    # প্রথমে exact match
    if file_path in changed_files:
        return True
    # তারপর prefix match (যদি AI path একটু ভুল দেয়)
    norm = _normalize_path(file_path)
    for cf in changed_files:
        cf_norm = _normalize_path(cf)
        if cf_norm == norm or cf_norm.endswith("/" + norm) or norm.endswith("/" + cf_norm):
            return True
    return False


def _is_protected_path(file_path: str) -> bool:
    """AI auto-fix কখনো protected path-এ touch করবে না (governance)."""
    if not file_path:
        return True  # unknown path → protected
    norm = _normalize_path(file_path)
    return any(norm.startswith(p) for p in PROTECTED_PATH_PREFIXES)


def _is_allowed_path(file_path: str) -> bool:
    """file_path কি allowed prefix-এ আছে।"""
    if not file_path:
        return False
    norm = _normalize_path(file_path)
    return any(norm.startswith(p) for p in ALLOWED_PATH_PREFIXES)


# --- Core generation loop ---------------------------------------------------


def _read_source(repo: str, file_path: str) -> str:
    """repo root থেকে source file পড়ে।"""
    if not file_path:
        return ""
    norm = _normalize_path(file_path)
    full = Path(repo) / norm
    try:
        text = full.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return ""
    # AI-কে পাঠানোর আগে truncate (MAX_SOURCE_BYTES)
    if len(text) > MAX_SOURCE_BYTES:
        text = text[:MAX_SOURCE_BYTES] + "\n# ... [truncated for prompt]\n"
    return text


def _build_prompt(failure: dict, source_code: str) -> str:
    """Failure-থেকে user prompt তৈরি করে।"""
    return USER_PROMPT_TEMPLATE.format(
        file_path=failure.get("file_path", ""),
        error_message=(failure.get("message", "") or "")[:1000],
        test_name=failure.get("test_name", ""),
        failure_type=failure.get("type", "unknown"),
        source_code=source_code,
    )


def generate_fixes(
    failures_data: dict,
    repo: str,
    model_choice: str = "auto",
    gemini_key: str | None = None,
    openai_key: str | None = None,
    mistral_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    request_timeout: int = 60,
) -> dict:
    """সব failures-এর জন্য AI fix generate করে।

    max_attempts: total fix attempts allowed per PR (issue safety: 2 default).
    """
    gemini_key = gemini_key or os.getenv("GEMINI_API_KEY", "")
    openai_key = openai_key or os.getenv("OPENAI_API_KEY", "")
    mistral_key = mistral_key or os.getenv("MISTRAL_API_KEY", "")

    changed_files = failures_data.get("changed_files", [])
    attempts: list[dict] = []
    applied = 0
    skipped_low_conf = 0
    skipped_out_of_scope = 0
    syntax_invalid = 0
    errors = 0
    attempt_count = 0

    for job in failures_data.get("failed_jobs", []):
        for failure in job.get("failures", []):
            if attempt_count >= max_attempts:
                # Safety: max attempts reached — বাকিগুলো escalate করবে
                attempts.append(
                    {
                        "failure_id": failure.get("test_name") or failure.get("file_path", ""),
                        "model_used": "",
                        "file_path": failure.get("file_path", ""),
                        "prompt_tokens": 0,
                        "response_text": "",
                        "fixed_code": "",
                        "confidence": 0.0,
                        "syntax_valid": False,
                        "in_diff_scope": _is_in_diff_scope(
                            failure.get("file_path", ""), changed_files
                        ),
                        "applied": False,
                        "error": "MAX_ATTEMPTS_REACHED — escalated to human review",
                    }
                )
                continue

            file_path = failure.get("file_path", "")
            failure_id = failure.get("test_name") or file_path or "unknown"

            # Safety 1: scope check
            if not _is_in_diff_scope(file_path, changed_files):
                attempts.append(
                    {
                        "failure_id": failure_id,
                        "file_path": file_path,
                        "model_used": "",
                        "prompt_tokens": 0,
                        "response_text": "",
                        "fixed_code": "",
                        "confidence": 0.0,
                        "syntax_valid": False,
                        "in_diff_scope": False,
                        "applied": False,
                        "error": "OUT_OF_SCOPE — file not in PR diff",
                    }
                )
                skipped_out_of_scope += 1
                continue

            # Safety 2: protected path check
            if _is_protected_path(file_path) or not _is_allowed_path(file_path):
                attempts.append(
                    {
                        "failure_id": failure_id,
                        "file_path": file_path,
                        "model_used": "",
                        "prompt_tokens": 0,
                        "response_text": "",
                        "fixed_code": "",
                        "confidence": 0.0,
                        "syntax_valid": False,
                        "in_diff_scope": True,
                        "applied": False,
                        "error": "PROTECTED_PATH — AI auto-fix not permitted on this path",
                    }
                )
                skipped_out_of_scope += 1
                continue

            source_code = _read_source(repo, file_path)
            if not source_code:
                attempts.append(
                    {
                        "failure_id": failure_id,
                        "file_path": file_path,
                        "model_used": "",
                        "prompt_tokens": 0,
                        "response_text": "",
                        "fixed_code": "",
                        "confidence": 0.0,
                        "syntax_valid": False,
                        "in_diff_scope": True,
                        "applied": False,
                        "error": f"SOURCE_FILE_UNREADABLE — {file_path} not found in repo",
                    }
                )
                errors += 1
                continue

            user_prompt = _build_prompt(failure, source_code)
            text, err, tokens, model_used = call_model(
                model_choice,
                gemini_key,
                openai_key,
                mistral_key,
                SYSTEM_PROMPT,
                user_prompt,
                timeout=request_timeout,
            )
            attempt_count += 1

            if err:
                attempts.append(
                    {
                        "failure_id": failure_id,
                        "file_path": file_path,
                        "model_used": model_used or model_choice,
                        "prompt_tokens": tokens,
                        "response_text": "",
                        "fixed_code": "",
                        "confidence": 0.0,
                        "syntax_valid": False,
                        "in_diff_scope": True,
                        "applied": False,
                        "error": err,
                    }
                )
                errors += 1
                continue

            fixed_code = _strip_markdown_code_block(text)
            syntax_valid = _is_syntax_valid(fixed_code)
            confidence = _estimate_confidence(source_code, fixed_code, file_path, syntax_valid)

            attempt_record = {
                "failure_id": failure_id,
                "file_path": file_path,
                "model_used": model_used,
                "prompt_tokens": tokens,
                "response_text": text[:2000],  # audit trail (truncated)
                "fixed_code": fixed_code,
                "confidence": confidence,
                "syntax_valid": syntax_valid,
                "in_diff_scope": True,
                "applied": False,
                "error": None,
            }

            # Safety 3: syntax check
            if not syntax_valid:
                attempt_record["error"] = "SYNTAX_INVALID — AI output did not pass ast.parse()"
                syntax_invalid += 1
                attempts.append(attempt_record)
                continue

            # Safety 4: confidence threshold
            if confidence < confidence_threshold:
                attempt_record["error"] = (
                    f"LOW_CONFIDENCE — {confidence:.2f} < {confidence_threshold:.2f} threshold, escalated"
                )
                skipped_low_conf += 1
                attempts.append(attempt_record)
                continue

            attempt_record["applied"] = True
            applied += 1
            attempts.append(attempt_record)

            # Apply fix to working tree (so next phase can commit + push)
            try:
                target = Path(repo) / _normalize_path(file_path)
                target.write_text(fixed_code, encoding="utf-8")
            except OSError as write_err:
                attempt_record["applied"] = False
                attempt_record["error"] = f"WRITE_FAILED: {write_err}"
                applied -= 1
                errors += 1

    return {
        "pr_number": failures_data.get("pr_number"),
        "head_sha": failures_data.get("head_sha"),
        "generated_at": datetime.now(UTC).isoformat(),
        "model_choice": model_choice,
        "confidence_threshold": confidence_threshold,
        "max_attempts": max_attempts,
        "attempts": attempts,
        "summary": {
            "total_attempts": len(attempts),
            "applied": applied,
            "skipped_low_confidence": skipped_low_conf,
            "skipped_out_of_scope": skipped_out_of_scope,
            "syntax_invalid": syntax_invalid,
            "errors": errors,
        },
    }


# --- CLI --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper — AI Fix Generator (#1034)")
    parser.add_argument("--failures", required=True, help="ci_failures.json from Phase 1")
    parser.add_argument("--repo", default=".", help="Repo root (to read + write source files)")
    parser.add_argument(
        "--model",
        default=os.getenv("AI_AUTO_FIX_MODEL", "auto"),
        help="auto|gemini|openai|mistral (default: auto)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Max AI fix attempts per PR (default: {DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f"Min confidence to apply (default: {DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument("--timeout", type=int, default=60, help="Per-request timeout sec")
    parser.add_argument("--output-json", default="ai_fixes.json", help="Output JSON path")
    args = parser.parse_args()

    failures_data = json.loads(Path(args.failures).read_text(encoding="utf-8"))

    result = generate_fixes(
        failures_data,
        repo=args.repo,
        model_choice=args.model,
        max_attempts=args.max_attempts,
        confidence_threshold=args.confidence_threshold,
        request_timeout=args.timeout,
    )

    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    s = result["summary"]
    print("AI Fix Generation complete:")
    print(f"  Total attempts: {s['total_attempts']}")
    print(f"  Applied:        {s['applied']}")
    print(f"  Skipped (low confidence): {s['skipped_low_confidence']}")
    print(f"  Skipped (out of scope):   {s['skipped_out_of_scope']}")
    print(f"  Syntax invalid: {s['syntax_invalid']}")
    print(f"  Errors:         {s['errors']}")
    for a in result["attempts"]:
        status = "APPLIED" if a["applied"] else "SKIP"
        print(
            f"  [{status}] {a['failure_id'][:60]}  conf={a['confidence']:.2f}  model={a['model_used']}"
        )

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"fixes_applied={s['applied']}\n")
            f.write(f"fixes_skipped={s['skipped_low_confidence'] + s['skipped_out_of_scope']}\n")
            f.write(f"fixes_failed={s['errors'] + s['syntax_invalid']}\n")
            f.write(f"any_applied={str(s['applied'] > 0).lower()}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
