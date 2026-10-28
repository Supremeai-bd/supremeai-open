import assert from "node:assert/strict";
import {
  QUEUE_LIMIT_MAX,
  QUEUE_MAX_PAGES,
  QUEUE_PAGE_SIZE,
  buildQueueQueryUrl,
  mergeIssuePages,
  normalizeQueueItem,
  queueFromIssues,
} from "./src/tools/bridge.tools.js";

/**
 * Queue-fidelity contract tests (#2115/#2123).
 *
 * The tower's bridge.work_queue must ENUMERATE the open board, not sample
 * one page of the newest creations. Live evidence 2026-10-28: a single
 * per_page=50 fetch returned 20-35 rows while 98 issues were open; rows
 * vanished as they fell past the page window (~2.5h-6.5h "age cutoff")
 * while bridge_read_feedback still resolved them by number.
 *
 * Regression scenarios encoded below:
 *   R1: URL carries page + per_page=100 paging contract.
 *   R2: page merge dedupes overlapping pages (GitHub pagination races).
 *   R3: an old open issue survives pagination even when the newest page is
 *       saturated with PRs (the exact #1912/#1769 drop).
 *   R4: limit slice caps at QUEUE_LIMIT_MAX (200), not the old 50.
 *   R5: short page terminates pagination (caller-side contract, mirrored
 *       by the Python reference self-test).
 *   R6: state_reason passthrough (#2218) — closed-as-completed vs
 *       closed-as-not_planned machine-readable Tower-only; absent or
 *       non-string upstream values normalize to null.
 *   R7: label-filtered bridge-state queries are not self-defeating
 *       (#2163 arc) — asking for bridge:rejected/bridge:landed returns
 *       those rows; the default board keeps filtering them.
 */

const REPO = "Supremeai-bd/supremeai-open";

function issue(n: number, opts: { pr?: boolean; state?: string; labels?: unknown[] } = {}) {
  const row: Record<string, unknown> = {
    number: n,
    title: `row-${n}`,
    state: opts.state ?? "open",
    labels: opts.labels ?? [],
    html_url: `https://example.test/${n}`,
    created_at: "2026-10-28T00:00:00Z",
    updated_at: "2026-10-28T00:00:00Z",
    comments: 0,
  };
  if (opts.pr) row["pull_request"] = { url: "https://example.test/pr" };
  return row as never; // RawIssue shape
}

// ─── R1: paging URL contract ────────────────────────────────────────────────
{
  const u1 = buildQueueQueryUrl(REPO, null, 1);
  assert.ok(u1.includes("state=open"), u1);
  assert.ok(u1.includes(`per_page=${QUEUE_PAGE_SIZE}`), u1);
  assert.ok(u1.includes("page=1"), u1);
  assert.ok(!u1.includes("labels="), u1);
  const u3 = buildQueueQueryUrl(REPO, "status:unclaimed", 3);
  assert.ok(u3.includes("page=3"), u3);
  assert.ok(u3.includes("labels=status%3Aunclaimed"), u3);
  const u0 = buildQueueQueryUrl(REPO, null, 0); // clamp to 1
  assert.ok(u0.includes("page=1"), u0);
  console.log("  ✓ R1 buildQueueQueryUrl: page/per_page/label contract");
}

// ─── R2: merge dedupes overlapping pages ────────────────────────────────────
{
  const p1 = [issue(2126), issue(2125), issue(2124)];
  const p2 = [issue(2124), issue(2123), issue(2122)]; // 2124 overlaps
  const merged = mergeIssuePages([p1, p2]);
  const nums = merged.map((r) => (r as { number: number }).number);
  assert.deepEqual(nums.sort((a, b) => b - a), [2126, 2125, 2124, 2123, 2122]);
  assert.equal(mergeIssuePages([]).length, 0);
  assert.equal(mergeIssuePages([[] as never[]]).length, 0);
  assert.equal(mergeIssuePages(undefined as never).length, 0);
  console.log("  ✓ R2 mergeIssuePages: flatten + dedupe by number");
}

