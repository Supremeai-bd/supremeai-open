# Archive & Devices (Card 3 export archive / Card 11 backup guidance / Card 12 multi-device how-to)

## Card 3: Chat history exported into a readable archive (`cu_display: no`)

**Trigger phrases**: "export my chat history", "I want a copy on file", "save my history before I change numbers"
**Input contract**: scope (everything / named chats) plus whether media is included plus archive format preference (HTML index or PDF).
**Supported route**: WhatsApp's current first-party export procedure is documented for Android and iOS, not Windows, Mac, or Web. Guide the user through the phone export; after they place the exported ZIP/text in the authorized folder, use the file pipeline.
**Steps**:
1. Confirm named chats, include-media choice, and the privacy scope
2. Give the matching Android or iOS export guidance; do not claim a Desktop export control unless the current build has a recorded O1 event
3. Ingest the supplied ZIP/text and build an HTML archive indexed by chat and date, with a media directory when present
4. Reconcile every imported file and message count; report gaps or an incomplete range instead of inventing completeness
↯ Export is blocked or incomplete → respect the product restriction, preserve the received files unchanged, and report the observable range and discrepancy. Never work around privacy settings.
**Output assertions**: archive message count = the sum of the message counts in the exported files; every chat opens from the index in one click; no send or write operation occurred.
**Recordability**: the phone export is guidance, not a Desktop CU recording. The deterministic file-ingestion and archive-verification stages belong in tests, not a GUI recording.
**Demo data**: synthetic Android and iOS export ZIPs with multilingual text, media, and known message counts.

## Card 11: Backup and new-phone guidance (guidance only)

**Trigger phrases**: "how do I bring my history to a new phone?", "my Google Drive backup will not restore"
**Scope**: the real work happens on the phone (cloud backup, new-phone pairing). What the desktop can contribute is linked-devices assistance plus guidance. **Never promise to operate the phone on the user's behalf.**
**Steps**: 1) Pin down the scenario (same-OS phone swap, cross-OS, restore only). 2) Give step-by-step guidance along the matching official path (using the help-center facts collected in formats/desktop_runtime.md, section "Official help-center facts"). 3) On the desktop side, check linked-device status for the user.
**Output assertions**: the guidance matches the official path; no irreversible operation is performed.

## Card 12: Desktop and multi-device how-to (walkthrough card)

**Trigger phrases**: "how do I use WhatsApp on my computer?", "why does the web version keep dropping?"
**Steps**: 1) Identify the ask (install, link Web/Desktop, or debug a dropped session). 2) Detect the current official surface and explain the QR handoff; the user handles the phone and QR scan. 3) Use My Browser or Computer Use only for the visible linked-device side of the flow. 4) For a dropped session, check current device state and explain that linked devices can sign out after the primary phone has not been used for more than 14 days.
**Output assertions**: the target state is reached (device linked, or the user restates the key rule).
**Recordability**: not a reusable recording candidate. The flow crosses a phone-owned security boundary, includes a QR or phone-number handoff, and may expose account-specific device state. Use a bounded O1 observation to qualify the companion-side controls, while keeping the primary-phone actions user-controlled.
