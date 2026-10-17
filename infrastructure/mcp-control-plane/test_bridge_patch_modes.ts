/**
 * #539 — Bridge dual-mode patch ingress test battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 * Covers: unified-diff parsing, in-memory apply (offsets, no-newline, CRLF),
 * fail-closed errors, and the mode dispatcher used by bridge.submit_patch.
 */
import { applyUnifiedDiff, parseUnifiedDiff, resolveFileContent } from "./src/lib/unified_diff.js";

let failures = 0;
function check(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}
function section(title: string): void {
  console.log(`\n=== ${title} ===`);
}

function throws(fn: () => unknown, needle: string): boolean {
  try {
    fn();
    return false;
  } catch (err) {
    return (err as Error).message.includes(needle);
  }
}

// ─── 1. Parsing ──────────────────────────────────────────────────────────────
section("1. parseUnifiedDiff (structure, counts, fail-closed)");
const SIMPLE_BASE = "alpha\nbeta\ngamma\ndelta\nepsilon\n";
const SIMPLE_DIFF = [
  "--- a/notes.txt",
  "+++ b/notes.txt",
  "@@ -2,3 +2,3 @@",
  " beta",
  "-gamma",
  "+GAMMA",
  " delta",
  "",
].join("\n");
const parsed1 = parseUnifiedDiff(SIMPLE_DIFF);
check("paths stripped of a/ b/ prefixes", parsed1.oldPath === "notes.txt" && parsed1.newPath === "notes.txt");
check("one hunk parsed", parsed1.hunks.length === 1);
check("hunk counts from header", parsed1.hunks[0].oldCount === 3 && parsed1.hunks[0].newCount === 3);

check("empty diff rejected", throws(() => parseUnifiedDiff(""), "empty diff"));
check("no hunks rejected", throws(() => parseUnifiedDiff("--- a/x\n+++ b/x\n"), "no hunks"));
check("missing headers rejected", throws(() => parseUnifiedDiff("@@ -1,1 +1,1 @@\n-a\n+b\n"), "missing ---/+++"));
check("bad count rejected", throws(
  () => parseUnifiedDiff("--- a/x\n+++ b/x\n@@ -1,5 +1,5 @@\n-a\n+b\n"),
  "old-side line count"
));
check("unrecognized line rejected", throws(
  () => parseUnifiedDiff("--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n*a\n"),
  "unexpected line"
));

// ─── 2. Apply: happy paths ───────────────────────────────────────────────────
section("2. applyUnifiedDiff (exact apply, offsets, multi-hunk)");
const applied1 = applyUnifiedDiff(SIMPLE_BASE, SIMPLE_DIFF);
check("single-hunk replacement", applied1.result === "alpha\nbeta\nGAMMA\ndelta\nepsilon\n", JSON.stringify(applied1.result));
check("hunksApplied reported", applied1.hunksApplied === 1);
check("zero offset reported", applied1.offsets.length === 1 && applied1.offsets[0] === 0);

// Addition-only hunk + subsequent hunk drift (offset handling).
const DRIFT_BASE = "one\ntwo\nthree\nfour\nfive\nsix\nseven\n";
const DRIFT_DIFF = [
  "--- a/drift.txt",
  "+++ b/drift.txt",
  "@@ -1,2 +1,3 @@",
  " one",
  "+one-and-a-half",
  " two",
  "@@ -6,2 +7,2 @@",
  " six",
  "-seven",
  "+six-appendix",
].join("\n");
const applied2 = applyUnifiedDiff(DRIFT_BASE, DRIFT_DIFF);
check("multi-hunk with drift applied", applied2.result === "one\none-and-a-half\ntwo\nthree\nfour\nfive\nsix\nsix-appendix\n", JSON.stringify(applied2.result));
check("second hunk offset recorded", applied2.offsets[1] === 1, `offsets=${JSON.stringify(applied2.offsets)}`);

// Deletion-only hunk.
const applied3 = applyUnifiedDiff("keep\ndrop-me\nkeep2\n", "--- a/f\n+++ b/f\n@@ -1,3 +1,2 @@\n keep\n-drop-me\n keep2\n");
check("deletion-only hunk", applied3.result === "keep\nkeep2\n");

// Pure insertion at top (count 0 old side).
const applied4 = applyUnifiedDiff("body\n", "--- a/f\n+++ b/f\n@@ -0,0 +1,2 @@\n+header1\n+header2\n");
check("creation-style insertion inside existing file", applied4.result === "header1\nheader2\nbody\n", JSON.stringify(applied4.result));

