/**
 * SupremeAI VS Code Extension - Main Entry Point
 * Real-time learning and AI assistance integration
 */

import * as vscode from 'vscode';
import { SupremeAIService, setSupremeAIService } from './services/SupremeAIService';
import { AuthService } from './services/AuthService';
import { AuthHandler } from './handlers/AuthHandler';
import { CodeEditHandler } from './handlers/CodeEditHandler';
import { ErrorHandler } from './handlers/ErrorHandler';
import { FeedbackHandler } from './handlers/FeedbackHandler';
import { CodeFlowHandler, setCodeFlowHandler } from './handlers/CodeFlowHandler';
import { SupremeAIConfig } from './types';
import { SupremeAISidebarProvider } from './providers/SupremeAISidebarProvider';
import { SupremeAIActivityProvider } from './providers/SupremeAIActivityProvider';
import { SupremeAIChatProvider } from './providers/SupremeAIChatProvider';
import { SupremeAIAdminDashboardProvider } from './providers/SupremeAIAdminDashboardProvider';
import { SupremeAICustomerDashboardProvider } from './providers/SupremeAICustomerDashboardProvider';
import { StreamingChatProvider } from './providers/StreamingChatProvider';
import { CodeFlowPanel } from './providers/CodeFlowPanel';
import { AIService, getAIService, setAIService } from './ai/AIService';
import { CodeGenerationService, getCodeGenerationService, setCodeGenerationService } from './ai/CodeGenerationService';
import { CodeReviewService, getCodeReviewService, setCodeReviewService } from './ai/CodeReviewService';
import { detectOtherAiAgents } from './agentDetector'; // এজেন্ট ডিটেক্টর ইম্পোর্ট করা হলো
import { SupremeWebviewProvider } from './providers/SupremeWebviewProvider';
import { CrossAiObserverService } from '@supremeai/shared-services';
import { registerSwarmCommands } from './services/SwarmPipelineProvider';
import { SelfHealingService } from '@supremeai/shared-services';
import { BrowserPreviewProvider } from './providers/BrowserPreviewProvider';
import { VsCodePlatformAdapter } from './adapters/VsCodePlatformAdapter';
// New imports for enhanced features
import { DependencyGraphProvider } from './providers/DependencyGraphProvider';
import { VisualizationHandler } from './handlers/VisualizationHandler';
import { EnhancedAIService } from './ai/EnhancedAIService';
import { SecurityScanner } from '@supremeai/shared-services';
import { PerformanceMonitor } from './performance/PerformanceMonitor';

let supremeAIService: SupremeAIService;
let aiService: AIService;
let codeGenService: CodeGenerationService;
let codeReviewService: CodeReviewService;
let codeFlowHandler: CodeFlowHandler;
// New service instances - initialized lazily
let visualizationHandler: VisualizationHandler;
let enhancedAIService: EnhancedAIService;
let securityScanner: SecurityScanner;
let performanceMonitor: PerformanceMonitor;

// Track initialization status to prevent duplicate initializations
let isInitialized = false;

function escapeHtml(value: string): string {
  return String(value).replace(/[&<>"']/g, (c) => {
    switch (c) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case '\'':
        return '&#39;';
      default:
        return c;
    }
  });
}

