"""Infinite feed scanning: dynamic scroll planning + runtime JS snippet.

Crawl4AI pattern (`scan_full_page`): expand the viewport downward in
controlled rounds to trigger lazy-loaded media and infinite feeds, with
stall detection. This module is PURE LOGIC + a JS constant:
  - `ScrollPlan` computes deterministic scroll steps (testable offline).
  - `SCROLL_AND_EXPAND_JS` is the snippet the browser tier executes.
  - `FeedExpander` models multi-round growth with a pluggable observer,
    so CI can simulate feeds without launching any browser.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "SCROLL_AND_EXPAND_JS",
    "FeedExpander",
    "ScrollPlan",
    "ScrollStep",
]

SCROLL_AND_EXPAND_JS = """
async () => {
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));
  const step = Math.floor(window.innerHeight * 0.8);
  let lastHeight = 0, stagnant = 0, rounds = 0;
  while (rounds < 200 && stagnant < 5) {
    window.scrollBy(0, step);
    await delay(400);
    const h = document.body.scrollHeight;
    if (h === lastHeight) { stagnant += 1; } else { stagnant = 0; }
    lastHeight = h;
    rounds += 1;
  }
  window.scrollTo(0, 0);
  return { rounds, finalHeight: lastHeight, stalled: stagnant >= 5 };
}
""".strip()


@dataclass(frozen=True)
class ScrollStep:
    """One planned scroll round."""

    round_index: int
    scroll_to_y: int
    wait_ms: int
    trigger_lazy_load: bool


class ScrollPlan:
    """Deterministic scroll plan for a page of known height."""

    def __init__(
        self,
        page_height: int,
        viewport_height: int = 1080,
        step_ratio: float = 0.8,
        wait_ms: int = 400,
        stall_limit: int = 5,
        max_rounds: int = 200,
    ) -> None:
        if page_height <= 0 or viewport_height <= 0:
            raise ValueError("heights must be positive")
        if not 0.1 <= step_ratio <= 1.0:
            raise ValueError("step_ratio must be within 0.1..1.0")
        if wait_ms < 0:
            raise ValueError("wait_ms must be >= 0")
        if stall_limit < 1 or max_rounds < 1:
            raise ValueError("stall_limit and max_rounds must be >= 1")
        self.page_height = page_height
        self.viewport_height = viewport_height
        self.step_ratio = step_ratio
        self.wait_ms = wait_ms
        self.stall_limit = stall_limit
        self.max_rounds = max_rounds

    def build(self) -> list[ScrollStep]:
        """Round-by-round plan; stops at stall_limit stagnant rounds."""
        step = max(1, int(self.viewport_height * self.step_ratio))
        plan: list[ScrollStep] = []
        stagnant = 0
        y = 0
        last_height = self.page_height
        round_index = 0
        while round_index < self.max_rounds and stagnant < self.stall_limit:
            y = min(y + step, self.page_height)
            plan.append(
                ScrollStep(
                    round_index=round_index,
                    scroll_to_y=y,
                    wait_ms=self.wait_ms,
                    trigger_lazy_load=(round_index % 2 == 1),
                )
            )
            round_index += 1
            stagnant += 1  # without page growth, every round is stagnant
        return plan


class FeedExpander:
    """Simulates/expands infinite feeds with a pluggable height observer."""

    def __init__(
        self,
        height_provider: Callable[[], int],
        grow: Callable[[int], None],
        initial_height: int = 2000,
    ) -> None:
        if initial_height <= 0:
            raise ValueError("initial_height must be positive")
        self._height_provider = height_provider
        self._grow = grow
        self._height = initial_height
        self.rounds_executed = 0
        self.stalled_rounds = 0

    def run_round(self) -> tuple[int, bool]:
        """Execute one expansion round; returns (height, grew)."""
        before = self._height
        self._grow(self.rounds_executed)
        provided = self._height_provider()
        self._height = provided if provided and provided > before else before
        grew = self._height > before
        self.rounds_executed += 1
        if not grew:
            self.stalled_rounds += 1
        return self._height, grew

    def expand(self, max_rounds: int = 50, stall_limit: int = 5) -> int:
        """Expand until stall or cap; returns final height."""
        if max_rounds < 1 or stall_limit < 1:
            raise ValueError("max_rounds and stall_limit must be >= 1")
        stagnant = 0
        while self.rounds_executed < max_rounds and stagnant < stall_limit:
            _, grew = self.run_round()
            stagnant = stagnant + 1 if not grew else 0
        return self._height
