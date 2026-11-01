# Outreach (Card 6 notifications / Card 7 bot routing / Card 9 scheduled messages)

## Card 6: Compliant audience notification

**Use when**: announce something to a community or opted-in audience without sending unsolicited DMs.

**Refuse**: scraping members, sequential personal-account DMs, bought members or views, account rotation, or any instruction framed around avoiding restrictions.

**Supported shapes**:

1. a post in a channel the user administers;
2. an announcement in a group where the user has permission;
3. a broadcast from the user's bot to users who have already started or otherwise opted in to that bot.

**Procedure**:

1. Establish the user's authority, the audience relationship, opt-in basis, and desired reach.
2. Choose the shape and explain its honest coverage. A channel or bot reaches subscribers, not arbitrary contact lists.
3. Preview the exact copy and target. A channel or group post follows Card 5; a bot broadcast follows Card 7 and requires a verified runtime.
4. Execute only through a verified route. Record destination, payload hash, input cursor/update ID where relevant, resulting message IDs, and ambiguous failures; reconcile before retrying.

**Verification**: no per-person human-account DM loop; target and sent count match the chosen supported shape; failures are reported without blind replay.

## Card 7: Decide, design, and route a bot

**Use when**: server alerts, group moderation, welcome messages, commands, opted-in subscriber notifications, or a reusable Telegram integration.

| Need | Route |
|---|---|
| Server or system notification | Bot API after runtime verification |
| Group moderation, commands, welcome flow | Bot API with explicit group permissions |
| Opted-in subscriber broadcast | Bot API with durable subscriber state and retry controls |
| Read arbitrary subscriptions as the user | My Browser or Computer Use; not a bot substitute |
| Send as the user's human identity | My Browser or Computer Use for a bounded, confirmed action |
| Export the user's account data | Telegram Desktop export, Card 3 |

**Procedure**:

1. Define bot identity, event source, chat type, required permissions, subscriber consent, retention, and expected volume.
2. Inspect the current Manus session for an actual Telegram connector, MCP, or supported local execution route. Telegram's documented Bot API is capability evidence, not proof that Manus can call it now.
3. If no execution route exists, provide an implementation plan and guide the user through BotFather. The user enters the token into a verified secret surface; do not request it in chat.
4. Build a smallest test: one opted-in test chat, one event, one expected response. Separate input update acknowledgement from output dedupe; store update ID, destination, payload hash, resulting message ID, and ambiguous state.
5. Test permission denial, invalid destination, duplicate event, timeout, and retry. Reconcile before any second attempt.

**Verification**: the test event produces exactly one expected bot action; no personal-account API is used; secrets are absent from prompts, logs, and artifacts.

## Card 9: Native scheduled message

**Use when**: schedule a bounded message through Telegram's native feature.

**Procedure**:

1. Confirm target, exact content, local time, time zone, and notification intent.
2. Treat Web and Desktop independently. Open only a selected surface whose current scheduling control has passed its own O1; otherwise keep the content as a draft and provide guidance.
3. Place the content, open scheduling, select the time, and show the final scheduled action before confirmation.
4. Verify the item in Scheduled Messages with the expected target, time, and content.

**Recovery**: setup does not prove future delivery. If the scheduled item is absent or ambiguous, preserve the draft and stop rather than scheduling a duplicate.
