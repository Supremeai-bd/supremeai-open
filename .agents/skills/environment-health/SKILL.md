---
name: environment-health
description: Check the operational status of SupremeAI environments and external dependencies (Render, Supabase, Infisical, Cloudflare, GitHub, etc.).
---

# Environment Health Check

This skill runs a script to test the availability and health of various SupremeAI environments, including internal services and external platforms.

## When to use

- When the user asks to "check environments", "check render/supabase/cloudflare status", or verify if "everything is working".
- After a deployment, to ensure all services are healthy and external platforms are operational.
- During troubleshooting, if there are connectivity or service availability issues.

## Instructions

1. **Run the Script**: Execute the health check script using the following command from the workspace root (`f:\supremeai backup`):
   ```bash
   python scripts/check_env_health.py
   ```

2. **Analyze Output**:
   - The script will output the status of:
     - **Frontend**: https://<render-frontend-url>/
     - **Admin**: https://supremeai-admin.web.app/
     - **Backend**: https://<render-backend-url>/
     - **Render Platform**: https://status.render.com
     - **Supabase Platform**: https://status.supabase.com
     - **Infisical Platform**: https://status.infisical.com
     - **Cloudflare**: https://www.cloudflarestatus.com
     - **Upstash (Redis)**: https://status.upstash.com
     - **GitHub**: https://www.githubstatus.com
     - **AI LLM Providers**: OpenAI, Anthropic, Groq, OpenRouter

3. **Report to User**:
   - Summarize the results clearly.
   - If any service is marked `[FAIL]` or `[WARN]`, highlight it using markdown alerts (`> [!WARNING]`).
   - If all systems are operational, confirm this to the user.
   - If a specific service needs further debugging, propose the next steps (e.g., checking Render logs or investigating API keys).
