/**
 * SupremeAI Service — Platform-Agnostic Backend Communication Core
 *
 * VS Code extension ও Electron desktop app দুটোই এই একই সার্ভিস ব্যবহার করে
 * SupremeAI backend-এর সাথে কথা বলে।
 *
 * বাংলা নোট: VS Code-এর পুরনো ভার্সনে `vscode` import ছিল — এখানে সেটা বাদ দিয়ে
 * ইনজেক্টেড platform adapter + token provider ব্যবহার করা হয়েছে, ফলে এই ক্লাসটি
 * সরাসরি desktop/web/VS Code যেকোনো জায়গায় চলে।
 */

import axios from 'axios';
import type { AxiosInstance } from 'axios';
import type {
  SupremeAIConfig,
  LearningUpload,
  LearningResponse,
  CodeEdit,
  ErrorReport,
  SuggestionFeedback,
  ChatRequest,
  ChatResponse,
  CodeFlowAnalysis,
  CodeFlowAnalysisRequest,
  CodeFlowAnalysisResponse,
  ErrorResolutionRequest,
  ErrorResolutionResponse,
  SecurityIssue,
  HealthScore,
  DependencyGraph,
  CodeAnalysis,
} from '../types';

/** Token provider — প্ল্যাটফর্ম থেকে টোকেন নেওয়ার abstraction। */
export interface TokenProvider {
  getToken(): string | null;
}

export class SupremeAIService {
  private client: AxiosInstance;
  private config: SupremeAIConfig;
  private sessionId: string;
  private tokenProvider?: TokenProvider;

