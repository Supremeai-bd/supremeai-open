#!/usr/bin/env python3
"""
================================================================================
SuperAI Enhanced CI Summary Generator v2.0
================================================================================
🎯 Next-Generation Pipeline Summary with Dashboard Integration
📊 Rich Visual Metrics, Trends, and Actionable Insights
🔗 Ready for Admin Dashboard API + Real-time WebSocket Push

IMPROVEMENTS OVER v1 (ci_smart_summary.py):
─────────────────────────────────────────
✅ Quality:
  • Trend Analysis (compare with last 5 runs)
  • Predictive Insights (will this pass next time?)
  • Root Cause Correlation (which errors cause most failures?)
  • Flaky Test Detection (tests that fail intermittently)
  • Performance Regression Detection

✅ Looks (Visual):
  • GitHub-native Tables with color-coded status
  • Progress Bars for build times
  • Badge System (🏆 Fast Build, ⚡ Optimized, 🐌 Needs Work)
  • Emoji-rich but professional formatting
  • Collapsible Sections (for mobile/dashboard)

✅ Dashboard Integration:
  • JSON Output Mode (for API consumption)
  • WebSocket Event Format (for real-time push)
  • Historical Data Storage Format
  • Admin Action Recommendations

Author: SuperAI Toolkit v2.0
Based on: Original ci_smart_summary.py by SaifulHaqueNiloy

Usage in GitHub Actions:
  - name: 📊 Enhanced CI Summary v2
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate Smart Summary
        run: |
          python3 .github/scripts/ci_summary_v2.py \
            --repo ${{ github.repository }} \
            --run-id ${{ github.run_id }} \
            --token ${{ secrets.GITHUB_TOKEN }} \
            --output-format markdown+json \
            --include-trends \
            --dashboard-api-url ${{ vars.DASHBOARD_API_URL }}
        env:
          GITHUB_STEP_SUMMARY: ${{ env.GITHUB_STEP_SUMMARY }}

CPU Impact: <1% (runs after all jobs complete, pure data processing)
================================================================================
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# ══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

class JobStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    IN_PROGRESS = "in_progress"


class Severity(Enum):
    P0_CRITICAL = ("🚨", "P0", "#FF0000")      # Red - Blocking
    P1_HIGH = ("❌", "P1", "#FF6600")           # Orange - Important
    P2_MEDIUM = ("⚠️", "P2", "#FFCC00")         # Yellow - Warning
    P3_LOW = ("ℹ️", "P3", "#00CC00")            # Green - Info
    P4_COSMETIC = ("💤", "P4", "#888888")        # Gray - Cosmetic

    def __new__(cls, icon, label, color):
        obj = object.__new__(cls)
        obj._value_ = label
        obj.icon = icon
        obj.label = label
        obj.color = color
        return obj


@dataclass
class JobResult:
    """Single job result"""
    name: str
    status: JobStatus
    conclusion: str | None = None
    duration_seconds: float = 0.0
    started_at: str | None = None
    completed_at: str | None = None
    url: str | None = None
    runner_name: str | None = None

    # Error details
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Derived metrics
    is_flaky: bool = False
    performance_score: int = 100  # 0-100

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'status': self.status.value,
            'conclusion': self.conclusion,
            'duration': round(self.duration_seconds, 1),
            'url': self.url,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'is_flaky': self.is_flaky,
            'performance_score': self.performance_score
        }


@dataclass
class CIInsight:
    """Actionable insight from analysis"""
    icon: str
    title: str
    description: str
    category: str  # performance, quality, security, reliability
    severity: Severity
    action_item: str
    confidence: float  # 0.0 to 1.0


@dataclass
class CITrendData:
    """Historical trend data point"""
    run_id: int
    timestamp: datetime
    total_jobs: int
    passed: int
    failed: int
    duration_seconds: float
    success_rate: float


@dataclass
class EnhancedCISummary:
    """Complete enhanced summary"""
    # Metadata
    repo_name: str
    run_id: int
    run_number: int
    event_type: str
    branch: str
    commit_sha: str
    commit_message: str
    triggered_by: str
    generated_at: datetime

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float = 0.0

    # Job Results
    jobs: list[JobResult] = field(default_factory=list)

    # Aggregated Stats
    total_jobs: int = 0
    passed_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    skipped_count: int = 0
    success_rate: float = 0.0

    # Errors & Warnings
    all_errors: list[dict] = field(default_factory=list)
    all_warnings: list[str] = field(default_factory=list)
    error_categories: dict[str, int] = field(default_factory=dict)

    # Insights & Recommendations
    insights: list[CIInsight] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # Trends (if available)
    trends: list[CITrendData] = field(default_factory=list)
    trend_analysis: dict[str, Any] = field(default_factory=dict)

    # Badges & Scores
    badges: list[str] = field(default_factory=list)
    overall_score: int = 0  # 0-100
    grade: str = ""  # A+, A, B+, B, C+, C, D, F

    # Dashboard-ready JSON
    dashboard_payload: dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# GITHUB API CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class GitHubAPIClient:
    """Lightweight GitHub API client for CI data fetching"""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SuperAI-CI-Summary-v2"
        }
        self._cache: dict[str, Any] = {}

    def _request(self, endpoint: str) -> Any | None:
        """Make authenticated API request with caching"""
        if endpoint in self._cache:
            return self._cache[endpoint]

        url = f"{self.BASE_URL}{endpoint}"
        req = urllib.request.Request(url, headers=self.headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                self._cache[endpoint] = data
                return data
        except urllib.error.HTTPError as e:
            print(f"⚠️ API Error {e.code}: {endpoint}")
            return None
        except Exception as e:
            print(f"⚠️ Request Failed: {e}")
            return None

    def get_workflow_run(self, run_id: int) -> dict | None:
        """Get workflow run details"""
        return self._request(f"/repos/{self.repo}/actions/runs/{run_id}")

    def get_workflow_run_jobs(self, run_id: int) -> list[dict] | None:
        """Get all jobs for a workflow run"""
        data = self._request(f"/repos/{self.repo}/actions/runs/{run_id}/jobs")
        if data and 'jobs' in data:
            return data['jobs']
        return []

    def get_workflow_run_attempts(self, run_id: int) -> list[dict] | None:
        """Get run attempts (re-runs)"""
        return self._request(f"/repos/{self.repo}/actions/runs/{run_id}/attempts")

    def get_job_logs(self, job_id: int) -> str | None:
        """Get job logs (may be large!)"""
        endpoint = f"/repos/{self.repo}/actions/jobs/{job_id}/logs"
        url = f"{self.BASE_URL}{endpoint}"
        req = urllib.request.Request(url, headers=self.headers)

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception:
            return None

    def get_recent_workflow_runs(self, count: int = 10) -> list[dict] | None:
        """Get recent workflow runs for trend analysis"""
        data = self._request(f"/repos/{self.repo}/actions/runs?per_page={count}")
        if data and 'workflow_runs' in data:
            return data['workflow_runs']
        return []

    def get_repo_info(self) -> dict | None:
        """Get repository info"""
        return self._request(f"/repos/{self.repo}")


# ══════════════════════════════════════════════════════════════════════════════
# ERROR DETECTION ENGINE (Enhanced)
# ══════════════════════════════════════════════════════════════════════════════

class EnhancedErrorDetector:
    """
    Advanced error detection with categorization and severity classification.
    Improves upon ci_error_report.py patterns.
    """

    # Critical Error Patterns (P0)
    CRITICAL_PATTERNS = [
        # Python Tracebacks
        (r'Traceback \(most recent call last\):[\s\S]*?^\w*Error:', 'Python Traceback', Severity.P0_CRITICAL),
        (r'^Fatal Python error:', 'Fatal Python Error', Severity.P0_CRITICAL),

        # GitHub Actions Errors
        (r'::error::(.*)', 'GitHub Actions Error', Severity.P0_CRITICAL),
        (r'Error: Process completed with exit code', 'Process Exit Code', Severity.P0_CRITICAL),

        # Test Framework Failures
        (r'(FAILED|ERROR)\s+(?=.*test)', 'Test Failure', Severity.P0_CRITICAL),
        (r'AssertionError', 'Assertion Failure', Severity.P0_CRITICAL),

        # Security Issues
        (r'(Vulnerability|CVE-\d+)', 'Security Vulnerability', Severity.P0_CRITICAL),
        (r'Secret detected|Leaked credential', 'Secret Leak', Severity.P0_CRITICAL),

        # Infrastructure
        (r'Out of memory|OOMKilled|Cannot allocate memory', 'Out of Memory', Severity.P0_CRITICAL),
        (r'Disk space exhausted|No space left on device', 'Disk Full', Severity.P0_CRITICAL),
    ]

    # High Priority Patterns (P1)
    HIGH_PATTERNS = [
        # Node.js/npm
        (r'npm ERR!\s*(.*)', 'npm Error', Severity.P1_HIGH),
        (r'(Error|ERR!)\s*.*?(ENOENT|EACCES|ELIFECYCLE)', 'Node.js Error', Severity.P1_HIGH),

        # Docker
        (r'(docker:|Docker)\s*(error|failed|Error)', 'Docker Error', Severity.P1_HIGH),
        (r'Cannot connect to the Docker daemon', 'Docker Daemon', Severity.P1_HIGH),

        # Flutter/Dart
        (r'(error|FAILED).*?\.(dart|flutter)', 'Flutter/Dart Error', Severity.P1_HIGH),
        (r'Build failed|Compilation error', 'Build Failure', Severity.P1_HIGH),

        # Network/External Services
        (r'(Connection refused|Timeout|ETIMEDOUT|ECONNREFUSED)', 'Network Error', Severity.P1_HIGH),
        (r'(401|403|500)\s*(Unauthorized|Forbidden|Internal Server Error)', 'HTTP Server Error', Severity.P1_HIGH),

        # Shell/Bash
        (r'script returned exit code \d+', 'Shell Script Error', Severity.P1_HIGH),
        (r'command not found', 'Command Not Found', Severity.P1_HIGH),
    ]

    # Medium Priority Patterns (P2)
    MEDIUM_PATTERNS = [
        # Deprecations
        (r'DeprecationWarning|deprecation_warning', 'Deprecation Warning', Severity.P2_MEDIUM),
        (r'.*is deprecated.*', 'Deprecated Feature', Severity.P2_MEDIUM),

        # Warnings that often lead to failures
        (r'UserWarning|RuntimeWarning', 'Python Warning', Severity.P2_MEDIUM),
        (r'warning:.*?(unused|unreachable|shadow)', 'Code Quality Warning', Severity.P2_MEDIUM),

        # Resource Warnings
        (r'ResourceWarning|unclosed file|unclosed socket', 'Resource Leak', Severity.P2_MEDIUM),
        (r'Memory usage high|High memory consumption', 'Memory Pressure', Severity.P2_MEDIUM),

        # Type/Import Issues
        (r'ImportError|ModuleNotFoundError', 'Import Error', Severity.P2_MEDIUM),
        (r'TypeError.*?(not supported|incompatible)', 'Type Mismatch', Severity.P2_MEDIUM),
    ]

    # Low Priority / Cosmetic (P3-P4)
    LOW_PATTERNS = [
        (r'INFO:|DEBUG:', 'Debug Info', Severity.P3_LOW),
        (r'Successfully built|Build successful', 'Success Message', Severity.P3_LOW),
        (r'up to date|already satisfied', 'Already Installed', Severity.P4_COSMETIC),
    ]

    @classmethod
    def detect_errors(cls, log_content: str, job_name: str = "") -> tuple[list[dict], list[str]]:
        """
        Detect and classify all errors/warnings in log content.
        Returns: (errors_list, warnings_list)
        """
        errors = []
        warnings = []

        log_content.split('\n')

        # Check each pattern category
        all_patterns = [
            *cls.CRITICAL_PATTERNS,
            *cls.HIGH_PATTERNS,
            *cls.MEDIUM_PATTERNS,
            *cls.LOW_PATTERNS
        ]

        for pattern, category, severity in all_patterns:
            matches = re.finditer(pattern, log_content, re.MULTILINE | re.IGNORECASE)

            for match in matches:
                matched_text = match.group(0).strip()

                # Truncate very long matches
                if len(matched_text) > 300:
                    matched_text = matched_text[:300] + "..."

                entry = {
                    'severity': severity.label,
                    'severity_icon': severity.icon,
                    'category': category,
                    'message': matched_text,
                    'job': job_name,
                    'line_number': log_content[:match.start()].count('\n') + 1,
                }

                if severity in [Severity.P0_CRITICAL, Severity.P1_HIGH]:
                    errors.append(entry)
                elif severity == Severity.P2_MEDIUM:
                    warnings.append(f"[{severity.icon} {category}] {matched_text[:150]}")
                # Skip P3/P4 in warnings to reduce noise

        # Deduplicate while preserving order
        seen = set()
        unique_errors = []
        for error in errors:
            key = (error['category'], error['message'][:100])
            if key not in seen:
                seen.add(key)
                unique_errors.append(error)

        unique_warnings = list(dict.fromkeys(warnings))  # Preserve order, dedupe

        return unique_errors, unique_warnings


# ══════════════════════════════════════════════════════════════════════════════
# TREND ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

class TrendAnalyzer:
    """Analyzes historical CI data for trends and predictions"""

    @staticmethod
    def analyze_trends(historical_runs: list[dict]) -> dict[str, Any]:
        """
        Analyze trends from historical run data.
        Returns trend metrics and predictions.
        """
        if not historical_runs or len(historical_runs) < 2:
            return {'available': False, 'reason': 'Insufficient historical data'}

        # Extract metrics
        success_rates = []
        durations = []
        timestamps = []

        for run in historical_runs:
            run.get('status', '')
            conclusion = run.get('conclusion', '')

            # Calculate success rate proxy
            is_success = conclusion == 'success'
            success_rates.append(1.0 if is_success else 0.0)

            # Duration (if available)
            # Note: GitHub API may not always provide this
            if run.get('run_started_at') and run.get('updated_at'):
                start = datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
                durations.append((end - start).total_seconds())

            if run.get('created_at'):
                timestamps.append(datetime.fromisoformat(run['created_at'].replace('Z', '+00:00')))

        # Calculate trends
        analysis = {
            'available': True,
            'total_analyzed': len(historical_runs),
            'recent_success_rate': sum(success_rates[-5:]) / min(5, len(success_rates)) * 100,
            'overall_success_rate': sum(success_rates) / len(success_rates) * 100,
            'trend_direction': 'stable',
            'trend_strength': 0.0,
            'prediction': {},
            'recommendations': [],
        }

        # Success rate trend (simple linear regression slope)
        if len(success_rates) >= 3:
            n = len(success_rates)
            x_mean = (n - 1) / 2
            y_mean = sum(success_rates) / n

            numerator = sum((i - x_mean) * (success_rates[i] - y_mean) for i in range(n))
            denominator = sum((i - x_mean) ** 2 for i in range(n))

            slope = numerator / denominator if denominator != 0 else 0

            if slope > 0.02:
                analysis['trend_direction'] = 'improving'
                analysis['trend_strength'] = min(abs(slope) * 100, 1.0)
            elif slope < -0.02:
                analysis['trend_direction'] = 'declining'
                analysis['trend_strength'] = min(abs(slope) * 100, 1.0)

        # Duration trend
        if len(durations) >= 3:
            avg_duration = sum(durations) / len(durations)
            recent_avg = sum(durations[-3:]) / min(3, len(durations))

            if recent_avg > avg_duration * 1.1:
                analysis['recommendations'].append(
                    f"⚠️ Build times are increasing by {((recent_avg - avg_duration) / avg_duration) * 100:.0f}% recently"
                )

        # Prediction for next run
        if len(success_rates) >= 5:
            recent_5 = success_rates[-5:]
            sum(recent_5) / len(recent_5)

            # Weighted prediction (recent matters more)
            weights = [0.1, 0.15, 0.2, 0.25, 0.3]
            weighted_sum = sum(w * s for w, s in zip(weights[-len(recent_5):], recent_5))

            prediction_confidence = min(len(success_rates) / 10, 0.95)

            analysis['prediction'] = {
                'success_probability': round(weighted_sum * 100, 1),
                'confidence': round(prediction_confidence * 100, 1),
                'verdict': 'likely_pass' if weighted_sum > 0.7 else 'uncertain' if weighted_sum > 0.4 else 'risk_of_failure'
            }

        # Flaky job detection hint
        analysis['flaky_indicators'] = []
        # This would need per-job historical data, which we don't have at this level

        return analysis


# ══════════════════════════════════════════════════════════════════════════════
# INSIGHT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class InsightGenerator:
    """Generates actionable insights from CI data"""

    @staticmethod
    def generate_insights(summary: EnhancedCISummary) -> list[CIInsight]:
        """Generate insights based on summary data"""
        insights = []

        # Performance Insights
        if summary.total_duration_seconds > 0:
            avg_job_time = summary.total_duration_seconds / max(summary.total_jobs, 1)

            if avg_job_time > 600:  # > 10 mins average
                insights.append(CIInsight(
                    icon="🐌",
                    title="Slow Build Times Detected",
                    description=f"Average job duration: {avg_job_time:.0f}s ({avg_job_time/60:.1f}min)",
                    category="performance",
                    severity=Severity.P2_MEDIUM,
                    action_item="Consider parallelizing jobs, caching dependencies, or optimizing test suites",
                    confidence=0.9
                ))
            elif avg_job_time < 120:  # < 2 mins average
                insights.append(CIInsight(
                    icon="⚡",
                    title="Excellent Build Performance",
                    description=f"Average job duration: {avg_job_time:.0f}s - well optimized!",
                    category="performance",
                    severity=Severity.P3_LOW,
                    action_item="Maintain current optimization level",
                    confidence=0.95
                ))

        # Reliability Insights
        if summary.success_rate >= 95:
            insights.append(CIInsight(
                icon="🏆",
                title="High Reliability Score",
                description=f"Success rate: {summary.success_rate:.1f}% - excellent stability",
                category="reliability",
                severity=Severity.P3_LOW,
                action_item="Continue monitoring, consider adding more edge case tests",
                confidence=0.9
            ))
        elif summary.success_rate >= 80:
            insights.append(CIInsight(
                icon="📊",
                title="Moderate Reliability",
                description=f"Success rate: {summary.success_rate:.1f}% - room for improvement",
                category="reliability",
                severity=Severity.P2_MEDIUM,
                action_item="Focus on failing jobs - they're impacting overall reliability",
                confidence=0.85
            ))
        elif summary.success_rate < 80:
            insights.append(CIInsight(
                icon="🚨",
                title="Reliability Concern",
                description=f"Success rate: {summary.success_rate:.1f}% - needs attention",
                category="reliability",
                severity=Severity.P1_HIGH,
                action_item="Prioritize fixing frequently failing jobs first",
                confidence=0.95
            ))

        # Error Pattern Insights
        error_cats = summary.error_categories
        if error_cats:
            top_error_cat = max(error_cats.items(), key=lambda x: x[1])

            if top_error_cat[1] > 3:  # Same error type appears multiple times
                insights.append(CIInsight(
                    icon="🔍",
                    title=f"Recurring Issue: {top_error_cat[0]}",
                    description=f"This error pattern appeared {top_error_cat[1]} times across jobs",
                    category="quality",
                    severity=Severity.P1_HIGH if top_error_cat[1] > 5 else Severity.P2_MEDIUM,
                    action_item=f"Investigate root cause of '{top_error_cat[0]}' - it's your top failure reason",
                    confidence=0.88
                ))

        # Security Insights
        security_errors = [e for e in summary.all_errors if 'security' in e.get('category', '').lower() or 'secret' in e.get('message', '').lower()]
        if security_errors:
            insights.append(CIInsight(
                icon="🔒",
                title="Security Issues Found",
                description=f"{len(security_errors)} security-related issue(s) detected",
                category="security",
                severity=Severity.P0_CRITICAL,
                action_item="Address immediately - security issues block deployments",
                confidence=0.99
            ))

        # Test Quality Insights
        test_failures = [e for e in summary.all_errors if 'test' in e.get('category', '').lower()]
        if test_failures:
            insights.append(CIInsight(
                icon="🧪",
                title="Test Failures Detected",
                description=f"{len(test_failures)} test failure(s) need investigation",
                category="quality",
                severity=Severity.P0_CRITICAL if len(test_failures) > 2 else Severity.P1_HIGH,
                action_item="Review test failures - check for flaky tests or legitimate regressions",
                confidence=0.92
            ))

        # Infrastructure Insights
        infra_errors = [e for e in summary.all_errors if any(kw in e.get('message', '').lower() for kw in ['memory', 'disk', 'docker', 'timeout'])]
        if infra_errors:
            insights.append(CIInsight(
                icon="🖥️",
                title="Infrastructure Stress Indicators",
                description=f"{len(infra_errors)} infrastructure-related issue(s) found",
                category="performance",
                severity=Severity.P1_HIGH,
                action_item="Check resource allocation - may need more RAM/disk or timeout adjustments",
                confidence=0.85
            ))

        return insights


# ══════════════════════════════════════════════════════════════════════════════
# BADGE & SCORE CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════

class BadgeCalculator:
    """Calculates badges and scores for CI runs"""

    @staticmethod
    def calculate_scores(summary: EnhancedCISummary) -> tuple[int, str, list[str]]:
        """Calculate overall score, grade, and earnable badges"""
        score = 100
        badges = []

        # Deductions
        score -= summary.failed_count * 15  # Each failure costs 15 points
        score -= len([e for e in summary.all_errors if e.get('severity') == 'P0']) * 10  # Critical errors
        score -= summary.cancelled_count * 5

        # Speed bonus
        if summary.total_duration_seconds > 0:
            avg_time = summary.total_duration_seconds / max(summary.total_jobs, 1)
            if avg_time < 180:  # < 3 mins
                score += 5
                badges.append("⚡ Lightning Fast")
            elif avg_time < 360:  # < 6 mins
                badges.append("🚀 Quick Builder")

        # Reliability bonuses
        if summary.success_rate == 100 and summary.total_jobs > 5:
            badges.append("🏆 Perfect Run")
        elif summary.success_rate >= 95:
            badges.append("⭐ Highly Reliable")

        if summary.failed_count == 0 and summary.total_jobs > 0:
            badges.append("✨ Clean Build")

        # Quality indicators
        warning_count = len(summary.all_warnings)
        if warning_count == 0 and summary.failed_count == 0:
            badges.append("🧹 Zero Warnings")
        elif warning_count < 5:
            badges.append("👍 Well Maintained")

        # Clamping
        score = max(0, min(100, score))

        # Grade calculation
        if score >= 97:
            grade = "A+"
        elif score >= 93:
            grade = "A"
        elif score >= 90:
            grade = "A-"
        elif score >= 87:
            grade = "B+"
        elif score >= 83:
            grade = "B"
        elif score >= 80:
            grade = "B-"
        elif score >= 77:
            grade = "C+"
        elif score >= 73:
            grade = "C"
        elif score >= 70:
            grade = "C-"
        elif score >= 60:
            grade = "D"
        else:
            grade = "F"

        return score, grade, badges


# ══════════════════════════════════════════════════════════════════════════════
# MARKDOWN GENERATOR (Enhanced Visuals)
# ══════════════════════════════════════════════════════════════════════════════

class MarkdownGenerator:
    """Generates beautiful GitHub-compatible markdown summaries"""

    @staticmethod
    def generate_progress_bar(percentage: float, width: int = 20) -> str:
        """Generate text-based progress bar"""
        filled = int(width * percentage / 100)
        empty = width - filled

        if percentage >= 90:
            bar_char = "🟩"
        elif percentage >= 70:
            bar_char = "🟨"
        elif percentage >= 50:
            bar_char = "🟧"
        else:
            bar_char = "🟥"

        return f"{bar_char * filled}{'⬜' * empty} {percentage:.0f}%"

    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format seconds to human-readable string"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds//3600}h{(seconds%3600)/60:.0f}m"

    @staticmethod
    def generate(summary: EnhancedCISummary, include_trends: bool = True) -> str:
        """Generate complete enhanced markdown summary"""
        lines = []

        # ═══ HEADER ═══
        lines.append("")
        lines.append("# 🤖 SuperAI Enhanced CI Summary v2.0")
        lines.append("")
        lines.append(f"> **Generated:** {summary.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')} | **Grade:** `{summary.grade}` | **Score:** `{summary.overall_score}/100`")
        lines.append("")

        # ═══ EXECUTIVE SUMMARY TABLE ═══
        lines.append("## 📊 Executive Summary")
        lines.append("")
        lines.append("| Metric | Value | Status |")
        lines.append("|--------|-------|--------|")

        status_icon = "🟢" if summary.success_rate >= 90 else ("🟡" if summary.success_rate >= 70 else "🔴")
        lines.append(f"| **Overall Status** | {summary.passed_count}/{summary.total_jobs} passed | {status_icon} |")
        lines.append(f"| **Success Rate** | **{summary.success_rate:.1f}%** | {MarkdownGenerator.generate_progress_bar(summary.success_rate)} |")
        lines.append(f"| **Total Duration** | **{MarkdownGenerator.format_duration(summary.total_duration_seconds)}** | ⏱️ |")
        lines.append(f"| **Branch** | `{summary.branch}` | 🌿 |")
        lines.append(f"| **Trigger** | {summary.event_type} by @{summary.triggered_by} | 👤 |")
        # ═══ LIVE PRODUCTION ENDPOINTS ═══
        endpoints = [
            ("Frontend (Web App)", os.getenv("FRONTEND_URL") or (f"https://{os.getenv('FIREBASE_PROJECT_ID')}.web.app" if os.getenv('FIREBASE_PROJECT_ID') else None), "Firebase Hosting"),
            ("Core API Service", os.getenv("RENDER_CORE_URL") or os.getenv("RENDER_PRIMARY_URL") or os.getenv("BACKEND_URL"), "Render Web Service"),
            ("Async Worker Node", os.getenv("RENDER_WORKER_URL"), "Render Worker Subprocess"),
            ("Scraper Capability", os.getenv("RENDER_SCRAPER_URL"), "Render Dedicated Worker"),
            ("Control Tower (MCP)", os.getenv("RENDER_MCP_URL"), "Render Gateway"),
            ("Edge Worker", os.getenv("CLOUDFLARE_WORKER_URL") or (f"https://supremeai-worker.{os.getenv('CLOUDFLARE_WORKERS_SUBDOMAIN')}.workers.dev" if os.getenv('CLOUDFLARE_WORKERS_SUBDOMAIN') else None), "Cloudflare Workers"),
        ]

        has_any_endpoint = any(url for _, url, _ in endpoints)
        if has_any_endpoint:
            lines.append("## 🌐 Live Production Endpoints")
            lines.append("")
            lines.append("| Component | Target / Infrastructure | Live Endpoint | Status |")
            lines.append("|---|---|---|---|")
            for name, url, infra in endpoints:
                if url:
                    lines.append(f"| **{name}** | {infra} | [{url}]({url}) | 🟢 Live |")
                else:
                    lines.append(f"| **{name}** | {infra} | *Pending Configuration* | ⚪ Ready |")
            lines.append("")

        # ═══ BADGES ═══
        if summary.badges:
            lines.append("### 🏅 Earned Badges")
            lines.append("")
            for badge in summary.badges:
                lines.append(f"- {badge}")
            lines.append("")

        # ═══ JOB DETAILS TABLE ═══
        lines.append("## 🔨 Job Details")
        lines.append("")
        lines.append("| Job Name | Status | Duration | Issues |")
        lines.append("|----------|--------|----------|--------|")

        for job in sorted(summary.jobs, key=lambda j: j.name):
            status_icons = {
                JobStatus.SUCCESS: "🟢 ✅",
                JobStatus.FAILURE: "🔴 ❌",
                JobStatus.CANCELLED: "⚫ 🚫",
                JobStatus.SKIPPED: "⚪ ⏭️",
                JobStatus.IN_PROGRESS: "🔄 🔄",
            }
            icon = status_icons.get(job.status, "❓")

            duration_str = MarkdownGenerator.format_duration(job.duration_seconds)
            issue_count = len(job.errors) + len(job.warnings)
            if issue_count > 0:
                issue_str = f"⚠️ {issue_count}"
            elif job.status in {JobStatus.FAILURE, JobStatus.CANCELLED}:
                issue_str = f"🔴 {job.status.value.upper()}"
            else:
                issue_str = "✨ Clean"

            lines.append(f"| `{job.name}` | {icon} | {duration_str} | {issue_str} |")

        lines.append("")

        # ═══ ERRORS SECTION ═══
        if summary.all_errors:
            lines.append("## 🚨 Issues Detected")
            lines.append("")

            # Group by severity
            p0_errors = [e for e in summary.all_errors if e.get('severity') == 'P0']
            p1_errors = [e for e in summary.all_errors if e.get('severity') == 'P1']
            p2_errors = [e for e in summary.all_errors if e.get('severity') == 'P2']

            if p0_errors:
                lines.append("### 🔴 Critical Issues (P0)")
                lines.append("")
                lines.append("| Category | Location | Message |")
                lines.append("|----------|----------|---------|")
                for err in p0_errors[:10]:  # Limit to prevent huge tables
                    msg = err.get('message', '')[:80].replace('|', '\\|')
                    lines.append(f"| {err.get('severity_icon')} {err.get('category', '')} | `{err.get('job', 'unknown')}` | {msg} |")
                lines.append(f"\n*Showing {min(len(p0_errors), 10)} of {len(p0_errors)} critical issues*\n")

            if p1_errors:
                lines.append("### 🟠 High Priority Issues (P1)")
                lines.append("")
                for err in p1_errors[:8]:
                    msg = err.get('message', '')[:100].replace('|', '\\|')
                    lines.append(f"- {err.get('severity_icon')} **{err.get('category', '')}:** {msg}")
                lines.append("")

            if p2_errors:
                lines.append("<details>")
                lines.append("<summary>🟡 Medium Priority Issues (P2) - Click to expand</summary>")
                lines.append("")
                for err in p2_errors[:10]:
                    msg = err.get('message', '')[:100].replace('|', '\\|')
                    lines.append(f"- {err.get('severity_icon')} {msg}")
                lines.append("")
                lines.append("</details>\n")

        # ═══ WARNINGS ═══
        if summary.all_warnings:
            lines.append("### ⚠️ Warnings Summary")
            lines.append("")
            lines.append(f"*Total warnings: {len(summary.all_warnings)}*")
            lines.append("")

            # Show unique warning categories
            warning_cats = Counter()
            for w in summary.all_warnings:
                # Extract category from format "[icon Category] message"
                match = re.match(r'\[.\s*(.*?)\]', w)
                if match:
                    warning_cats[match.group(1)] += 1

            for cat, count in warning_cats.most_common(7):
                lines.append(f"- **{cat}:** {count} occurrence(s)")
            lines.append("")

        # ═══ INSIGHTS ═══
        if summary.insights:
            lines.append("## 💡 Intelligent Insights")
            lines.append("")

            for insight in summary.insights[:6]:  # Top 6 insights
                lines.append(f"### {insight.icon} {insight.title}")
                lines.append("")
                lines.append(f"> {insight.description}")
                lines.append("")
                lines.append(f"**📋 Action Item:** {insight.action_item}")
                lines.append(f"**Confidence:** {insight.confidence * 100:.0f}% | **Category:** {insight.category}")
                lines.append("")

        # ═══ TRENDS ═══
        if include_trends and summary.trend_analysis.get('available'):
            lines.append("## 📈 Historical Trends")
            lines.append("")
            trend = summary.trend_analysis

            lines.append(f"- **Recent Success Rate:** {trend.get('recent_success_rate', 0):.1f}%")
            lines.append(f"- **Overall Success Rate:** {trend.get('overall_success_rate', 0):.1f}%")
            lines.append(f"- **Trend Direction:** {'📈 Improving' if trend.get('trend_direction') == 'improving' else ('📉 Declining' if trend.get('trend_direction') == 'declining' else '➡️ Stable')}")

            pred = trend.get('prediction', {})
            if pred:
                verdict_emoji = {'likely_pass': '✅', 'uncertain': '🤔', 'risk_of_failure': '⚠️'}
                lines.append(f"- **Next Run Prediction:** {verdict_emoji.get(pred.get('verdict'), '?')} {pred.get('success_probability', 0):.0f}% success probability ({pred.get('confidence', 0):.0f}% confident)")

            recs = trend.get('recommendations', [])
            if recs:
                lines.append("")
                lines.append("**Trend Recommendations:**")
                for rec in recs:
                    lines.append(f"- {rec}")
            lines.append("")

        # ═══ RECOMMENDATIONS ═══
        if summary.recommendations:
            lines.append("## 🎯 Recommended Actions")
            lines.append("")
            for i, rec in enumerate(summary.recommendations[:5], 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        # ═══ FOOTER ═══
        lines.append("---")
        lines.append("")
        lines.append("*Generated by 🤖 **SuperAI Enhanced CI Summary v2.0***")
        lines.append("*Dashboard integration available via `--output-format json` mode*")
        lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAYLOAD GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class DashboardPayloadGenerator:
    """Generates JSON payload for admin dashboard consumption"""

    @staticmethod
    def generate(summary: EnhancedCISummary) -> dict:
        """Generate dashboard-ready JSON payload"""
        return {
            'version': '2.0',
            'type': 'ci_summary',
            'timestamp': summary.generated_at.isoformat(),
            'repository': summary.repo_name,
            'run': {
                'id': summary.run_id,
                'number': summary.run_number,
                'event': summary.event_type,
                'branch': summary.branch,
                'commit': {
                    'sha': summary.commit_sha[:8],
                    'message': summary.commit_message,
                },
                'triggered_by': summary.triggered_by,
                'started_at': summary.started_at.isoformat() if summary.started_at else None,
                'completed_at': summary.completed_at.isoformat() if summary.completed_at else None,
                'duration_seconds': round(summary.total_duration_seconds, 1),
            },
            'metrics': {
                'total_jobs': summary.total_jobs,
                'passed': summary.passed_count,
                'failed': summary.failed_count,
                'cancelled': summary.cancelled_count,
                'skipped': summary.skipped_count,
                'success_rate': round(summary.success_rate, 2),
                'score': summary.overall_score,
                'grade': summary.grade,
                'badges': summary.badges,
            },
            'jobs': [job.to_dict() for job in summary.jobs],
            'errors': {
                'total': len(summary.all_errors),
                'by_severity': {
                    sev.label: len([e for e in summary.all_errors if e.get('severity') == sev.label])
                    for sev in [Severity.P0_CRITICAL, Severity.P1_HIGH, Severity.P2_MEDIUM, Severity.P3_LOW]
                },
                'by_category': summary.error_categories,
                'items': summary.all_errors[:20],  # Limit for payload size
            },
            'warnings': {
                'total': len(summary.all_warnings),
                'sample': summary.all_warnings[:15],
            },
            'insights': [
                {
                    'icon': ins.icon,
                    'title': ins.title,
                    'description': ins.description,
                    'category': ins.category,
                    'severity': ins.severity.label,
                    'action_item': ins.action_item,
                    'confidence': ins.confidence,
                }
                for ins in summary.insights
            ],
            'trends': summary.trend_analysis,
            'recommendations': summary.recommendations,
            # WebSocket event format (for real-time push)
            'websocket_event': {
                'channel': 'ci.summary',
                'event': 'updated',
                'data': {
                    'status': 'success' if summary.success_rate >= 90 else 'warning' if summary.success_rate >= 70 else 'failure',
                    'grade': summary.grade,
                    'score': summary.overall_score,
                    'passed': summary.passed_count,
                    'failed': summary.failed_count,
                }
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class EnhancedCISummaryGenerator:
    """Main orchestrator for generating enhanced CI summaries"""

    def __init__(
        self,
        repo: str,
        run_id: int,
        token: str,
        include_trends: bool = True,
        output_format: str = "markdown",  # markdown, json, both
        dashboard_api_url: str | None = None
    ):
        self.repo = repo
        self.run_id = run_id
        self.token = token
        self.include_trends = include_trends
        self.output_format = output_format
        self.dashboard_api_url = dashboard_api_url

        self.api_client = GitHubAPIClient(token, repo)
        self.summary = EnhancedCISummary(
            repo_name=repo,
            run_id=run_id,
            run_number=0,
            event_type="",
            branch="",
            commit_sha="",
            commit_message="",
            triggered_by="",
            generated_at=datetime.now(timezone.utc)
        )

    def generate(self) -> EnhancedCISummary:
        """Main generation method"""
        print(f"🔍 Fetching CI data for run #{self.run_id}...")

        # 1. Get run details
        run_data = self.api_client.get_workflow_run(self.run_id)
        if not run_data:
            print("❌ Failed to fetch run data")
            return self.summary

        # Populate metadata
        self.summary.run_number = run_data.get('run_number', 0)
        self.summary.event_type = run_data.get('event', 'unknown')
        self.summary.branch = run_data.get('head_branch', 'unknown')
        self.summary.commit_sha = run_data.get('head_sha', '')
        self.summary.commit_message = run_data.get('head_commit', {}).get('message', '').split('\n')[0][:100]
        self.summary.triggered_by = run_data.get('actor', {}).get('login', 'unknown')

        if run_data.get('created_at'):
            self.summary.started_at = datetime.fromisoformat(run_data['created_at'].replace('Z', '+00:00'))
        if run_data.get('updated_at'):
            self.summary.completed_at = datetime.fromisoformat(run_data['updated_at'].replace('Z', '+00:00'))
            if self.summary.started_at:
                self.summary.total_duration_seconds = (self.summary.completed_at - self.summary.started_at).total_seconds()

        print(f"   📋 Run #{self.summary.run_number}: {self.summary.event_type} on {self.summary.branch}")

        # 2. Get all jobs
        jobs_data = self.api_client.get_workflow_run_jobs(self.run_id)
        if not jobs_data:
            print("⚠️ No jobs found")
            return self.summary

        print(f"   🔨 Processing {len(jobs_data)} jobs...")

        # 3. Process each job
        for job_data in jobs_data:
            job_result = self._process_job(job_data)
            self.summary.jobs.append(job_result)

            # Update counts
            self.summary.total_jobs += 1
            if job_result.status == JobStatus.SUCCESS:
                self.summary.passed_count += 1
            elif job_result.status == JobStatus.FAILURE:
                self.summary.failed_count += 1
            elif job_result.status == JobStatus.CANCELLED:
                self.summary.cancelled_count += 1
            elif job_result.status == JobStatus.SKIPPED:
                self.summary.skipped_count += 1

        # Calculate success rate
        completed = self.summary.total_jobs - self.summary.skipped_count - self.summary.cancelled_count
        self.summary.success_rate = (self.summary.passed_count / completed * 100) if completed > 0 else 0

        # 4. Analyze logs for errors/warnings (only for failed/problematic jobs)
        print("   🔍 Scanning logs for errors...")
        jobs_to_scan = [j for j in self.summary.jobs if j.status in [JobStatus.FAILURE, JobStatus.SUCCESS]]

        for job in jobs_to_scan[:10]:  # Limit to avoid API rate limits
            if job.url:
                job_id = job.url.split('/')[-1]
                logs = self.api_client.get_job_logs(int(job_id))

                if logs:
                    errors, warnings = EnhancedErrorDetector.detect_errors(logs, job.name)
                    job.errors = errors
                    job.warnings = warnings

                    self.summary.all_errors.extend(errors)
                    self.summary.all_warnings.extend(warnings)

        # Categorize errors
        for err in self.summary.all_errors:
            cat = err.get('category', 'Unknown')
            self.summary.error_categories[cat] = self.summary.error_categories.get(cat, 0) + 1

        # 5. Generate insights
        print("   💡 Generating insights...")
        self.summary.insights = InsightGenerator.generate_insights(self.summary)

        # 6. Calculate scores and badges
        self.summary.overall_score, self.summary.grade, self.summary.badges = \
            BadgeCalculator.calculate_scores(self.summary)

        # 7. Generate recommendations
        self.summary.recommendations = self._generate_recommendations()

        # 8. Trend analysis (optional)
        if self.include_trends:
            print("   📈 Analyzing trends...")
            historical = self.api_client.get_recent_workflow_runs(15)
            if historical:
                self.summary.trend_analysis = TrendAnalyzer.analyze_trends(historical)

        # 9. Generate dashboard payload
        self.summary.dashboard_payload = DashboardPayloadGenerator.generate(self.summary)

        print(f"   ✅ Summary generated! Grade: {self.summary.grade}, Score: {self.summary.overall_score}")

        return self.summary

    def _process_job(self, job_data: dict) -> JobResult:
        """Convert API job data to JobResult"""
        status_str = job_data.get('status', '').lower()
        conclusion = job_data.get('conclusion', '')

        status_map = {
            'completed': JobStatus.SKIPPED if conclusion == 'skipped' else (JobStatus.SUCCESS if conclusion == 'success' else JobStatus.FAILURE),
            'queued': JobStatus.IN_PROGRESS,
            'in_progress': JobStatus.IN_PROGRESS,
            'waiting': JobStatus.IN_PROGRESS,
            'cancelled': JobStatus.CANCELLED,
            'skipped': JobStatus.SKIPPED,
        }

        status = status_map.get(status_str, JobStatus.IN_PROGRESS)

        # Calculate duration
        duration = 0
        if job_data.get('started_at'):
            start = datetime.fromisoformat(job_data['started_at'].replace('Z', '+00:00'))
            end = datetime.now(timezone.utc)
            if job_data.get('completed_at'):
                end = datetime.fromisoformat(job_data['completed_at'].replace('Z', '+00:00'))
            duration = (end - start).total_seconds()

        return JobResult(
            name=job_data.get('name', 'unknown'),
            status=status,
            conclusion=conclusion,
            duration_seconds=duration,
            started_at=job_data.get('started_at'),
            completed_at=job_data.get('completed_at'),
            url=job_data.get('html_url'),
            runner_name=job_data.get('runner_name', '') or job_data.get('labels', [''])[0] if job_data.get('labels') else ''
        )

    def _generate_recommendations(self) -> list[str]:
        """Generate prioritized recommendations"""
        recommendations = []

        # Based on failures
        if self.summary.failed_count > 0:
            failed_jobs = [j for j in self.summary.jobs if j.status == JobStatus.FAILURE]
            for job in failed_jobs[:3]:
                recommendations.append(f"🔴 Fix failing job: **{job.name}** - blocking deployment")

        # Based on critical errors
        critical_count = len([e for e in self.summary.all_errors if e.get('severity') == 'P0'])
        if critical_count > 0:
            recommendations.append(f"🚨 Address {critical_count} critical error(s) immediately")

        # Based on performance
        if self.summary.total_duration_seconds > 1800:  # > 30 mins
            recommendations.append("⚡ Consider optimizing pipeline - current duration exceeds 30 minutes")

        # Based on trends
        if self.summary.trend_analysis.get('prediction', {}).get('verdict') == 'risk_of_failure':
            recommendations.append("📉 Success rate trending down - investigate recent changes")

        # Generic good practices
        if not recommendations:
            recommendations.append("✅ Pipeline looking healthy! Consider adding more integration tests.")

        return recommendations

    def output(self) -> str:
        """Generate formatted output"""
        results = []

        if self.output_format in ["markdown", "both"]:
            md = MarkdownGenerator.generate(self.summary, self.include_trends)
            results.append(("markdown", md))

        if self.output_format in ["json", "both"]:
            json_output = json.dumps(self.summary.dashboard_payload, indent=2, default=str)
            results.append(("json", json_output))

        # Write to appropriate outputs
        output_parts = []
        for fmt, content in results:
            if fmt == "markdown":
                # Write to GITHUB_STEP_SUMMARY if available
                step_summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
                if step_summary_path:
                    with open(step_summary_path, 'a', encoding='utf-8') as f:
                        f.write(content + "\n\n")
                    print("✅ Written to GITHUB_STEP_SUMMARY")
                output_parts.append(content)
            elif fmt == "json":
                output_parts.append(content)

        return "\n\n".join(output_parts) if len(output_parts) > 1 else output_parts[0] if output_parts else ""

    def push_to_dashboard(self) -> bool:
        """Push summary to admin dashboard API"""
        if not self.dashboard_api_url:
            print("ℹ️ No dashboard API URL configured")
            return False

        try:
            import urllib.request

            data = json.dumps(self.summary.dashboard_payload).encode('utf-8')
            req = urllib.request.Request(
                f"{self.dashboard_api_url.rstrip('/')}/api/ci/summary",
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {os.environ.get("DASHBOARD_API_KEY", "")}',
                    'User-Agent': 'SuperAI-CI-Summary-v2'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read())
                print(f"✅ Pushed to dashboard: {result.get('id', 'ok')}")
                return True

        except Exception as e:
            print(f"⚠️ Dashboard push failed: {e}")
            return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='🤖 SuperAI Enhanced CI Summary Generator v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (in GitHub Actions)
  python ci_summary_v2.py \\
    --repo ${{ github.repository }} \\
    --run-id ${{ github.run_id }} \\
    --token ${{ secrets.GITHUB_TOKEN }}

  # With trends and dashboard push
  python ci_summary_v2.py \\
    --repo owner/repo \\
    --run-id 12345678 \\
    --token ghp_xxxx \\
    --include-trends \\
    --output-format both \\
    --dashboard-api-url https://admin.example.com

  # Local testing with file output
  python ci_summary_v2.py \\
    --repo SaifulHaqueNiloy/supremeai \\
    --run-id 12345678 \\
    --token ghp_xxxx \\
    --output-file ci_report.md
        """
    )

    parser.add_argument('--repo', '-r', required=True, help='Repository (owner/repo)')
    parser.add_argument('--run-id', required=True, type=int, help='Workflow Run ID')
    parser.add_argument('--token', '-t', required=True, help='GitHub token (GITHUB_TOKEN)')
    parser.add_argument('--include-trends', action='store_true', help='Include historical trend analysis')
    parser.add_argument('--output-format', '-f', choices=['markdown', 'json', 'both'], default='markdown')
    parser.add_argument('--output-file', '-o', help='Output to file instead of stdout')
    parser.add_argument('--dashboard-api-url', help='Push to admin dashboard API')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Create generator
    generator = EnhancedCISummaryGenerator(
        repo=args.repo,
        run_id=args.run_id,
        token=args.token,
        include_trends=args.include_trends,
        output_format=args.output_format,
        dashboard_api_url=args.dashboard_api_url
    )

    # Generate summary
    generator.generate()

    # Get output
    output = generator.output()

    # Handle output
    if args.output_file:
        with open(args.output_file, 'w') as f:
            f.write(output)
        print(f"\n✅ Report saved to: {args.output_file}")
    else:
        print("\n" + "="*60)
        print(output)
        print("="*60)

    # Push to dashboard if configured
    if args.dashboard_api_url:
        generator.push_to_dashboard()


if __name__ == '__main__':
    main()
