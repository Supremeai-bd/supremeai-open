import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import Editor from '@monaco-editor/react';
import type { Terminal } from 'xterm';
import type { FitAddon } from '@xterm/addon-fit';
import 'xterm/css/xterm.css';

import { AiAssistantBar } from '../../components/editor/AiAssistantBar';
import { AiOutputPanel, type AiOutput } from '../../components/editor/AiOutputPanel';
import { JitOtpDialogHost } from '../../components/editor/JitOtpDialogHost';
import { setupMonacoAi } from '../../components/editor/monacoAi';
import { useIdeStore } from '../../store/useIdeStore';
import { FileExplorer } from '../../components/editor/FileExplorer';
import { EditorTabs } from '../../components/editor/EditorTabs';

export const IdeWorkspace: React.FC = () => {
  const { webContainer, setWebContainer, files, activeFile, updateFileContent, markFileSaved } = useIdeStore();

  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);

  const [isBooting, setIsBooting] = useState(true);

  // SupremeAI AI ইন্টারফেস স্টেট
  const [aiOutput, setAiOutput] = useState<AiOutput | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

  const handleAiOutput = (output: AiOutput) => setAiOutput(output);

  // Initialize Terminal and WebContainer
  useEffect(() => {
    let term: Terminal;

    const initEnv = async () => {
      if (terminalRef.current && !xtermRef.current) {
        const { Terminal } = await import('xterm');
        const { FitAddon } = await import('@xterm/addon-fit');
        term = new Terminal({
          theme: { background: '#1e1e1e', foreground: '#d4d4d4' },
          fontFamily: '"Fira Code", monospace',
          fontSize: 13,
          cursorBlink: true,
        });
        const fitAddon = new FitAddon();
        term.loadAddon(fitAddon);
        term.open(terminalRef.current);
        fitAddon.fit();
        xtermRef.current = term;
        fitAddonRef.current = fitAddon;

        term.writeln('🚀 \x1b[1;34mSupremeAI Code Editor\x1b[0m initializing...');
        term.writeln('⏳ Booting Zero-Cost Node.js environment in browser...');

        try {
          // Boot WebContainer if not already booted
          let wc = webContainer;
          if (!wc) {
            const { WebContainer } = await import('@webcontainer/api');
            wc = await WebContainer.boot();
            setWebContainer(wc);
          }
          term.writeln('✅ \x1b[1;32mWebContainer Booted Successfully!\x1b[0m\r\n');
          setIsBooting(false);

          // Start jsh shell
          const shellProcess = await wc.spawn('jsh');

          shellProcess.output.pipeTo(
            new WritableStream({
              write(data) {
                term.write(data);
              }
            })
          );

          const input = shellProcess.input.getWriter();
          term.onData((data) => {
            input.write(data);
          });

        } catch (error) {
          term.writeln(`\r\n❌ \x1b[1;31mError booting WebContainer:\x1b[0m ${error}`);
          setIsBooting(false);
        }
      }
    };

    initEnv();

    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit();
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once

  // Handle Monaco Editor Change
  const handleEditorChange = (value: string | undefined) => {
    if (activeFile && value !== undefined) {
      updateFileContent(activeFile, value);
    }
  };

  // Sync to WebContainer
  const handleSave = async () => {
    if (activeFile && webContainer) {
      const file = files[activeFile];
      if (file && file.isModified) {
        try {
          await webContainer.fs.writeFile(file.path, file.content);
          markFileSaved(activeFile);
          if (xtermRef.current) {
            xtermRef.current.writeln(`\r\n\x1b[1;32m[IDE] Saved ${file.name}\x1b[0m`);
          }
        } catch (e) {
          console.error("Save failed", e);
        }
      }
    }
  };

  // Monaco onMount — inline completion + context menu (VS Code extension equivalent)
  const handleEditorMount = useCallback(
    (editor: Parameters<NonNullable<React.ComponentProps<typeof Editor>['onMount']>>[0], monaco: Parameters<NonNullable<React.ComponentProps<typeof Editor>['onMount']>>[1]) => {
      setupMonacoAi(editor, monaco, {
        onOutput: (title, content) => setAiOutput({ title, content, kind: "plain" }),
      });
    },
    []
  );

  // Bind Ctrl+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFile, files, webContainer]);

  const currentFileData = activeFile ? files[activeFile] : null;

  return (
    <div className="h-screen w-full bg-[#1e1e1e] flex flex-col overflow-hidden text-gray-300">
      {/* Header */}
      <div className="h-12 bg-[#252526] border-b border-[#1e1e1e] flex items-center px-4 justify-between">
        <div className="flex items-center space-x-2">
          <div className="text-blue-400 font-bold">SupremeAI Code Editor</div>
          <div className="text-xs px-2 py-0.5 bg-gray-700 rounded text-gray-300">
            {isBooting ? 'Booting Engine...' : 'Engine Ready'}
          </div>
        </div>
        <div className="flex space-x-2">
           <button
             onClick={handleSave}
             disabled={!currentFileData?.isModified}
             className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-white text-xs font-semibold transition-colors"
           >
             Save (Ctrl+S)
           </button>
        </div>
      </div>

      {/* SupremeAI AI Action Bar — VS Code extension-এর মতো */}
      <AiAssistantBar activeFile={currentFileData} onOutput={handleAiOutput} onLoading={setAiLoading} />

      {/* Main Layout using react-resizable-panels */}
      <div className="flex-1 flex min-h-0">
        <PanelGroup orientation="horizontal">

          {/* LEFT: File Explorer */}
          <Panel defaultSize="20%" minSize="10%" maxSize="40%">
            <FileExplorer />
          </Panel>

          <PanelResizeHandle className="w-1 bg-[#252526] hover:bg-blue-500 cursor-col-resize transition-colors" />

          {/* RIGHT: Editor + Terminal */}
          <Panel defaultSize="80%">
            <PanelGroup orientation="vertical">

              {/* TOP: Editor */}
              <Panel defaultSize="70%" minSize="30%">
                <div className="flex flex-col h-full bg-[#1e1e1e]">
                  <EditorTabs />
                  <div className="flex-1 min-h-0">
                    {currentFileData ? (
                      <Editor
                        height="100%"
                        theme="vs-dark"
                        language={currentFileData.language}
                        value={currentFileData.content}
                        onChange={handleEditorChange}
                        onMount={handleEditorMount}
                        options={{ minimap: { enabled: false }, wordWrap: 'on' }}
                      />
                    ) : (
                      <div className="flex items-center justify-center h-full text-gray-500">
                        Select a file to edit
                      </div>
                    )}
                  </div>
                </div>
              </Panel>

              <PanelResizeHandle className="h-1 bg-[#252526] hover:bg-blue-500 cursor-row-resize transition-colors" />

              {/* BOTTOM: Terminal */}
              <Panel defaultSize="30%" minSize="10%">
                <div className="flex flex-col h-full bg-[#1e1e1e]">
                  <div className="h-8 bg-[#252526] border-b border-[#1e1e1e] flex items-center px-3 text-xs text-gray-400">
                    TERMINAL
                  </div>
                  <div ref={terminalRef} className="flex-1 p-2 min-h-0 bg-[#1e1e1e]" />
                </div>
              </Panel>

            </PanelGroup>
          </Panel>

        </PanelGroup>
      </div>

      {/* SupremeAI AI Output Overlay */}
      <AiOutputPanel output={aiOutput} loading={aiLoading} onClose={() => setAiOutput(null)} />

      {/* Global JIT OTP / prompt dialog host */}
      <JitOtpDialogHost />
    </div>
  );
};