export async function activate(context: vscode.ExtensionContext) {
  console.log('[SupremeAI] VS Code Extension activating...');

  if (isInitialized) {
    console.log('[SupremeAI] Extension already initialized, skipping duplicate activation');
    return;
  }

  // Initialize services lazily and only when needed
  const config = vscode.workspace.getConfiguration('supremeai');
  const backendUrl = config.get<string>('backendUrl', 'https://supremeai-worker.paykaribazaronline.workers.dev');

  const supremeConfig: SupremeAIConfig = {
    backendUrl,
    enableRealTimeLearning: config.get<boolean>('enableRealTimeLearning', true),
    autoReportErrors: config.get<boolean>('autoReportErrors', true),
  };

  const platformAdapter = new VsCodePlatformAdapter();
  supremeAIService = new SupremeAIService({
    ...supremeConfig,
    tokenProvider: platformAdapter,
    platformContext: platformAdapter.getContext(),
  } as any);
  setSupremeAIService(supremeAIService);

  // Initialize core services only when needed
  aiService = getAIService();
  setAIService(aiService);

  codeGenService = new CodeGenerationService();
  setCodeGenerationService(codeGenService);

  codeReviewService = new CodeReviewService();
  setCodeReviewService(codeReviewService);

  // Only initialize heavy services when user performs actions
  // Don't initialize CrossAiObserverService and SelfHealingService at startup to reduce resource usage

  // Initialize authentication — NON-BLOCKING (fire-and-forget with timeout)
  // ⚠️ Do NOT await these — Render backend cold start can take 60+ seconds
  const auth = AuthService.getInstance(supremeConfig, context.secrets);
  Promise.race([
    auth.initialize().then(() => auth.loginAsGuest()),
    new Promise<void>(resolve => setTimeout(resolve, 5000)) // 5s timeout
  ]).catch(err => {
    console.warn('[SupremeAI] Auth init warning (non-critical):', err);
  });

  // Register URI handler for OAuth callback
  AuthHandler.registerAuthCallback(context);

  // Initialize handlers
  const editHandler = new CodeEditHandler(context);
  const errHandler = new ErrorHandler(context);
  const fbHandler = new FeedbackHandler(context);
  codeFlowHandler = new CodeFlowHandler(context);
  setCodeFlowHandler(codeFlowHandler);

  editHandler.register();
  errHandler.register();
  fbHandler.register();
  codeFlowHandler.register();

  // Register only essential providers initially
  registerChatProvider(context);
  registerInlineCompletionProvider(context, fbHandler);
  registerStatusBar(context);

  // Register recipe provider
  const recipeProvider = new SupremeWebviewProvider(context.extensionUri);
  context.subscriptions.push(
      vscode.window.registerWebviewViewProvider(SupremeWebviewProvider.viewType, recipeProvider)
  );

  // Register commands for additional features (only initialize services when commands are used)
  registerCommands(context);

  // Swarm Intelligence: dynamically detect Gemini/Kilo/Cline + other AI agents
  // and expose the collective-intelligence pipeline command.
  registerSwarmCommands(context);

  // Auto-focus SupremeAI Chat panel on startup so user does not need to open it manually
  setTimeout(() => {
    vscode.commands.executeCommand('supremeaiChat.focus');
  }, 1500);

  // Show lightweight activation message
  console.log('[SupremeAI] Extension activated with essential services only');

  // Only run agent detection if needed (maybe on demand)
  if (config.get<boolean>('enableAgentDetection', false)) {
    // Run agent detection after a delay to avoid blocking activation
    setTimeout(() => {
      const agents = detectOtherAiAgents();
      if (agents.length > 0) {
        supremeAIService.sendCodeAnalysis('env-discovery', `Detected AI Agents in environment: ${agents.join(', ')}`, 'system-meta');
      }
    }, 5000); // Delay by 5 seconds to not impact startup
  }

  isInitialized = true;
}

