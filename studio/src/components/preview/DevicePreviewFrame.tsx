import React, { useState } from 'react';
import { LiveSandboxRenderer } from './LiveSandboxRenderer';
import { MiniDevToolsBar } from './MiniDevToolsBar';
import { VisualElementInspector } from '../inspector/VisualElementInspector';
import { CodeDiffViewer } from '../diff/CodeDiffViewer';
import { TimeTravelBar } from '../timetravel/TimeTravelBar';
import type { SelectedElementInfo, VersionSnapshot, ProjectFile } from '../../types/worldclass';
import { INITIAL_PROJECT_FILES, VERSION_SNAPSHOTS } from '../../data/projectFiles';
import { PREVIEW_TEMPLATES } from '../../data/previewTemplates';
import { jarvisAudio } from '../../utils/audioFx';
import { 
  Monitor, Tablet, Smartphone, RotateCcw,
  Eye, MousePointerClick, 
  GitCompare, FolderTree, Package, Rocket, FileCode 
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
  const [refreshKey, setRefreshKey] = useState(0);

  // Click-to-edit Inspector state
  const [isInspectorActive, setIsInspectorActive] = useState(false);
  const [selectedElement, setSelectedElement] = useState<SelectedElementInfo | null>(null);

  // Multi-File Project State
  const [projectFiles] = useState<ProjectFile[]>(INITIAL_PROJECT_FILES);
  const [selectedFilePath, setSelectedFilePath] = useState<string>('src/App.tsx');

  const activeProjectFile = projectFiles.find((f) => f.path === selectedFilePath) || projectFiles[0];

  const handleRefresh = () => {
    setRefreshKey((k) => k + 1);
    jarvisAudio.playScan();
    if (onRefreshCode) onRefreshCode();
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
    <div className="flex flex-col h-full bg-[#080c14] border border-white/10 rounded-2xl overflow-hidden shadow-2xl relative">
      {/* =========================================================================
          Top Controls Toolbar: Mode Selectors, Inspector Toggle, Cloud Deploy
          ========================================================================= */}
      <div className="h-12 bg-[#0d131f]/90 border-b border-white/10 px-3 sm:px-4 flex items-center justify-between gap-2 shrink-0 backdrop-blur-md">
        {/* Left: Device Switcher (Desktop, Tablet, Mobile) + Inspector Toggle */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          {/* 3-State Viewport Switcher */}
          <div className="flex items-center gap-0.5 p-0.5 bg-black/40 border border-white/10 rounded-lg">
            <button
              type="button"
              onClick={() => setDeviceMode('desktop')}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 ${
                deviceMode === 'desktop'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="Desktop 100% Fluid View"
            >
              <Monitor className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">100%</span>
            </button>

            <button
              type="button"
              onClick={() => setDeviceMode('tablet')}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 ${
                deviceMode === 'tablet'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="Tablet 768px View"
            >
              <Tablet className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">768px</span>
            </button>

            <button
              type="button"
              onClick={() => setDeviceMode('mobile')}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 ${
                deviceMode === 'mobile'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="Mobile 390px View"
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">390px</span>
            </button>
          </div>

          {/* Click-to-Edit Visual DOM Inspector Toggle */}
          <button
            type="button"
            onClick={toggleInspector}
            className={`px-2.5 py-1 text-xs font-semibold rounded-lg border transition-all flex items-center gap-1.5 ${
              isInspectorActive
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-400 shadow-md shadow-cyan-500/20'
                : 'bg-black/30 text-slate-300 hover:text-white hover:bg-white/5 border-white/10'
            }`}
            title="Click to edit visual elements directly on screen"
          >
            <MousePointerClick className="w-3.5 h-3.5 text-cyan-300" />
            <span className="hidden md:inline">
              {isInspectorActive ? 'Inspecting ✕' : 'Click to Edit'}
            </span>
          </button>
        </div>

        {/* Center: View Tab Switcher (Preview, Diff, Files, Code) */}
        <div className="flex items-center gap-0.5 p-0.5 bg-black/40 border border-white/10 rounded-lg text-xs font-medium">
          <button
            type="button"
            onClick={() => setViewTab('preview')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'preview' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Eye className="w-3 h-3" />
            <span className="hidden lg:inline">Preview</span>
          </button>

          <button
            type="button"
            onClick={() => setViewTab('diff')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'diff' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <GitCompare className="w-3 h-3" />
            <span className="hidden lg:inline">Diff</span>
          </button>

          <button
            type="button"
            onClick={() => setViewTab('files')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'files' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <FolderTree className="w-3 h-3" />
            <span className="hidden lg:inline">Files</span>
          </button>

          <button
            type="button"
            onClick={() => setViewTab('code')}
            className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
              viewTab === 'code' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            <FileCode className="w-3 h-3" />
            <span className="hidden lg:inline">Source</span>
          </button>
        </div>

        {/* Right: Packages & Deploy Live Button */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          {onOpenPackageModal && (
            <button
              type="button"
              onClick={onOpenPackageModal}
              className="px-2.5 py-1 text-xs text-slate-300 hover:text-white bg-black/40 border border-white/10 hover:border-white/20 rounded-lg transition-colors flex items-center gap-1 font-mono"
              title="Inject npm / CDN packages"
            >
              <Package className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden xl:inline">Packages</span>
            </button>
          )}

          {onOpenDeployModal && (
            <button
              type="button"
              onClick={onOpenDeployModal}
              className="px-3 py-1 text-xs font-bold text-slate-950 bg-gradient-to-r from-cyan-400 to-emerald-400 hover:brightness-110 rounded-lg transition-all flex items-center gap-1.5 shadow-sm shadow-cyan-500/20 whitespace-nowrap active:scale-95"
              title="1-Click Multi-Cloud Deploy"
            >
              <Rocket className="w-3.5 h-3.5" />
              <span>Deploy</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleRefresh}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors border border-white/10"
            title="Reload Preview"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* =========================================================================
          Embedded Time-Travel Version Scrubber Bar & Quick Template Switcher
          ========================================================================= */}
      <div className="p-2 bg-[#090d16] border-b border-white/10 flex flex-col gap-2">
        <TimeTravelBar
          snapshots={snapshots}
          currentVersionIndex={currentVersionIndex}
          onSelectSnapshot={(idx) => {
            if (onSelectSnapshot) onSelectSnapshot(idx);
          }}
          language={language}
        />

        {/* Ready-to-Run Interactive Templates Strip */}
        {onSelectTemplate && (
          <div className="flex items-center gap-1.5 overflow-x-auto text-[11px] font-mono pb-0.5">
            <span className="text-slate-500 text-[10px] shrink-0 font-bold">TEMPLATES:</span>
            {PREVIEW_TEMPLATES.map((tmpl) => {
              const isSelected = selectedTemplateId === tmpl.id;
              return (
                <button
                  key={tmpl.id}
                  type="button"
                  onClick={() => onSelectTemplate(tmpl.id)}
                  className={`px-2.5 py-0.5 rounded-lg border transition-all whitespace-nowrap shrink-0 flex items-center gap-1 ${
                    isSelected
                      ? 'bg-cyan-950/80 border-cyan-500 text-cyan-300 font-semibold shadow-sm'
                      : 'bg-black/30 border-white/10 text-slate-400 hover:text-white hover:border-white/20'
                  }`}
                >
                  <span>{tmpl.nameEn}</span>
                  {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* =========================================================================
          Main Interactive Canvas Area
          ========================================================================= */}
      <div className="flex-1 overflow-auto bg-[#060911] p-3 sm:p-4 flex items-center justify-center relative">
        <VisualElementInspector
          isOpen={isInspectorActive && selectedElement !== null}
          onClose={() => setSelectedElement(null)}
          selectedElement={selectedElement}
          onApplyPrompt={handleApplyMicroPromptInternal}
          language={language}
        />

        {viewTab === 'preview' && (
          <div
            className={`transition-all duration-300 mx-auto h-full flex flex-col items-center justify-center ${
              deviceMode === 'desktop'
                ? 'w-full'
                : deviceMode === 'tablet'
                ? 'w-[768px] max-w-full shadow-2xl rounded-2xl border border-white/10 overflow-hidden'
                : 'w-[390px] max-w-full shadow-2xl rounded-[36px] border-4 border-slate-800 overflow-hidden'
            }`}
          >
            <div className="w-full h-full relative rounded-xl overflow-hidden bg-slate-950">
              <LiveSandboxRenderer
                key={refreshKey}
                htmlContent={htmlCode}
                onError={setErrors}
                onElementClick={isInspectorActive ? handleElementSelected : undefined}
                isInspecting={isInspectorActive}
              />
            </div>
          </div>
        )}

        {viewTab === 'diff' && (
          <div className="w-full h-full p-2 overflow-auto">
            <CodeDiffViewer
              oldCode={snapshots[0]?.html || htmlCode}
              newCode={htmlCode}
              language="html"
            />
          </div>
        )}

        {viewTab === 'files' && (
          <div className="w-full h-full flex bg-[#0d131f] border border-white/10 rounded-xl overflow-hidden">
            <div className="w-56 border-r border-white/10 p-3 bg-black/40 text-xs font-mono">
              <span className="text-slate-400 font-bold block mb-2 uppercase text-[10px]">Project Files</span>
              <div className="space-y-1">
                {projectFiles.map((file) => (
                  <button
                    key={file.path}
                    type="button"
                    onClick={() => setSelectedFilePath(file.path)}
                    className={`w-full text-left px-2 py-1.5 rounded-lg transition-colors flex items-center gap-2 ${
                      file.path === selectedFilePath
                        ? 'bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/40'
                        : 'text-slate-400 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <span>{file.name}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 p-4 font-mono text-xs text-slate-300 overflow-auto bg-slate-950">
              <pre>{activeProjectFile.content}</pre>
            </div>
          </div>
        )}

        {viewTab === 'code' && (
          <div className="w-full h-full p-4 font-mono text-xs text-cyan-300/90 overflow-auto bg-slate-950 rounded-xl border border-white/10">
            <pre className="whitespace-pre-wrap">{htmlCode}</pre>
          </div>
        )}
      </div>

      {/* Embedded Mini DevTools Bar at bottom */}
      <MiniDevToolsBar
        errorCount={errors.length}
        performanceScore={98}
        isMobile={deviceMode === 'mobile'}
        onFixWithHumanEye={onFixWithHumanEye}
        isFixing={isFixing}
        language={language}
      />
    </div>
  );
};
