// src/services/audio/webSpeechCapability.test.ts
// M14 P-C (issue #453): Web Speech capability-detection চুক্তি —
// সৎ-সেমান্টিকস: অসমর্থন স্পষ্ট ঘোষিত, কখনো নীরব অনুমান নয়।

import { afterEach, describe, expect, it, vi } from 'vitest';
import { AudioPlaybackService } from './AudioPlaybackService';
import { detectWebSpeechCapability } from './webSpeechCapability';

describe('detectWebSpeechCapability', () => {
  const originalWindow = globalThis.window;
  const globalObj = globalThis as unknown as Record<string, unknown>;

  afterEach(() => {
    globalObj.window = originalWindow;
    vi.restoreAllMocks();
  });

  it('reports unsupported when speechSynthesis is absent', () => {
    globalObj.window = {} as Window;
    const cap = detectWebSpeechCapability();
    expect(cap.ttsSupported).toBe(false);
    expect(cap.sttSupported).toBe(false);
    expect(cap.unsupportedReason).toContain('speechSynthesis');
    expect(cap.unsupportedReason).toContain('SpeechRecognition');
  });

  it('reports tts-only support honestly', () => {
    globalObj.window = {
      speechSynthesis: {},
      SpeechSynthesisUtterance: function mockUtterance(this: Record<string, unknown>) {},
    } as unknown as Window;
    const cap = detectWebSpeechCapability();
    expect(cap.ttsSupported).toBe(true);
    expect(cap.sttSupported).toBe(false);
    expect(cap.unsupportedReason).not.toContain('speechSynthesis');
  });

  it('reports both supported with empty reason', () => {
    globalObj.window = {
      speechSynthesis: {},
      SpeechSynthesisUtterance: function mockUtterance(this: Record<string, unknown>) {},
      SpeechRecognition: function mockRecognition(this: Record<string, unknown>) {},
    } as unknown as Window;
    const cap = detectWebSpeechCapability();
    expect(cap.ttsSupported).toBe(true);
    expect(cap.sttSupported).toBe(true);
    expect(cap.unsupportedReason).toBe('');
  });

  it('never throws in undefined window context', () => {
    globalObj.window = undefined;
    expect(() => detectWebSpeechCapability()).not.toThrow();
    expect(detectWebSpeechCapability().ttsSupported).toBe(false);
  });
});

describe('AudioPlaybackService fail-safe', () => {
  const originalWindow = globalThis.window;
  const globalObj = globalThis as unknown as Record<string, unknown>;

  afterEach(() => {
    globalObj.window = originalWindow;
    vi.restoreAllMocks();
  });

  it('constructor does not crash and play() honestly fails without speechSynthesis', () => {
    globalObj.window = {} as Window;
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const svc = new AudioPlaybackService();
    expect(svc.ttsSupported).toBe(false);
    expect(svc.play('hello')).toBe(false); // ভাঙা-বোতাম নয় — সৎ অসমর্থন
    expect(errSpy).toHaveBeenCalledWith(expect.stringContaining('speechSynthesis unavailable'));
  });

  it('getAnalyser returns null safely when AudioContext absent', () => {
    globalObj.window = {} as Window;
    const svc = new AudioPlaybackService();
    expect(svc.getAnalyser()).toBeNull();
  });
});
