# backend/sandbox/docker_sandbox.py
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from core.logging_config import logger

# AUDIT-FIX (#1696 HIGH): আগে শুধু `".." in bind_source` স্ট্রিং চেক ছিল —
# `/etc/./shadow` বা symlink-ভায়া `/tmp/innocent → /etc` দিয়ে bypass হতো।
# এখন Path.resolve() দিয়ে symlink resolution করে whitelist-এ validate
# করা হয়। Pattern: microvm_sandbox._validate_sandbox_root থেকে নেওয়া।
# Whitelist env var দিয়ে extend করা যায় — ডিফল্ট নিরাপদ।
_DEFAULT_BIND_WHITELIST: tuple[str, ...] = (
    "/tmp/sandboxes",
    "/var/tmp/sandboxes",
    "/run/sandboxes",
)


def _resolve_bind_whitelist() -> frozenset[str]:
    """Build the active bind-mount whitelist at call time.

    Combines the default safe set with env-supplied extras (comma-separated).
    All paths are resolved via Path.resolve() so symlink-supplied env values
    can't smuggle in /etc paths.
    """
    extras_raw = os.environ.get("DOCKER_SANDBOX_BIND_WHITELIST", "")
    paths: list[str] = list(_DEFAULT_BIND_WHITELIST)
    for entry in extras_raw.split(","):
        entry = entry.strip()
        if entry:
            paths.append(entry)
    resolved: set[str] = set()
    for p in paths:
        try:
            resolved.add(str(Path(p).resolve()))
        except (OSError, ValueError):
            # Path may not exist yet on this worker; keep literal form so
            # future-create paths still match. Path.resolve() on a
            # non-existent path still normalizes the string in 3.6+.
            resolved.add(str(Path(p).absolute()))
    return frozenset(resolved)


def _is_path_in_whitelist(path_str: str, whitelist: frozenset[str]) -> bool:
    """Return True iff path_str resolves to a path inside the whitelist.

    Uses Path.resolve() which follows symlinks — so a symlink pointing
    outside the whitelist (e.g. /tmp/innocent → /etc) is resolved to its
    real target (/etc) and then rejected.
    """
    if not path_str:
        return False
    try:
        resolved = str(Path(path_str).resolve())
    except (OSError, ValueError):
        return False
    # Exact match OR is a subdirectory of an allowed root
    for allowed in whitelist:
        if resolved == allowed or resolved.startswith(allowed + os.sep):
            return True
    return False


