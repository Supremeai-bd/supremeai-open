/**
 * SelfHealingService — Error analysis + auto-patch proposal (platform-agnostic core).
 *
 * VS Code-এ backend থেকে returning fixed code diff view দেখানো হয়;
 * desktop-এ React component দিয়ে। এখানে মূল লজিক (backend call + state machine) রাখা হয়েছে।
 */

import type { SupremeAIService } from './SupremeAIService';
import { HealingStateManager, HealingState } from './HealingStateManager';

export { HealingState } from './HealingStateManager';

export interface SelfHealingPayload {
  filePath: string;
  message: string;
  lineNumber: number;
  codeContext: string;
  languageId: string;
}

export interface SelfHealingFix {
  fixedCode?: string;
  explanation?: string;
}

export interface HealingDiffRender {
  originalUri: { fsPath: string };
  fixedCode: string;
  fileName: string;
}

export class SelfHealingService {
  private static instance: SelfHealingService | null = null;
  private supremeService: SupremeAIService;
  private isHealing = false;

  private constructor(supremeService: SupremeAIService) {
    this.supremeService = supremeService;
  }

  public static initialize(supremeService: SupremeAIService): SelfHealingService {
    if (!SelfHealingService.instance) {
      SelfHealingService.instance = new SelfHealingService(supremeService);
      // eslint-disable-next-line no-console
      console.log('🩺 [Self-Healing] Agent-in-the-Loop initialized.');
    }
    return SelfHealingService.instance;
  }

  public static getInstance(): SelfHealingService | null {
    return SelfHealingService.instance;
  }

  /**
   * একটি এরর + codeContext-এর উপর ভিত্তি করে ফিক্স তৈরি করবে এবং
   * healing state machine কে SUCCESS/FAILED এ নিয়ে যাবে।
   */
  public async healError(payload: SelfHealingPayload): Promise<SelfHealingFix | null> {
    const stateManager = HealingStateManager.getInstance();
    if (this.isHealing) {
      return null;
    }

    this.isHealing = true;
    stateManager.setState(HealingState.ANALYZING_ERROR);

    try {
      const fixResponse = await this.supremeService.resolveError({
        errorType: this.inferErrorType(payload.message),
        errorMessage: payload.message,
        filePath: payload.filePath,
        codeSnippet: payload.codeContext,
        context: `language=${payload.languageId}, line=${payload.lineNumber}`,
      });

      stateManager.setState(HealingState.GENERATING_PATCH);

      if (fixResponse && fixResponse.suggestedFixes && fixResponse.suggestedFixes.length > 0) {
        const best = fixResponse.suggestedFixes[0];
        const fix: SelfHealingFix = { fixedCode: best.code, explanation: best.description };
        stateManager.setState(HealingState.SUCCESS);
        return fix;
      }

      stateManager.setState(HealingState.FAILED, 'No fix returned from backend.');
      return null;
    } catch (err: any) {
      stateManager.setState(HealingState.FAILED, err?.message || 'Unknown healing error');
      return null;
    } finally {
      this.isHealing = false;
    }
  }

  private inferErrorType(message: string): string {
    const m = message.toLowerCase();
    if (m.includes('security') || m.includes('injection') || m.includes('xss')) return 'security';
    if (m.includes('undefined') || m.includes('null') || m.includes('cannot read')) return 'runtime';
    if (m.includes('syntax') || m.includes('unexpected token')) return 'syntax';
    if (m.includes('performance') || m.includes('slow') || m.includes('latency')) return 'performance';
    return 'lint';
  }
}

/**
 * Error-এর চারপাশের semantic block বের করে — platform text document থেকে।
 * (AST না থাকলে fallback: error-line ± 10 লাইন)
 */
export function extractErrorContext(
  document: { getText(): string; lineCount: number; lineAt(l: number): { text: string } },
  errorLine: number
): string {
  const code = document.getText();
  const imports = extractImports(code);
  const lines = code.split('\n');
  const start = Math.max(0, errorLine - 10);
  const end = Math.min(lines.length - 1, errorLine + 10);
  const contextBlock = lines.slice(start, end + 1).join('\n');
  return `// --- FILE IMPORTS ---\n${imports}\n\n// --- ERROR CONTEXT ---\n${contextBlock}`;
}

function extractImports(code: string): string {
  const importRegex = /^(?:import|export|const .*? = require).*?;/gm;
  const matches = code.match(importRegex);
  return matches ? matches.join('\n') : '// No external imports found';
}