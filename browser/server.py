"""SupremeAI Browser - Lightweight Gemini Cookie Relay Engine (~20MB RAM, $0 Cost).

Connects directly to gemini.google.com session over HTTP using stored session cookies.
Zero Headless Browser overhead, zero Playwright memory bloat.
Runs seamlessly on Render Free Tier or local machine (port 8788). Refs #756.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("supremeai-cookie-relay")

app = FastAPI(title="SupremeAI Gemini Web Cookie Relay", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Stealth-Secret", "Accept", "Origin", "Referer"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = "gemini-web-relay"
    messages: List[ChatMessage] = []
    stream: Optional[bool] = False


class GeminiCookieEngine:
    def __init__(self) -> None:
        self._snl: Optional[str] = None
        self._bl: str = "boq_gemini-web-uiserver_20261022.00_p0"
        self._token_expiry: float = 0
        self._cookies: Dict[str, str] = {}
        self._infisical_cookies: Dict[str, str] = {}
        self._infisical_expiry: float = 0
        self._infisical_ttl: float = 3600.0
        self._proxy_list: List[str] = []
        self._proxy_idx: int = 0
        self._proxy_expiry: float = 0

    async def get_proxy(self) -> Optional[str]:
        direct_proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("ROTATING_PROXY_URL")
        if direct_proxy:
            return direct_proxy

        webshare_key = os.getenv("WEBSHARE_API_KEY")
        if not webshare_key:
            return None

        now = time.time()
        if not self._proxy_list or now > self._proxy_expiry:
            try:
                async with httpx.AsyncClient(timeout=10.0) as pc:
                    res = await pc.get(
                        "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=25",
                        headers={"Authorization": f"Token {webshare_key}"},
                    )
                    if res.status_code == 200:
                        data = res.json()
                        results = data.get("results", [])
                        proxies = []
                        for p in results:
                            u, pw, ip, port = p.get("username"), p.get("password"), p.get("proxy_address"), p.get("port")
                            if u and pw and ip and port:
                                proxies.append(f"http://{u}:{pw}@{ip}:{port}")
                        if proxies:
                            self._proxy_list = proxies
                            self._proxy_expiry = now + 3600.0
                            logger.info(f"Loaded {len(proxies)} Webshare rotating proxies")
            except Exception as e:
                logger.warning(f"Failed to fetch Webshare proxy list: {e}")

        if not self._proxy_list:
            return None

        proxy = self._proxy_list[self._proxy_idx % len(self._proxy_list)]
        self._proxy_idx += 1
        return proxy

    def get_cookies(self) -> Dict[str, str]:
        # Prefer Infisical cached cookies if fresh (TTL 1h)
        if self._infisical_cookies and time.time() < self._infisical_expiry:
            self._cookies = self._infisical_cookies
            return self._cookies

        if self._cookies:
            return self._cookies

        # 1. Environment variables
        c: Dict[str, str] = {}
        for key in ("1PSID", "3PSID", "SID", "1PSIDTS", "3PSIDTS", "1PSIDCC", "3PSIDCC"):
            val = os.environ.get(f"SUPREMEAI_GEMINI_{key}", "")
            if val:
                c[f"__Secure-{key}" if "PSID" in key else key] = val
        if c:
            self._cookies = c
            return self._cookies

        # 2. Local encrypted vault fallback (~/.supremeai_vault)
        try:
            vault_path = pathlib.Path.home() / ".supremeai_vault" / "ai_fleet_cookies.enc.json"
            if vault_path.exists():
                ghost_tower_dir = str(pathlib.Path(__file__).resolve().parent / "ghost_tower")
                if ghost_tower_dir not in sys.path:
                    sys.path.insert(0, ghost_tower_dir)
                from credential_vault import CredentialVault

                vault = CredentialVault()
                cookie_list = json.loads(vault.decrypt(vault_path.read_text("utf-8")))
                for cookie in cookie_list:
                    if "google" in cookie.get("domain", ""):
                        name = cookie.get("name")
                        if name in (
                            "__Secure-1PSID",
                            "__Secure-3PSID",
                            "SID",
                            "__Secure-1PSIDTS",
                            "__Secure-3PSIDTS",
                            "__Secure-1PSIDCC",
                            "__Secure-3PSIDCC",
                        ):
                            c[name] = cookie.get("value")
                self._cookies = c
        except Exception as exc:
            logger.warning(f"Could not read cookies from local vault: {exc}")

        return self._cookies

    async def fetch_cookies_from_infisical(self) -> Dict[str, str]:
        """Dynamically fetch Gemini cookies from Infisical Vault (in-memory, TTL 1h)."""
        now = time.time()
        if self._infisical_cookies and now < self._infisical_expiry:
            self._cookies = self._infisical_cookies
            return self._infisical_cookies

        client_id = os.getenv("INFISICAL_CLIENT_ID", "").strip()
        client_secret = os.getenv("INFISICAL_CLIENT_SECRET", "").strip()
        workspace_id = (os.getenv("INFISICAL_WORKSPACE_ID", "") or os.getenv("INFISICAL_PROJECT_ID", "")).strip()
        if not client_id or not client_secret or not workspace_id:
            return self.get_cookies()

        environment = os.getenv("INFISICAL_ENV", "prod").strip() or "prod"
        base_url = os.getenv("INFISICAL_API_URL", "https://app.infisical.com").rstrip("/")
        secret_name = os.getenv("INFISICAL_GEMINI_COOKIES_SECRET", "SUPREMEAI_GEMINI_COOKIES").strip() or "SUPREMEAI_GEMINI_COOKIES"

        old_cookies = dict(self._infisical_cookies)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                login_resp = await client.post(
                    f"{base_url}/api/v1/auth/universal-auth/login",
                    json={"clientId": client_id, "clientSecret": client_secret},
                )
                login_resp.raise_for_status()
                token = login_resp.json().get("accessToken")
                if not token:
                    raise ValueError("Infisical auth did not return accessToken")

                url = f"{base_url}/api/v3/secrets/raw/{secret_name}"
                params = {"workspaceId": workspace_id, "environment": environment, "secretPath": "/"}
                resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
                resp.raise_for_status()
                data = resp.json()

                raw_value = None
                if isinstance(data, dict):
                    if isinstance(data.get("secret"), dict):
                        raw_value = data["secret"].get("secretValue")
                    elif isinstance(data.get("secrets"), list) and data["secrets"]:
                        raw_value = data["secrets"][0].get("secretValue")
                    else:
                        raw_value = data.get("secretValue")
                if not raw_value:
                    raise ValueError("Infisical secret value is empty")

                cookies = self._parse_infisical_cookie_value(str(raw_value))
                if not cookies:
                    raise ValueError("No Gemini cookies parsed from Infisical secret")

                # Reset token cache if cookies changed
                if cookies != old_cookies:
                    self._snl = None
                    self._token_expiry = 0

                self._infisical_cookies = cookies
                self._infisical_expiry = time.time() + self._infisical_ttl
                self._cookies = cookies
                logger.info(f"Fetched {len(cookies)} Gemini cookies from Infisical (TTL {int(self._infisical_ttl)}s)")
                return cookies
        except Exception as exc:
            logger.warning(f"Could not fetch cookies from Infisical: {exc}")
            return self.get_cookies()

    def _parse_infisical_cookie_value(self, raw: str) -> Dict[str, str]:
        text = raw.strip()
        # Try gzip/base64 compressed payload
        try:
            decoded = base64.b64decode(text, validate=True)
            try:
                text = gzip.decompress(decoded).decode("utf-8")
            except Exception:
                try:
                    text = decoded.decode("utf-8")
                except Exception:
                    pass
        except Exception:
            pass

        # Try JSON
        try:
            data = json.loads(text)
        except Exception:
            cookies: Dict[str, str] = {}
            for part in text.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookies[k.strip()] = v.strip()
            known = {"__Secure-1PSID", "__Secure-3PSID", "SID", "__Secure-1PSIDTS", "__Secure-3PSIDTS", "__Secure-1PSIDCC", "__Secure-3PSIDCC"}
            filtered = {k: v for k, v in cookies.items() if k in known}
            return filtered if filtered else cookies

        cookies = {}
        if isinstance(data, dict):
            if isinstance(data.get("cookies"), list):
                data = data["cookies"]
            else:
                mapping: Dict[str, str] = {}
                for k, v in data.items():
                    if isinstance(v, str):
                        mapping[k] = v
                if mapping:
                    normalized: Dict[str, str] = {}
                    for k, v in mapping.items():
                        name = k
                        if k in ("1PSID", "3PSID", "SID", "1PSIDTS", "3PSIDTS", "1PSIDCC", "3PSIDCC"):
                            name = f"__Secure-{k}" if "PSID" in k else k
                        normalized[name] = v
                    return normalized
        if isinstance(data, list):
            for cookie in data:
                if not isinstance(cookie, dict):
                    continue
                name = cookie.get("name")
                value = cookie.get("value")
                domain = str(cookie.get("domain", ""))
                if name and value and ("google" in domain.lower() or str(name).startswith("__Secure-") or name == "SID"):
                    cookies[str(name)] = str(value)

        known = {"__Secure-1PSID", "__Secure-3PSID", "SID", "__Secure-1PSIDTS", "__Secure-3PSIDTS", "__Secure-1PSIDCC", "__Secure-3PSIDCC"}
        filtered = {k: v for k, v in cookies.items() if k in known}
        return filtered if filtered else cookies

    async def _ensure_tokens(self, client: httpx.AsyncClient) -> tuple[str, str]:
        now = time.time()
        if self._snl and now < self._token_expiry:
            return self._snl, self._bl

        if os.getenv("INFISICAL_CLIENT_ID") and os.getenv("INFISICAL_CLIENT_SECRET"):
            cookies = await self.fetch_cookies_from_infisical()
        else:
            cookies = self.get_cookies()
        if not cookies:
            raise ValueError("No Gemini cookies configured (missing env vars and local vault)")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = await client.get(
            "https://gemini.google.com/app", headers=headers, cookies=cookies, follow_redirects=True
        )
        if "accounts.google.com" in str(resp.url):
            raise PermissionError("Gemini cookies expired or redirected to Google Login")

        snl_match = re.search(r'"SNlM0e":"([^"]+)"', resp.text)
        if not snl_match:
            raise RuntimeError("Could not find SNlM0e session token on gemini.google.com/app")

        self._snl = snl_match.group(1)
        bl_match = re.search(r'"cfb2h":"([^"]+)"', resp.text)
        if bl_match:
            self._bl = bl_match.group(1)
        self._token_expiry = now + 3600  # Cache token for 1 hour
        logger.info(f"Refreshed Gemini SNlM0e session token (bl={self._bl})")
        return self._snl, self._bl

    def _extract_reply_text(self, raw_text: str) -> str:
        best_text = ""
        lines = raw_text.splitlines()
        for line in lines:
            line_s = line.strip()
            if not line_s or line_s == ")]}'" or line_s.isdigit():
                continue
            try:
                data = json.loads(line_s)
                for item in data:
                    if isinstance(item, list) and len(item) > 2 and item[0] == "wrb.fr":
                        payload = json.loads(item[2])
                        if len(payload) > 4 and payload[4]:
                            cand0 = payload[4][0]
                            if len(cand0) > 1 and cand0[1]:
                                part0 = cand0[1][0]
                                if isinstance(part0, str) and len(part0) > len(best_text):
                                    best_text = part0
            except Exception:
                continue
        return best_text.strip()

    async def ask(self, prompt: str) -> str:
        if os.getenv("INFISICAL_CLIENT_ID") and os.getenv("INFISICAL_CLIENT_SECRET"):
            cookies = await self.fetch_cookies_from_infisical()
        else:
            cookies = self.get_cookies()
        if not cookies:
            raise HTTPException(status_code=503, detail="No Gemini cookies configured")

        proxy = await self.get_proxy()
        client_kwargs = {"timeout": 45.0}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                snl, bl = await self._ensure_tokens(client)
            except PermissionError as exc:
                self._infisical_cookies = {}
                self._infisical_expiry = 0
                self._cookies = {}
                fallback_reply = await self._try_api_fallback(prompt)
                if fallback_reply:
                    return fallback_reply
                raise HTTPException(status_code=502, detail=str(exc))
            except Exception as exc:
                fallback_reply = await self._try_api_fallback(prompt)
                if fallback_reply:
                    return fallback_reply
                raise HTTPException(status_code=502, detail=f"Token initialization error: {exc}")

            reqid = int(time.time() * 1000) % 1000000
            post_url = (
                f"https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
                f"?bl={bl}&_reqid={reqid}&rt=c"
            )

            message_struct = [
                [prompt, 0, None, None, None, None, 0],
                ["en"],
                ["", "", ""],
                None,
                None,
                None,
                [1],
                0,
                [],
                [],
                1,
                0,
            ]
            req_payload = [None, json.dumps(message_struct)]
            post_headers = {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": "https://gemini.google.com",
                "Referer": "https://gemini.google.com/app",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            post_data = {
                "f.req": json.dumps(req_payload),
                "at": snl,
            }

            try:
                resp = await client.post(post_url, headers=post_headers, cookies=cookies, data=post_data)
            except httpx.HTTPError as exc:
                fallback_reply = await self._try_api_fallback(prompt)
                if fallback_reply:
                    return fallback_reply
                raise HTTPException(status_code=502, detail=f"Gemini upstream error: {exc}")

            if resp.status_code != 200:
                fallback_reply = await self._try_api_fallback(prompt)
                if fallback_reply:
                    return fallback_reply
                raise HTTPException(status_code=502, detail=f"Gemini returned HTTP {resp.status_code}")

            reply = self._extract_reply_text(resp.text)
            if not reply:
                fallback_reply = await self._try_api_fallback(prompt)
                if fallback_reply:
                    return fallback_reply
                raise HTTPException(status_code=502, detail="Failed to extract chat text from Gemini stream")
            return reply

    async def _try_api_fallback(self, prompt: str) -> Optional[str]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return None
        logger.info("Attempting Gemini API Key fallback response...")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    cands = data.get("candidates", [])
                    if cands and "content" in cands[0]:
                        parts = cands[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            text = parts[0]["text"].strip()
                            logger.info(f"Gemini API fallback succeeded ({len(text)} chars)")
                            return text
        except Exception as exc:
            logger.warning(f"Gemini API fallback error: {exc}")
        return None


relay_engine = GeminiCookieEngine()


class DuckAiEngine:
    """Duck.ai (DuckDuckGo AI Chat) headless & API relay ($0 cost, no account cookies required).

    Duck.ai supports models including:
    - gpt-4o-mini
    - claude-3-haiku-20240307
    - meta-llama/Llama-3.3-70B-Instruct-Turbo
    - mistralai/Mixtral-8x7B-Instruct-v0.1
    """

    MODEL_ALIASES: Dict[str, str] = {
        "duck": "gpt-4o-mini",
        "duck-ai": "gpt-4o-mini",
        "duck-gpt": "gpt-4o-mini",
        "duck-gpt-4o-mini": "gpt-4o-mini",
        "duck-claude": "claude-3-haiku-20240307",
        "duck-claude-haiku": "claude-3-haiku-20240307",
        "duck-llama": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "duck-llama-70b": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "duck-mixtral": "mistralai/Mixtral-8x7B-Instruct-v0.1",
    }

    def __init__(self) -> None:
        self._vqd_token: Optional[str] = None
        self._vqd_expiry: float = 0.0

    def resolve_model(self, model_name: Optional[str]) -> str:
        if not model_name:
            return "gpt-4o-mini"
        cleaned = model_name.strip().lower()
        return self.MODEL_ALIASES.get(cleaned, cleaned if "gpt-" in cleaned or "claude-" in cleaned or "llama" in cleaned or "mixtral" in cleaned else "gpt-4o-mini")

    async def _fetch_vqd_token(self, client: httpx.AsyncClient) -> Optional[str]:
        """Fetch fresh vqd session token from duckduckgo status endpoint."""
        now = time.time()
        if self._vqd_token and now < self._vqd_expiry:
            return self._vqd_token

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "x-vqd-accept": "1",
            "Referer": "https://duck.ai/",
            "Origin": "https://duck.ai",
        }
        try:
            resp = await client.get("https://duckduckgo.com/duckchat/v1/status", headers=headers)
            token = resp.headers.get("x-vqd-4")
            if token:
                self._vqd_token = token
                self._vqd_expiry = now + 600.0  # 10 min cache
                return token
        except Exception as exc:
            logger.warning(f"[DuckAI] Failed to fetch vqd token via HTTP: {exc}")

        return None

    async def ask(self, prompt: str, model: Optional[str] = None) -> str:
        """Query duck.ai directly. First tries lightweight HTTP with token, then falls back gracefully."""
        target_model = self.resolve_model(model)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Referer": "https://duck.ai/",
            "Origin": "https://duck.ai",
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            token = await self._fetch_vqd_token(client)
            if token:
                headers["x-vqd-4"] = token
                payload = {
                    "model": target_model,
                    "messages": [{"role": "user", "content": prompt}],
                }
                try:
                    resp = await client.post("https://duckduckgo.com/duckchat/v1/chat", headers=headers, json=payload)
                    if resp.status_code == 200:
                        # Update token if renewed
                        new_token = resp.headers.get("x-vqd-4")
                        if new_token:
                            self._vqd_token = new_token
                            self._vqd_expiry = time.time() + 600.0
                        # Parse SSE stream text
                        reply_parts: list[str] = []
                        for line in resp.text.split("\n"):
                            line = line.strip()
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    parsed = json.loads(data_str)
                                    msg = parsed.get("message")
                                    if msg:
                                        reply_parts.append(msg)
                                except Exception:
                                    continue
                        if reply_parts:
                            return "".join(reply_parts)
                    else:
                        logger.warning(f"[DuckAI] HTTP chat returned status {resp.status_code}")
                except Exception as exc:
                    logger.warning(f"[DuckAI] HTTP chat request failed: {exc}")

        # If HTTP direct mode was blocked by bot check or challenge, try headless browser execution
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
                context = await browser.new_context(
                    user_agent=headers["User-Agent"]
                )
                page = await context.new_page()
                await page.goto("https://duck.ai/chat", wait_until="networkidle")
                await page.wait_for_timeout(1000)
                ta = page.locator("textarea")
                if await ta.count() > 0:
                    await ta.fill(prompt)
                    ask = page.get_by_role("button", name="Ask")
                    if await ask.count() > 0:
                        await ask.first.click()
                    else:
                        await page.keyboard.press("Enter")
                    await page.wait_for_timeout(4000)
                    text = await page.evaluate("() => document.body.innerText")
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    await browser.close()
                    if lines:
                        return lines[-1]
                await browser.close()
        except Exception as exc:
            logger.warning(f"[DuckAI] Playwright fallback failed: {exc}")

        raise HTTPException(status_code=502, detail="Duck.ai upstream challenge or rate-limit encountered")


duck_engine = DuckAiEngine()


@app.on_event("startup")
async def on_startup():
    if os.getenv("INFISICAL_CLIENT_ID") and os.getenv("INFISICAL_CLIENT_SECRET"):
        logger.info("Initializing Infisical cookie prefetch on startup...")
        try:
            await relay_engine.fetch_cookies_from_infisical()
        except Exception as exc:
            logger.warning(f"Startup Infisical prefetch notice: {exc}")


@app.get("/health")
async def health() -> Dict[str, Any]:
    cookies = relay_engine._infisical_cookies or relay_engine.get_cookies()
    service_name = os.getenv("SERVICE_NAME", "supremeai-scraper")
    max_concurrency = int(os.getenv("SCRAPER_MAX_CONCURRENCY", "3"))
    return {
        "status": "healthy",
        "service": service_name,
        "browser_service": "supremeai-browser-cookie-relay",
        "playwright_available": True,
        "max_concurrency": max_concurrency,
        "cookies_loaded": bool(cookies),
        "total_cookies": len(cookies),
        "infisical_configured": bool(os.getenv("INFISICAL_CLIENT_ID") and os.getenv("INFISICAL_CLIENT_SECRET")),
        "timestamp": time.time(),
    }


def _verify_stealth_secret(request: Request) -> None:
    expected = os.getenv("STEALTH_WEBHOOK_SECRET", "").strip()
    if not expected:
        return
    incoming = (
        request.headers.get("X-Stealth-Secret")
        or request.headers.get("X-Webhook-Secret")
        or request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    )
    if incoming != expected:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing stealth secret")


@app.post("/api/chat")
async def api_chat(request: Request) -> Dict[str, Any]:
    _verify_stealth_secret(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    prompt = body.get("message") or body.get("prompt") or ""
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Empty prompt or message")

    model = str(body.get("model") or "").strip().lower()
    source = "gemini.google.com (Cookie Relay)"

    if "duck" in model:
        reply = await duck_engine.ask(prompt.strip(), model=model)
        source = f"duck.ai ({duck_engine.resolve_model(model)})"
    else:
        try:
            reply = await relay_engine.ask(prompt.strip())
        except Exception as exc:
            logger.warning(f"Gemini relay failed ({exc}); attempting Duck.ai fallback...")
            try:
                reply = await duck_engine.ask(prompt.strip(), model="gpt-4o-mini")
                source = "duck.ai (gpt-4o-mini fallback)"
            except Exception:
                raise exc

    return {
        "reply": reply,
        "source": source,
        "cost": "$0.00",
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, request: Request) -> JSONResponse:
    _verify_stealth_secret(request)
    prompt = "\n".join(m.content for m in req.messages if m.role == "user")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Missing user message in payload")

    req_model = str(req.model or "gemini-web").strip().lower()
    served_model = "gemini-web"
    engine_code = "ge"
    engine_label = "SupremeAI w.ge Turbo"

    if "duck" in req_model:
        duck_target = duck_engine.resolve_model(req_model)
        reply = await duck_engine.ask(prompt.strip(), model=req_model)
        served_model = f"duck-{duck_target}"
        engine_code = "dk"
        engine_label = f"SupremeAI w.dk ({duck_target})"
    else:
        try:
            reply = await relay_engine.ask(prompt.strip())
        except Exception as exc:
            logger.warning(f"Gemini relay failed ({exc}); falling back to Duck.ai...")
            try:
                reply = await duck_engine.ask(prompt.strip(), model="gpt-4o-mini")
                served_model = "duck-gpt-4o-mini"
                engine_code = "dk"
                engine_label = "SupremeAI w.dk (gpt-4o-mini)"
            except Exception:
                raise exc

    return JSONResponse(
        {
            "id": "chatcmpl-stealth-relay-" + os.urandom(6).hex(),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": served_model,
            "supremeai_engine": engine_code,
            "supremeai": {
                "channel": "w",
                "engine": engine_code,
                "tier": "Turbo",
                "label": engine_label,
            },
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    )



if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8788"))
    logger.info(f"Starting SupremeAI Gemini Cookie Relay on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