  constructor(config: SupremeAIConfig, tokenProvider?: TokenProvider) {
    this.config = config;
    this.tokenProvider = tokenProvider;
    this.sessionId = this.generateSessionId();

    // Axios instance সাধারণ কনফিগ
    this.client = axios.create({
      baseURL: config.backendUrl,
      timeout: 10000,
      headers: { 'Content-Type': 'application/json' },
    });

    // Request interceptor — auth + logging
    this.client.interceptors.request.use((request) => {
      const token = this.resolveToken();
      if (token) {
        request.headers.set('Authorization', `Bearer ${token}`);
      }
      // eslint-disable-next-line no-console
      console.log(`[SupremeAI] Sending ${request.method?.toUpperCase()} to ${request.url}`);
      return request;
    });

    // Response interceptor — centralized error log
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        // eslint-disable-next-line no-console
        console.error(`[SupremeAI] API Error: ${error.message}`);
        return Promise.reject(error);
      }
    );
  }

  private resolveToken(): string | null {
    return this.tokenProvider?.getToken() ?? null;
  }

  private generateSessionId(): string {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `session-${crypto.randomUUID()}`;
    }
    return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  // ========== Knowledge / Learning API ==========

  async sendCodeEdit(edit: CodeEdit): Promise<LearningResponse> {
    if (!this.config.enableRealTimeLearning) {
      return { success: false, message: 'Real-time learning disabled' };
    }
    try {
      const payload: LearningUpload = { type: 'CODE_EDIT', data: edit, sessionId: this.sessionId };
      const res = await this.client.post<LearningResponse>('/api/knowledge/learn', payload);
      return res.data;
    } catch (error: any) {
      return { success: false, message: error.message || 'Failed to send code edit' };
    }
  }

  async reportError(error: ErrorReport): Promise<LearningResponse> {
    if (!this.config.autoReportErrors) {
      return { success: false, message: 'Auto-error reporting disabled' };
    }
    try {
      const payload: LearningUpload = { type: 'ERROR_REPORT', data: error, sessionId: this.sessionId };
      const res = await this.client.post<LearningResponse>('/api/knowledge/failure', payload);
      return res.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] Failed to report error: ${error.message}`);
      return { success: false, message: error.message || 'Failed to report error' };
    }
  }

  async sendFeedback(feedback: SuggestionFeedback): Promise<LearningResponse> {
    return this.sendSuggestionFeedback(feedback);
  }

  async sendSuggestionFeedback(feedback: SuggestionFeedback): Promise<LearningResponse> {
    try {
      const payload: LearningUpload = { type: 'SUGGESTION_FEEDBACK', data: feedback, sessionId: this.sessionId };
      const res = await this.client.post<LearningResponse>('/api/knowledge/feedback', payload);
      return res.data;
    } catch (error: any) {
      return { success: false, message: error.message || 'Failed to send feedback' };
    }
  }

  async getLearningStats(): Promise<{ recentActivity: Array<{ type: string, message: string, timestamp: string }> }> {
    try {
      const res = await this.client.get('/api/knowledge/stats');
      return res.data;
    } catch (error: any) {
      // Mocked fallback if endpoint not available
      return { recentActivity: [] };
    }
  }

  async sendCodeAnalysis(filePath: string, code: string, language: string): Promise<LearningResponse> {
    try {
      const analysis: CodeAnalysis = {
        filePath,
        code,
        language,
        timestamp: new Date().toISOString(),
        metrics: this.analyzeCodeMetrics(code, language),
      };
      const payload: LearningUpload = { type: 'CODE_ANALYSIS', data: analysis, sessionId: this.sessionId };
      const res = await this.client.post<LearningResponse>('/api/knowledge/learn', payload);
      return res.data;
    } catch (error: any) {
      return { success: false, message: error.message || 'Failed to analyze code' };
    }
  }

  async getInlineCompletions(prefix: string, suffix: string, fileName: string, languageId: string): Promise<{ suggestions: string[] }> {
    try {
      // Stub for completion
      const request: ChatRequest = {
        message: `Complete this code:\n${prefix}`,
        sessionId: this.sessionId,
        context: { source: 'desktop', language: languageId, timestamp: new Date().toISOString() }
      };
      const res = await this.client.post<ChatResponse>('/api/completion', request);
      return { suggestions: [res.data.response] };
    } catch (error) {
      return { suggestions: [] };
    }
  }

  // ========== Chat API ==========

  async sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
    try {
      const res = await this.client.post<ChatResponse>('/api/chat', {
        ...request,
        context: {
          ...(request.context ?? {}),
          source: request.context?.source ?? 'desktop',
          timestamp: request.context?.timestamp || new Date().toISOString(),
        },
      });
      return res.data;
    } catch (error: any) {
      return {
        success: false,
        message: 'Chat request failed',
        response: `⚠️ চ্যাট ব্যাকএন্ড এখনে পৌঁছাতে পারেনি: ${error.message}`,
        sessionId: this.sessionId,
        timestamp: new Date().toISOString(),
      };
    }
  }

  // ========== CodeFlow API ==========
  // ========== CodeFlow API ==========

  async analyzeRepository(request: CodeFlowAnalysisRequest): Promise<CodeFlowAnalysisResponse> {
    const response = await this.startCodeFlowAnalysis(request);
    return response ?? {
      success: false,
      analysisId: '',
      data: {
        repositoryId: '',
        files: [],
        dependencies: { nodes: [], edges: [] },
        patterns: [],
        securityIssues: [],
        healthScore: {
          score: 0,
          grade: 'F',
          breakdown: { security: 0, maintainability: 0, complexity: 0, documentation: 0, testing: 0 },
          details: [],
        },
        analysisTimestamp: new Date().toISOString(),
        status: 'failed',
      },
      message: 'Repository analysis failed',
    };
  }

  async startCodeFlowAnalysis(request: CodeFlowAnalysisRequest): Promise<CodeFlowAnalysisResponse | null> {
    try {
      const res = await this.client.post<CodeFlowAnalysisResponse>('/api/codeflow/analyze', request);
      return res.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] CodeFlow analysis failed: ${error.message}`);
      return null;
    }
  }

  async getCodeFlowAnalysis(analysisId: string): Promise<CodeFlowAnalysis | null> {
    try {
      const res = await this.client.get<CodeFlowAnalysisResponse>(`/api/codeflow/analysis/${analysisId}`);
      return res.data.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] Failed to get codeflow analysis: ${error.message}`);
      return null;
    }
  }

  async resolveError(request: ErrorResolutionRequest): Promise<ErrorResolutionResponse | null> {
    try {
      const res = await this.client.post<ErrorResolutionResponse>('/api/codeflow/resolve', request);
      return res.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] Error resolution failed: ${error.message}`);
      return null;
    }
  }

  async getRepositorySecurityIssues(repositoryId: string, severity?: string): Promise<SecurityIssue[]> {
    try {
      const res = await this.client.get<SecurityIssue[]>(`/api/codeflow/repository/${repositoryId}/security`, {
        params: { severity },
      });
      return res.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] Failed to get security issues: ${error.message}`);
      return [];
    }
  }

  async getDependencyGraph(repositoryId: string): Promise<DependencyGraph | null> {
    try {
      const res = await this.client.get<DependencyGraph>(`/api/codeflow/repository/${repositoryId}/dependencies`);
      return res.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] Failed to get dependency graph: ${error.message}`);
      return null;
    }
  }

  async getHealthScore(repositoryId: string): Promise<HealthScore | null> {
    try {
      const res = await this.client.get<HealthScore>(`/api/codeflow/repository/${repositoryId}/health`);
      return res.data;
    } catch (error: any) {
      // eslint-disable-next-line no-console
      console.error(`[SupremeAI] Failed to get health score: ${error.message}`);
      return null;
    }
  }

  // ========== Helpers ==========

  private analyzeCodeMetrics(code: string, language: string): CodeAnalysis['metrics'] {
    const lines = code.split('\n');
    return {
      linesOfCode: lines.length,
      nonEmptyLines: lines.filter((l) => l.trim().length > 0).length,
      commentLines:
        language === 'typescript' || language === 'javascript'
          ? lines.filter((l) => l.trim().startsWith('//') || l.trim().startsWith('/*')).length
          : 0,
      complexityEstimate: this.estimateComplexity(code),
    };
  }

  private estimateComplexity(code: string): number {
    const decisionPoints = (code.match(/\b(if|else|for|while|switch|case|catch)\b/g) || []).length;
    return decisionPoints + 1;
  }

  updateConfig(newConfig: Partial<SupremeAIConfig>): void {
    this.config = { ...this.config, ...newConfig };
  }

  getSessionId(): string {
    return this.sessionId;
  }
}

/** Singleton helper */
let supremeAIService: SupremeAIService | null = null;

export function getSupremeAIService(config?: SupremeAIConfig, tokenProvider?: TokenProvider): SupremeAIService {
  if (!supremeAIService && config) {
    supremeAIService = new SupremeAIService(config, tokenProvider);
  }
  if (!supremeAIService) {
    throw new Error('SupremeAIService not initialized. Call getSupremeAIService(config) first.');
  }
  return supremeAIService;
}

export function setSupremeAIService(service: SupremeAIService): void {
  supremeAIService = service;
}
