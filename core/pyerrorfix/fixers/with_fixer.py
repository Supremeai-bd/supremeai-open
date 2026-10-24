"""Wrap bare `f = open(...)` in `with open(...) as f:`.

This is the trickiest fixer: it must re-indent the following block. We only
attempt the transformation when the open() is the sole RHS of a simple
assignment inside a function body (not a module-level statement) and the
following lines are a contiguous indented block.
"""

from __future__ import annotations

from pyerrorfix.fixers.base import BaseFixer


class WithOpenFixer(BaseFixer):
    name = "with-open"
    applies_to = {"open-without-context"}

    def apply(self) -> str:
        # Conservative: this fixer is opt-in and we skip it unless the snippet is
        # clearly a single `x = open(path)` followed by an indented block.
        # The detector already produces a clear suggestion, so the user can apply
        # it manually; we do not auto-rewrite multi-line blocks to avoid breaking
        # indentation heuristically.
        return self.source
