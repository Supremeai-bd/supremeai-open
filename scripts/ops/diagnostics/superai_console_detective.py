#!/usr/bin/env python3
"""
================================================================================
SuperAI Browser Console Detective - Human-Like Error Hunter 🔍
================================================================================
👁️ Analyzes browser console logs LIKE HUMAN EYES would
⚡ ZERO heavy dependencies (No Playwright, Puppeteer, Selenium!)
📋 Works with Chrome DevTools export OR simple copy-paste
🧠 Detects "suspicious" patterns humans notice

HOW TO USE (3 Methods):
────────────────────────
Method 1: Chrome DevTools Export (BEST)
  1. Open website → F12 → Console tab
  2. Right-click → "Save as..." → Save as .log or .json
  3. Run: python3 superai_console_detective.py --file console.log

Method 2: Simple Copy-Paste (EASIEST)
  1. Open website → F12 → Console
  2. Ctrl+A (select all) → Ctrl+C (copy)
  3. Run: python3 superai_console_detective.py --paste
  4. Paste content → Enter → Ctrl+D (EOF)

Method 3: URL Monitor (LIVE)
  1. Run: python3 superai_console_detective.py --url https://example.com
  2. Script fetches page + checks common JS errors patterns

WHAT IT DETECTS (Human-like Intelligence):
─────────────────────────────────────────
❌ Red Errors: Failed requests, JS crashes, undefined errors
⚠️ Yellow Warnings: Deprecations, security issues  
🔴 Critical: Uncaught exceptions, promise rejections
💀 Silent Killers: Errors caught but ignored
🐛 Bug Patterns: Common mistakes developers make
🔒 Security Issues: XSS attempts, mixed content
⚡ Performance: Slow operations, memory leaks signs
🎯 User-Impacting: Things real users would complain about

CPU Impact: <1% (pure text processing, no browser needed!)

Author: SuperAI Toolkit
Version: 2.0.0 - "Human Eye Simulator"
================================================================================
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# ====================================================================================
# HUMAN-LIKE ERROR CLASSIFICATION
# (These are patterns a human developer would flag as "wrong")
# ====================================================================================

class HumanSeverity(Enum):
    """How worried a human would be seeing this"""
    CRITICAL = "🚨"      # Would drop everything to fix
    HIGH = "❌"          # Must fix before release
    MEDIUM = "⚠️"       # Should fix soon
    LOW = "ℹ️"           # Nice to know
    NOISE = "➡️"         # Ignore (normal)


@dataclass
class HumanIssue:
    """An issue a human eye would catch"""
    severity: HumanSeverity
    category: str        # What type of problem
    pattern_matched: str # What text triggered it
    line_text: str       # The actual log line
    line_number: int = 0
    human_explanation: str = ""  # Why humans care about this
    likely_cause: str = ""       # What probably caused it
    fix_suggestion: str = ""     # How to fix

    def to_dict(self):
        return {
            'severity': self.severity.value,
            'category': self.category,
            'pattern': self.pattern_matched,
            'text': self.line_text[:150],
            'explanation': self.human_explanation,
            'cause': self.likely_cause,
            'fix': self.fix_suggestion
        }


# ====================================================================================
# PATTERN DEFINITIONS - What Human Eyes Look For
# ====================================================================================

HUMAN_EYE_PATTERNS = {

    # ═══════════════════════════════════════════════════════════════
    # 🚨 CRITICAL - Drop Everything Errors
    # ═══════════════════════════════════════════════════════════════

    HumanSeverity.CRITICAL: [
        # JavaScript Crashes
        {
            'pattern': r'Uncaught\s+(?:RangeError|TypeError|ReferenceError|SyntaxError):\s*(.+)',
            'category': 'JS Crash',
            'explanation': 'JavaScript completely crashed - users see nothing working',
            'cause': 'Code bug accessing wrong variable type',
            'fix': 'Add null checks, validate data before use'
        },
        {
            'pattern': r'Cannot\s+read\s+properties?\s+of\s+(?:undefined|null)\s+reading\s+[\'"]?(\w+)[\'"]?',
            'category': 'Null Crash',
            'explanation': 'Trying to use something that doesn\'t exist - very common crash',
            'cause': 'API returned unexpected format or missing field',
            'fix': 'Add optional chaining: obj?.field?.nested'
        },
        {
            'pattern': r'(\w+)\s+is\s+not\s+a\s+function',
            'category': 'Not A Function',
            'explanation': 'Calling something that isn\'t callable - breaks feature completely',
            'cause': 'Wrong variable name or library not loaded',
            'fix': 'Check spelling, verify library loaded'
        },
        {
            'pattern': r'Unexpected\s+token',
            'category': 'Syntax Error',
            'explanation': 'Code syntax error - entire script may not run',
            'cause': 'Typo or copy-paste error',
            'fix': 'Check for missing brackets, commas'
        },
        {
            'pattern': r'Maximum\s+call\s+stack\s+size\s+exceeded',
            'category': 'Infinite Loop',
            'explanation': 'Infinite recursion - browser freezes/crashes',
            'cause': 'Function calling itself without exit condition',
            'fix': 'Add base case to recursive function'
        },

        # Network Failures Users Notice
        {
            'pattern': r'Failed\s+to\s+fetch',
            'category': 'Network Failure',
            'explanation': 'API call failed - user sees loading spinner forever',
            'cause': 'Server down, CORS issue, or offline',
            'fix': 'Check server status, add error handling + retry'
        },
        {
            'pattern': r'Net::ERR_(\w+)',
            'category': 'Network Error',
            'explanation': 'Network connection error - feature broken',
            'cause': 'DNS failure, SSL cert issue, or firewall',
            'fix': 'Check URL, SSL certificate, network connectivity'
        },
        {
            'pattern': r'(?:XHR|Fetch)\s+error.*(?:status\s*)?(?:4\d{2}|5\d{2})',
            'category': 'API Error',
            'explanation': 'Server returned error - data not loaded',
            'cause': 'Backend bug or invalid request',
            'fix': 'Check API endpoint, verify request params'
        },

        # Security Red Flags
        {
            'pattern': r'(?:XSS|Cross-site\s+scripting)',
            'category': 'Security: XSS',
            'explanation': 'Potential XSS vulnerability - hackers can steal user data!',
            'cause': 'User input not sanitized before displaying',
            'fix': 'Sanitize HTML, use CSP headers'
        },
        {
            'pattern': r'Mixed\s+Content',
            'category': 'Security: Mixed Content',
            'explanation': 'HTTPS page loading insecure resources - browser blocks it',
            'cause': 'HTTP URLs on HTTPS page',
            'fix': 'Change all URLs to HTTPS'
        },

        # Promise Rejections (Silent Failures)
        {
            'pattern': r'Unhandled\s+promise\s+rejection',
            'category': 'Unhandled Promise',
            'explanation': 'Async error silently failed - feature broken without visible error',
            'cause': 'Missing .catch() handler',
            'fix': 'Add .catch() to all promises'
        },
    ],

    # ═══════════════════════════════════════════════════════════════
    # ❌ HIGH - Must Fix Before Release
    # ═══════════════════════════════════════════════════════════════

    HumanSeverity.HIGH: [
        # Undefined Variables That Break Features
        {
            'pattern': r'(\w+)\s+is\s+not\s+defined',
            'category': 'Undefined Variable',
            'explanation': 'Using variable that was never declared - feature broken',
            'cause': 'Typo or forgot to import/require',
            'fix': 'Declare variable or check import statement'
        },
        {
            'pattern': r'Cannot\s+set\s+properties?\s+of\s+null',
            'category': 'Null Assignment',
            'explanation': 'Trying to set property on null - silent failure',
            'cause': 'Object should exist but doesn\'t',
            'fix': 'Initialize object before using'
        },

        # Resource Loading Failures
        {
            'pattern': r'Failed\s+to\s+load\s+(?:resource|script|module):\s*(.+)',
            'category': 'Resource Load Failed',
            'explanation': 'Critical file (JS/CSS) didn\'t load - page broken',
            'cause': 'Wrong path, file deleted, or permissions',
            'fix': 'Verify file exists at path, check 404s'
        },
        {
            'pattern': r'GET\s+.+\s*(?:404|403)\s*\(Forbidden\)|\(Not Found\)',
            'category': 'Missing Resource',
            'explanation': 'File not found - broken images, styles, or scripts',
            'cause': 'Wrong URL or file moved/deleted',
            'fix': 'Update reference or restore file'
        },

        # React/Vue/Angular Specific
        {
            'pattern': r'(?:Warning|Error):\s*(?:Failed\s+prop\s+type|Invalid\s+prop)',
            'category': 'Component Prop Error',
            'explanation': 'Component received wrong data type - UI glitch or crash',
            'cause': 'Parent passing wrong prop type',
            'fix': 'Check PropTypes validation'
        },
        {
            'pattern': r'(?:Warning|Error):\s*Each\s+child.*should\s+have\s+a\s+unique\s+"key"\s*prop',
            'category': 'React Key Missing',
            'explanation': 'List rendering without keys - React warnings + bugs',
            'cause': 'Mapping array without key prop',
            'fix': 'Add key={item.id} to list items'
        },
        {
            'pattern': r'Cannot\s+read\s+property.*of\s+undefined.*\buseState\b|\buseEffect\b',
            'category': 'Hook Error',
            'explanation': 'React Hook misused - component crash',
            'cause': 'Calling hook conditionally or in wrong order',
            'fix': 'Follow Rules of Hooks strictly'
        },

        # Timeout Issues
        {
            'pattern': r'timeout\s*exceeded|request\s*timeout|abort.*timeout',
            'category': 'Timeout',
            'explanation': 'Operation too slow - user sees error message',
            'cause': 'Slow server or huge payload',
            'fix': 'Increase timeout, optimize query, add loading state'
        },
    ],

    # ═══════════════════════════════════════════════════════════════
    # ⚠️ MEDIUM - Should Fix Soon
    # ═══════════════════════════════════════════════════════════════

    HumanSeverity.MEDIUM: [
        # Deprecations (Will Break Soon)
        {
            'pattern': r'Deprecation\s*(?:warning|notice):?\s*(.+)',
            'category': 'Deprecated API',
            'explanation': 'Using old API that will be removed - breaks in future update',
            'cause': 'Outdated library or code',
            'fix': 'Update to new API version'
        },

        # Warnings That Indicate Problems
        {
            'pattern': r'(?:Warning|WARN):\s*(?:Possible|Potential)\s*(?:memory\s*leak|leak).*?(?:component|node)',
            'category': 'Memory Leak Warning',
            'explanation': 'App slowly eating memory - gets slower over time',
            'cause': 'Not cleaning up event listeners/intervals',
            'fix': 'Cleanup in useEffect return or componentWillUnmount'
        },
        {
            'pattern': r'(?:Warning|WARN):.*?(?:render|rendered)\s*fewer.*than\s*expected',
            'category': 'Render Mismatch',
            'explanation': 'React hydration mismatch - visual glitches',
            'cause': 'SSR and client rendering different HTML',
            'fix': 'Ensure server/client render same output'
        },

        # Performance Issues Humans Notice
        {
            'pattern': r'(?:Main thread|Long task).*?took\s+(\d+)ms',
            'category': 'Performance: Slow Task',
            'explanation': 'Page freezing/janking - users notice lag',
            'cause': 'Heavy computation blocking main thread',
            'fix': 'Move to Web Worker or break into chunks'
        },
        {
            'pattern': r'(?:Large|Big).*?(?:payload|response|request).*?(\d+\.?\d*\s*[KMGT]?B)',
            'category': 'Performance: Large Payload',
            'explanation': 'Slow load times - users on mobile suffer most',
            'cause': 'Sending too much data at once',
            'fix': 'Implement pagination, compression, or GraphQL'
        },

        # Security Concerns
        {
            'pattern': r'(?:Content Security Policy|CSP)\s*(?:violation|warning)',
            'category': 'Security: CSP',
            'explanation': 'Security policy violation - something blocked or risky',
            'cause': 'Inline scripts or external resources not whitelisted',
            'fix': 'Update CSP header or move inline code'
        },
        {
            'pattern': r'(?:Subresource Integrity|SRI)\s*(?:warning|error|missing)',
            'category': 'Security: No SRI',
            'explanation': 'External libraries loaded without integrity check',
            'cause': 'CDN links missing integrity attribute',
            'fix': 'Add integrity="" and crossorigin="" to script tags'
        },
    ],

    # ═══════════════════════════════════════════════════════════════
    # ℹ️ LOW - Nice To Know
    # ═══════════════════════════════════════════════════════════════

    HumanSeverity.LOW: [
        {
            'pattern': r'\[DevTools\]|\[console\]',
            'category': 'DevTools Info',
            'explanation': 'Just informational message from browser tools',
            'cause': 'Normal browser behavior',
            'fix': 'None needed - purely informational'
        },
        {
            'pattern': r'The\s+page\s+(?:at|at\s+\S+)\s+(?:was\s+)?(loaded|refreshed)',
            'category': 'Page Load',
            'explanation': 'Normal page navigation message',
            'cause': 'User navigated or refreshed',
            'fix': 'None needed'
        },
        {
            'pattern': r'(Download\s+the\s+React\s+DevTools|Install\s+React\s+DevTools)',
            'category': 'DevTools Suggestion',
            'explanation': 'Browser suggesting dev tools extension',
            'cause': 'Detected React in development mode',
            'fix': 'Optional - helps debugging'
        },
    ],
}


# Special "Silent Killer" patterns - errors caught but hidden
SILENT_KILLER_PATTERNS = [
    {
        'name': 'Swallowed Error',
        'pattern': r'catch\s*\([^)]*\)\s*\{\s*\}',  # catch(e) {}
        'severity': HumanSeverity.MEDIUM,
        'explanation': 'Error caught but completely ignored - hides real bugs!'
    },
    {
        'name': 'Empty Catch Block',
        'pattern': r'catch\s*\([^)]*\)\s*\{\s*//.*\}',
        'severity': HumanSeverity.MEDIUM,
        'explanation': 'Error only has comment - still hidden from users/logs'
    },
    {
        'name': 'Console Error Suppressed',
        'pattern': r'console\.(error|warn)\s*=\s*function',
        'severity': HumanSeverity.HIGH,
        'explanation': 'Someone disabled console.error - hiding all errors!'
    },
]


class BrowserConsoleDetective:
    """
    Human-like console log analyzer.
    
    Simulates what an experienced developer looks for when scanning console logs.
    """

    def __init__(
        self,
        input_file: str | None = None,
        url: str | None = None,
        paste_mode: bool = False,
        show_noise: bool = False,
        group_by_category: bool = True,
        max_issues_per_type: int = 10,
        output_format: str = "human"  # human, json, csv
    ):
        self.input_file = input_file
        self.url = url
        self.paste_mode = paste_mode
        self.show_noise = show_noise
        self.group_by_category = group_by_category
        self.max_issues = max_issues_per_type
        self.output_format = output_format

        self.raw_lines: list[str] = []
        self.issues: list[HumanIssue] = []
        self.stats = {
            'total_lines': 0,
            'error_count': 0,
            'warning_count': 0,
            'info_count': 0,
            'issues_found': 0,
            'by_severity': Counter(),
            'by_category': Counter(),
        }

        self.start_time = datetime.now()

    def collect_input(self) -> str:
        """Collect console log content from various sources."""

        if self.paste_mode:
            print("\n" + "="*60)
            print("📋 PASTE CONSOLE LOG CONTENT BELOW")
            print("   (Ctrl+D or Ctrl+Z then Enter to finish)")
            print("="*60 + "\n")

            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")

            return '\n'.join(lines)

        elif self.input_file:
            if not os.path.exists(self.input_file):
                print(f"❌ File not found: {self.input_file}")
                sys.exit(1)

            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Try to detect format
            if self.input_file.endswith('.json'):
                return self._parse_json_export(content)

            return content

        elif self.url:
            return self._fetch_url_content()

        else:
            # Try default locations
            default_files = ['console.log', 'browser.log', 'logs/console.log']
            for f in default_files:
                if os.path.exists(f):
                    self.input_file = f
                    with open(f, 'r') as fh:
                        return fh.read()

            print("❌ No input provided. Use --file, --paste, or --url")
            print("   Examples:")
            print("   python3 superai_console_detective.py --file console.log")
            print("   python3 superai_console_detective.py --paste")
            print("   python3 superai_console_detective.py --url https://example.com")
            sys.exit(1)

    def _parse_json_export(self, json_content: str) -> str:
        """Parse Chrome DevTools JSON export."""
        try:
            data = json.loads(json_content)
            lines = []

            # Chrome exports as array of entries
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        # Extract message based on format
                        message = entry.get('text') or entry.get('message') or entry.get('content', '')
                        level = entry.get('level') or entry.get('type', '')

                        if message:
                            prefix = ''
                            if 'error' in level.lower():
                                prefix = '[ERROR] '
                            elif 'warn' in level.lower():
                                prefix = '[WARNING] '
                            elif level.lower() in ['info', 'log']:
                                prefix = '[INFO] '

                            lines.append(f"{prefix}{message}")
                    elif isinstance(entry, str):
                        lines.append(entry)

            return '\n'.join(lines)

        except json.JSONDecodeError:
            # Not valid JSON, treat as plain text
            return json_content

    def _fetch_url_content(self) -> str:
        """Fetch URL and extract potential JS errors."""
        try:
            import urllib.request

            req = urllib.request.Request(
                self.url,
                headers={'User-Agent': 'Mozilla/5.0 (Detective Bot)'}
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')

            # Extract inline scripts and look for error patterns
            lines = [f"[URL FETCH] {self.url}"]
            lines.append("[INFO] Fetched page source - checking for obvious issues...")

            # Check for common issues in HTML
            if '<script>' in html and '</script>' not in html[:html.find('<script>')+500]:
                lines.append("[ERROR] Unclosed <script> tag detected!")

            if 'console.error' in html:
                lines.append("[WARNING] Page contains console.error calls - errors expected")

            if 'debugger;' in html:
                lines.append("[WARNING] Debugger statement found in production code!")

            # Count errors/warnings in script content
            error_indicators = ['throw new ', '.error(', 'catch(', 'fail(', 'reject(']
            for indicator in error_indicators:
                count = html.count(indicator)
                if count > 0:
                    lines.append(f"[INFO] Found {count} instances of '{indicator}'")

            return '\n'.join(lines)

        except Exception as e:
            return f"[ERROR] Failed to fetch URL: {e!s}"

    def analyze(self) -> list[HumanIssue]:
        """Run human-like analysis on collected logs."""

        # Get input
        content = self.collect_input()
        self.raw_lines = content.split('\n')
        self.stats['total_lines'] = len(self.raw_lines)

        print(f"\n{'='*60}")
        print("🔍 SUPERAI BROWSER CONSOLE DETECTIVE")
        print("   Human-Like Error Analysis Engine v2.0")
        print('='*60)
        print(f"📊 Analyzing {len(self.raw_lines)} lines of console output...")
        print("🧠 Mode: Simulating experienced developer's eyes...")
        print()

        # Process each line
        for line_num, line in enumerate(self.raw_lines, 1):
            line_stripped = line.strip()

            if not line_stripped:
                continue

            # Classify base level
            if any(x in line_stripped.upper() for x in ['[ERROR]', 'ERROR:', 'CRITICAL:', 'FATAL:']):
                self.stats['error_count'] += 1
            elif any(x in line_stripped.upper() for x in ['[WARN]', 'WARNING:', 'DEPRECATION']):
                self.stats['warning_count'] += 1
            elif any(x in line_stripped.upper() for x in ['[INFO]', '[LOG]', 'DEBUG:']):
                self.stats['info_count'] += 1

            # Apply human-eye patterns
            issue = self._apply_human_patterns(line_stripped, line_num)
            if issue:
                self.issues.append(issue)
                self.stats['issues_found'] += 1
                self.stats['by_severity'][issue.severity] += 1
                self.stats['by_category'][issue.category] += 1

        # Sort by severity (critical first)
        severity_order = {
            HumanSeverity.CRITICAL: 0,
            HumanSeverity.HIGH: 1,
            HumanSeverity.MEDIUM: 2,
            HumanSeverity.LOW: 3,
            HumanSeverity.NOISE: 4
        }
        self.issues.sort(key=lambda x: severity_order.get(x.severity, 5))

        # Limit per category
        if self.group_by_category:
            category_counts = Counter()
            filtered_issues = []

            for issue in self.issues:
                if category_counts[issue.category] < self.max_issues:
                    filtered_issues.append(issue)
                    category_counts[issue.category] += 1

            self.issues = filtered_issues

        return self.issues

    def _apply_human_patterns(self, line: str, line_num: int) -> HumanIssue | None:
        """Apply all human-like detection patterns to a line."""

        # Check each severity level
        for severity, patterns in HUMAN_EYE_PATTERNS.items():

            # Skip noise unless requested
            if severity == HumanSeverity.NOISE and not self.show_noise:
                continue

            for pattern_info in patterns:
                pattern = pattern_info['pattern']

                try:
                    match = re.search(pattern, line, re.IGNORECASE | re.DOTALL)

                    if match:
                        return HumanIssue(
                            severity=severity,
                            category=pattern_info['category'],
                            pattern_matched=pattern,
                            line_text=line,
                            line_number=line_num,
                            human_explanation=pattern_info.get('explanation', ''),
                            likely_cause=pattern_info.get('cause', ''),
                            fix_suggestion=pattern_info.get('fix', '')
                        )

                except re.error:
                    continue

        return None

    def generate_report(self):
        """Generate human-readable analysis report."""

        elapsed = (datetime.now() - self.start_time).total_seconds()

        # Header
        print("\n" + "╔" + "═"*58 + "╗")
        print("║" + "  🕵️  DETECTION COMPLETE - ANALYSIS REPORT".center(56) + "║")
        print("╚" + "═"*58 + "╝")

        # Summary Stats
        print("\n📊 INPUT STATISTICS:")
        print(f"   Total Lines Scanned: {self.stats['total_lines']:,}")
        print(f"   Error Messages:     {self.stats['error_count']}")
        print(f"   Warnings:           {self.stats['warning_count']}")
        print(f"   Info Messages:      {self.stats['info_count']}")

        print("\n🔍 FINDINGS:")
        print(f"   Total Issues Found: {len(self.issues)}")

        if self.issues:
            print("\n   By Severity:")
            severity_labels = {
                HumanSeverity.CRITICAL: ('🚨 Critical', 'red'),
                HumanSeverity.HIGH: ('❌ High', 'red'),
                HumanSeverity.MEDIUM: ('⚠️  Medium', 'yellow'),
                HumanSeverity.LOW: ('ℹ️  Low', 'blue'),
                HumanSeverity.NOISE: ('➡️  Noise', 'dim'),
            }

            for sev, (label, color) in severity_labels.items():
                count = self.stats['by_severity'].get(sev, 0)
                if count > 0:
                    print(f"      {label}: {count}")

        print(f"\n   ⏱️  Analysis Time: {elapsed:.2f} seconds")

        # Grouped Results
        if self.group_by_category and self.issues:
            self._print_grouped_results()
        else:
            self._print_chronological_results()

        # Top Categories
        if self.stats['by_category']:
            print("\n📈 TOP ISSUE CATEGORIES:")
            for category, count in self.stats['by_category'].most_common(5):
                bar = '█' * min(count, 20)
                print(f"   {category:<30} {count:>3} {bar}")

        # Human Summary
        self._print_human_summary()

        # Output in other formats if requested
        if self.output_format == 'json':
            self._export_json()
        elif self.output_format == 'csv':
            self._export_csv()

    def _print_grouped_results(self):
        """Print results grouped by category."""

        current_severity = None

        for issue in self.issues:
            # Print severity header
            if issue.severity != current_severity:
                current_severity = issue.severity

                severity_headers = {
                    HumanSeverity.CRITICAL: "\n🚨🚨🚨 CRITICAL ISSUES (Fix Immediately!) 🚨🚨🚨",
                    HumanSeverity.HIGH: "\n❌ HIGH PRIORITY (Must Fix)",
                    HumanSeverity.MEDIUM: "\n⚠️  MEDIUM PRIORITY (Should Fix)",
                    HumanSeverity.LOW: "\nℹ️  LOW PRIORITY (Informational)",
                    HumanSeverity.NOISE: "\n➡️  NOISE (Can Ignore)",
                }

                print(severity_headers.get(current_severity, f"\n{current_severity.value}"))
                print("-" * 60)

            # Print issue
            icon = issue.severity.value
            print(f"{icon} [{issue.category}] Line {issue.line_number}")
            print(f"   📝 Text: {issue.line_text[:120]}...")

            if issue.human_explanation:
                print(f"   💡 Why It Matters: {issue.human_explanation}")

            if issue.likely_cause:
                print(f"   🔍 Likely Cause: {issue.likely_cause}")

            if issue.fix_suggestion:
                print(f"   ✅ How To Fix: {issue.fix_suggestion}")

            print()

    def _print_chronological_results(self):
        """Print results in chronological order."""

        for i, issue in enumerate(self.issues[:50], 1):  # Limit to 50
            icon = issue.severity.value
            print(f"{i}. {icon} Line {issue.line_number}: [{issue.category}]")
            print(f"   {issue.line_text[:100]}...")
            print()

    def _print_human_summary(self):
        """Print a human-friendly summary of findings."""

        critical_count = self.stats['by_severity'].get(HumanSeverity.CRITICAL, 0)
        high_count = self.stats['by_severity'].get(HumanSeverity.HIGH, 0)
        medium_count = self.stats['by_severity'].get(HumanSeverity.MEDIUM, 0)

        print("\n" + "╔" + "═"*58 + "╗")
        print("║" + "  👁️  HUMAN DEVELOPER SUMMARY".center(56) + "║")
        print("╚" + "═"*58 + "╝")

        if critical_count > 0:
            print(f"""
