import React, { useRef } from 'react';
import { motion } from 'framer-motion';
import type { BrowserController } from './useBrowserController';
import { DEVICE_SPECS } from './useBrowserController';

export interface BrowserViewportProps {
  controller?: BrowserController;
  device?: string;
  orientation?: 'portrait' | 'landscape';
  url?: string;
  src?: string;
  effectiveUrl?: string;
  viewportHeight?: number;
  keyboardVisible?: boolean;
  inspectMode?: boolean;
  onElementInspect?: (meta: { selector: string; tag: string; text: string }) => void;
  isLoading?: boolean;
  onLoad?: () => void;
  onError?: () => void;
}

export const BrowserViewport: React.FC<BrowserViewportProps> = (props) => {
  const c = props.controller;
  const device = (c ? c.state.device : (props.device ?? 'desktop')) as keyof typeof DEVICE_SPECS;
  const orientation = c ? c.state.orientation : (props.orientation ?? 'portrait');
  const url = c ? c.state.url : (props.url ?? props.src ?? '');
  const effectiveUrl = c ? c.effectiveUrl : (props.effectiveUrl ?? props.src ?? url);
  const viewportHeight = c ? c.viewportHeight : (props.viewportHeight ?? 800);
  const keyboardVisible = c ? c.state.keyboardVisible : (props.keyboardVisible ?? false);
  const inspectMode = c ? c.state.inspectMode : (props.inspectMode ?? false);
  const isLoading = c ? c.state.isLoading : (props.isLoading ?? false);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const spec = DEVICE_SPECS[device] ?? DEVICE_SPECS.desktop;
  const portrait = orientation === 'portrait';
  const width = device === 'desktop' ? '100%' : `${portrait ? spec.width : spec.height}px`;
  const height = device === 'desktop' ? '100%' : `${viewportHeight}px`;

  const isMobile = device !== 'desktop';

  return (
    <div className="flex-1 flex flex-col bg-[#0d1117] relative overflow-hidden">
      {isLoading && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 bg-[#161b22] px-3 py-1 rounded-full flex items-center gap-2 shadow-lg">
          <span className="w-3 h-3 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs text-slate-300">Loading...</span>
        </div>
      )}

      <div className={`flex-1 flex ${isMobile ? 'justify-center items-start bg-[#1c2128] p-4' : ''} overflow-auto`}>
        <motion.div
          layout
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          style={{ width, height, maxWidth: '100%' }}
          className={`${isMobile ? 'bg-white rounded-[2.5rem] shadow-2xl overflow-hidden relative border-8 border-black' : 'h-full w-full relative'}`}
        >
          {isMobile && spec.hasDynamicIsland && (
            <div className="absolute top-2 left-1/2 -translate-x-1/2 w-28 h-7 bg-black rounded-full z-20" />
          )}
          <iframe
            ref={iframeRef}
            src={effectiveUrl || 'about:blank'}
            className="w-full h-full border-0 bg-white"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-presentation"
            onLoad={() => { if (c) c.setLoading(false); props.onLoad?.(); }}
            onError={() => { if (c) c.setError('Failed to load'); props.onError?.(); }}
            title="SupremeAI Browser"
          />
          {inspectMode && (
            <div
              className="absolute inset-0 z-30 cursor-crosshair"
              onClick={(_e) => {
                const meta = { selector: 'body', tag: 'div', text: '' };
                props.onElementInspect?.(meta);
                if (c) c.setInspectMode(false);
              }}
            >
              <div className="absolute top-2 left-2 bg-cyan-500 text-black text-xs px-2 py-1 rounded">Inspect mode: click an element</div>
            </div>
          )}
          {keyboardVisible && isMobile && (
            <div className="absolute bottom-0 left-0 right-0 h-[260px] bg-[#222] border-t border-slate-600 flex items-center justify-center text-slate-400 text-xs z-20">
              Simulated mobile keyboard
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
};

export default BrowserViewport;