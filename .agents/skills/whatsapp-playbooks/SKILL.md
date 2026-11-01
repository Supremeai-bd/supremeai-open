---
name: whatsapp-playbooks
description: "Use when the user asks what Manus can do with WhatsApp or needs help summarizing and organizing chats, drafting replies, exporting history, creating Status or business content, configuring Business features, sending compliant notifications, or managing devices and backups. Routes each workflow among My Browser, WhatsApp Desktop through Computer Use, native content tools, file processing, and official WhatsApp features."
---

# WhatsApp Playbooks (Manus for WhatsApp)

Handle bounded WhatsApp jobs—message review, draft preparation, content, data ownership, and business guidance—through official product surfaces and supported file tools, with account safety above every scenario.

## Step 0: Red-line constitution (precedes every scenario; full rules in formats/safety_rules.md)

Fear of account restrictions dominates requests around this app. Four ironclad rules:
1. **Keep activity bounded and policy-compliant**: no unsolicited messaging, no burst automation, no unofficial personal-account protocol client, and no repeated account actions designed to evade limits.
2. **Read-only first**: if a task can be finished read-only, never trigger a write.
3. **Drafts do not send**: generate outside the client by default, or place text in a composer and stop. A send to any chat, including "Message yourself," is still a send and requires confirmation at that boundary.
4. **Bulk messaging is not a Desktop CU loop**: choose among ordinary mobile broadcast lists, the rollout-limited paid business-broadcast feature in the WhatsApp Business app, and a separately verified WhatsApp Business Platform workflow according to account type, region, purpose, consent, and actual runtime. These are distinct product surfaces; rotating accounts, unofficial senders, per-recipient UI loops, and evasion are refused.

## Step 0.5: Channel routing (R0-R4)

```
R0 An explicit user instruction wins when the requested workflow is supported: "use the desktop app" -> Computer Use; "use the web version" -> My Browser; "do not actually send it" -> draft-only
R1 Environment probe: use a logged-in WhatsApp Web session through My Browser or the installed official desktop app through Computer Use according to user preference and the verified feature surface
   A linked-device session can be signed out when the primary phone has not been used for more than 14 days
   Neither -> guide the user to install the desktop app or link WhatsApp Web by QR code; pure content-production jobs (Card 4 / Card 7) need no client at all and are made in the cloud
R2 Account type: personal linked-device work stays in official Web/Desktop surfaces | Business work distinguishes the WhatsApp Business app from the WhatsApp Business Platform and detects the exact feature, country rollout, price, and device surface
R3 Computer Use trigger: use the desktop app only for a verified desktop control or when the user explicitly requests that surface; staged rollouts must be detected, not assumed
R4 Delivery loop: summaries, tables, and archives land as local files; content deliverables are previewed and wait for confirmation
```

## Step 1: Routing and completion contracts

