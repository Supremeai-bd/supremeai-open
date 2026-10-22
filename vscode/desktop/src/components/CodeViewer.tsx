import React, { Suspense, lazy } from "react";

const MonacoEditor: any = lazy(() => import("@monaco-editor/react"));

export interface CodeViewerProps {
  value: string;
  language?: string;
  onChange?: (value: string) => void;
}

export function CodeViewer({ value, language = "typescript", onChange }: CodeViewerProps) {
  return (
    <Suspense fallback={<div className="p-4 text-slate-400">Loading editor...</div>}>
      <MonacoEditor
        height="100%"
        language={language}
        value={value}
        onChange={(v: any) => onChange?.(v ?? "")}
        theme="vs-dark"
      />
    </Suspense>
  );
}
