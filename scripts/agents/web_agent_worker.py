"""Generic Multi-Tab Web Agent Worker (site-agnostic).

বাংলা সারসংক্ষেপ:
    যেকোনো ওয়েব-চ্যাট সাইটে কাজ করে — কোডে কোনো সাইটের নাম, URL, সিলেক্টর নেই।
    • সেশন আবিষ্কার: পেজ লোডের সময় নেটওয়ার্কের JSON রেসপন্স পর্যবেক্ষণ করে
      (id + title আছে এমন তালিকা) + DOM লিংক — স্বয়ংক্রিয়ভাবে সব কথোপকথন খুঁজে নেয়।
    • URL টেমপ্লেট নিজে শেখে (বর্তমান URL / লিংক থেকে), না পেলে শিরোনামে ক্লিক করে।
    • প্রতিটি সেশনের জন্য আলাদা ট্যাব, সব ট্যাব asyncio.gather দিয়ে সমান্তরালে চলে।
    • UI ইন্টার‍্যাকশন web_intent_engine দিয়ে — intent-ভিত্তিক, self-healing।
    • টাস্ক IPC: <tasks-dir>/inbox/*.json → processing → completed (continuous loop থেকে)।

Site config (local, git-ignored) — <tasks-dir>/site.json:
    {"start_url": "https://...", "max_tabs": 4}
or env WEB_AGENT_START_URL / CLI --url.

Task file format (<tasks-dir>/inbox/<task_id>.json):
    {"task_id": "...", "prompt": "...", "role": "coder"}           # route by role
    {"task_id": "...", "prompt": "...", "session_pattern": "vault"} # or by title regex
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page, Response, async_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "backend"))
from web_intent_engine import IntentEngine, extract_reply  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_PROFILE = os.environ.get("WEB_AGENT_PROFILE", str(REPO_ROOT / ".browser_profile"))
DEFAULT_TASKS = os.environ.get("WEB_AGENT_TASKS", str(REPO_ROOT / ".browser_tasks"))

ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[A-Za-z0-9_-]{20,}"
)


def log(msg: str, tag: str | None = None) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {'[' + tag[:28] + '] ' if tag else ''}{msg}", flush=True)


@dataclass
class Session:
    sid: str
    title: str
    role: str
    url: str | None = None
    updated: float = 0
    page: Page | None = None
    last_action: float = 0.0


# ---------------------------------------------------------------- discovery
class SessionSniffer:
    """Passively learns conversation lists from any JSON the site itself loads."""

    def __init__(self) -> None:
        self.groups: list[dict[str, dict[str, Any]]] = []  # one dict per discovered list

    def _walk(self, obj: Any) -> None:
        if isinstance(obj, list):
            group: dict[str, dict[str, Any]] = {}
            for x in (x for x in obj if isinstance(x, dict)):
                sid = next((x.get(k) for k in ("id", "uuid", "conversation_id", "chat_id", "thread_id") if x.get(k)), None)
                title = next((x.get(k) for k in ("title", "name", "summary", "subject") if isinstance(x.get(k), str)), None)
                if sid and title is not None and ID_RE.fullmatch(str(sid)):
                    upd = x.get("updated_at") or x.get("update_time") or x.get("updatedAt") or 0
                    try:
                        upd = float(upd)
                    except (TypeError, ValueError):
                        upd = 0.0
                    group[str(sid)] = {"title": title.strip(), "updated": upd}
            if group:
                self.groups.append(group)
            for x in obj:
                if isinstance(x, (list, dict)):
                    self._walk(x)
        elif isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    self._walk(v)

    def sessions(self, anchor_urls: list[str]) -> dict[str, dict[str, Any]]:
        """Prefer lists that contain the currently-open session id (the real session index)."""
        trusted = [g for g in self.groups if any(i in u for i in g for u in anchor_urls)]
        merged: dict[str, dict[str, Any]] = {}
        for g in (trusted or self.groups):
            for sid, meta in g.items():
                if sid not in merged or (meta["title"] and not merged[sid]["title"]):
                    merged[sid] = meta
        return merged

    async def on_response(self, resp: Response) -> None:
        try:
            if "json" in (resp.headers.get("content-type") or "") and resp.ok:
                self._walk(await resp.json())
        except Exception:
            pass


def learn_template(urls: list[str], ids: list[str]) -> str | None:
    for u in urls:
        for i in ids:
            if i in u:
                return u.replace(i, "{id}")
    for u in urls:
        m = ID_RE.search(urlparse(u).path)
        if m:
            return u.replace(m.group(0), "{id}")
    return None


def infer_role(title: str, roles_cfg: dict[str, dict]) -> str:
    low = title.lower()
    for role, cfg in roles_cfg.items():
        if any(k in low for k in cfg.get("keywords", [])):
            return role
    return next(iter(roles_cfg), "coder")


async def open_session_by_title(page: Page, start_url: str, title: str) -> str | None:
    """Fallback when no URL template is learnable: click the session title like a human."""
    try:
        await page.goto(start_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        before = page.url
        await page.get_by_text(title, exact=True).first.click(timeout=5000)
        for _ in range(20):
            await asyncio.sleep(0.5)
            if page.url != before:
                return page.url
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- task IPC
class TaskQueue:
    def __init__(self, base: Path):
        self.inbox, self.proc, self.done = base / "inbox", base / "processing", base / "completed"
        for d in (self.inbox, self.proc, self.done):
            d.mkdir(parents=True, exist_ok=True)

    def take(self, s: Session) -> dict | None:
        for f in sorted(self.inbox.glob("*.json")):
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            role_ok = t.get("role") and t["role"].lower() == s.role
            pat_ok = t.get("session_pattern") and re.search(t["session_pattern"], s.title, re.I)
            id_ok = t.get("session_id") == s.sid
            untargeted = not any(t.get(k) for k in ("role", "session_pattern", "session_id"))
            if role_ok or pat_ok or id_ok or untargeted:
                dest = self.proc / f.name
                try:
                    f.rename(dest)  # atomic claim across tabs
                except OSError:
                    continue
                t["_path"] = str(dest)
                t.setdefault("task_id", f.stem)
                return t
        return None

    def finish(self, t: dict, s: Session, reply: str) -> None:
        out = {k: v for k, v in t.items() if not k.startswith("_")}
        out.update(status="completed", session=s.title, role=s.role, output=reply,
                   completed_at=datetime.now().isoformat())
        (self.done / f"{t['task_id']}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        Path(t["_path"]).unlink(missing_ok=True)

    def release(self, t: dict) -> None:
        """Return a claimed task to the inbox (e.g. budget exhausted or send failed)."""
        src = Path(t["_path"])
        if src.exists():
            src.rename(self.inbox / src.name)


# ---------------------------------------------------------------- pacing / budget
class Pacer:
    """Human-like rhythm + hard budgets. Never retries while the remote side is busy."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.global_sent: deque[float] = deque()
        self.tab_sent: dict[str, deque[float]] = {}
        self.next_at: dict[str, float] = {}
        self.backoff: dict[str, float] = {}
        self.cooldown_until = 0.0

    def _gap(self) -> float:
        lo, hi = self.cfg.get("min_gap_minutes", 6), self.cfg.get("max_gap_minutes", 18)
        return random.uniform(lo, hi) * 60

    def quiet_now(self) -> bool:
        q = self.cfg.get("quiet_hours")
        if not q:
            return False
        h = datetime.now().hour
        a, b = q
        return a <= h < b if a < b else (h >= a or h < b)

    def may_send(self, sid: str, is_task: bool) -> tuple[bool, str]:
        now = time.time()
        for dq in (self.global_sent, *self.tab_sent.values()):
            while dq and now - dq[0] > 3600:
                dq.popleft()
        if now < self.cooldown_until:
            return False, f"rate-limit cooldown {int(self.cooldown_until - now)}s"
        if len(self.global_sent) >= self.cfg.get("max_messages_global_per_hour", 15):
            return False, "global hourly budget reached"
        if is_task:
            return True, ""
        if self.quiet_now():
            return False, "quiet hours"
        if len(self.tab_sent.get(sid, ())) >= self.cfg.get("max_nudges_per_tab_per_hour", 4):
            return False, "tab hourly budget reached"
        if now < self.next_at.get(sid, 0):
            return False, "waiting for jittered gap"
        return True, ""

    def record(self, sid: str, progressed: bool | None = None) -> None:
        now = time.time()
        self.global_sent.append(now)
        self.tab_sent.setdefault(sid, deque()).append(now)
        b = self.backoff.get(sid, 1.0)
        if progressed is False:
            b = min(b * 2, self.cfg.get("no_progress_backoff_max_minutes", 240) * 60 / self._gap())
        elif progressed:
            b = 1.0
        self.backoff[sid] = b
        self.next_at[sid] = now + self._gap() * b

    def park(self, sid: str, minutes: float) -> None:
        self.next_at[sid] = time.time() + minutes * 60

    def rate_limited(self) -> None:
        self.cooldown_until = time.time() + self.cfg.get("rate_limit_cooldown_minutes", 60) * 60


