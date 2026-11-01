# Inbox (Card 1 digest / Card 2 drafts / Card 4 messages to table)

## Shared read contract

Before reading, name the chats or channels, time window, inclusion rule, and excluded conversations. Defaulting to every unread chat is not acceptable when the user asked about a narrower scope. Store a resumable cursor per chat and keep source pointers in every output.

## Card 1: Group and channel digest

**Use when**: summarize named groups or subscribed channels, surface mentions, or extract action items from a bounded period.

**Primary route**: a selected official Web/Desktop surface only after that surface has a disposable-account O1 for bounded reading. A bot is not a substitute for arbitrary human-account subscriptions. Without O1, provide a read plan or use a supplied export.

**Procedure**:

1. Confirm scope and whether the user wants unread-only, a date range, or messages since a known marker.
2. Read without reacting, marking, pinning, or typing. Do not open excluded chats.
3. Cluster by chat and topic; separate decisions, requests, deadlines, mentions of the user, and unresolved questions.
4. Attach chat name and timestamp to each actionable item. Mark ambiguity rather than inventing missing context.
5. Report inaccessible/partial history, save the per-chat cursor, and produce a digest plus a needs-reply queue.

**Verification**: sampled claims trace back to source messages; excluded chats remain unopened; Telegram write count is zero.

## Card 2: Drafted replies

**Use when**: prepare a response in the context of a named chat without sending it.

**Procedure**:

1. Read only the minimum surrounding context needed for the reply.
2. Draft one concise answer and, when tone is uncertain, one alternative. Flag factual or relationship-sensitive assumptions.
3. Preview the recipient and full text. In-app placement requires O1 for the selected composer; preserve any existing text or ask before replacing it.
4. Type into the target composer and stop. Sending to Saved Messages is still a send and is not a zero-write substitute.
5. Verify the composer contents and unchanged send count.

## Card 4: Messages to a table

**Use when**: turn orders, registrations, moderation events, or responses from named chats into structured rows.

**Procedure**:

1. Agree on the extraction schema, deduplication key, time range, and treatment of edited or deleted messages.
2. Prefer a supplied export. A live read requires selected-surface O1 and retains chat, sender, timestamp, and message reference with each matched record.
3. Parse into a staging table. Keep unmatched text and parse exceptions in a review sheet.
4. Build and verify the spreadsheet through the spreadsheet playbook; Telegram itself remains read-only.
5. Reconcile matched-message count, output-row count, duplicates, and exceptions; spot-check at least one record per source chat.

**Route note**: if the user supplies an export, skip Telegram UI and parse the files directly.
