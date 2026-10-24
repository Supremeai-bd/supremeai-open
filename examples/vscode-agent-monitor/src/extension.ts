/**
 * extension.ts — vscode glue (issue #333 AC1+AC2).
 *
 * The ONLY module importing 'vscode'. Everything testable lives in the pure
 * modules (statusLogic, resilience, wsTransport). Wiring:
 *   status bar item  <- statusBarView(monitor state)          (AC1)
 *   output channel   <- outputLine(frame) via bounded buffer  (AC2)
 *   reconnecting ws  <- injected WebSocket factory             (AC3)
 *
 * The WebSocket runtime is resolved honestly: global WebSocket if present,
 * else the optional 'ws' package, else the monitor reports "unsupported"
 * and stays idle — it never crashes the extension host.
 */
import * as vscode from "vscode";
import { createRequire } from "node:module";
import { ReconnectingTransport, type WsFactory, type WsLike } from "./wsTransport";
import { BoundedOutputBuffer, ReconnectBackoff } from "./resilience";
import { initialState, outputLine, statusBarView, type MonitorState } from "./statusLogic";

function resolveWsFactory(): { factory: WsFactory; note: string } | null {
  const g = globalThis as { WebSocket?: new (url: string) => WsLike };
  if (typeof g.WebSocket === "function") {
    const Ctor = g.WebSocket;
    return { factory: (url) => new Ctor(url), note: "global WebSocket" };
  }
  try {
    const nodeRequire = createRequire(__filename);
    const Ws = nodeRequire("ws") as (new (url: string) => WsLike) | undefined;
    if (typeof Ws === "function") {
      return { factory: (url) => new Ws(url), note: "ws package" };
    }
  } catch {
    // ws package absent - fall through to unsupported
  }
  return null;
}

export function activate(context: vscode.ExtensionContext): void {
  const statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  const output = vscode.window.createOutputChannel("SupremeAI Agent Monitor");
  const buffer = new BoundedOutputBuffer(2000);
  const state: { monitor: MonitorState } = { monitor: initialState() };

  const render = () => {
    const view = statusBarView(state.monitor);
    statusItem.text = view.text;
    statusItem.tooltip = view.tooltip;
    statusItem.backgroundColor =
      view.status === "error"
        ? new vscode.ThemeColor("statusBarItem.errorBackground")
        : undefined;
  };
  render();

  const cfg = vscode.workspace.getConfiguration("supremeaiAgentMonitor");
  const towerUrl = String(cfg.get("towerUrl") ?? "ws://127.0.0.1:8765");
  const taskFilter = String(cfg.get("taskFilter") ?? "");

  let transport: ReconnectingTransport | null = null;

  const connectCmd = vscode.commands.registerCommand("supremeaiAgentMonitor.connect", () => {
    if (transport) {
      output.appendLine("already running");
      return;
    }
    const resolved = resolveWsFactory();
    if (resolved === null) {
      vscode.window.showWarningMessage(
        "SupremeAI Agent Monitor: no WebSocket runtime available (need global WebSocket or the ws package).",
      );
      return;
    }
    output.appendLine(`connecting to ${towerUrl} via ${resolved.note}`);
    transport = new ReconnectingTransport(towerUrl, resolved.factory, {
      onFrame: (frame, monitor) => {
        state.monitor = monitor;
        render();
        if (taskFilter === "" || frame.task_id === taskFilter || frame.frame_type === "heartbeat") {
          buffer.push(outputLine(frame));
          for (const line of buffer.drain()) output.appendLine(line);
        }
      },
      onOutput: (line) => output.appendLine(line),
      onStatusNote: (note) => output.appendLine(`[transport] ${note}`),
      onResync: (reason) => {
        output.appendLine(`[resync] ${reason} - reconnecting for a fresh seq space`);
      },
    }, new ReconnectBackoff());
    transport.start();
  });

  const disconnectCmd = vscode.commands.registerCommand("supremeaiAgentMonitor.disconnect", () => {
    if (transport) {
      transport.dispose();
      transport = null;
      state.monitor = initialState();
      render();
      output.appendLine("disconnected");
    }
  });

  context.subscriptions.push(statusItem, output, connectCmd, disconnectCmd);
  statusItem.show();
}

export function deactivate(): void {
  // transport disposal is owned by the connect command's closure
}
