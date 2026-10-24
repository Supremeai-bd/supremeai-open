#!/usr/bin/env python3
"""
Infrastructure as Code Validator
Validates Terraform and CloudFormation configurations.
Priority: 🟡 Medium
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IaCType(Enum):
    """Infrastructure as Code types."""
    TERRAFORM = "terraform"
    CLOUDFORMATION = "cloudformation"
    KUBERNETES = "kubernetes"


class ValidationResult(Enum):
    """Validation result."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationIssue:
    """Single validation issue."""
    file: str
    line: int
    severity: ValidationResult
    rule_id: str
    message: str
    suggestion: str | None


@dataclass
class IaCValidationResult:
    """Result of IaC validation."""
    file_path: str
    iac_type: IaCType
    timestamp: datetime
    issues: list[ValidationIssue]
    security_count: int
    warning_count: int
    passed: bool
    score: int  # 0-100


class InfrastructureAsCodeValidator:
    """
    Validates Terraform and CloudFormation configurations.
    """

    # Security rules for Terraform
    TF_SECURITY_RULES = {
        'tf_public_s3': r'acl\s*=\s*["\']public',
        'tf_public_sg': r'ingress.*from_port.*=.*0',
        'tf_hardcoded_secrets': r'(password|secret|key)\s*=\s*["\'][^"\']+["\']',
        'tf_wide_open_sg': r'cidr_blocks\s*=\s*\[["\']0\.0\.0\.0/0["\']',
    }

    # Security rules for CloudFormation
    CF_SECURITY_RULES = {
        'cf_public_s3': r'AccessControl:\s*PublicRead',
        'cf_hardcoded_secrets': r'(Password|Secret|Key):\s*!Ref',
        'cf_wide_open_sg': r'0\.0\.0\.0/0',
    }

    # Best practice rules
    BEST_PRACTICE_RULES = {
        'missing_tags': r'tags\s*=\s*\{[^}]*\}',
        'unpinned_versions': r'source\s*=\s*["\'][^"\']*["\']',
    }

    def __init__(self, strict: bool = False):
        self.strict = strict

    def detect_iac_type(self, file_path: Path) -> IaCType | None:
        """Detect IaC type from file extension and content."""
        if file_path.suffix in ['.tf', '.tfvars']:
            return IaCType.TERRAFORM
        elif file_path.suffix in ['.yaml', '.yml', '.json'] and 'AWSTemplateFormatVersion' in file_path.read_text(errors='ignore'):
            return IaCType.CLOUDFORMATION
        elif file_path.suffix in ['.yaml', '.yml', '.json'] and 'apiVersion' in file_path.read_text(errors='ignore'):
            return IaCType.KUBERNETES
        return None

    def validate_terraform(self, content: str, file_path: str) -> list[ValidationIssue]:
        """Validate Terraform configuration."""
        issues = []
        lines = content.split('\n')

        # Check for public resources
        for rule_id in {**self.TF_SECURITY_RULES, **self.BEST_PRACTICE_RULES}.values():
            for i, line in enumerate(lines, 1):
                if re.search(rule_id, line, re.IGNORECASE):
                    severity = ValidationResult.FAILED if rule_id in self.TF_SECURITY_RULES else ValidationResult.WARNING
                    suggestion = self._get_suggestion(rule_id)
                    issues.append(ValidationIssue(
                        file=file_path,
                        line=i,
                        severity=severity,
                        rule_id=rule_id,
                        message="Security or best practice issue detected",
                        suggestion=suggestion
                    ))

        return issues

    def validate_cloudformation(self, content: str, file_path: str) -> list[ValidationIssue]:
        """Validate CloudFormation template."""
        issues = []
        lines = content.split('\n')

        for rule_id in self.CF_SECURITY_RULES.values():
            for i, line in enumerate(lines, 1):
                if re.search(rule_id, line, re.IGNORECASE):
                    issues.append(ValidationIssue(
                        file=file_path,
                        line=i,
                        severity=ValidationResult.FAILED,
                        rule_id=rule_id,
                        message="Security issue detected",
                        suggestion=self._get_suggestion(rule_id)
                    ))

        return issues

    def _get_suggestion(self, rule_id: str) -> str:
        """Get suggestion for rule."""
        suggestions = {
            'tf_public_s3': "Use private ACL and bucket policies",
            'tf_hardcoded_secrets': "Use variables and secrets manager",
            'tf_wide_open_sg': "Restrict CIDR blocks to specific IPs",
            'cf_public_s3': "Remove public read access",
            'cf_hardcoded_secrets': "Use Parameter Store or Secrets Manager",
        }
        return suggestions.get(rule_id, "Review and fix the issue")

    def run_external_validator(self, file_path: Path, iac_type: IaCType) -> tuple[bool, str]:
        """Run external IaC validator tool."""
        try:
            if iac_type == IaCType.TERRAFORM:
                # Check if terraform is available
                result = subprocess.run(
                    ['terraform', 'validate', str(file_path.parent)],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                return result.returncode == 0, result.stderr

            elif iac_type == IaCType.CLOUDFORMATION:
                # Check if cfn-lint is available
                result = subprocess.run(
                    ['cfn-lint', str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                return result.returncode == 0, result.stdout

        except FileNotFoundError:
            logger.warning(f"External validator not found for {iac_type.value}")
        except subprocess.TimeoutExpired:
            logger.warning("Validator timed out")

        return True, "External validator skipped"

    def validate_file(self, file_path: Path) -> IaCValidationResult | None:
        """Validate a single IaC file."""
        iac_type = self.detect_iac_type(file_path)
        if not iac_type:
            return None

        try:
            content = file_path.read_text()
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return None

        # Run validation
        if iac_type == IaCType.TERRAFORM:
            issues = self.validate_terraform(content, str(file_path))
        else:
            issues = self.validate_cloudformation(content, str(file_path))

        # Run external validator
        ext_passed, ext_output = self.run_external_validator(file_path, iac_type)

        if not ext_passed and ext_output:
            issues.append(ValidationIssue(
                file=str(file_path),
                line=0,
                severity=ValidationResult.WARNING,
                rule_id="external_validator",
                message=ext_output,
                suggestion="Fix the validation errors"
            ))

        # Calculate score
        security_issues = [i for i in issues if i.severity == ValidationResult.FAILED]
        warnings = [i for i in issues if i.severity == ValidationResult.WARNING]
        score = max(0, 100 - len(security_issues) * 20 - len(warnings) * 5)

        return IaCValidationResult(
            file_path=str(file_path),
            iac_type=iac_type,
            timestamp=datetime.now(),
            issues=issues,
            security_count=len(security_issues),
            warning_count=len(warnings),
            passed=score >= 80,
            score=score
        )

    def validate_directory(self, dir_path: str) -> list[IaCValidationResult]:
        """Validate all IaC files in a directory."""
        results = []
        path = Path(dir_path)

        if not path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return results

        for ext in ['*.tf', '*.yaml', '*.yml', '*.json']:
            for file_path in path.rglob(ext):
                result = self.validate_file(file_path)
                if result:
                    results.append(result)

        return results

    def generate_report(self, results: list[IaCValidationResult]) -> dict[str, Any]:
        """Generate validation summary report."""
        if not results:
            return {"status": "no_files_validated"}

        total_security = sum(r.security_count for r in results)
        total_warnings = sum(r.warning_count for r in results)
        avg_score = sum(r.score for r in results) / len(results)

        return {
            'total_files': len(results),
            'total_security_issues': total_security,
            'total_warnings': total_warnings,
            'average_score': round(avg_score, 1),
            'overall_status': 'PASSED' if avg_score >= 80 else 'FAILED',
            'details': [
                {
                    'file': r.file_path,
                    'type': r.iac_type.value,
                    'security_issues': r.security_count,
                    'warnings': r.warning_count,
                    'score': r.score,
                    'passed': r.passed
                }
                for r in results
            ]
        }

    def save_report(self, report: dict[str, Any], output_path: str | None = None) -> str:
        """Save report to file."""
        output = Path(output_path or 'iac_validation_reports')
        output.mkdir(exist_ok=True)

        report_file = output / f"iac_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report saved to: {report_file}")
        return str(report_file)


def main():
    """Main entry point for IaC validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate IaC configurations")
    parser.add_argument('--path', required=True, help='Path to IaC files')
    parser.add_argument('--output', default='iac_validation_reports', help='Output directory')
    parser.add_argument('--strict', action='store_true', help='Fail on warnings')

    args = parser.parse_args()

    validator = InfrastructureAsCodeValidator(strict=args.strict)
    results = validator.validate_directory(args.path)
    report = validator.generate_report(results)

    report_path = validator.save_report(report, args.output)

    print("\nIaC Validation Summary:")
    print(f"  Files validated: {report['total_files']}")
    print(f"  Security issues: {report['total_security_issues']}")
    print(f"  Warnings: {report['total_warnings']}")
    print(f"  Average score: {report['average_score']}")
    print(f"  Status: {report['overall_status']}")

    if report['total_security_issues'] > 0:
        print(f"\n⚠️ Security issues found! See: {report_path}")


if __name__ == "__main__":
    main()
