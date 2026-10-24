import React from "react";
import { useAiActions } from "../../services/aiActions";
import type { FileContext } from "../../services/aiActions";
import type { AiOutput } from "./AiOutputPanel";
import type { IdeFile } from "../../store/useIdeStore";

interface Props {
  activeFile: IdeFile | null;
  onOutput: (output: AiOutput) => void;
  onLoading: (loading: boolean) => void;
}

/** Desktop IDE-তে SupremeAI quick action toolbar (VS Code command palette-এর মতো)। */
export const AiAssistantBar: React.FC<Props> = ({ activeFile, onOutput, onLoading }) => {
  const { busy, runWithContext, explain, review, securityScan, analyzePerformance, autoHeal, jitAction } =
    useAiActions();

  const btn = (label: string, key: string, action: () => void, danger = false) => (
    <button
      key={key}
      onClick={action}
      disabled={busy !== null}
      className={`px-2.5 py-1 text-xs rounded font-medium transition-colors ${
        danger
          ? "bg-red-900/40 hover:bg-red-800/60 text-red-300 border border-red-800/50"
          : "bg-gray-700 hover:bg-gray-600 text-gray-200 border border-gray-600/50"
      } ${busy === key ? "opacity-60 animate-pulse" : ""} ${busy !== null && busy !== key ? "opacity-40" : ""}`}
    >
      {busy === key ? "…" : label}
    </button>
  );

  const run = (handler: (ctx: FileContext, out: (o: AiOutput) => void, loading: (b: boolean) => void) => Promise<void>) => {
    runWithContext(activeFile, onOutput, (ctx) => handler(ctx, onOutput, onLoading));
  };

  return (
    <div className="flex items-center space-x-1.5 px-3 py-1.5 bg-[#2b2b2b] border-b border-[#1e1e1e]">
      <span className="text-[10px] uppercase tracking-wider text-gray-500 mr-1 font-semibold">SupremeAI</span>
      {btn("Explain", "explain", () => run(explain))}
      {btn("Review", "review", () => run(review))}
      {btn("Security Scan", "security", () => run(securityScan))}
      {btn("Analyze Perf", "performance", () => run(analyzePerformance))}
      {btn("Auto-Heal", "heal", () => run(autoHeal))}
      {btn("🔐 JIT Action", "jit", () => jitAction(onOutput, onLoading), true)}
    </div>
  );
};
