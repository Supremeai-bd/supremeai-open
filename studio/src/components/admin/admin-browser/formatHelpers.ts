// ════════════════════════════════════════════════════════════════════
// ✅ HELPER FUNCTIONS
// (Extracted verbatim from AdminBrowserPanel.tsx — mechanical refactor)
// FINAL-TEST FEATURE FIX: getPageContent() used to be a stub returning '',
// so every AI action (summarize / explain / find_issues) sent an EMPTY
// context string to /api/browser/ai-action. It now extracts the visible
// text of the currently rendered preview iframe when the document is
// same-origin readable, and degrades gracefully (URL + title only) for
// cross-origin pages where the browser blocks DOM access.
// ════════════════════════════════════════════════════════════════════

/** Hard cap so a huge page cannot blow up the AI request body. */
const MAX_CONTEXT_CHARS = 4_000;

interface ExtractedPageInfo {
  title: string;
  text: string;
  readable: boolean;
}

function extractFromDocument(doc: Document): ExtractedPageInfo {
  const title = doc.title || '';
  let text = '';

  try {
    const body = doc.body;
    if (body) {
      // Prefer innerText (layout-aware, skips hidden nodes) with innerHTML
      // text as fallback for JSDOM-like environments.
      text =
        (body as HTMLElement & { innerText?: string }).innerText ||
        body.textContent ||
        '';
    }
  } catch (err) {
    // Surface extraction problems — title may still be available.
    console.warn('[admin-browser] body text extraction failed:', err);
  }

  text = text.replace(/\s+/g, ' ').trim();
  return { title, text, readable: text.length > 0 };
}

/**
 * Attempts to extract text content from the preview iframe for AI context.
 * Handles cross-origin restrictions gracefully: same-origin documents are
 * fully read; cross-origin ones yield a short URL/title-only context.
 *
 * @param iframeRef ref to the browser-preview iframe (optional)
 */
export async function getPageContent(
  iframeRef?: { current: HTMLIFrameElement | null } | null,
): Promise<string> {
  const iframe = iframeRef?.current;
  if (!iframe) return '';

  let info: ExtractedPageInfo = { title: '', text: '', readable: false };

  try {
    const doc = iframe.contentDocument;
    if (doc) {
      info = extractFromDocument(doc);
    }
  } catch (err) {
    // Cross-origin iframe: contentDocument access throws (or returns null
    // depending on the browser). Fall through to the limited context below.
    console.warn('[admin-browser] iframe document access failed (cross-origin?):', err);
  }

  if (!info.readable) {
    // We cannot read a cross-origin document from the client. Provide the
    // URL so the backend can fetch/analyze the page server-side if it wants.
    const url = iframe.src || '';
    if (!url || url === 'about:blank') return '';
    return `[cross-origin page — DOM not readable from the client]\nURL: ${url}${info.title ? `\nTitle: ${info.title}` : ''}`;
  }

  if (!info.text) return info.title || '';

  const truncated =
    info.text.length > MAX_CONTEXT_CHARS
      ? `${info.text.slice(0, MAX_CONTEXT_CHARS)}… [truncated]`
      : info.text;

  return info.title ? `Title: ${info.title}\n\n${truncated}` : truncated;
}

export function formatLinksFromData(links: Record<string, unknown>[]): string {
  if (!links?.length) return 'No links found.';
  return `🔗 **Links Extracted (${links.length} found)**\n\n${
    links.map((link: Record<string, unknown>, i: number) => `${i+1}. [${link.text || link.url}](${link.url})`).join('\n')
  }`;
}

export function formatIssuesFromData(issues: Record<string, unknown>[]): string {
  if (!issues?.length) return '✅ No issues found!';

  const critical = issues.filter((i: Record<string, unknown>) => i.severity === 'critical');
  const warnings = issues.filter((i: Record<string, unknown>) => i.severity === 'warning');

  return `🚨 **Issues Detected (${issues.length} total)**\n\n**Critical (${critical.length}):**\n${
    critical.map((i: Record<string, unknown>) => `- ⚠️ ${i.message}`).join('\n') || 'None'
  }\n\n**Warnings (${warnings.length}):**\n${
    warnings.map((i: Record<string, unknown>) => `- ⚡ ${i.message}`).join('\n') || 'None'
  }\n\n**Suggestions:** Run security scan for detailed remediation steps.`;
}
