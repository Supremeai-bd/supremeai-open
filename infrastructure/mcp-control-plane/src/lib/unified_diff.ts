/**
 * #539 — Unified-diff ingress for the bridge patch lane (pure, zero-dep).
 *
 * House style: pure functions, fail-closed errors, offline-testable.
 * The applier intentionally mirrors `git apply` semantics that matter for
 * the bridge lane, WITHOUT requiring a server-side git checkout:
 *   - exact context matching with bounded offset search (±50 lines),
 *   - monotone, non-overlapping hunks applied in order,
 *   - "\ No newline at end of file" handling on both sides,
 *   - CRLF-safe: context must match byte-exactly, so no line-ending
 *     normalization ever happens (that is the whole point of #539).
 * Anything ambiguous is an ERROR, never a silent fuzz.
 */

export interface DiffHunk {
  oldStart: number; // 1-based, from the @@ header
  oldCount: number;
  newStart: number; // 1-based, from the @@ header
  newCount: number;
  /** Raw hunk-body lines in order (' ', '-', '+' prefixed; '\' markers kept). */
  raw: string[];
}

export interface ParsedDiff {
  oldPath: string;
  newPath: string;
  hunks: DiffHunk[];
}

export interface AppliedDiff {
  result: string;
  hunksApplied: number;
  /** Per-hunk applied offset (matched position - header position), 0-based. */
  offsets: number[];
}

const MAX_OFFSET = 50;

function stripPathPrefix(raw: string): string {
  let p = raw.trim();
  if (p === "/dev/null") return p;
  // Remove git-style a/ or b/ prefixes (also tolerate quoted paths).
  p = p.replace(/^"(.*)"$/, "$1");
  if (p.startsWith("a/") || p.startsWith("b/")) p = p.slice(2);
  // Timestamp suffixes after a tab are ignored.
  const tab = p.indexOf("\t");
  if (tab >= 0) p = p.slice(0, tab);
  return p.trim();
}

function parseHunkHeader(line: string, index: number): DiffHunk {
  const m = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
  if (!m) {
    throw new Error(`hunk #${index + 1}: malformed @@ header: ${line.slice(0, 60)}`);
  }
  return {
    oldStart: parseInt(m[1], 10),
    oldCount: m[2] === undefined ? 1 : parseInt(m[2], 10),
    newStart: parseInt(m[3], 10),
    newCount: m[4] === undefined ? 1 : parseInt(m[4], 10),
    raw: [],
  };
}

/** Parse a git unified diff. Fail-closed on any structural problem. */
export function parseUnifiedDiff(diff: string): ParsedDiff {
  if (typeof diff !== "string" || diff.trim().length === 0) {
    throw new Error("empty diff");
  }
  const lines = diff.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();

  let oldPath: string | null = null;
  let newPath: string | null = null;
  const hunks: DiffHunk[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("diff --git ")) {
      i += 1;
      continue;
    }
    if (line.startsWith("--- ")) {
      oldPath = stripPathPrefix(line.slice(4));
      i += 1;
      continue;
    }
    if (line.startsWith("+++ ")) {
      newPath = stripPathPrefix(line.slice(4));
      i += 1;
      continue;
    }
    if (line.startsWith("@@ ")) {
      const hunk = parseHunkHeader(line, hunks.length);
      i += 1;
      let oldSeen = 0;
      let newSeen = 0;
      let noNewlineOld = false;
      let noNewlineNew = false;
      while (i < lines.length) {
        const body = lines[i];
        if (body.startsWith("@@ ") || body.startsWith("diff --git ") || body.startsWith("--- ")) break;
        if (body.startsWith("\\")) {
          // "\ No newline at end of file" — keep it in raw so the applier
          // can verify EOF-newline semantics on both sides.
          hunk.raw.push(body);
          i += 1;
          continue;
        }
        if (body.startsWith(" ") || body === "") {
          oldSeen += 1;
          newSeen += 1;
          hunk.raw.push(body === "" ? " " : body);
        } else if (body.startsWith("-")) {
          oldSeen += 1;
          hunk.raw.push(body);
        } else if (body.startsWith("+")) {
          newSeen += 1;
          hunk.raw.push(body);
        } else {
          throw new Error(`hunk #${hunks.length + 1}: unexpected line outside hunk body: ${body.slice(0, 60)}`);
        }
        i += 1;
      }
      if (hunk.oldCount !== 0 && oldSeen !== hunk.oldCount) {
        throw new Error(`hunk #${hunks.length + 1}: old-side line count ${oldSeen} != header ${hunk.oldCount}`);
      }
      if (hunk.newCount !== 0 && newSeen !== hunk.newCount) {
        throw new Error(`hunk #${hunks.length + 1}: new-side line count ${newSeen} != header ${hunk.newCount}`);
      }
      if (oldSeen === 0 && newSeen === 0) {
        throw new Error(`hunk #${hunks.length + 1}: empty hunk body`);
      }
      // Carry markers on the hunk object via a hidden convention: they are
      // re-derived during apply from raw + the '\' scan, so nothing to store.
      hunks.push(hunk);
      continue;
    }
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    throw new Error(`unrecognized diff line ${i + 1}: ${line.slice(0, 60)}`);
  }

  if (!oldPath || !newPath) {
    throw new Error("missing ---/+++ file headers");
  }
  if (hunks.length === 0) {
    throw new Error("diff contains no hunks");
  }
  return { oldPath, newPath, hunks };
}