| User outcome | Card / read | Primary route | Escalation route | Hybrid contract | Verification contract | CU display and reason |
|---|---|---|---|---|---|---|
| Summarize selected messages | **1 Inbox digest** / `references/inbox.md` | My Browser when the authenticated Web session contains the requested scope; Desktop CU only when the user requests Desktop or a verified Web gap requires it | Supplied export or manual selection when linked-device history is incomplete | Browser/Desktop supplies bounded read-only context; file tools produce the digest | Source citations reconcile to the selected chats/time range; WhatsApp write count is zero | **Conditional highlight**: CU is justified only by retained Desktop session or a verified client-only state |
| Draft a reply | 2 Ghostwritten drafts / `references/inbox.md` | Draft outside WhatsApp; optionally place the chosen text in a Web/Desktop composer and stop | Return copy-ready text if the target, existing draft, or send boundary is uncertain | Read only the approved context, draft outside the client, then optionally place one approved draft | Existing draft is preserved or reported; target and text match; no send action occurs | **Conditional**: only for placing text in the requested Desktop composer |
| Turn messages into a table | 5 Messages to table / `references/inbox.md` | Bounded My Browser read or Desktop CU read, followed by spreadsheet/file tools | Supplied export or manual source selection | UI supplies source messages; file tools create the table and provenance map | Row counts, sampled fields, timestamps, and low-confidence items reconcile to source | **Conditional**: only when the source exists solely in the Desktop client |
| Build a readable archive | **3 Export archive** / `references/archive-devices.md` | Phone export guidance, then deterministic file ingestion | Preserve received files and report incomplete scope; never invent a Desktop export path | User exports on phone; Manus indexes, validates, and renders the supplied files | Source hashes, message/file counts, parse exceptions, and observable date range are reported | **No**: the supported export mainline is not Desktop CU |
| Create or publish Status content | 4 Status and assets / `references/content.md` | Native content tools create the asset; hand over the file by default | For personal WhatsApp, publish through a currently verified Web/Desktop surface; for WhatsApp Business linked devices, do not assume Status creation is supported | Native tools create; My Browser or CU performs only an optional account-appropriate publish step after content, audience, and final-action confirmation | Media spec passes; if published, the Status is visibly present once | **Conditional highlight**: CU is only a verified personal-WhatsApp Desktop publish step, not a cross-product assumption |
| Create stickers or greeting assets | 7 Stickers and greetings / `references/content.md` | Native content tools create and validate the files | Give current manual import guidance when no verified import surface exists | Asset generation stays separate from account actions | File count, dimensions, transparency, and copy are checked; no send is implied | **No**: creation does not require WhatsApp Desktop |
| Plan supported customer outreach | 6 Compliant outreach / `references/outreach.md` | Route to ordinary mobile broadcast lists, an available WhatsApp Business app business broadcast, or a separately verified Business Platform workflow | Refuse unofficial senders, evasion, and Desktop/Web recipient-by-recipient loops | Manus validates account type, rollout, consent, audience, copy, price, and runtime before the supported surface performs delivery | Eligibility and rollout gaps are listed; no unsupported UI batch occurs | **No**: Desktop CU batching is explicitly unsupported |
| Configure Business replies | 8 Business setup / `references/outreach.md` | Phone guidance by default | A detected, current, O1-verified Web/Desktop control may be used for that exact feature | Manus drafts copy and test cases; the supported surface stores the setting | A consented second account triggers the expected reply; unsupported media behavior is reported | **Conditional**: only for a verified Desktop control, never inferred from phone docs |
| Research a WhatsApp marketing plan | 9 Marketing research / `references/outreach.md` | Cloud research and strategy | Route later ad execution to its separately verified advertising workflow | No WhatsApp client action belongs to the research phase | The memo identifies audience, value, measurement, consent, and compliance limits | **No**: no retained WhatsApp state is needed |
| Prepare a timed message | 10 Scheduled assistance / `references/outreach.md` | Create an exact draft plus reminder | At run time, hand off or request a fresh final-send confirmation; do not send when unattended | Scheduler stores reminder/draft only; active user and client perform the consequential action | Reminder text, recipient, and time match; no unattended send occurs | **No for scheduling**; optional CU at run time remains a separately confirmed single send |
| Move or restore phone history | 11 Backup guidance / `references/archive-devices.md` | Phone-side guidance | Optional read-only linked-device status check on a verified surface | Manus explains and verifies prerequisites; user performs phone operations | Guidance matches the phone platform and no irreversible phone action is automated | **No**: the retained state is on the phone/cloud backup, not Desktop |
| Learn or troubleshoot linked devices | 12 Multi-device how-to / `references/archive-devices.md` | Manual phone/QR handoff plus My Browser or Desktop CU for the visible companion side | Stop for credentials, QR scan, unavailable rollout, or unverified control | User controls the primary phone; Manus handles only the visible approved companion-side steps | Device becomes linked or the observed blocker is reported without claiming success | **Conditional highlight**: CU is useful when teaching or inspecting the installed Desktop client |

**Channel vocabulary**: *Sandbox/file tools* process authorized files without driving WhatsApp. *Computer Use* drives the official desktop app. *My Browser* uses the user's logged-in WhatsApp Web session. *Native content tools* create media without opening WhatsApp. *Ordinary broadcast lists* are a mobile linked-contact feature. *Business broadcasts* are a distinct, rollout-limited paid feature inside the WhatsApp Business app. *WhatsApp Business Platform* is a separate integration product and does not imply that the Business app's business-broadcast feature is available through an API. *Guidance* walks the user through a phone-only, rollout-limited, or unavailable action.

**Computer Use display markers (for the front end)**: conditional-highlight = Card 1 when the user selects the installed desktop client; yes = Card 4 publish and Card 12 walkthrough after the feature is detected; no = Card 3 export and Card 6 outreach because their supported main paths are not Desktop CU.

Read `formats/desktop_runtime.md` for surface facts and `formats/safety_rules.md` before any account action. The table above is the canonical per-card route and completion contract.

## Step 2: Output gates

1. Zero autonomy on sends: before any action that puts a message out, display the full content plus the recipient and wait for the user to confirm each one individually. Scheduled assistance creates a reminder and draft; it does not perform an unattended Computer Use send.
2. Minimize scope: open only the named chats and time range, avoid unrelated conversations, keep read-only tasks write-free, and let the user choose the output location. Do not claim host-only processing.
3. Chats with "Advanced chat privacy" turned on: respect the no-export setting, never work around it.
4. Data deliverables (digests, tables, archives) ship with an integrity check (message counts and chat counts reconciled against the source).


## SupremeAI integration notes
- Supports omnichannel communication/notification pipeline.
- Redact secrets; least privilege.
- Verification: 3-Tier Verify.

