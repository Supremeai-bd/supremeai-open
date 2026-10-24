// বাংলা মন্তব্য: Execution Mode — user-facing ৩টি মোড (Settings page-এ থাকবে,
// main dashboard-এ নয়)। Admin অন্য user-এর মোড বদলাতে পারবে; user শুধু নিজেরটা।

export const EXECUTION_MODES = ['read_only', 'ask_before_acting', 'autonomous'] as const;

export type ExecutionMode = (typeof EXECUTION_MODES)[number];

export const DEFAULT_EXECUTION_MODE: ExecutionMode = 'ask_before_acting';

export const EXECUTION_MODE_LABELS: Record<ExecutionMode, string> = {
  read_only: 'Read-only mode',
  ask_before_acting: 'Ask before acting',
  autonomous: 'Act autonomously',
};

export function isExecutionMode(value: unknown): value is ExecutionMode {
  return typeof value === 'string' && (EXECUTION_MODES as readonly string[]).includes(value);
}
