import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowUpRight, Code2, Monitor, MonitorSmartphone, Smartphone, Sparkles } from 'lucide-react';
import type { DeviceKey, ViewKey } from '../types';

type DeviceLabProps = { onNavigate: (view: ViewKey) => void };

const surfaces: { id: DeviceKey; title: string; subtitle: string; icon: typeof Monitor }[] = [
  { id: 'web', title: 'Studio web', subtitle: 'Think, explore, create', icon: Monitor },
  { id: 'mobile', title: 'Mobile companion', subtitle: 'Carry the signal', icon: Smartphone },
  { id: 'desktop', title: 'VSCode desktop', subtitle: 'Build with context', icon: Code2 },
];

export function DeviceLab({ onNavigate }: DeviceLabProps) {
  const [selected, setSelected] = useState<DeviceKey>('web');
  const surface = surfaces.find((item) => item.id === selected)!;
  const Icon = surface.icon;

  return (
    <div className="device-lab-view">
      <section className="page-intro device-intro"><div className="intro-copy"><div className="eyebrow"><span className="eyebrow-mark" /> DESIGN SYSTEM <span className="eyebrow-divider">·</span> <span className="eyebrow-muted">ONE SIGNAL, MANY SCREENS</span></div><h1>Fits your flow.<br /><em>On any screen.</em></h1><p>Explore how one SupremeAI language adapts to the web, mobile, and developer desktop.</p></div><div className="device-intro-icon"><MonitorSmartphone size={25} /><span>RESPONSIVE BY DESIGN</span></div></section>

      <div className="device-lab-layout">
        <section className="device-selector-panel panel"><div className="panel-kicker">CHOOSE A SURFACE</div><h2>Same intelligence.<br /><em>Different rhythm.</em></h2><p>Each surface gets its own pace and shape, while the SupremeAI signal stays familiar.</p>
          <div className="surface-list" role="group" aria-label="Choose a device preview">
            {surfaces.map((item, index) => { const SurfaceIcon = item.icon; return <button aria-pressed={selected === item.id} type="button" className={`surface-option ${selected === item.id ? 'surface-selected' : ''}`} key={item.id} onClick={() => setSelected(item.id)}><span className="surface-option-icon"><SurfaceIcon size={16} /></span><span><strong>{item.title}</strong><small>{item.subtitle}</small></span><kbd>{index + 1}</kbd></button>; })}
          </div>
          <div className="device-system-note"><span className="device-note-icon"><Sparkles size={14} /></span><span><strong>One design system</strong><small>Shared tone, adaptive layouts, clear intent.</small></span></div>
        </section>

        <motion.section className={`device-preview-stage preview-${selected}`} key={selected} initial={{ opacity: 0, scale: .985 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: .2 }} aria-label={`${surface.title} preview`} aria-live="polite">
          <div className="device-stage-top"><span className="device-stage-label"><i /> DEVICE PREVIEW</span><span className="device-stage-dimensions">{selected === 'mobile' ? '390 × 844' : selected === 'desktop' ? '1440 × 900' : '1280 × 800'}</span></div>
          <div className={`device-frame device-frame-${selected}`}>
            {selected === 'mobile' ? <MobileMockup /> : selected === 'desktop' ? <DesktopMockup /> : <WebMockup />}
          </div>
          <div className="device-stage-footer"><div><span className="device-stage-icon"><Icon size={14} /></span><span><strong>{surface.title}</strong><small>{surface.subtitle}</small></span></div><button onClick={() => onNavigate(selected === 'desktop' ? 'vscode' : 'studio')}>Open experience <ArrowUpRight size={13} /></button></div>
        </motion.section>
      </div>
      <div className="device-footnote"><span className="device-footnote-dot" /> This is a visual concept built in one React preview. The native mobile and desktop clients remain in their own repositories.</div>
    </div>
  );
}

