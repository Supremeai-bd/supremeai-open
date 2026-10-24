/**
 * Monaco AI Integration — VS Code extension-এর মতো IDE-integrated AI features:
 * 1. Inline Code Completion (Ctrl+Space)
 * 2. Context Menu actions (Explain / Review / Security Scan)
 *
 * VS Code extension-এ `registerInlineCompletionProvider` ও `editor/context` menus
 * এর সমতুল্য। @monaco-editor/react ব্যবহার করার সময় Editor onMount-এ call করা হয়।
 */

import type * as Monaco from "monaco-editor";
import { getSharedServices } from "../../services/supremeShared";

export type MonacoEditor = Monaco.editor.IStandaloneCodeEditor;
export type MonacoInstance = typeof Monaco;

export interface MonacoAiCallbacks {
  /** আউটপুট (Explain/Review ইত্যাদি) দেখানোর জন্য */
  onOutput?: (title: string, content: string) => void;
}

/**
 * Editor-এ inline completion provider + context menu সেটআপ করে।
 * Cleanup ফাংশন return করে (unmount-এ dispose করার জন্য)।
 */
export function setupMonacoAi(
  editor: MonacoEditor,
  monaco: MonacoInstance,
  callbacks: MonacoAiCallbacks = {}
): () => void {
  const getSelectionText = (): string | null => {
    const sel = editor.getSelection();
    const model = editor.getModel();
    if (!sel || !model) return null;
    return model.getValueInRange(sel);
  };

  const runAiAction = async (cmd: string) => {
    const code = getSelectionText();
    if (!code || !code.trim()) {
      callbacks.onOutput?.("SupremeAI", "⚠️ কিছু সিলেক্ট করা হয়নি। এডিটরে কোড সিলেক্ট করুন।");
      return;
    }
    const { service } = getSharedServices();
    const language = editor.getModel()?.getLanguageId() ?? "plaintext";

    try {
      let response = "";
      if (cmd === "explain") {
        response = (
          await service.sendChatMessage({
            message: `Please explain the following ${language} code in detail:\n\n\`\`\`${language}\n${code}\n\`\`\``,
            sessionId: service.getSessionId(),
            context: { source: "desktop", language, timestamp: new Date().toISOString() },
          })
        ).response;
      } else if (cmd === "review") {
        response = (
          await service.sendChatMessage({
            message: `Please review the following ${language} code for bugs, style, and performance:\n\n\`\`\`${language}\n${code}\n\`\`\``,
            sessionId: service.getSessionId(),
            context: { source: "desktop", language, timestamp: new Date().toISOString() },
          })
        ).response;
      } else if (cmd === "security") {
        const issues = await getSharedServices().security.scanCode(code, language);
        response = issues.length
          ? issues.map((i) => `• [${i.severity}] ${i.type}: ${i.description}`).join("\n")
          : "✅ কোনো স্পষ্ট security issue পাওয়া যায়নি।";
      }
      callbacks.onOutput?.(
        cmd === "explain" ? "📘 Explain" : cmd === "review" ? "🛡️ Review" : "🛡️ Security Scan",
        response
      );
    } catch (e: unknown) {
      callbacks.onOutput?.("SupremeAI Error", String((e as Error)?.message ?? e));
    }
  };

  // ---------- Inline Completion (AI predict) ----------
  const inlineProvider = {
    provideInlineCompletions: async (model: Monaco.editor.ITextModel) => {
      try {
        const { service } = getSharedServices();
        const pos = editor.getPosition();
        if (!pos) return { items: [] };
        const lineText = model.getLineContent(pos.lineNumber);
        const before = lineText.slice(0, pos.column - 1).trimEnd();
        // খুব ছোট প্রেক্ষাপটে eager predict না করা — কাস্টম keybinding (Ctrl+Space) ব্যবহার করে
        if (!before || before.length < 8) return { items: [] };

        const startLine = Math.max(1, pos.lineNumber - 5);
        const context = model.getValueInRange({
          startLineNumber: startLine,
          startColumn: 1,
          endLineNumber: pos.lineNumber,
          endColumn: pos.column,
        });
        if (context.length > 4000) return { items: [] };

        const res = await service.sendChatMessage({
          message: `Complete the following ${model.getLanguageId()} code right where it ends. Return ONLY the continuation to append (no markdown, no explanation, no context duplication):\n\n${context}`,
          sessionId: service.getSessionId(),
          context: { source: "desktop", language: model.getLanguageId(), timestamp: new Date().toISOString() },
        });

        let token: string = res.response || "";
        token = token.replace(/^```[a-z]*\s*\n?/, "").replace(/\n?```$/, "").trim();
        if (!token || token.length > 800) {
          return { items: [] };
        }

        return {
          items: [
            {
              insertText: token,
              range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
            },
          ],
        };
      } catch {
        return { items: [] };
      }
    },
    freeInlineCompletions: () => {},
    disposeInlineCompletions: () => {},
  };

  const inlineDisposable = monaco.languages.registerInlineCompletionsProvider("*", inlineProvider);

  // ---------- Context Menu (right-click) ----------
  const disposables: Monaco.IDisposable[] = [inlineDisposable];

  const addContextAction = (label: string, cmd: string, order: number) => {
    disposables.push(
      editor.addAction({
        id: `supremeai-${cmd}`,
        label,
        contextMenuGroupId: "navigation",
        contextMenuOrder: order,
        run: async () => {
          await runAiAction(cmd);
        },
      })
    );
  };

  addContextAction("SupremeAI: Explain Selection", "explain", 1.1);
  addContextAction("SupremeAI: Review Selection", "review", 1.2);
  addContextAction("SupremeAI: Security Scan Selection", "security", 1.3);

  return () => {
    disposables.forEach((d) => d.dispose());
  };
}
