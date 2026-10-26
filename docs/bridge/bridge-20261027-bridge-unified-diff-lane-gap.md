# Bridge v2 lane gap: unified_diff existence check makes monorepo-only existing-file edits impossible — plus a ready-to-apply streaming patch artifact for #1333

Work order: `bridge-20261027-bridge-unified-diff-lane-gap` — an ops/product gap report in the same class as the WAF body-filter hazard, with a concrete, pre-verified patch artifact attached so a coder can land the #1333 root-client fix in one command.

## The gap (three lanes exhausted, all verified today against live bridge v2)
Target: edit the EXISTING file `packages/shared-services/src/services/SupremeAIService.ts` on the monorepo (path exists ONLY there; the open repo and open patch branches have never carried it).

1. **full_file on existing file** → deterministically fails: "already exists in working directory" (seen on order #1373, verdict quoted Supremeai-bd/supremeai@main).
2. **unified_diff** → fails BEFORE parsing hunks can matter: "File ... uses mode unified_diff but does not exist on bridge/<task-id>; use mode full_file to create it." The existence check runs against the open-repo patch branch tip, where monorepo-only paths never exist. Reproduced twice today with a content-only diff (no mode lines, no index lines) whose `git apply --check` is CLEAN against the exact monorepo main content (sha b6cfa2e5).
3. **NEW-file lane** (r3, order #1419) → mechanically succeeds but its PR #1420 closed unmerged with no verdict, leaving the root consumer unfixed.

Net effect: the bridge currently accepts NO order shape that edits an existing monorepo-only file. Files that exist only in the monorepo (packages/, scripts/, data/ on the private repo) are permanently stuck on the new-file-plus-manual-swap lane.

## Minimal fix options for the bridge (either closes the gap)
- Run the unified_diff existence check against the ROUTED target repo's patch branch (created from that repo's main tip) instead of the open-repo branch; or
- allow `full_file` with an explicit `baseSha` field that fail-closed matches the target tip before replacing content.

## Attached artifact: the #1333 root streaming fix, ready to apply
`docs/bridge/patches/SupremeAIService-streaming-r4.diff` — content-only unified diff (verified: `git apply --check` CLEAN; post-apply file byte-identical to the tsc 5.9.3-verified r3 implementation; diff base equals current monorepo main content, sha b6cfa2e5). Apply from the monorepo root:

    git apply docs/bridge/patches/SupremeAIService-streaming-r4.diff

The diff ships `streamChatMessage` (fetch + ReadableStream SSE parsing), `requestWithRetry` (2 retries, exponential backoff plus jitter), a 120s configurable timeout, and typed `ApiError` into the root shared-services client — the consumer path for the VS Code extension (`workspace:^`), the last unfixed surface of #1333.

## Acceptance criteria
- [ ] Bridge v2: editing an existing monorepo-only file via work order is possible (either fix option above) — track as a bridge product improvement
- [ ] Interim: the attached diff is applied to monorepo main and the root client gains streaming/retry/timeout/typed-errors
- [ ] Post-apply symbol audit on monorepo main: streamChatMessage, requestWithRetry, ReadableStream all present in the root file
- [ ] Order #1419 (r3 new-file lane) is then closed as superseded

## Rollback
The attached artifact is documentation-only until applied; `git revert` the apply commit if needed.
