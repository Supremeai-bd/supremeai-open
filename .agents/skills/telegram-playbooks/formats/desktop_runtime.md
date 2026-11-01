# Desktop runtime and channel facts

## Capability versus Manus execution

| Surface | What is established | What still requires run-time proof |
|---|---|---|
| Telegram Web through My Browser | Selected user-account state may be reachable through the authenticated Web surface | My Browser exposure, login, history depth, exact control, disposable-account O1, and recovery |
| Telegram Desktop through Computer Use | Official Desktop is a documented export surface and may expose selected user-account state | App/version/OS, exact control, accessibility, disposable-account O1, recovery, and separate evidence from Web |
| Official Bot API | Supported bot identity for notifications, moderation, commands, and opted-in subscribers | A usable Manus connector/MCP/local runtime, permissions, credentials, limits, idempotency, and error handling |
| MTProto or TDLib personal-account automation | Technically possible but excluded from this Manus package | No verified Manus session/secret/runtime design; account-abuse and deployment risks remain |
| Sandbox/file pipeline | Can transform an already-exported HTML/JSON/media bundle | Authorized file availability, schema detection, count reconciliation, and output location |
| Official sticker surfaces | Built-in Sticker Editor creates from photos in a chat; the @Stickers Mini App creates and manages packs | Which selected Web/Desktop/mobile surface exposes the required controls, exact O1, account state, and publish verification |

The checked Manus builtin connector enum contains My Browser and no Telegram builtin identifier. That does not prove the server catalog has no Telegram MCP, so inspect the actual session tool list before claiming either availability or absence.

## Desktop export facts

- Telegram documents all-data and per-chat export from Telegram Desktop, with HTML or JSON output. Exact current item coverage and schema still require the generated summary and files.
- A newly logged-in Desktop session may require a 24-hour wait or confirmation from another device before export.
- Exact menu nesting can drift. Find the named control in the current version; do not replay a coordinate or stale path.
- Web is not the full-export route. Once output files exist, app control is unnecessary for indexing and analysis.

## Computer Use operating contract

1. Detect the installed official app and record app version, OS, locale, and theme before a recording or O1 claim.
2. Prefer semantic accessibility elements. Do not instruct the agent to rely on icon position when labels are localized; use current state plus nearby semantics and visual verification.
3. Credentials, login codes, and session-termination decisions remain user-controlled.
4. A background state read is not proof that clicks or typing remain in the background.
5. Computer Use has a cross-session lease; serialize CU tests and maintain a durable cursor for resumable multi-chat work.
6. Telegram Web is operated through My Browser, not Computer Use.
7. Web and Desktop require separate O1. Do not infer parity from a shared account or a first-party feature description.

## File-processing boundary

Desktop shared-folder files can be bridged to a remote sandbox. Describe scope, authorization, and output location accurately; never promise that chat exports are processed only on the host or that nothing is uploaded.

## Sticker handoff boundary

- Static sticker assets prepared outside Telegram use PNG or WEBP. One side must be exactly 512 pixels and the other must be no larger than 512 pixels.
- Animated and video stickers use different official formats and limits; never apply the static-image contract to them.
- The built-in Sticker Editor and the @Stickers Mini App are distinct official creation surfaces. Their public documentation is O2, not proof that the chosen client surface is executable through Manus.
