// FINAL-TEST: tests for the real getPageContent() implementation (was a stub
// returning '' — AI actions ran with zero page context).
import { describe, it, expect } from 'vitest';
import { getPageContent } from '../formatHelpers';

type RefLike = { current: HTMLIFrameElement | null };

function fakeIframe(doc: Document | null, src = ''): RefLike {
  return {
    current: {
      contentDocument: doc,
      src,
    } as unknown as HTMLIFrameElement,
  };
}

describe('getPageContent', () => {
  it('returns "" when no iframe ref is provided', async () => {
    await expect(getPageContent(null)).resolves.toBe('');
    await expect(getPageContent({ current: null })).resolves.toBe('');
  });

  it('extracts title and visible text from a same-origin document', async () => {
    const doc = {
      title: 'My Page',
      body: {
        innerText: '  Hello   world \n from the preview  ',
        textContent: 'Hello   world \n from the preview',
      },
    } as unknown as Document;

    const result = await getPageContent(fakeIframe(doc));
    expect(result).toContain('Title: My Page');
    expect(result).toContain('Hello world from the preview');
  });

  it('falls back to textContent when innerText is unavailable', async () => {
    const doc = {
      title: '',
      body: { textContent: 'plain content' },
    } as unknown as Document;
    const result = await getPageContent(fakeIframe(doc));
    expect(result).toBe('plain content');
  });

  it('returns a cross-origin context with the URL when DOM access is blocked', async () => {
    // contentDocument null (cross-origin in real browsers)
    const result = await getPageContent(
      fakeIframe(null, 'https://example.com/page'),
    );
    expect(result).toContain('[cross-origin page');
    expect(result).toContain('https://example.com/page');
  });

  it('falls back safely when contentDocument getter throws', async () => {
    const ref: RefLike = {
      current: {
        get contentDocument(): Document | null {
          throw new DOMException('Blocked', 'SecurityError');
        },
        src: 'https://blocked.example',
      } as unknown as HTMLIFrameElement,
    };
    const result = await getPageContent(ref);
    expect(result).toContain('[cross-origin page');
    expect(result).toContain('https://blocked.example');
  });

  it('returns "" for about:blank cross-origin frames', async () => {
    const result = await getPageContent(fakeIframe(null, 'about:blank'));
    expect(result).toBe('');
  });

  it('truncates very long text', async () => {
    const long = 'x'.repeat(10_000);
    const doc = {
      title: 'Big',
      body: { innerText: long, textContent: long },
    } as unknown as Document;
    const result = await getPageContent(fakeIframe(doc));
    expect(result.length).toBeLessThan(10_000);
    expect(result).toContain('[truncated]');
  });
});
