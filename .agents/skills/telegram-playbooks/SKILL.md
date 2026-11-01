---
name: telegram-playbooks
description: "Use when the user asks what Manus can do with Telegram or needs workflows for chat summaries and drafts, structured extraction, history exports, channel publishing, scheduled messages, sticker packs, compliant notifications, bots, devices, or Telegram guidance. Routes each workflow by identity, selected client, durable state, runtime availability, and consequence among file and content tools, Telegram Web in My Browser, Telegram Desktop through Computer Use, and a separately verified official Bot API runtime."
---

# Telegram Playbooks (Manus for Telegram)

Route Telegram work by identity, durable state, and supported surface. A user-account task, a bot task, a file task, and a content-production task are different jobs even when they end in the same chat.

## Step 0: Safety and scope

1. Manus does not use MTProto, TDLib, or another personal-account client route in this package. Telegram permits third-party clients but monitors non-official-client logins and enforces abuse rules; Manus additionally lacks a verified session/secret/runtime design for this route. This is a product route exclusion, not a claim that every third-party client is prohibited.
2. Keep user-account work bounded to the named chats, channels, and time range. Read-only jobs create no Telegram writes.
3. A composer draft is not a send. Every actual post, message, pin, or scheduled-message confirmation is a consequential action and must match the approved target and content.
4. Refuse unsolicited per-person DM batches, fake members, fake views, and attempts to evade rate or abuse controls. Offer a channel post, group announcement, or opted-in bot subscription instead.
5. Do not put bot tokens or login codes in prompts, files, logs, or chat output. Use a verified secure credential surface if one exists; otherwise guide the user through setup without capturing the secret.

Read `formats/safety_rules.md` before any workflow that sends, publishes, schedules, administers a group, or handles a credential.

## Step 0.5: Runtime routing

```
R0 Assign one status before acting: EXECUTABLE, CONDITIONAL-O1, GUIDANCE, or REFUSE.
R1 Honor an explicit supported surface request: Telegram Web -> My Browser; installed Telegram Desktop -> Computer Use.
R2 Determine the identity:
   - bot identity and opted-in audience -> official Bot API, but only if a usable Manus integration or local runtime is verified;
   - the user's human identity -> My Browser or Computer Use on an official Telegram client;
   - no Telegram identity needed -> native content tools or sandbox/file tools.
R3 Determine the durable state:
   - existing cloud chat/channel state -> My Browser or Computer Use;
   - Desktop export state -> Computer Use in Telegram Desktop;
   - already-exported HTML/JSON/media -> sandbox/file pipeline;
   - generated art or copy -> native content tools first.
R4 Detect availability at run time. A documented Telegram API or feature is not proof that the current Manus session exposes it or that the selected Web/Desktop build has the control.
R5 Verify the result and preserve recovery state before leaving the workflow.
```

## Step 1: Routing and completion contracts

