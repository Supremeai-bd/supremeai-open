import React, { useState } from 'react';
import { GitCompare, Check, Copy, ArrowLeft, ArrowRight, Layers } from 'lucide-react';

interface CodeDiffViewerProps {
  fileName: string;
  originalCode: string;
  modifiedCode: string;
  language: 'bn' | 'en';
}

export const CodeDiffViewer: React.FC<CodeDiffViewerProps> = ({
  fileName,
  originalCode,
  modifiedCode,
  language,
}) => {
  const [diffMode, setDiffMode] = useState<'split' | 'unified'>('split');
  const [copied, setCopied] = useState(false);

  const origLines = originalCode.split('\n');
  const modLines = modifiedCode.split('\n');

  const handleCopyMod = () => {
    navigator.clipboard.writeText(modifiedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden font-mono text-xs">
      {/* Diff Header */}
      <div className="h-10 bg-slate-900 px-4 flex items-center justify-between border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-2 text-slate-300">
          <GitCompare className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-bold text-white">{fileName}</span>
          <span className="text-[10px] text-emerald-400 bg-emerald-950/80 px-1.5 py-0.2 rounded border border-emerald-800">
            +18 lines
          </span>
          <span className="text-[10px] text-rose-400 bg-rose-950/80 px-1.5 py-0.2 rounded border border-rose-800">
            -2 lines
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-slate-950 p-0.5 rounded border border-slate-800 text-[11px]">
            <button
              onClick={() => setDiffMode('split')}
              className={`px-2 py-0.5 rounded transition-colors ${
                diffMode === 'split' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Split
            </button>
            <button
              onClick={() => setDiffMode('unified')}
              className={`px-2 py-0.5 rounded transition-colors ${
                diffMode === 'unified' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Unified
            </button>
          </div>

          <button
            onClick={handleCopyMod}
            className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition-colors"
            title="Copy Modified Code"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Diff Content Body */}
      <div className="flex-1 overflow-auto p-2">
        {diffMode === 'split' ? (
          <div className="grid grid-cols-2 gap-2 h-full">
            {/* Left: Original */}
            <div className="bg-slate-900/60 rounded-lg p-2 border border-slate-800/80 overflow-auto">
              <span className="text-[10px] text-slate-500 font-bold block mb-1">BEFORE (Original)</span>
              <div className="space-y-0.5">
                {origLines.map((line, idx) => {
                  const isModified = idx > 15 && idx < 19;
                  return (
                    <div
                      key={idx}
                      className={`flex items-start gap-3 px-1 py-0.2 rounded ${
                        isModified ? 'bg-rose-950/40 text-rose-300' : 'text-slate-400'
                      }`}
                    >
                      <span className="w-6 text-slate-600 select-none text-right">{idx + 1}</span>
                      <span className="whitespace-pre">{line || ' '}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right: Modified */}
            <div className="bg-slate-900/60 rounded-lg p-2 border border-slate-800/80 overflow-auto">
              <span className="text-[10px] text-emerald-400 font-bold block mb-1">AFTER (JARVIS Modified)</span>
              <div className="space-y-0.5">
                {modLines.map((line, idx) => {
                  const isAdded = idx > 15 && idx < 22;
                  return (
                    <div
                      key={idx}
                      className={`flex items-start gap-3 px-1 py-0.2 rounded ${
                        isAdded ? 'bg-emerald-950/50 text-emerald-200 font-semibold' : 'text-slate-300'
                      }`}
                    >
                      <span className="w-6 text-slate-600 select-none text-right">{idx + 1}</span>
                      <span className="whitespace-pre">{line || ' '}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          /* Unified Diff View */
          <div className="space-y-0.5">
            {modLines.map((line, idx) => {
              const isAdded = idx > 15 && idx < 22;
              return (
                <div
                  key={idx}
                  className={`flex items-start gap-3 px-2 py-0.5 rounded ${
                    isAdded ? 'bg-emerald-950/40 text-emerald-200' : 'text-slate-300'
                  }`}
                >
                  <span className="w-8 text-slate-600 select-none">{idx + 1}</span>
                  <span className="w-3 text-emerald-400 select-none">{isAdded ? '+' : ' '}</span>
                  <span className="whitespace-pre">{line || ' '}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
