/**
 * AI Actions — Desktop IDE-তে VS Code extension-এর মতো quick AI actions।
 * সবগুলোই @supremeai/shared-services (platform-agnostic core) ব্যবহার করে।
 */

import { useCallback, useState } from "react";
import { getSharedServices } from "./supremeShared";
import { promptForOtp } from "@supremeai/shared-services";
import { desktopPrompt } from "../components/editor/desktopPrompt";
import type { AiOutput } from "../components/editor/AiOutputPanel";
import type { IdeFile } from "../store/useIdeStore";

export interface FileContext {
  code: string;
  language: string;
  path: string;
}

export function useAiActions() {
  const [busy, setBusy] = useState<string | null>(null);

  const setLoading = useCallback((b: boolean, key?: string) => {
    setBusy(b ? key ?? "busy" : null);
  }, []);

  const runWithContext = useCallback(
    (activeFile: IdeFile | null, onOutput: (o: AiOutput) => void, handler: (ctx: FileContext) => Promise<void>) => {
      if (!activeFile) {
        onOutput({ title: "SupremeAI", content: "⚠️ কোনো ফাইল সিলেক্ট করা নেই।", kind: "plain" });
        return;
      }
      handler({ code: activeFile.content, language: activeFile.language, path: activeFile.path });
    },
    []
  );

  const explain = useCallback(
    async (ctx: FileContext, onOutput: (o: AiOutput) => void, onLoading: (b: boolean) => void) => {
      setLoading(true, "explain");
      onLoading(true);
      try {
        const { service } = getSharedServices();
        const res = await service.sendChatMessage({
          message: `Please explain the following ${ctx.language} code in detail:\n\n\`\`\`${ctx.language}\n${ctx.code}\n\`\`\``,
          sessionId: service.getSessionId(),
          context: { source: "desktop", language: ctx.language, filePath: ctx.path, timestamp: new Date().toISOString() },
        });
        onOutput({ title: "📘 Code Explanation", content: res.response, kind: "plain" });
      } catch (e: unknown) {
        onOutput({ title: "Explain Failed", content: String((e as Error)?.message ?? e), kind: "plain" });
      } finally {
        setLoading(false);
        onLoading(false);
      }
    },
    [setLoading]
  );

  const review = useCallback(
    async (ctx: FileContext, onOutput: (o: AiOutput) => void, onLoading: (b: boolean) => void) => {
      setLoading(true, "review");
      onLoading(true);
      try {
        const { service } = getSharedServices();
        const res = await service.sendChatMessage({
          message: `Please review the following ${ctx.language} code for bugs, style issues, and performance optimizations:\n\n\`\`\`${ctx.language}\n${ctx.code}\n\`\`\``,
          sessionId: service.getSessionId(),
          context: { source: "desktop", language: ctx.language, filePath: ctx.path, timestamp: new Date().toISOString() },
        });
        onOutput({ title: "🛡️ AI Code Review", content: res.response, kind: "plain" });
      } catch (e: unknown) {
        onOutput({ title: "Review Failed", content: String((e as Error)?.message ?? e), kind: "plain" });
      } finally {
        setLoading(false);
        onLoading(false);
      }
    },
    [setLoading]
  );

  const securityScan = useCallback(
    async (ctx: FileContext, onOutput: (o: AiOutput) => void, onLoading: (b: boolean) => void) => {
      setLoading(true, "security");
      onLoading(true);
      try {
        const { security } = getSharedServices();
        const issues = await security.scanCode(ctx.code, ctx.language, ctx.path);
        const content = issues.length
          ? issues
              .map((i, idx) => `${idx + 1}. [${i.severity?.toUpperCase()}] ${i.type}: ${i.description}\n   → ${i.recommendation}`)
              .join("\n\n")
          : "✅ কোনো স্পষ্ট security issue পাওয়া যায়নি। (AI-আনুমানিক — রিভিউ করা আবশ্যক।)";
        onOutput({ title: "🛡️ Security Scan", content, kind: "plain", meta: `${issues.length} issue(s)` });
      } catch (e: unknown) {
        onOutput({ title: "Security Scan Failed", content: String((e as Error)?.message ?? e), kind: "plain" });
      } finally {
        setLoading(false);
        onLoading(false);
      }
    },
    [setLoading]
  );
const analyzePerformance = useCallback(
    async (ctx: FileContext, onOutput: (o: AiOutput) => void, onLoading: (b: boolean) => void) => {
      setLoading(true, "performance");
      onLoading(true);
      try {
        const { performance } = getSharedServices();
        const insight = await performance.analyzePerformance(ctx.code, ctx.language, ctx.path);
        const content = [
          `Complexity Score: ${insight.complexity_score}/100`,
          `Estimated Impact: ${insight.estimated_impact}`,
          "",
          "🔻 Bottlenecks:",
          ...(insight.bottlenecks.length ? insight.bottlenecks.map((b) => `  • ${b}`) : ["  • None detected"]),
          "",
          "💡 Recommendations:",
          ...(insight.recommendations.length ? insight.recommendations.map((r) => `  • ${r}`) : ["  • None detected"]),
        ].join("\n");
        onOutput({ title: "⚡ Performance Analysis", content, kind: "plain" });
      } catch (e: unknown) {
        onOutput({ title: "Performance Analysis Failed", content: String((e as Error)?.message ?? e), kind: "plain" });
      } finally {
        setLoading(false);
        onLoading(false);
      }
    },
    [setLoading]
  );

  const autoHeal = useCallback(
    async (ctx: FileContext, onOutput: (o: AiOutput) => void, onLoading: (b: boolean) => void) => {
      setLoading(true, "heal");
      onLoading(true);
      try {
        const { healing } = getSharedServices();
        const fix = await healing.healError({
          filePath: ctx.path,
          message: "User requested auto-fix for current file",
          lineNumber: 1,
          codeContext: ctx.code,
          languageId: ctx.language,
        });
        if (fix?.fixedCode) {
          onOutput({
            title: "🩺 SupremeAI Fix",
            content: `▪️ ব্যাখ্যা: ${fix.explanation}\n\n--------- Proposed Fixed Code ---------\n\n${fix.fixedCode}`,
            kind: "plain",
          });
        } else {
          onOutput({ title: "Self-Healing", content: "কোনো automatic fix পাওয়া যায়নি।", kind: "plain" });
        }
      } catch (e: unknown) {
        onOutput({ title: "Self-Healing Failed", content: String((e as Error)?.message ?? e), kind: "plain" });
      } finally {
        setLoading(false);
        onLoading(false);
      }
    },
    [setLoading]
  );

  const jitAction = useCallback(
    async (onOutput: (o: AiOutput) => void, onLoading: (b: boolean) => void) => {
      setLoading(true, "jit");
      onLoading(true);
      try {
        const result = await promptForOtp(desktopPrompt, "Bind target workspace (write scope)");
        if (result.cancelled) {
          onOutput({ title: "JIT OTP", content: "অপারেশন বাতিল হয়েছে।", kind: "plain" });
        } else {
          const { apiCall } = await import("./supremeShared");
          // ERR-H03 FIX: backend route is POST /admin-api/workspaces/bind-target
          // (workspaces_route.py mounts /admin-api/workspaces) — the old
          // /api/v1/workspaces/bind-target path never existed (404).
          const res = await apiCall({
            endpoint: "/admin-api/workspaces/bind-target",
            method: "POST",
            body: { target: "current-workspace", reason: result.reason, otp: result.otpCode },
          });
          onOutput({
            title: "🔐 JIT OTP Bound",
            content: `✅ OTP যাচাই সফল!\nবাইন্ড রেসপন্স:\n${JSON.stringify(res, null, 2)}`,
            kind: "json",
          });
        }
      } catch (e: unknown) {
        onOutput({ title: "JIT OTP Failed", content: String((e as Error)?.message ?? e), kind: "plain" });
      } finally {
        setLoading(false);
        onLoading(false);
      }
    },
    [setLoading]
  );

  return { busy, setLoading, runWithContext, explain, review, securityScan, analyzePerformance, autoHeal, jitAction };
}
