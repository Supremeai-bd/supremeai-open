/**
 * @supremeai/shared-services — Platform-Agnostic SupremeAI core services
 *
 * VS Code extension ও Electron desktop app উভয়ে এই প্যাকেজ থেকে
 * কোর সার্ভিসগুলো শেয়ার করে (DRY)। প্রতিটি প্ল্যাটফর্ম শুধুমাত্র নিজের
 * platform adapter inject করে।
 */

// ---------- Types ----------
export * from './types';

// ---------- Platform abstraction ----------
export {
  TinyEventEmitter,
  type PlatformLogger,
  type PlatformNotification,
  type PlatformPrompt,
  type PlatformSecretStorage,
  type PlatformWorkspace,
  type PlatformTextDocument,
  type PlatformEditor,
} from './platform';

// ---------- Core services ----------
export { SupremeAIService, getSupremeAIService, setSupremeAIService, type TokenProvider } from './services/SupremeAIService';
export {
  SupremeExtensionBridge,
  getApiBridge,
  type EvolveCodeResult,
  type BridgeRequestOptions,
  type BridgeTokenSource,
  type UnauthorizedHandler,
} from './services/apiBridge';
export { ScopeGuardService, PermissionScope } from './services/ScopeGuardService';
export { SecurityScanner, type SecurityIssueV2 } from './services/SecurityScanner';
export { PerformanceMonitor, type PerformanceInsight } from './services/PerformanceMonitor';
export { HealingStateManager, HealingState, type HealingStateEvent } from './services/HealingStateManager';
export {
  SelfHealingService,
  extractErrorContext,
  type SelfHealingPayload,
  type SelfHealingFix,
} from './services/SelfHealingService';
export {
  TelemetryTracker,
  type PatchTelemetry,
  type PatchAcceptance,
} from './services/TelemetryTracker';
export { CrossAiObserverService } from './services/CrossAiObserverService';

// ---------- Realtime services ----------
export { BaseWebSocketManager, type BaseWebSocketManagerOptions, type WsStatus } from './realtime/BaseWebSocketManager';

// ---------- Canonical HTTP transport (DRY Phase 1-B2) ----------
// একক transport primitive: timeout + exponential retry + auth injection +
// normalized HttpError। নতুন fetch wrapper লেখার আগে এটাই ব্যবহার করতে হবে।
export {
  buildUrl,
  createHttpClient,
  type HttpClient,
  type HttpClientConfig,
  type HttpError,
  type HttpMethod,
  type HttpRequestOptions,
} from './http/canonical-http';

// ---------- UI helpers ----------
export { promptForOtp, isValidOtp, type JitOtpResult } from './ui/JitOtpDialog';

// ---------- Platform adapters (browser-safe: শুধুমাত্র Electron) ----------
// গুরুত্বপূর্ণ: `platform/vscode.ts` এখানে export করা হয় না — কারণ সেটা `vscode`
// মডিউল import করে, যা browser/Electron renderer এ রেজলভ হয় না।
// VS Code এক্সটেনশন: `import { ... } from '@supremeai/shared-services/vscode'`। 
export * from './platform/electron';