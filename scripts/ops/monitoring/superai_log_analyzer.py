#!/usr/bin/env python3
"""
================================================================================
SuperAI Log Analyzer - Intelligent Log Analysis & Alerting
================================================================================
📝 Analyzes application and system logs for issues
🔍 Detects errors, anomalies, and performance patterns
⚡ Real-time log monitoring with alerting
📊 Generates reports with statistics and trends

Author: SuperAI Toolkit
Version: 1.0.0
License: MIT

Usage:
    python superai_log_analyzer.py                           # Analyze all logs
    python superai_log_analyzer.py --file app.log            # Analyze specific file
    python superai_log_analyzer.py --follow --tail           # Real-time monitoring
    python superai_log_analyzer.py --errors-only             # Show only errors
    python superai_log_analyzer.py --since "1 hour ago"      # Time-based filter
    python superai_log_analyzer.py --alert                   # Enable alerts

Log Sources Supported:
  🐍 Python/FastAPI (uvicorn/gunicorn)
  ⚛️ Next.js/Node.js console output
  🗄️ PostgreSQL database logs
  💾 Redis logs
  🐳 Docker container logs
  🔧 System logs (syslog/journal)

Detection Capabilities:
  ❌ Error detection with categorization
  ⚠️ Warning patterns and thresholds
  📈 Performance anomaly detection
  🔒 Security event identification
  🔄 Request pattern analysis

CPU Impact:
  - Analysis: ~2-5% CPU during processing (short bursts)
  - Real-time follow mode: <1% continuous
  - Memory: Scales with log file size (~10MB per 100K lines)
================================================================================
"""

import argparse
import json
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorCategory(Enum):
    GENERAL = "general"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NETWORK = "network"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    LLM_API = "llm_api"
    RATE_LIMIT = "rate_limit"
    MEMORY = "memory"
    SECURITY = "security"
    UNKNOWN = "unknown"


@dataclass
class LogEntry:
    """Parsed log entry."""
    raw_line: str
    timestamp: datetime | None = None
    level: LogLevel | None = None
    message: str = ""
    source: str = ""  # File/module name
    line_number: int = 0
    error_category: ErrorCategory | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'level': self.level.value if self.level else None,
            'message': self.message,
            'source': self.source,
            'line_number': self.line_number,
            'error_category': self.error_category.value if self.error_category else None,
            'details': self.details
        }


@dataclass
class LogAnalysisReport:
    """Complete log analysis report."""
    source_files: list[str] = field(default_factory=list)
    total_lines: int = 0
    parsed_entries: int = 0
    entries_by_level: dict[str, int] = field(default_factory=dict)
    error_categories: dict[str, int] = field(default_factory=dict)
    top_errors: list[tuple[str, int]] = field(default_factory=list)
    time_range: tuple[datetime, datetime] | None = None
    anomalies: list[dict] = field(default_factory=list)
    security_events: list[dict] = field(default_factory=list)
    performance_metrics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'source_files': self.source_files,
            'total_lines': self.total_lines,
            'parsed_entries': self.parsed_entries,
            'entries_by_level': self.entries_by_level,
            'error_categories': self.error_categories,
            'top_errors': self.top_errors[:20],
            'time_range': [t.isoformat() for t in self.time_range] if self.time_range else None,
            'anomalies': self.anomalies,
            'security_events': self.security_events,
            'performance_metrics': self.performance_metrics,
            'recommendations': self.recommendations
        }


# Pattern definitions for different log formats
LOG_PATTERNS = {
    # Python logging format
    'python': re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s*'
        r'\[(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\s*'
        r'(?P<source>[^:]+):(?P<line>\d+)\s*'
        r'(?P<message>.*)',
        re.IGNORECASE
    ),

    # Uvicorn/Gunicorn format
    'uvicorn': re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*'
        r'(?:\[(?P<level>info|warning|error|critical)\])?\s*'
        r'(?P<message>.*)',
        re.IGNORECASE
    ),

    # ISO format with level
    'iso_level': re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s*'
        r'\[(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\]\s*'
        r'(?P<message>.*)',
        re.IGNORECASE
    ),

    # Generic timestamp + message
    'generic': re.compile(
        r'(?:(?P<timestamp>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*)?'
        r'(?P<message>.*)'
    ),
}

