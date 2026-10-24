import React, { type Dispatch, type SetStateAction } from 'react';
import {
  Globe, ArrowLeft, ArrowRight, RotateCw, Plus, X, Star, Camera,
  Clock, ExternalLink, Lock,
  Shield, Loader2, Code,
  Bot, Copy,
} from 'lucide-react';

import type { BrowserTab } from './types';

// ════════════════════════════════════════════════════════════════════
// BROWSER TOOLBAR (Row 1: navigation/URL/actions, Row 2: tab bar)
// Extracted verbatim from the CrownJewelBrowser render tree.
// ════════════════════════════════════════════════════════════════════

interface BrowserToolbarProps {
  goBack: () => void;
  canGoBack: boolean;
  goForward: () => void;
  canGoForward: boolean;
  refresh: () => void;
  isLoading: boolean;
  showHistory: boolean;
  setShowHistory: Dispatch<SetStateAction<boolean>>;
  urlInputValue: string;
  setUrlInputValue: Dispatch<SetStateAction<string>>;
  navigateTo: (url: string) => void;
  activeTab?: BrowserTab;
  copyUrl: () => void;
  showBookmarks: boolean;
  setShowBookmarks: Dispatch<SetStateAction<boolean>>;
  toggleBookmark: () => void;
  takeScreenshot: () => void;
  runSecurityScan: () => void;
  showDevToolsPanel: boolean;
  setShowDevToolsPanel: Dispatch<SetStateAction<boolean>>;
  showAIPanel: boolean;
  setShowAIPanel: Dispatch<SetStateAction<boolean>>;
  tabs: BrowserTab[];
  activeTabId: string;
  setActiveTabId: Dispatch<SetStateAction<string>>;
  closeTab: (tabId: string) => void;
  createNewTab: () => void;
}

