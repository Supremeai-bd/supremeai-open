import React, { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Check, ExternalLink, Loader2, ShieldCheck, Square, WandSparkles } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { policyService } from '../../services/policyService';

type TaskState = 'idle' | 'planning' | 'ready' | 'running' | 'complete' | 'blocked';

interface TaskPlan {
  title: string;
  steps: string[];
  note: string;
  risk: 'low' | 'approval' | 'manual';
}

const blockedWords = ['payment', 'pay', 'password', 'change security', 'delete account', 'wire transfer'];

function buildPlan(url: string, goal: string): TaskPlan {
  const lower = goal.toLowerCase();
  if (blockedWords.some((word) => lower.includes(word))) {
    return { title: 'This needs you to finish it manually', steps: ['Open the website for you', 'Show you where the sensitive action is'], note: 'SupremeAI does not have permission to make payments, change passwords, or perform account-destructive actions. You can complete that step yourself.', risk: 'manual' };
  }
  const research = /find|research|read|summar|collect|look up/i.test(goal);
  let siteLabel = 'Open the website';
  if (url.trim()) {
    try { siteLabel = `Open ${new URL(url).hostname}`; } catch { siteLabel = 'Open the website link you provided'; }
  }
  return { title: research ? 'I can research this for you' : 'I can help with this task', steps: [siteLabel, 'Understand the page and your goal', research ? 'Read the relevant public information' : 'Prepare the requested action', 'Show you the result before anything sensitive'], note: 'I will pause if the site asks for a login, payment, password, or an action that needs your personal approval.', risk: research ? 'low' : 'approval' };
}

