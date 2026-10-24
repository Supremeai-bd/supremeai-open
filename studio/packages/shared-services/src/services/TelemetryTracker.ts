/**
 * TelemetryTracker — Self-healing patch acceptance tracking (platform-agnostic).
 * Levenshtein distance ব্যবহার করে patch কতটা মিলছিল তা মাপা হয়।
 * (বাহ্যিক dependency না রেখে একটি হালকা inline implementation ব্যবহার করা হয়েছে।)
 */

export type PatchStatus = 'ACCEPTED' | 'REJECTED' | 'MODIFIED';

export interface PatchTelemetry {
  errorId: string;
  filePath: string;
  status: PatchStatus;
  similarityScore: number;
}

export interface PatchAcceptance {
  errorId: string;
  filePath: string;
  status: PatchStatus;
  similarityScore: number;
}

/** Levenshtein distance — dynamic programming বড় string-এর জন্য অভিন্ন। */
export function levenshteinDistance(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  if (m > n) return levenshteinDistance(b, a);

  let prev = new Array<number>(m + 1).fill(0);
  let curr = new Array<number>(m + 1).fill(0);
  for (let i = 0; i <= m; i++) prev[i] = i;

  for (let j = 1; j <= n; j++) {
    curr[0] = j;
    for (let i = 1; i <= m; i++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[i] = Math.min(
        prev[i] + 1,      // deletion
        curr[i - 1] + 1,  // insertion
        prev[i - 1] + cost // substitution
      );
    }
    const tmp = prev;
    prev = curr;
    curr = tmp;
  }
  return prev[m];
}

export class TelemetryTracker {
  private static instance: TelemetryTracker | null = null;
  private activePatches = new Map<string, { originalErrorId: string; proposedPatch: string }>();

  private constructor() {}

  public static initialize(): TelemetryTracker {
    if (!TelemetryTracker.instance) {
      TelemetryTracker.instance = new TelemetryTracker();
    }
    return TelemetryTracker.instance;
  }

  public static getInstance(): TelemetryTracker {
    return TelemetryTracker.initialize();
  }

  public trackProposedPatch(filePath: string, errorId: string, patchText: string): void {
    this.activePatches.set(filePath, { originalErrorId: errorId, proposedPatch: patchText });
  }

  public evaluatePatch(filePath: string, savedText: string): PatchAcceptance | null {
    const patchData = this.activePatches.get(filePath);
    if (!patchData) return null;

    const proposedText = patchData.proposedPatch;
    const distance = levenshteinDistance(savedText, proposedText);
    const maxLength = Math.max(savedText.length, proposedText.length);
    const similarityScore = maxLength === 0 ? 1.0 : 1.0 - distance / maxLength;

    let status: PatchStatus = 'MODIFIED';
    if (similarityScore >= 0.98) {
      status = 'ACCEPTED';
    } else if (similarityScore <= 0.5) {
      status = 'REJECTED';
    }

    const result: PatchAcceptance = { errorId: patchData.originalErrorId, filePath, status, similarityScore };
    this.activePatches.delete(filePath);
    return result;
  }

  public async sendTelemetry(backendUrl: string, result: PatchAcceptance): Promise<void> {
    try {
      await fetch(`${backendUrl}/api/v1/swarm/telemetry/patch-result`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          error_id: result.errorId,
          patch_id: `patch-${Date.now()}`,
          file_path: result.filePath,
          status: result.status,
          similarity_score: result.similarityScore,
        }),
      });
      // eslint-disable-next-line no-console
      console.log(`[SupremeAI Telemetry] Sent: ${result.status} (Score: ${result.similarityScore.toFixed(2)})`);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[SupremeAI Telemetry] Failed to send telemetry:', err);
    }
  }
}