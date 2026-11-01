# Content (Card 5 channel publishing / Card 8 sticker packs)

## Card 5: Channel publishing

**Use when**: prepare, format, publish, or pin content in a channel the user administers.

**Route choice**:

- one-off human-admin post: selected official surface only after its own disposable-account O1;
- recurring or system-generated publishing: official Bot API only after a usable Manus integration or tested local runtime is verified;
- copy or media creation: native content tools first, before opening Telegram.

**Procedure**:

1. Confirm channel, admin authority, post type, media, formatting, link-preview choice, notification behavior, and whether a pin is requested.
2. Produce an off-client preview of the final copy and media. Split or redesign content that does not fit the detected current limit or format.
3. If the selected surface lacks O1 for this card, stop at the preview and guided handoff. Otherwise open the exact channel and compare its identity to the approved target.
4. Place the content and inspect the rendered preview. Wait at the publish boundary according to the current confirmation semantics.
5. Publish once. Pinning is a second consequential action and is confirmed separately.
6. Verify text, media, formatting, target, and pin state. If the state is ambiguous, do not retry blindly.

**Recovery**: retain the approved payload and target identifier so a failed attempt can be reconciled without duplicate posting.

## Card 8: Sticker pack production

**Use when**: turn owned or licensed artwork into a Telegram sticker set.

**Procedure**:

1. Confirm image rights, visual style, sticker count, emoji mappings, and pack name.
2. Generate or edit transparent assets with native image tools. Inspect edge quality and legibility at small size.
3. Choose between Telegram's built-in Sticker Editor for creating from a photo in a chat and the official @Stickers Mini App for creating and managing packs. Do not treat remembered legacy bot commands as the mainline.
4. For static assets prepared outside Telegram, validate PNG or WEBP output with one side exactly 512 pixels and the other no larger than 512 pixels. Animated and video assets have different official formats and limits; detect and validate that branch separately.
5. If the selected official surface has O1, upload one approved test sticker, bind the intended emoji, and preview it; otherwise deliver prepared assets plus current guidance.
6. Complete the remaining items only after the test passes; then choose the short name and publish once.
7. Verify that the returned pack link opens and that a sampled sticker renders correctly.

**Boundaries**: do not copy unlicensed character packs, impersonate another creator, or use unofficial upload automation on the user's account. Asset production is executable; pack creation remains conditional until the selected official surface is observed. This handoff is not a Record-as-Skill candidate by default because most reusable value is deterministic asset preparation and the remaining upload is short, identity-bound, and publish-consequential.
