import React, { useState } from 'react';
import { ArrowLeft, ArrowRight, RotateCw, Home, Search, Smartphone, Monitor, Target, Keyboard, RotateCcw, QrCode } from 'lucide-react';
import type { BrowserController, DeviceProfile } from './useBrowserController';

export interface SmartOmniboxProps {
  controller?: BrowserController;
  url?: string;
  inputUrl?: string;
  onNavigate?: (raw: string) => void;
  onInputChange?: (v: string) => void;
  onBack?: () => void;
  onForward?: () => void;
  onReload?: () => void;
  onHome?: () => void;
  viewMode?: 'desktop' | 'mobile';
  device?: DeviceProfile;
  onToggleViewMode?: () => void;
  onSetDevice?: (d: DeviceProfile) => void;
  inspectMode?: boolean;
  onToggleInspect?: () => void;
  keyboardVisible?: boolean;
  onToggleKeyboard?: () => void;
  orientation?: 'portrait' | 'landscape';
  onToggleOrientation?: () => void;
  onShowQr?: () => void;
}

export const SmartOmnibox: React.FC<SmartOmniboxProps> = (props) => {
  const c = props.controller;
  const url = c ? c.state.url : (props.url ?? '');
  const inputUrl = c ? c.state.inputUrl : (props.inputUrl ?? url);
  const viewMode = c ? c.state.viewMode : (props.viewMode ?? 'desktop');
  const device = c ? c.state.device : (props.device ?? 'desktop');
  const inspectMode = c ? c.state.inspectMode : (props.inspectMode ?? false);
  const keyboardVisible = c ? c.state.keyboardVisible : (props.keyboardVisible ?? false);

  const [local, setLocal] = useState(inputUrl);
  React.useEffect(() => setLocal(inputUrl), [inputUrl]);

  const navigate = (raw: string) => {
    if (c) c.navigate(raw); else props.onNavigate?.(raw);
  };
  const back = () => { if (c) c.goBack(); else props.onBack?.(); };
  const fwd = () => { if (c) c.goForward(); else props.onForward?.(); };
  const reload = () => { if (c) c.reload(); else props.onReload?.(); };
  const home = () => { if (c) c.home(); else props.onHome?.(); };
  const toggleView = () => { if (c) c.toggleViewMode(); else props.onToggleViewMode?.(); };
  const setDevice = (d: DeviceProfile) => { if (c) c.setDevice(d); else props.onSetDevice?.(d); };
  const toggleInspect = () => { if (c) c.toggleInspect(); else props.onToggleInspect?.(); };
  const toggleKb = () => { if (c) c.toggleKeyboard(); else props.onToggleKeyboard?.(); };
  const toggleOrient = () => { if (c) c.toggleOrientation(); else props.onToggleOrientation?.(); };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate(local);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-[#161b22] border-b border-slate-700">
      <button onClick={back} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="Back" aria-label="back">
        <ArrowLeft size={16} />
      </button>
      <button onClick={fwd} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="Forward" aria-label="forward">
        <ArrowRight size={16} />
      </button>
      <button onClick={reload} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="Reload" aria-label="reload">
        <RotateCw size={16} />
      </button>
      <button onClick={home} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="Home" aria-label="home">
        <Home size={16} />
      </button>

      <form onSubmit={onSubmit} className="flex-1 flex items-center">
        <div className="flex-1 flex items-center bg-[#0d1117] border border-slate-600 rounded-lg px-3 py-1.5">
          <Search size={14} className="text-slate-500 mr-2" />
          <input
            value={local}
            onChange={(e) => { setLocal(e.target.value); props.onInputChange?.(e.target.value); if (c) c.setInputUrl(e.target.value); }}
            className="flex-1 bg-transparent outline-none text-sm text-slate-200"
            placeholder="Enter URL or search..."
            aria-label="url-input"
          />
        </div>
      </form>

      <select
        value={device}
        onChange={(e) => setDevice(e.target.value as DeviceProfile)}
        className="bg-[#0d1117] border border-slate-600 text-slate-200 text-xs rounded px-2 py-1.5"
        aria-label="device-select"
      >
        <option value="desktop">Desktop</option>
        <option value="iphone16pro">iPhone 16 Pro</option>
        <option value="galaxy-s24">Galaxy S24</option>
        <option value="ipad">iPad</option>
      </select>

      <button onClick={toggleView} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="Toggle view" aria-label="toggle-view">
        {viewMode === 'desktop' ? <Smartphone size={16} /> : <Monitor size={16} />}
      </button>
      <button onClick={toggleInspect} className={`p-1.5 rounded hover:bg-slate-700 ${inspectMode ? 'text-cyan-400' : 'text-slate-300'}`} title="Inspect" aria-label="inspect">
        <Target size={16} />
      </button>
      <button onClick={toggleKb} className={`p-1.5 rounded hover:bg-slate-700 ${keyboardVisible ? 'text-cyan-400' : 'text-slate-300'}`} title="Keyboard" aria-label="keyboard">
        <Keyboard size={16} />
      </button>
      <button onClick={toggleOrient} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="Rotate" aria-label="rotate">
        <RotateCcw size={16} />
      </button>
      <button onClick={() => (props.onShowQr ? props.onShowQr() : null)} className="p-1.5 rounded hover:bg-slate-700 text-slate-300" title="QR" aria-label="qr">
        <QrCode size={16} />
      </button>
    </div>
  );
};

export default SmartOmnibox;