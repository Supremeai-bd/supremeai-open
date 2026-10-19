/**
 * Lightweight context gathering for SupremeAI chat/code actions.
 */

import * as vscode from "vscode";

export interface EditorContext {
  filePath: string;
  language: string;
  selection: string;
  fileContent: string;
}

export function getEditorContext(): EditorContext | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return undefined;
  const doc = editor.document;
  const selection = doc.getText(editor.selection);
  return {
    filePath: vscode.workspace.asRelativePath(doc.uri),
    language: doc.languageId,
    selection: selection.trim(),
    fileContent: doc.getText(),
  };
}

export function buildPrompt(question: string, ctx?: EditorContext): string {
  if (!ctx) return question;
  const parts: string[] = [];
  if (ctx.selection) {
    parts.push(`File: ${ctx.filePath} (${ctx.language})\nSelected code:\n\`\`\`${ctx.language}\n${ctx.selection}\n\`\`\``);
  } else {
    parts.push(`File: ${ctx.filePath} (${ctx.language})`);
  }
  parts.push(`Question: ${question}`);
  return parts.join("\n\n");
}
