import React, { useMemo, useState } from 'react';
import { ExternalLink, Maximize2, RefreshCw, RotateCcw, Smartphone, Tablet, ZoomIn, ZoomOut } from 'lucide-react';

type Orientation = 'portrait' | 'landscape';
type DeviceId = 'iphone' | 'pixel' | 'ipad';

interface DevicePreset {
  id: DeviceId;
  name: string;
  width: number;
  height: number;
  icon: React.ReactNode;
  frame: 'phone' | 'tablet';
}

const DEVICES: DevicePreset[] = [
  { id: 'iphone', name: 'iPhone 15', width: 390, height: 844, icon: <Smartphone size={14} />, frame: 'phone' },
  { id: 'pixel', name: 'Pixel 8', width: 412, height: 915, icon: <Smartphone size={14} />, frame: 'phone' },
  { id: 'ipad', name: 'iPad Pro', width: 1024, height: 1366, icon: <Tablet size={14} />, frame: 'tablet' },
];

interface MobilePreviewPanelProps {
  html: string;
  title?: string;
}

/** Customer-facing generated-HTML preview; this is not a real phone. */
export function MobilePreviewPanel({ html, title = 'SupremeAI mobile preview' }: MobilePreviewPanelProps) {
  const [deviceId, setDeviceId] = useState<DeviceId>('iphone');
  const [orientation, setOrientation] = useState<Orientation>('portrait');
  const [zoom, setZoom] = useState(75);
  const [showChrome, setShowChrome] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const device = useMemo(() => DEVICES.find(item => item.id === deviceId) ?? DEVICES[0], [deviceId]);
  const viewport = useMemo(() => ({
    width: orientation === 'portrait' ? device.width : device.height,
    height: orientation === 'portrait' ? device.height : device.width,
  }), [device, orientation]);

  const openInNewTab = () => {
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const objectUrl = URL.createObjectURL(blob);
    const opened = window.open(objectUrl, '_blank', 'noopener,noreferrer');
    if (!opened) URL.revokeObjectURL(objectUrl);
    else window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  };

  return (
    <section className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950 text-slate-100" aria-label={title}>
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-slate-900/80 px-3 py-2">
        <div className="flex items-center gap-2">
          <Smartphone size={15} className="text-cyan-300" aria-hidden="true" />
          <span className="text-xs font-semibold tracking-wide">Mobile Preview</span>
          <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-300">PREVIEW ONLY</span>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setZoom(value => Math.max(50, value - 10))} className="min-h-9 min-w-9 rounded border border-white/10 text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200" aria-label="Zoom out" title="Zoom out"><ZoomOut size={14} className="mx-auto" /></button>
          <span className="min-w-12 text-center font-mono text-[10px] text-slate-400" aria-live="polite">{zoom}%</span>
          <button type="button" onClick={() => setZoom(value => Math.min(125, value + 10))} className="min-h-9 min-w-9 rounded border border-white/10 text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200" aria-label="Zoom in" title="Zoom in"><ZoomIn size={14} className="mx-auto" /></button>
          <button type="button" onClick={openInNewTab} className="ml-1 min-h-9 min-w-9 rounded border border-white/10 text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200" aria-label="Open preview in a new tab" title="Open in new tab"><ExternalLink size={14} className="mx-auto" /></button>
        </div>
      </header>

      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-white/10 bg-slate-950 px-3 py-2">
        {DEVICES.map(item => (
          <button key={item.id} type="button" onClick={() => setDeviceId(item.id)} aria-pressed={deviceId === item.id} className={`flex min-h-9 items-center gap-1.5 rounded border px-2.5 text-[11px] transition-colors ${deviceId === item.id ? 'border-cyan-400/60 bg-cyan-400/10 text-cyan-200' : 'border-white/10 text-slate-400 hover:border-white/25 hover:text-slate-200'}`}>
            {item.icon}{item.name}
          </button>
        ))}
        <button type="button" onClick={() => setOrientation(value => value === 'portrait' ? 'landscape' : 'portrait')} aria-pressed={orientation === 'landscape'} className="flex min-h-9 items-center gap-1.5 rounded border border-white/10 px-2.5 text-[11px] text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200" title="Rotate device">
          <RotateCcw size={13} /> {orientation === 'portrait' ? 'Portrait' : 'Landscape'}
        </button>
        <button type="button" onClick={() => setShowChrome(value => !value)} aria-pressed={showChrome} className="flex min-h-9 items-center gap-1.5 rounded border border-white/10 px-2.5 text-[11px] text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200" title="Toggle device chrome">
          <Maximize2 size={13} /> Chrome {showChrome ? 'on' : 'off'}
        </button>
        <button type="button" onClick={() => setReloadKey(value => value + 1)} className="ml-auto flex min-h-9 items-center gap-1.5 rounded border border-white/10 px-2.5 text-[11px] text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200" title="Reload preview">
          <RefreshCw size={13} /> Reload
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.12),transparent_45%)] p-4">
        <div className="flex min-h-full min-w-full items-start justify-center py-4">
          <div className={`relative shrink-0 overflow-hidden border-4 border-slate-700 bg-slate-950 shadow-2xl ring-1 ring-white/10 ${device.frame === 'phone' ? 'rounded-[38px]' : 'rounded-[26px]'}`} style={{ width: viewport.width, height: viewport.height, transform: `scale(${zoom / 100})`, transformOrigin: 'top center', marginBottom: `${viewport.height * (zoom / 100 - 1)}px` }}>
            {showChrome && <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex h-8 items-center justify-between px-5 pt-1 text-[10px] font-medium text-slate-400"><span>9:41</span><span>5G&nbsp; ◉</span></div>}
            {showChrome && device.frame === 'phone' && <div className="pointer-events-none absolute left-1/2 top-1.5 z-20 h-4 w-28 -translate-x-1/2 rounded-full bg-slate-800" aria-hidden="true" />}
            <iframe key={reloadKey} title={`${device.name} preview`} srcDoc={html} sandbox="allow-scripts allow-modals" className={`h-full w-full border-0 bg-white ${showChrome ? 'pt-8' : ''}`} />
            {showChrome && device.frame === 'phone' && <div className="pointer-events-none absolute bottom-1.5 left-1/2 z-20 h-1 w-24 -translate-x-1/2 rounded-full bg-slate-600" aria-hidden="true" />}
          </div>
        </div>
      </div>

      <footer className="flex shrink-0 items-center justify-between border-t border-white/10 bg-slate-900/70 px-3 py-2 text-[10px] text-slate-400">
        <span>{device.name} · {viewport.width} × {viewport.height} · {orientation}</span>
        <span className="font-mono text-emerald-300/80">sandboxed HTML</span>
      </footer>
    </section>
  );
}

export default MobilePreviewPanel;
