import React, { type Dispatch, type SetStateAction } from 'react';
import { Loader2, Check, Monitor, Smartphone, Tablet, ZoomIn, ZoomOut } from 'lucide-react';

import type { BrowserTab, DeviceMode, SecurityScanResult } from './types';

// ════════════════════════════════════════════════════════════════════
// STATUS BAR (bottom: URL/title, device mode, zoom, security badge)
// Extracted verbatim from the CrownJewelBrowser render tree.
// ════════════════════════════════════════════════════════════════════

interface StatusBarProps {
  isLoading: boolean;
  activeTab?: BrowserTab;
  deviceMode: DeviceMode;
  setDeviceMode: Dispatch<SetStateAction<DeviceMode>>;
  zoomLevel: number;
  setZoomLevel: Dispatch<SetStateAction<number>>;
  securityScanResult: SecurityScanResult | null;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  isLoading,
  activeTab,
  deviceMode,
  setDeviceMode,
  zoomLevel,
  setZoomLevel,
  securityScanResult,
}) => {
  return (
    <div className="bg-[#0d1117] border-t border-cyan-500/20 px-3 py-1 flex items-center justify-between text-[10px] text-slate-500">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1">
          {isLoading ? (
            <Loader2 size={8} className="animate-spin text-cyan-400" />
          ) : (
            <Check size={8} className="text-green-400" />
          )}
          {activeTab?.url || 'about:blank'}
        </span>
        <span>{activeTab?.title || 'Loading...'}</span>
      </div>
      <div className="flex items-center gap-4">
        {/* Device Mode Switcher */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setDeviceMode('desktop')}
            className={`p-1 rounded ${deviceMode === 'desktop' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
            title="Desktop"
          >
            <Monitor size={12} />
          </button>
          <button
            onClick={() => setDeviceMode('tablet')}
            className={`p-1 rounded ${deviceMode === 'tablet' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
            title="Tablet"
          >
            <Tablet size={12} />
          </button>
          <button
            onClick={() => setDeviceMode('mobile')}
            className={`p-1 rounded ${deviceMode === 'mobile' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
            title="Mobile"
          >
            <Smartphone size={12} />
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1">
          <button onClick={() => setZoomLevel(z => Math.max(25, z - 25))} className="p-1 hover:bg-slate-800 rounded">
            <ZoomOut size={10} />
          </button>
          <span className="w-10 text-center">{zoomLevel}%</span>
          <button onClick={() => setZoomLevel(z => Math.min(200, z + 25))} className="p-1 hover:bg-slate-800 rounded">
            <ZoomIn size={10} />
          </button>
        </div>

        {/* Security Score Badge */}
        {securityScanResult && (
          <span className={`px-2 py-0.5 rounded ${
            securityScanResult.score >= 80 ? 'bg-green-900/30 text-green-400' :
            securityScanResult.score >= 60 ? 'bg-yellow-900/30 text-yellow-400' :
            'bg-red-900/30 text-red-400'
          }`}>
            Sec: {securityScanResult.score}
          </span>
        )}
      </div>
    </div>
  );
};
