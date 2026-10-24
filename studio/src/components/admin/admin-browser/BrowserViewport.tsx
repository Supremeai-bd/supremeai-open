import React, { type Dispatch, type SetStateAction } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, X, AlertTriangle } from 'lucide-react';

import type { RefObject } from 'react';
import type { BrowserTab, DeviceMode, SecurityScanResult } from './types';

// ════════════════════════════════════════════════════════════════════
// BROWSER VIEWPORT (device frame + iframe + overlays)
// Extracted verbatim from the CrownJewelBrowser render tree.
// ════════════════════════════════════════════════════════════════════

interface BrowserViewportProps {
  isLoading: boolean;
  deviceMode: DeviceMode;
  zoomLevel: number;
  activeTab?: BrowserTab;
  iframeRef: RefObject<HTMLIFrameElement | null>;
  handleIframeLoad: () => void;
  handleIframeError: () => void;
  refresh: () => void;
  securityScanResult: SecurityScanResult | null;
  setSecurityScanResult: Dispatch<SetStateAction<SecurityScanResult | null>>;
}

export const BrowserViewport: React.FC<BrowserViewportProps> = ({
  isLoading,
  deviceMode,
  zoomLevel,
  activeTab,
  iframeRef,
  handleIframeLoad,
  handleIframeError,
  refresh,
  securityScanResult,
  setSecurityScanResult,
}) => {
  const deviceWidths = {
    desktop: '100%',
    tablet: '768px',
    mobile: '375px',
  };

  return (
    <div className="flex-1 flex flex-col bg-[#0d1117] relative">

      {/* Loading Indicator */}
      <AnimatePresence>
        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute top-2 left-1/2 transform -translate-x-1/2 z-10 bg-[#161b22] px-3 py-1 rounded-full flex items-center gap-2 shadow-lg"
          >
            <Loader2 size={12} className="animate-spin text-cyan-400" />
            <span className="text-xs text-slate-300">Loading...</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Device Mode Frame */}
      <div className={`flex-1 flex ${deviceMode !== 'desktop' ? 'justify-center bg-[#1c2128] p-4' : ''}`}>
        <div
          style={{ width: deviceWidths[deviceMode], maxWidth: '100%' }}
          className={`${deviceMode !== 'desktop' ? 'bg-white rounded-lg shadow-2xl overflow-hidden h-full' : 'h-full'} relative`}
        >
          {/* Mobile Device Frame (Tablet/Mobile mode) */}
          {deviceMode !== 'desktop' && (
            <div className="absolute top-0 left-0 right-0 h-6 bg-black flex items-center justify-center">
              <div className="w-16 h-4 bg-gray-800 rounded-full" />
            </div>
          )}

          <iframe
            ref={iframeRef}
            src={activeTab?.url}
            className="w-full h-full border-0 bg-white"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-presentation"
            onLoad={handleIframeLoad}
            onError={handleIframeError}
            title="SupremeAI Browser"
            style={{
              transform: `scale(${zoomLevel / 100})`,
              transformOrigin: 'top left',
            }}
          />
        </div>
      </div>

      {/* Error Overlay */}
      {activeTab?.error && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#0d1117]/90 backdrop-blur-sm">
          <div className="text-center p-6">
            <AlertTriangle size={48} className="mx-auto text-red-400 mb-4" />
            <h3 className="text-lg font-bold text-white mb-2">Failed to Load Page</h3>
            <p className="text-sm text-slate-400 mb-4">{activeTab.error}</p>
            <button
              onClick={refresh}
              className="px-4 py-2 bg-cyan-500 text-black font-bold rounded-lg hover:bg-cyan-400 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      )}

      {/* Security Scan Result Overlay */}
      <AnimatePresence>
        {securityScanResult && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute top-4 right-4 bg-[#161b22] border border-green-500/30 rounded-lg p-4 max-w-xs shadow-xl"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-green-400">Security Score</span>
              <button onClick={() => setSecurityScanResult(null)}>
                <X size={12} className="text-slate-400" />
              </button>
            </div>
            <div className="text-2xl font-bold text-white mb-2">{securityScanResult.score}/100</div>
            <div className="space-y-1">
              {securityScanResult.issues.map((issue, i) => (
                <div key={i} className="text-[10px] text-slate-300">{issue}</div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
