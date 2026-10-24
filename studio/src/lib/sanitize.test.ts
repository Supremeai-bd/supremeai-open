/**
 * Guard suite for issue #2509 — every payload is a real/known bypass class
 * against the previous regex sanitizer. None of them may survive.
 */
import { describe, it, expect } from 'vitest';
import { sanitizeSvg, sanitizeHighlighted } from './sanitize';

// Assertion helpers — the output must not contain any executable vector.
function expectDefused(out: string) {
  expect(out).not.toMatch(/<script[\s>/]/i);
  expect(out).not.toMatch(/\son\w+\s*=/i); // no event-handler attributes
  expect(out).not.toMatch(/javascript:/i);
  expect(out).not.toMatch(/vbscript:/i);
  expect(out).not.toMatch(/foreignObject/i);
  expect(out).not.toMatch(/<(animate|set|handler)[\s>/]/i); // no SMIL retarget
  expect(out).not.toMatch(/data:text\/html/i);
}

describe('sanitizeSvg — regex-bypass payloads must NOT survive (#2509)', () => {
  const bypasses: Array<[string, string]> = [
    ['classic script block', '<svg><script>alert(1)</script></svg>'],
    // The killer for the old regex: no closing tag → no regex match → tag lived.
    ['unterminated script', '<svg><script>alert(1)'],
    ['entity-encoded js: href', '<svg><a href="java&#115;cript:alert(1)"><text>x</text></a></svg>'],
    ['entity-encoded xlink:href', '<svg><a xlink:href="javas&#99;ript:alert(1)"><text>x</text></a></svg>'],
    ['raw js: href', '<svg><a href="javascript:alert(1)"><text>click</text></a></svg>'],
    ['data:text/html href', '<svg><a href="data:text/html;base64,PHNjcmlwdD4="><text>x</text></a></svg>'],
    ['SMIL animate retarget', '<svg><animate attributeName="href" values="javascript:alert(1)"/><a><text>x</text></a></svg>'],
    ['SMIL set retarget', '<svg><set attributeName="href" to="javascript:alert(1)"/><a><text>x</text></a></svg>'],
    ['on-load attribute', '<svg onload=alert(1)></svg>'],
    ['onmouseover on shape', '<svg><rect width="10" height="10" onmouseover="alert(1)"/></svg>'],
    ['foreignObject HTML payload', '<svg><foreignObject><body><img src=x onerror=alert(1)></body></foreignObject></svg>'],
    ['unterminated foreignObject', '<svg><foreignObject><img src=x onerror=alert(1)>'],
    ['image onerror', '<svg><image href="x" onerror="alert(1)"/></svg>'],
    ['svg use href to data', '<svg><use href="data:image/svg+xml;base64,PHN2Zz48c2NyaXB0PmFsZXJ0KDEpPC9zY3JpcHQ+PC9zdmc+"/></svg>'],
  ];

  it.each(bypasses)('defuses: %s', (_name, payload) => {
    const out = sanitizeSvg(payload);
    expectDefused(out);
  });

  it('keeps benign diagram markup renderable', () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 20"><rect x="1" y="1" width="18" height="18" fill="#ddd"/><circle cx="30" cy="10" r="8"/><text x="4" y="12">flow</text><path d="M5 5 L15 15"/></svg>';
    const out = sanitizeSvg(svg);
    expect(out).toContain('<svg');
    expect(out).toContain('<rect');
    expect(out).toContain('<circle');
    expect(out).toContain('<text');
    expect(out).toContain('flow');
    expect(out).toContain('<path');
    expect(out).toContain('viewBox');
  });

  it('keeps fill/stroke presentation attributes (diagram fidelity)', () => {
    const svg = '<svg><rect style="fill:#f00" stroke="blue" stroke-width="2"/></svg>';
    const out = sanitizeSvg(svg);
    expect(out).toContain('stroke');
    expect(out).toMatch(/fill/i);
  });

  it('fails closed on empty input', () => {
    expect(sanitizeSvg('')).toBe('');
  });
});

describe('sanitizeHighlighted — <mark> allowlist (#2509 point 2)', () => {
  it('strips event handlers from <mark> (old regex kept them intact)', () => {
    const out = sanitizeHighlighted('<mark onmouseover="alert(1)" class="hl">hi</mark>');
    expect(out).toContain('<mark');
    expect(out).toContain('class="hl"');
    expect(out).toContain('hi');
    expect(out).not.toMatch(/\son\w+\s*=/i);
  });

  it('strips non-mark tags but keeps their text content', () => {
    const out = sanitizeHighlighted('<img src=x onerror=alert(1)>safe <b>bold</b> tail');
    expectDefused(out);
    expect(out).toContain('safe');
    expect(out).toContain('bold');
    expect(out).toContain('tail');
    expect(out).not.toMatch(/<(img|b)[\s>/]/i);
  });

  it('removes script blocks and their content path is inert', () => {
    const out = sanitizeHighlighted('<script>alert(1)</script>after');
    expect(out).not.toMatch(/<script[\s>/]/i);
    expect(out).toContain('after');
  });

  it('preserves a well-formed highlight', () => {
    const cls = 'bg-amber-200 dark:bg-amber-500/30 text-amber-900 rounded px-0.5';
    const out = sanitizeHighlighted(`<mark class="${cls}">match</mark> rest`);
    expect(out).toContain('<mark');
    expect(out).toContain('match');
    expect(out).toContain('rest');
  });

  it('fails closed on empty input', () => {
    expect(sanitizeHighlighted('')).toBe('');
  });
});
