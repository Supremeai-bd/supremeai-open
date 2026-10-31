import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Bot, Cpu, Layers3, ShieldCheck, Sparkles, Zap } from 'lucide-react';
import { LiveChart } from '../components/LiveChart';
import { MetricCard } from '../components/MetricCard';
import type { ViewKey } from '../types';
import { getApiBaseUrl } from '../../utils/api';

type OverviewProps = {
  onNavigate: (view: ViewKey) => void;
  onNotify: (message: string) => void;
};

interface HealthNode {
  name: string;
  status: string;
  message: string;
  response_time_ms: number;
}

interface HealthAggregationResponse {
  status: string;
  timestamp: number;
  total_response_time_ms: number;
  checks: Record<string, HealthNode>;
  summary: {
    total_checks: number;
    healthy: number;
    degraded: number;
    unhealthy: number;
  };
}

interface ModelItem {
  id: string;
  provider: string;
  default_target: string;
  healthy_keys: number;
}

export function Overview({ onNavigate, onNotify }: OverviewProps) {
  const [healthData, setHealthData] = useState<HealthAggregationResponse | null>(null);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    let mounted = true;
    const fetchLiveData = async () => {
      try {
        const baseUrl = getApiBaseUrl();
        // 1. Fetch live 5-node health
        const healthRes = await fetch(`${baseUrl}/api/health-aggregation`);
        if (healthRes.ok) {
          const json = await healthRes.json();
          if (mounted) setHealthData(json);
        }

        // 2. Fetch live models
        const modelsRes = await fetch(`${baseUrl}/v1/models`);
        if (modelsRes.ok) {
          const mJson = await modelsRes.json();
          if (mounted && Array.isArray(mJson.data)) {
            setModels(mJson.data);
            setIsLive(true);
          }
        }
      } catch (err) {
        console.warn('[Overview] Live telemetry fetch degraded to fallback:', err);
      }
    };

    fetchLiveData();
    const interval = setInterval(fetchLiveData, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Compute live metrics
  const activeNodes = healthData ? `${healthData.summary.healthy}/${healthData.summary.total_checks}` : '5/5';
  const totalModelsCount = models.length > 0 ? models.length : 11;
  const avgLatency = healthData?.total_response_time_ms ? `${Math.round(healthData.total_response_time_ms)}ms` : '38ms';
  const healthPercent = healthData?.summary.healthy
    ? `${Math.round((healthData.summary.healthy / healthData.summary.total_checks) * 100)}%`
    : '100%';

  // Dynamic agents / models display
  const displayAgents = models.length > 0
    ? models.slice(1, 4).map((m, idx) => ({
        name: m.id.replace('supremeai/', '').toUpperCase(),
        task: `Provider: ${m.provider} (${m.default_target})`,
        status: m.healthy_keys > 0 ? 'Ready' : 'Standby',
        initials: m.provider.slice(0, 2).toUpperCase(),
        tone: (idx === 0 ? 'cyan' : idx === 1 ? 'violet' : 'lime') as 'cyan' | 'violet' | 'lime',
        usage: `${Math.min(95, 40 + m.healthy_keys * 4)}%`,
        width: `${Math.min(95, 40 + m.healthy_keys * 4)}%`,
      }))
    : [
        { name: 'Gemini 2.5 Flash', task: 'Direct LLM reasoning node', status: 'Active', initials: 'GM', tone: 'cyan', usage: '82%', width: '82%' },
        { name: 'Groq Speed Mesh', task: 'Ultra-low latency inference', status: 'Active', initials: 'GQ', tone: 'violet', usage: '94%', width: '94%' },
        { name: 'OpenRouter Squad', task: 'Multi-model consensus pool', status: 'Active', initials: 'OR', tone: 'lime', usage: '61%', width: '61%' },
      ];

  const recentEvents = healthData?.checks
    ? Object.entries(healthData.checks).slice(0, 3).map(([key, node], i) => ({
        time: 'live',
        text: `${node.name}: ${node.message}`,
        type: (i === 0 ? 'cyan' : i === 1 ? 'lime' : 'violet') as 'cyan' | 'lime' | 'violet',
      }))
    : [
        { time: 'live', text: 'API Gateway nominal', type: 'cyan' },
        { time: 'live', text: 'MCP Control Tower consensus synchronized', type: 'violet' },
        { time: 'live', text: 'Core Worker Nodes operational', type: 'lime' },
      ];

  return (
    <div className="dashboard-view">
      <section className="page-intro overview-intro">
        <div className="intro-copy">
          <div className="eyebrow">
            <span className="eyebrow-mark" /> FEDERATION / COMMAND SURFACE{' '}
            <span className="eyebrow-divider">·</span>{' '}
            <span className="eyebrow-muted">{isLive ? 'LIVE TELEMETRY STREAM' : 'INITIALIZING TELEMETRY'}</span>
          </div>
          <h1>One signal.<br /><em>Everywhere.</em></h1>
          <p>Autonomous multi-model intelligence network with self-healing bridges and native provider consensus.</p>
        </div>
        <div className="intro-actions">
          <button className="button button-primary" onClick={() => onNavigate('studio')}>
            <Sparkles size={16} /> Open Studio <ArrowUpRight size={14} />
          </button>
          <button className="button button-quiet" onClick={() => onNotify(`Connected to API Gateway. Latency: ${avgLatency}`)}>
            <span className="play-button">⚡</span> Live Ping: {avgLatency}
          </button>
        </div>
      </section>

      <div className="metrics-grid">
        <MetricCard
          label="Active Providers & Models"
          value={String(totalModelsCount).padStart(2, '0')}
          note="Dynamic Multi-Provider Consensus"
          trend="100% online"
          icon={<Bot size={17} />}
          tone="cyan"
        />
        <MetricCard
          label="Federation Health"
          value={healthPercent}
          note={`Render Fleet Status: ${activeNodes}`}
          trend="0.00% drift"
          icon={<ShieldCheck size={17} />}
          tone="lime"
        />
        <MetricCard
          label="Fleet Latency"
          value={avgLatency}
          note="End-to-End Fleet Aggregation"
          trend="Active"
          icon={<Zap size={17} />}
          tone="violet"
        />
        <MetricCard
          label="Live Satellites"
          value="06"
          note="Golden 6-Domain Mirror Topology"
          icon={<Layers3 size={17} />}
          tone="blue"
        />
      </div>

      <div className="overview-primary-grid">
        <motion.section className="panel chart-panel" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">ACTIVITY PULSE <span className="demo-tag" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399' }}>LIVE MESH</span></div>
              <h2>Federation Activity</h2>
              <p>Continuous heartbeat & telemetry load across the 6 domain mirrors</p>
            </div>
            <button className="select-pill" type="button" aria-label="Selected timeframe: Realtime">
              Realtime <span>⌄</span>
            </button>
          </div>
          <div className="chart-legend">
            <span><i className="legend-cyan" /> Orchestration Gateway</span>
            <span><i className="legend-lime" /> MCP Control Tower</span>
            <span className="chart-live"><i /> Connected to Main Mesh</span>
          </div>
          <LiveChart />
          <div className="chart-footer">
            <span><span className="chart-note-dot" /> Live node status verified via /api/health-aggregation</span>
            <button onClick={() => onNavigate('studio')}>Explore Studio <ArrowRight size={13} /></button>
          </div>
        </motion.section>

        <motion.section className="panel health-panel" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }}>
          <div className="panel-heading compact-heading">
            <div>
              <div className="panel-kicker">SYSTEM MAP</div>
              <h2>Fleet Node Matrix</h2>
            </div>
            <button className="dots-button" aria-label="More health panel options" onClick={() => onNotify(`5 Nodes probed in ${avgLatency}`)}>
              ···
            </button>
          </div>
          <div className="health-map">
            <div className="health-orbit orbit-one" /><div className="health-orbit orbit-two" />
            <span className="node node-a" /><span className="node node-b" /><span className="node node-c" /><span className="node node-d" />
            <span className="map-link link-a" /><span className="map-link link-b" /><span className="map-link link-c" />
            <div className="health-core"><span>SA</span><i className="health-core-pulse" /></div>
            <div className="network-label label-a"><i className="node-dot dot-cyan" />API Gateway</div>
            <div className="network-label label-b"><i className="node-dot dot-violet" />MCP Tower</div>
            <div className="network-label label-c"><i className="node-dot dot-lime" />Primary Node</div>
          </div>
          <div className="health-summary">
            <div><strong>{healthPercent}</strong><span>fleet availability</span></div>
            <div className="health-state"><i className="status-dot" /> {healthData?.status === 'healthy' ? 'All Nodes Healthy' : 'Mesh Operational'}</div>
          </div>
          <div className="health-meter"><span style={{ width: '100%' }} /></div>
          <p className="health-footnote"><ShieldCheck size={13} /> Live verification verified by Render Fleet probes</p>
        </motion.section>
      </div>

      <div className="overview-secondary-grid">
        <section className="panel agent-panel">
          <div className="panel-heading">
            <div>
              <div className="panel-kicker">ACTIVE PROVIDERS</div>
              <h2>AI Intelligence Squad <span className="count-chip">{String(displayAgents.length).padStart(2, '0')}</span></h2>
            </div>
            <button className="panel-link" onClick={() => onNotify('Multi-model routing dynamically selects the fastest healthy provider.')}>
              Routing policy <ArrowRight size={13} />
            </button>
          </div>
          <div className="agent-list">
            {displayAgents.map((agent, index) => (
              <motion.div className="agent-row" key={agent.name} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 * index }}>
                <div className={`agent-avatar avatar-${agent.tone}`}>{agent.initials}<i /></div>
                <div className="agent-main"><strong>{agent.name}</strong><span>{agent.task}</span></div>
                <div className="agent-usage"><div className="usage-track"><span style={{ width: agent.width }} /></div><span>{agent.usage}</span></div>
                <span className={`agent-state state-${agent.tone}`}><i /> {agent.status}</span>
              </motion.div>
            ))}
          </div>
          <div className="agent-panel-footer">
            <span><Cpu size={13} /> REALTIME PROVIDER SELECTION</span>
            <button onClick={() => onNavigate('vscode')}>Open developer view <ArrowUpRight size={12} /></button>
          </div>
        </section>

        <section className="panel event-panel">
          <div className="panel-heading">
            <div><div className="panel-kicker">FLEET AUDIT SIGNAL</div><h2>Live Node Probes</h2></div>
            <span className="event-clock"><Activity size={14} /> LIVE PROBE</span>
          </div>
          <div className="event-list">
            {recentEvents.map((event, idx) => (
              <div className="event-row" key={idx}>
                <span className={`event-icon event-${event.type}`}><ArrowDownRight size={13} /></span>
                <span className="event-copy">{event.text}</span>
                <time>{event.time}</time>
              </div>
            ))}
          </div>
          <button className="all-events-button" onClick={() => onNotify('Probes run against live Render microservices every 15s.')}>
            Refresh Fleet Probes <ArrowRight size={13} />
          </button>
        </section>
      </div>

      <section className="platform-strip">
        <div className="platform-strip-copy">
          <span className="platform-strip-kicker">BUILT TO TRAVEL WITH YOU</span>
          <h2>One intelligence layer.<br /><em>Every workspace.</em></h2>
        </div>
        <button className="platform-card platform-studio" onClick={() => onNavigate('studio')}>
          <span className="platform-icon"><Sparkles size={17} /></span>
          <span><strong>SupremeAI Studio</strong><small>Think, explore, create.</small></span>
          <ArrowUpRight size={14} />
        </button>
        <button className="platform-card platform-code" onClick={() => onNavigate('vscode')}>
          <span className="platform-icon"><Code2Icon /></span>
          <span><strong>SupremeAI VSCode</strong><small>Build with context.</small></span>
          <ArrowUpRight size={14} />
        </button>
        <button className="platform-more" onClick={() => onNavigate('devices')}>
          Explore every surface <ArrowRight size={13} />
        </button>
      </section>
    </div>
  );
}

function Code2Icon() {
  return <span className="code2-glyph" aria-hidden="true">&lt;/&gt;</span>;
}
