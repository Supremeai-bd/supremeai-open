// Lightweight intent classifier for chat/voice commands (English + Bangla).
// Keeps logic dependency-free so it can be reused by chat, voice, or webhook bridges.

export type IntentType =
  | 'system_status'
  | 'deploy'
  | 'logs'
  | 'alerts'
  | 'config'
  | 'search'
  | 'help'
  | 'notify'
  | 'unknown';

const INTENT_PATTERNS: Record<IntentType, RegExp[]> = {
  system_status: [
    /(status|obostha|health|swasthya|running|online|offline|theek|ache|nei)/i,
  ],
  deploy: [/(deploy|koro|chalao|run|start|restart|production|staging)/i],
  logs: [/(log|history|activity|audit|track|লগ)/i],
  alerts: [/(alert|incident|warning|error|সতর্ক)/i],
  config: [/(config|setting|rules|configuration)/i],
  search: [/(search|find|lookup|খুঁজ)/i],
  help: [/(help|sahajyo|what can|কি করতে পারি|commands?)/i],
  notify: [/(notify|send|message|telegram|discord|পাঠাও)/i],
  unknown: [],
};

const DESTRUCTIVE_PATTERNS = [
  /(delete|remove|destroy|kill|shutdown|purge|drop)/i,
  /(মুছে|বন্ধ|বন্ধ কর|ডিলিট)/i,
];

export function classifyIntent(text: string): IntentType {
  const normalized = text.trim();
  if (!normalized) return 'unknown';
  for (const [intent, patterns] of Object.entries(INTENT_PATTERNS) as [IntentType, RegExp[]][]) {
    if (intent === 'unknown') continue;
    if (patterns.some((pattern) => pattern.test(normalized))) {
      return intent;
    }
  }
  return 'unknown';
}

export function isDestructiveCommand(text: string): boolean {
  const normalized = text.trim();
  return DESTRUCTIVE_PATTERNS.some((pattern) => pattern.test(normalized));
}

export function detectLanguage(text: string): 'en' | 'bn' {
  return /[\u0980-\u09FF]/.test(text) ? 'bn' : 'en';
}
