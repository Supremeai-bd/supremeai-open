"""Web Session AI Client CLI (Track A Zero-Cost Agent Compute).

বাংলা সারসংক্ষেপ:
------------------
SupremeAI এজেন্টদের জন্য ব্রাউজার কুকি ও সেশনভিত্তিক জিরো-কস্ট AI ক্লায়েন্ট CLI।
এটি ক্যামোফ্লেজ সেশন ইন্টারফেস ব্যবহার করে অপ্টিমাইজড ইনফারেন্স চালাতে পারে।

ব্যবহার:
  python scripts/agents/web_session_client.py --service core-architect --prompt "সফটওয়্যার আর্কিটেকচার রিভিউ"
  python scripts/agents/web_session_client.py --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# প্রোজেক্ট রুট পাথ অ্যাড
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

async def main_async() -> int:
    # বাংলা মন্তব্য: উইন্ডোজ কনসোলে বাংলা বা ইউনিকোড প্রিন্ট ক্র্যাশ এড়াতে UTF-8 এনকোডিং নিশ্চিতকরণ
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="SupremeAI Web Session AI Client")
    parser.add_argument(
        "--service",
        choices=["core-architect", "core-logic", "core-design", "core-speed", "architect", "logic", "design", "speed"],
        default="core-architect",
        help="Target web session AI service (core-architect, core-logic, core-design, core-speed)",
    )
    parser.add_argument("--prompt", type=str, help="Prompt to send to AI")
    parser.add_argument("--system", type=str, default=None, help="System prompt")
    parser.add_argument("--token", type=str, default=None, help="Direct session token / cookie string")
    parser.add_argument(
        "--vault-path",
        type=str,
        default=os.getenv("BROWSER_VAULT_PATH", str(REPO_ROOT / ".browser_vault")),
        help="Path to encrypted browser session vault",
    )
    parser.add_argument("--status", action="store_true", help="Check session health & vault status")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Silently refresh all active sessions using local IP and update vault",
    )
    parser.add_argument(
        "--boot-sync",
        action="store_true",
        help="Run silent session refresh after 5-min natural delay on PC boot (Anti-Spike Delay)",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Delay in seconds before initiating refresh (default: 0, or ~300s with --boot-sync)",
    )
    parser.add_argument(
        "--relay-server",
        action="store_true",
        help="Run local residential IP relay server for Cloud/Render bridge",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for local relay server (default: 8765)",
    )
    parser.add_argument(
        "--parallel-tasks",
        type=str,
        help="JSON string or file path containing multiple tasks to execute simultaneously across multiple AIs",
    )

    args = parser.parse_args()

    from core.web_ai_session_bridge import WebAISessionBridge, WebAISessionError

    # বাংলা মন্তব্য: ব্রিজ ও পুল ইনস্ট্যান্স তৈরি
    bridge = WebAISessionBridge(vault_path=args.vault_path)

    # বাংলা মন্তব্য: বুট সিঙ্ক ডিলে নির্ধারণ (৫ মিনিট / ৩০০ সেকেন্ড, স্বাভাবিক মানুষের মতো জ্যাম এড়াতে)
    delay_sec = args.delay
    if args.boot_sync and delay_sec == 0:
        import random
        # ২৭০ থেকে ৩৩০ সেকেন্ডের মধ্যে স্বাভাবিক মানুষের অ্যাক্টিভিটি জিম্যাপিং
        delay_sec = random.randint(270, 330)

    from core.web_ai_session_bridge import WebAISessionPool
    pool = WebAISessionPool(bridge=bridge)

    async def _execute_silent_refresh(delay: int) -> dict:
        if delay > 0:
            print(f"⏳ [Boot Sync] Waiting {delay}s (~{round(delay/60, 1)}m) for network stabilization & human realism...")
            await asyncio.sleep(delay)
        print("🔄 [Local PC Boot] Initiating silent session refresh with residential IP...")
        res = await pool.refresh_pool_sessions()
        print(f"✅ [Local PC Boot] Refresh Summary: {json.dumps(res, indent=2, ensure_ascii=False)}")
        return res

    # বাংলা মন্তব্য: লোকাল পিসি অন হলে বা --refresh/--boot-sync দিলে সাইলেন্ট রিফ্রেশ এক্সিকিউট করা
    if (args.refresh or args.boot_sync) and not args.relay_server:
        await _execute_silent_refresh(delay_sec)
        return 0

    # বাংলা মন্তব্য: একই সাথে একাধিক AI সেশনে মাল্টি-টাস্ক সমান্তরালে (Parallel) এক্সিকিউট করা
    if args.parallel_tasks:
        raw_val = args.parallel_tasks.strip()
        tasks_list = []
        if os.path.isfile(raw_val):
            tasks_list = json.loads(Path(raw_val).read_text(encoding="utf-8"))
        else:
            tasks_list = json.loads(raw_val)

        if not isinstance(tasks_list, list):
            print("Error: --parallel-tasks must be a JSON array of task objects.", file=sys.stderr)
            return 1

        print(f"🚀 [Multi-Session Parallel AI] Dispatching {len(tasks_list)} tasks simultaneously across multiple AIs...")
        batch_outcomes = await pool.execute_parallel_tasks(tasks_list)
        print(json.dumps(batch_outcomes, indent=2, ensure_ascii=False))
        return 0

    # বাংলা মন্তব্য: রিলে সার্ভার ডেমন মোড (Cloud vs Local IP গ্যাপ বাইপাস)
    if args.relay_server:
        import uvicorn
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        relay_app = FastAPI(title="SupremeAI Local Session Relay")
        bridge = WebAISessionBridge(vault_path=args.vault_path)

        @relay_app.post("/relay")
        async def handle_relay(req: Request):
            data = await req.json()
            status, res = await bridge.execute_http_request(
                service=data.get("service", "core-architect"),
                method=data.get("method", "GET"),
                url=data["url"],
                headers=data.get("headers", {}),
                cookies=data.get("cookies", {}),
                json_data=data.get("json_data"),
            )
            return JSONResponse(status_code=status, content=res)

        print(f"=== SupremeAI Local Residential IP Relay running on http://127.0.0.1:{args.port} ===")  # is_local()
        print("Set LOCAL_SESSION_RELAY_URL=http://127.0.0.1:8765 on Cloud/Render to bridge the IP gap!")  # is_local()
        # বাংলা মন্তব্য: রিলে সার্ভার চালু হওয়ার পর ব্যাকগ্রাউন্ডে ৫ মিনিট অপেক্ষা করে সাইলেন্ট রিফ্রেশ
        asyncio.create_task(_execute_silent_refresh(delay_sec or 300))
        config = uvicorn.Config(relay_app, host="127.0.0.1", port=args.port, log_level="warning")  # is_local()
        server = uvicorn.Server(config)
        await server.serve()
        return 0

    # বাংলা মন্তব্য: ব্রিজ ইনস্ট্যান্স তৈরি
    bridge = WebAISessionBridge(vault_path=args.vault_path)

    if args.status:
        # বাংলা মন্তব্য: সেশন বৈধতা ও উপলব্ধতা পরীক্ষা
        print("=== SupremeAI Web AI Session Status ===")
        print(f"Vault Path: {args.vault_path}")
        from core.web_ai_session_bridge import CURL_CFFI_AVAILABLE, ROOKIEPY_AVAILABLE

        print(f"TLS Impersonation (curl_cffi): {'AVAILABLE' if CURL_CFFI_AVAILABLE else 'UNAVAILABLE (httpx fallback)'}")
        print(f"Local Cookie Extractor (rookiepy): {'AVAILABLE' if ROOKIEPY_AVAILABLE else 'UNAVAILABLE'}")

        for s in ["core-architect", "core-logic", "core-design", "core-speed"]:
            cookies = bridge.resolve_session_cookies(s)
            has_cookies = bool(cookies)
            print(f"Service [{s}]: {'Active Session Found' if has_cookies else 'No Active Session'}")
        return 0

    if not args.prompt:
        print("Error: --prompt is required when not running with --status", file=sys.stderr)
        return 1

    try:
        # বাংলা মন্তব্য: AI কমপ্লিশন রিকোয়েস্ট পাঠানো
        res = await bridge.complete(
            service=args.service,
            prompt=args.prompt,
            system_prompt=args.system,
            session_token=args.token,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    except WebAISessionError as exc:
        print(f"[WebSessionClient Error] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[Unexpected Error] {exc}", file=sys.stderr)
        return 3


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