function registerCommands(context: vscode.ExtensionContext): void {
  // Register commands that initialize services only when called
  const forceLearnCommand = vscode.commands.registerCommand('supremeai.forceLearn', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to learn from');
      return;
    }

    const document = editor.document;
    const code = document.getText();
    const language = document.languageId;

    try {
      await supremeAIService.sendCodeAnalysis(document.fileName, code, language);
      vscode.window.showInformationMessage('Code analysis sent for learning');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      vscode.window.showErrorMessage(`Failed to send code analysis: ${message}`);
    }
  });

  const explainCodeCommand = vscode.commands.registerCommand('supremeai.aiExplain', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor selected.');
      return;
    }
    const selection = editor.selection;
    const text = selection.isEmpty ? editor.document.getText() : editor.document.getText(selection);
    if (!text.trim()) {
      vscode.window.showWarningMessage('No code selected to explain.');
      return;
    }

    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Explaining Code...',
      cancellable: false
    }, async () => {
      try {
        const response = await supremeAIService.sendChatMessage({
          message: `Please explain the following code in detail:\n\n\`\`\`${editor.document.languageId}\n${text}\n\`\`\``,
          sessionId: supremeAIService.getSessionId()
        });
        const panel = vscode.window.createWebviewPanel(
          'supremeaiExplanation',
          'Code Explanation',
          vscode.ViewColumn.Two,
          {}
        );
        panel.webview.html = `<html><body><pre style="white-space: pre-wrap; font-family: sans-serif; padding: 15px;">${escapeHtml(response.response)}</pre></body></html>`;
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to explain code: ${error}`);
      }
    });
  });

  const reviewCodeCommand = vscode.commands.registerCommand('supremeai.aiReview', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor selected.');
      return;
    }
    const selection = editor.selection;
    const text = selection.isEmpty ? editor.document.getText() : editor.document.getText(selection);
    if (!text.trim()) {
      vscode.window.showWarningMessage('No code selected to review.');
      return;
    }

    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Reviewing Code...',
      cancellable: false
    }, async () => {
      try {
        const response = await supremeAIService.sendChatMessage({
          message: `Please review the following code for bugs, style issues, and performance optimizations:\n\n\`\`\`${editor.document.languageId}\n${text}\n\`\`\``,
          sessionId: supremeAIService.getSessionId()
        });
        const panel = vscode.window.createWebviewPanel(
          'supremeaiReview',
          'Code Review',
          vscode.ViewColumn.Two,
          {}
        );
        panel.webview.html = `<html><body><pre style="white-space: pre-wrap; font-family: sans-serif; padding: 15px;">${escapeHtml(response.response)}</pre></body></html>`;
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to review code: ${error}`);
      }
    });
  });

  const loginAsGuestCommand = vscode.commands.registerCommand('supremeai.loginAsGuest', async () => {
    const auth = AuthService.getInstance();
    if (auth) {
      await auth.loginAsGuest();
    }
  });

  const loginCommand = vscode.commands.registerCommand('supremeai.login', async () => {
    const auth = AuthService.getInstance();
    if (auth) {
      await auth.login();
    }
  });

  const logoutCommand = vscode.commands.registerCommand('supremeai.logout', async () => {
    const auth = AuthService.getInstance();
    if (auth) {
      await auth.logout();
    }
  });

  // Add new commands for enhanced features - initialize services only when needed
  const generateCodeCommand = vscode.commands.registerCommand('supremeai.generateCode', async () => {
    // Initialize enhanced AI service only when needed
    if (!enhancedAIService) {
      enhancedAIService = new EnhancedAIService(supremeAIService);
    }
    
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor selected.');
      return;
    }
    
    const selection = editor.selection;
    const text = selection.isEmpty ? editor.document.getText() : editor.document.getText(selection);
    if (!text.trim()) {
      vscode.window.showWarningMessage('No code selected.');
      return;
    }

    const requirement = await vscode.window.showInputBox({
      prompt: 'Enter code generation requirements:'
    });
    
    if (!requirement) return;

    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Generating Code...',
      cancellable: false
    }, async () => {
      try {
        const generatedCode = await enhancedAIService.generateCode(text, requirement);
        const panel = vscode.window.createWebviewPanel(
          'supremeaiGeneratedCode',
          'Generated Code',
          vscode.ViewColumn.Two,
          {}
        );
        panel.webview.html = `<html><body><pre style="white-space: pre-wrap; font-family: sans-serif; padding: 15px;">${escapeHtml(generatedCode)}</pre></body></html>`;
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to generate code: ${error}`);
      }
    });
  });

  const suggestRefactoringCommand = vscode.commands.registerCommand('supremeai.suggestRefactoring', async () => {
    // Initialize enhanced AI service only when needed
    if (!enhancedAIService) {
      enhancedAIService = new EnhancedAIService(supremeAIService);
    }
    
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor selected.');
      return;
    }
    const selection = editor.selection;
    const text = selection.isEmpty ? editor.document.getText() : editor.document.getText(selection);
    if (!text.trim()) {
      vscode.window.showWarningMessage('No code selected.');
      return;
    }

    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Analyzing Refactoring Options...',
      cancellable: false
    }, async () => {
      try {
        const suggestions = await enhancedAIService.suggestRefactoring(text, editor.document.languageId);
        const panel = vscode.window.createWebviewPanel(
          'supremeaiRefactoringSuggestions',
          'Refactoring Suggestions',
          vscode.ViewColumn.Two,
          {}
        );
        const suggestionsHtml = suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join('');
        panel.webview.html = `<html><body><ul>${suggestionsHtml}</ul></body></html>`;
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to suggest refactoring: ${error}`);
      }
    });
  });

  const performSecurityScanCommand = vscode.commands.registerCommand('supremeai.performSecurityScan', async () => {
    // Initialize security scanner only when needed
    if (!securityScanner) {
      securityScanner = new SecurityScanner(supremeAIService);
    }
    
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor selected.');
      return;
    }

    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Performing Security Scan...',
      cancellable: false
    }, async () => {
      try {
        const issues = await securityScanner.scanCode(editor.document.getText(), editor.document.languageId, editor.document.fileName);
        if (issues.length === 0) {
          vscode.window.showInformationMessage('No security issues found.');
        } else {
          const panel = vscode.window.createWebviewPanel(
            'supremeaiSecurityIssues',
            'Security Issues Found',
            vscode.ViewColumn.Two,
            {}
          );
          const issuesHtml = issues.map((i: any) => `<li><strong>${i.severity.toUpperCase()}:</strong> ${escapeHtml(i.description)}</li>`).join('');
          panel.webview.html = `<html><body><h3>Security Issues Found:</h3><ul>${issuesHtml}</ul></body></html>`;
        }
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to perform security scan: ${error}`);
      }
    });
  });

  const analyzePerformanceCommand = vscode.commands.registerCommand('supremeai.analyzePerformance', async () => {
    // Initialize performance monitor only when needed
    if (!performanceMonitor) {
      performanceMonitor = new PerformanceMonitor(supremeAIService);
    }
    
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor selected.');
      return;
    }
    const selection = editor.selection;
    const text = selection.isEmpty ? editor.document.getText() : editor.document.getText(selection);
    if (!text.trim()) {
      vscode.window.showWarningMessage('No code selected.');
      return;
    }

    vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: 'Analyzing Performance...',
      cancellable: false
    }, async () => {
      try {
        const insights = await performanceMonitor.analyzePerformance(text, editor.document.languageId);
        const panel = vscode.window.createWebviewPanel(
          'supremeaiPerformanceInsights',
          'Performance Insights',
          vscode.ViewColumn.Two,
          {}
        );
        panel.webview.html = `<html><body><pre style="white-space: pre-wrap; font-family: sans-serif; padding: 15px;">${escapeHtml(JSON.stringify(insights, null, 2))}</pre></body></html>`;
      } catch (error) {
        vscode.window.showErrorMessage(`Failed to analyze performance: ${error}`);
      }
    });
  });

  // Command to show dependency graph - initialize provider when needed
  const showDependencyGraphCommand = vscode.commands.registerCommand('supremeai.showDependencyGraph', async () => {
    // Create and show dependency graph view
    const providers = vscode.window.visibleTextEditors;
    if (providers.length > 0) {
      await vscode.commands.executeCommand('supremeaiDependencyGraph.focus');
    } else {
      // Fallback: show a message
      vscode.window.showInformationMessage('Dependency Graph view is registered in the sidebar.');
    }
  });

  // Register openChat command for status bar click
  const openChatCommand = vscode.commands.registerCommand('supremeai.openChat', () => {
    vscode.commands.executeCommand('workbench.view.extension.supremeai-sidebar');
    vscode.commands.executeCommand('supremeaiChat.focus');
  });

  // Register analyzeCodeFlow command to trigger CodeFlow analysis
  const analyzeCodeFlowCommand = vscode.commands.registerCommand('supremeai.analyzeCodeFlow', () => {
    if (codeFlowHandler) {
      codeFlowHandler.analyzeCodeFlow();
    }
  });

  // Register visualization handler only when needed
  const visualizationCommand = vscode.commands.registerCommand('supremeai.visualizeCode', async () => {
    if (!visualizationHandler) {
      visualizationHandler = new VisualizationHandler(context, supremeAIService);
      visualizationHandler.register();
    }
    // Execute visualization command
  });

  // Register remaining commands declared in package.json so their buttons work
  const aiCompleteCommand = vscode.commands.registerCommand('supremeai.aiComplete', async () => {
    vscode.window.showInformationMessage('AI Code Completion is provided inline as you type. Just keep typing and suggestions appear automatically.');
  });

  const createProjectCommand = vscode.commands.registerCommand('supremeai.createProject', async () => {
    const name = await vscode.window.showInputBox({ prompt: 'Enter the new project name:' });
    if (!name) {
      return;
    }
    vscode.window.showInformationMessage(`Project creation ("${name}") is managed from the SupremeAI Web Dashboard. Open Settings to configure your backend.`);
  });

  const openExtensionSettingsCommand = vscode.commands.registerCommand('supremeai.openExtensionSettings', () => {
    vscode.commands.executeCommand('workbench.action.openSettings', '@ext:supremeai.supremeai-vscode');
  });

  const reportErrorCommand = vscode.commands.registerCommand('supremeai.reportError', async () => {
    try {
      const errorText = await vscode.window.showInputBox({ prompt: 'Describe the error you want to report:' });
      if (!errorText) {
        return;
      }
      const editor = vscode.window.activeTextEditor;
      await supremeAIService.reportError({
        errorType: 'runtime',
        errorMessage: errorText,
        filePath: editor?.document.fileName ?? 'unknown',
        lineNumber: editor ? editor.selection.active.line + 1 : 0,
        severity: 'info',
        timestamp: new Date().toISOString(),
      });
      vscode.window.showInformationMessage('Error reported to SupremeAI. Thank you!');
    } catch (error) {
      vscode.window.showErrorMessage(`Failed to report error: ${error}`);
    }
  });

  const viewHistoryCommand = vscode.commands.registerCommand('supremeai.viewHistory', () => {
    vscode.window.showInformationMessage('Learning history is available in the SupremeAI Chat panel and Web Dashboard.');
  });

  context.subscriptions.push(
    forceLearnCommand,
    explainCodeCommand,
    reviewCodeCommand,
    loginAsGuestCommand,
    loginCommand,
    logoutCommand,
    generateCodeCommand,
    suggestRefactoringCommand,
    performSecurityScanCommand,
    analyzePerformanceCommand,
    showDependencyGraphCommand,
    visualizationCommand,
    openChatCommand,
    analyzeCodeFlowCommand,
    aiCompleteCommand,
    createProjectCommand,
    openExtensionSettingsCommand,
    reportErrorCommand,
    viewHistoryCommand
  );
}

