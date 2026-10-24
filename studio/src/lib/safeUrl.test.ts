/**
 * Unit tests for safeUrl (issue #2520) — the dynamic-href allowlist contract.
 *
 * বাংলা: প্রতিটি ডাইনামিক href-এর নিরাপত্তা কন্ট্র্যাক্ট — script-executing প্রোটোকল
 * (javascript:, data:, vbscript:, file:) কখনোই বেরোতে পারবে না (fail-closed "#"),
 * বৈধ http/https/mailto অপরিবর্তিত থাকবে, খালি/অজানা ইনপুটও "#" হবে, আর
 * whitespace-প্যাডেড পেলোড ট্রিম করে আটকাতে হবে।
 */
import { describe, it, expect } from 'vitest';
import { safeUrl } from './safeUrl';

describe('safeUrl — allowlist contract (#2520)', () => {
  it('neutralizes javascript:alert(1) to "#"', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('#');
  });

  it('neutralizes data:text/html to "#"', () => {
    expect(safeUrl('data:text/html,<script>alert(1)</script>')).toBe('#');
  });

  it('neutralizes vbscript: and file: to "#"', () => {
    expect(safeUrl('vbscript:msgbox(1)')).toBe('#');
    expect(safeUrl('file:///etc/passwd')).toBe('#');
  });

  it('keeps an absolute https URL unchanged', () => {
    expect(safeUrl('https://example.com/a')).toBe('https://example.com/a');
  });

  it('keeps an http URL (resolved to absolute href)', () => {
    expect(safeUrl('http://x')).toBe('http://x/');
  });

  it('keeps a mailto: URL unchanged', () => {
    expect(safeUrl('mailto:a@b.c')).toBe('mailto:a@b.c');
  });

  it('returns internal hash routes as-is', () => {
    expect(safeUrl('#/session/1')).toBe('#/session/1');
  });

  it('fails closed on empty string', () => {
    expect(safeUrl('')).toBe('#');
  });

  it('fails closed on undefined and null', () => {
    expect(safeUrl(undefined)).toBe('#');
    expect(safeUrl(null)).toBe('#');
  });

  it('trims leading whitespace before the allowlist check (evasion payload)', () => {
    expect(safeUrl(' javascript:alert(1)')).toBe('#');
  });

  it('fails closed on unparseable URLs', () => {
    expect(safeUrl('http://')).toBe('#');
  });

  it('resolves relative paths against window.location.origin over an allowed protocol', () => {
    expect(safeUrl('/files/1')).toBe(new URL('/files/1', window.location.origin).href);
  });
});