# ---------------------------------------------------------------- human-required guard
def _send_telegram(text: str) -> bool:
    """Send alert to Telegram using environment variables or .env."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("TELEGRAM_CHAT_ID=") or line.startswith("ADMIN_TELEGRAM_CHAT_ID="):
                    if not chat_id:
                        chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not (token and chat_id):
        return False
    try:
        import urllib.parse
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as exc:
        log(f"Telegram notification error: {exc}")
        return False


class Guard:
    """When any tab hits CAPTCHA / verification, ALL tabs pause until a human clears it."""

    def __init__(self, tasks_dir: Path):
        self.flag = tasks_dir / "HUMAN_ACTION_REQUIRED.json"
        self.blocked_by: str | None = None

    def block(self, s: Session, reason: str) -> None:
        if self.blocked_by:
            return
        self.blocked_by = s.title
        self.flag.write_text(json.dumps({"reason": reason, "session": s.title, "url": s.url,
                                         "since": datetime.now().isoformat()}, indent=2), encoding="utf-8")
        log(f"⚠ {reason} — ALL tabs paused. Solve it in the browser window; work resumes automatically.", s.title)
        
        # Native Telegram Alert
        _send_telegram(
            f"🚨 <b>SupremeAI Browser Alert</b>\n\n"
            f"<b>Issue:</b> {reason}\n"
            f"<b>Session:</b> <code>{s.title}</code>\n"
            f"<b>URL:</b> {s.url or 'N/A'}\n\n"
            f"<i>All browser tabs have been paused. Please solve the challenge in the browser window. Automation will resume automatically once cleared.</i>"
        )

        hook = os.environ.get("WEB_AGENT_NOTIFY_CMD")  # optional custom script hook
        if hook:
            try:
                subprocess.Popen(hook, shell=True, env={**os.environ, "WEB_AGENT_EVENT": reason, "WEB_AGENT_SESSION": s.title})
            except Exception:
                pass

    def clear(self, s: Session) -> None:
        if self.blocked_by == s.title:
            self.blocked_by = None
            self.flag.unlink(missing_ok=True)
            log("✓ human verification cleared — resuming all tabs", s.title)
            _send_telegram(
                f"✅ <b>SupremeAI Browser Alert</b>\n\n"
                f"Human verification cleared on <code>{s.title}</code>.\n"
                f"All browser tabs have resumed automation."
            )


# ---------------------------------------------------------------- prompt composer
class PromptComposer:
    """Context-aware, non-repeating follow-ups.

    Priority: external AI hook (WEB_AGENT_PROMPT_CMD: reads JSON on stdin, prints prompt)
           → follow-up built from the previous reply's next-steps / questions
           → varied role pool (never the same text twice in a row).
    """

    _ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.{8,140})$", re.M)
    _NEXT_RE = re.compile(r"(?:next(?: step)?s?|todo|remaining|should i|shall i|would you like)[^\n]{0,160}", re.I)

    def __init__(self, recipes: dict):
        self.roles = recipes.get("roles", {})
        self.templates = recipes.get("followup_templates", ["Go ahead with {item}"])
        self.done_re = [re.compile(p, re.I) for p in recipes.get("guards", {}).get("task_done_text", [])]
        self.history: dict[str, deque[str]] = {}

    def says_done(self, reply: str) -> bool:
        tail = reply[-1500:]
        return any(r.search(tail) for r in self.done_re)

    def _external(self, role: str, title: str, reply: str) -> str | None:
        cmd = os.environ.get("WEB_AGENT_PROMPT_CMD")
        if not cmd:
            return None
        try:
            r = subprocess.run(cmd, shell=True, input=json.dumps({"role": role, "session": title, "last_reply": reply[-6000:]}),
                               capture_output=True, text=True, timeout=90)
            out = r.stdout.strip()
            return out[:2000] if r.returncode == 0 and out else None
        except Exception:
            return None

    def compose(self, s: Session, last_reply: str) -> str:
        hist = self.history.setdefault(s.sid, deque(maxlen=6))
        msg = self._external(s.role, s.title, last_reply)
        if not msg and last_reply:
            tail = last_reply[-3000:]
            items = [m.strip().rstrip(".") for m in self._ITEM_RE.findall(tail)] + [m.strip() for m in self._NEXT_RE.findall(tail)]
            items = [i for i in items if not any(i[:40] in h for h in hist)]
            if items:
                item = items[-1] if random.random() < 0.6 else random.choice(items)
                msg = random.choice(self.templates).format(item=item[0].lower() + item[1:])
        if not msg:
            pool = self.roles.get(s.role, {}).get("prompts") or ["Please continue."]
            fresh = [p for p in pool if p not in hist] or pool
            msg = random.choice(fresh)
        hist.append(msg)
        return msg


# ---------------------------------------------------------------- tab loop
async def drive_tab(s: Session, eng: IntentEngine, q: TaskQueue, pacer: Pacer, guard: Guard,
                    composer: PromptComposer, stop: asyncio.Event, keep_alive: bool, stagger: float) -> None:
    page = s.page
    assert page is not None
    active: dict | None = None      # queued task awaiting reply
    nudged = False                  # keep-alive awaiting reply
    before_text, last_reply, last_note = "", "", ""
    log(f"attached (role={s.role}); first action in ~{int(stagger)}s", s.title)
    pacer.park(s.sid, random.uniform(1, pacer.cfg.get("min_gap_minutes", 6)))  # no instant burst on start
    await asyncio.sleep(stagger)
    while not stop.is_set():
        try:
            blocker = await eng.detect_blocker(page)
            if blocker == "human_verification":
                guard.block(s, "human verification required")
                await asyncio.sleep(20)
                continue
            guard.clear(s)
            if guard.blocked_by:            # another tab is blocked → stay silent
                await asyncio.sleep(20)
                continue
            if blocker == "rate_limit":
                pacer.rate_limited()
                log("rate-limit notice detected → global cooldown", s.title)

            if await eng.needs_login(page):
                log("login required → running saved 'login' process", s.title)
                if not await eng.run_recipe(page, "login"):
                    guard.block(s, "login could not complete automatically")
                continue

            if await eng.is_busy(page):     # remote is working → never resend
                if random.random() < 0.15:
                    await eng.idle_wander(page)
                await asyncio.sleep(random.uniform(4, 9))
                continue
            if not await eng.present(page, "message_input"):
                await asyncio.sleep(5)
                continue

            # ---- harvest the reply to whatever we last sent
            if active or nudged:
                after = await eng.snapshot_text(page)
                sent = active.get("prompt", "") if active else (composer.history.get(s.sid) or [""])[-1]
                last_reply = extract_reply(before_text, after, sent)
                progressed = len(last_reply) > 200
                if active:
                    q.finish(active, s, last_reply)
                    log(f"task {active['task_id']} completed ({len(last_reply)} chars)", s.title)
                    pacer.record(s.sid, progressed=True)
                    active = None
                else:
                    pacer.record(s.sid, progressed=progressed)
                    nudged = False
                    if composer.says_done(last_reply):
                        pacer.park(s.sid, 180)
                        log("agent reports work complete → parking tab for 3h (queued tasks still accepted)", s.title)
                continue

            # ---- queued task first
            task = q.take(s)
            if task:
                ok, why = pacer.may_send(s.sid, is_task=True)
                if not ok:
                    q.release(task)
                    if why != last_note:
                        log(f"task deferred: {why}", s.title)
                        last_note = why
                    await asyncio.sleep(30)
                    continue
                before_text = await eng.snapshot_text(page)
                if await eng.send_message(page, task.get("prompt", "")):
                    active = task
                    log(f"task {task['task_id']} dispatched", s.title)
                else:
                    q.release(task)
                await asyncio.sleep(random.uniform(5, 9))
                continue

            # ---- context-aware keep-alive, within budget
            if keep_alive:
                ok, why = pacer.may_send(s.sid, is_task=False)
                if ok:
                    msg = composer.compose(s, last_reply)
                    before_text = await eng.snapshot_text(page)
                    if await eng.send_message(page, msg):
                        nudged = True
                        log(f"follow-up sent: {msg[:70]!r}", s.title)
                    await asyncio.sleep(random.uniform(5, 9))
                    continue
                if why != last_note:
                    log(f"idle, not sending: {why}", s.title)
                    last_note = why
            if random.random() < 0.1:
                await eng.idle_wander(page)
        except Exception as exc:
            log(f"tab error: {exc}", s.title)
        await asyncio.sleep(random.uniform(8, 20))


# ---------------------------------------------------------------- main
async def run(args: argparse.Namespace) -> None:
    tasks_dir = Path(args.tasks_dir)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    site_cfg_path = tasks_dir / "site.json"
    site_cfg = json.loads(site_cfg_path.read_text(encoding="utf-8")) if site_cfg_path.exists() else {}
    start_url = args.url or os.environ.get("WEB_AGENT_START_URL") or site_cfg.get("start_url")
    if not start_url:
        sys.exit("start URL required: --url, WEB_AGENT_START_URL, or <tasks-dir>/site.json")
    max_tabs = args.max_tabs or site_cfg.get("max_tabs", 4)

    eng = IntentEngine(memory_path=tasks_dir / "intent_memory.json")
    roles_cfg = eng.recipes.get("roles", {})
    skip_re = re.compile(eng.recipes.get("session_skip_titles", "^$"), re.I)
    q = TaskQueue(tasks_dir)
    stop = asyncio.Event()
    pacer = Pacer(eng.recipes.get("pacing", {}))
    guard = Guard(tasks_dir)
    composer = PromptComposer(eng.recipes)

    async with async_playwright() as p:
        if args.cdp:  # most natural: attach to the user's own running Chrome
            browser = await p.chromium.connect_over_cdp(args.cdp)
            ctx: BrowserContext = browser.contexts[0] if browser.contexts else await browser.new_context()
        else:
            if args.headless:
                log("note: headless has a distinct fingerprint; prefer headed or --cdp")
            launch = dict(user_data_dir=args.profile_dir, headless=args.headless, no_viewport=True,
                          ignore_default_args=["--enable-automation"],
                          args=["--disable-blink-features=AutomationControlled", "--start-maximized"])
            try:  # real installed Chrome binary (genuine fingerprint) when available
                ctx = await p.chromium.launch_persistent_context(channel="chrome", **launch)
            except Exception:
                ctx = await p.chromium.launch_persistent_context(**launch)

        # --- discovery (passive network + DOM) ---
        sniffer = SessionSniffer()
        first = ctx.pages[0] if ctx.pages else await ctx.new_page()
        first.on("response", sniffer.on_response)
        await first.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)
        if await eng.needs_login(first):
            log("login required on start page → running saved 'login' process")
            await eng.run_recipe(first, "login")
            await first.goto(start_url, wait_until="domcontentloaded")
            await asyncio.sleep(8)
        first.remove_listener("response", sniffer.on_response)

        hrefs = await first.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)")
        origin = f"{urlparse(first.url).scheme}://{urlparse(first.url).netloc}"
        found = sniffer.sessions([first.url, start_url])
        ids = list(found)
        template = learn_template([first.url, start_url, *[h for h in hrefs if h.startswith(origin)]], ids)

        sessions: list[Session] = []
        for sid, meta in sorted(found.items(), key=lambda kv: -kv[1]["updated"]):
            if skip_re.match(meta["title"]) or (args.filter and not re.search(args.filter, meta["title"], re.I)):
                continue
            sessions.append(Session(sid=sid, title=meta["title"] or sid[:8], role=infer_role(meta["title"], roles_cfg),
                                    url=template.replace("{id}", sid) if template else None, updated=meta["updated"]))
        sessions = sessions[:max_tabs]
        if not sessions:
            log("no sessions discovered → driving start page as a single session")
            sessions = [Session(sid="start", title="start", role=next(iter(roles_cfg), "coder"), url=first.url)]

        log(f"discovered {len(sessions)} session(s); url-template={'learned' if template else 'none (click fallback)'}")
        for s in sessions:
            log(f"  role={s.role:<8} title={s.title}")

        # Optional: Sync browser session into BrowserSessionVault (Dual-Mode Compute Engine)
        if args.sync_vault:
            try:
                state = await ctx.storage_state()
                cookies = state.get("cookies", [])
                origins = state.get("origins", [])
                ls = {}
                for o in origins:
                    for item in o.get("localStorage", []):
                        ls[item["name"]] = item["value"]
                from core.browser_session_vault import BrowserSessionVault
                vpath = os.environ.get("BROWSER_VAULT_PATH", str(REPO_ROOT / ".browser_vault"))
                vault = BrowserSessionVault(vault_path=vpath)
                vault.save_session(args.sync_vault, cookies, ls)
                log(f"Synced {len(cookies)} cookies to session vault service: '{args.sync_vault}'")
            except Exception as v_err:
                log(f"Vault sync skipped/failed: {v_err}")

        # --- one tab per session ---
        for i, s in enumerate(sessions):
            s.page = first if i == 0 else await ctx.new_page()
            if s.url:
                await s.page.goto(s.url, wait_until="domcontentloaded", timeout=60000)
            else:
                s.url = await open_session_by_title(s.page, urljoin(origin, "/"), s.title)
            await asyncio.sleep(1.5)

        lo, hi = eng.recipes.get("pacing", {}).get("tab_start_stagger_seconds", [20, 120])
        coros = [drive_tab(s, eng, q, pacer, guard, composer, stop, not args.no_keep_alive,
                           stagger=0 if args.once else random.uniform(lo, hi) * i)
                 for i, s in enumerate(sessions) if s.page]
        if args.once:
            runner = asyncio.gather(*coros)
            await asyncio.sleep(args.once_seconds)
            stop.set()
            await runner
        else:
            await asyncio.gather(*coros)


# ---------------------------------------------------------------- episodic pulse mode
async def sweep_tab_pulse(
    s: Session,
    eng: IntentEngine,
    q: TaskQueue,
    pacer: Pacer,
    guard: Guard,
    composer: PromptComposer,
    keep_alive: bool,
) -> None:
    page = s.page
    if not page:
        return
    log(f"Pulse sweep starting (role={s.role})", s.title)
    try:
        blocker = await eng.detect_blocker(page)
        if blocker == "human_verification":
            guard.block(s, "human verification required")
            return
        guard.clear(s)
        if guard.blocked_by:
            return

        if await eng.is_busy(page):
            log("Remote agent is currently BUSY generating. Safe handshake intact.", s.title)
            return

        if not await eng.present(page, "message_input"):
            log("Message input not ready, skipping tab this pulse.", s.title)
            return

        after = await eng.snapshot_text(page)
        last_reply = after[-3000:]

        # Queued task first
        task = q.take(s)
        if task:
            ok, why = pacer.may_send(s.sid, is_task=True)
            if not ok:
                q.release(task)
                log(f"Queued task deferred: {why}", s.title)
                return
            sent = await eng.send_message(page, task.get("prompt", ""))
            if sent:
                log(f"Dispatched task {task['task_id']}. Waiting for safe handshake...", s.title)
                for _ in range(8):
                    await asyncio.sleep(1)
                    if await eng.is_busy(page):
                        log("Handshake confirmed (GENERATING). Safe to exit tab.", s.title)
                        break
                pacer.record(s.sid, progressed=True)
            else:
                q.release(task)
                log(f"Failed to dispatch task {task['task_id']}.", s.title)
            return

        # Autonomous keep-alive / follow-up
        if keep_alive:
            ok, why = pacer.may_send(s.sid, is_task=False)
            if ok:
                msg = composer.compose(s, last_reply)
                log(f"Sending pulse follow-up: {msg[:60]!r}", s.title)
                sent = await eng.send_message(page, msg)
                if sent:
                    log("Follow-up sent. Waiting for safe handshake...", s.title)
                    for _ in range(8):
                        await asyncio.sleep(1)
                        if await eng.is_busy(page):
                            log("Handshake confirmed (GENERATING). Safe to exit tab.", s.title)
                            break
                    pacer.record(s.sid, progressed=True)
            else:
                log(f"Tab idle: {why}", s.title)
    except Exception as exc:
        log(f"Pulse tab error: {exc}", s.title)


async def run_pulse_cycle(args: argparse.Namespace) -> None:
    tasks_dir = Path(args.tasks_dir)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    site_cfg_path = tasks_dir / "site.json"
    site_cfg = json.loads(site_cfg_path.read_text(encoding="utf-8")) if site_cfg_path.exists() else {}
    start_url = args.url or os.environ.get("WEB_AGENT_START_URL") or site_cfg.get("start_url")
    if not start_url:
        sys.exit("start URL required: --url, WEB_AGENT_START_URL, or <tasks-dir>/site.json")
    max_tabs = args.max_tabs or site_cfg.get("max_tabs", 4)

    eng = IntentEngine(memory_path=tasks_dir / "intent_memory.json")
    roles_cfg = eng.recipes.get("roles", {})
    skip_re = re.compile(eng.recipes.get("session_skip_titles", "^$"), re.I)
    q = TaskQueue(tasks_dir)
    pacer = Pacer(eng.recipes.get("pacing", {}))
    guard = Guard(tasks_dir)
    composer = PromptComposer(eng.recipes)

    pulse_min = args.pulse_min
    pulse_max = args.pulse_max
    cycle = 1

    while True:
        log("=" * 65)
        log(f"🚀 Pulse Cycle #{cycle}: Launching browser for active check & sweep...")
        log("=" * 65)

        async with async_playwright() as p:
            if args.cdp:
                browser = await p.chromium.connect_over_cdp(args.cdp)
                ctx: BrowserContext = browser.contexts[0] if browser.contexts else await browser.new_context()
            else:
                launch = dict(
                    user_data_dir=args.profile_dir,
                    headless=args.headless,
                    no_viewport=True,
                    ignore_default_args=["--enable-automation"],
                    args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
                )
                try:
                    ctx = await p.chromium.launch_persistent_context(channel="chrome", **launch)
                except Exception:
                    ctx = await p.chromium.launch_persistent_context(**launch)

            sniffer = SessionSniffer()
            first = ctx.pages[0] if ctx.pages else await ctx.new_page()
            first.on("response", sniffer.on_response)
            await first.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(8)
            first.remove_listener("response", sniffer.on_response)

            hrefs = await first.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)")
            origin = f"{urlparse(first.url).scheme}://{urlparse(first.url).netloc}"
            found = sniffer.sessions([first.url, start_url])
            ids = list(found)
            template = learn_template([first.url, start_url, *[h for h in hrefs if h.startswith(origin)]], ids)

            sessions: list[Session] = []
            for sid, meta in sorted(found.items(), key=lambda kv: -kv[1]["updated"]):
                if skip_re.match(meta["title"]) or (args.filter and not re.search(args.filter, meta["title"], re.I)):
                    continue
                sessions.append(Session(sid=sid, title=meta["title"] or sid[:8], role=infer_role(meta["title"], roles_cfg),
                                        url=template.replace("{id}", sid) if template else None, updated=meta["updated"]))
            sessions = sessions[:max_tabs]
            if not sessions:
                sessions = [Session(sid="start", title="start", role=next(iter(roles_cfg), "coder"), url=first.url)]

            log(f"Discovered {len(sessions)} session(s). Attaching tabs for pulse sweep...")
            for i, s in enumerate(sessions):
                s.page = first if i == 0 else await ctx.new_page()
                if s.url:
                    await s.page.goto(s.url, wait_until="domcontentloaded", timeout=60000)
                else:
                    s.url = await open_session_by_title(s.page, urljoin(origin, "/"), s.title)
                await asyncio.sleep(1.5)

            sweep_coros = [
                sweep_tab_pulse(s, eng, q, pacer, guard, composer, keep_alive=not args.no_keep_alive)
                for s in sessions if s.page
            ]
            await asyncio.gather(*sweep_coros)

            log("All tabs processed and handshakes verified. Closing browser context...")
            await ctx.close()

        gap_min = random.uniform(pulse_min, pulse_max)
        next_dt = datetime.fromtimestamp(time.time() + gap_min * 60).strftime("%H:%M:%S")
        log(f"💤 Pulse Cycle #{cycle} Complete. Browser closed. Sleeping {gap_min:.1f} mins (next at {next_dt})...")
        log("=" * 65)

        if args.once:
            break

        cycle += 1
        await asyncio.sleep(gap_min * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generic multi-tab web agent worker")
    ap.add_argument("--url", help="Start URL (else env WEB_AGENT_START_URL or <tasks-dir>/site.json)")
    ap.add_argument("--profile-dir", default=DEFAULT_PROFILE)
    ap.add_argument("--tasks-dir", default=DEFAULT_TASKS)
    ap.add_argument("--headless", action="store_true", help="Not recommended (distinct fingerprint)")
    ap.add_argument("--headed", action="store_true", help="(default; kept for compatibility)")
    ap.add_argument("--cdp", help="Attach to your own running Chrome, e.g. http://localhost:9222 (most natural)")
    ap.add_argument("--max-tabs", type=int, default=0)
    ap.add_argument("--filter", help="Regex on session titles")
    ap.add_argument("--sync-vault", default=None, help="Sync browser cookies/storage into BrowserSessionVault service")
    ap.add_argument("--no-keep-alive", action="store_true", help="Only run queued tasks")
    ap.add_argument("--once", action="store_true", help="Smoke test: run briefly then exit")
    ap.add_argument("--once-seconds", type=int, default=30)
    ap.add_argument("--pulse", action="store_true", help="Enable episodic pulse mode (sweep tabs, safe handshake, close browser, sleep)")
    ap.add_argument("--pulse-min", type=float, default=18.0, help="Min sleep minutes between pulses (default: 18)")
    ap.add_argument("--pulse-max", type=float, default=32.0, help="Max sleep minutes between pulses (default: 32)")

    args = ap.parse_args()
    try:
        if args.pulse:
            asyncio.run(run_pulse_cycle(args))
        else:
            asyncio.run(run(args))
    except KeyboardInterrupt:
        log("stopped by user")


if __name__ == "__main__":
    main()