| User outcome | Card / read | Primary route | Escalation route | Hybrid contract | Verification contract | CU display and reason |
|---|---|---|---|---|---|---|
| Summarize named groups or channels | 1 / `references/inbox.md` | Supplied export/file pipeline; otherwise My Browser read-only after Web O1 | Desktop CU only after separate Desktop O1 when required state is unavailable on Web | Selected surface supplies bounded messages; Manus builds the digest and durable cursor | Sampled claims trace to chat/timestamp; exclusions stay unopened; Telegram write count is zero | **Conditional**: only Desktop-only retained state after current-build O1 |
| Draft a reply without sending | 2 / `references/inbox.md` | Native text drafting; optional placement through the explicitly selected Web surface after O1 | Desktop composer after separate O1 when the user explicitly wants the installed app | Manus drafts off-client; selected surface places text without sending or replacing existing text silently | Recipient and composer text match; send count remains unchanged | **Conditional**: only explicit Desktop placement after O1 |
| Turn messages into a structured table | 4 / `references/inbox.md` | Existing export → file parser → spreadsheet playbook | Bounded Web read after O1; Desktop CU only for state unavailable through export/Web | Telegram supplies source records; spreadsheet tools create and verify the table | Matched messages, rows, duplicates, exceptions, and per-chat spot checks reconcile | **Conditional**: source acquisition only, never table construction |
| Export all or selected Telegram data | 3 / `references/archive.md` | Existing export → file pipeline | Telegram Desktop CU after current-build export O1 when a new official export is required | Desktop creates the scoped export; file tools preserve, parse, index, and reconcile it | Source hashes and Telegram completion counts reconcile; originals remain unchanged | **Highlight after O1**: official full-export state is Desktop-specific |
| Format and publish a channel post | 5 / `references/content.md` | Native content tools for copy/media; selected human-admin surface after its own O1 for one-off publish | Verified Bot API runtime for recurring or system-generated publishing | Manus prepares payload; selected identity publishes once; pin is a separate action | Text, media, formatting, channel, message state, and optional pin state match | **Conditional**: one-off human-admin Desktop publishing after O1 |
| Build a sticker pack | 8 / `references/content.md` | Native image tools prepare licensed assets | Use Telegram's current in-app Sticker Editor or the official @Stickers Mini App only after the selected surface has O1; otherwise deliver assets plus guidance | Manus creates and checks assets; the verified official surface uploads one test before the remainder | Pack link opens and sampled sticker/emoji mapping renders correctly | **No by default**: asset preparation dominates; a selected app handoff is conditional and is not known to require Desktop CU |
| Notify an audience compliantly | 6 / `references/outreach.md` | Channel/group post or verified opted-in Bot API route | GUIDANCE when authority, consent, runtime, or surface O1 is absent | Manus prepares approved copy; Card 5 or Card 7 owns execution | No human-account DM loop; destination, payload hash, result IDs, and failure count reconcile | **Conditional**: bounded Desktop group/channel post only after O1, never DM batches |
| Decide, design, and route a bot | 7 / `references/outreach.md` | Runtime inspection and GUIDANCE; verified Bot API implementation only after full gate | User-operated setup plan when no supported Manus runtime exists | Manus designs/tests non-secret behavior; user enters token through a verified secret surface | One opted-in test event produces exactly one expected action; revoke and denied-permission tests pass | **No**: bot identity and runtime are not Desktop CU work |
| Schedule a message | 9 / `references/outreach.md` | Explicitly selected Web surface after Web O1 | Desktop CU after separate Desktop O1; otherwise preserve a draft and guide | Manus prepares content/time; selected surface creates one scheduled item | Scheduled queue shows target, time zone, and content; absence or ambiguity never triggers blind retry | **Conditional**: only explicit Desktop scheduling after O1 |
| Learn Desktop or manage devices | 10 / `references/archive.md` | Evidence-gated GUIDANCE for install, sign-in, or device review | Desktop CU after exact installed-control O1 for a bounded inventory or termination | Manus provides a versioned step card; user handles codes and confirms any termination target | Intended session state is observed; credentials are absent; no unrelated session changes | **Conditional**: retained Desktop session state after O1; security handoffs stay user-controlled |

**Channel vocabulary**: *My Browser* uses the user's authenticated Telegram Web session and is not Computer Use. *Computer Use* drives an installed official desktop app. *Sandbox/file tools* process user-authorized files and may run in a remote sandbox; do not claim host-only processing. *Native content tools* create media or text without opening Telegram. *Official Bot API* describes Telegram's supported bot capability, but execution requires a separately verified Manus connector, MCP, local runtime, or user-operated integration. *Guidance* explains a route that Manus cannot currently execute safely.

**Computer Use display markers**: Card 3 is the strongest candidate because the official Desktop export produces useful downstream files, but it remains unrecorded until current-build O1. Cards 1, 5, 9, and 10 are conditional only after separate Desktop evidence. Do not label bot setup, bulk outreach, Web operation, or file-only post-processing as CU.

Read `formats/desktop_runtime.md` for channel boundaries, `formats/route-contract.md` for route status and precedence, and `formats/verification-manifest.md` before declaring completion. The table above is the canonical per-card route and completion contract.

## Step 2: Output and verification gates

1. Before a write, restate the target, exact content, selected identity, and write type. Apply the confirmation semantics of the current Manus runtime.
2. Keep a durable cursor for multi-chat reads: named chat, last processed timestamp or message, and excluded chats. Resume from the cursor instead of starting over.
3. Data outputs reconcile source chats, matched messages, output rows, attachments, detected schema, unsupported item types, and parse exceptions. Never say “all history” without the selected scope and Telegram completion summary.
4. A scheduled-message task passes only when the item is visible in Telegram's scheduled queue with the expected target, time zone, and content. Setup is not proof of future delivery.
5. Never claim a bot route is executable until the current session exposes a supported integration or a tested local implementation. Never infer that Computer Use bypasses Telegram's spam or consent rules.


## SupremeAI integration notes
- Connects to SupremeAI notification system (
otify_telegram); Telegram Bot integration.
- Redact secrets; least privilege.
- Verification: 3-Tier Verify.

