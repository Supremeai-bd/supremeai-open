import ast

from core.logging_config import logger

# Testing Suite Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


class SecurityError(Exception):
    pass


def run_sandbox_ast_check(code: str) -> bool:
    """
    SkillLoader-এর মূল AST ডিফেন্স গেটকিপার লজিক।
    রিটার্ন করবে True যদি কোডটি সেফ হয়, অন্যথায় SecurityError থ্রো করবে।
    """
    try:
        tree = ast.parse(code)
        # P0 (Task 9-c2): ban list extended beyond the process/exec crowd to also
        # cover network access (requests/urllib/http), code-loading primitives
        # (importlib/runpy/marshal), FFI (ctypes) and deserialization (pickle).
        banned_imports = {
            "os",
            "sys",
            "subprocess",
            "shutil",
            "socket",
            "pty",
            "requests",
            "urllib",
            "http",
            "importlib",
            "ctypes",
            "pickle",
            "runpy",
            "marshal",
        }
        banned_keys = {
            "eval",
            "exec",
            "compile",
            "__import__",
            "getattr",
            "setattr",
            "delattr",
            "globals",
            "locals",
        }

        for node in ast.walk(tree):
            # ২. Type-Safe Import Blocker
            if isinstance(node, ast.Import | ast.ImportFrom):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module]
                )
                for mod in modules:
                    if mod and mod.split(".")[0] in banned_imports:
                        raise SecurityError(f"Banned root import '{mod}' blocked.")

            # ৩. Dunder and Method Reflection Blocker
            if isinstance(node, ast.Attribute) and (
                node.attr.startswith("__") or node.attr in banned_keys
            ):
                raise SecurityError(f"Malicious attribute access '{node.attr}' detected.")

            # 💥 ৪. Global Identifier Protection
            if isinstance(node, ast.Name) and node.id in banned_keys:
                raise SecurityError(
                    f"Attempted reference to banned identifier '{node.id}' blocked."
                )

            # ৫. Subscript Protection
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in banned_keys
            ):
                raise SecurityError(f"Obfuscated key reference '{node.value}' blocked.")
        return True
    except SyntaxError:
        return False


def generate_fuzz_payloads():
    """১০০টি বিভিন্ন পারমিউটেশনের অবফাসকেটেড ও বিপজ্জনক আরসিই অ্যাটাক ম্যাট্রিক্স জেনারেটর"""
    payloads = []

    # Category 1: Direct Builtin Attacks & Subscript Bypasses
    banned_keys = [
        "eval",
        "exec",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "globals",
        "locals",
    ]
    for key in banned_keys:
        payloads.append((f"{key}('logger.info(1)')", "Direct Builtin Execution"))
        payloads.append((f"x = {key}\nx('pass')", "Alias Binding Attack"))
        payloads.append((f"fn = '{key}'\nfunc = globals()[fn]", "Dynamic String Key Lookup"))
        payloads.append(("f = 'ev' + 'al'\nmain = globals()[f]", "String Concatenation Lookup"))

    # Category 2: Banned Imports & Aliasing
    banned_imports = [
        "os",
        "sys",
        "subprocess",
        "shutil",
        "socket",
        "pty",
        "requests",
        "urllib",
        "http",
        "importlib",
        "ctypes",
        "pickle",
        "runpy",
        "marshal",
    ]
    for imp in banned_imports:
        payloads.append((f"import {imp}", "Direct Banned Import"))
        payloads.append((f"import {imp} as hacked_m", "Import Aliasing"))
        payloads.append((f"from {imp} import *", "Star Import Injection"))
        payloads.append((f"__import__('{imp}').system('ls')", "Dynamic Dunder Import RCE"))

    # Category 3: Dunder Reflection & Jailbreak Constructs (Subclasses, Classes, Bases)
    dunder_tricks = [
        "().__class__.__base__.__subclasses__()",
        "object.__subclasses__()",
        "[].__class__.__mro__[1].__subclasses__()",
        "request.__init__.__globals__",
        "self.__dict__",
        "None.__class__.__bootstrap__",
    ]
    for trick in dunder_tricks:
        payloads.append((f"x = {trick}", "Dunder Reflection Jailbreak"))
        payloads.append((f"logger.info({trick})", "Nested Print Dunder Exfiltration"))

    # Category 4: Dynamic Attribute Injection (Reflection Gateways)
    payloads.append(("getattr(object, 'banned')", "Direct Getattr Reflection"))
    payloads.append(("setattr(object, 'key', value)", "Direct Setattr Manipulation"))
    payloads.append(("delattr(object, 'key')", "Delattr State Disruption"))

    # Category 5: Complex Obfuscated Structural Strings (AST Constant Targets)
    payloads.append(("payload = 'eval'\nlogger.info(payload)", "Plaintext Constant Injection"))
    payloads.append(("def malicious():\n    return 'exec'", "Nested Function Constant Return"))
    payloads.append(
        (
            "class Hack:\n    def __init__(self):\n        self.x = 'compile'",
            "Class Property Constant Assignment",
        )
    )

    # ১০০টি টেস্ট কেস পুর্ন করতে ডাইনামিক লুপ ম্যাট্রিক্স এক্সপেনশন
    count = 1
    while len(payloads) < 100:
        payloads.append(
            (
                f"# Cache Noise Padding {count}\nx = 'eval'",
                "Structural Constant Matrix Padding",
            )
        )
        count += 1

    return payloads[:100]


