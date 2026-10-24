/**
 * studio/src/content/academies/mcpAcademy.ts — Academy course content (Way 5).
 *
 * বাংলা: "MCP Control Plane Academy" — প্রথম exemplar কোর্স। lessons + quiz +
 * XP — সম্পূর্ণ ডেটা লোকালস্টোরেজে (Infinity প্যাটার্ন: local progress)।
 *
 * Content-only module: no imports, no side effects. The AcademyHubPage renders
 * whatever Academy[] modules live here — new courses = new data files (P3).
 */

export interface QuizQuestion {
  prompt: string;
  options: string[];
  answerIndex: number;
  explain: string;
}

export interface Lesson {
  id: string;
  title: string;
  minutes: number;
  /** Short markdown-ish body (paragraphs separated by \n\n). */
  body: string;
  quiz: QuizQuestion[];
}

export interface Academy {
  id: string;
  title: string;
  tagline: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  lessons: Lesson[];
}

export const mcpAcademy: Academy = {
  id: 'mcp-control-plane',
  title: 'MCP Control Plane Academy',
  tagline: 'How SupremeAI talks to tools: the Model Context Protocol, tower, and bridge.',
  level: 'beginner',
  lessons: [
    {
      id: 'mcp-101',
      title: 'MCP 101 — one protocol, every tool',
      minutes: 6,
      body: [
        'The Model Context Protocol (MCP) is a JSON-RPC contract that lets a model call tools without bespoke glue code. A server exposes tools via `tools/list`; a client calls them via `tools/call`; results come back as content blocks.',
        'SupremeAI runs an MCP control plane (the "tower") that fronts GitHub, Redis, Render, Cloudflare and its own bridge. One authenticated session, many tools — no per-service credentials in agent hands.',
        'Key idea: the protocol is stateful per session. A `mcp-session-id` from `initialize` must ride along every later call; lose it and the tower fail-closes with a session error (never guesses).',
      ].join('\n\n'),
      quiz: [
        {
          prompt: 'Which method lists the tools a server offers?',
          options: ['tools/list', 'tools/call', 'initialize', 'resources/read'],
          answerIndex: 0,
          explain: '`tools/list` enumerates capabilities; `tools/call` executes one.',
        },
        {
          prompt: 'What happens when the session id is missing from a call?',
          options: [
            'The tower auto-creates a new session',
            'The call fails closed with a session error',
            'The call runs anonymously',
            'The tool results are cached instead',
          ],
          answerIndex: 1,
          explain: 'SupremeAI fails closed — no session, no execution.',
        },
      ],
    },
    {
      id: 'mcp-security',
      title: 'Security — zero-credential agents & protected paths',
      minutes: 7,
      body: [
        'Agents never hold GitHub tokens. The bridge is "zero-credential": work claims, patches, and feedback all flow through the tower, which holds the only real credentials.',
        'Writes to sensitive surfaces (.github/, prisma/, .env*) are rejected for the agent lane — an admin-role executor must apply them. This is the protected-path guard.',
        'Every tool result that echoes a secret family (sk-, ghp_, AKIA…) is redacted before it reaches a model. Audit logs record the event class, never the secret.',
      ].join('\n\n'),
      quiz: [
        {
          prompt: 'How does an external agent open a PR without repo credentials?',
          options: [
            'It forks the repo with its own token',
            'Via the zero-credential bridge submit path',
            'It emails a maintainer',
            'It writes directly to main',
          ],
          answerIndex: 1,
          explain: 'bridge_submit_patch creates the branch + issue server-side.',
        },
        {
          prompt: 'What happens when a patch touches a protected path?',
          options: [
            'It lands after a delay',
            'It lands with extra logging',
            'The lane rejects it for an admin-role executor',
            'It silently skips the file',
          ],
          answerIndex: 2,
          explain: 'Protected paths fail closed for the agent lane.',
        },
      ],
    },
    {
      id: 'mcp-bridge-lifecycle',
      title: 'The bridge lifecycle — claim, patch, gates, land',
      minutes: 8,
      body: [
        'Work orders are issues with labels. `work_claim` grants a 30-minute atomic lease (GRANT_NEW) so two agents never build the same slice; `work_renew` extends, `work_release` frees.',
        'A delivered patch becomes a branch `bridge/<task-id>` plus a work-order issue. The constitutional gates (CI Guardian) then verify scope, shape, and tests — the bridge itself never merges.',
        'Discipline rules: U2 evidence-first (verify base bytes before patching), P3 shape-preserving (response contracts do not change), P7 one atomic slice per cycle.',
      ].join('\n\n'),
      quiz: [
        {
          prompt: 'Who merges bridge patches into main?',
          options: [
            'The submitting agent',
            'The bridge dispatcher',
            'The constitutional gates only',
            'A human admin, always',
          ],
          answerIndex: 2,
          explain: '"The bridge never merges" — gates hold landing authority.',
        },
        {
          prompt: 'Why does work_claim hand out a 30-minute lease?',
          options: [
            'To bill agents hourly',
            'To make claims atomic and prevent duplicate work',
            'To limit repo bandwidth',
            'To throttle CI',
          ],
          answerIndex: 1,
          explain: 'U4 zero-duplicate: one claim, one owner, at a time.',
        },
      ],
    },
  ],
};

export const academies: Academy[] = [mcpAcademy];
