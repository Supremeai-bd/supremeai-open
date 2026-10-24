/**
 * M08 P-A — Deep Research SSE contract (single source of truth for parsing).
 *
 * বাংলা: ব্যাকএন্ড `deep_research.py` যেসব SSE ইভেন্ট emit করে —
 *   {"type":"step",   step:int, name:string, content:string}
 *   {"type":"report", content:{title,sections:[{title,content,sources?}],
 *                              sources:[{title,url,snippet?}],summary},
 *                     steps_completed:int, total_sources:int, id:string}
 *   {"type":"error",  content:string}
 * এবং `data: [DONE]` টার্মিনেটর — তা এখানে টাইপ + পার্সারে পিন করা।
 * ব্যাকএন্ড-সাইড পিন: `backend/tests/api/test_deep_research_contract.py`।
 *
 * ঐতিহাসিক নোট: "step_update"/"complete" নামগুলো ছিল ফ্রন্টএন্ড-অভিন্ন
 * ভুল নাম (issue #452) — প্রকৃত ব্যাকএন্ড কখনো সেগুলো পাঠায় না, তাই
 * মৃত শাখা wire-or-delete নীতিতে বাদ (contract টেস্ট রক্ষণাবেক্ষণ করে)।
 */

export interface ParsedResearchStep {
  step_number: number;
  name: string;
  content_preview: string;
}

export interface ParsedResearchReport {
  title: string;
  sections: {
    heading: string;
    content: string;
  }[];
  sources: {
    title: string;
    url: string;
  }[];
  summary: string;
}

export type ParsedResearchEvent =
  | { kind: 'step'; step: ParsedResearchStep }
  | { kind: 'report'; report: ParsedResearchReport; id: string }
  | { kind: 'error'; message: string }
  | { kind: 'ignored' };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/**
 * Parse one raw SSE `data:` payload (already JSON-decoded by the caller).
 * Unknown/malformed shapes → `{kind:'ignored'}` (never throws — non-JSON
 * লাইন ও অচেনা ইভেন্ট নীরবে স্কিপ হওয়াই আজকের panel-আচরণ)।
 */
export function parseResearchEvent(raw: unknown): ParsedResearchEvent {
  if (!isRecord(raw) || typeof raw.type !== 'string') return { kind: 'ignored' };

  if (raw.type === 'step' && typeof raw.step === 'number') {
    return {
      kind: 'step',
      step: {
        step_number: raw.step,
        name: typeof raw.name === 'string' && raw.name ? raw.name : `Step ${raw.step}`,
        content_preview: typeof raw.content === 'string' ? raw.content : '',
      },
    };
  }

  if (raw.type === 'report' && isRecord(raw.content)) {
    const body = raw.content;
    const sections = Array.isArray(body.sections)
      ? body.sections
          .filter(isRecord)
          .map((s) => ({
            heading: String(s.heading ?? s.title ?? ''),
            content: String(s.content ?? ''),
          }))
      : [];
    const sources = Array.isArray(body.sources)
      ? body.sources.filter(isRecord).map((s) => ({
          title: String(s.title ?? ''),
          url: String(s.url ?? ''),
        }))
      : [];
    return {
      kind: 'report',
      id: typeof raw.id === 'string' ? raw.id : '',
      report: {
        title: String(body.title ?? 'Research Report'),
        sections,
        sources,
        summary: String(body.summary ?? ''),
      },
    };
  }

  if (raw.type === 'error') {
    return {
      kind: 'error',
      message:
        (typeof raw.error === 'string' && raw.error) ||
        (typeof raw.content === 'string' && raw.content) ||
        'Research failed unexpectedly',
    };
  }

  return { kind: 'ignored' };
}

/** Parse one raw SSE `data:` LINE (text) → event, or `ignored` for `[DONE]`/non-JSON. */
export function parseResearchSseLine(line: string): ParsedResearchEvent {
  if (!line.startsWith('data: ')) return { kind: 'ignored' };
  const payload = line.slice(6).trim();
  if (!payload || payload === '[DONE]') return { kind: 'ignored' };
  try {
    return parseResearchEvent(JSON.parse(payload));
  } catch {
    return { kind: 'ignored' };
  }
}