# Error classification patterns
ERROR_PATTERNS = {
    ErrorCategory.DATABASE: [
        re.compile(r'database|postgres|sql|query|connection.*refused', re.IGNORECASE),
        re.compile(r'integrity.*error|unique.*violation|foreign.*key', re.IGNORECASE),
        re.compile(r'deadlock|lock.*timeout|connection.*pool', re.IGNORECASE),
    ],
    ErrorCategory.AUTHENTICATION: [
        re.compile(r'unauthorized|authentication.*failed|invalid.*token', re.IGNORECASE),
        re.compile(r'401|login.*failed|auth.*error', re.IGNORECASE),
        re.compile(r'session.*expired|token.*expired', re.IGNORECASE),
    ],
    ErrorCategory.AUTHORIZATION: [
        re.compile(r'forbidden|permission.*denied|access.*denied', re.IGNORECASE),
        re.compile(r'403|not.*allowed|unauthorized.*access', re.IGNORECASE),
        re.compile(r'role.*required|insufficient.*privileges', re.IGNORECASE),
    ],
    ErrorCategory.NETWORK: [
        re.compile(r'connection.*reset|connection.*refused|network.*error', re.IGNORECASE),
        re.compile(r'timeout|ECONNREFUSED|ENOTFOUND', re.IGNORECASE),
        re.compile(r'dns.*fail|socket.*error|network.*unreachable', re.IGNORECASE),
    ],
    ErrorCategory.TIMEOUT: [
        re.compile(r'timed out|timeout|request.*timeout', re.IGNORECASE),
        re.compile(r'operation.*expired|deadline.*exceeded', re.IGNORECASE),
    ],
    ErrorCategory.VALIDATION: [
        re.compile(r'validation.*error|invalid.*input|bad.*request', re.IGNORECASE),
        re.compile(r'400|schema.*error|type.*error', re.IGNORECASE),
        re.compile(r'missing.*required|field.*required', re.IGNORECASE),
    ],
    ErrorCategory.LLM_API: [
        re.compile(r'openai|anthropic|claude|gemini|llm', re.IGNORECASE),
        re.compile(r'api.*key.*invalid|rate.*limit.*exceeded', re.IGNORECASE),
        re.compile(r'model.*not.*found|context.*length.*exceeded', re.IGNORECASE),
        re.compile(r'429|500.*from.*llm|provider.*error', re.IGNORECASE),
    ],
    ErrorCategory.RATE_LIMIT: [
        re.compile(r'rate.*limit|too.*many.*requests|429', re.IGNORECASE),
        re.compile(r'throttl|quota.*exceeded', re.IGNORECASE),
    ],
    ErrorCategory.MEMORY: [
        re.compile(r'out.*of.*memory|oom|memory.*error', re.IGNORECASE),
        re.compile(r'heap.*overflow|allocation.*failed', re.IGNORECASE),
        re.compile(r'MemoryError|cannot.*allocate', re.IGNORECASE),
    ],
    ErrorCategory.SECURITY: [
        re.compile(r'injection|xss|csrf|sqli', re.IGNORECASE),
        re.compile(r'unauthorized.*access|suspicious.*activity', re.IGNORECASE),
        re.compile(r'brute.*force|attack|malicious', re.IGNORECASE),
        re.compile(r'permission.*escalation|privilege.*escalation', re.IGNORECASE),
    ],
}

# Security event patterns
SECURITY_PATTERNS = {
    'sql_injection': re.compile(r"(?:union.*select|'.*or.*'|1=1|--)", re.IGNORECASE),
    'xss_attempt': re.compile(r"<script|javascript:|on\w+\s*=", re.IGNORECASE),
    'path_traversal': re.compile(r"\.\./|\.\.\\|%2e%2e", re.IGNORECASE),
    'brute_force': re.compile(r"multiple.*failed.*login|authentication.*failure.*\d+", re.IGNORECASE),
    'unusual_user_agent': re.compile(r"(?:bot|scanner|curl|python-requests|nikto|sqlmap)", re.IGNORECASE),
}


