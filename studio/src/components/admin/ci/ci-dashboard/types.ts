// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — TYPES & INTERFACES
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

export interface JobResult {
  id?: string;
  name: string;
  status: 'success' | 'failure' | 'cancelled' | 'skipped' | 'in_progress';
  conclusion?: string;
  duration: number;
  url?: string;
  runner_name?: string;
  error_count: number;
  warning_count: number;
  is_flaky?: boolean;
  performance_score?: number;
  started_at?: string;
  completed_at?: string;
}

export interface CIError {
  severity: string;
  severity_icon: string;
  category: string;
  message: string;
  job: string;
  line_number?: number;
}

export interface CIInsight {
  icon: string;
  title: string;
  description: string;
  category: string;
  severity: string;
  action_item: string;
  confidence: number;
}

export interface CISummaryData {
  version: string;
  timestamp: string;
  repository: string;
  run: {
    id: number;
    number: number;
    event: string;
    branch: string;
    commit: {
      sha: string;
      message: string;
    };
    triggered_by: string;
    started_at?: string;
    completed_at?: string;
    duration_seconds: number;
  };
  metrics: {
    total_jobs: number;
    passed: number;
    failed: number;
    cancelled: number;
    skipped: number;
    success_rate: number;
    score: number;
    grade: string;
    badges: string[];
  };
  jobs: JobResult[];
  errors: {
    total: number;
    by_severity: Record<string, number>;
    by_category: Record<string, number>;
    items: CIError[];
  };
  warnings: {
    total: number;
    sample: string[];
  };
  insights: CIInsight[];
  trends?: {
    available: boolean;
    total_analyzed?: number;
    recent_success_rate?: number;
    overall_success_rate?: number;
    trend_direction?: string;
    prediction?: {
      success_probability: number;
      confidence: number;
      verdict: string;
    };
    recommendations?: string[];
  };
  recommendations: string[];
}

export type ConnectionStatus = 'connected' | 'disconnected' | 'connecting' | 'error';

export interface CIDashboardProps {
  repoName?: string;
  refreshInterval?: number;
  showTrends?: boolean;
  maxHistoryItems?: number;
  onJobClick?: (job: JobResult) => void;
  className?: string;
  compact?: boolean;
  apiUrl?: string;
  wsUrl?: string;
}

// Shape of the sample/derived trend chart data used by the Overview & Trends tabs.
export interface TrendChartPoint {
  name: string;
  success: number;
  duration: number;
}
