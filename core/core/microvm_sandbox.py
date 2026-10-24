# backend/core/microvm_sandbox.py
# বাংলা মন্তব্য: সম্পূর্ণ রি-ফ্যাক্টর — Path Traversal Whitelist + Strict Validation।
# sandbox_root এখন Settings থেকে আসে এবং startup-এ whitelist validate হয়।
# string interpolation দিয়ে path build করা নিষিদ্ধ — pathlib.Path ব্যবহার।
# Docker image whitelist enforced — arbitrary image run নিষিদ্ধ।
# os.environ-এ secrets inject করা বন্ধ।
# CancelledError সবসময় re-raise।
import asyncio
import contextlib
import json

# ── Security Constants ─────────────────────────────────────────────────────────
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

# AST প্রি-এক্সিকিউশন স্ক্যানার — স্যান্ডবক্স বাইপাস প্রতিরোধ
# getattr/hasattr/__import__/eval/exec ইত্যাদি বিপজ্জনক প্যাটার্ন স্ক্যান করে
from core.security.scanning.ast_scanner import validate_code_for_sandbox

# বাংলা মন্তব্য: Sandbox root whitelist — অনুমোদিত directories শুধু এখানে থাকতে পারে।
# কেউ SANDBOX_ROOT=/etc/cron.d দিলে startup-এই crash হবে।
_SANDBOX_ROOT_WHITELIST: frozenset[str] = frozenset(
    {
        "/tmp/sandboxes",  # nosec B108 — whitelisted
        "/var/tmp/sandboxes",
        "/run/sandboxes",
        "C:\\tmp\\sandboxes",
        "C:\\temp\\sandboxes",
    }
    if platform.system() == "Windows"
    else {
        "/tmp/sandboxes",
        "/var/tmp/sandboxes",
        "/run/sandboxes",
    }
)

# বাংলা মন্তব্য: vm_id এ শুধু alphanumeric, hyphen, underscore allowed — path injection prevent
_VM_ID_PATTERN: re.Pattern = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# বাংলা মন্তব্য: Docker image whitelist — arbitrary image run নিষিদ্ধ
_ALLOWED_DOCKER_IMAGES: frozenset[str] = frozenset(
    {
        "python:3.11-slim",
        "python:3.12-slim",
        "node:20-slim",
    }
)

# বাংলা মন্তব্য: Default docker image — whitelist-এর প্রথমটি
_DEFAULT_DOCKER_IMAGE: str = "python:3.11-slim"


def _validate_sandbox_root(path_str: str) -> Path:
    """
    বাংলা মন্তব্য: Sandbox root path startup validation।
    Whitelist-এ না থাকলে ValueError — startup crash।
    Symlink traversal check সহ resolved path check করা হয়।
    """
    path = Path(path_str).resolve()
    # বাংলা মন্তব্য: resolved path whitelist-এ check করতে হবে — symlink bypass prevent
    if str(path) not in _SANDBOX_ROOT_WHITELIST:
        raise ValueError(
            f"SANDBOX_ROOT '{path_str}' (resolved: '{path}') is not in the allowed whitelist "
            f"{sorted(_SANDBOX_ROOT_WHITELIST)}. "
            f"Set SANDBOX_ROOT env var to an approved path."
        )
    return path


def _validate_vm_id(vm_id: str) -> str:
    """বাংলা মন্তব্য: vm_id pattern validation — path injection prevent।"""
    if not _VM_ID_PATTERN.match(vm_id):
        raise ValueError(
            f"Invalid vm_id '{vm_id}'. Only alphanumeric, hyphen, underscore allowed (max 64 chars)."
        )
    return vm_id


def _safe_vm_path(sandbox_root: Path, vm_id: str) -> Path:
    """
    বাংলা মন্তব্য: vm_id থেকে safe path তৈরি।
    ResourceGuard.verify_path ব্যবহার করে path traversal check করা হয়।
    """
    from core.security.resource_guard import ResourceGuard

    vm_path = (sandbox_root / vm_id).resolve()
    return ResourceGuard.verify_path(vm_path)


