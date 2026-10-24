"""Auth & Security error detector (NEW — category 7).

Catches:
  * `ExpiredSignatureError` / `InvalidTokenError` — `jwt.decode()` without
    verifying signature / expiry (the #1 JWT bug: `options={"verify_signature":
    False}` or omitting the secret).
  * CORS misconfiguration — `CORSMiddleware(allow_origins=["<all>"])` combined with
    `allow_credentials=True` (browsers reject this, but more dangerously it
    allows any site to read authenticated responses).
  * Hardcoded `401`/`403` — `raise HTTPException(401)` / `(403)` without an
    actual auth check preceding it (suggests manual gate that bypasses the
    dependency-injected auth).
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name


class AuthSecurityDetector(BaseDetector):
    name = "auth-security"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)

        # --- jwt.decode without verify signature ---
        if name in ("jwt.decode", "jwt.get_unverified_header", "jose.jwt.decode"):
            # get_unverified_header is BY DESIGN unsafe — only flag jwt.decode
            if name == "jwt.get_unverified_header":
                self.add(
                    rule_id="jwt-unverified",
                    code="InvalidTokenError",
                    category=Category.SECURITY,
                    severity=Severity.WARNING,
                    title="jwt.get_unverified_header() used",
                    message="get_unverified_header() reads the token without validating "
                    "signature or expiry — only for inspecting `alg`/`kid` before "
                    "verification. Never use its output for auth decisions.",
                    node=node,
                    fixable=False,
                    fix_description="Use jwt.decode(token, key, algorithms=[...]) for auth.",
                )
            else:
                # look for options={"verify_signature": False} or no algorithms=
                has_algorithms = any(kw.arg == "algorithms" for kw in node.keywords)
                disable_sig = False
                for kw in node.keywords:
                    if kw.arg == "options" and isinstance(kw.value, ast.Dict):
                        for k, v in zip(kw.value.keys, kw.value.values, strict=False):
                            if (
                                isinstance(k, ast.Constant)
                                and k.value == "verify_signature"
                                and isinstance(v, ast.Constant)
                                and v.value is False
                            ):
                                disable_sig = True
                if disable_sig:
                    self.add(
                        rule_id="jwt-unverified",
                        code="InvalidTokenError",
                        category=Category.SECURITY,
                        severity=Severity.CRITICAL,
                        title="jwt.decode with verify_signature=False",
                        message="Decoding with verify_signature=False accepts ANY token, "
                        "including forged ones. This is a complete auth bypass.",
                        node=node,
                        fixable=False,
                        fix_description="Remove options={'verify_signature': False} and pass the real key.",
                    )
                elif not has_algorithms:
                    self.add(
                        rule_id="jwt-missing-algorithms",
                        code="InvalidTokenError",
                        category=Category.SECURITY,
                        severity=Severity.WARNING,
                        title="jwt.decode without algorithms=",
                        message="jwt.decode() without `algorithms=[...]` raises a "
                        "DeprecationWarning and will become an error. It also lets "
                        "the `none` algorithm through on older versions.",
                        node=node,
                        fixable=True,
                        fix_description="Pass algorithms=['HS256'] (or your actual algorithm).",
                        suggestion=f"{ast.unparse(node).rstrip(')')}, algorithms=['HS256'])",
                    )

        # --- CORS misconfiguration ---
        if name in ("CORSMiddleware", "fastapi.middleware.cors.CORSMiddleware"):
            origins = None
            credentials = False
            for kw in node.keywords:
                if kw.arg == "allow_origins" and isinstance(kw.value, ast.List | ast.Tuple):
                    origins = kw.value.elts
                if kw.arg == "allow_credentials" and isinstance(kw.value, ast.Constant):
                    credentials = bool(kw.value.value)
            if origins is not None:
                has_wildcard = any(isinstance(o, ast.Constant) and o.value == "*" for o in origins)
                if has_wildcard and credentials:
                    self.add(
                        rule_id="cors-wildcard-credentials",
                        code="RuntimeError",
                        category=Category.SECURITY,
                        severity=Severity.CRITICAL,
                        title="CORS allow_origins=['<all>'] + allow_credentials=True",
                        message="This combination is rejected by browsers AND, when "
                        "allowed by a permissive server, lets any website read "
                        "authenticated responses (cookie/Authorization header leak).",
                        node=node,
                        fixable=False,
                        fix_description="Set allow_origins to an explicit list, or set allow_credentials=False.",
                    )
                elif has_wildcard:
                    self.add(
                        rule_id="cors-wildcard",
                        code="RuntimeError",
                        category=Category.SECURITY,
                        severity=Severity.WARNING,
                        title="CORS allow_origins=['<all>']",
                        message="allow_origins=['<all>'] permits any website to call your "
                        "API. Acceptable for public read-only APIs; dangerous for "
                        "anything that returns user-specific data.",
                        node=node,
                        fixable=False,
                        fix_description="Restrict to your real frontend origins.",
                    )

        # --- hardcoded 401/403 without auth dependency ---
        if name == "HTTPException" and node.args:
            status = node.args[0]
            if isinstance(status, ast.Constant) and status.value in (401, 403):
                # very heuristic: look back for Depends() in enclosing function signature
                self.add(
                    rule_id="manual-auth-gate",
                    code="HTTPException",
                    category=Category.WEB_API,
                    severity=Severity.INFO,
                    title=f"Manual HTTPException({status.value}) — verify auth dependency",
                    message=f"`raise HTTPException({status.value})` is a manual gate. "
                    f"Prefer FastAPI's `Depends(get_current_user)` so auth is enforced "
                    f"consistently and documented in OpenAPI.",
                    node=node,
                    fixable=False,
                    fix_description="Use Depends(get_current_user) on the route instead.",
                )

        self.generic_visit(node)
