import { useState, type FormEvent } from 'react';
import { ArrowDown, ArrowRight, ArrowUpRight, Check, Clock3, FileText, Image, LoaderCircle, Plus, Send, Sparkles, Workflow } from 'lucide-react';

type StudioViewProps = { onNotify: (message: string) => void };

const suggestions = ['Map a research sprint', 'Draft a product story', 'Turn notes into a workflow'];
const queue = [
  { title: 'Market map · AI copilots', kind: 'Research synthesis', status: 'Ready', tone: 'cyan', icon: FileText },
  { title: 'Onboarding storyboards', kind: 'Visual exploration', status: 'In progress', tone: 'violet', icon: Image },
  { title: 'Agent handoff flow', kind: 'Workflow design', status: 'Queued', tone: 'lime', icon: Workflow },
];

export function StudioView({ onNotify }: StudioViewProps) {
  const [prompt, setPrompt] = useState('');
  const [running, setRunning] = useState(false);
  const [taskTitle, setTaskTitle] = useState('Shape a new idea into a clear first move');
  const [step, setStep] = useState(1);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = prompt.trim();
    if (!clean || running) return;
    setTaskTitle(clean);
    setPrompt('');
    setRunning(true);
    setStep(1);
    window.setTimeout(() => setStep(2), 550);
    window.setTimeout(() => {
      setRunning(false);
      setStep(3);
      onNotify('Preview workflow complete — this is a local interaction, not a live Tower task.');
    }, 1700);
  }

  return (
    <div className="studio-view">
      <section className="page-intro studio-intro">
        <div className="intro-copy">
          <div className="eyebrow"><span className="eyebrow-mark" /> SUPREMEAI STUDIO <span className="eyebrow-divider">·</span> <span className="eyebrow-muted">CREATIVE COMMAND</span></div>
          <h1>Make ideas<br /><em>move forward.</em></h1>
          <p>Bring rough intent into focus. Then shape a clear next step with your AI workspace.</p>
        </div>
        <div className="studio-intro-badge"><span className="studio-orbit-small"><i /></span><span><strong>Studio is ready</strong><small>Creative preview mode</small></span></div>
      </section>

      <div className="studio-layout">
        <section className="panel studio-workspace-panel">
          <div className="studio-panel-head"><div><span className="panel-kicker">INTENT WORKSPACE <span className="demo-tag">SIMULATION</span></span><h2>What are we making?</h2></div><button className="dots-button" type="button" aria-label="Studio workspace options" onClick={() => onNotify('More Studio actions are coming soon.')}>···</button></div>
          <div className="intent-stage">
            <div className="intent-stage-wash" aria-hidden="true" />
            <div className="intent-orbit orbit-large"><span /><i /><b /></div>
            <div className="intent-orbit orbit-medium"><span /><i /></div>
            <div className="intent-orb"><Sparkles size={21} /><small>SAI</small></div>
            <div className="intent-label label-intent"><span>01</span><strong>Intent</strong><small>Find the core</small></div>
            <div className="intent-label label-context"><span>02</span><strong>Context</strong><small>Bring the signal</small></div>
            <div className="intent-label label-creation"><span>03</span><strong>Creation</strong><small>Shape what’s next</small></div>
            <div className="orbit-caption"><span className="pulse-dot" /> YOUR WORKSPACE IS WARM</div>
          </div>
          <div className="studio-composer-wrap">
            <form className="studio-composer" onSubmit={submit}>
              <label className="sr-only" htmlFor="studio-prompt">Describe what you want to create</label>
              <textarea id="studio-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Describe what you want to explore, make, or understand…" rows={2} />
              <div className="composer-footer"><span><span className="composer-spark">✳</span> Ideas stay yours. AI helps you find their shape.</span><button className="send-round" type="submit" disabled={!prompt.trim() || running} aria-label="Run simulated Studio workflow">{running ? <LoaderCircle size={16} className="spin" /> : <Send size={15} />}</button></div>
            </form>
            <div className="suggestion-row"><span>START WITH</span>{suggestions.map((item) => <button key={item} type="button" onClick={() => setPrompt(item)}>{item}<ArrowUpRight size={11} /></button>)}</div>
          </div>
        </section>

        <aside className="studio-right-column">
          <section className="panel focus-panel">
            <div className="panel-kicker">ACTIVE CREATION <span className="live-pill"><i /> DEMO</span></div>
            <h2>{taskTitle}</h2>
            <p className="focus-copy">A focused first pass is taking shape. Review the trail, then choose what deserves more attention.</p>
            <div className="workflow-steps">
              {[['Capture intent', 'Reading the initial signal'], ['Find the pattern', 'Connect ideas and context'], ['Create a next move', 'Turn direction into action']].map(([title, desc], index) => <div className={`workflow-step ${step >= index + 1 ? 'step-active' : ''} ${step > index + 1 ? 'step-done' : ''}`} key={title}><span className="step-icon">{step > index + 1 ? <Check size={13} /> : index + 1}</span><span><strong>{title}</strong><small>{desc}</small></span>{index < 2 && <span className="step-connector" />}</div>)}
            </div>
            <div className="focus-card-footer"><span><Clock3 size={13} /> Sample run · 02 sec</span><button className="button button-small" type="button" onClick={() => onNotify('Workflow details are a concept. No external task was created.')}>View notes <ArrowRight size={12} /></button></div>
          </section>
          <section className="panel queue-panel">
            <div className="panel-heading compact-heading"><div><div className="panel-kicker">YOUR CREATIVE QUEUE</div><h2>In motion <span className="count-chip">03</span></h2></div><button className="add-small" aria-label="Add a demo workflow" onClick={() => onNotify('A new workflow can be created in the full Studio product.')}><Plus size={15} /></button></div>
            <div className="queue-list">{queue.map((item) => { const Icon = item.icon; return <button className="queue-item" key={item.title} type="button" onClick={() => { setTaskTitle(item.title); onNotify(`${item.title} opened as sample content.`); }}><span className={`queue-icon queue-${item.tone}`}><Icon size={15} /></span><span className="queue-item-copy"><strong>{item.title}</strong><small>{item.kind}</small></span><span className={`queue-status status-${item.tone}`}>{item.status}</span></button>; })}</div>
            <button className="queue-all" onClick={() => onNotify('The queue is illustrative in this preview.')}>View all creations <ArrowDown size={13} /></button>
          </section>
        </aside>
      </div>
    </div>
  );
}
