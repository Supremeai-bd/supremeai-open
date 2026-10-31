import { useState, type FormEvent } from 'react';
import { Activity, ArrowRight, Check, ChevronDown, ChevronRight, Circle, Command, FileCode2, FileJson2, GitBranch, LoaderCircle, Play, Search, Send, ShieldCheck, Sparkles, TerminalSquare } from 'lucide-react';

type VSCodeViewProps = { onNotify: (message: string) => void };

const codeLines = [
  <><span className="syntax-key">export async function</span> <span className="syntax-fn">routeSignal</span>(signal: <span className="syntax-type">IntentSignal</span>) {'{'}</>,
  <>  <span className="syntax-key">const</span> context = <span className="syntax-key">await</span> tower.read({'{'}</>,
  <>    scope: <span className="syntax-string">'federation'</span>,</>,
  <>    intent: signal.intent,</>,
  <>    verify: <span className="syntax-bool">true</span>,</>,
  <>  {'}'});</>,
  <>&nbsp;</>,
  <>  <span className="syntax-comment">// Keep human intent attached to every result.</span></>,
  <>  <span className="syntax-key">return</span> studio.compose({'{'}</>,
  <>    context,</>,
  <>    audience: signal.audience,</>,
  <>    goal: signal.goal,</>,
  <>    mode: <span className="syntax-string">'considered'</span>,</>,
  <>  {'}'});</>,
  <>{'}'}</>,
];

