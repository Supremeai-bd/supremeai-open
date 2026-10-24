"""TokenJuice — High-efficiency Context & Tool Output Compression Engine.

Inspired by OpenHuman's TokenJuice architecture, this module deterministically
compresses bulky tool outputs (Playwright DOM snapshots, Terminal/CLI logs,
JSON API payloads, Git diffs, Tracebacks) by 60-80% before passing them to LLMs,
dramatically saving tokens and inference latency.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class CompressionResult:
    """Result of a TokenJuice compression pass."""

    original_text: str
    compressed_text: str
    original_chars: int
    compressed_chars: int
    estimated_original_tokens: int
    estimated_compressed_tokens: int
    compression_ratio: float  # e.g., 0.72 means 72% reduction
    content_type: str


class TokenJuice:
    """Deterministic token compressor for agent tool outputs and web context."""

    # ANSI escape regex
    ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    # Progress bars / spinners regex
    PROGRESS_BAR_RE = re.compile(
        r"(\r?\[[=\-#\s>]+\]|\r?\d+%\s*\|\s*[█▉▊▋▌▍▎▏\s]+\||\r?\s*\d+/\d+\s*\[[0-9:\.\s<]+,\s*[0-9\.\w/]+\])"
    )

    def __init__(self, char_per_token_estimate: float = 3.8):
        self.char_per_token_estimate = char_per_token_estimate

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count based on character length heuristics."""
        if not text:
            return 0
        return max(1, int(len(text) / self.char_per_token_estimate))

    def compress(self, content: str, content_type: str | None = None) -> CompressionResult:
        """Auto-detect content type and compress accordingly."""
        if not content or not content.strip():
            return CompressionResult(
                original_text=content,
                compressed_text="",
                original_chars=len(content),
                compressed_chars=0,
                estimated_original_tokens=0,
                estimated_compressed_tokens=0,
                compression_ratio=0.0,
                content_type=content_type or "empty",
            )

        detected_type = content_type or self.detect_content_type(content)

        if detected_type == "html" or detected_type == "dom":
            compressed = self.compress_dom(content)
        elif detected_type == "json":
            compressed = self.compress_json(content)
        elif detected_type == "log" or detected_type == "terminal":
            compressed = self.compress_terminal_logs(content)
        elif detected_type == "git_diff":
            compressed = self.compress_git_diff(content)
        else:
            compressed = self.compress_generic_text(content)

        orig_len = len(content)
        comp_len = len(compressed)
        orig_tokens = self.estimate_tokens(content)
        comp_tokens = self.estimate_tokens(compressed)
        ratio = (orig_len - comp_len) / orig_len if orig_len > 0 else 0.0

        return CompressionResult(
            original_text=content,
            compressed_text=compressed,
            original_chars=orig_len,
            compressed_chars=comp_len,
            estimated_original_tokens=orig_tokens,
            estimated_compressed_tokens=comp_tokens,
            compression_ratio=round(ratio, 4),
            content_type=detected_type,
        )

    def detect_content_type(self, text: str) -> str:
        """Detect whether text is HTML, JSON, Git Diff, Terminal Log, or plain text."""
        stripped = text.strip()
        if stripped.startswith("<") and (
            "</html>" in text.lower() or "</div>" in text.lower() or "<body" in text.lower()
        ):
            return "html"
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                json.loads(stripped)
                return "json"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")
        if stripped.startswith("diff --git") or "--- a/" in stripped or "+++ b/" in stripped:
            return "git_diff"
        if (
            "\x1b[" in text
            or "Traceback (most recent call last):" in text
            or "npm ERR!" in text
            or "ERROR:" in text
            or "[INFO]" in text
        ):
            return "terminal"
        return "generic"

    def compress_dom(self, html: str) -> str:
        """Compress HTML / Playwright DOM snapshots while preserving semantic interactive elements."""
        # 1. Remove comments
        cleaned = re.sub(r"<!--[\s\S]*?-->", "", html)

        # 2. Strip noise tags: script, style, svg, noscript, link, meta, path
        cleaned = re.sub(
            r"<(script|style|noscript|svg|meta|link)[^>]*>[\s\S]*?<\/\1>",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"<(svg|path|circle|rect|polygon)[^>]*\/>", "", cleaned, flags=re.IGNORECASE
        )

        # 3. Strip data URIs and inline base64 images
        cleaned = re.sub(
            r"data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+", "[img-data-omitted]", cleaned
        )

        # 4. Remove heavy presentation attributes (e.g., style="...", onclick="...", etc.) but keep id, role, aria, testid, href, class
        def clean_attributes(match: re.Match) -> str:
            tag_name = match.group(1)
            attrs = match.group(2)
            if not attrs:
                return f"<{tag_name}>"

            # Keep meaningful attributes
            kept_attrs = []
            for attr_match in re.finditer(r'([a-zA-Z0-9_\-:]+)(?:=(["\'])(.*?)\2)?', attrs):
                name = attr_match.group(1).lower()
                val = attr_match.group(3) if attr_match.group(3) is not None else ""

                # Relevant agent attributes
                if (
                    name
                    in (
                        "id",
                        "name",
                        "role",
                        "type",
                        "href",
                        "src",
                        "placeholder",
                        "title",
                        "value",
                    )
                    or name.startswith("aria-")
                    or name.startswith("data-test")
                ):
                    val_clean = val[:100]  # truncate overly long attribute strings
                    kept_attrs.append(f'{name}="{val_clean}"')
                elif name == "class":
                    # Keep important class keywords (btn, nav, modal, error, input, form, card)
                    classes = val.split()
                    important = [
                        c
                        for c in classes
                        if any(
                            k in c.lower()
                            for k in [
                                "btn",
                                "nav",
                                "modal",
                                "error",
                                "alert",
                                "form",
                                "input",
                                "item",
                                "header",
                                "footer",
                                "card",
                                "active",
                                "hidden",
                            ]
                        )
                    ]
                    if important:
                        kept_attrs.append(f'class="{" ".join(important[:4])}"')

            if kept_attrs:
                return f"<{tag_name} {' '.join(kept_attrs)}>"
            return f"<{tag_name}>"

        cleaned = re.sub(r"<([a-zA-Z0-9]+)\s+([^>]+)>", clean_attributes, cleaned)

        # 5. Remove empty container tags repeatedly
        for _ in range(2):
            cleaned = re.sub(r"<(div|span|section|p|li)\s*><\/\1>", "", cleaned)

        # 6. Normalize whitespace
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)

        return cleaned.strip()

    def compress_json(self, raw_json: str, max_array_items: int = 5) -> str:
        """Compress JSON payloads by pruning nulls/empty values and sampling large arrays."""
        try:
            data = json.loads(raw_json)
        except Exception:
            return self.compress_generic_text(raw_json)

        def prune(obj: Any) -> Any:
            if isinstance(obj, dict):
                cleaned = {}
                for k, v in obj.items():
                    # skip useless metadata keys if bulky
                    if k in ("__v", "$schema", "etag", "headers") and isinstance(
                        v, str | dict | list
                    ):
                        continue
                    pruned_v = prune(v)
                    if (
                        pruned_v is not None
                        and pruned_v != ""
                        and pruned_v != []
                        and pruned_v != {}
                    ):
                        cleaned[k] = pruned_v
                return cleaned
            elif isinstance(obj, list):
                if not obj:
                    return None
                pruned_list = [prune(item) for item in obj if prune(item) is not None]
                if len(pruned_list) > max_array_items:
                    sampled = pruned_list[:max_array_items]
                    sampled.append(
                        f"... [{len(pruned_list) - max_array_items} items omitted by TokenJuice]"
                    )
                    return sampled
                return pruned_list
            elif isinstance(obj, str):
                s = obj.strip()
                if len(s) > 400:
                    return s[:380] + "... [truncated]"
                return s
            return obj

        pruned_data = prune(data)
        return json.dumps(pruned_data, separators=(",", ":"), ensure_ascii=False)

    def compress_terminal_logs(self, logs: str, max_tail_lines: int = 50) -> str:
        """Compress terminal output, progress bars, ANSI codes, and duplicate log lines."""
        # 1. Strip ANSI codes
        cleaned = self.ANSI_ESCAPE_RE.sub("", logs)

        # 2. Strip progress bars
        cleaned = self.PROGRESS_BAR_RE.sub("", cleaned)

        lines = cleaned.splitlines()
        filtered_lines = []
        last_line = None
        repeat_count = 0

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Deduplicate identical consecutive lines
            if trimmed == last_line:
                repeat_count += 1
                continue
            else:
                if repeat_count > 0:
                    filtered_lines.append(f"... [repeated {repeat_count} times]")
                    repeat_count = 0
                last_line = trimmed

                # Check for critical keywords
                is_critical = any(
                    k in trimmed.lower()
                    for k in [
                        "error",
                        "fail",
                        "exception",
                        "traceback",
                        "warning",
                        "fatal",
                        "passed",
                        "done",
                        "status",
                    ]
                )
                if (
                    is_critical
                    or len(filtered_lines) < 20
                    or len(lines) - len(filtered_lines) <= max_tail_lines
                ):
                    filtered_lines.append(trimmed)

        if repeat_count > 0:
            filtered_lines.append(f"... [repeated {repeat_count} times]")

        # If still too large, sample head and tail
        if len(filtered_lines) > 80:
            head = filtered_lines[:25]
            tail = filtered_lines[-40:]
            omitted = len(filtered_lines) - 65
            return "\n".join(
                [
                    *head,
                    f"\n--- [TokenJuice: {omitted} intermediate log lines omitted] ---\n",
                    *tail,
                ]
            )

        return "\n".join(filtered_lines)

    def compress_git_diff(self, diff_text: str) -> str:
        """Compress Git diffs by collapsing large vendor/lockfile changes while preserving source changes."""
        lines = diff_text.splitlines()
        result = []
        skipping_binary_or_lock = False
        skipped_count = 0

        for line in lines:
            if line.startswith("diff --git"):
                if skipping_binary_or_lock and skipped_count > 0:
                    result.append(f"... [{skipped_count} lines of lockfile/asset diff omitted]")
                    skipped_count = 0

                # Check if lockfile or asset
                if any(
                    lock in line
                    for lock in [
                        "pnpm-lock.yaml",
                        "package-lock.json",
                        "poetry.lock",
                        "yarn.lock",
                        ".png",
                        ".svg",
                        ".jpg",
                        ".min.js",
                    ]
                ):
                    skipping_binary_or_lock = True
                    result.append(line + " [COMPRESSED FILE SUMMARY]")
                    continue
                else:
                    skipping_binary_or_lock = False

            if skipping_binary_or_lock:
                skipped_count += 1
                continue

            result.append(line)

        if skipping_binary_or_lock and skipped_count > 0:
            result.append(f"... [{skipped_count} lines of lockfile/asset diff omitted]")

        return "\n".join(result)

    def compress_generic_text(self, text: str) -> str:
        """Generic whitespace and deduplication compression."""
        cleaned = re.sub(r"[ \t]+", " ", text)
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
        return cleaned.strip()
