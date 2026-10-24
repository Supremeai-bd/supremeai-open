# Delivery contract (Telegram + MCP Tower)

Both tools come from the `supremeai` MCP server (MCP Tower). Load them with `tool_search` if they are not already available. If the server is not connected, say so and hand over `report.md` / `telegram.txt` / `tower_payload.json` instead.

## Telegram: `notify_send_telegram`
- `message`: contents of `telegram.txt` (1 to 4000 chars; the builder keeps it under 3800).
- Do not pass `parseMode`: the text contains characters that break Markdown/HTML parsing.
- Omit `chatId` to use the configured default chat.
- Optional pre-check: `notify_telegram` pings the bot token (it sends nothing).
- Very long reports: send the short summary only; the full report goes to the Tower.

## MCP Tower: `bridge_submit_patch`
Pass the fields of `tower_payload.json` unchanged: `taskId`, `summary`, `files`, `scopePaths`, `testsEvidence`, `reflectionWhy`, `alternativesRejected`, `agentIdentity`.
- `taskId` must match `^bridge-[0-9]{8}-[a-z0-9-]+$` (the builder does this).
- Max 30 files and about 200 KB of diff; reports are far smaller.
- The intake runs a secret scan (ghp_, github_pat_, sk-, AKIA, xox, AIza, PEM blocks, redis URLs) and rejects matching content. The builder redacts these, but if a submission is rejected, call `bridge_read_feedback` for the verdict, scrub the flagged text and resubmit once.
- Reports land under `reports/frontend-audit/<site>/...`, which is outside the protected paths (`.github/`, `docs/ledger/`, `.env*`, `*credential*`, keys). Never move a report into those.
- Reflection fields (`reflectionWhy`, `alternativesRejected`) are mandatory for the bridge; keep them.
- The bridge opens a work-order branch and issue in `Supremeai-bd/supremeai-open`; it never merges to main. Tell the user the work-order/issue reference from the tool result.

## Optional: episodic memory for agents
`memory_record_task`, `memory_remember_fact` and `memory_store_document` exist on the Tower but are proxied and may expose no parameter schema. Use them only if their schema is visible at call time, and store the compact `report.json` summary (counts + top findings), never raw network data. Otherwise skip.

## Failure handling
- Tool missing, auth error or timeout: report it plainly, keep the generated files, and offer to retry later.
- Never fabricate a "sent" confirmation. Quote the tool result.
- Do not resend the same report to Telegram on retry unless the user asks; duplicates are noisy.