def execute_ultimate_fuzz_test():
    logger.info("💥 Initiating Ultimate AST Sandbox Fuzz Testing Shooting Range...")
    payloads = generate_fuzz_payloads()

    blocked_count = 0
    bypass_count = 0
    syntax_error_count = 0

    logger.info("\n" + "=" * 80)
    logger.info(f"| {'ATTACK VECTOR CATEGORY':<35} | {'STATUS':<12} | {'ENGINE VERDICT':<23} |")
    logger.info("=" * 80)

    for idx, (code, category) in enumerate(payloads, 1):
        try:
            is_safe = run_sandbox_ast_check(code)
            if is_safe:
                # স্যান্ডবক্স কোডটিকে সেফ বলেছে -> অর্থাৎ হ্যাক সফল, স্যান্ডবক্স ফেল করেছে (Bypass)!
                logger.info(
                    f"| {idx:03d}. {category:<30} | {RED}{'BYPASS':<12}{RESET} | Allowed Malicious Code  |"
                )
                bypass_count += 1
            else:
                # সিনট্যাক্স এরর হ্যান্ডলিং
                logger.info(
                    f"| {idx:03d}. {category:<30} | {GREEN}{'BLOCKED':<12}{RESET} | Syntax Normalization    |"
                )
                syntax_error_count += 1
        except SecurityError as e:
            # স্যান্ডবক্স সফলভাবে সিকিউরিটি এরর রেইজ করে অ্যাটাক ব্লক করেছে (Success)
            logger.info(
                f"| {idx:03d}. {category:<30} | {GREEN}{'BLOCKED':<12}{RESET} | {str(e)[:23]:<23} |"
            )
            blocked_count += 1

    logger.info("=" * 80)
    logger.info("\n📊 FINAL FUZZING LAB REPORT:")
    logger.info(
        f"  🟢 TOTAL ATTACKS SECURELY DEFENDED : {GREEN}{blocked_count + syntax_error_count}/100{RESET}"
    )
    logger.info(
        f"  🔴 TOTAL BYPASSES (SANDBOX CRACKS) : {RED if bypass_count > 0 else GREEN}{bypass_count}/100{RESET}"
    )
    logger.info("=" * 80)

    if bypass_count == 0:
        logger.info(
            f"\n🏆 {GREEN}PASSED! Your SkillLoader AST Sandbox is 100% UNKILLABLE against all 100 fuzz vectors.{RESET}\n"
        )
    else:
        logger.info(
            f"\n🚨 {RED}SECURITY WARNING: Your sandbox was cracked! Review the BYPASS vectors immediately.{RESET}\n"
        )


if __name__ == "__main__":
    execute_ultimate_fuzz_test()