function registerChatProvider(context: vscode.ExtensionContext): void {
  const chatProvider = new SupremeAIChatProvider(context);
  const adminDashboardProvider = new SupremeAIAdminDashboardProvider(context.extensionUri);
  const customerDashboardProvider = new SupremeAICustomerDashboardProvider(context.extensionUri);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('supremeaiChat', chatProvider),
    vscode.window.registerWebviewViewProvider('supremeaiAdminDashboard', adminDashboardProvider),
    vscode.window.registerWebviewViewProvider('supremeaiCustomerDashboard', customerDashboardProvider),
    vscode.commands.registerCommand('supremeai.sendMessageToChat', (message?: string) => {
      let finalMessage = message;
      if (!finalMessage) {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
          const selection = editor.selection;
          const text = editor.document.getText(selection);
          if (text) {
            finalMessage = `Please check this code:\n\n\`\`\`${editor.document.languageId}\n${text}\n\`\`\``;
          }
        }
      }
      if (finalMessage) {
        chatProvider.postMessageToChat(finalMessage);
      } else {
        vscode.window.showWarningMessage('No message or selection found to send to chat.');
      }
    })
  );
}

function registerStatusBar(context: vscode.ExtensionContext): void {
  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = '$(brain) SupremeAI';
  statusBarItem.tooltip = 'SupremeAI Assistant (Chat)';
  statusBarItem.command = 'supremeai.openChat'; // স্ট্যাটাস বার ক্লিক করলে চ্যাট ট্যাব খুলবে
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);
}