// ─── 3. No-newline-at-EOF handling ──────────────────────────────────────────
section("3. \\ No newline at end of file (both sides, verified not guessed)");
const NN_BASE = "last-old-line-no-newline";
const NN_DIFF = [
  "--- a/tail.txt",
  "+++ b/tail.txt",
  "@@ -1 +1 @@",
  "-last-old-line-no-newline",
  "+last-new-line-no-newline",
  "\\ No newline at end of file",
].join("\n");
const applied5 = applyUnifiedDiff(NN_BASE, NN_DIFF);
check("no-newline preserved on new side", applied5.result === "last-new-line-no-newline", JSON.stringify(applied5.result));

check("marker on old side vs newline-terminated base rejected", throws(
  () => applyUnifiedDiff("last-old-line-no-newline\n", NN_DIFF),
  "not EOF-without-newline"
));
check("missing marker vs newline-terminated base rejected", throws(
  () => applyUnifiedDiff(NN_BASE, "--- a/t\n+++ b/t\n@@ -1 +1 @@\n-last-old-line-no-newline\n+last-new-line\n"),
  "lacks the trailing newline"
));

// ─── 4. CRLF discipline (the #539 core motivation) ──────────────────────────
section("4. CRLF safety (no line-ending thrash)");
const CRLF_BASE = "alpha\r\nbeta\r\ngamma\r\n";
const CRLF_DIFF = "--- a/f\r\n+++ b/f\r\n@@ -2,2 +2,2 @@\r\n beta\r\n-gamma\r\n+GAMMA\r\n";
const applied6 = applyUnifiedDiff(CRLF_BASE, CRLF_DIFF);
check("CRLF round-trips byte-exactly", applied6.result === "alpha\r\nbeta\r\nGAMMA\r\n", JSON.stringify(applied6.result));
check("LF context against CRLF base fails closed", throws(
  () => applyUnifiedDiff(CRLF_BASE, "--- a/f\n+++ b/f\n@@ -2,2 +2,2 @@\n beta\n-gamma\n+GAMMA\n"),
  "context mismatch"
));

// ─── 5. Fail-closed application errors ──────────────────────────────────────
section("5. Apply fail-closed (ambiguity is an error, never a fuzz)");
check("context mismatch rejected", throws(
  () => applyUnifiedDiff("x\ny\nz\n", "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n A\n-B\n+C\n"),
  "context mismatch"
));
check("creation diff rejected", throws(
  () => applyUnifiedDiff("whatever\n", "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,1 @@\n+hi\n"),
  "creation diff"
));
check("deletion diff rejected", throws(
  () => applyUnifiedDiff("hi\n", "--- a/old.txt\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-hi\n"),
  "deletion diff"
));
check("overlap beyond offset window rejected", throws(
  () => applyUnifiedDiff(`${"filler\n".repeat(80)}target\n`, "--- a/f\n+++ b/f\n@@ -1,1 +1,1 @@\n-target\n+TARGET\n"),
  "context mismatch"
));

// ─── 6. Mode dispatcher (bridge.submit_patch integration shape) ─────────────
section("6. resolveFileContent (injectable fetcher, fail-closed modes)");
const full = await resolveFileContent({ path: "a.txt", content: "FULL" }, async () => "unused");
check("full_file passthrough", full.content === "FULL" && full.mode === "full_file");

const diffed = await resolveFileContent(
  { path: "b.txt", mode: "unified_diff", diff: SIMPLE_DIFF },
  async () => SIMPLE_BASE
);
check("unified_diff resolves via fetcher", diffed.content === "alpha\nbeta\nGAMMA\ndelta\nepsilon\n");
check("unified_diff reports hunk stats", diffed.hunksApplied === 1 && Array.isArray(diffed.offsets));

check("unified_diff on missing file rejected", await (async () => {
  try {
    await resolveFileContent({ path: "ghost.txt", mode: "unified_diff", diff: SIMPLE_DIFF }, async () => null);
    return false;
  } catch (err) {
    return (err as Error).message.includes("existing file");
  }
})());
check("full_file without content rejected", await (async () => {
  try {
    await resolveFileContent({ path: "a.txt" }, async () => null);
    return false;
  } catch (err) {
    return (err as Error).message.includes("requires content");
  }
})());
check("unified_diff without diff rejected", await (async () => {
  try {
    await resolveFileContent({ path: "b.txt", mode: "unified_diff" }, async () => "x");
    return false;
  } catch (err) {
    return (err as Error).message.includes("requires a diff");
  }
})());
check("both content and diff rejected", await (async () => {
  try {
    await resolveFileContent({ path: "b.txt", mode: "unified_diff", diff: SIMPLE_DIFF, content: "dup" }, async () => SIMPLE_BASE);
    return false;
  } catch (err) {
    return (err as Error).message.includes("exactly one");
  }
})());

// ─── Verdict ─────────────────────────────────────────────────────────────────
console.log("\n=============================================");
if (failures === 0) {
  console.log("ALL BRIDGE PATCH-MODE TESTS PASSED (#539)");
} else {
  console.error(`${failures} TEST(S) FAILED (#539)`);
}
process.exit(failures === 0 ? 0 : 1);
