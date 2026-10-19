"""
ghost_bridge_server.py — SupremeAI Ghost Tower Live Gemini Web Scraper ($0 Priority-1 Engine)
=============================================================================================
Controls a persistent Google Chrome session logged into gemini.google.com.
Enables real-time website chat responses directly from gemini.google.com with ZERO API keys & ZERO API costs.
Includes a built-in modern Web Chat interface at http://localhost:8788/
"""

from __future__ import annotations

import logging
import os
import sys
import time

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from .gemini_web_engine import GeminiWebEngine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ghost_tower.bridge")

app = FastAPI(title="SupremeAI Ghost Tower Live Gemini Web Scraper", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Gemini Web Engine (headless=False so user can see and log in once if needed)
engine = GeminiWebEngine(headless=False)


@app.on_event("startup")
async def on_startup():
    logger.info("Initializing Live Gemini Web Scraper Engine on startup...")
    # Initialize in background so server boots immediately
    import asyncio

    asyncio.create_task(engine.initialize())


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down Gemini Web Engine...")
    await engine.close()


@app.get("/health")
async def health():
    status = (
        await engine.check_login_status()
        if engine._is_ready
        else {"status": "initializing"}
    )
    return {
        "service": "SupremeAI Ghost Tower Live Gemini Web Scraper",
        "engine": "gemini.google.com ($0 Web Scraping)",
        "api_cost": "$0.00 (Zero API Key)",
        "ready": engine._is_ready,
        "details": status,
        "timestamp": time.time(),
    }


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """Direct Web Chat API endpoint for website chat widgets."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    message = body.get("message") or body.get("prompt") or ""
    if not message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    logger.info(f"Incoming web chat prompt: {message[:80]}...")
    reply = await engine.ask(message)
    return {"reply": reply, "source": "gemini.google.com (Web Relay)", "cost": "$0.00"}


@app.post("/v1/chat/completions")
@app.post("/v1/generate")
async def completions_endpoint(request: Request):
    """OpenAI-compatible format for existing gateway or external frontend clients."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    prompt = body.get("prompt", "")
    if not prompt and "messages" in body:
        messages = body.get("messages", [])
        for m in reversed(messages):
            if m.get("role") == "user":
                prompt = m.get("content", "")
                break

    if not prompt:
        raise HTTPException(status_code=400, detail="No prompt found in payload")

    reply = await engine.ask(prompt)

    return {
        "id": "chatcmpl-gemini-web-" + os.urandom(6).hex(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gemini.google.com-live-web",
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


@app.get("/", response_class=HTMLResponse)
@app.get("/web", response_class=HTMLResponse)
async def web_chat_page():
    """Serves a modern, real-time glassmorphism chat UI for direct website testing."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SupremeAI Ghost Tower — Live Gemini Web Chat ($0)</title>
  <style>
    :root {
      --bg: #090a0f;
      --card: rgba(18, 22, 34, 0.75);
      --border: rgba(255, 255, 255, 0.1);
      --accent: #2563eb;
      --accent-glow: #3b82f6;
      --text: #f3f4f6;
      --text-dim: #9ca3af;
      --gemini-bubble: rgba(30, 41, 59, 0.7);
      --user-bubble: #1d4ed8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body {
      background: radial-gradient(circle at 50% 10%, #1e1b4b, var(--bg) 80%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .chat-container {
      width: 100%;
      max-width: 820px;
      height: 85vh;
      background: var(--card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 20px;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
      overflow: hidden;
    }
    .chat-header {
      padding: 16px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(255, 255, 255, 0.02);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-logo {
      width: 38px; height: 38px; border-radius: 10px;
      background: linear-gradient(135deg, #3b82f6, #9333ea);
      display: flex; align-items: center; justify-content: center;
      font-weight: bold; font-size: 18px; color: white;
    }
    .brand-title { font-size: 16px; font-weight: 600; }
    .badge {
      font-size: 12px; padding: 4px 10px; border-radius: 20px;
      background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3);
      display: flex; align-items: center; gap: 6px;
    }
    .badge-dot { width: 8px; height: 8px; border-radius: 50%; background: #4ade80; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { opacity: 0.4; } 50% { opacity: 1; } 100% { opacity: 0.4; } }
    .messages-area {
      flex: 1;
      padding: 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .msg {
      max-width: 80%;
      padding: 14px 18px;
      border-radius: 16px;
      line-height: 1.5;
      font-size: 15px;
      word-break: break-word;
      animation: fadeIn 0.25s ease-out;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    .msg-user {
      align-self: flex-end;
      background: var(--user-bubble);
      color: white;
      border-bottom-right-radius: 4px;
    }
    .msg-bot {
      align-self: flex-start;
      background: var(--gemini-bubble);
      border: 1px solid var(--border);
      border-bottom-left-radius: 4px;
    }
    .msg-bot pre {
      background: rgba(0, 0, 0, 0.4); padding: 10px; border-radius: 8px; overflow-x: auto; margin-top: 8px;
    }
    .input-bar {
      padding: 16px 20px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 12px;
      background: rgba(0, 0, 0, 0.2);
    }
    .chat-input {
      flex: 1;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 18px;
      color: white;
      font-size: 15px;
      outline: none;
      transition: border 0.2s;
    }
    .chat-input:focus { border-color: var(--accent-glow); }
    .send-btn {
      background: linear-gradient(135deg, #2563eb, #3b82f6);
      color: white;
      border: none;
      border-radius: 12px;
      padding: 0 24px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: opacity 0.2s, transform 0.1s;
    }
    .send-btn:hover { opacity: 0.95; }
    .send-btn:active { transform: scale(0.98); }
    .send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .status-text { font-size: 12px; color: var(--text-dim); text-align: center; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="chat-container">
    <div class="chat-header">
      <div class="brand">
        <div class="brand-logo">G</div>
        <div>
          <div class="brand-title">SupremeAI Web Chat</div>
          <div style="font-size: 12px; color: var(--text-dim);">Live gemini.google.com Relay (Zero API Cost)</div>
        </div>
      </div>
      <div class="badge">
        <div class="badge-dot"></div>
        <span>Ghost Tower Active ($0)</span>
      </div>
    </div>

    <div class="messages-area" id="messagesArea">
      <div class="msg msg-bot">
        👋 হ্যালো! এটি সরাসরি <b>gemini.google.com</b> ব্রাউজার স্ক্র্যাপার দিয়ে যুক্ত। কোনো API Key ছাড়াই আপনার যেকোনো প্রশ্ন এখানে টাইপ করুন, সরাসরি উত্তর পাবেন!
      </div>
    </div>

    <form class="input-bar" id="chatForm">
      <input type="text" id="userInput" class="chat-input" placeholder="Type your message here..." autocomplete="off" required>
      <button type="submit" id="sendBtn" class="send-btn">Send ➔</button>
    </form>
    <div class="status-text" id="statusIndicator">Engine: gemini.google.com live browser relay</div>
  </div>

  <script>
    const form = document.getElementById('chatForm');
    const input = document.getElementById('userInput');
    const btn = document.getElementById('sendBtn');
    const messages = document.getElementById('messagesArea');
    const statusText = document.getElementById('statusIndicator');

    function appendMessage(text, isUser = false) {
      const msg = document.createElement('div');
      msg.className = 'msg ' + (isUser ? 'msg-user' : 'msg-bot');
      msg.innerHTML = text.replace(/\\n/g, '<br>');
      messages.appendChild(msg);
      messages.scrollTop = messages.scrollHeight;
      return msg;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;

      appendMessage(text, true);
      input.value = '';
      input.disabled = true;
      btn.disabled = true;
      statusText.innerText = "⏳ Gemini ব্রাউজারে টাইপ হচ্ছে ও উত্তর জেনারেট হচ্ছে...";

      const botBubble = appendMessage("<i>Gemini ভাবছে...</i>", false);

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        botBubble.innerHTML = (data.reply || "No reply").replace(/\\n/g, '<br>');
        statusText.innerText = "✅ সম্পন্ন (Source: " + (data.source || 'gemini.google.com') + " | " + data.cost + ")";
      } catch (err) {
        botBubble.innerHTML = "⚠️ ত্রুটি: " + err.message;
        statusText.innerText = "❌ কানেকশন এরর";
      } finally {
        input.disabled = false;
        btn.disabled = false;
        input.focus();
      }
    });
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    port = int(os.getenv("GHOST_PORT", "8788"))
    logger.info(
        f"Starting SupremeAI Ghost Tower Live Gemini Web Server on port {port}..."
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
