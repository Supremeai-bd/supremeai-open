/**
 * Centralized HTML sanitizers (issue #2509 — regex sanitizers are bypassable).
 *
 * Why not regex: a regex sanitizer is lossy-by-design. Unterminated tags
 * (`<script>alert(1)` with no closing tag), entity-encoded URI schemes
 * (`java&#115;cript:`), and SMIL attribute-injection (`<animate
 * attributeName="href" values="javascript:…">`) all sail past pattern-based
 * stripping, because the browser parses entities and fragments *after* the
 * regex has run. DOMPurify parses the string into a real DOM first and then
 * serializes only what survived the allowlist — entities are already decoded
 * at parse time, so encoded schemes cannot slip through.
 *
 * Policy: allowlist (default-deny), never blocklist. SSR / non-DOM
 * environments fail closed to an empty string.
 */
import DOMPurify from 'dompurify';

/** True when a real DOM is available (browser, jsdom in tests). */
function hasDom(): boolean {
  return typeof window !== 'undefined' && typeof window.document !== 'undefined';
}

// SMIL (`<animate>` / `<set>`) can retarget another element's `href` (or other
// URI attributes) at runtime — an XSS vector no static allowlist of the
// original attribute can see. SVG artifacts are static diagrams; animation is
// not worth the risk, so SMIL is forbidden outright.
const FORBID_SVG_TAGS = ['script', 'foreignObject', 'animate', 'set', 'handler'];

/**
 * Sanitize an SVG artifact for rendering via `dangerouslySetInnerHTML`.
 *
 * Uses DOMPurify's SVG + svg-filters profile (tag/attribute allowlist), then
 * hard-forbids the known-dangerous tags on top. Event handlers (`on*`) and
 * `javascript:` / `data:` URIs are rejected by DOMPurify's URI checks —
 * including entity-encoded forms, which the previous regex sanitizer missed.
 */
export function sanitizeSvg(svgContent: string): string {
  if (!svgContent || !hasDom()) return '';
  return DOMPurify.sanitize(svgContent, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: FORBID_SVG_TAGS,
    // Defense-in-depth: keep content even when a disallowed wrapper tag is
    // stripped, so a `<foreignObject>text</foreignObject>` does not vanish.
    KEEP_CONTENT: true,
  });
}

/**
 * Sanitize a backend-provided search-highlight string so that only `<mark>`
 * elements (with a `class` attribute) survive. Every other tag is stripped
 * while its text content is preserved; all attributes except `class` are
 * dropped — including event handlers the previous regex sanitizer left intact
 * on `<mark>` (`<mark onmouseover=alert(1)>`).
 */
export function sanitizeHighlighted(html: string): string {
  if (!html || !hasDom()) return '';
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['mark'],
    ALLOWED_ATTR: ['class'],
    KEEP_CONTENT: true,
  });
}
