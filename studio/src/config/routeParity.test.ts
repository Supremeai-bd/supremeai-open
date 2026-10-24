import { describe, expect, it } from 'vitest';
import { getImplementedRoutePaths } from './navigationRegistry';
import { workspaceFeatureRoutes } from '../routes/workspaceFeatureRoutes';

// FIX(nav-parity 2026-10-24): automated navigation <-> actual-route parity gate
// (rating-audit P1 item 10). Every registry entry marked 'implemented' must
// resolve to a real route definition so direct URLs can never fall through to
// the 404 catch-all while the sidebar still advertises them.
//
// Scope: workspaceFeatureRoutes.tsx exports the Tier-S route table. App.tsx
// additionally declares a small set of inline routes (snapshot below, taken
// from src/App.tsx on 2026-10-24); prune this list when App routes move into
// the registry-driven table.

const routePaths = new Set<string>(
  workspaceFeatureRoutes
    .map((r) => r.path)
    .filter((p): p is string => typeof p === 'string'),
);

const APP_INLINE_ROUTES = new Set<string>([
  '/',
  '/about',
  '/admin/*',
  '/chat',
  '/cockpit',
  '/contact',
  '/docs',
  '/features',
  '/knowledge',
  '/login',
  '/models',
  '/pricing',
  '/register',
  '/telemetry',
  '/workspace',
  '/workspace/live',
]);

describe('navigation <-> route parity', () => {
  it('every implemented registry path resolves to a real route', () => {
    const implemented = getImplementedRoutePaths();
    const dead = implemented.filter((p) => !routePaths.has(p) && !APP_INLINE_ROUTES.has(p));
    expect(dead, `implemented nav paths with no backing route: ${dead.join(', ')}`).toEqual([]);
  });
});