export const TaskAutomationCard: React.FC = () => {
  const [url, setUrl] = useState('');
  const [goal, setGoal] = useState('');
  const [state, setState] = useState<TaskState>('idle');
  const [plan, setPlan] = useState<TaskPlan | null>(null);
  const [message, setMessage] = useState('');
  const policyQuery = useQuery({ queryKey: ['browser-policy'], queryFn: policyService.get });
  const policyMutation = useMutation({ mutationFn: policyService.updatePersonal, onSuccess: () => policyQuery.refetch() });
  const approvalEnabled = policyQuery.data?.rules?.allow_submissions !== false;

  const createPlan = () => {
    if (!goal.trim()) return;
    setState('planning');
    setMessage('');
    setPlan(buildPlan(url, goal));
    setState('ready');
  };

  const startTask = async () => {
    if (!plan || plan.risk === 'manual') { setState('blocked'); return; }
    setState('running');
    try {
      const response = await apiClient.post<{ message?: string }>('/api/browser/tasks/preview', { url: url || null, goal, approved: true });
      setMessage(response.message || 'Your task is underway. We will show the result here.');
      setState('complete');
    } catch {
      setMessage('I could not start this yet. Your information is safe; please check the saved site session and try again.');
      setState('blocked');
    }
  };

  return <section className="sa-surface-raised overflow-hidden" aria-labelledby="task-automation-heading">
    <div className="border-b border-[var(--sa-border)] px-5 py-5 sm:px-7">
      <div className="flex items-start gap-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--sa-primary-soft)] text-[var(--sa-primary)]"><WandSparkles size={19} /></span><div><p className="sa-eyebrow">New: simple site tasks</p><h2 id="task-automation-heading" className="mt-1 text-xl font-semibold">Tell me what to do on a website</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--sa-ink-muted)]">Add a link and explain your goal in everyday words. SupremeAI will make a clear plan first—no technical setup needed.</p></div></div>
    </div>
    <div className="mx-5 mt-5 flex items-center justify-between gap-3 rounded-xl border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-4 py-3 sm:mx-7"><div><p className="text-sm font-medium">My approval preference</p><p className="text-xs text-[var(--sa-ink-muted)]">You can turn off posting, sending, and submitting for yourself.</p></div><button type="button" role="switch" aria-checked={approvalEnabled} onClick={() => policyMutation.mutate({ allow_submissions: !approvalEnabled })} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${approvalEnabled ? 'bg-[var(--sa-primary-soft)] text-[var(--sa-primary)]' : 'bg-[var(--sa-border)] text-[var(--sa-ink-muted)]'}`}>{approvalEnabled ? 'Allowed with approval' : 'Off for me'}</button></div><div className="grid gap-4 px-5 py-5 sm:px-7 lg:grid-cols-[0.85fr_1.15fr]">
      <div className="flex flex-col gap-3"><label className="text-sm font-medium" htmlFor="task-url">Website link <span className="font-normal text-[var(--sa-ink-muted)]">(optional)</span></label><div className="flex items-center gap-2 rounded-xl border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-3 focus-within:border-[var(--sa-primary)]"><ExternalLink size={15} className="text-[var(--sa-ink-muted)]" /><input id="task-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" className="min-w-0 flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-[var(--sa-ink-muted)]" /></div><label className="mt-1 text-sm font-medium" htmlFor="task-goal">What would you like done?</label><textarea id="task-goal" value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="For example: Find the latest public information about this company and give me a short summary." rows={4} className="resize-none rounded-xl border border-[var(--sa-border)] bg-[var(--sa-canvas)] px-3 py-3 text-sm leading-6 outline-none placeholder:text-[var(--sa-ink-muted)] focus:border-[var(--sa-primary)]" /><button type="button" onClick={createPlan} disabled={!goal.trim() || state === 'planning'} className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--sa-primary)] px-4 py-3 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">{state === 'planning' ? <Loader2 size={16} className="animate-spin" /> : <WandSparkles size={16} />} Make a simple plan</button></div>
      <div className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-canvas)] p-5" aria-live="polite">{!plan && <div className="flex h-full min-h-56 flex-col items-center justify-center text-center"><ShieldCheck size={28} className="text-[var(--sa-primary)]" /><h3 className="mt-3 text-sm font-semibold">You stay in control</h3><p className="mt-2 max-w-xs text-xs leading-5 text-[var(--sa-ink-muted)]">I will explain what I plan to do before I touch a website. Payments and sensitive account changes always stay manual.</p></div>}{plan && <><p className="sa-eyebrow">Your plan</p><h3 className="mt-2 text-lg font-semibold">{plan.title}</h3><ol className="mt-4 flex flex-col gap-3">{plan.steps.map((step, index) => <li key={step} className="flex items-start gap-3 text-sm"><span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--sa-primary-soft)] text-xs font-semibold text-[var(--sa-primary)]">{index + 1}</span><span className="pt-0.5">{step}</span></li>)}</ol><div className={`mt-5 rounded-xl border px-3 py-3 text-xs leading-5 ${plan.risk === 'manual' ? 'border-amber-300/60 bg-amber-50 text-amber-900' : 'border-[var(--sa-border)] bg-[var(--sa-surface)] text-[var(--sa-ink-muted)]'}`}><strong className="font-semibold">{plan.risk === 'manual' ? 'Manual step:' : plan.risk === 'approval' ? 'Approval needed:' : 'Safe to start:'}</strong> {plan.note}</div>{state === 'ready' && <button type="button" onClick={startTask} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--sa-primary)] px-4 py-3 text-sm font-semibold text-white hover:opacity-90">{plan.risk === 'manual' ? 'I understand' : 'Start this task'} <Check size={16} /></button>}{state === 'running' && <div className="mt-4 flex items-center justify-center gap-2 rounded-xl border border-[var(--sa-border)] px-4 py-3 text-sm"><Loader2 size={16} className="animate-spin" /> Working carefully…</div>}{(state === 'complete' || state === 'blocked') && <div className="mt-4 flex items-start gap-2 rounded-xl border border-[var(--sa-border)] bg-[var(--sa-surface)] px-3 py-3 text-sm"><Square size={14} className="mt-1 text-[var(--sa-primary)]" /> <span>{message || 'This action stays manual. You can continue on the website yourself.'}</span></div>}</>}</div>
    </div>
  </section>;
};

export default TaskAutomationCard;
