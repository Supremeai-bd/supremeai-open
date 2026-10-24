#!/usr/bin/env python3
"""
RTL Support Checker
Validates RTL (Right-to-Left) language support in CSS/HTML.
Priority: 🟢 Low
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Bangla character regex for detection
BANGLA_REGEX = re.compile(r'[\u0980-\u09FF]')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# RTL languages
RTL_LANGUAGES = {
    'ar': 'Arabic',
    'he': 'Hebrew',
    'fa': 'Persian/Farsi',
    'ur': 'Urdu',
    'ps': 'Pashto',
    'sd': 'Sindhi',
    'ku': 'Kurdish',
    'dv': 'Dhivehi',
    'bn': 'Bangla',
    'as': 'Assamese',
    'mni': 'Manipuri/Meitei',
}

# RTL CSS properties to check
RTL_CSS_PROPERTIES = [
    'direction',
    'text-align',
    'float',
    'clear',
    'margin-left',
    'margin-right',
    'padding-left',
    'padding-right',
    'border-left',
    'border-right',
    'left',
    'right',
]

# Required RTL properties
REQUIRED_RTL_PROPERTIES = {
    'direction: rtl': 'Sets text direction to RTL',
    'text-align: right': 'Aligns text to the right for RTL',
}


@dataclass
class RTLCheckResult:
    """Result of RTL support check."""
    file_path: str
    line_number: int
    issue_type: str
    property_name: str
    message: str
    suggestion: str


@dataclass
class RTLReport:
    """Complete RTL validation report."""
    timestamp: datetime
    files_checked: int
    total_issues: int
    rtl_issues: list[RTLCheckResult]
    ltr_issues: list[RTLCheckResult]
    summary: dict[str, Any]


class RTLSupportChecker:
    """
    Checks for RTL language support in web applications.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.project_path = Path(config.get('project_path', '.'))
        self.rtl_issues: list[RTLCheckResult] = []
        self.ltr_issues: list[RTLCheckResult] = []

    def _is_rtl_language(self, lang_code: str) -> bool:
        """Check if language is RTL."""
        return lang_code.lower() in RTL_LANGUAGES

    def _check_css_for_rtl(self, content: str, file_path: str) -> list[RTLCheckResult]:
        """Check CSS content for RTL compatibility."""
        issues = []
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # Check for hardcoded LTR values that should be RTL-aware
            if 'margin-left:' in line or 'margin-right:' in line:
                if 'rtl' not in line.lower() and '!important' not in line:
                    issues.append(RTLCheckResult(
                        file_path=file_path,
                        line_number=i,
                        issue_type='margin_direction',
                        property_name='margin',
                        message="Hardcoded margin direction may cause RTL issues",
                        suggestion="Use logical properties (margin-inline-start, margin-inline-end)"
                    ))

            if 'padding-left:' in line or 'padding-right:' in line:
                if 'rtl' not in line.lower():
                    issues.append(RTLCheckResult(
                        file_path=file_path,
                        line_number=i,
                        issue_type='padding_direction',
                        property_name='padding',
                        message="Hardcoded padding direction may cause RTL issues",
                        suggestion="Use logical properties (padding-inline-start, padding-inline-end)"
                    ))

            # Check for float direction issues
            if 'float: left' in line or 'float: right' in line:
                issues.append(RTLCheckResult(
                    file_path=file_path,
                    line_number=i,
                    issue_type='float_direction',
                    property_name='float',
                    message="Hardcoded float direction may cause RTL issues",
                    suggestion="Consider using flexbox or grid for RTL-compatible layouts"
                ))

        return issues

    def _check_html_for_rtl(self, content: str, file_path: str) -> list[RTLCheckResult]:
        """Check HTML content for RTL attributes."""
        issues = []
        lines = content.split('\n')


        for i, line in enumerate(lines, 1):
            # Check for lang attribute with RTL language
            if re.search(r'lang=["\'](ar|he|fa|ur|ps|sd|ku|dv|bn|as)', line, re.IGNORECASE):
                pass

            # Check for dir="rtl"
            if 'dir="rtl"' in line or "dir='rtl'" in line:
                pass

            # Check for missing lang attribute on RTL content
            if BANGLA_REGEX.search(line):
                if not re.search(r'lang=["\']', line) and 'dir=' not in line:
                    issues.append(RTLCheckResult(
                        file_path=file_path,
                        line_number=i,
                        issue_type='missing_rtl_attrs',
                        property_name='lang/dir',
                        message="Bangla content found without RTL attributes",
                        suggestion='Add lang="bn" and dir="rtl" attributes to parent element'
                    ))

        return issues

    def _check_javascript_for_rtl(self, content: str, file_path: str) -> list[RTLCheckResult]:
        """Check JavaScript for RTL-related logic."""
        issues = []
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # Check for hardcoded text direction
            if re.search(r'(textDirection|direction)["\']\s*=\s*["\']ltr["\']', line):
                issues.append(RTLCheckResult(
                    file_path=file_path,
                    line_number=i,
                    issue_type='hardcoded_direction',
                    property_name='textDirection',
                    message="Hardcoded LTR direction detected",
                    suggestion="Make direction dynamic based on locale"
                ))

        return issues

    def check_file(self, file_path: str) -> list[RTLCheckResult]:
        """Check a single file for RTL issues."""
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File not found: {file_path}")
            return []

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return []

        suffix = path.suffix.lower()

        if suffix == '.css':
            return self._check_css_for_rtl(content, file_path)
        elif suffix in ['.html', '.htm', '.jsx', '.tsx']:
            return self._check_html_for_rtl(content, file_path)
        elif suffix in ['.js', '.ts']:
            return self._check_javascript_for_rtl(content, file_path)

        return []

    def check_directory(self, dir_path: str) -> RTLReport:
        """Check all files in a directory for RTL support."""
        path = Path(dir_path)
        if not path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return RTLReport(
                timestamp=datetime.now(),
                files_checked=0,
                total_issues=0,
                rtl_issues=[],
                ltr_issues=[],
                summary={"error": "Directory not found"}
            )

        all_issues = []
        files_checked = 0

        for ext in ['*.css', '*.html', '*.js', '*.ts', '*.jsx', '*.tsx']:
            for file_path in path.rglob(ext):
                issues = self.check_file(str(file_path))
                all_issues.extend(issues)
                files_checked += 1

        # Categorize issues
        rtl_issues = [i for i in all_issues if i.issue_type in ['missing_rtl_attrs', 'hardcoded_direction']]
        ltr_issues = [i for i in all_issues if i.issue_type in ['margin_direction', 'padding_direction', 'float_direction']]

        self.rtl_issues.extend(rtl_issues)
        self.ltr_issues.extend(ltr_issues)

        return RTLReport(
            timestamp=datetime.now(),
            files_checked=files_checked,
            total_issues=len(all_issues),
            rtl_issues=rtl_issues,
            ltr_issues=ltr_issues,
            summary={
                'total_files_checked': files_checked,
                'total_issues': len(all_issues),
                'rtl_specific_issues': len(rtl_issues),
                'layout_issues': len(ltr_issues),
                'status': 'PASSED' if len(all_issues) == 0 else 'NEEDS_REVIEW'
            }
        )

    def generate_report(self, check_result: RTLReport) -> dict[str, Any]:
        """Generate JSON report."""
        return {
            'timestamp': check_result.timestamp.isoformat(),
            'files_checked': check_result.files_checked,
            'total_issues': check_result.total_issues,
            'summary': check_result.summary,
            'rtl_issues': [
                {
                    'file': i.file_path,
                    'line': i.line_number,
                    'type': i.issue_type,
                    'property': i.property_name,
                    'message': i.message,
                    'suggestion': i.suggestion
                }
                for i in check_result.rtl_issues
            ],
            'layout_issues': [
                {
                    'file': i.file_path,
                    'line': i.line_number,
                    'type': i.issue_type,
                    'property': i.property_name,
                    'message': i.message,
                    'suggestion': i.suggestion
                }
                for i in check_result.ltr_issues
            ]
        }

    def save_report(self, report: dict[str, Any], output_path: str | None = None) -> str:
        """Save report to file."""
        output = Path(output_path or 'rtl_reports')
        output.mkdir(exist_ok=True)

        report_file = output / f"rtl_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"RTL report saved to: {report_file}")
        return str(report_file)


def main():
    """Main entry point for RTL checking."""
    import argparse

    parser = argparse.ArgumentParser(description="Check RTL language support")
    parser.add_argument('--path', required=True, help='Path to check')
    parser.add_argument('--output', default='rtl_reports', help='Output directory')

    args = parser.parse_args()

    checker = RTLSupportChecker({'project_path': args.path})
    result = checker.check_directory(args.path)
    report = checker.generate_report(result)

    report_path = checker.save_report(report, args.output)

    print("\nRTL Support Check Results:")
    print(f"  Files checked: {report['files_checked']}")
    print(f"  Total issues: {report['total_issues']}")
    print(f"  Status: {report['summary']['status']}")

    if report['total_issues'] > 0:
        print(f"\n⚠️ Found {report['total_issues']} potential RTL issues!")
        print(f"See full report: {report_path}")


if __name__ == "__main__":
    main()
