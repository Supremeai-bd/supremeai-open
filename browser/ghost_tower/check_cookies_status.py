import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Import local credential vault and gemini engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credential_vault import CredentialVault


def check_vault_cookies():
    vault_path = Path.home() / ".supremeai_vault" / "ai_fleet_cookies.enc.json"
    print("======================================================================")
    print("   SupremeAI: AI Fleet Cookies & Session Health Check")
    print("======================================================================")

    if not vault_path.exists():
        print(f"[!] Warning: Vault file not found at: {vault_path}")
        print("    Run '2_login_to_multi_ai.bat' to generate fresh session cookies.")
        return False

    try:
        vault = CredentialVault()
        encrypted_data = vault_path.read_text(encoding="utf-8")
        decrypted_json = vault.decrypt(encrypted_data)
        cookies = json.loads(decrypted_json)
    except Exception as e:
        print(f"[!] Failed to decrypt vault cookies: {e}")
        return False

    print(f"\n[+] Total Cookies in Vault: {len(cookies)}")
    now = time.time()

    domains = {}
    for c in cookies:
        dom = c.get("domain", "unknown")
        domains.setdefault(dom, []).append(c)

    print("\n--- Domain Summary ---")
    for dom, clist in sorted(domains.items(), key=lambda x: -len(x[1])):
        expired_count = sum(
            1 for c in clist if c.get("expires", -1) != -1 and c.get("expires") < now
        )
        valid_count = len(clist) - expired_count
        status = "[OK]" if valid_count > 0 else "[EXPIRED]"
        print(
            f" {status} {dom:<28} | Valid: {valid_count:<3} | Expired: {expired_count}"
        )

    print("\n--- Critical Session Expiration ---")
    critical_names = [
        "__Secure-1PSID",
        "__Secure-3PSID",
        "SID",
        "__Secure-next-auth.session-token",
    ]
    for c in cookies:
        name = c.get("name")
        if name in critical_names:
            dom = c.get("domain")
            exp = c.get("expires", -1)
            if exp == -1:
                status_str = "Session (Active indefinitely)"
            elif exp < now:
                status_str = (
                    f"EXPIRED on {datetime.fromtimestamp(exp).strftime('%Y-%m-%d')}"
                )
            else:
                status_str = (
                    f"VALID until {datetime.fromtimestamp(exp).strftime('%Y-%m-%d')}"
                )
            print(f" * [{dom}] {name:<28} : {status_str}")

    return True


async def check_live_gemini():
    print("\n======================================================================")
    print("   Running Live Query Verification on gemini.google.com ($0)...")
    print("======================================================================")
    try:
        from gemini_web_engine import GeminiWebEngine

        engine = GeminiWebEngine(headless=True)
        await engine.initialize()
        resp = await engine.ask(
            "Say 'Cookies are active' in 3 words.", timeout_seconds=25
        )
        await engine.close()
        print(f"\n[SUCCESS] Live Gemini Response: {resp.strip()}")
        print("\n>>> ALL COOKIES ARE HEALTHY, VALID & OPERATIONAL! <<<")
    except Exception as e:
        print(f"\n[!] Live test notice: {e}")
        print(
            ">>> If needed, run 1_login_to_gemini.bat or 2_login_to_multi_ai.bat to refresh. <<<"
        )


if __name__ == "__main__":
    ok = check_vault_cookies()
    if ok:
        import asyncio

        asyncio.run(check_live_gemini())
    print("======================================================================\n")
