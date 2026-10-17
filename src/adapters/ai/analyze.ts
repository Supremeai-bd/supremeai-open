/**
 * AI analysis delegation stub (issue #643 — zero-credential control plane).
 *
 * বাংলা মন্তব্য: analyzeWithAI আগে সরাসরি provider key pool দিয়ে Gemini/Groq/
 * OpenRouter/Mistral call করত — control plane-এ অপ্রয়োজনীয় credential
 * exposure তৈরি করে (#643)। এখন এটি সৎ delegation উত্তর দেয়: কোনো provider
 * call, কোনো key, কোনো network — analysis বাইরের agent-caller context (বা
 * Core API) করবে। ফাংশন signature অপরিবর্তিত রাখা হয়েছে যাতে বিদ্যমান
 * consumer-দের import ভাঙে না (P3)।
 */

export const ANALYSIS_DELEGATION_NOTICE =
  "AI analysis is delegated to the external agent caller context (or Core API) — the MCP Control Tower holds no direct LLM provider keys (#643).";

export type AnalyzeResult = {
  provider: string;
  model: string;
  content: string;
  attempts: number;
  usedFallback: boolean;
};

/** সৎ delegation উত্তর — zero-key resilient mode, কোনো provider call নেই। */
export async function analyzeWithAI(
  _task: string,
  _content: string,
  _preferredProvider?: string,
): Promise<AnalyzeResult> {
  return {
    provider: "none",
    model: "none",
    content: ANALYSIS_DELEGATION_NOTICE,
    attempts: 0,
    usedFallback: false,
  };
}

/** সবসময় খালি — control plane-এ কোনো configured analysis provider নেই (#643)। */
export function listConfiguredAnalysisProviders(): string[] {
  return [];
}
