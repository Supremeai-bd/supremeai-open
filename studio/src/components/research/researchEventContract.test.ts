/**
 * M08 P-A — Frontend side of the two-sided Deep Research SSE contract.
 *
 * বাংলা: ব্যাকএন্ড `deep_research.py`-এর emit-আকৃতি এখানে ফিক্সচার হিসেবে
 * খাওয়ানো হয় — যা ব্যাকএন্ড পাঠায়, প্যানেল ঠিক সেটাই parse করে
 * (`researchEventContract.ts`-এর পার্সার দিয়ে, যা প্যানেল নিজেও ব্যবহার করে)।
 * ব্যাকএন্ড-সাইড পিন: backend/tests/api/test_deep_research_contract.py।
 */
import { describe, expect, it } from 'vitest';

import { parseResearchEvent, parseResearchSseLine } from './researchEventContract';

// Shapes copied verbatim from backend deep_research.py emission sites.
const BACKEND_STEP_EVENT = {
  type: 'step',
  step: 2,
  name: 'Searching sources',
  content: 'Fetched 5 pages',
};

const BACKEND_REPORT_EVENT = {
  type: 'report',
  content: {
    title: 'Quantum Computing',
    sections: [{ title: 'Background', content: 'Section body', sources: ['s1'] }],
    sources: [{ title: 'Example', url: 'https://example.com', snippet: '…' }],
    summary: 'Final summary',
  },
  steps_completed: 5,
  total_sources: 3,
  id: 'sess-123',
};

const BACKEND_ERROR_EVENT = { type: 'error', content: 'Pipeline task failed: boom' };

describe('M08 research SSE contract (frontend parser ↔ backend emitter)', () => {
  it('parses the backend step event into a panel-ready step', () => {
    const parsed = parseResearchEvent(BACKEND_STEP_EVENT);
    expect(parsed).toEqual({
      kind: 'step',
      step: { step_number: 2, name: 'Searching sources', content_preview: 'Fetched 5 pages' },
    });
  });

  it('defaults a missing step name like the backend contract allows', () => {
    const parsed = parseResearchEvent({ type: 'step', step: 1 });
    expect(parsed).toEqual({
      kind: 'step',
      step: { step_number: 1, name: 'Step 1', content_preview: '' },
    });
  });

  it('maps the backend report payload (sections[].title → heading)', () => {
    const parsed = parseResearchEvent(BACKEND_REPORT_EVENT);
    expect(parsed.kind).toBe('report');
    if (parsed.kind === 'report') {
      expect(parsed.id).toBe('sess-123');
      expect(parsed.report.title).toBe('Quantum Computing');
      expect(parsed.report.sections).toEqual([
        { heading: 'Background', content: 'Section body' },
      ]);
      expect(parsed.report.sources).toEqual([
        { title: 'Example', url: 'https://example.com' },
      ]);
      expect(parsed.report.summary).toBe('Final summary');
    }
  });

  it('parses the backend error event message', () => {
    expect(parseResearchEvent(BACKEND_ERROR_EVENT)).toEqual({
      kind: 'error',
      message: 'Pipeline task failed: boom',
    });
  });

  it('ignores the [DONE] terminator and non-JSON lines like the stream loop does', () => {
    expect(parseResearchSseLine('data: [DONE]')).toEqual({ kind: 'ignored' });
    expect(parseResearchSseLine('data: not-json')).toEqual({ kind: 'ignored' });
    expect(parseResearchSseLine(': keep-alive comment')).toEqual({ kind: 'ignored' });
  });

  it('never throws on unknown backend event types', () => {
    expect(parseResearchEvent({ type: 'mystery' })).toEqual({ kind: 'ignored' });
    expect(parseResearchEvent(null)).toEqual({ kind: 'ignored' });
    expect(parseResearchEvent('string')).toEqual({ kind: 'ignored' });
  });
});
