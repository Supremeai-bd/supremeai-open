"""Universal Web Intent Engine (site-agnostic, selector-free).

বাংলা সারসংক্ষেপ:
    কোনো CSS ক্লাস / XPath / বাটনের অবস্থান সেভ করা হয় না। শুধু "প্রসেস" (intent
    sequence) সেভ থাকে — যেমন: login_entry ক্লিক → identifier_field পূরণ →
    password_field পূরণ → submit। রানটাইমে ইঞ্জিন পেজের অ্যাক্সেসিবিলিটি সেমান্টিক্স
    (role, accessible name, placeholder, autocomplete, form-সম্পর্ক, নৈকট্য) স্কোর করে
    সঠিক এলিমেন্ট খুঁজে নেয়। সাইট UI বদলালেও কোড বদলাতে হয় না।

Resolution ladder per intent:
    1. Self-healing memory  — last successful (role, accessible-name) for this origin,
                              re-validated via Playwright get_by_role (never trusted blindly).
    2. Semantic scoring     — in-page scan of every visible interactive element, scored by
                              accessible name / hints / input type / form-submit / proximity.
    3. Keyboard fallback    — e.g. Enter for submit-type intents.

No site / vendor identifiers live in code. Site specifics (start URL, credentials refs)
come from local, git-ignored config or environment variables.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Locator, Page

DEFAULT_RECIPES = Path(__file__).with_name("web_intent_recipes.json")

# In-page semantic scorer. Returns a temporary token for the best candidate.
_SCORER_JS = r"""
({spec, anchorToken}) => {
  const vis = el => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const accName = el => {
    const lb = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(i => (document.getElementById(i) || {}).innerText || '').join(' ').trim();
    const lbl = el.labels && el.labels.length ? el.labels[0].innerText : '';
    return (el.getAttribute('aria-label') || lb || lbl || (el.innerText || '') ||
            el.getAttribute('title') || el.getAttribute('placeholder') || el.value || '').trim().slice(0, 120);
  };
  const hints = el => [el.getAttribute('placeholder'), el.getAttribute('name'), el.id,
    el.getAttribute('autocomplete'), el.getAttribute('aria-label'), el.getAttribute('title'),
    el.getAttribute('type'), el.getAttribute('data-testid'),
    typeof el.className === 'string' ? el.className : ''].filter(Boolean).join(' ');
  const roleOf = el => {
    const r = el.getAttribute('role'); if (r) return r;
    const t = el.tagName.toLowerCase();
    if (t === 'button' || (t === 'input' && ['submit', 'button'].includes(el.type))) return 'button';
    if (t === 'a') return 'link';
    if (t === 'textarea' || el.isContentEditable || t === 'input') return 'textbox';
    return t;
  };
  const rx = a => (a || []).map(p => new RegExp(p, 'i'));
  const names = rx(spec.names), hs = rx(spec.hints), neg = rx(spec.exclude);
  const anchor = anchorToken ? document.querySelector(`[data-wi="${anchorToken}"]`) : null;
  const ar = anchor ? anchor.getBoundingClientRect() : null;
  let best = null, bestScore = -1e9;
  document.querySelectorAll('button,a,input,textarea,select,[contenteditable="true"],[role]').forEach(el => {
    if (!vis(el)) return;
    const role = roleOf(el);
    if (spec.roles && !spec.roles.includes(role)) return;
    if (spec.input_types) {
      if (el.tagName !== 'INPUT' || !spec.input_types.includes((el.type || 'text').toLowerCase())) return;
    }
    if (el.tagName === 'INPUT' && ['hidden', 'file', 'checkbox', 'radio'].includes(el.type)) return;
    const name = accName(el), h = hints(el);
    let score = 0, matched = false;
    if (names.some(r => r.test(name))) { score += 10; matched = true; }
    if (hs.some(r => r.test(h) || r.test(name))) { score += 5; matched = true; }
    if (neg.some(r => r.test(name) || r.test(h))) score -= 25;
    if (spec.input_types) matched = true;
    if (spec.require_match && !matched) return;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') score -= spec.allow_disabled ? 0 : 6;
    if (spec.form_submit && el.type === 'submit') score += 6;
    if (role === 'textbox') score += Math.min(4, el.getBoundingClientRect().width / 300);
    if (ar) {
      const r = el.getBoundingClientRect();
      const d = Math.hypot((r.left + r.right) / 2 - (ar.left + ar.right) / 2, (r.top + r.bottom) / 2 - (ar.top + ar.bottom) / 2);
      score += Math.max(0, 8 - d / 80);
    }
    if (score > bestScore) { bestScore = score; best = {el, role, name}; }
  });
  if (!best || bestScore < (spec.min_score ?? 3)) return null;
  const token = 'w' + Math.random().toString(36).slice(2, 10);
  best.el.setAttribute('data-wi', token);
  return {token, role: best.role, name: best.name, score: bestScore};
}
"""

_ARIA_ROLES = {"button", "link", "textbox", "combobox", "searchbox", "menuitem", "tab"}


def human_pause(lo: float = 0.25, hi: float = 0.9) -> float:
    return random.uniform(lo, hi)


class IntentEngine:
    """Resolves abstract intents (e.g. ``send_message``) to live elements on any site."""

    def __init__(self, recipes_path: Path | str = DEFAULT_RECIPES, memory_path: Path | str | None = None):
        self.recipes: dict[str, Any] = json.loads(Path(recipes_path).read_text(encoding="utf-8"))
        self.intents: dict[str, dict] = self.recipes["intents"]
        self.memory_path = Path(memory_path) if memory_path else None
        self.memory: dict[str, dict] = {}
        if self.memory_path and self.memory_path.exists():
            try:
                self.memory = json.loads(self.memory_path.read_text(encoding="utf-8"))
            except Exception:
                self.memory = {}
        self._tokens: dict[tuple[int, str], str] = {}
        self._mouse: dict[int, tuple[float, float]] = {}

    # ---------------- human-like pointer ----------------
    async def _human_click(self, page: Page, loc: Locator) -> None:
        """Quadratic-Bezier pointer path with jitter, then click at a random point inside the target."""
        try:
            await loc.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        box = await loc.bounding_box()
        if not box:
            await loc.click(timeout=4000)
            return
        tx = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        sx, sy = self._mouse.get(id(page), (random.uniform(200, 900), random.uniform(150, 600)))
        cx = (sx + tx) / 2 + random.uniform(-120, 120)
        cy = (sy + ty) / 2 + random.uniform(-90, 90)
        steps = random.randint(16, 34)
        for i in range(1, steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
            y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
            await page.mouse.move(x + random.uniform(-1, 1), y + random.uniform(-1, 1))
            await asyncio.sleep(random.uniform(0.004, 0.02))
        await asyncio.sleep(random.uniform(0.05, 0.25))
        await page.mouse.click(tx, ty, delay=random.randint(40, 130))
        self._mouse[id(page)] = (tx, ty)

    async def idle_wander(self, page: Page) -> None:
        """Occasional small pointer drift / scroll while reading — like a person."""
        try:
            sx, sy = self._mouse.get(id(page), (640, 400))
            nx, ny = sx + random.uniform(-150, 150), sy + random.uniform(-100, 100)
            await page.mouse.move(max(5, nx), max(5, ny), steps=random.randint(5, 15))
            self._mouse[id(page)] = (nx, ny)
            if random.random() < 0.3:
                await page.mouse.wheel(0, random.choice([-1, 1]) * random.randint(80, 400))
        except Exception:
            pass

    # ---------------- blockers ----------------
    async def detect_blocker(self, page: Page) -> str | None:
        """Return 'human_verification' | 'rate_limit' | None.

        Scoped to iframes / alerts / dialogs / short interstitial pages so normal chat
        content that merely *mentions* these words does not trigger a false stop.
        """
        g = self.recipes.get("guards", {})
        try:
            return await page.evaluate(
                r"""(g) => {
                  const has = (t, arr) => arr.some(p => new RegExp(p, 'i').test(t));
                  const frames = Array.from(document.querySelectorAll('iframe')).map(f => (f.src || '') + ' ' + (f.title || ''));
                  if (frames.some(s => has(s, g.human_verification_frames || []))) return 'human_verification';
                  const scoped = Array.from(document.querySelectorAll(
                    '[role=alert],[role=alertdialog],[role=dialog],[data-sonner-toast],.toast'))
                    .map(e => e.innerText || '').join('\n');
                  const body = document.body ? document.body.innerText : '';
                  const surface = scoped + (body.length < 1500 ? '\n' + body : '');
                  if (has(surface, g.human_verification_text || [])) return 'human_verification';
                  if (has(scoped, g.rate_limit_text || [])) return 'rate_limit';
                  return null;
                }""",
                g,
            )
        except Exception:
            return None

    # ---------------- memory (self-healing) ----------------
    def _remember(self, page: Page, intent: str, role: str, name: str) -> None:
        if not self.memory_path or not name or role not in _ARIA_ROLES:
            return
        origin = urlparse(page.url).netloc
        self.memory.setdefault(origin, {})[intent] = {"role": role, "name": name}
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory_path.write_text(json.dumps(self.memory, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _forget(self, page: Page, intent: str) -> None:
        self.memory.get(urlparse(page.url).netloc, {}).pop(intent, None)

    # ---------------- resolution ----------------
    async def resolve(self, page: Page, intent: str, near: str | None = None) -> Locator | None:
        spec = self.intents[intent]
        mem = self.memory.get(urlparse(page.url).netloc, {}).get(intent)
        if mem:
            try:
                loc = page.get_by_role(mem["role"], name=mem["name"], exact=True).first
                if await loc.is_visible(timeout=600):
                    return loc
            except Exception:
                pass
            self._forget(page, intent)  # stale → heal by re-scoring

        anchor = self._tokens.get((id(page), near)) if near else None
        try:
            res = await page.evaluate(_SCORER_JS, {"spec": spec, "anchorToken": anchor})
        except Exception:
            return None
        if not res:
            return None
        self._tokens[(id(page), intent)] = res["token"]
        self._remember(page, intent, res["role"], res["name"])
        return page.locator(f'[data-wi="{res["token"]}"]').first

    async def present(self, page: Page, intent: str) -> bool:
        return await self.resolve(page, intent) is not None

    # ---------------- actions ----------------
    async def click(self, page: Page, intent: str, near: str | None = None) -> bool:
        loc = await self.resolve(page, intent, near=near)
        if loc is None:
            if self.intents[intent].get("enter_fallback"):
                await page.keyboard.press("Enter")
                return True
            return False
        await asyncio.sleep(human_pause())
        try:
            await self._human_click(page, loc)
            return True
        except Exception:
            if self.intents[intent].get("enter_fallback"):
                await page.keyboard.press("Enter")
                return True
            return False

    async def fill(self, page: Page, intent: str, text: str) -> bool:
        loc = await self.resolve(page, intent)
        if loc is None:
            return False
        try:
            await self._human_click(page, loc)
            await asyncio.sleep(human_pause(0.1, 0.4))
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            if len(text) <= 160:  # human-like cadence for short input
                await page.keyboard.type(text, delay=random.randint(18, 55))
            else:  # paste-like insertion for long prompts
                await page.keyboard.insert_text(text)
            return True
        except Exception:
            return False

    # ---------------- page state ----------------
    async def is_busy(self, page: Page, sample_s: float = 1.5) -> bool:
        """Busy if a stop/cancel control exists, aria-busy is set, or content is still streaming."""
        if "stop_generation" in self.intents and await self.present(page, "stop_generation"):
            return True
        try:
            if await page.locator("[aria-busy='true']").count():
                return True
            a = await page.evaluate("() => document.body.innerText.length")
            await asyncio.sleep(sample_s)
            b = await page.evaluate("() => document.body.innerText.length")
            return a != b
        except Exception:
            return False

    async def needs_login(self, page: Page) -> bool:
        if await self.present(page, "message_input"):
            return False
        return await self.present(page, "password_field") or await self.present(page, "login_entry")

    async def snapshot_text(self, page: Page) -> str:
        try:
            return await page.evaluate("() => document.body.innerText")
        except Exception:
            return ""

    # ---------------- recipes (saved processes) ----------------
    async def run_recipe(self, page: Page, name: str) -> bool:
        """Execute a saved process. Values like ``env:VAR`` are resolved from environment."""
        for step in self.recipes["recipes"][name]:
            do, intent = step["do"], step.get("intent")
            value = step.get("value")
            if isinstance(value, str) and value.startswith("env:"):
                value = os.environ.get(value[4:], "")
            ok = True
            if do == "click":
                ok = await self.click(page, intent, near=step.get("near"))
            elif do == "fill":
                ok = bool(value) and await self.fill(page, intent, value)
            elif do == "press":
                await page.keyboard.press(value or "Enter")
            elif do == "wait":
                await asyncio.sleep(float(value or 2))
            if not ok and not step.get("optional"):
                return False
            await asyncio.sleep(human_pause(0.6, 1.6))
        return True

    async def send_message(self, page: Page, text: str) -> bool:
        if not await self.fill(page, "message_input", text):
            return False
        await asyncio.sleep(human_pause(0.3, 0.8))
        return await self.click(page, "send_message", near="message_input")


def extract_reply(before: str, after: str, prompt: str) -> str:
    """Site-agnostic reply extraction: text that appeared after our prompt."""
    idx = after.rfind(prompt[:80]) if prompt else -1
    if idx >= 0:
        return after[idx + len(prompt[:80]):].strip()
    return after[len(before):].strip() if after.startswith(before[:200]) else after[-4000:].strip()
