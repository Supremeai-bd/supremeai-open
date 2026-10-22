/**
 * SupremeAI Chat Sidebar — WebviewViewProvider for in-editor AI chat.
 *
 * Talks to the SupremeAI Gateway (/v1/chat/completions) using the configured
 * gateway URL and API key. Supports a model selector (auto + individual models).
 */

import * as vscode from "vscode";
import { MODEL_TIERS, tierToModel } from "./models";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export class SupremeAIChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "supremeai.chat";

  private view: vscode.WebviewView | undefined;
  private messages: ChatMessage[] = [];

  constructor(private readonly context: vscode.ExtensionContext) {}

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.context.extensionUri],
    };
    webviewView.webview.html = this.getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (!msg || typeof msg !== "object") return;
      if (msg.type === "send") {
        const text = String(msg.text || "").trim();
        const model = String(msg.model || "auto");
        if (!text) return;
        this.messages.push({ role: "user", content: text });
        this.post({ type: "user", text });
        this.post({ type: "thinking" });
        try {
          const reply = await this.callGateway(text, model);
          this.messages.push({ role: "assistant", content: reply });
          this.post({ type: "assistant", text: reply });
        } catch (err) {
          const e = err instanceof Error ? err.message : String(err);
          this.post({ type: "error", text: e });
        }
      } else if (msg.type === "clear") {
        this.messages = [];
        this.post({ type: "cleared" });
      }
    });
  }

  private async callGateway(userText: string, model: string): Promise<string> {
    const config = vscode.workspace.getConfiguration("supremeai");
    const gatewayUrl = config.get<string>("gatewayUrl", "http://127.0.0.1:8080");
    const apiKey = config.get<string>("apiKey", "") || process.env.SUPREMEAI_API_KEY || "";

    const messages = [...this.messages.filter((m) => m.role === "user" || m.role === "assistant")];
    // ensure last user message present
    if (messages.length === 0 || messages[messages.length - 1].content !== userText) {
      messages.push({ role: "user", content: userText });
    }

    const url = gatewayUrl.replace(/\/$/, "") + "/v1/chat/completions";
    const gatewayModel = tierToModel(model);
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-SupremeAI-Key": apiKey,
      },
      body: JSON.stringify({ model: gatewayModel, messages, stream: false }),
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`Gateway HTTP ${res.status}: ${body.slice(0, 200)}`);
    }
    const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }> };
    const content = data?.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      throw new Error("Gateway returned no content");
    }
    return content;
  }

  private post(payload: unknown): void {
    if (this.view) {
      this.view.webview.postMessage(payload);
    }
  }

  private getHtml(_webview: vscode.Webview): string {
    const nonce = getNonce();
    const csp = `default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';`;
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SupremeAI Chat</title>
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); background: var(--vscode-sideBar-background); margin: 0; display: flex; flex-direction: column; height: 100vh; }
    #toolbar { display: flex; gap: 6px; padding: 8px; border-bottom: 1px solid var(--vscode-panel-border); }
    select { flex: 1; background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground); border: 1px solid var(--vscode-dropdown-border); padding: 4px; }
    button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 4px 8px; cursor: pointer; }
    button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
    #messages { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 8px; }
    .msg { padding: 8px 10px; border-radius: 6px; max-width: 100%; white-space: pre-wrap; word-break: break-word; }
    .msg.user { background: var(--vscode-inputOption-activeBackground); align-self: flex-end; }
    .msg.assistant { background: var(--vscode-editor-inactiveSelectionBackground); align-self: flex-start; }
    .msg.error { background: var(--vscode-inputValidation-errorBackground); color: var(--vscode-errorForeground); }
    .msg.thinking { opacity: 0.6; font-style: italic; }
    #inputbar { display: flex; gap: 6px; padding: 8px; border-top: 1px solid var(--vscode-panel-border); }
    #input { flex: 1; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 6px; resize: none; font-family: inherit; }
  </style>
</head>
<body>
  <div id="toolbar">
    <select id="model">
      ${MODEL_TIERS.map((t, i) => `<option value="${t.id}"${i === 0 ? " selected" : ""}>${t.label}</option>`).join("")}
    </select>
    <button id="clear" class="secondary">Clear</button>
  </div>
  <div id="messages"></div>
  <div id="inputbar">
    <textarea id="input" rows="2" placeholder="Ask SupremeAI..."></textarea>
    <button id="send">Send</button>
  </div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const messages = document.getElementById('messages');
    const input = document.getElementById('input');
    const model = document.getElementById('model');
    const sendBtn = document.getElementById('send');

    function append(cls, text) {
      const div = document.createElement('div');
      div.className = 'msg ' + cls;
      div.textContent = text;
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
      return div;
    }

    function send() {
      const text = input.value.trim();
      if (!text) return;
      vscode.postMessage({ type: 'send', text, model: model.value });
      input.value = '';
    }

    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    document.getElementById('clear').addEventListener('click', () => {
      vscode.postMessage({ type: 'clear' });
    });

    window.addEventListener('message', (event) => {
      const m = event.data;
      if (m.type === 'user') append('user', m.text);
      else if (m.type === 'assistant') append('assistant', m.text);
      else if (m.type === 'error') append('error', 'Error: ' + m.text);
      else if (m.type === 'thinking') append('thinking', 'Thinking...');
      else if (m.type === 'cleared') messages.innerHTML = '';
    });
  </script>
</body>
</html>`;
  }
}

function getNonce(): string {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
