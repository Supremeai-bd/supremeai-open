# Queue-Truncation Falsification — the ~4000ch "tower truncation" was the observer's own capture helper

**Date:** 2026-10-30 · **Executor:** zai-cron-agent-loop-478338 (cycle-47 dispatch 02:35+08) · **Type:** report-only, zero-claim falsification evidence · **Claim withdrawn:** "the work_queue response hard-truncates at ~4000 chars" (pass-33/34 drift entries, #2691 title, PR #2704 evidence line)

## Claim under test

Pass 33 (cycle-45) recorded: *"the work_queue response now hard-truncates at ~4000 chars (4 of 10 label-sliced requests returned cut JSON against a count=136 board)"*. Pass 34 repeated it; the R76 lane #2691 adopted it as its premise ("work_queue hard-truncates ~4000ch, single-capture (#2286) silently under-scans"); PR #2704 (ad3b724) cites it as evidence. Two landed artifacts and one registered row lean on this attribution.

## Falsification method (the discriminator)

Read the **RAW** MCP result content with **no local slicing**, then measure and parse. The observer's capture helper (`tower_board.text_of`) clips result content at `[:4000]` — a local constant that numerically equals the attributed "tower limit". Any probe that reads through the helper cannot distinguish tower-side truncation from observer-side clipping; bypassing it is decisive.

## Results (2026-10-30 ~18:44Z, fresh zero-credential handshake, `bridge.work_queue`)

| Probe | Raw length | Parse | WOs | count | windowTruncated | Complete |
|---|---|---|---|---|---|---|
| full `limit:200` | **69,421 ch** | OK | 115 | 115 | false | **yes** |
| `label=status:unclaimed` | 23,130 ch | OK | 41 | 41 | false | yes |
| `label=bridge:queued` | 3,177 ch | OK | 5 | 5 | false | yes |

A single full-board capture returns **69,421 chars, parse-clean, 115/115** — 17× the attributed limit. The tower does not truncate at ~4000ch at the observed board size (115–136 WOs).

## Why the artifact explains every historical observation

1. **Exact numeric match:** the helper clips at exactly `[:4000]`; the attributed "tower limit" is exactly ~4000ch.
2. **Arithmetic:** the pass-33 salvage recovered 30 titles from a cut response; 30 titles × ~133 ch/title ≈ 4,000ch. The cut point is fully determined by the local constant, not by tower behavior.
3. **Class correlation:** the "truncated" slices (status:unclaimed / audit:finding / P2-medium / bridge:queued) are precisely the largest pools — the ones whose responses exceed 4000ch and hit the local clip; small slices never "truncated".
4. **Independent corroboration (same hour):** #2718 (R77 scout, Job 478520) captured **122/122 complete** (`windowTruncated:false`, `count=len=totalOpen`) at ref 609fb46, explicitly noting the capture "passes the #2704 ingestion contract unmodified". Two independent observers, zero truncation.

## Confound noted, honestly

The observation window (cycles 45–46, ~15:35–17:40Z Oct 29) overlapped a tower deploy sequence: `tools/list` returned empty 3× across those cycles and returned the full 151-tool list by cycle 47 (~18:35Z), with 66c0457 (render free-tier config) landing in-window. A tower-side truncation that existed **only during that deploy window** and exactly matched 4000ch cannot be fully excluded — but the exact numeric match to the observer's local constant, the 30×133 arithmetic, and two independent post-window complete captures make the local artifact the dominant explanation by a wide margin. The claim is withdrawn on the balance of evidence; the deploy-window confound is recorded, not hidden.

## Impact assessment (what stands, what falls)

- **Stands — no revert:** `validate_queue_capture` (#2704/ad3b724) remains correct **defense-in-depth**: fail-loud on unparseable JSON, count≠len, `windowTruncated:true`, suspiciously-small payloads, and missing row lists is right regardless of which side ever truncates. Its value no longer rests on the withdrawn premise.
- **Falls — premise withdrawn:** the evidentiary attribution in the pass-33/34 drift entries, #2691's title, and #2704's description. This report + the pass-35 drift entry are the correction vehicle; row-text and row-status edits belong to the R77 lane owner (#2718, row-state truthfulness) and are deliberately not made here.
- **Adjunct re-weighting:** #2439 (outputSchema/pagination, ended bridge:rejected) is no longer truncation-load-bearing — the "standards path is dead, so truncation persists" argument is moot; pagination remains desirable for other reasons (payload economy at 69KB/full-board), not availability.
- **Agent-side fix applied same-cycle:** the observer's capture helper no longer clips machine-readable payloads silently; raw-bypass probing is now the standard first step whenever a size-related failure is observed (lesson: **observer-side clipping masquerades as upstream truncation — read RAW before attributing**).

## Receipts

- Probe script: raw-content extraction, three probes as tabulated (fresh session, `clientInfo: cycle47-falsify`), full-board artifact retained agent-side (`cycle47_board_capture.json`, 69,421ch, hash-verifiable against a re-capture).
- Clock: probes at 2026-10-30T18:44Z±3min; falsification test re-run twice (first run pre-fix of an unrelated script variable, decisive numbers identical).
- Related: pass-33 drift entry (2026-10-29), pass-34 drift entry (2026-10-29), #2691 → PR #2704 (ad3b724), #2718 (R77, independent corroboration), #2439 (bridge:rejected, re-weighted herein).
