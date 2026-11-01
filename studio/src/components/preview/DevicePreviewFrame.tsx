import React, { useState } from 'react';
import { LiveSandboxRenderer } from './LiveSandboxRenderer';
import { MiniDevToolsBar } from './MiniDevToolsBar';
import { VisualElementInspector } from '../inspector/VisualElementInspector';
import { CodeDiffViewer } from '../diff/CodeDiffViewer';
import { TimeTravelBar } from '../timetravel/TimeTravelBar';
import type { SelectedElementInfo, VersionSnapshot, ProjectFile } from '../../types/worldclass';
import { INITIAL_PROJECT_FILES, VERSION_SNAPSHOTS } from '../../data/projectFiles';
import { PREVIEW_TEMPLATES, type PreviewTemplate } from '../../data/previewTemplates';
import { jarvisAudio } from '../../utils/audioFx';
import { 
  Monitor, Tablet, Smartphone, RotateCcw, ExternalLink, Code2, 
  Eye, Check, Copy, Sparkles, Layers, MousePointerClick, 
  GitCompare, FolderTree, Package, Rocket, FileCode, CheckCircle2 
} from 'lucide-react';

interface DevicePreviewFrameProps {
  htmlCode: string;
  onRefreshCode?: () => void;
  onFixWithHumanEye: () => void;
  isFixing: boolean;
  language: 'bn' | 'en';
  onApplyMicroPrompt?: (prompt: string, element: SelectedElementInfo) => void;
  onOpenDeployModal?: () => void;
  onOpenPackageModal?: () => void;
  snapshots?: VersionSnapshot[];
  currentVersionIndex?: number;
  onSelectSnapshot?: (index: number) => void;
  selectedTemplateId?: string;
  onSelectTemplate?: (templateId: string) => void;
}

