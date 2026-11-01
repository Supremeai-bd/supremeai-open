# Desktop Runtime (WhatsApp-specific channel facts)

## Channel landscape

| Channel | Status | Notes |
|---|---|---|
| Official API (personal account) | Not a verified route in this Manus runtime | Do not automate a personal account through unofficial protocols; use official Web/Desktop surfaces for bounded user-authorized work |
| Reverse-engineered personal-account protocol | Forbidden | Not an approved official route for this package; do not use it to automate a personal account |
| **Computer Use (official desktop client)** | Conditional peer | Use for a verified desktop control or the user's explicit surface preference; do not promise background mutation |
| **My Browser (WhatsApp Web)** | Conditional peer | Uses the logged-in web session; linked devices can sign out after the primary phone has not been used for more than 14 days; detect feature rollout item by item |
| File pipeline | Composite use | Parsing and archiving exported txt/zip (Card 3); table deliverables (Card 5) |

## Computer Use operating notes

- Detect the installed app through the current Desktop application inventory and open the verified official app identity. Do not rely on a remembered filesystem path, Start-menu label, or AUMID.
- Interface controls and labels vary by build, rollout, language, and platform. Exact paths require an O1 event for the current build; never infer a Desktop export control from a phone procedure.
- Brief the user at every step; hand control back for anything involving credentials or a QR-code scan.

## Web client differences (tell the user when routing through My Browser)

- A linked-device session can be signed out when the primary phone has not been used for more than 14 days.
- Coverage of features such as Status publishing and calling can differ because of staged rollouts. Verify each required control against the current session instead of assuming parity.
- Choose the surface by verified capability and user preference, not by a blanket desktop-first rule.
- Keep personal WhatsApp and WhatsApp Business product guidance separate. Current personal-WhatsApp guidance documents Status creation on Web, Mac, and Windows, while current WhatsApp Business linked-device guidance lists adding and deleting Status as unsupported. Detect the account product before offering a publish path.

## Official help-center facts (use these when guiding the user)

- Export chat: current first-party procedures cover Android and iOS. The exported copy cannot be imported back as a backup. Desktop/Web export is not promised by this package.
- Backup and restore: chat history is backed up to the phone-side cloud account (Google Drive on Android, iCloud on iPhone) and restored during a reinstall; moving history to a new phone is a phone-side transfer flow, not something the desktop client can do.
- Linked devices: the phone remains the primary device, companion devices are linked from it, and a linked device can be signed out when the primary phone has not been used for more than 14 days.
- Broadcast lists: a mobile feature, unsupported on Windows, Mac, and Web; capped at 256 recipients and delivered only to recipients who have saved the sender's number.
- Business broadcasts: a separate WhatsApp Business app feature that is available only in limited countries and may not appear on an account. It can be paid, reviewed before delivery, sent immediately or scheduled, and requires consent and opt-out handling. Do not confuse it with ordinary broadcast lists or with the WhatsApp Business Platform; the Platform does not currently expose the Business app's business-broadcast feature.
- Quick replies (WhatsApp Business): setup is guided on the phone unless a current Desktop/Web control is detected and already live-verified; media quick replies are not supported on Web/Desktop.