function hunkOldSide(hunk: DiffHunk): string[] {
  const out: string[] = [];
  for (const raw of hunk.raw) {
    if (raw.startsWith("\\")) continue;
    if (raw.startsWith("+")) continue;
    out.push(raw.slice(1));
  }
  return out;
}

function hunkNewSide(hunk: DiffHunk): string[] {
  const out: string[] = [];
  for (const raw of hunk.raw) {
    if (raw.startsWith("\\")) continue;
    if (raw.startsWith("-")) continue;
    out.push(raw.slice(1));
  }
  return out;
}

/**
 * Scan a hunk's raw body for the "\ No newline" markers.
 * Returns { old: boolean; new: boolean }.
 *
 * git semantics (defect-class fix): a "\" marker applies ONLY to the
 * hunk-body line it immediately follows — "-" or " " → the OLD side,
 * "+" → the NEW side. A side "lacks the trailing newline" iff its FINAL
 * body line is directly followed by the marker. The previous heuristic
 * (any marker ⇒ both sides) mis-attributed one-sided markers and either
 * silently dropped the trailing newline (diff ADDS a newline at EOF) or
 * false-rejected a valid diff (diff REMOVES a newline at EOF).
 */
function scanNoNewline(hunk: DiffHunk): { old: boolean; new: boolean } {
  let lastOldIdx = -1;
  let lastNewIdx = -1;
  for (let k = 0; k < hunk.raw.length; k += 1) {
    const l = hunk.raw[k];
    if (l.startsWith("\\")) continue;
    if (l.startsWith("+")) lastNewIdx = k;
    else lastOldIdx = k; // "-" or " "
  }
  const followsMarker = (idx: number) =>
    idx >= 0 && idx + 1 < hunk.raw.length && hunk.raw[idx + 1].startsWith("\\");
  return { old: followsMarker(lastOldIdx), new: followsMarker(lastNewIdx) };
}

/**
 * Apply a unified diff to `base` content. Fail-closed:
 *  - creation/deletion diffs rejected (bridge lane never creates via diff),
 *  - hunks must apply in order without overlap,
 *  - exact context match with bounded ±MAX_OFFSET search,
 *  - no-newline-at-EOF markers verified against the base, never guessed.
 */
