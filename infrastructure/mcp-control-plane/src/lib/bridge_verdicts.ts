/**
 * #2344 — intake-verdict read-side fallback (Option A from the verdict-stall
 * tracker): make landed work orders machine-readable again.
 *
 * Pure, offline helpers (no network, no env) so the regression battery
 * (test_bridge_verdicts.ts) can replay the live cohort deterministically —
 * same discipline as bridge_dedup.ts (#2136/#2227) and bridge_staleness.ts
 * (#2333).
 *
 * Failure being fixed (live cohort, 2026-10-28 ~23:3xZ, #2344 evidence):
 * the intake-verdict plane NEVER writes for anonymous-bridge work orders —
 * 7 of the filer's own WOs across 5 cycles all show latestVerdict=null +
 * verdictHistory=[] in fresh bridge_read_feedback probes, 5 of them with
 * stale bridge:queued labels despite byte-verified landings, 2 correctly
 * landed-labeled yet still verdict-null. Guard lane #2203 independently
 * logged the same plane. The intake service (src/events/bridge_intake.ts)
 * only processes signed webhook events; anonymous zero-credential WOs never
 * pass through a verdict-writing gate, so the feedbackTool contract string
 * ("machine-readable intake verdicts (APPLIED/REJECTED + reason)") promises
 * data the plane never produces for exactly the WOs the bridge creates.
 *
 * Option A contract (read-side, no write-path risk):
 * - An intake-bot verdict exists (raw parse non-null) -> pass through
 *   unchanged, verdictSource = "intake-bot" (nothing changes for WOs the
 *   plane DOES serve).
 * - No intake verdict + labels contain `bridge:landed` + state `closed`
 *   -> derive APPLIED_LABEL_DERIVED as latestVerdict, verdictSource =
 *   "label-fallback"; the raw absence is preserved as intakeVerdict: null
 *   (auditability: the derived verdict never masquerades as an intake-bot
 *   one).
 * - Anything else (open WOs, in-gates, plain queued) -> unchanged nulls,
 *   verdictSource = null.
 * verdictHistory stays pure intake-bot history — the fallback never pollutes
 * the historical record it derives from.
 */

export interface IntakeVerdictLike {
  verdict: string;
  task: string | null;
  reason: string | null;
  repo: string | null;
  pr: string | null;
  at: string | null;
}

export type VerdictSource = "intake-bot" | "label-fallback" | null;

export interface LabelFallbackResult {
  latestVerdict: IntakeVerdictLike | null;
  intakeVerdict: IntakeVerdictLike | null;
  verdictSource: VerdictSource;
}

export const LABEL_DERIVED_VERDICT = "APPLIED_LABEL_DERIVED";
export const LABEL_DERIVED_REASON =
  "label-fallback (#2344 Option A): bridge:landed + state=closed with no intake-verdict record — derived read-side; the verdict-writing plane has never fired for anonymous-bridge WOs.";

/**
 * Derive the read-side fallback verdict for one work order.
 * Pure: state + labels + already-parsed raw verdict in, verdict shape out.
 */
export function applyLabelFallback(
  state: string,
  labels: readonly string[],
  rawLatestVerdict: IntakeVerdictLike | null
): LabelFallbackResult {
  // The plane served this WO: pass through untouched, source attributed.
  if (rawLatestVerdict) {
    return { latestVerdict: rawLatestVerdict, intakeVerdict: rawLatestVerdict, verdictSource: "intake-bot" };
  }
  // Landed + closed with no verdict record: the #2344 cohort shape. Derive
  // from what the read side already sees — labels and state are the same
  // bytes a human uses to conclude "landed".
  const landed = labels.some((l) => l === "bridge:landed");
  if (landed && state === "closed") {
    return {
      latestVerdict: {
        verdict: LABEL_DERIVED_VERDICT,
        task: null,
        reason: LABEL_DERIVED_REASON,
        repo: null,
        pr: null,
        at: null,
      },
      intakeVerdict: null,
      verdictSource: "label-fallback",
    };
  }
  // Open / in-gates / queued / rejected-without-record: no derivation — the
  // tracker's spec deliberately covers only the landed class; inventing a
  // REJECTED_LABEL_DERIVED from a stale bridge:rejected label would launder
  // the #2275 false-rejection class into machine-readable "truth".
  return { latestVerdict: null, intakeVerdict: null, verdictSource: null };
}