// ─── R3: the #1912 drop cannot recur ────────────────────────────────────────
{
  // One saturated page: 40 PRs + 10 newest issues (page-1 shape under the
  // old per_page=50 single fetch). The old open issue #1912 lives on page 2.
  const prs = Array.from({ length: 40 }, (_, i) => issue(3000 - i, { pr: true }));
  const newest = Array.from({ length: 10 }, (_, i) => issue(2126 - i));
  const old = issue(1912, { labels: [{ name: "status:unclaimed" }] });
  const page1 = [...prs, ...newest];
  const page2 = [old, issue(1911), issue(1910)];

  const single = queueFromIssues(mergeIssuePages([page1]), 200);
  assert.ok(!single.some((w) => w.number === 1912), "sanity: single page drops #1912");

  const paged = queueFromIssues(mergeIssuePages([page1, page2]), 200);
  assert.ok(paged.some((w) => w.number === 1912), "pagination must restore #1912");
  assert.equal(paged.length, 13, "all open non-PR rows from both pages survive (10+3, PRs filtered)");
  console.log("  ✓ R3 saturated page + PR pollution no longer drops open work");
}

// ─── R4: limit slice honors QUEUE_LIMIT_MAX ─────────────────────────────────
{
  const rows = Array.from({ length: 250 }, (_, i) => issue(2500 - i));
  const q = queueFromIssues(mergeIssuePages([rows]), QUEUE_LIMIT_MAX);
  assert.equal(q.length, QUEUE_LIMIT_MAX);
  assert.equal(q[0].number, 2500);
  const qTiny = queueFromIssues(mergeIssuePages([rows]), 3);
  assert.equal(qTiny.length, 3);
  const qDefault = queueFromIssues(mergeIssuePages([rows]));
  assert.equal(qDefault.length, 20, "default limit stays 20");
  console.log(`  ✓ R4 slice cap raised 50 -> ${QUEUE_LIMIT_MAX}, default still 20`);
}

// ─── R5: constants contract (mirrored by scripts/tower reference) ───────────
{
  assert.equal(QUEUE_PAGE_SIZE, 100);
  assert.ok(QUEUE_MAX_PAGES >= 2, "cap must allow at least 2 pages");
  assert.equal(QUEUE_LIMIT_MAX, 200);
  console.log("  ✓ R5 paging constants pinned for parity with the reference");
}

// ─── R6: state_reason passthrough (#2218) ───────────────────────────────────
{
  const done = normalizeQueueItem({ number: 2187, state: "closed", state_reason: "completed" } as never);
  assert.equal(done.stateReason, "completed");
  assert.equal(done.state, "closed");
  assert.equal(
    normalizeQueueItem({ state: "closed", state_reason: "not_planned" } as never).stateReason,
    "not_planned",
  );
  assert.equal(
    normalizeQueueItem({ state: "open", state_reason: "reopened" } as never).stateReason,
    "reopened",
  );
  assert.equal(
    normalizeQueueItem({ state: "open" } as never).stateReason,
    null,
    "absent state_reason normalizes to null",
  );
  assert.equal(
    normalizeQueueItem({ state: "open", state_reason: 42 } as never).stateReason,
    null,
    "non-string state_reason normalizes to null",
  );
  const withReason = (n: number, reason: unknown) =>
    ({
      number: n,
      title: `row-${n}`,
      state: "open",
      labels: [],
      html_url: `https://example.test/${n}`,
      created_at: "2026-10-28T00:00:00Z",
      updated_at: "2026-10-28T00:00:00Z",
      comments: 0,
      state_reason: reason,
    }) as never;
  const q = queueFromIssues([withReason(2218, "reopened"), withReason(2219, null)], 10);
  const row = q.find((w) => w.number === 2218);
  assert.ok(row, "open row with state_reason survives the queue filters");
  assert.equal(row?.stateReason, "reopened", "queue rows carry stateReason through");
  console.log("  ✓ R6 stateReason passthrough (#2218): completed/not_planned/reopened/null/junk");
}

// ─── R7: label-filtered bridge-state queries (#2163 arc) ────────────────────
{
  const rejRow = issue(2020, { labels: ["bridge:rejected"] });
  const landedRow = issue(2021, { labels: [{ name: "bridge:landed" }] });
  const plain = issue(2022);

  const board = queueFromIssues([rejRow, landedRow, plain], 10);
  assert.ok(
    !board.some((w) => w.number === 2020 || w.number === 2021),
    "default board keeps filtering bridge-state rows (unchanged contract)",
  );

  const targeted = queueFromIssues([rejRow, landedRow, plain], 10, { keepBridgeStateRows: true });
  assert.deepEqual(
    targeted.map((w) => w.number),
    [2022, 2021, 2020],
    "targeted bridge-state query returns exactly the asked-for rows",
  );

  console.log("  ✓ R7 label-filtered bridge-state queries survive (#2163 arc)");
}

console.log("Queue-fidelity contract tests passed (#2115/#2123)");
