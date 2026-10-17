/**
 * Federation Cockpit — telemetry logic test battery.
 *
 * Zero-dependency, runner-agnostic: execute directly (bun tests/telemetryClient.test.ts)
 * and it self-asserts, prints per-check results, exits non-zero on failure.
 * Covers normalizeSnapshot, CockpitSSEParser, and TelemetryClient with an
 * injected fetch — no network, no component renderer.
 */

import {
  CockpitSSEParser,
  TelemetryClient,
  TelemetryError,
  normalizeSnapshot,
} from '../src/services/telemetryClient';
import type { RawTowerSnapshot } from '../src/types/federation';

let passed = 0;
let failed = 0;

function check(name: string, condition: boolean, detail?: string): void {
  if (condition) {
    passed++;
    console.log(`ok   ${name}`);
  } else {
    failed++;
    console.log(`FAIL ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

function section(title: string): void {
  console.log(`\n== ${title} ==`);
}

function testNormalizeSnapshot(): void {
  section('normalizeSnapshot');
  const raw: RawTowerSnapshot = {
    capturedAt: '2026-10-17T10:00:00Z',
    satellites: {
      open: { healthy: true, sha: '0152050abcdef', lastSyncedAt: '2026-10-17T09:00:00Z', activeClaims: 2, latencyMs: 42 },
      sdk: { healthy: true, sha: 'aabbccdd1122' },
      core: {},
    },
    workOrders: [
      { taskId: 'bridge-20261017-sdk-multilang', title: 'Multi-Language SDK', stage: 'landed', ciStatus: 'green', prNumber: 542, updatedAt: '2026-10-17T10:30:00Z' },
      { taskId: 'bridge-20261017-fix-x', title: 'Fix X', stage: 'weird-stage', ciStatus: 'banana', diagnostics: 'retry exhausted' },
      { title: 'no task id — dropped' },
    ],
    defense: { activeClaims: 3, claimRejections: 11, rateLimitCapacity: 8, taskVelocityPerHour: 24 },
  };

  const snapshot = normalizeSnapshot(raw);
  check('twelve canonical satellites', snapshot.satellites.length === 12);
  check('satellite order preserved', snapshot.satellites[0].id === 'open' && snapshot.satellites[11].id === 'archive');
  check('healthy flag mapped', snapshot.satellites[0].healthy === true && snapshot.satellites[2].healthy === false);
  check('sha + latency mapped', snapshot.satellites[0].latestSha === '0152050abcdef' && snapshot.satellites[0].latencyMs === 42);
  check('missing claims default 0', snapshot.satellites[2].activeClaims === 0);
  check('runway drops id-less entries', snapshot.runway.length === 2);
  check('valid stage/ci pass through', snapshot.runway[0].stage === 'landed' && snapshot.runway[0].ciStatus === 'green');
  check('invalid stage/ci fall back', snapshot.runway[1].stage === 'queued' && snapshot.runway[1].ciStatus === 'amber');
  check('diagnostics carried', snapshot.runway[1].diagnostics === 'retry exhausted');
  check('defense mapped', snapshot.defense.activeClaims === 3 && snapshot.defense.claimRejections === 11);
  check('capturedAt honored', snapshot.capturedAt === '2026-10-17T10:00:00Z');

  const empty = normalizeSnapshot({}, new Date('2026-10-17T11:00:00Z'));
  check('empty raw degrades to defaults', empty.defense.rateLimitCapacity === 0 && empty.runway.length === 0 && empty.satellites.length === 12);
  check('capturedAt falls back to now', empty.capturedAt === '2026-10-17T11:00:00.000Z');
}

function testSSEParser(): void {
  section('CockpitSSEParser');
  const parser = new CockpitSSEParser();
  check('no complete frames yet', parser.push('data: {"type":"to').length === 0);
  const first = parser.push('ken"}\n\n');
  check('frame completes on blank line', first.length === 1 && first[0] === '{"type":"token"}');

  const multi = parser.push('data: line-one\ndata: line-two\n\n: keep-alive\ndata: [DONE]\n\n');
  check('multi-line data joined', multi[0] === 'line-one\nline-two');
  check('comment lines ignored', multi.length === 2);
  check('done sentinel passes through', multi[1] === '[DONE]');

  const crlf = new CockpitSSEParser();
  const crlfFrames = crlf.push('data: a\r\ndata: b\r\n\r\n');
  check('CRLF endings handled', crlfFrames.length === 1 && crlfFrames[0] === 'a\nb');

  const partial = new CockpitSSEParser();
  partial.push('data: tail-without-blank');
  check('finish flushes trailing frame', partial.finish()[0] === 'tail-without-blank');
  check('finish clears state', partial.finish().length === 0);
}

async function testTelemetryClient(): Promise<void> {
  section('TelemetryClient (injected fetch)');

  const goodPayload = {
    capturedAt: '2026-10-17T10:00:00Z',
    satellites: { open: { healthy: true } },
    workOrders: [{ taskId: 'bridge-20261017-t', title: 'T', stage: 'queued', ciStatus: 'amber' }],
    defense: { activeClaims: 1, claimRejections: 0, rateLimitCapacity: 4, taskVelocityPerHour: 6 },
  };

  let calls = 0;
  let failMode = false;
  const fetchImpl = (async () => {
    calls++;
    if (failMode) {
      return { ok: false, status: 503 } as Response;
    }
    return { ok: true, status: 200, json: async () => goodPayload } as unknown as Response;
  }) as typeof fetch;

  const client = new TelemetryClient({ baseUrl: '', pollIntervalMs: 60000, fetchImpl });
  const seen: number[] = [];
  const unsubscribe = await client.subscribe((snapshot) => seen.push(snapshot.satellites.length));

  check('subscribe fires immediately', seen.length === 1 && seen[0] === 12);
  check('snapshot endpoint hit', calls === 1);

  await client.tick();
  check('manual tick delivers again', seen.length === 2);
  check('runway row normalized in tick', (await client.fetchSnapshot()).runway[0].taskId === 'bridge-20261017-t');

  failMode = true;
  await client.tick();
  check('failed tick degrades silently', seen.length === 2);

  unsubscribe();
  await client.tick();
  check('unsubscribe stops delivery', seen.length === 2);
  client.dispose();

  let threw = false;
  try {
    await new TelemetryClient({ baseUrl: '', pollIntervalMs: 1000, fetchImpl: (async () => ({ ok: false, status: 503 }) as Response) as typeof fetch }).fetchSnapshot();
  } catch (err) {
    threw = err instanceof TelemetryError && err.status === 503;
  }
  check('fetchSnapshot raises TelemetryError on bad status', threw);
}

async function main(): Promise<void> {
  console.log('Federation Cockpit — telemetry test battery');
  testNormalizeSnapshot();
  testSSEParser();
  await testTelemetryClient();
  console.log(`\nRan ${passed + failed} checks: ${passed} passed, ${failed} failed`);
  if (failed > 0) {
    throw new Error(`${failed} checks failed`);
  }
  console.log('ALL CHECKS PASSED');
}

void main();
