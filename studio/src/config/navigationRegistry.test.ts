import { describe, expect, it } from 'vitest';
import { getNavigationForContext, getImplementedRoutePaths } from './navigationRegistry';

describe('canonical navigation registry', () => {
  it('keeps advanced operational routes out of the core user navigation', () => {
    const paths = getNavigationForContext('user')
      .flatMap((group) => group.items)
      .filter((item) => item.kind === 'route')
      .map((item) => item.path);

    expect(paths).toContain('/workspace');
    // FIX(nav-truth 2026-10-24): /integrations has no route yet — the registry
    // entry is 'planned' (hidden) per dead-link prevention, so it must NOT appear.
    expect(paths).not.toContain('/integrations');
    // The user-context Chat entry now targets the shared unified chat surface.
    expect(paths).toContain('/workspace/live');
    expect(paths).not.toContain('/swarm');
    expect(paths).not.toContain('/evolution-forge');
    expect(paths).not.toContain('/architect-tower');
  });

  it('does not expose action-only admin entries as user navigation', () => {
    const userItems = getNavigationForContext('user').flatMap((group) => group.items);
    expect(userItems.every((item) => item.kind === 'route')).toBe(true);
  });

  it('only reports implemented route paths', () => {
    expect(getImplementedRoutePaths()).not.toContain('/swarm');
    expect(getImplementedRoutePaths()).toContain('/workspace');
  });

  it('exposes full administrative capabilities in admin context while keeping user context simplified', () => {
    const adminGroups = getNavigationForContext('admin');
    const adminGroupIds = adminGroups.map((g) => g.id);
    expect(adminGroupIds).toEqual(
      expect.arrayContaining(['admin-operations', 'admin-security', 'admin-governance', 'admin-core'])
    );

    const adminActionIds = adminGroups
      .flatMap((g) => g.items)
      .filter((i) => i.kind === 'action')
      .map((i) => (i as { actionId: string }).actionId);

    // High impact operational capabilities
    expect(adminActionIds).toContain('overview');
    expect(adminActionIds).toContain('topology');
    expect(adminActionIds).toContain('telemetry');
    expect(adminActionIds).toContain('automation-queue');
    expect(adminActionIds).toContain('platform-vault');
    expect(adminActionIds).toContain('llm-gateway');
    expect(adminActionIds).toContain('security');
    expect(adminActionIds).toContain('tenants-rbac');
    expect(adminActionIds).toContain('finops');
    expect(adminActionIds).toContain('command-center');

    // Customer workspace must not contain any administrative action items
    const userItems = getNavigationForContext('user').flatMap((g) => g.items);
    expect(userItems.some((i) => i.kind === 'action')).toBe(false);
    expect(userItems.some((i) => i.id.startsWith('admin-'))).toBe(false);
  });
});
