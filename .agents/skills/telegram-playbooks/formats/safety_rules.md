# Safety rules

## Account and audience boundary

- This Manus package excludes unofficial personal-account clients because it has no verified session/secret/runtime design and because Telegram monitors non-official-client logins and enforces abuse rules. Do not misstate that every third-party client is categorically prohibited.
- Do not treat Computer Use as a policy exemption. The official client changes the technical route, not the user's obligations around spam, consent, or harassment.
- Refuse unsolicited personal-account DM batches, scraped-member outreach, fake members, fake views, and account rotation. Offer channel, group, or opted-in bot shapes.

## Operating rules

1. **Bound the task**: named chats, channels, time range, target, and action type. Do not use randomized delays or evasion instructions. Stop when the approved scope is exhausted.
2. **Read-only first**: digests and extraction add no reaction, draft, pin, mark, or send.
3. **Protect the send boundary**: preserve existing composer text; preview target and exact content; sending to Saved Messages is still a send; verify before retrying.
4. **Separate consequences**: publish, pin, schedule, delete, terminate session, and change permissions are distinct actions. Do not bundle their approval.
5. **Protect secrets**: never capture bot tokens or login codes in chat, prompts, files, screenshots, or event logs. Use a verified secure credential entry surface or remain in guidance mode.
6. **Make output at-most-once**: retain target, payload hash, input update ID where applicable, resulting message ID, observed state, and ambiguous failure point. Bot update acknowledgement is not send idempotency. Never replay an ambiguous output.
7. **State the data path honestly**: exported files may be processed in a remote sandbox through the Desktop bridge. Minimize scope and use a user-authorized output location; do not claim host-only processing.

## Refusal replacements

- personal-account DM blast → channel post, group announcement, or opted-in bot broadcast;
- unofficial user-account automation → a surface-specific conditional official-client workflow, manual guidance, or a bot identity for reusable automation;
- fake growth → onboarding, content, moderation, or legitimate promotion plan;
- secret pasted into chat → secure credential setup guidance;
- bypassing the export security wait → wait or confirm from another trusted device through Telegram's official flow.
