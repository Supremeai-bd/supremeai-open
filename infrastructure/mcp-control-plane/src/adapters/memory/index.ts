/**
 * Memory Sub-Adapter — bridges the Python Memory MCP Server into the
 * Control Tower as an internal sidecar over STDIO.
 *
 * - Law #9 (MCP Is Universal Interface): real MCP protocol via
 *   Client + StdioClientTransport — NOT raw HTTP fetch.
 * - 100% dynamic: discovers Python tools via listTools(), exposes ALL
 *   under the memory.* prefix. New Python tools = zero TS changes.
 * - Graceful degradation: failures return clear retry message.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
function defaultBackendDir(): string {
  return path.resolve(__dirname, "..", "..", "..", "..", "..", "backend");
}

/**
 * (#2612) Does a backend dir actually contain the sidecar entry file?
 * বাংলা মন্তব্য: অস্তিত্বহীন পাথে spawn করলে Node ভুয়া "spawn <cmd> ENOENT"
 * দেখায় (uv /usr/local/bin-এ থাকা সত্ত্বেও) — কারণ spawn-cwd অস্তিত্বহীন
 * হলে ENOENT কমান্ডের ঘাড়ে চাপানো হয়। আগে-ই চেক করলে সৎ ডায়াগনস্টিক সম্ভব।
 */