export const BrowserToolbar: React.FC<BrowserToolbarProps> = ({
  goBack,
  canGoBack,
  goForward,
  canGoForward,
  refresh,
  isLoading,
  showHistory,
  setShowHistory,
  urlInputValue,
  setUrlInputValue,
  navigateTo,
  activeTab,
  copyUrl,
  showBookmarks,
  setShowBookmarks,
  toggleBookmark,
  takeScreenshot,
  runSecurityScan,
  showDevToolsPanel,
  setShowDevToolsPanel,
  showAIPanel,
  setShowAIPanel,
  tabs,
  activeTabId,
  setActiveTabId,
  closeTab,
  createNewTab,
}) => {
  return (
    <div className="bg-[#0d1117] border-b border-cyan-500/20 px-3 py-2">

      {/* Row 1: Navigation & Tabs */}
      <div className="flex items-center gap-2 mb-2">

        {/* Navigation Controls */}
        <div className="flex items-center gap-1 bg-[#161b22] rounded-lg p-1">
          <button
            onClick={goBack}
            disabled={!canGoBack}
            className="p-1.5 hover:bg-cyan-500/10 disabled:opacity-30 disabled:cursor-not-allowed rounded transition-colors"
            title="Back"
          >
            <ArrowLeft size={14} className="text-slate-300" />
          </button>
          <button
            onClick={goForward}
            disabled={!canGoForward}
            className="p-1.5 hover:bg-cyan-500/10 disabled:opacity-30 disabled:cursor-not-allowed rounded transition-colors"
            title="Forward"
          >
            <ArrowRight size={14} className="text-slate-300" />
          </button>
          <button
            onClick={refresh}
            className={`p-1.5 hover:bg-cyan-500/10 rounded transition-colors ${isLoading ? 'animate-spin' : ''}`}
            title="Refresh"
          >
            <RotateCw size={14} className="text-slate-300" />
          </button>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="p-1.5 hover:bg-cyan-500/10 rounded transition-colors"
            title="History"
          >
            <Clock size={14} className="text-slate-300" />
          </button>
        </div>

        {/* URL Bar */}
        <div className="flex-1 flex items-center bg-[#161b22] rounded-lg px-3 py-1.5 group focus-within:ring-2 focus-within:ring-cyan-500/30">
          <Lock size={12} className="text-green-400 mr-2 flex-shrink-0" />
          <input
            type="text"
            value={urlInputValue}
            onChange={(e) => setUrlInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') navigateTo(urlInputValue);
              if (e.key === 'Escape') setUrlInputValue(activeTab?.url || '');
            }}
            placeholder="Enter URL or search..."
            className="flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500 font-mono"
          />
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={copyUrl} className="p-1 hover:bg-slate-700 rounded" title="Copy URL">
              <Copy size={12} className="text-slate-400" />
            </button>
            <button onClick={() => navigateTo(urlInputValue)} className="p-1 hover:bg-slate-700 rounded" title="Go">
              <ExternalLink size={12} className="text-slate-400" />
            </button>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1">
          {/* Bookmarks Toggle */}
          <button
            onClick={() => setShowBookmarks(!showBookmarks)}
            className={`p-1.5 rounded transition-colors ${showBookmarks ? 'bg-yellow-500/20 text-yellow-400' : 'hover:bg-slate-700 text-slate-400'}`}
            title="Bookmarks"
          >
            <Star size={14} fill={showBookmarks ? 'currentColor' : 'none'} />
          </button>

          {/* Bookmark Current Tab */}
          <button
            onClick={() => toggleBookmark()}
            className={`p-1.5 rounded transition-colors ${activeTab?.bookmarked ? 'bg-yellow-500/20 text-yellow-400' : 'hover:bg-slate-700 text-slate-400'}`}
            title="Bookmark this page"
          >
            <Star size={14} fill={activeTab?.bookmarked ? 'currentColor' : 'none'} />
          </button>

          {/* Screenshot */}
          <button
            onClick={takeScreenshot}
            className="p-1.5 hover:bg-slate-700 text-slate-400 rounded transition-colors"
            title="Take Screenshot"
          >
            <Camera size={14} />
          </button>

          {/* Security Scan */}
          <button
            onClick={runSecurityScan}
            className="p-1.5 hover:bg-slate-700 text-slate-400 rounded transition-colors"
            title="Run Security Scan"
          >
            <Shield size={14} />
          </button>

          {/* Dev Tools Toggle */}
          <button
            onClick={() => setShowDevToolsPanel(!showDevToolsPanel)}
            className={`p-1.5 rounded transition-colors ${showDevToolsPanel ? 'bg-purple-500/20 text-purple-400' : 'hover:bg-slate-700 text-slate-400'}`}
            title="Developer Tools"
          >
            <Code size={14} />
          </button>

          {/* AI Assistant Toggle */}
          <button
            onClick={() => setShowAIPanel(!showAIPanel)}
            className={`p-1.5 rounded-lg transition-all ${showAIPanel ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-cyan-400 shadow-lg shadow-cyan-500/10' : 'hover:bg-slate-700 text-slate-400'}`}
            title="AI Assistant"
          >
            <Bot size={14} className={showAIPanel ? 'animate-pulse' : ''} />
          </button>
        </div>
      </div>

      {/* Row 2: Tab Bar */}
      <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            onClick={() => setActiveTabId(tab.id)}
            className={`group flex items-center gap-2 px-3 py-1.5 rounded-t-lg cursor-pointer max-w-[180px] transition-all ${
              tab.id === activeTabId
                ? 'bg-[#1c2128] text-white border-t-2 border-t-cyan-400'
                : 'bg-[#161b22] text-slate-400 hover:bg-[#1c2128]/50 hover:text-slate-200'
            }`}
          >
            {tab.isLoading ? (
              <Loader2 size={10} className="animate-spin text-cyan-400 flex-shrink-0" />
            ) : (
              <Globe size={10} className="flex-shrink-0" />
            )}
            <span className="truncate text-xs font-medium">{tab.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
              className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-red-500/20 rounded transition-all"
            >
              <X size={10} />
            </button>
          </div>
        ))}
        <button
          onClick={createNewTab}
          className="p-1.5 hover:bg-slate-700 text-slate-400 rounded transition-colors"
          title="New Tab"
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
};
