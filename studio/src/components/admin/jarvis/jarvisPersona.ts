// ============================================================
// SUPREME OS — JARVIS Admin Voice Persona & Classifier
// Dedicated for Super Admin Dashboard (Zero-Cost, Cloud/Web-Native)
// ============================================================

export type OrbState =
  | 'boot'
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'alert';

export interface TelemetryBriefingContext {
  activeIncidents?: number;
  runningDeployments?: number;
  latencyP95?: string | number | null;
  healthyServicesCount?: number;
  totalServicesCount?: number;
}

// ------------------------------------------------------------
// Time-based polite British Butler greeting
// ------------------------------------------------------------
export function greetingForHour(hour: number = new Date().getHours()): string {
  if (hour < 5) return 'Burning the midnight oil, Sir?';
  if (hour < 12) return 'Good morning, Sir.';
  if (hour < 17) return 'Good afternoon, Sir.';
  return 'Good evening, Sir.';
}

// ------------------------------------------------------------
// Dynamic spoken briefing generated from live admin telemetry
// ------------------------------------------------------------
export function generateAdminBriefing(ctx: TelemetryBriefingContext): string {
  const greeting = greetingForHour();
  const incidents = ctx.activeIncidents ?? 0;
  const deploys = ctx.runningDeployments ?? 0;
  const latency = ctx.latencyP95 ? `${ctx.latencyP95} milliseconds` : 'normal';

  let summary = `${greeting} Supreme Control Plane is online. `;
  
  if (incidents === 0) {
    summary += 'All systems operational with zero critical incidents. ';
  } else {
    summary += `Attention required: ${incidents} high severity incident${incidents > 1 ? 's' : ''} detected. `;
  }

  if (deploys > 0) {
    summary += `${deploys} active deployment${deploys > 1 ? 's are' : ' is'} in flight. `;
  }

  summary += `Latency is stable at ${latency}. Standing by for your command, Sir.`;
  return summary;
}

// ------------------------------------------------------------
// Spoken-Style System Prompt (≤80 words, no markdown/emoji)
// ------------------------------------------------------------
export function buildJarvisSystemPrompt(): string {
  const now = new Date().toISOString();
  return [
    "You are JARVIS, the personal AI assistant of the SupremeAI system administrator (address him as 'Sir').",
    "PERSONALITY: classic JARVIS — impeccably polite, razor-sharp, subtly witty British butler tone. Calm under pressure. Never grovel, never spam exclamation marks.",
    "CONTEXT: Super Admin voice cockpit. The administrator controls the whole SupremeAI platform.",
    `CURRENT TIME: ${now}.`,
    "LANGUAGE: Mirror the user's language. If he speaks Banglish or Bengali, reply naturally in the same style with English technical terms kept as-is. If English, reply in English.",
    "VOICE RULES (CRITICAL — reply is read aloud by TTS):",
    "- Keep replies under 60-80 words unless explicitly asked for detail.",
    "- Plain conversational text only. NO markdown, NO bullet points, NO asterisks, NO code blocks, NO emojis.",
    "- Speak numbers and technical terms cleanly.",
    "SAFETY: For destructive or major actions (deploy, delete, restart, shutdown, purge, rotate credentials), inform the administrator that 2FA authorization is required.",
  ].join('\n');
}

// ------------------------------------------------------------
// Destructive / High-Privilege Command Classifier
// English + Banglish + Bengali script
// ------------------------------------------------------------
const DESTRUCTIVE_PATTERNS: RegExp[] = [
  /\b(deploy|undeploy|redeploy)\b/i,
  /\b(delete|del|remove|rm|drop|destroy|wipe|purge|flush|truncate)\b/i,
  /\b(kill|shutdown|shut\s?down|power\s?off|halt|stop\s+(the\s+)?(server|service|node|system))\b/i,
  /\b(restart|reboot|reset|rollback|roll\s?back|migrate|migration)\b/i,
  /\b(force\s?(push|merge)|merge\s+to\s+(main|master)|git\s+push)\b/i,
  /\b(revoke|rotate|suspend|terminate|disable|turn\s+off|switch\s+off|shut\s?off)\b/i,
  /\b(credential|secret|token|password|api\s?key).{0,20}(rotate|reset|revoke|change)\b/i,
  /\b(off\s?koro|off\s?kore\s?dao|bondho\s?koro|bandh?o\s?koro|band\s?koro)\b/i,
  /\b(muchh?e?\s?(felo|dao|dibo)|delete\s?koro|remove\s?koro)\b/i,
  /\b(deploy\s?koro|restart\s?koro|reset\s?koro|bondho\s?kore\s?dao)\b/i,
  /\b(null\s?koro|khali\s?koro|uroye\s?fe?lo)\b/i,
  /বন্ধ\s?কর/, /মুছে\s?ফেল/, /ডিলিট/, /ডিপ্লয/, /রিস্টার্ট/, /শাট\s?ডাউন/,
  /ফেলে\s?দাও/, /রিসেট/, /বন্ধ\s?করে\s?দাও/, /নিভিয়ে\s?দাও/,
];

export function isDestructiveCommand(text: string): boolean {
  const t = text.trim();
  if (t.length < 3) return false;
  return DESTRUCTIVE_PATTERNS.some((re) => re.test(t));
}

export function detectDestructiveReason(text: string): string | null {
  for (const re of DESTRUCTIVE_PATTERNS) {
    const m = text.match(re);
    if (m) return m[0];
  }
  return null;
}