export function applyUnifiedDiff(base: string, diff: string): AppliedDiff {
  const parsed = parseUnifiedDiff(diff);
  if (parsed.oldPath === "/dev/null") {
    throw new Error("creation diff (--- /dev/null) cannot be applied; use mode full_file to create files");
  }
  if (parsed.newPath === "/dev/null") {
    throw new Error("deletion diff (+++ /dev/null) is not supported by the bridge lane");
  }

  const baseHasTrailingNewline = base.endsWith("\n");
  const logical = base.length === 0 ? [] : base.split("\n");
  if (baseHasTrailingNewline) logical.pop();

  const lines = logical;
  let offset = 0;
  let cursor = 0; // first logical line index not yet consumed
  const offsets: number[] = [];

  // Pre-scan markers.
  const markers = parsed.hunks.map(scanNoNewline);

  // Whether the LAST hunk's new side reaches EOF (i.e. it rewrites the
  // final line of the result). Only then does its new-side marker decide
  // the trailing newline; otherwise the base's EOF state is preserved.
  let lastHunkEndsAtEof = false;

  for (let h = 0; h < parsed.hunks.length; h += 1) {
    const hunk = parsed.hunks[h];
    const marker = markers[h];
    const oldSide = hunkOldSide(hunk);
    const newSide = hunkNewSide(hunk);

    if (oldSide.length !== hunk.oldCount) {
      throw new Error(`hunk #${h + 1}: reconstructed old-side ${oldSide.length} lines != header ${hunk.oldCount}`);
    }
    if (newSide.length !== hunk.newCount) {
      throw new Error(`hunk #${h + 1}: reconstructed new-side ${newSide.length} lines != header ${hunk.newCount}`);
    }

    const headerPos = hunk.oldStart - 1 + offset;
    let matched = -1;
    for (let probe = 0; probe <= MAX_OFFSET; probe += 1) {
      for (const candidate of probe === 0 ? [headerPos] : [headerPos + probe, headerPos - probe]) {
        if (candidate < cursor) continue;
        if (candidate + oldSide.length > lines.length) continue;
        let ok = true;
        for (let k = 0; k < oldSide.length; k += 1) {
          if (lines[candidate + k] !== oldSide[k]) {
            ok = false;
            break;
          }
        }
        if (ok) {
          matched = candidate;
          break;
        }
      }
      if (matched >= 0) break;
    }
    if (matched < 0) {
      throw new Error(
        `hunk #${h + 1}: context mismatch — no match for old-side block within ±${MAX_OFFSET} lines of line ${headerPos + 1}`
      );
    }

    // No-newline verification (old side): marker ⇔ EOF-lacking-newline.
    const reachesEof = matched + oldSide.length === lines.length;
    if (marker.old) {
      if (!reachesEof || baseHasTrailingNewline) {
        throw new Error(`hunk #${h + 1}: "\\ No newline" marker on old side but the base region is not EOF-without-newline`);
      }
    } else if (reachesEof && !baseHasTrailingNewline && oldSide.length > 0) {
      throw new Error(`hunk #${h + 1}: hunk reaches EOF but base lacks the trailing newline the diff expects`);
    }

    // Overlap guard (monotone, non-overlapping hunks).
    if (matched < cursor) {
      throw new Error(`hunk #${h + 1}: overlaps previously applied hunks`);
    }

    lines.splice(matched, oldSide.length, ...newSide);
    offset += newSide.length - oldSide.length;
    offsets.push(matched - (hunk.oldStart - 1));
    cursor = matched + newSide.length;
    if (h === parsed.hunks.length - 1) {
      lastHunkEndsAtEof = matched + newSide.length === lines.length;
    }
  }

  // Trailing-newline resolution for the result.
  //  - Last hunk rewrites the final line: git emits the new-side "\ No
  //    newline" marker iff the new final line lacks the trailing newline,
  //    so append "\n" iff that marker is absent.
  //  - Last hunk does NOT reach EOF: everything after it is unchanged, so
  //    the result must preserve the BASE's trailing-newline state instead
  //    of unconditionally appending "\n".
  const lastMarker = markers[markers.length - 1];
  const result = lines.join("\n") +
    (lastHunkEndsAtEof ? (lastMarker.new ? "" : "\n") : (baseHasTrailingNewline ? "\n" : ""));
  return { result, hunksApplied: parsed.hunks.length, offsets };
}

/** Per-file input for the bridge lane (mirrors the tool schema, loose). */
export interface PatchFileInput {
  path: string;
  content?: string;
  mode?: "full_file" | "unified_diff";
  diff?: string;
}

/**
 * Resolve one patch file's final content (mode dispatcher).
 * `fetchCurrent` returns the branch-tip content for a path, or null when the
 * file does not exist. Injectable for offline tests.
 */
export async function resolveFileContent(
  file: PatchFileInput,
  fetchCurrent: (path: string) => Promise<string | null>
): Promise<{ content: string; mode: "full_file" | "unified_diff"; hunksApplied?: number; offsets?: number[] }> {
  const mode = file.mode ?? "full_file";
  if (mode === "full_file") {
    if (typeof file.content !== "string") {
      throw new Error(`file '${file.path}': mode full_file requires content`);
    }
    // Zero-Corrupted-Payload Invariant: Reject raw diff headers submitted as full_file content
    const firstLines = file.content.slice(0, 500).split(/\r?\n/).slice(0, 5);
    for (const line of firstLines) {
      if (/^diff --git\s|^index [0-9a-f]{7,}\.\./.test(line)) {
        throw new Error(
          `file '${file.path}': raw unified diff header detected in full_file content. ` +
          `Use mode: 'unified_diff' with diff field, or provide clean source code without git diff headers.`
        );
      }
    }
    return { content: file.content, mode };
  }
  // unified_diff
  if (typeof file.diff !== "string" || file.diff.length === 0) {
    throw new Error(`file '${file.path}': mode unified_diff requires a diff`);
  }
  if (file.content !== undefined) {
    throw new Error(`file '${file.path}': send exactly one of content (full_file) or diff (unified_diff)`);
  }
  const current = await fetchCurrent(file.path);
  if (current === null || current === undefined) {
    throw new Error(`file '${file.path}': unified_diff requires an existing file; use mode full_file to create it`);
  }
  const applied = applyUnifiedDiff(current, file.diff);
  return { content: applied.result, mode, hunksApplied: applied.hunksApplied, offsets: applied.offsets };
}