function registerInlineCompletionProvider(context: vscode.ExtensionContext, fbHandler: FeedbackHandler): void {
  let debounceTimeout: NodeJS.Timeout | undefined;

  // Check if real-time learning is enabled before registering the provider
  const config = vscode.workspace.getConfiguration('supremeai');
  const enableRealTimeLearning = config.get<boolean>('enableRealTimeLearning', true);
  if (!enableRealTimeLearning) {
    console.log('[SupremeAI] Real-time learning disabled, skipping inline completion provider');
    return;
  }

  const provider: vscode.InlineCompletionItemProvider = {
    async provideInlineCompletionItems(
      document: vscode.TextDocument,
      position: vscode.Position,
      context: vscode.InlineCompletionContext,
      token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionList | vscode.InlineCompletionItem[] | undefined> {

      // Use a longer debounce to reduce resource usage
      const debounceDelay = config.get<number>('inlineCompletionDebounce', 800); // Default to 800ms instead of 400ms
      
      if (debounceTimeout) {
        clearTimeout(debounceTimeout);
      }

      return new Promise<vscode.InlineCompletionList | undefined>((resolve) => {
        debounceTimeout = setTimeout(async () => {
          if (token.isCancellationRequested) {
            resolve(undefined);
            return;
          }

          // Check again if real-time learning is enabled
          const currentConfig = vscode.workspace.getConfiguration('supremeai');
          const currentEnableRealTimeLearning = currentConfig.get<boolean>('enableRealTimeLearning', true);
          if (!currentEnableRealTimeLearning) {
            resolve(undefined);
            return;
          }

          try {
            const docText = document.getText();
            const offset = document.offsetAt(position);
            const prefix = docText.substring(0, offset);
            const suffix = docText.substring(offset);

            const response = await supremeAIService.getInlineCompletions(
              prefix,
              suffix,
              document.fileName,
              document.languageId
            );

            if (token.isCancellationRequested) {
              resolve(undefined);
              return;
            }

            if (!response.suggestions || response.suggestions.length === 0) {
              resolve(undefined);
              return;
            }

            const items: vscode.InlineCompletionItem[] = response.suggestions.map((text: string) => {
              const item = new vscode.InlineCompletionItem(text);
              const suggestionId = `inline-${Date.now()}`;

              fbHandler.captureSuggestionContext(
                suggestionId,
                `completion-${Date.now()}`,
                '',
                text,
                `File: ${document.uri.fsPath}`,
                position
              );

              item.command = {
                title: 'Accept Suggestion',
                command: 'supremeai.acceptSuggestion',
                arguments: [document.fileName, text, document.languageId]
              };
              return item;
            });

            resolve({ items });
          } catch (error) {
            console.error('[SupremeAI] Error fetching inline completion:', error);
            resolve(undefined);
          }
        }, debounceDelay);
      });
    }
  };

  const disposable = vscode.languages.registerInlineCompletionItemProvider(
    { pattern: '**' },
    provider
  );
  context.subscriptions.push(disposable);
  console.log('[SupremeAI] InlineCompletionItemProvider registered with optimized debounce');
}

export function deactivate() {
  console.log('[SupremeAI] VS Code Extension deactivating...');
  isInitialized = false;
  // Clear any pending timeouts
  // Note: We can't access debounceTimeout from here, but the extension lifecycle will clean up resources
}