function WebMockup() {
  return <div className="mock-web"><div className="mock-web-sidebar"><div className="mock-logo"><span>◉</span> SupremeAI</div><div className="mock-nav active">◈ <span>Overview</span></div><div className="mock-nav">✳ <span>Studio</span></div><div className="mock-nav">&lt;/&gt; <span>VSCode</span></div><div className="mock-web-user">SA <span>Workspace</span></div></div><div className="mock-web-content"><div className="mock-topline"><span>SUPREMEAI / COMMAND</span><i>DEMO FEED</i></div><div className="mock-heading">One signal.<br /><em>Everywhere.</em></div><div className="mock-subheading">Keep intent at the center of every move.</div><div className="mock-cards"><div><small>ACTIVE AGENTS</small><strong>08</strong><span><i /> 2 online</span></div><div><small>FEDERATION HEALTH</small><strong>99.98%</strong><span>Sample availability</span></div><div><small>THROUGHPUT</small><strong>1.28k</strong><span>Illustrative tokens / sec</span></div></div><div className="mock-chart"><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><i /></div><div className="mock-table"><span>ACTIVE WORKFLOWS</span><i>03</i><div>Research Scout <small>Mapping model landscape</small><b>WORKING</b></div><div>Code Pilot <small>Reviewing Studio routes</small><b>READY</b></div></div></div></div>;
}

function MobileMockup() {
  return <div className="mock-phone"><div className="phone-island" /><div className="phone-top"><span>9:41</span><span>● ● ▰</span></div><div className="phone-brand"><span className="phone-mark">◉</span><strong>SUPREME<span>AI</span></strong><span className="phone-avatar">S</span></div><div className="phone-greeting"><small>YOUR SIGNAL, IN MOTION</small><h3>Good evening,<br /><em>Alex.</em></h3><p>What would you like to move forward?</p></div><div className="phone-prompt"><span>✳</span><p>Ask SupremeAI anything…</p><i>↑</i></div><div className="phone-chip-row"><span>Write</span><span>Explore</span><span>Create</span></div><div className="phone-section-head"><strong>Pick up where you left off</strong><small>SEE ALL</small></div><div className="phone-project"><span className="phone-project-icon">◈</span><span><strong>Launch story</strong><small>Studio · 4 notes</small></span><i>→</i></div><div className="phone-project"><span className="phone-project-icon phone-violet">⌘</span><span><strong>Code review</strong><small>VSCode · just now</small></span><i>→</i></div><div className="phone-bottom-nav"><span className="phone-nav-active">⌂<small>Home</small></span><span>✳<small>Studio</small></span><span>&lt;/&gt;<small>VSCode</small></span><span>◯<small>Profile</small></span></div></div>;
}

function DesktopMockup() {
  return <div className="mock-desktop"><div className="mock-desktop-sidebar"><div className="mock-logo"><span>◉</span> SupremeAI</div><small>WORKSPACE</small><div className="desktop-nav-selected">✳ <span>New chat</span></div><div className="desktop-nav">⌕ <span>Search chats</span></div><div className="desktop-nav">▧ <span>Projects</span></div><div className="desktop-recent"><small>RECENT</small><span>Signal handoff</span><span>Studio routes</span><span>Launch story</span></div><div className="mock-profile">SA <span>SupremeAI Team</span></div></div><div className="mock-editor"><div className="mock-editor-top"><span>SupremeAI / Studio Workspace</span><i>DESKTOP CONCEPT</i></div><div className="mock-editor-content"><div className="mock-editor-title"><small>CONTEXT COMPANION</small><h3>Let’s build<br /><em>what’s next.</em></h3><p>One workspace for ideas, research, and things worth building.</p></div><div className="mock-chat-bubble">Help me turn this idea into a clear product launch plan.</div><div className="mock-answer"><span className="mock-ai-mark">✳</span><div><small>SUPREMEAI · REASONING PRO</small><p>Let’s start with the audience, then identify the one promise they should remember.</p></div></div><div className="mock-input"><span>Ask SupremeAI anything…</span><i>↑</i></div><small className="mock-editor-note">Local preview · no request sent</small></div></div></div>;
}
