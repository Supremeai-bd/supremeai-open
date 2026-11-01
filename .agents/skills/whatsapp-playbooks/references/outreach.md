# Outreach (Card 6 compliant outreach / Card 8 Business setup / Card 9 marketing research / Card 10 scheduled-message assistance)

This whole group sits under the strictest reading of the red-line constitution (formats/safety_rules.md).

## Card 6: Compliant outreach planning and supported handoff (hard red line)

**Trigger phrases**: "send my customers a notice", "push the new-product message to my regulars"
**Input contract**: the recipient list plus the copy. The list must consist of people saved as contacts — WhatsApp's documented precondition is that a broadcast is delivered only to recipients who have the sender's number saved in their own address book.
**Route boundary**: treat three official surfaces as different products. Ordinary broadcast lists are configured and used on mobile and are unsupported on Windows, Mac, and Web. WhatsApp Business app business broadcasts are rollout-limited, can be paid, require opt-in and opt-out handling, and may support send-now or scheduled delivery. WhatsApp Business Platform workflows require a separately verified integration runtime, and the Platform does not currently expose the Business app's business-broadcast feature. Manus does not control the phone in this skill.
**Steps**: 1) Confirm account product, country, purpose, consent, audience eligibility, copy, and opt-out handling. 2) Reconcile the list and separate ineligible or unknown recipients. 3) For ordinary broadcast lists, provide mobile guidance and the 256/contact-saved constraints. 4) If the WhatsApp Business app exposes business broadcasts, review the audience, content, price, review state, schedule, and online-device requirement before the user completes the consequential action. 5) For a different API-based business workflow, inspect the actual Manus runtime, credentials, templates, receipts, dedupe, and revocation before execution. 6) Never replace an unavailable route with a Desktop CU recipient-by-recipient loop.
↯ The user asks to split lists to evade limits or use an unofficial sender → refuse and explain the supported choices.
**Output assertions**: no unsupported Desktop/Web broadcast-list action and no per-person CU blast; account product, feature availability, eligibility, consent, opt-out, pricing, and runtime gaps are explicit.

## Card 8: WhatsApp Business auto-reply and quick-reply setup

**Trigger phrases**: "set up an auto-reply", "after hours, say I will get back to them tomorrow"
**Prerequisites**: requires the WhatsApp Business app. Current first-party setup guidance is phone-based; Desktop/Web creation and configuration remain conditional until detected and live-verified.
**Steps**: 1) Confirm account type and target feature. 2) Draft the greeting, away message, or quick-reply text. 3) Guide phone setup by default; if the exact control is visible and already O1-verified on the current Desktop/Web build, use that surface. 4) Test with a consented second account and leave a step card.
**Output assertions**: the test trigger fires (the auto-reply lands in the test conversation).

## Card 9: WhatsApp marketing research and strategy (cloud only, never touches the client)

**Trigger phrases**: "is WhatsApp marketing worth doing?", "how do I use WhatsApp to bring in new customers?"
**Steps**: cloud research (case studies, numbers, compliance boundaries) → a strategy memo. If it reaches ad execution, route the user to the Meta Ads flow; on the WhatsApp side, advise only on the receiving setup.
**Output assertions**: the memo includes a compliance red-line section (citing safety_rules).

## Card 10: Scheduled-message assistance (draft + reminder)

**Trigger phrases**: "send this birthday message for me at 6am tomorrow"
**Steps**: 1) Draft the exact text and recipient. 2) Create a reminder for the chosen time with the draft attached. 3) At run time, show the content and recipient again; the user performs or confirms the final send on the active surface. 4) If no user is present or the session state differs, do not send.
↯ The client is offline, the chat changed, or the recipient cannot be verified → keep the draft and notify; never blind-retry.
**Output assertions**: the reminder contains the approved draft; no unattended CU send occurs.
**Reopen gate**: an autonomous scheduled-send branch requires a proven local-session handoff, at-most-once execution, exact-content diff, consent semantics, and failure recovery. None is currently certified here.
