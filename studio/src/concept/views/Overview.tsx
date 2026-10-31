import { motion } from 'framer-motion';
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Bot, Cpu, Layers3, ShieldCheck, Sparkles, Zap } from 'lucide-react';
import { LiveChart } from '../components/LiveChart';
import { MetricCard } from '../components/MetricCard';
import type { ViewKey } from '../types';

type OverviewProps = {
  onNavigate: (view: ViewKey) => void;
  onNotify: (message: string) => void;
};

const agents = [
  { name: 'Research Scout', task: 'Mapping model landscape', status: 'Working', initials: 'RS', tone: 'cyan', usage: '82%', width: '82%' },
  { name: 'Code Pilot', task: 'Reviewing studio routes', status: 'Working', initials: 'CP', tone: 'violet', usage: '64%', width: '64%' },
  { name: 'Signal Curator', task: 'Preparing daily digest', status: 'Ready', initials: 'SC', tone: 'lime', usage: '41%', width: '41%' },
];

const events = [
  { time: 'just now', text: 'Research Scout opened a new task', type: 'cyan' },
  { time: '2m ago', text: 'Studio workspace refreshed', type: 'violet' },
  { time: '5m ago', text: 'Federation check completed', type: 'lime' },
];

export function Overview({ onNavigate, onNotify }: OverviewProps) {
  return (
    <div className="dashboard-view">
      <section className="page-intro overview-intro">
        <div className="intro-copy">
          <div className="eyebrow"><span className="eyebrow-mark" /> FEDERATION / COMMAND SURFACE <span className="eyebrow-divider">·</span> <span className="eyebrow-muted">SAMPLE SIGNALS</span></div>
          <h1>One signal.<br /><em>Everywhere.</em></h1>
          <p>Keep human intent at the center while your ideas move through the SupremeAI ecosystem.</p>
        </div>
        <div className="intro-actions">
          <button className="button button-primary" onClick={() => onNavigate('studio')}><Sparkles size={16} /> Open Studio <ArrowUpRight size={14} /></button>
          <button className="button button-quiet" onClick={() => onNotify('This is a design preview; the guide is still being shaped.')}><span className="play-button">▶</span> Product tour</button>
        </div>
      </section>

      <div className="metrics-grid">
        <MetricCard label="Active agents" value="08" note="Across 4 sample workflows" trend="2 online" icon={<Bot size={17} />} tone="cyan" />
        <MetricCard label="Federation health" value="99.98%" note="Demo availability indicator" trend="0.04%" icon={<ShieldCheck size={17} />} tone="lime" />
        <MetricCard label="Throughput" value="1.28k" note="Illustrative tokens per second" trend="12.8%" icon={<Zap size={17} />} tone="violet" />
        <MetricCard label="Workspaces" value="12" note="Connected surfaces in concept" icon={<Layers3 size={17} />} tone="blue" />
      </div>

      <div className="overview-primary-grid">
        <motion.section className="panel chart-panel" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .08 }}>
          <div className="panel-heading">
            <div><div className="panel-kicker">ACTIVITY PULSE <span className="demo-tag">DEMO</span></div><h2>Agent activity</h2><p>Sample workload over the last 12 hours</p></div>
            <button className="select-pill" type="button" aria-label="Selected timeframe: last 12 hours">12 hours <span>⌄</span></button>
          </div>
          <div className="chart-legend"><span><i className="legend-cyan" /> Orchestration</span><span><i className="legend-lime" /> Completed tasks</span><span className="chart-live"><i /> Illustrative feed</span></div>
          <LiveChart />
          <div className="chart-footer"><span><span className="chart-note-dot" /> Activity data is simulated for this concept</span><button onClick={() => onNavigate('studio')}>Explore Studio <ArrowRight size={13} /></button></div>
        </motion.section>

        <motion.section className="panel health-panel" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .16 }}>
          <div className="panel-heading compact-heading">
            <div><div className="panel-kicker">SYSTEM MAP</div><h2>Federation health</h2></div>
            <button className="dots-button" aria-label="More health panel options" onClick={() => onNotify('System-map details are illustrative in this preview.')}>···</button>
          </div>
          <div className="health-map">
            <div className="health-orbit orbit-one" /><div className="health-orbit orbit-two" />
            <span className="node node-a" /><span className="node node-b" /><span className="node node-c" /><span className="node node-d" />
            <span className="map-link link-a" /><span className="map-link link-b" /><span className="map-link link-c" />
            <div className="health-core"><span>SA</span><i className="health-core-pulse" /></div>
            <div className="network-label label-a"><i className="node-dot dot-cyan" />Studio</div>
            <div className="network-label label-b"><i className="node-dot dot-violet" />VSCode</div>
            <div className="network-label label-c"><i className="node-dot dot-lime" />Mobile</div>
          </div>
          <div className="health-summary"><div><strong>99.98%</strong><span>sample availability</span></div><div className="health-state"><i className="status-dot" /> Concept healthy</div></div>
          <div className="health-meter"><span style={{ width: '86%' }} /></div>
          <p className="health-footnote"><ShieldCheck size={13} /> No live service checks performed</p>
        </motion.section>
      </div>

      <div className="overview-secondary-grid">
        <section className="panel agent-panel">
          <div className="panel-heading">
            <div><div className="panel-kicker">ORCHESTRATION LAYER</div><h2>Agent pulse <span className="count-chip">03</span></h2></div>
            <button className="panel-link" onClick={() => onNotify('Agent statuses shown here are sample states.')}>View all <ArrowRight size={13} /></button>
          </div>
          <div className="agent-list">
            {agents.map((agent, index) => <motion.div className="agent-row" key={agent.name} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: .08 * index }}>
              <div className={`agent-avatar avatar-${agent.tone}`}>{agent.initials}<i /></div>
              <div className="agent-main"><strong>{agent.name}</strong><span>{agent.task}</span></div>
              <div className="agent-usage"><div className="usage-track"><span style={{ width: agent.width }} /></div><span>{agent.usage}</span></div>
              <span className={`agent-state state-${agent.tone}`}><i /> {agent.status}</span>
            </motion.div>)}
          </div>
          <div className="agent-panel-footer"><span><Cpu size={13} /> SIMULATED AGENT STATES</span><button onClick={() => onNavigate('vscode')}>Open developer view <ArrowUpRight size={12} /></button></div>
        </section>

        <section className="panel event-panel">
          <div className="panel-heading"><div><div className="panel-kicker">RECENT SIGNAL</div><h2>What moved</h2></div><span className="event-clock"><Activity size={14} /> LIVE DEMO</span></div>
          <div className="event-list">
            {events.map((event) => <div className="event-row" key={event.text}><span className={`event-icon event-${event.type}`}><ArrowDownRight size={13} /></span><span className="event-copy">{event.text}</span><time>{event.time}</time></div>)}
          </div>
          <button className="all-events-button" onClick={() => onNotify('The event stream is sample content, not connected to your production Tower.')}>Sample event stream <ArrowRight size={13} /></button>
        </section>
      </div>

      <section className="platform-strip">
        <div className="platform-strip-copy"><span className="platform-strip-kicker">BUILT TO TRAVEL WITH YOU</span><h2>One intelligence layer.<br /><em>Every workspace.</em></h2></div>
        <button className="platform-card platform-studio" onClick={() => onNavigate('studio')}><span className="platform-icon"><Sparkles size={17} /></span><span><strong>SupremeAI Studio</strong><small>Think, explore, create.</small></span><ArrowUpRight size={14} /></button>
        <button className="platform-card platform-code" onClick={() => onNavigate('vscode')}><span className="platform-icon"><Code2Icon /></span><span><strong>SupremeAI VSCode</strong><small>Build with context.</small></span><ArrowUpRight size={14} /></button>
        <button className="platform-more" onClick={() => onNavigate('devices')}>Explore every surface <ArrowRight size={13} /></button>
      </section>
    </div>
  );
}

function Code2Icon() {
  return <span className="code2-glyph" aria-hidden="true">&lt;/&gt;</span>;
}