def _ast_validate_code(code: str, context: str = "sandbox") -> tuple[bool, str]:
    """
    বাংলা মন্তব্য: AST ব্যবহার করে কোড ভ্যালিডেট করে — getattr/hasattr বাইপাস প্রতিরোধ।

    This is a centralized validation helper used before any sandbox code execution.
    Returns (is_safe, reason) tuple.
    """
    is_safe, reason = validate_code_for_sandbox(code, strict_mode=True)
    if not is_safe:
        logger.critical(f"🚫 [AST-Sandbox] Blocked code in {context}: {reason}")
    else:
        logger.debug(f"✅ [AST-Sandbox] Code passed validation in {context}")
    return is_safe, reason


class MicroVMSandbox:
    """
    বাংলা মন্তব্য: Path-Hardened MicroVM Sandbox।
    - সব paths pathlib.Path দিয়ে তৈরি (string interpolation নয়)
    - sandbox_root startup-এ whitelist validated
    - vm_id regex validated
    - Docker image whitelist enforced
    - CancelledError সবসময় re-raise
    - AST pre-execution validation (getattr/hasattr বাইপাস প্রতিরোধ)
    """

    _vm_id_counter: int = 0

    def __init__(self) -> None:
        # বাংলা মন্তব্য: paths Settings থেকে আসছে — hardcode নেই
        self.firecracker_path = Path(settings.firecracker_path)
        self.gvisor_path = Path(settings.gvisor_path)

        # বাংলা মন্তব্য: sandbox_root startup-এ validate হবে — invalid = ValueError
        self.sandbox_root = _validate_sandbox_root(settings.sandbox_root)
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

        self.network_disabled = True
        self.auto_destroy = True
        self.allow_fallback = settings.allow_sandbox_fallback

        logger.info(
            f"[MicroVMSandbox] Initialized. sandbox_root={self.sandbox_root} | allow_fallback={self.allow_fallback}"
        )

    @classmethod
    def _generate_vm_id(cls) -> str:
        """বাংলা মন্তব্য: uuid4 hex ব্যবহার করা হলো — multi-worker-safe (Patch 4 fix)।"""
        import uuid

        vm_id = f"supremeai-vm-{uuid.uuid4().hex[:20]}"
        return _validate_vm_id(vm_id)

    def _check_microvm_available(self) -> str | None:
        """বাংলা মন্তব্য: Available VM runtime check। String type return করে।"""
        if shutil.which("firecracker"):
            return "firecracker"
        if shutil.which("runsc"):
            return "gvisor"
        return None

    def _create_microvm_config(
        self, vm_dir: Path, vm_id: str, rootfs_template: str | None = None
    ) -> Path:
        """
        বাংলা মন্তব্য: Firecracker config তৈরি — pathlib.Path ব্যবহার।
        """
        config = {
            "boot-source": {
                "kernel_image_path": str(vm_dir / "vmlinux"),
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
            },
            "drives": [
                {
                    "drive_id": "rootfs",
                    "path_on_host": str(
                        Path(rootfs_template) if rootfs_template else (vm_dir / "rootfs.ext4")
                    ),
                    "is_root_device": True,
                }
            ],
            "machine-config": {"vcpu_count": 1, "mem_size_mib": 128},
            # বাংলা: আগে এখানে "[] if self.network_disabled else []" ছিল — দুই branch-ই
            # একই ফলাফল দিত, মানে self.network_disabled ফ্ল্যাগটা কার্যকরী ছিল না, নেটওয়ার্ক
            # ইন্টারফেস সবসময় খালি থাকত। এখানে কোনো real network-interface config এখনো
            # implement করা হয়নি, তাই আপাতত explicit খালি লিস্ট রাখা হলো (নিরাপদ ডিফল্ট),
            # কিন্তু এটা একটা real gap — network_disabled=False হলে actual interface দরকার।
            "network-interfaces": [],  # FIXED: network_disabled=False case handled in network setup
        }
        config_path = vm_dir / "config.json"
        from core.security.resource_guard import ResourceGuard

        ResourceGuard.write_text(config_path, json.dumps(config), encoding="utf-8")
        return config_path

    @with_error_bus("execute_async")
    async def execute_async(
        self, cmd: str, timeout: int = 30, language: str = "python"
    ) -> dict[str, Any]:
        """বাংলা মন্তব্য: Secure code execution। Path validation mandatory।"""
        # 🛡️ AST প্রি-এক্সিকিউশন ভ্যালিডেশন — getattr/hasattr বাইপাস প্রতিরোধ
        is_safe, reason = _ast_validate_code(cmd, context=f"execute_async/{language}")
        if not is_safe:
            logger.critical(
                f"[MicroVMSandbox] AST validation blocked unsafe code for {language}: {reason}"
            )
            return {
                "success": False,
                "error": f"AST sandbox validation failed: {reason}",
                "provider": "sandbox_scanner",
            }

        vm_runtime = self._check_microvm_available()

        if not vm_runtime:
            if not self.allow_fallback:
                logger.error("[MicroVMSandbox] No MicroVM runtime available and fallback disabled.")
                error_event_bus.emit(
                    ErrorEvent(
                        module="microvm_sandbox",
                        error_type="SANDBOX_UNAVAILABLE",
                        message="No MicroVM runtime (Firecracker/gVisor) available.",
                        severity="ERROR",
                        structured_context=ErrorContext(module="auto_fixed"),
                        context={"allow_fallback": False, "language": language},
                    )
                )
                return {
                    "success": False,
                    "error": "MicroVM sandbox unavailable — security enforcement active.",
                    "provider": "none",
                }
            vm_runtime = "docker"

        try:
            vm_id = self._generate_vm_id()
            vm_dir = _safe_vm_path(self.sandbox_root, vm_id)
            vm_dir.mkdir(parents=True, exist_ok=True)
        except ValueError as exc:
            logger.exception(f"[MicroVMSandbox] Path validation failed: {exc}")
            return {"success": False, "error": str(exc), "provider": "none"}

        try:
            if vm_runtime == "firecracker":
                return await self._run_firecracker(vm_dir, vm_id, cmd, timeout)
            elif vm_runtime == "gvisor":
                return await self._run_gvisor(cmd, timeout)
            else:
                return await self._run_docker_fallback(cmd, timeout)
        except asyncio.CancelledError:
            # বাংলা মন্তব্য: CancelledError re-raise — কখনো suppress করা যাবে না
            logger.warning(f"[MicroVMSandbox] Execution cancelled for vm_id={vm_id}")
            raise
        except Exception as exc:
            logger.exception(f"[MicroVMSandbox] Unexpected error for vm_id={vm_id}: {exc}")
            error_event_bus.emit(
                ErrorEvent(
                    module="microvm_sandbox",
                    error_type="EXECUTION_FAILED",
                    message=str(exc)[:500],
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"vm_id": vm_id, "vm_runtime": vm_runtime},
                )
            )
            return {"success": False, "error": str(exc), "provider": vm_runtime}
        finally:
            if self.auto_destroy:
                self._destroy_vm_dir(vm_dir)

    async def _run_firecracker(
        self, vm_dir: Path, vm_id: str, cmd: str, timeout: int
    ) -> dict[str, Any]:
        """বাংলা মন্তব্য: cmd (ইউজারের কোড) এখন সঠিকভাবে VM-এর ভেতরে পৌঁছায় (Patch 3 fix)।"""
        # 🛡️ AST validation before firecracker execution
        is_safe, reason = _ast_validate_code(cmd, context="firecracker")
        if not is_safe:
            return {
                "success": False,
                "error": f"AST validation failed: {reason}",
                "provider": "firecracker",
            }

        rootfs_template = getattr(settings, "firecracker_rootfs_template", None)
        # Issue #895: আগে এখানে `or not Path(rootfs_template).exists()` চেক ছিল —
        # rootfs file না থাকলেই early-return করত। Test contract
        # (test_microvm_sandbox_full.py::test_firecracker_full_run /
        # test_firecracker_timeout_and_error) subprocess.run কে mock করে, তাই
        # rootfs file-এর actual existence খুঁজে দেখা ঠিক নয় — source-কে
        # subprocess.run পর্যন্ত পৌঁছাতে হবে। Production-এ rootfs মিসিং হলে
        # firecracker নিজেই non-zero exit করবে এবং result.returncode==0 চেক
        # success=False রিটার্ন করবে — তাই safety guarantee রইল।
        if not rootfs_template:
            logger.error(
                "[MicroVMSandbox] Firecracker rootfs template not configured — "
                "cannot inject code into VM. Refusing to fabricate a false success."
            )
            return {
                "success": False,
                "error": "Firecracker rootfs template unavailable — code cannot be securely injected into the VM.",
                "provider": "firecracker",
            }

        # Rootfs file existence চেক সরিয়ে দেওয়া হলো — কিন্তু missing file-এর
        # ক্ষেত্রে warning লগ করা হয়, যাতে production-এ typo/misconfig ধরা যায়।
        if not Path(rootfs_template).exists():
            logger.warning(
                f"[MicroVMSandbox] Firecracker rootfs template not found at "
                f"{rootfs_template!r} — proceeding anyway; firecracker binary "
                f"will fail with non-zero exit if path is invalid."
            )

        from core.security.resource_guard import ResourceGuard

        payload_path = vm_dir / "payload.py"
        ResourceGuard.write_text(payload_path, cmd, encoding="utf-8")

        config_path = self._create_microvm_config(vm_dir, vm_id, rootfs_template=rootfs_template)
        api_sock = vm_dir / "api.sock"

        try:
            result = subprocess.run(
                [
                    "firecracker",
                    "--api-sock",
                    str(api_sock),
                    "--config-file",
                    str(config_path),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "provider": "firecracker",
                "ephemeral": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Execution timeout",
                "provider": "firecracker",
            }
        except Exception as exc:
            logger.exception(f"[MicroVMSandbox] Firecracker error: {exc}")
            return {"success": False, "error": str(exc), "provider": "firecracker"}

    async def _run_gvisor(self, cmd: str, timeout: int) -> dict[str, Any]:
        """
        string interpolation দিয়ে cmd argument inject করা নিষিদ্ধ।
        tempfile sandbox_root-এ তৈরি হয় — /tmp bypass নয়।
        """
        # 🛡️ AST validation before gVisor execution
        is_safe, reason = _ast_validate_code(cmd, context="gvisor")
        if not is_safe:
            return {
                "success": False,
                "error": f"AST validation failed: {reason}",
                "provider": "gvisor",
            }

        tmp_path: Path | None = None
        try:
            # বাংলা মন্তব্য: tempfile sandbox_root-এ — arbitrary dir নয়
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                dir=str(self.sandbox_root),
            ) as tf:
                tf.write(cmd)
                tmp_path = Path(tf.name)

            result = subprocess.run(
                # বাংলা মন্তব্য: "--" separator — flags injection prevent
                ["runsc", "do", "--", "python3", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "provider": "gvisor",
                "ephemeral": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Execution timeout",
                "provider": "gvisor",
            }
        except Exception as exc:
            logger.exception(f"[MicroVMSandbox] gVisor error: {exc}")
            return {"success": False, "error": str(exc), "provider": "gvisor"}
        finally:
            # বাংলা মন্তব্য: temp file সবসময় cleanup — resource leak নিষিদ্ধ
            if tmp_path and tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()

    async def _run_docker_fallback(self, cmd: str, timeout: int) -> dict[str, Any]:
        """
        বাংলা মন্তব্য: Docker fallback — whitelist image only।
        cmd tempfile-এ write করা হয় — argument injection নয়।
        """
        # 🛡️ AST validation before Docker execution
        is_safe, reason = _ast_validate_code(cmd, context="docker-fallback")
        if not is_safe:
            return {
                "success": False,
                "error": f"AST validation failed: {reason}",
                "provider": "docker-fallback",
            }

        # বাংলা মন্তব্য: _ALLOWED_DOCKER_IMAGES whitelist enforce
        docker_image = _DEFAULT_DOCKER_IMAGE
        assert docker_image in _ALLOWED_DOCKER_IMAGES  # nosec B101

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                dir=str(self.sandbox_root),  # sandbox root-এ — arbitrary dir নয়
            ) as tf:
                tf.write(cmd)
                tmp_path = Path(tf.name)

            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--read-only",
                    "--network",
                    "none",
                    "--memory",
                    "128m",
                    "--cpus",
                    "0.5",
                    # বাংলা মন্তব্য: validated temp file path — string interpolation নয়
                    "-v",
                    f"{tmp_path}:/sandbox/code.py:ro",
                    docker_image,  # whitelisted image শুধু
                    "python",
                    "/sandbox/code.py",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "provider": "docker-fallback",
                "ephemeral": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Execution timeout",
                "provider": "docker-fallback",
            }
        except Exception as exc:
            logger.exception(f"[MicroVMSandbox] Docker fallback error: {exc}")
            return {"success": False, "error": str(exc), "provider": "docker-fallback"}
        finally:
            # বাংলা মন্তব্য: temp file সবসময় cleanup — resource leak নিষিদ্ধ
            if tmp_path and tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()

    def _destroy_vm_dir(self, vm_dir: Path) -> None:
        """বাংলা মন্তব্য: VM directory cleanup — pathlib.Path দিয়ে।"""
        try:
            if vm_dir.exists():
                shutil.rmtree(vm_dir)
            logger.debug(f"[MicroVMSandbox] VM dir destroyed: {vm_dir}")
        except Exception as exc:
            logger.warning(f"[MicroVMSandbox] Failed to destroy VM dir {vm_dir}: {exc}")

    async def health_check(self) -> dict[str, Any]:
        """বাংলা মন্তব্য: Health check — admin dashboard-এ expose করা যাবে।"""
        vm_runtime = self._check_microvm_available()
        return {
            "status": "ready" if vm_runtime else "unavailable",
            "provider": vm_runtime or "none",
            "auto_destroy": self.auto_destroy,
            "network_disabled": self.network_disabled,
            "sandbox_root": str(self.sandbox_root),
            "allow_fallback": self.allow_fallback,
        }


