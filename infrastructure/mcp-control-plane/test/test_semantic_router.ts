/**
 * test_semantic_router.ts — Way 3 evidence (deterministic TF-IDF routing + pruning).
 * Run: npx tsx test_semantic_router.ts   (or wire into the existing test_*.ts pattern)
 */

import { SemanticToolRouter, type ToolDescriptor } from '../src/registry/semantic_router';

let failures = 0;
function check(label: string, cond: boolean, detail = ''): void {
  if (cond) {
    console.log(`PASS ${label}`);
  } else {
    failures += 1;
    console.error(`FAIL ${label} ${detail}`);
  }
}

const TOOLS: ToolDescriptor[] = [
  { name: 'github.list_prs', description: 'List open pull requests in a repository', tags: ['github', 'pr'], group: 'github' },
  { name: 'github.get_failed_logs', description: 'Fetch failed CI run logs', tags: ['ci', 'logs'], group: 'github' },
  { name: 'bridge.work_queue', description: 'List open bridge work-order issues', tags: ['bridge', 'queue'], group: 'bridge' },
  { name: 'redis.read_key', description: 'Read a key value from Redis', tags: ['redis', 'kv'], group: 'redis' },
  { name: 'system_health', description: 'Fleet health snapshot for all services', tags: ['health', 'ops'], group: 'ops' },
];

const router = new SemanticToolRouter(TOOLS);
check('index size', router.size === TOOLS.length);

const ciHits = router.route('why did the ci run fail, show me the logs', 3);
check(
  'ci query ranks failed-logs top-1',
  ciHits[0]?.name === 'github.get_failed_logs',
  JSON.stringify(ciHits),
);

const prHits = router.route('list open pull requests', 2);
check('pr query ranks list_prs top-1', prHits[0]?.name === 'github.list_prs');

const healthHits = router.route('is the fleet healthy right now', 2);
check('health query in top-2', healthHits.slice(0, 2).some((h) => h.name === 'system_health'));

const empty = router.route('');
check('empty query -> no matches', empty.length === 0);

const gibberish = router.route('zzzz qqqq xvxy');
check('gibberish -> no matches', gibberish.length === 0);

// Determinism
const a = router.route('ci logs', 3).map((m) => [m.name, m.score]);
const b = router.route('ci logs', 3).map((m) => [m.name, m.score]);
check('deterministic ranking', JSON.stringify(a) === JSON.stringify(b));

// Pruning
const schemas = TOOLS.map((t) => ({ name: t.name, schema: { description: t.description } }));
const { kept, dropped } = router.pruneForQuery('ci run failed logs', schemas, 0.05);
check('prune keeps relevant', kept.some((k) => k.name === 'github.get_failed_logs'));
check('prune drops irrelevant', dropped.includes('redis.read_key'), JSON.stringify({ kept: kept.map((k) => k.name), dropped }));
check('token reduction measured', dropped.length >= 2, `dropped=${dropped.length}`);

const rebased = new SemanticToolRouter([]);
rebased.reindex(TOOLS);
check('reindex after churn', rebased.size === TOOLS.length);

if (failures > 0) {
  console.error(`\n${failures} check(s) FAILED`);
  process.exit(1);
}
console.log('\nALL CHECKS PASSED');
