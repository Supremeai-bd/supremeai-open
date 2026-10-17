import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

/**
 * AI tools registration — RETIRED (issue #643, zero-credential control plane).
 *
 * বাংলা মন্তব্য: আগে এখানে ai.list_providers / ai.test_provider / ai_analyze_code
 * টুল সরাসরি LLM provider key pool ব্যবহার করত — control plane-এ অপ্রয়োজনীয়
 * credential exposure (#643)। AI analysis এখন বাইরের agent-caller context (বা
 * Core API) delegate করা হয়, তাই tower-এর tool surface থেকে সরাসরি AI
 * inference টুলগুলো সরানো হয়েছে।
 *
 * `registerAITools(server)` signature অপরিবর্তিত — tools/index.ts-এর boot
 * পাইপলাইন অটুট থাকে, ফাংশনটি এখন ইচ্ছাকৃতভাবে কোনো টুল রেজিস্টার করে না।
 */
export async function registerAITools(_server: McpServer): Promise<void> {
  // Intentionally registers no tools (#643): no direct LLM keys or inference
  // surface lives in the zero-credential control plane. Analysis is delegated
  // to the external agent caller context (or Core API).
  return;
}
