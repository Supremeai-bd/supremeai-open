import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, ChevronDown, CircleHelp, Clock3, Command, Search, ShieldCheck } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Overview } from './views/Overview';
import { StudioView } from './views/StudioView';
import { VSCodeView } from './views/VSCodeView';
import { DeviceLab } from './views/DeviceLab';
import type { ViewKey } from './types';

const viewTitle: Record<ViewKey, string> = {
  overview: 'Command room',
  studio: 'Studio workspace',
  vscode: 'VSCode companion',
  devices: 'Cross-platform lab',
};

const commandOptions: { view: ViewKey; icon: string; description: string; shortcut: string }[] = [
  { view: 'overview', icon: '◈', description: 'Federation signals and active agents', shortcut: '1' },
  { view: 'studio', icon: '✳', description: 'AI creation workspace', shortcut: '2' },
  { view: 'vscode', icon: '</>', description: 'Developer companion and code review', shortcut: '3' },
  { view: 'devices', icon: '▣', description: 'Web, mobile and desktop previews', shortcut: '4' },
];

function currentTime() {
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date());
}

export default function App() {
  const [active, setActive] = useState<ViewKey>('overview');
  const [clock, setClock] = useState(currentTime);
  const [toast, setToast] = useState('');
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState('');
  const commandInputRef = useRef<HTMLInputElement>(null);
  const commandOpenerRef = useRef<HTMLElement | null>(null);

  const openCommand = useCallback(() => {
    commandOpenerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCommandQuery('');
    setCommandOpen(true);
  }, []);

  const closeCommand = useCallback(() => {
    setCommandOpen(false);
    window.requestAnimationFrame(() => commandOpenerRef.current?.focus());
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(currentTime()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (commandOpen) window.requestAnimationFrame(() => commandInputRef.current?.focus());
  }, [commandOpen]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      const isTyping = target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
      if (event.key === 'Escape' && commandOpen) {
        event.preventDefault();
        closeCommand();
        return;
      }
      if (commandOpen) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !isTyping) {
        event.preventDefault();
        openCommand();
        return;
      }
      if (!isTyping && /^[1-4]$/.test(event.key)) {
        const views: ViewKey[] = ['overview', 'studio', 'vscode', 'devices'];
        setActive(views[Number(event.key) - 1]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, closeCommand, commandOpen, openCommand]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 3000);
  };

  const renderView = () => {
    if (active === 'studio') return <StudioView onNotify={notify} />;
    if (active === 'vscode') return <VSCodeView onNotify={notify} />;
    if (active === 'devices') return <DeviceLab onNavigate={setActive} />;
    return <Overview onNavigate={setActive} onNotify={notify} />;
  };

  const filteredCommands = commandOptions.filter(({ view, description }) => `${viewTitle[view]} ${description}`.toLowerCase().includes(commandQuery.toLowerCase()));

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <div className="ambient ambient-a" aria-hidden="true" />
      <div className="ambient ambient-b" aria-hidden="true" />
      <Sidebar active={active} onNavigate={setActive} onOpenCommand={openCommand} />
      <div className="main-column">
        <header className="topbar">
          <div className="topbar-title"><span className="topbar-mobile-mark">🔱</span><span className="crumb-root">SupremeAI</span><span className="crumb-divider">/</span><strong>{viewTitle[active]}</strong></div>
          <div className="topbar-actions">
            <button className="search-shortcut" type="button" onClick={openCommand} aria-label="Open command menu" aria-haspopup="dialog" aria-expanded={commandOpen}>
              <Search size={15} /><span>Search anything</span><kbd><Command size={11} /> K</kbd>
            </button>
            <span className="topbar-separator" />
            <div className="clock-display"><Clock3 size={14} /><span>{clock}</span><span className="utc-label">LOCAL</span></div>
            <button className="icon-action notification-button" type="button" aria-label="Notifications" onClick={() => notify('You are viewing sample product alerts.') }><Bell size={17} /><i /></button>
            <button className="user-menu" type="button" aria-label="SupremeAI preview profile"><span>SA</span><ChevronDown size={13} /></button>
          </div>
        </header>
        <div className="demo-ribbon" role="status">
          <span className="demo-ribbon-icon"><ShieldCheck size={13} /></span>
          <span><strong>DESIGN PREVIEW</strong><i> · </i> Animated UI with sample telemetry; not connected to live Tower data.</span>
          <span className="demo-clock"><span className="pulse-dot" /> SIMULATION RUNNING</span>
        </div>
        <main className="page-content" id="main-content" tabIndex={-1}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.section key={active} className="view-container" initial={{ opacity: 0, y: 9, filter: 'blur(4px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} exit={{ opacity: 0, y: -7, filter: 'blur(3px)' }} transition={{ duration: 0.24, ease: 'easeOut' }}>
              {renderView()}
            </motion.section>
          </AnimatePresence>
        </main>
        <footer className="footer-line"><span>SUPREMEAI · CROSS-PLATFORM CONCEPT</span><span><CircleHelp size={12} /> Prototype data is illustrative</span></footer>
      </div>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {(['overview', 'studio', 'vscode', 'devices'] as ViewKey[]).map((view, index) => {
          const icons = ['⌂', '✳', '</>', '▣'];
          return <button key={view} type="button" className={active === view ? 'active' : ''} onClick={() => setActive(view)} aria-current={active === view ? 'page' : undefined} aria-keyshortcuts={String(index + 1)}><span>{icons[index]}</span><small>{view === 'overview' ? 'Home' : view === 'vscode' ? 'VSCode' : view === 'devices' ? 'Devices' : 'Studio'}</small></button>;
        })}
      </nav>
      <AnimatePresence>
        {toast && <motion.div className="toast" role="status" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}><span className="toast-check">✓</span>{toast}</motion.div>}
      </AnimatePresence>
      <AnimatePresence>
        {commandOpen && <motion.div className="command-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) closeCommand(); }}>
          <motion.div className="command-panel" role="dialog" aria-modal="true" aria-labelledby="quick-navigation-title" onKeyDown={(event) => {
            if (event.key !== 'Tab') return;
            const focusable = event.currentTarget.querySelectorAll<HTMLElement>('input:not(:disabled), button:not(:disabled)');
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (!first || !last) return;
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
          }} initial={{ opacity: 0, y: -10, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: .98 }}>
            <h2 id="quick-navigation-title" className="sr-only">Quick navigation</h2>
            <div className="command-search"><Search size={17} /><label className="sr-only" htmlFor="command-query">Search workspaces</label><input ref={commandInputRef} id="command-query" value={commandQuery} onChange={(event) => setCommandQuery(event.target.value)} placeholder="Jump to a workspace…" /><kbd>ESC</kbd></div>
            {filteredCommands.length ? filteredCommands.map(({ view, icon, description, shortcut }) => <button key={view} type="button" className="command-item" aria-keyshortcuts={shortcut} onClick={() => { setActive(view); closeCommand(); }}><span className="command-item-icon">{icon}</span><span><strong>{viewTitle[view]}</strong><small>{description}</small></span><kbd>{shortcut}</kbd></button>) : <p className="command-empty">No destinations match “{commandQuery}”.</p>}
          </motion.div>
        </motion.div>}
      </AnimatePresence>
    </div>
  );
}
