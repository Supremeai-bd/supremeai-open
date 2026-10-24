"""Convert bare `except:` → `except Exception:`."""

from __future__ import annotations

import re

from pyerrorfix.fixers.base import BaseFixer


class BareExceptFixer(BaseFixer):
    name = "bare-except"
    applies_to = {"broad-except"}

    def apply(self) -> str:
        lines = self._lines()
        # find lines that are exactly 'except:' (with leading whitespace)
        out: list[str] = []
        for line in lines:
            m = re.match(r"^(\s*)except\s*:", line)
            if m:
                indent = m.group(1)
                rest = line[len(indent) + len("except:") :].lstrip()
                if rest:
                    out.append(f"{indent}except Exception:{rest}")
                else:
                    out.append(f"{indent}except Exception:\n")
            else:
                out.append(line)
        return "".join(out)
