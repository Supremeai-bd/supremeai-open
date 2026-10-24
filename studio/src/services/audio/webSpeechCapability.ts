// src/services/audio/webSpeechCapability.ts
// M14 P-C (issue #453): শূন্য-ব্যয় ভয়েস প্রথম-পথ — ব্রাউজার Web Speech API
// capability-detection। সৎ-সেমান্টিকস: অসমর্থন বিক্রয়-হ্যান্ডলারে স্পষ্ট ঘোষিত
// হয়, কখনো নীরব অনুমান নয় (False-Assurance doctrine)।

export interface WebSpeechCapability {
  /** ব্রাউজারে speechSynthesis (TTS) আছে কি না */
  ttsSupported: boolean;
  /** ব্রাউজারে SpeechRecognition (STT) আছে কি না */
  sttSupported: boolean;
  /** মানুষ-পাঠযোগ্য অসমর্থন-কারণ — দুটোই সমর্থিত হলে খালি */
  unsupportedReason: string;
}

/**
 * Detect browser Web Speech capabilities — never throws, never guesses.
 *
 * বাংলা: capability প্রশ্নের উত্তর একমাত্র প্রকৃত API-উপস্থিতি দিয়ে —
 * কোনো "ধরে নেওয়া সমর্থন" নয়।
 */
export function detectWebSpeechCapability(): WebSpeechCapability {
  const ttsSupported =
    typeof window !== 'undefined' &&
    'speechSynthesis' in window &&
    'SpeechSynthesisUtterance' in window;

  // STT: Chrome/Edge = webkitSpeechRecognition prefix, কোথাও কোথাও standard।
  const w = typeof window !== 'undefined' ? (window as unknown as Record<string, unknown>) : {};
  const sttSupported = typeof window !== 'undefined' && ('SpeechRecognition' in w || 'webkitSpeechRecognition' in w);

  const reasons: string[] = [];
  if (!ttsSupported) reasons.push('TTS: speechSynthesis API is not available in this browser');
  if (!sttSupported) reasons.push('STT: SpeechRecognition API is not available in this browser');

  return {
    ttsSupported,
    sttSupported,
    unsupportedReason: reasons.join('; '),
  };
}
