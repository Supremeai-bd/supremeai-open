---
name: universal-ai-web-bridge
version: 0.1.0
description: Send prompts to an AI web interface through an authorized browser session and retrieve replies.
triggers: [web bridge, browser automation, gemini web, chatgpt web]
permission_level: read
memory_policy: write
owner: supremeai-skills
verification_required: true
evidence_requirements: [conversation id, provider, provenance]
idempotency: one conversation per session id
stop_conditions: [session expired, ui changed, provider restriction]
---

# Universal AI Web Bridge

## Purpose
Send prompts to an AI web interface through an authorized browser session, retrieve replies, continue a supported conversation, and optionally send approved structured knowledge to SupremeAI memory.

## Architecture
SupremeAI/Telegram -> MCP Tower -> authenticated browser bridge -> provider web UI -> response -> Tower/Telegram -> optional memory review.

## Requirements
Start with one provider; protect browser sessions; map conversation IDs; handle UI changes and failures; provide clear provenance.

## Limits
No bypassing login, CAPTCHA, anti-bot protections, or provider restrictions. A remote MCP service cannot automatically access cookies in a user's local browser; a secure bridge is required.

## Existing implementation
`browser/ghost_tower/` + `browser/runtime/` (cookie_bridge, session_manager, stealth_profile). This skill documents the procedure and metadata contract.