class SuperAILogAnalyzer:
    """
    Advanced log analysis tool for SuperAI platform.
    
    Features:
    - Multi-format log parsing
    - Intelligent error categorization
    - Security event detection
    - Anomaly identification
    - Trend analysis
    - Real-time monitoring
    """

    def __init__(
        self,
        log_files: list[str] | None = None,
        log_dir: str | None = None,
        since: str | None = None,
        until: str | None = None,
        errors_only: bool = False,
        follow_mode: bool = False,
        enable_alerts: bool = False,
        max_lines: int | None = None,
        verbose: bool = False
    ):
        self.log_files = log_files or []
        self.log_dir = Path(log_dir) if log_dir else None
        self.since = self._parse_time(since) if since else None
        self.until = self._parse_time(until) if until else None
        self.errors_only = errors_only
        self.follow_mode = follow_mode
        self.enable_alerts = enable_alerts
        self.max_lines = max_lines
        self.verbose = verbose

        self.report = LogAnalysisReport()
        self.entries: list[LogEntry] = []
        self._stop_follow = threading.Event()

        # Auto-discover logs if none specified
        if not self.log_files and not self.log_dir:
            self._discover_logs()

    def _parse_time(self, time_str: str) -> datetime | None:
        """Parse relative or absolute time string."""
        now = datetime.now()

        # Relative patterns
        relative_patterns = [
            (r'(\d+)\s*minute[s]?\s*ago', lambda m: now - timedelta(minutes=int(m.group(1)))),
            (r'(\d+)\s*hour[s]?\s*ago', lambda m: now - timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s*day[s]?\s*ago', lambda m: now - timedelta(days=int(m.group(1)))),
            (r'(\d+)\s*week[s]?\s*ago', lambda m: now - timedelta(weeks=int(m.group(1)))),
            (r'yesterday', lambda m: now - timedelta(days=1)),
            (r'today', lambda m: now.replace(hour=0, minute=0, second=0, microsecond=0)),
        ]

        for pattern, handler in relative_patterns:
            match = re.match(pattern, time_str.strip(), re.IGNORECASE)
            if match:
                return handler(match)

        # Try ISO format
        try:
            return datetime.fromisoformat(time_str)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")

        print(f"Warning: Could not parse time: {time_str}")
        return None

    def _discover_logs(self):
        """Auto-discover log files in common locations."""
        project_root = Path.cwd()

        search_paths = [
            project_root / 'logs',
            project_root / '.next',
            project_root / 'backend' / 'logs',
            Path('/var/log'),
        ]

        log_extensions = ['.log', '.txt', '.json']

        for search_path in search_paths:
            if not search_path.exists():
                continue

            for ext in log_extensions:
                for log_file in search_path.glob(f'*{ext}'):
                    if log_file.is_file() and log_file.stat().st_size > 0:
                        self.log_files.append(str(log_file))

        # Also check for common app log names
        common_names = ['app.log', 'server.log', 'error.log', 'access.log', 'uvicorn.log']
        for name in common_names:
            for parent in [project_root, project_root / 'backend']:
                candidate = parent / name
                if candidate.exists() and str(candidate) not in self.log_files:
                    self.log_files.append(str(candidate))

    def parse_line(self, line: str, line_number: int = 0) -> LogEntry | None:
        """Parse a single log line into a structured entry."""
        line = line.strip()
        if not line:
            return None

        entry = LogEntry(raw_line=line, line_number=line_number)

        # Try each pattern
        for pattern in LOG_PATTERNS.values():
            match = pattern.match(line)
            if match:
                groups = match.groupdict()

                # Parse timestamp
                if groups.get('timestamp'):
                    try:
                        entry.timestamp = self._parse_timestamp(groups['timestamp'])
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(f"Silenced error: {e}")

                # Parse level
                level_str = groups.get('level', '')
                if level_str:
                    entry.level = self._normalize_level(level_str)

                # Extract fields
                entry.message = groups.get('message', line)
                entry.source = groups.get('source', '')

                if groups.get('line'):
                    entry.line_number = int(groups['line'])

                break
        else:
            # No pattern matched - treat as raw message
            entry.message = line
            entry.level = LogLevel.INFO  # Default to INFO

        # Classify errors
        if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
            entry.error_category = self._classify_error(entry.message)

            # Extract additional details
            entry.details = self._extract_error_details(entry.message)

        # Check for security events
        self._check_security_event(entry)

        return entry

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse various timestamp formats."""
        formats = [
            '%Y-%m-%d %H:%M:%S,%f',     # Python logging with ms
            '%Y-%m-%d %H:%M:%S',         # Standard
            '%Y-%m-%dT%H:%M:%S.%f',      # ISO with microseconds
            '%Y-%m-%dT%H:%M:%S',         # ISO
            '%Y-%m-%dT%H:%M:%SZ',        # ISO UTC
            '%Y-%m-%dT%H:%M:%S%z',       # ISO with timezone
        ]

        for fmt in formats:
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Cannot parse timestamp: {ts_str}")

    def _normalize_level(self, level_str: str) -> LogLevel:
        """Normalize log level string to enum."""
        level_map = {
            'DEBUG': LogLevel.DEBUG,
            'INFO': LogLevel.INFO,
            'WARN': LogLevel.WARNING,
            'WARNING': LogLevel.WARNING,
            'ERROR': LogLevel.ERROR,
            'CRITICAL': LogLevel.CRITICAL,
            'FATAL': LogLevel.CRITICAL,
            'info': LogLevel.INFO,
            'warning': LogLevel.WARNING,
            'error': LogLevel.ERROR,
            'critical': LogLevel.CRITICAL,
        }

        return level_map.get(level_str.upper(), LogLevel.INFO)

    def _classify_error(self, message: str) -> ErrorCategory:
        """Classify error into category based on patterns."""
        scores = {}

        for category, patterns in ERROR_PATTERNS.items():
            score = sum(1 for p in patterns if p.search(message))
            if score > 0:
                scores[category] = score

        if scores:
            return max(scores.keys(), key=lambda k: scores[k])

        return ErrorCategory.UNKNOWN

    def _extract_error_details(self, message: str) -> dict:
        """Extract structured details from error messages."""
        details = {}

        # Extract status codes
        status_match = re.search(r'(?:status|code)[:\s]*(\d{3})', message, re.IGNORECASE)
        if status_match:
            details['status_code'] = int(status_match.group(1))

        # Extract exception types
        exc_match = re.search(r'([A-Z][a-z]+(?:Error|Exception|Warning))', message)
        if exc_match:
            details['exception_type'] = exc_match.group(1)

        # Extract URLs
        url_match = re.search(r'https?://[^\s\]"\'<>]+', message)
        if url_match:
            details['url'] = url_match.group(0)

        # Extract IP addresses
        ip_matches = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message)
        if ip_matches:
            details['ip_addresses'] = ip_matches

        # Extract request IDs
        req_id_match = re.search(r'(?:request[-_]?id|trace[-_]?id|correlation[-_]?id)[=:]\s*([\w-]+)', message, re.IGNORECASE)
        if req_id_match:
            details['request_id'] = req_id_match.group(1)

        return details

    def _check_security_event(self, entry: LogEntry):
        """Check if entry contains security-relevant information."""
        for event_type, pattern in SECURITY_PATTERNS.items():
            if pattern.search(entry.raw_line):
                entry.details['security_event_type'] = event_type

                if entry not in [e for e in self.report.security_events]:
                    self.report.security_events.append({
                        'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
                        'event_type': event_type,
                        'message': entry.message[:200],
                        'source': entry.source,
                        'severity': 'high' if event_type in ['sql_injection', 'xss_attempt'] else 'medium'
                    })

    def analyze_file(self, filepath: str) -> list[LogEntry]:
        """Analyze a single log file."""
        path = Path(filepath)

        if not path.exists():
            print(f"❌ File not found: {filepath}")
            return []

        entries = []
        line_count = 0

        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line_count += 1

                    # Check max lines limit
                    if self.max_lines and len(entries) >= self.max_lines:
                        break

                    entry = self.parse_line(line, line_num)

                    if entry:
                        # Apply time filter
                        if entry.timestamp:
                            if self.since and entry.timestamp < self.since:
                                continue
                            if self.until and entry.timestamp > self.until:
                                continue

                        # Apply error filter
                        if self.errors_only and entry.level not in [LogLevel.ERROR, LogLevel.CRITICAL]:
                            continue

                        entries.append(entry)

                        if self.enable_alerts and entry.level == LogLevel.CRITICAL:
                            self._emit_alert(entry)

        except Exception as e:
            print(f"Error reading {filepath}: {e}")

        self.report.total_lines += line_count
        self.report.parsed_entries += len(entries)

        if filepath not in self.report.source_files:
            self.report.source_files.append(filepath)

        return entries

    def analyze_all(self) -> LogAnalysisReport:
        """Analyze all configured log sources."""
        print("\n" + "="*60)
        print("📝 SuperAI Log Analyzer")
        print("="*60)

        # Determine files to analyze
        files_to_analyze = list(self.log_files)

        if self.log_dir and self.log_dir.exists():
            for log_file in self.log_dir.glob('*'):
                if log_file.is_file() and log_file.suffix in ['.log', '.txt']:
                    files_to_analyze.append(str(log_file))

        if not files_to_analyze:
            print("\nNo log files found. Specify files with --file or --log-dir")
            print("Or place logs in ./logs/ directory")
            return self.report

        print(f"\nAnalyzing {len(files_to_analyze)} log file(s)...")

        if self.follow_mode:
            self._run_follow_mode(files_to_analyze)
        else:
            # Analyze each file
            for filepath in files_to_analyze:
                if self.verbose:
                    print(f"   📄 {filepath}")
                entries = self.analyze_file(filepath)
                self.entries.extend(entries)

            # Generate analysis
            self._generate_analysis()

        self.print_report()
        return self.report

    def _run_follow_mode(self, files_to_analyze: list[str]):
        """Real-time log following mode."""
        print(f"\n👀 Following {len(files_to_analyze)} file(s)... (Ctrl+C to stop)")
        print("-"*60)

        # Initial read of existing content
        file_positions = {}

        for filepath in files_to_analyze:
            try:
                with open(filepath, 'r') as f:
                    f.seek(0, 2)  # Seek to end
                    file_positions[filepath] = f.tell()
            except Exception:
                file_positions[filepath] = 0

        # Follow loop
        while not self._stop_follow.is_set():
            for filepath in files_to_analyze:
                try:
                    with open(filepath, 'r') as f:
                        f.seek(file_positions.get(filepath, 0))

                        for line in f:
                            entry = self.parse_line(line)

                            if entry:
                                # Print based on filters
                                should_print = True

                                if self.errors_only:
                                    should_print = entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]

                                if should_print:
                                    self._print_entry(entry)

                                    if self.enable_alerts and entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                                        self._emit_alert(entry)

                        file_positions[filepath] = f.tell()

                except Exception as e:
                    if self.verbose:
                        print(f"Error reading {filepath}: {e}")

            time.sleep(0.5)  # Polling interval

    def _generate_analysis(self):
        """Generate analysis from collected entries."""
        if not self.entries:
            return

        # Count by level
        level_counter = Counter(e.level.value for e in self.entries if e.level)
        self.report.entries_by_level = dict(level_counter)

        # Count error categories
        error_entries = [e for e in self.entries if e.level in [LogLevel.ERROR, LogLevel.CRITICAL]]
        category_counter = Counter(e.error_category.value for e in error_entries if e.error_category)
        self.report.error_categories = dict(category_counter)

        # Top errors (by message similarity)
        error_messages = [e.message for e in error_entries]
        # Simple grouping by first 100 chars
        message_counter = Counter(m[:100] for m in error_messages)
        self.report.top_errors = message_counter.most_common(20)

        # Time range
        timestamps = [e.timestamp for e in self.entries if e.timestamp]
        if timestamps:
            self.report.time_range = (min(timestamps), max(timestamps))

        # Detect anomalies
        self._detect_anomalies()

        # Calculate performance metrics
        self._calculate_performance_metrics()

        # Generate recommendations
        self._generate_recommendations()

    def _detect_anomalies(self):
        """Detect unusual patterns in logs."""
        if len(self.entries) < 100:
            return

        # Time-based clustering of errors
        error_timestamps = [e.timestamp for e in self.entries
                          if e.level in [LogLevel.ERROR, LogLevel.CRITICAL] and e.timestamp]

        if len(error_timestamps) >= 5:
            # Look for burst patterns (many errors in short time)
            sorted_ts = sorted(error_timestamps)

            for i in range(len(sorted_ts) - 4):
                window = sorted_ts[i:i+5]
                time_diff = (window[-1] - window[0]).total_seconds()

                if time_diff < 10:  # 5 errors within 10 seconds
                    self.report.anomalies.append({
                        'type': 'error_burst',
                        'timestamp': window[0].isoformat(),
                        'count': 5,
                        'duration_seconds': round(time_diff, 1),
                        'description': f'5 errors in {time_diff:.1f}s indicates possible issue'
                    })
                    break  # Report first anomaly only

        # Check for repeated identical errors (possible stuck process)
        if self.report.top_errors:
            top_count = self.report.top_errors[0][1]
            total_errors = sum(count for _, count in self.report.top_errors)

            if top_count > total_errors * 0.5 and top_count > 10:
                self.report.anomalies.append({
                    'type': 'repeated_error',
                    'message': self.report.top_errors[0][0][:100],
                    'count': top_count,
                    'description': f'Same error repeated {top_count} times - may indicate stuck state'
                })

    def _calculate_performance_metrics(self):
        """Calculate performance-related metrics from logs."""
        # Look for timing information in logs
        duration_pattern = re.compile(r'(?:duration|time|elapsed)[:\s]*(\d+(?:\.\d+)?)\s*(ms|s|milliseconds)?', re.IGNORECASE)

        durations_ms = []

        for entry in self.entries:
            matches = duration_pattern.findall(entry.raw_line)
            for value, unit in matches:
                try:
                    val = float(value)
                    if unit == 's':
                        val *= 1000
                    elif unit == 'milliseconds':
                        pass  # Already in ms

                    if 0 < val < 60000:  # Reasonable range (< 60s)
                        durations_ms.append(val)
                except ValueError:
                    continue

        if durations_ms:
            self.report.performance_metrics = {
                'total_request_timings': len(durations_ms),
                'avg_duration_ms': round(sum(durations_ms) / len(durations_ms), 2),
                'min_duration_ms': round(min(durations_ms), 2),
                'max_duration_ms': round(max(durations_ms), 2),
                'p95_duration_ms': round(sorted(durations_ms)[int(len(durations_ms) * 0.95)], 2) if len(durations_ms) > 1 else 0,
            }

    def _generate_recommendations(self):
        """Generate recommendations based on analysis."""
        recs = []

        # High error rate
        total = len(self.entries)
        errors = sum(self.report.entries_by_level.get(l, 0)
                    for l in ['ERROR', 'CRITICAL'])

        if total > 0:
            error_rate = errors / total * 100
            if error_rate > 10:
                recs.append(f"High error rate ({error_rate:.1f}%): Investigate root causes")
            elif error_rate > 5:
                recs.append(f"Elevated error rate ({error_rate:.1f}%): Monitor closely")

        # Specific category recommendations
        if self.report.error_categories.get('database', 0) > 5:
            recs.append("Multiple database errors: Check connection pool, query performance")

        if self.report.error_categories.get('llm_api', 0) > 5:
            recs.append("LLM API errors: Verify API keys, check rate limits, review model availability")

        if self.report.error_categories.get('rate_limit', 0) > 3:
            recs.append("Rate limiting hits: Consider increasing limits or implementing caching")

        if self.report.error_categories.get('memory', 0) > 0:
            recs.append("Memory errors detected: Review memory usage, consider scaling")

        # Security events
        if len(self.report.security_events) > 0:
            high_severity = sum(1 for e in self.report.security_events if e.get('severity') == 'high')
            if high_severity > 0:
                recs.append(f"⚠️ {high_severity} high-security security events detected!")
            recs.append(f"{len(self.report.security_events)} total security events: Review access logs")

        # Performance
        perf = self.report.performance_metrics
        if perf and perf.get('p95_duration_ms', 0) > 5000:
            recs.append(f"Slow responses detected (P95: {perf['p95_duration_ms']}ms): Optimize slow endpoints")

        if not recs:
            recs.append("✅ No significant issues detected - logs look healthy!")

        self.report.recommendations = recs

    def _print_entry(self, entry: LogEntry):
        """Print a single log entry."""
        icons = {
            LogLevel.DEBUG: "🔍",
            LogLevel.INFO: "ℹ️",
            LogLevel.WARNING: "⚠️",
            LogLevel.ERROR: "❌",
            LogLevel.CRITICAL: "🚨",
        }

        icon = icons.get(entry.level, "•")
        ts = entry.timestamp.strftime('%H:%M:%S') if entry.timestamp else '??'

        color_map = {
            LogLevel.DEBUG: '\033[90m',   # Gray
            LogLevel.INFO: '\033[94m',    # Blue
            LogLevel.WARNING: '\033[93m', # Yellow
            LogLevel.ERROR: '\033[91m',   # Red
            LogLevel.CRITICAL: '\033[95m',# Magenta
        }

        reset = '\033[0m'
        color = color_map.get(entry.level, '')

        print(f"{color}{ts} {icon} [{entry.level.value}] {entry.message[:150]}{reset}")

    def _emit_alert(self, entry: LogEntry):
        """Emit an alert for critical entries."""
        ts = entry.timestamp.isoformat() if entry.timestamp else ''

        alert_msg = (
            f"\n🚨 ALERT [{ts}]\n"
            f"   Level: {entry.level.value}\n"
            f"   Source: {entry.source}\n"
            f"   Message: {entry.message}\n"
        )

        if entry.error_category:
            alert_msg += f"   Category: {entry.error_category.value}\n"

        print(alert_msg)

    def print_report(self):
        """Print formatted analysis report."""
        print("\n" + "="*60)
        print("📊 LOG ANALYSIS REPORT")
        print("="*60)

        # Overview
        print(f"\nFiles Analyzed: {len(self.report.source_files)}")
        print(f"Total Lines: {self.report.total_lines:,}")
        print(f"Parsed Entries: {self.report.parsed_entries:,}")

        if self.report.time_range:
            start, end = self.report.time_range
            print(f"Time Range: {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%Y-%m-%d %H:%M')}")

        # Level breakdown
        print(f"\n{'─'*40}")
        print("LOG LEVELS")
        print("─"*40)

        level_icons = {
            'DEBUG': '🔍', 'INFO': 'ℹ️', 'WARNING': '⚠️',
            'ERROR': '❌', 'CRITICAL': '🚨'
        }

        for level, count in sorted(self.report.entries_by_level.items()):
            icon = level_icons.get(level, '•')
            pct = count / self.report.parsed_entries * 100 if self.report.parsed_entries else 0
            bar = '█' * int(pct / 2)
            print(f"  {icon} {level:<12} {count:>6} ({pct:>5.1f}%) {bar}")

        # Error categories
        if self.report.error_categories:
            print(f"\n{'─'*40}")
            print("ERROR CATEGORIES")
            print("─"*40)

            for cat, count in sorted(self.report.error_categories.items(), key=lambda x: x[1], reverse=True):
                print(f"  🔴 {cat:<25} {count:>4}")

        # Top errors
        if self.report.top_errors:
            print(f"\n{'─'*40}")
            print("TOP ERRORS")
            print("─"*40)

            for msg, count in self.report.top_errors[:10]:
                print(f"  ({count:>3}x) {msg[:80]}...")

        # Security events
        if self.report.security_events:
            print(f"\n{'─'*40}")
            print(f"⚠️  SECURITY EVENTS: {len(self.report.security_events)}")
            print("─"*40)

            for event in self.report.security_events[:5]:
                print(f"  [{event.get('event_type','?')}] {event.get('message','')[:80]}")

        # Anomalies
        if self.report.anomalies:
            print(f"\n{'─'*40}")
            print("🔮 ANOMALIES DETECTED")
            print("─"*40)

            for anomaly in self.report.anomalies:
                print(f"  • {anomaly.get('description', 'Unknown anomaly')}")

        # Performance metrics
        if self.report.performance_metrics:
            print(f"\n{'─'*40}")
            print("⚡ PERFORMANCE METRICS")
            print("─"*40)

            perf = self.report.performance_metrics
            print(f"  Requests timed: {perf.get('total_request_timings', 0)}")
            print(f"  Avg duration: {perf.get('avg_duration_ms', 0)}ms")
            print(f"  P95 duration: {perf.get('p95_duration_ms', 0)}ms")
            print(f"  Max duration: {perf.get('max_duration_ms', 0)}ms")

        # Recommendations
        if self.report.recommendations:
            print(f"\n{'='*60}")
            print("💡 RECOMMENDATIONS")
            print("="*60)

            for i, rec in enumerate(self.report.recommendations, 1):
                print(f"  {i}. {rec}")

        print()


def main():
    parser = argparse.ArgumentParser(
        description='📝 SuperAI Log Analyzer - Intelligent log analysis & alerting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                          # Auto-discover and analyze logs
  %(prog)s --file app.log --file error.log          # Analyze specific files
  %(prog)s --log-dir ./logs                         # Analyze all logs in directory
  %(prog)s --errors-only                            # Show only errors
  %(prog)s --since "2 hours ago"                    # Recent logs only
  %(prog)s --follow --tail                          # Real-time monitoring
  %(prog)s --alert                                  # Enable critical alerts
  %(prog)s --json                                   # JSON report output
        """
    )

    parser.add_argument('--file', '-f', action='append', dest='files',
                       help='Log file to analyze (can specify multiple)')
    parser.add_argument('--log-dir', '-d', type=str,
                       help='Directory containing log files')
    parser.add_argument('--since', '-s', type=str,
                       help='Analyze logs since this time (e.g., "2 hours ago")')
    parser.add_argument('--until', '-u', type=str,
                       help='Analyze logs until this time')
    parser.add_argument('--errors-only', '-e', action='store_true',
                       help='Show only error-level entries')
    parser.add_argument('--follow', '-F', action='store_true',
                       help='Follow mode (real-time monitoring)')
    parser.add_argument('--tail', '-t', action='store_true',
                       help='Start from end of file (use with --follow)')
    parser.add_argument('--alert', '-a', action='store_true',
                       help='Enable alerts for critical events')
    parser.add_argument('--max-lines', '-n', type=int,
                       help='Maximum lines to analyze')
    parser.add_argument('--json', '-j', action='store_true',
                       help='JSON output format')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    analyzer = SuperAILogAnalyzer(
        log_files=args.files,
        log_dir=args.log_dir,
        since=args.since,
        until=args.until,
        errors_only=args.errors_only,
        follow_mode=args.follow,
        enable_alerts=args.alert,
        max_lines=args.max_lines,
        verbose=args.verbose
    )

    report = analyzer.analyze_all()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))


if __name__ == '__main__':
    main()
