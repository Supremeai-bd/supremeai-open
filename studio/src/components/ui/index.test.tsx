import { describe, it, expect } from 'vitest';
import * as ui from './index';

describe('components/ui barrel exports', () => {
  it('re-exports all public components', () => {
    expect(ui.Card).toBeDefined();
    expect(ui.Badge).toBeDefined();
    expect(ui.Skeleton).toBeDefined();
    expect(ui.ActionCard).toBeDefined();
    expect(ui.StatCard).toBeDefined();
    expect(ui.SpotlightCard).toBeDefined();
    expect(ui.EmptyState).toBeDefined();
    expect(ui.Breadcrumb).toBeDefined();
    expect(ui.PageHeader).toBeDefined();
    expect(ui.BanglaHint).toBeDefined();
    expect(ui.UnifiedChatBubble).toBeDefined();
    expect(ui.TypingIndicator).toBeDefined();
  });
});
