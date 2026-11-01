# Inbox (Card 1 inbox digest / Card 2 ghostwritten drafts / Card 5 messages to table)

Shared by all three cards: **read-only for the whole run is the default**; minimize scope to named chats/time windows and let the user choose the deliverable location. Do not claim host-only processing.

## Card 1: Inbox digest (cu_display: highlight)

**Trigger phrases**: "look through my messages for me", "too many unread, sort them out", "what did my customers say?"
**Input contract**: scope (all unread / named chats / a time window) plus output preference (by person, by topic, to-do extraction). If missing, default to "unread plus the last 24h, clustered by chat, with to-dos extracted".
**Steps**: 1) Probe My Browser and Desktop and honor the user's surface choice. 2) Confirm the chat/time scope. 3) Read only that scope, keeping a cursor after each completed chat. 4) Cluster by sender, topic, and urgency. 5) Produce the digest, to-dos, and needs-reply list with chat name and timestamp. 6) Deliver as a file. A self-chat delivery is a separate confirmed send, not part of read-only mode.
↯ Too many chats to cover → agree a batch order and resume from the stored cursor; do not infer completeness when linked-device history is missing.
**Output assertions**: every to-do traces back to the message it came from; no send action occurred at any point.
**Recordability**: candidate only after a disposable-account O1 proves bounded traversal, privacy exclusions, cursor resume, and zero writes. The reusable object is the scope/cursor/verification contract, not captured coordinates or real chat identities.
**Demo data**: test account plus three scripted chats.

## Card 2: Ghostwritten drafts (draft-only, never sends)

**Trigger phrases**: "reply to this for me", "how do I answer this politely?"
**Input contract**: target chat plus tone preference (past messages can be supplied as a reference; D4 can be externalized). If missing, read the context and match the user's historical tone.
**Steps**: 1) Read the agreed context read-only. 2) Draft two versions outside the client. 3) By default, deliver the text without changing WhatsApp. If the user wants it placed in the composer, preserve any existing draft, type the chosen version, and stop. 4) The user sends it. A self-chat is not a draft substitute; it is a confirmed send.
↯ Sensitive content (conflict, financial commitments) → attach a risk note to the draft.
**Output assertions**: the draft is in place; the send key was never touched by the agent (safety assertion).
**Recordability**: not a default reusable recording. Draft generation is channel-independent and composer placement is a short, identity-bound last mile. Use O1 to qualify placement and rollback; return text-only whenever the selected surface is not proven.

## Card 5: Order and signup messages into a table

**Trigger phrases**: "turn the orders in this group into a spreadsheet", "tally up the signups"
**Input contract**: target group or chat plus the field schema (name, quantity, address, time). If missing, propose a schema based on the shape of the messages and ask for confirmation.
**Steps**: 1) Read the target chat read-only. 2) Pattern-extract, tagging each row with the source message's timestamp as provenance. 3) Write to xlsx (following the artifact standard from excel-playbooks: number_format, low-confidence flagging). 4) Spot-check points.
↯ Message formatting is chaotic → flag low confidence and produce a manual-review list; do not force the parse.
**Output assertions**: extracted row count = number of matched messages; sampled amount and quantity columns match the original messages.
**Cross-skill note**: defer to excel-playbooks (formats/engineering_standards.md) for the table artifact standard.
