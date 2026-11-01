# Archive and devices (Card 3 full export / Card 10 Desktop and device walkthrough)

## Card 3: Full or selected export to a searchable archive

**Use when**: the user wants a durable copy of all Telegram data, selected chats, or a channel before an account change, investigation, or cleanup.

**Route boundary**: starting a full export is a Telegram Desktop workflow. Telegram Web is not the route. If the user already has HTML, JSON, and media from an export, skip the app and use the sandbox/file pipeline.

**Input contract**:

- full account or named chats;
- HTML for direct reading, JSON for structured processing, or both;
- date range and media categories;
- output location and whether media should be copied, linked, or omitted.

**Procedure**:

1. Detect Telegram Desktop and record the current app version, OS, account, and intended scope. Do not open unrelated chats.
2. Locate the current **Export Telegram data** control in Settings, or use the named chat's export control for a chat-only request. Exact menu nesting is version-sensitive and requires live detection.
3. Show the selected scope, format, date range, and media options before starting. Do not silently broaden the export.
4. If Telegram requires either a 24-hour wait for a newly logged-in Desktop session or confirmation from another device, stop and explain the official choices. Do not bypass the protection or repeatedly retry.
5. Export to the user-authorized shared location. Capture Telegram's completion summary before leaving the app.
6. Detect the actual export schema/version and parse HTML/JSON/media into a searchable index. Preserve each source file, chat name, message identifier or timestamp, sender, attachment reference, and parse exception.
7. Reconcile chat/message/media counts with Telegram's completion summary. Keep an unsupported-type ledger and never broaden “selected export” into “all history.”

**Verification**: archive index opens; source files remain unchanged; reconciled counts and exceptions are included; no Telegram send, delete, or account mutation occurs.

**Important boundary**: an export is not a restorable Telegram backup. Secret Chats are device-specific; do not claim that a particular export includes or excludes them without checking the current export summary and output.

**Record-as-skill parameters**: account label, full-versus-chat scope, date range, format, media categories, output location, and security-wait branch. Never record a login code, account identifier, fixed path, or coordinate.

## Card 10: Desktop and multi-device walkthrough

**Use when**: install or sign in on a computer, inspect active sessions, terminate an unfamiliar session, or explain device behavior.

**Procedure**:

1. Classify install, sign-in, active-session review, or session termination.
2. For install or sign-in, guide the official client flow and hand verification-code entry to the user. Do not read or store the code.
3. For a session review, detect the current Devices control on the selected surface. Inventory only the fields currently visible and flag anomalies without terminating anything.
4. For termination, present the exact target session and wait at the consequential boundary. Verify that the intended session—not the current one—disappears.
5. Explain that normal cloud chats synchronize across devices while Secret Chats remain device-specific.

**Availability**: guidance is ready; inventory or termination remains conditional until the exact selected-surface control and recovery pass O1.

**Recovery**: if the current session is at risk, stop before termination and give the user a relogin plan. Never mass-terminate sessions as an unreviewed batch.
