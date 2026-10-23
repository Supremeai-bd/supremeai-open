/**
 * Golden-file tests for the bridge-lane unified-diff applier's
 * EOF / trailing-newline semantics (#539 defect-class guard).
 *
 * Background: the "\ No newline at end of file" marker is the most
 * error-prone area of the applier. A one-sided marker was previously
 * mis-attributed to BOTH sides, silently dropping or adding the final
 * newline, and a last hunk that did not reach EOF unconditionally
 * appended "\n". Each case below pins the EXACT expected output
 * (golden), so any future drift in newline handling fails loudly.
 *
 * Offline, pure, zero-dep (house style: node:assert + plain script).
 * Run: tsx scripts/test-runner.ts test_unified_diff_eof.ts
 */

import assert from "node:assert/strict";
import { applyUnifiedDiff } from "./src/lib/unified_diff.js";

interface GoldenCase {
  name: string;
  base: string;
  diff: string;
  expected: string;
}

const h = (body: string[]) => ["--- a/file.txt", "+++ b/file.txt", "@@ -1,3 +1,3 @@", ...body].join("\n");

const GOLDEN: GoldenCase[] = [
  {
    // Diff ADDS a trailing newline: marker after the last "-" line only.
    name: "adds trailing newline at EOF",
    base: "line1\nline2\nline3",
    diff: h([" line1", " line2", "-line3", "\\ No newline at end of file", "+line3"]),
    expected: "line1\nline2\nline3\n",
  },
  {
    // Diff REMOVES the trailing newline: marker after the last "+" line only.
    name: "removes trailing newline at EOF",
    base: "line1\nline2\nline3\n",
    diff: h([" line1", " line2", "-line3", "+line3", "\\ No newline at end of file"]),
    expected: "line1\nline2\nline3",
  },
  {
    // Both sides lack the newline: two markers, one per side.
    name: "both sides lack trailing newline",
    base: "line1\nline2\nline3",
    diff: h([" line1", " line2", "-line3", "\\ No newline at end of file", "+line3-modified", "\\ No newline at end of file"]),
    expected: "line1\nline2\nline3-modified",
  },
  {
    // Plain mid-file change: base newline state carried into the result.
    name: "plain mid-file change keeps trailing newline",
    base: "a\nb\nc\n",
    diff: h([" a", "-b", "+B", " c"]),
    expected: "a\nB\nc\n",
  },
  {
    // Last hunk does NOT reach EOF: base WITHOUT trailing newline must be
    // preserved (no silent "\n" append).
    name: "non-EOF hunk preserves base without trailing newline",
    base: "a\nb\nc",
    diff: ["--- a/f", "+++ b/f", "@@ -1,1 +1,1 @@", "-a", "+A"].join("\n"),
    expected: "A\nb\nc",
  },
  {
    // Marker after "-" line while "+" lines follow: old side lacks the
    // newline, new side (with added lines) HAS one.
    name: "old-side marker with appended lines gains newline",
    base: "x\ny",
    diff: ["--- a/f", "+++ b/f", "@@ -1,2 +1,3 @@", " x", "-y", "\\ No newline at end of file", "+y2", "+z"].join("\n"),
    expected: "x\ny2\nz\n",
  },
  {
    // Two hunks applied in order, second rewrites the EOF line.
    name: "multi-hunk monotone apply",
    base: "a\nb\nc\nd\ne\n",
    diff: ["--- a/f", "+++ b/f", "@@ -1,2 +1,2 @@", " a", "-b", "+B", "@@ -4,2 +4,2 @@", " d", "-e", "+E"].join("\n"),
    expected: "a\nB\nc\nd\nE\n",
  },
];

// Fail-closed guards: (name, base, diff, errorFragment)
interface GuardCase {
  name: string;
  base: string;
  diff: string;
  errorFragment: string;
}

const GUARDS: GuardCase[] = [
  {
    name: "creation diff rejected",
    base: "x\n",
    diff: ["--- /dev/null", "+++ b/f", "@@ -0,0 +1,1 @@", "+x"].join("\n"),
    errorFragment: "creation diff",
  },
  {
    name: "deletion diff rejected",
    base: "x\n",
    diff: ["--- a/f", "+++ /dev/null", "@@ -1,1 +0,0 @@", "-x"].join("\n"),
    errorFragment: "deletion diff",
  },
  {
    name: "context mismatch rejected",
    base: "a\nb\nc\n",
    diff: h([" a", "-z", "+Z", " c"]),
    errorFragment: "context mismatch",
  },
  {
    name: "malformed @@ header rejected",
    base: "a\n",
    diff: ["--- a/f", "+++ b/f", "@@ junk @@", " a"].join("\n"),
    errorFragment: "malformed @@ header",
  },
  {
    // Hunk reaches EOF, base lacks the newline, but the diff carries NO
    // old-side marker → inconsistent diff → fail-closed.
    name: "EOF hunk without required old-side marker rejected",
    base: "a\nb\nc",
    diff: h([" a", " b", "-c", "+C"]),
    errorFragment: "base lacks the trailing newline",
  },
  {
    // Old-side marker present but base HAS the trailing newline → fail-closed.
    name: "old-side marker against newline-terminated base rejected",
    base: "a\nb\nc\n",
    diff: h([" a", " b", "-c", "\\ No newline at end of file", "+C"]),
    errorFragment: "not EOF-without-newline",
  },
];

let passed = 0;
for (const c of GOLDEN) {
  const result = applyUnifiedDiff(c.base, c.diff);
  assert.equal(result.result, c.expected, `golden case '${c.name}': exact output drift`);
  passed++;
  console.log(`✔ ${c.name}`);
}
for (const c of GUARDS) {
  assert.throws(
    () => applyUnifiedDiff(c.base, c.diff),
    (err: Error) => err.message.includes(c.errorFragment),
    `guard case '${c.name}' must fail-closed with '${c.errorFragment}'`
  );
  passed++;
  console.log(`✔ ${c.name} (fail-closed)`);
}

console.log(`unified_diff EOF golden tests passed (${passed} cases)`);