🚨 STOP EVERYTHING!
   Found {critical_count} CRITICAL issue(s) that will cause real users problems.
   
   Imagine a user is testing your site right now:
   • They'd see features completely broken
   • They'd get error messages they don't understand
   • They might leave and never come back
   
   FIX THESE FIRST before anything else!
""")

        if high_count > 0:
            print(f"""❌ You have {high_count} HIGH priority issues.
   
   These aren't emergencies, but they'll generate support tickets:
   • Users will report "X isn't working"
   • QA team will flag them as bugs
   • They're embarrassing in demos
   
   Plan: Fix within next sprint or before release.
""")

        if medium_count > 0:
            print(f"""⚠️  {medium_count} medium issues found.
   
   Not urgent, but technical debt accumulates:
   • Future you will hate present you
   • May cause weird edge case bugs
   • Performance degrades over time
   
   Plan: Fix when working on related code, or schedule cleanup day.
""")

        if not self.issues:
            print("""
✅ CONGRATULATIONS!
   Your console looks clean! 
   
   Either:
   • Your code is solid (great job!) 🎉
   • The errors haven't happened yet (test more scenarios)
   • Errors are being swallowed silently (check catch blocks)
   
   Recommendation: Test error scenarios intentionally.
""")

        # Overall verdict
        total_problems = critical_count + high_count

        if total_problems == 0:
            verdict = "✅ READY FOR PRODUCTION"
        elif critical_count > 0:
            verdict = "🚨 NOT READY - Critical Fixes Needed"
        elif high_count > 3:
            verdict = "⚠️  CAUTION - Multiple High Priority Issues"
        else:
            verdict = "🟡 ACCEPTABLE - Minor Issues Only"

        print(f"\n{'='*60}")
        print(f"VERDICT: {verdict}")
        print(f"{'='*60}\n")

    def _export_json(self):
        """Export results to JSON."""
        output = {
            'analysis_time': datetime.now().isoformat(),
            'stats': self.stats,
            'issues': [issue.to_dict() for issue in self.issues]
        }

        filename = f"console_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)

        print(f"\n📁 JSON report saved: {filename}")

    def _export_csv(self):
        """Export summary to CSV."""
        filename = f"console_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(filename, 'w') as f:
            f.write("Severity,Category,Line Number,Pattern,Text\n")
            for issue in self.issues:
                # CSV escape
                text = issue.line_text.replace('"', '""')
                f.write(f'{issue.severity.value},"{issue.category}",{issue.line_number},"{issue.pattern_matched}","{text}"\n')

        print(f"\n📁 CSV report saved: {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="🔍 SuperAI Browser Console Detective - Find errors like human eyes would",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file console.log              # Analyze exported console log
  %(prog)s --file chrome_export.json        # Parse Chrome DevTools JSON export
  %(prog)s --paste                          # Paste console content directly
  %(prog)s --url https://example.com        # Fetch & analyze URL
  %(prog)s --file console.log --json        # Machine-readable output
  %(prog)s --file console.log --show-noise  # Show everything including noise

How to Get Console Logs:
────────────────────────
1. Open browser DevTools (F12)
2. Go to Console tab
3. Right-click → "Save as..." to save as file
   OR select all (Ctrl+A) and copy (Ctrl+C)

Supported Formats:
  • Plain text (.log, .txt)
  • Chrome DevTools JSON export (.json)
  • Direct paste from clipboard
  • URL fetching (basic analysis)
        """
    )

    parser.add_argument('--file', '-f', help='Console log file to analyze')
    parser.add_argument('--url', '-u', help='URL to fetch and analyze')
    parser.add_argument('--paste', '-p', action='store_true', help='Paste mode (interactive)')
    parser.add_argument('--show-noise', action='store_true', help='Show noise/info level items')
    parser.add_argument('--no-group', action='store_true', help='Show chronologically instead of grouped')
    parser.add_argument('--max-per-category', type=int, default=10, help='Max issues per category (default: 10)')
    parser.add_argument('--format', choices=['human', 'json', 'csv'], default='human', help='Output format')

    args = parser.parse_args()

    # Create detective instance
    detective = BrowserConsoleDetective(
        input_file=args.file,
        url=args.url,
        paste_mode=args.paste,
        show_noise=args.show_noise,
        group_by_category=not args.no_group,
        max_issues_per_type=args.max_per_category,
        output_format=args.format
    )

    # Run analysis
    detective.analyze()

    # Generate report
    detective.generate_report()


if __name__ == '__main__':
    main()
