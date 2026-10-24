from __future__ import annotations

"""Logging & exception-handling detector (NEW category).

Catches:
  * f-string in logger calls — `logger.info(f"...")` formats eagerly even when
    the level is disabled (perf + log-injection). Use lazy `%`.
  * Broad `except:` (bare) — swallows KeyboardInterrupt/SystemExit.
  * Broad `except Exception:` without re-raise — swallows + hides bugs.
  * `except` without binding the exception — `except:` (bare) and
    `except Exception:` lose the traceback.
  * `raise` inside `except` without `from` — loses cause chain (Python 3+).
  * `print()` in production code (info).
"""


import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log"}
_LOGGER_NAMES = {"logger", "log", "logging", "LOGGER", "LOG", "_logger", "lgr"}


class LoggingDetector(BaseDetector):
    name = "logging"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)
        # logger.<method>(f"...")  or  logging.<method>(f"...")
        if name and "." in name:
            base, _, method = name.rpartition(".")
            if method in _LOG_METHODS and (base in _LOGGER_NAMES or _looks_like_logger(base, node)):
                if node.args and isinstance(node.args[0], ast.JoinedStr):
                    self.add(
                        rule_id="fstring-in-logging",
                        code="RuntimeWarning",
                        category=Category.LOGGING,
                        severity=Severity.WARNING,
                        title=f"f-string in {name}()",
                        message=f"`{name}(f'...')` formats the string even when the log "
                        f"level is disabled. Use lazy formatting `{name}('...', arg)`.",
                        node=node,
                        fixable=True,
                        fix_description="Convert f-string to %-style lazy args.",
                        suggestion=_to_lazy_log(node),
                    )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # type: ignore[override]
        # bare except:
        if node.type is None:
            self.add(
                rule_id="broad-except",
                code="Exception",
                category=Category.LOGGING,
                severity=Severity.WARNING,
                title="Bare 'except:' swallows everything",
                message="`except:` catches KeyboardInterrupt & SystemExit too, making "
                "the program hard to stop. Use `except Exception:` at minimum.",
                node=node,
                fixable=True,
                fix_description="Replace `except:` with `except Exception:`.",
                suggestion="except Exception:",
            )
        elif (
            isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
            and not node.body_re_raises()
        ):
            # broad except Exception that doesn't re-raise
            if not _body_re_raises(node.body):
                self.add(
                    rule_id="broad-except",
                    code="Exception",
                    category=Category.LOGGING,
                    severity=Severity.INFO,
                    title="'except Exception:' without re-raise",
                    message="`except Exception:` swallows the error silently. Re-raise "
                    "after logging, or narrow the exception type.",
                    node=node,
                    fixable=False,
                    fix_description="Log with logger.exception(...) then `raise`, or catch a specific type.",
                )

        # `raise X` inside except without `from` — loses cause chain
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Raise) and sub.exc is not None and sub.cause is None:
                    self.add(
                        rule_id="exception-not-logged",
                        code="RuntimeError",
                        category=Category.LOGGING,
                        severity=Severity.INFO,
                        title="raise inside except without `from`",
                        message="Raising a new exception inside `except` without `from` "
                        "drops the original traceback. Use `raise NewError(...) from err`.",
                        node=sub,
                        fixable=True,
                        fix_description="Add `from err` (bind the caught exception).",
                        suggestion="raise NewError(...) from err",
                    )
                    break
            else:
                continue
            break

    def visit_Call_print(self, node: ast.Call) -> None:  # noqa: N802
        pass

    def visit_Expr(self, node: ast.Expr) -> None:  # type: ignore[override]
        if isinstance(node.value, ast.Call):
            name = iter_call_name(node.value)
            if name == "print":
                self.add(
                    rule_id="print-in-production",
                    code="RuntimeWarning",
                    category=Category.LOGGING,
                    severity=Severity.INFO,
                    title="print() in production code",
                    message="`print()` bypasses the logging framework (no levels, no "
                    "structured output). Use `logger.info(...)`.",
                    node=node,
                    fixable=False,
                    fix_description="Replace print() with logger.info().",
                )
        self.generic_visit(node)


def _looks_like_logger(base: str, call: ast.Call) -> bool:
    # heuristic: any name ending with _logger / _log / LOGGER
    return base.lower().endswith("logger") or base.lower().endswith("_log")


def _body_re_raises(body: list[ast.stmt]) -> bool:
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Raise) and sub.exc is None:
                return True
    return False


def _to_lazy_log(node: ast.Call) -> str:
    """Best-effort conversion of logger.info(f"a {x} b {y}") to logger.info('a %s b %s', x, y)."""
    if not node.args or not isinstance(node.args[0], ast.JoinedStr):
        return ""
    jstr: ast.JoinedStr = node.args[0]
    fmt_parts: list[str] = []
    args: list[str] = []
    for part in jstr.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            fmt_parts.append(part.value.replace("%", "%%"))
        elif isinstance(part, ast.FormattedValue):
            fmt_parts.append("%s")
            try:
                args.append(ast.unparse(part.value))
            except Exception:
                args.append("?")
    fmt = "".join(fmt_parts)
    base = ""
    func = node.func
    if isinstance(func, ast.Attribute):
        try:
            base = ast.unparse(func.value)
        except Exception:
            base = "logger"
        method = func.attr
    else:
        base, method = "logger", "info"
    extra = ", ".join(args)
    return f"{base}.{method}({fmt!r}{(', ' + extra) if extra else ''})"


# monkeypatch helper for ExceptHandler.body_re_raises — kept minimal
def _except_body_re_raises(self: ast.ExceptHandler) -> bool:  # noqa: D401
    return _body_re_raises(self.body)


# attach helper (used in visit_ExceptHandler via node.body_re_raises())
ast.ExceptHandler.body_re_raises = _except_body_re_raises  # type: ignore[attr-defined]