export const DevicePreviewFrame: React.FC<DevicePreviewFrameProps> = ({
  htmlCode,
  onRefreshCode,
  onFixWithHumanEye,
  isFixing,
  language,
  onApplyMicroPrompt,
  onOpenDeployModal,
  onOpenPackageModal,
  snapshots = VERSION_SNAPSHOTS,
  currentVersionIndex = VERSION_SNAPSHOTS.length - 1,
  onSelectSnapshot,
  selectedTemplateId = 'food-delivery',
  onSelectTemplate,
}) => {
  const [deviceMode, setDeviceMode] = useState<'desktop' | 'tablet' | 'mobile'>('desktop');
  const [viewTab, setViewTab] = useState<'preview' | 'diff' | 'files' | 'code'>('preview');
  const [errors, setErrors] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // Click-to-edit Inspector state
  const [isInspectorActive, setIsInspectorActive] = useState(false);
  const [selectedElement, setSelectedElement] = useState<SelectedElementInfo | null>(null);

  // Multi-File Project State
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>(INITIAL_PROJECT_FILES);
  const [selectedFilePath, setSelectedFilePath] = useState<string>('src/App.tsx');

  const activeProjectFile = projectFiles.find((f) => f.path === selectedFilePath) || projectFiles[0];

  const handleErrorDetected = (err: string) => {
    setErrors((prev) => [...prev, err]);
  };

  const handleClearErrors = () => {
    setErrors([]);
  };

  const handleRefresh = () => {
    setRefreshKey((k) => k + 1);
    if (onRefreshCode) onRefreshCode();
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(htmlCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleInspector = () => {
    const nextState = !isInspectorActive;
    setIsInspectorActive(nextState);
    if (nextState) {
      jarvisAudio.playScan();
      setViewTab('preview');
    } else {
      setSelectedElement(null);
    }
  };

  const handleElementSelected = (elInfo: SelectedElementInfo) => {
    setSelectedElement(elInfo);
    jarvisAudio.playActivate();
  };

  const handleApplyMicroPromptInternal = (prompt: string, el: SelectedElementInfo) => {
    jarvisAudio.playSuccess();
    if (onApplyMicroPrompt) {
      onApplyMicroPrompt(prompt, el);
    }
    setSelectedElement(null);
    setIsInspectorActive(false);
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl relative">
      {/* =========================================================================
          Top Controls Toolbar: Mode Selectors, Inspector Toggle, Cloud Deploy
          ========================================================================= */}
      <div className="h-12 bg-slate-900/90 border-b border-slate-800 px-3 sm:px-4 flex items-center justify-between gap-2 shrink-0">
        {/* Left: Device Switcher (Desktop, Tablet, Mobile) + Inspector Toggle */}
        <div className="flex items-center gap-1 sm:gap-2">
          {/* 3-State Viewport Switcher */}
          <div className="flex items-center gap-0.5 p-0.5 bg-slate-950 border border-slate-800 rounded-lg">
            <button
              onClick={() => setDeviceMode('desktop')}
              className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors flex items-center gap-1 ${
                deviceMode === 'desktop'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="Desktop 100% Fluid View"
            >
              <Monitor className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">100%</span>
            </button>

            <button
              onClick={() => setDeviceMode('tablet')}
              className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors flex items-center gap-1 ${
                deviceMode === 'tablet'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="Tablet 768px View"
            >
              <Tablet className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">768px</span>
            </button>

            <button
              onClick={() => setDeviceMode('mobile')}
              className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors flex items-center gap-1 ${
                deviceMode === 'mobile'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="Mobile 375px/390px View"
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">390px</span>
            </button>
          </div>

          {/* Click-to-Edit Visual DOM Inspector Toggle */}
          <button
            onClick={toggleInspector}
            className={`px-2.5 py-1 text-xs font-bold rounded-lg border transition-all flex items-center gap-1.5 ${
              isInspectorActive
                ? 'bg-indigo-600 text-white border-indigo-400 shadow-md shadow-indigo-600/30 animate-pulse'
                : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-800 border-slate-800'
            }`}
            title="Click to edit any visual element directly on the screen (Lovable/v0 style)"
          >
            <MousePointerClick className="w-3.5 h-3.5 text-indigo-300" />
            <span className="hidden md:inline">
              {language === 'bn'
                ? (isInspectorActive ? 'ইনস্পেক্ট সক্রিয় ✕' : '🎯 এলিমেন্ট এডিট')
                : (isInspectorActive ? 'Inspecting ✕' : '🎯 Click to Edit')}
            </span>
          </button>
        </div>

        {/* Center: View Tab Switcher (Preview, Diff, Files, Code) */}
        <div className="flex items-center gap-1 p-0.5 bg-slate-950 border border-slate-800 rounded-lg text-xs font-medium">
          <button
            onClick={() => setViewTab('preview')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'preview' ? 'bg-indigo-600 text-white font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Eye className="w-3 h-3" />
            <span className="hidden lg:inline">{language === 'bn' ? 'লাইভ প্রিভিউ' : 'Preview'}</span>
          </button>

          <button
            onClick={() => setViewTab('diff')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'diff' ? 'bg-indigo-600 text-white font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <GitCompare className="w-3 h-3" />
            <span className="hidden lg:inline">{language === 'bn' ? 'ডিফ ভিউ' : 'Diff'}</span>
          </button>

          <button
            onClick={() => setViewTab('files')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'files' ? 'bg-indigo-600 text-white font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <FolderTree className="w-3 h-3" />
            <span className="hidden lg:inline">{language === 'bn' ? 'ফাইল ট্রি' : 'Files'}</span>
          </button>

          <button
            onClick={() => setViewTab('code')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'code' ? 'bg-indigo-600 text-white font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Code2 className="w-3 h-3" />
            <span className="hidden lg:inline">{language === 'bn' ? 'সোর্স' : 'Source'}</span>
          </button>
        </div>

        {/* Right: NPM Packages & Deploy Live Button */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          {onOpenPackageModal && (
            <button
              onClick={onOpenPackageModal}
              className="p-1.5 sm:px-2.5 sm:py-1 text-xs text-slate-300 hover:text-white bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-lg transition-colors flex items-center gap-1 font-mono"
              title="Inject npm / CDN packages"
            >
              <Package className="w-3.5 h-3.5 text-indigo-400" />
              <span className="hidden xl:inline">{language === 'bn' ? 'প্যাকেজ' : 'Packages'}</span>
            </button>
          )}

          {onOpenDeployModal && (
            <button
              onClick={onOpenDeployModal}
              className="px-2.5 py-1 text-xs font-bold text-slate-950 bg-gradient-to-r from-emerald-400 to-teal-400 hover:from-emerald-300 hover:to-teal-300 rounded-lg transition-all flex items-center gap-1.5 shadow-sm shadow-emerald-500/20 whitespace-nowrap active:scale-95"
              title="1-Click Multi-Cloud Deploy (Cloudflare Edge / Vercel / Render)"
            >
              <Rocket className="w-3.5 h-3.5" />
              <span>{language === 'bn' ? 'পাবলিশ' : 'Publish'}</span>
            </button>
          )}

          <button
            onClick={handleRefresh}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors border border-slate-800"
            title="Reload Preview Sandbox"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* =========================================================================
          Embedded Time-Travel Version Scrubber Bar & Quick Template Switcher
          ========================================================================= */}
      <div className="p-2 bg-slate-950 border-b border-slate-800/80 flex flex-col gap-2">
        <TimeTravelBar
          snapshots={snapshots}
          currentVersionIndex={currentVersionIndex}
          onSelectSnapshot={(idx) => {
            if (onSelectSnapshot) onSelectSnapshot(idx);
          }}
          language={language}
        />

        {/* Ready-to-Run Interactive Templates Strip (Tier 1 Mandate) */}
        {onSelectTemplate && (
          <div className="flex items-center gap-1.5 overflow-x-auto text-[11px] font-mono pb-0.5">
            <span className="text-slate-500 text-[10px] shrink-0 font-bold">TEMPLATES:</span>
            {PREVIEW_TEMPLATES.map((tmpl) => {
              const isSelected = selectedTemplateId === tmpl.id;
              return (
                <button
                  key={tmpl.id}
                  onClick={() => onSelectTemplate(tmpl.id)}
                  className={`px-2.5 py-0.5 rounded-lg border transition-all whitespace-nowrap shrink-0 flex items-center gap-1 ${
                    isSelected
                      ? 'bg-indigo-950 border-indigo-500 text-indigo-300 font-bold shadow-sm'
                      : 'bg-slate-900/80 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700'
                  }`}
                >
                  <span>{tmpl.nameEn}</span>
                  {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* =========================================================================
          Main Interactive Canvas Area
          ========================================================================= */}
      <div className="flex-1 overflow-auto bg-slate-950/70 p-3 sm:p-4 flex items-center justify-center relative">
        {/* Floating Click-to-Edit Inspector Micro-Prompt Popover */}
        <VisualElementInspector
          isOpen={isInspectorActive && selectedElement !== null}
          onClose={() => setSelectedElement(null)}
          selectedElement={selectedElement}
          onApplyMicroPrompt={handleApplyMicroPromptInternal}
          language={language}
        />

        {/* 1. LIVE SANDBOX PREVIEW */}
        {viewTab === 'preview' && (
          deviceMode === 'desktop' ? (
            /* Desktop Viewport (100% Fluid Container with browser header bar) */
            <div className="w-full h-full bg-slate-950 rounded-xl overflow-hidden border border-slate-800 flex flex-col shadow-2xl relative">
              <div className="h-8 bg-slate-900 border-b border-slate-800 px-3 flex items-center gap-2 text-xs font-mono text-slate-500 shrink-0 select-none">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                </div>
                <div className="flex-1 max-w-sm mx-auto bg-slate-950 px-3 py-0.5 rounded text-[11px] text-slate-400 text-center truncate border border-slate-800/80">
                  https://app.supremeai.local/preview
                </div>
                {isInspectorActive && (
                  <span className="text-[10px] text-indigo-400 font-bold bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-800">
                    CLICK-TO-EDIT ACTIVE
                  </span>
                )}
              </div>

              {/* Sandboxed Renderer */}
              <div className="flex-1 w-full h-full">
                <LiveSandboxRenderer
                  key={refreshKey}
                  htmlCode={htmlCode}
                  onErrorDetected={handleErrorDetected}
                  onClearErrors={handleClearErrors}
                  isMobile={false}
                  inspectorActive={isInspectorActive}
                  onElementSelected={handleElementSelected}
                />
              </div>
            </div>
          ) : deviceMode === 'tablet' ? (
            /* Tablet Viewport (768px Width Container with iPad-style frame) */
            <div className="my-auto relative flex flex-col items-center">
              <div className="w-[768px] h-[780px] max-h-[85vh] bg-slate-900 rounded-[36px] p-3 border-4 border-slate-800 shadow-2xl shadow-indigo-950/40 relative flex flex-col overflow-hidden">
                {/* Tablet Top Camera Notch */}
                <div className="h-6 flex items-center justify-center shrink-0">
                  <div className="w-3 h-3 rounded-full bg-black border border-slate-700/60" />
                </div>

                {/* Tablet Screen Surface */}
                <div className="flex-1 w-full rounded-[24px] overflow-hidden bg-slate-950 border border-slate-800/80">
                  <LiveSandboxRenderer
                    key={refreshKey}
                    htmlCode={htmlCode}
                    onErrorDetected={handleErrorDetected}
                    onClearErrors={handleClearErrors}
                    isMobile={false}
                    inspectorActive={isInspectorActive}
                    onElementSelected={handleElementSelected}
                  />
                </div>

                {/* Tablet Bottom Bezel */}
                <div className="h-4 shrink-0" />
              </div>
            </div>
          ) : (
            /* Mobile Viewport (iPhone 16 Pro Frame 390px x 844px) */
            <div className="my-auto relative flex flex-col items-center">
              <div className="w-[390px] h-[780px] bg-slate-900 rounded-[50px] p-3 border-4 border-slate-800 shadow-2xl shadow-indigo-950/30 relative flex flex-col overflow-hidden">
                {/* Dynamic Island / Speaker Notch */}
                <div className="absolute top-4 left-1/2 -translate-x-1/2 w-28 h-6 bg-black rounded-full z-30 flex items-center justify-between px-3">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-950 border border-indigo-700/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                </div>

                {/* Status Bar */}
                <div className="h-9 px-6 pt-1 flex items-center justify-between text-[11px] font-mono text-slate-300 select-none shrink-0 z-20">
                  <span className="font-bold">9:41</span>
                  <div className="flex items-center gap-1.5 text-[10px]">
                    <span>5G</span>
                    <span className="font-bold">100%</span>
                  </div>
                </div>

                {/* Mobile Screen Surface */}
                <div className="flex-1 w-full rounded-[38px] overflow-hidden bg-slate-950 border border-slate-800/80">
                  <LiveSandboxRenderer
                    key={refreshKey}
                    htmlCode={htmlCode}
                    onErrorDetected={handleErrorDetected}
                    onClearErrors={handleClearErrors}
                    isMobile={true}
                    inspectorActive={isInspectorActive}
                    onElementSelected={handleElementSelected}
                  />
                </div>

                {/* iPhone Home Bar Indicator */}
                <div className="h-5 flex items-center justify-center shrink-0">
                  <div className="w-32 h-1 bg-slate-600/80 rounded-full" />
                </div>
              </div>
            </div>
          )
        )}

        {/* 2. GIT-STYLE CODE DIFF VIEWER */}
        {viewTab === 'diff' && (
          <div className="w-full h-full">
            <CodeDiffViewer
              fileName="src/components/Hero.tsx"
              originalCode={activeProjectFile.content.replace('bg-gradient-to-r from-emerald-500 to-teal-500', 'bg-emerald-600')}
              modifiedCode={activeProjectFile.content}
              language={language}
            />
          </div>
        )}

        {/* 3. MULTI-FILE PROJECT EXPLORER */}
        {viewTab === 'files' && (
          <div className="w-full h-full bg-slate-900/90 rounded-xl border border-slate-800 flex overflow-hidden">
            {/* Left File Tree Sidebar */}
            <div className="w-56 bg-slate-950 border-r border-slate-800 p-3 space-y-2 shrink-0">
              <span className="text-[11px] font-bold text-slate-400 font-mono block">WORKSPACE FILES</span>
              <div className="space-y-1">
                {projectFiles.map((file) => (
                  <button
                    key={file.path}
                    onClick={() => setSelectedFilePath(file.path)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-mono transition-colors flex items-center gap-2 ${
                      selectedFilePath === file.path
                        ? 'bg-indigo-600 text-white font-semibold'
                        : 'text-slate-400 hover:text-white hover:bg-slate-900'
                    }`}
                  >
                    <FileCode className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{file.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Right File Code Viewer */}
            <div className="flex-1 flex flex-col overflow-hidden bg-slate-900">
              <div className="h-9 px-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-xs font-mono text-slate-400">
                <span className="font-semibold text-white">{activeProjectFile.path}</span>
                <span>{activeProjectFile.language}</span>
              </div>
              <pre className="flex-1 p-4 font-mono text-xs text-slate-200 overflow-auto leading-relaxed">
                {activeProjectFile.content}
              </pre>
            </div>
          </div>
        )}

        {/* 4. RAW GENERATED HTML SOURCE VIEWER */}
        {viewTab === 'code' && (
          <div className="w-full h-full bg-slate-900 rounded-xl border border-slate-800 p-4 flex flex-col justify-between">
            <div className="flex justify-between items-center pb-2 border-b border-slate-800 text-xs font-mono">
              <span className="text-slate-400">Generated Frontend Template (HTML / Tailwind)</span>
              <button
                onClick={handleCopyCode}
                className="text-slate-300 hover:text-white flex items-center gap-1 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy HTML'}</span>
              </button>
            </div>
            <pre className="flex-1 p-3 font-mono text-xs text-slate-300 overflow-auto leading-relaxed">
              {htmlCode}
            </pre>
          </div>
        )}
      </div>

      {/* =========================================================================
          Bottom DevTools Telemetry Bar
          ========================================================================= */}
      <MiniDevToolsBar
        errorCount={errors.length}
        performanceScore={errors.length > 0 ? 82 : 98}
        isMobile={deviceMode === 'mobile'}
        onFixWithHumanEye={onFixWithHumanEye}
        isFixing={isFixing}
        language={language}
      />
    </div>
  );
};