export function sidecarEntryExists(backendDir: string): boolean {
  try {
    fs.accessSync(path.join(backendDir, "memory", "mcp_server.py"), fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * (#2612) Resolve the backend dir with layout-default fallback.
 * env-নির্দেশিত পাথে sidecar-ইন্ট্রি না থাকলে (classic misconfig) —
 * defaultBackendDir()-এ ফলব্যাক (fallback-ও না থাকলে caller সৎ এরর দেখাবে)।
 * Returns the resolved dir + whether the env value was abandoned.
 */
export function resolveBackendDir(
  rawDir: string | undefined,
  existsFn: (dir: string) => boolean = sidecarEntryExists,
): { backendDir: string; fellBack: boolean } {
  const envDir = rawDir && rawDir.length > 0 ? rawDir : "";
  if (!envDir) return { backendDir: defaultBackendDir(), fellBack: false };
  if (existsFn(envDir)) return { backendDir: envDir, fellBack: false };
  const fallback = defaultBackendDir();
  if (existsFn(fallback)) return { backendDir: fallback, fellBack: true };
  return { backendDir: envDir, fellBack: false };
}

/**
 * Resolve how to launch the Python sidecar.
 * 1. Existing `.venv` interpreter inside backend/ (fast — no uv sync).
 * 2. Fallback: `uv run --directory <backendDir> python ...` (matches mcp.json).
 */
function resolvePythonLaunch(backendDir: string): { command: string; args: string[] } {
  const venvPython = process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");
  try {
    fs.accessSync(venvPython, fs.constants.X_OK);
    return { command: venvPython, args: ["memory/mcp_server.py"] };
  } catch {
    const uv = process.platform === "win32" ? "uv.exe" : "uv";
    return { command: uv, args: ["run", "--directory", backendDir, "python", "memory/mcp_server.py"] };
  }
}

export interface MemoryToolDescriptor {
  name: string;
  description?: string;
  inputSchema: unknown;
}

export class MemorySubAdapter {
  private client: Client | null = null;
  private starting: Promise<void> | null = null;
  private toolsCache: MemoryToolDescriptor[] | null = null;
  private toolsCacheAt = 0;
  private lastError: string | null = null;
  private startAttempts = 0;
  /** (#2612) টেস্ট-ইনজেকশন পয়েন্ট — প্রোডাকশনে sidecarEntryExists */
  private readonly existsCheck: (dir: string) => boolean;

  constructor(existsCheck?: (dir: string) => boolean) {
    this.existsCheck = existsCheck ?? sidecarEntryExists;
  }

  get lastFailure(): string | null { return this.lastError; }
  get isReady(): boolean { return this.client !== null; }
  get attemptCount(): number { return this.startAttempts; }

  async start(): Promise<void> {
    if (this.client) return;
    if (this.starting) return this.starting;
    this.starting = this.doStart().finally(() => { this.starting = null; });
    return this.starting;
  }

  private async doStart(): Promise<void> {
    this.startAttempts += 1;
    const rawDir = process.env["SUPREMEAI_BACKEND_DIR"];
    // (#2612) env-নির্দেশিত পাথে sidecar-ইন্ট্রি না থাকলে layout-default-এ
    // ফলব্যাক — আগে অস্তিত্বহীন cwd (/backend) নিয়ে spawn হতো, Node তখন
    // ভুয়া "spawn uv ENOENT" দেখাত (লাইভ প্রমাণ: 81 বার start attempt)।
    const { backendDir, fellBack } = resolveBackendDir(rawDir, this.existsCheck);
    if (fellBack) {
      console.error(
        `[Memory Sidecar] SUPREMEAI_BACKEND_DIR="${rawDir}" has no memory/mcp_server.py — fell back to ${backendDir} (#2612)`,
      );
    }
    if (!this.existsCheck(backendDir)) {
      this.lastError =
        `memory sidecar backend not found: ${backendDir}/memory/mcp_server.py does not exist ` +
        `(SUPREMEAI_BACKEND_DIR=${rawDir ?? "<unset>"}; layout default=${defaultBackendDir()}). ` +
        "Set SUPREMEAI_BACKEND_DIR to a real backend/ checkout or bake it into the image (#2612).";
      this.client = null;
      console.error("[Memory Sidecar] Not starting:", this.lastError);
      return;
    }
    const childEnv: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) {
      if (typeof v === "string") childEnv[k] = v;
    }
    childEnv["MEMORY_MCP_TRANSPORT"] = "stdio";
    const launch = resolvePythonLaunch(backendDir);
    try {
      const transport = new StdioClientTransport({
        command: launch.command,
        args: launch.args,
        env: childEnv,
        stderr: "pipe",
        cwd: backendDir,
      });
      const client = new Client(
        { name: "supremeai-control-tower-memory-bridge", version: "1.0.0" },
        { capabilities: {} },
      );
      await client.connect(transport);
      this.client = client;
      this.lastError = null;
      this.toolsCache = null;
      console.error("[Memory Sidecar] Python memory server connected (stdio).");
    } catch (err) {
      const msg = (err as Error)?.message ?? String(err);
      // Issue #1441: a bare "spawn uv ENOENT" masked which launcher was tried.
      // Surface the resolved command plus an actionable hint.
      const prefix = `launch "${launch.command} ${launch.args.join(" ")}" failed`;
      this.lastError = msg.includes("ENOENT")
        ? `${prefix} (ENOENT — launcher missing on PATH; Render builds must provision backend/.venv, see render.yaml buildCommand): ${msg}`
        : `${prefix}: ${msg}`;
      this.client = null;
      console.error("[Memory Sidecar] Failed to start:", this.lastError);
    }
  }

  async stop(): Promise<void> {
    const c = this.client;
    this.client = null;
    this.toolsCache = null;
    if (c) {
      try {
        // Race close against a timeout — child-process teardown on
        // Windows can hang; never block gateway shutdown on it.
        await Promise.race([
          c.close(),
          new Promise((resolve) => setTimeout(resolve, 3000)),
        ]);
      } catch { /* ignore */ }
    }
  }

  async listTools(): Promise<MemoryToolDescriptor[]> {
    await this.start();
    if (!this.client) return [];
    const now = Date.now();
    if (this.toolsCache && now - this.toolsCacheAt < 60_000) return this.toolsCache;
    try {
      const result = await this.client.listTools();
      this.toolsCache = (result.tools ?? []).map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema,
      }));
      this.toolsCacheAt = now;
      this.lastError = null;
      return this.toolsCache;
    } catch (err) {
      this.lastError = (err as Error)?.message ?? String(err);
      await this.stop();
      return [];
    }
  }

  async callTool(
    name: string,
    args: Record<string, unknown>,
  ): Promise<{ ok: boolean; data?: unknown; error?: string; transient?: boolean }> {
    await this.start();
    if (!this.client) {
      const enoent = (this.lastError ?? "").includes("ENOENT");
      return {
        ok: false, transient: !enoent,
        error: enoent
          ? // Honest failure: this deployment bundles no Python runtime/uv and no
            // backend/ directory, so the memory sidecar can never spawn here.
            // The mission-control console keeps its own local memory store, so
            // operator memory workflows remain functional end-to-end.
            "Memory sidecar unavailable — no Python runtime in this deployment (spawn failed: " +
            (this.lastError ?? "ENOENT") + "). Console memory stays on its local store."
          : "Memory service unavailable/startup in progress (" +
            (this.lastError ?? "spawning Python sidecar") + "). Retry in a few seconds.",
      };
    }
    try {
      const result = await this.client.callTool({ name, arguments: args ?? {} });
      this.lastError = null;
      const content = (result as unknown as { content?: unknown }).content;
      if (Array.isArray(content)) {
        const texts = content
          .filter((c): c is { type: string; text: string } =>
            typeof c === "object" && c !== null &&
            (c as { type?: unknown }).type === "text" &&
            typeof (c as { text?: unknown }).text === "string")
          .map((c) => c.text);
        if (texts.length > 0) {
          const joined = texts.join("\n");
          try { return { ok: true, data: JSON.parse(joined) }; }
          catch { return { ok: true, data: joined }; }
        }
      }
      const structured = (result as unknown as { structuredContent?: unknown }).structuredContent;
      return { ok: true, data: structured ?? result };
    } catch (err) {
      const message = (err as Error)?.message ?? String(err);
      this.lastError = message;
      await this.stop();
      return { ok: false, transient: true, error: "Memory service error: " + message };
    }
  }
}
