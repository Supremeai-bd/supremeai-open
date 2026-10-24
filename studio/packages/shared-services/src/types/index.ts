/**
 * SupremeAI Shared Services - Platform-Agnostic Type Definitions
 * VS Code extension ও Electron desktop app উভয়েই এই টাইপগুলো ব্যবহার করবে,
 * ফলে দুটি প্ল্যাটফর্মে টাইপ সংজ্ঞা আলাদা হয়ে যাওয়ার ঝুঁকি থাকে না।
 */

// ---------- Core Config ----------
export interface SupremeAIConfig {
  backendUrl: string;
  enableRealTimeLearning: boolean;
  autoReportErrors: boolean;
  enableChat?: boolean;
}

// ---------- Learning & Telemetry ----------
export interface CodeEdit {
  taskId: string;
  originalCode: string;
  editedCode: string;
  context: string;
  language: string;
  timestamp: string;
  filePath: string;
  lineNumber?: number;
}

export interface ErrorReport {
  errorType: 'compilation' | 'runtime' | 'lint' | 'security' | 'performance';
  errorMessage: string;
  errorCode?: string;
  filePath: string;
  lineNumber: number;
  columnNumber?: number;
  stackTrace?: string;
  codeSnippet?: string;
  severity: 'error' | 'warning' | 'info';
  timestamp: string;
}

export interface SuggestionFeedback {
  suggestionId: string;
  accepted: boolean;
  modifiedCode?: string;
  context: string;
  taskId: string;
  timestamp: string;
  originalPosition?: any;
}

export interface LearningUpload {
  type: 'CODE_EDIT' | 'ERROR_REPORT' | 'SUGGESTION_FEEDBACK' | 'CODE_ANALYSIS' | 'CHAT_MESSAGE';
  data: CodeEdit | ErrorReport | SuggestionFeedback | ChatMessage | CodeAnalysis;
  sessionId: string;
  userId?: string;
}

export interface LearningResponse {
  success: boolean;
  message: string;
  learnedPatterns?: string[];
}

// ---------- Notification ----------
export interface NotificationMessage {
  type: 'GITHUB_PIPELINE' | 'SYSTEM_ALERT' | 'LEARNING_UPDATE' | 'CHAT_MESSAGE';
  status: 'success' | 'failure' | 'warning' | 'info';
  message: string;
  timestamp: string;
  details?: Record<string, unknown>;
}
// ---------- Chat ----------
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  error?: boolean;
  thinking?: boolean;
  context?: unknown;
}

export interface ChatSession {
  id: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
  context?: {
    language?: string;
    filePath?: string;
    projectInfo?: unknown;
  };
}

export interface ChatRequest {
  message: string;
  sessionId: string;
  messages?: ChatMessage[];
  context?: {
    source: 'vscode' | 'intellij' | 'web' | 'flutter' | 'electron' | 'desktop';
    language?: string;
    filePath?: string;
    codeSnippet?: string;
    timestamp: string;
  };
}

export interface ChatResponse {
  success: boolean;
  message: string;
  response: string;
  sessionId: string;
  timestamp: string;
  suggestions?: string[];
}

// ---------- CodeFlow: Analysis ----------
export interface CodeFlowAnalysis {
  repositoryId: string;
  repositoryUrl?: string;
  files: CodeFlowFile[];
  dependencies: DependencyGraph;
  patterns: PatternDetection[];
  securityIssues: SecurityIssue[];
  healthScore: HealthScore;
  analysisTimestamp: string;
  status: 'pending' | 'analyzing' | 'completed' | 'failed';
}

export interface CodeFlowFile {
  path: string;
  language: string;
  size: number;
  lastModified: string;
  functions: CodeFlowFunction[];
  classes: CodeFlowClass[];
  imports: string[];
  exports: string[];
  complexity: number;
  linesOfCode: number;
}

export interface CodeFlowFunction {
  name: string;
  line: number;
  args: string[];
  returnType: string;
  complexity: number;
  calls: string[];
  calledBy: string[];
}

export interface CodeFlowClass {
  name: string;
  line: number;
  methods: string[];
  properties: string[];
  extends?: string;
  implements?: string[];
}

export interface DependencyGraph {
  nodes: DependencyNode[];
  edges: DependencyEdge[];
}

export interface DependencyNode {
  id: string;
  label: string;
  type: 'file' | 'function' | 'class' | 'module';
  file?: string;
  metrics?: {
    complexity: number;
    linesOfCode: number;
    dependencies: number;
  };
}

export interface DependencyEdge {
  source: string;
  target: string;
  type: 'imports' | 'calls' | 'extends' | 'implements';
  weight?: number;
}

export interface PatternDetection {
  type: 'singleton' | 'factory' | 'observer' | 'react_hooks' | 'god_object' | 'circular_dependency';
  severity: 'low' | 'medium' | 'high' | 'critical';
  file: string;
  line: number;
  description: string;
  suggestion: string;
}

export interface SecurityIssue {
  type: 'hardcoded_secret' | 'eval_usage' | 'sql_injection' | 'debug_statement' | 'unsafe_import';
  severity: 'critical' | 'high' | 'medium' | 'low';
  file: string;
  line: number;
  code: string;
  description: string;
  fix: string;
  cwe?: string;
}

export interface HealthScore {
  score: number;
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  breakdown: {
    security: number;
    maintainability: number;
    complexity: number;
    documentation: number;
    testing: number;
  };
  details: string[];
}

export interface CodeFlowAnalysisRequest {
  repositoryUrl?: string;
  files?: Array<{
    path: string;
    content: string;
  }>;
  options?: {
    includePatterns: boolean;
    includeSecurity: boolean;
    includeDependencies: boolean;
    depth: number;
  };
}

export interface CodeFlowAnalysisResponse {
  success: boolean;
  analysisId: string;
  data: CodeFlowAnalysis;
  message: string;
}

// ---------- Error Resolution ----------
export interface ErrorResolutionRequest {
  errorType: string;
  errorMessage: string;
  stackTrace?: string;
  filePath?: string;
  codeSnippet?: string;
  context: string;
}

export interface ErrorResolutionResponse {
  success: boolean;
  rootCause: string;
  affectedFiles: string[];
  blastRadius: string[];
  suggestedFixes: SuggestedFix[];
  confidence: number;
}

export interface SuggestedFix {
  description: string;
  code: string;
  explanation: string;
  impact: string;
  difficulty: 'easy' | 'medium' | 'hard';
}

export interface CodeAnalysis {
  filePath: string;
  code: string;
  language: string;
  timestamp: string;
  metrics: {
    linesOfCode: number;
    nonEmptyLines: number;
    commentLines: number;
    complexityEstimate: number;
  };
}