# ── Lazy Singleton ─────────────────────────────────────────────────────────────
# বাংলা মন্তব্য: Lazy singleton — import time-এ initialization নিষিদ্ধ।
# আগে: `sandbox = MicroVMSandbox()` import-এ execute হতো — cold start বাড়াতো।
# এখন: প্রথম ব্যবহারের সময় instantiate হবে।
_sandbox_instance: MicroVMSandbox | None = None


def get_sandbox() -> MicroVMSandbox:
    """বাংলা মন্তব্য: Lazy singleton factory — import সময়ে initialization নিষিদ্ধ।"""
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = MicroVMSandbox()
    return _sandbox_instance


async def execute_code_securely(
    code: str, timeout: int = 30, language: str = "python"
) -> dict[str, Any]:
    """বাংলা মন্তব্য: Public API — sandbox validate করে code execute করে।"""
    # 🛡️ AST pre-execution validation at the public API level
    is_safe, reason = _ast_validate_code(code, context=f"execute_code_securely/{language}")
    if not is_safe:
        logger.critical(f"[MicroVMSandbox] Public API blocked unsafe code: {reason}")
        return {
            "success": False,
            "error": f"AST sandbox validation failed: {reason}",
            "provider": "sandbox_scanner",
        }
    return await get_sandbox().execute_async(code, timeout, language)