class DockerSandbox:
    def __init__(self, image_name: str = "python:3.11-slim"):
        self.image_name = image_name
        self.memory_limit = "256m"
        self.cpu_limit = "0.5"
        self.timeout_seconds = 10

    def _sanitize_module_name(self, entry_file: str) -> str:
        """Sanitize entry file name - only allow alphanumeric and underscore to prevent injection."""
        # Remove .py extension and sanitize
        safe_name = entry_file.replace(".py", "").replace(".PY", "").replace(".Py", "")
        # Only allow alphanumeric and underscore characters
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "", safe_name)
        if not safe_name:
            raise ValueError("Invalid entry file name after sanitization")
        return safe_name

    def run_quarantine_test(
        self, staging_path: Path, entry_file: str, test_payload: str
    ) -> dict[str, Any]:
        """
        Default-deny network এবং Read-only মাউন্টে একটি পাইথন ফাইল স্যান্ডবক্সে রান করায়।
        """
        if not staging_path.exists():
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Staging path does not exist.",
            }

        # স্যান্ডবক্সের ভেতর এক্সিকিউট করার জন্য একটি সেফ রানিং স্ক্রিপ্ট ইনজেক্ট করা হচ্ছে
        # এটি নিশ্চিত করে যে কোডটি রান করার পর আউটপুটটি জেসন ফরম্যাটে ট্র্যাপড হবে
        target_file_path = staging_path / entry_file
        if not target_file_path.exists():
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Entry file {entry_file} not found.",
            }

        # নিরাপত্তা: entry_file নাম স্যানিটাইজ করা হচ্ছে (শুধুমাত্র alphanumeric ও underscore)
        safe_module_name = self._sanitize_module_name(entry_file)

        # Subprocess এর মাধ্যমে সরাসরি ডকার সিএলআই এনফোর্সমেন্ট
        # বাংলা মন্তব্য: পাইথন ইনজেকশন এড়াতে payload-টি সরাসরি কমান্ড স্ট্রিং-এ কনক্যাট না করে এনভায়রনমেন্ট ভ্যারিয়েবল হিসেবে পাস করা হচ্ছে।
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",  # 🔒 নো নেটওয়ার্ক (Default-deny)
            "--memory",
            self.memory_limit,  # 📉 মেমরি ক্যাপ
            "--cpus",
            self.cpu_limit,  # 📊 সিপিইউ ক্যাপ
            "-e",
            f"SANDBOX_PAYLOAD={test_payload}",
            "-v",
            f"{staging_path.resolve()}:/workspace:ro",  # 📁 রিড-ওনলি মাউন্ট
            "-w",
            "/workspace",
            self.image_name,
            "python",
            "-c",
            f"import os, sys, json, ast; import {safe_module_name} as tool; "
            f"payload = ast.literal_eval(os.environ.get('SANDBOX_PAYLOAD', '{{}}')); "
            f"print(json.dumps(tool.execute_tool(payload)))",
        ]

        try:
            # বাংলা মন্তব্য: UP022 ফিক্স — capture_output=True ব্যবহার করা হয়েছে
            # stdout=PIPE + stderr=PIPE এর চেয়ে আধুনিক ও Pythonic পদ্ধতি
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,  # Standard timeout exit code
                "stdout": "",
                "stderr": f"🚨 Security Sandbox Timeout: Execution exceeded {self.timeout_seconds}s limit.",
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Docker execution engine failure: {e!s}",
            }

    def run_safe_container(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        হোস্টের আইসোলেটেড ফাইলকে কন্টেইনারের ভেতর Read-Only মাউন্ট করে
        নিরাপদে পাইথন স্ক্রিপ্ট এক্সিকিউট করে এবং আউটপুট রিটার্ন করে।
        """
        script = payload.get("script", "")
        bind_source = payload.get("bind_mount_source", "")
        bind_target = payload.get("bind_mount_target", "")

        if not script:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "No script provided for sandbox execution.",
            }

        # 🛡️ ডকার সিকিউরিটি এবং আইসোলেশন ফ্ল্যাগস এনফোর্সমেন্ট
        # AUDIT-FIX (#1696 HIGH): আগে শুধু `".." in bind_source` চেক ছিল —
        # `/etc/./shadow`, symlink `/tmp/innocent → /etc` দিয়ে bypass হতো।
        # এখন Path.resolve() দিয়ে symlink resolve করে whitelist validate হয়।
        bind_whitelist = _resolve_bind_whitelist()
        if not _is_path_in_whitelist(bind_source, bind_whitelist):
            logger.critical(f"Bind source path rejected (not in whitelist): {bind_source!r}")
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Invalid bind mount path detected: source not in allowed sandbox whitelist.",
            }
        if not _is_path_in_whitelist(bind_target, bind_whitelist):
            # bind_target is the in-container path, but it still must not
            # contain traversal patterns. We apply a weaker check here —
            # the more important check is bind_source (host path).
            if (
                ".." in bind_target
                or bind_target.startswith("/etc")
                or bind_target.startswith("/proc")
            ):
                logger.critical(f"Bind target path rejected (suspicious): {bind_target!r}")
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Invalid bind mount target path detected.",
                }

        # 🛡️ AUDIT-FIX (#1701 MEDIUM): AST pre-execution validation — parity
        # with core/microvm_sandbox.py::_ast_validate_code. The raw script used
        # to go straight into `python3 -c` inside the container with no static
        # inspection. বাংলা: কন্টেইনারে চলার আগেই AST দিয়ে কোড যাচাই হয় —
        # getattr/hasattr বাইপাস ও unsafe কনস্ট্রাক্ট এখানেই ব্লক হয়।
        from core.security.scanning.ast_scanner import validate_code_for_sandbox

        is_safe, reason = validate_code_for_sandbox(script, strict_mode=True)
        if not is_safe:
            logger.critical(f"[DockerSandbox] AST validation blocked unsafe script: {reason}")
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"AST sandbox validation failed: {reason}",
            }

        docker_command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "-v",
            f"{bind_source}:{bind_target}:ro",
            self.image_name,
            "python3",
            "-c",
            script,
        ]

        try:
            logger.info(f"⚡ Spawning Docker Sandbox for source volume: {bind_source}")

            result = subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Sandbox execution timed out after {self.timeout_seconds}s limit.")
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Execution barrier breached: Timeout of {self.timeout_seconds}s exceeded.",
            }
        except Exception as e:
            logger.error(f"Critical exception inside Docker execution wrapper: {e!s}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Sandbox Runtime Anomaly: {e!s}",
            }