export function VSCodeView({ onNotify }: VSCodeViewProps) {
  const [running, setRunning] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [draft, setDraft] = useState('');
  const [assistantText, setAssistantText] = useState('I’ve mapped the flow from user intent into the Studio workspace. Want me to review the handoff or expand this into a test?');

  function runReview() {
    if (running) return;
    setRunning(true);
    setReviewed(false);
    window.setTimeout(() => {
      setRunning(false);
      setReviewed(true);
      setAssistantText('Review complete. The handoff preserves the original intent, and the simulated context check passed. This result is part of the UI preview.');
      onNotify('Demo code review complete — nothing was sent to a backend.');
    }, 1350);
  }

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question) return;
    setAssistantText(`For “${question}” — keep the handoff contract small and inspectable. In the full VSCode client, this panel would use your selected AI route.`);
    setDraft('');
  }

  return (
    <div className="vscode-view">
      <section className="page-intro code-intro">
        <div className="intro-copy"><div className="eyebrow"><span className="eyebrow-mark" /> SUPREMEAI VSCODE <span className="eyebrow-divider">·</span> <span className="eyebrow-muted">DEVELOPER COMPANION</span></div><h1>Build with<br /><em>the full picture.</em></h1><p>Bring context into your editor and keep your next move close to the code.</p></div>
        <div className="code-intro-actions"><span className="editor-ready"><i /> EDITOR PREVIEW</span><button className="button button-primary" onClick={runReview} disabled={running}>{running ? <LoaderCircle size={15} className="spin" /> : <Play size={14} fill="currentColor" />} {running ? 'Reviewing…' : 'Run demo review'}</button></div>
      </section>

      <section className="workbench panel">
        <div className="workbench-topbar"><div className="window-lights" aria-hidden="true"><i /><i /><i /></div><div className="workbench-title"><span>supremeai-studio</span><ChevronRight size={12} /><strong>packages / federation / signal.ts</strong></div><div className="workbench-actions"><span className="workbench-branch"><GitBranch size={13} /> preview</span><button type="button" aria-label="Search in files" onClick={() => onNotify('Search is a visual affordance in this preview.')}><Search size={14} /></button></div></div>
        <div className="workbench-tabs"><div className="workbench-tab active"><FileCode2 size={14} /><span>signal.ts</span><Circle size={7} fill="currentColor" /></div><div className="workbench-tab"><FileJson2 size={14} /><span>dashboard.schema.json</span></div><div className="workbench-tab-spacer" /><span className="editor-demo-badge">READ-ONLY CONCEPT</span></div>
        <div className="workbench-body">
          <aside className="explorer"><div className="explorer-head"><span>EXPLORER</span><button aria-label="Explorer options" onClick={() => onNotify('This repository tree is illustrative.')}>···</button></div><div className="repo-name"><ChevronDown size={12} /> <strong>SUPREMEAI-STUDIO</strong></div><div className="tree-row"><ChevronDown size={12} /> <span className="folder-glyph">▾</span> src</div><div className="tree-row indent"><ChevronDown size={12} /> <span className="folder-glyph">▾</span> federation</div><div className="tree-row file active indent-two"><FileCode2 size={13} /> signal.ts</div><div className="tree-row file indent-two"><FileJson2 size={13} /> dashboard.schema.json</div><div className="tree-row"><ChevronRight size={12} /> <span className="folder-glyph">▸</span> components</div><div className="tree-row"><ChevronRight size={12} /> <span className="folder-glyph">▸</span> packages</div><div className="explorer-separator" /><div className="explorer-foot"><span><Activity size={12} /> Demo workspace</span><small>Not connected to git</small></div></aside>
          <div className="editor-column"><div className="editor-breadcrumb"><span>src</span><ChevronRight size={11} /><span>federation</span><ChevronRight size={11} /><strong>signal.ts</strong><span className="editor-language">TypeScript</span></div><div className="code-editor" role="region" aria-label="Illustrative TypeScript editor code"><div className="code-lines">{codeLines.map((line, index) => <div className={`code-line ${index === 7 ? 'line-highlight' : ''}`} key={index}><span className="line-number">{String(index + 1).padStart(2, '0')}</span><code>{line}</code></div>)}</div><div className="editor-watermark" aria-hidden="true">SAI</div></div><div className="terminal-bar"><span className="terminal-tab active"><TerminalSquare size={13} /> OUTPUT</span><span className="terminal-tab">PROBLEMS <i>0</i></span><span className="terminal-tab">AGENT LOG</span><span className="terminal-spacer" /><span className="terminal-status">{reviewed ? <><Check size={12} /> DEMO REVIEW PASSED</> : <><Circle size={7} fill="currentColor" /> SAMPLE OUTPUT</>}</span></div><div className="terminal-output"><span className="terminal-prompt">›</span> {reviewed ? 'Context boundary clear. No external request was made.' : 'Awaiting a local demo action. Your code stays in this preview.'}</div></div>
          <aside className="companion-panel"><div className="companion-heading"><span className="companion-mark"><Sparkles size={15} /></span><span><strong>SupremeAI</strong><small>Context companion</small></span><button aria-label="Companion options" onClick={() => onNotify('Companion configuration will be part of a connected product.')}>···</button></div><div className="context-chip"><ShieldCheck size={13} /><span>Context window</span><i>SAFE</i></div><div className="assistant-message"><p>{assistantText}</p><div className="assistant-meta"><span><span className="tiny-orbit" /> SAMPLE RESPONSE</span><span>JUST NOW</span></div></div><div className="review-result"><div className="review-result-head"><span className="review-spark"><Sparkles size={13} /></span><span><strong>Review handoff</strong><small>Preserve intent across surfaces</small></span><span className={`review-badge ${reviewed ? 'review-done' : ''}`}>{reviewed ? 'PASSED' : 'READY'}</span></div><div className="review-progress"><span className={running ? 'review-running' : reviewed ? 'review-complete' : ''} /></div><button className="review-card-button" onClick={runReview} disabled={running}>{running ? <><LoaderCircle size={13} className="spin" /> Reviewing context</> : <><Check size={13} /> {reviewed ? 'Run again' : 'Run local demo'} <ArrowRight size={13} /></>}</button></div><form className="companion-input" onSubmit={ask}><label className="sr-only" htmlFor="companion-question">Ask the SupremeAI companion</label><input id="companion-question" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about this code…" /><button type="submit" aria-label="Send question" disabled={!draft.trim()}><Send size={14} /></button></form><div className="companion-privacy">Concept only · no code or prompts leave this page</div></aside>
        </div>
        <div className="workbench-statusbar"><span><GitBranch size={12} /> preview</span><span><Circle size={7} fill="currentColor" /> 0 problems</span><span className="status-spacer" /><span>UTF-8</span><span>TypeScript</span><span><Command size={11} /> SupremeAI preview</span></div>
      </section>
      <div className="code-callout"><span className="callout-icon"><Sparkles size={15} /></span><p><strong>Context first, autocomplete second.</strong> The VSCode concept shows where assistant guidance meets real developer workflows.</p><button onClick={() => onNotify('This editor is a clickable design prototype, not an installed VSCode extension.')}>What’s in the extension? <ArrowRight size={13} /></button></div>
    </div>
  );
}
