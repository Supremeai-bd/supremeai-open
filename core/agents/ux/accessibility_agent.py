"""
Accessibility Agent for SupremeAI 2.0
Ensures system accessibility for users with disabilities and compliance with accessibility standards.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

from core.cache.redis_manager import redis_manager
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger


@dataclass
class AccessibilityIssue:
    """Data class to hold accessibility issue information."""

    id: str
    severity: str  # critical, high, medium, low
    category: str  # visual, auditory, motor, cognitive
    description: str
    wcag_level: str  # A, AA, AAA
    suggestions: list[str]
    affected_elements: list[str]
    timestamp: datetime


@dataclass
class AccessibilityReport:
    """Data class to hold accessibility assessment results."""

    content_analyzed: str
    issues_found: list[AccessibilityIssue]
    overall_score: float  # 0.0 to 1.0
    compliance_level: str  # A, AA, AAA, not_compliant
    recommendations: list[str]
    timestamp: datetime


class HTMLAccessibilityParser(HTMLParser):
    """Custom HTML parser to identify accessibility issues."""

    def __init__(self):
        super().__init__()
        self.issues = []
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append({"tag": tag, "attrs": dict(attrs)})

        # Check for common accessibility issues
        issues = self._check_tag_accessibility(tag, dict(attrs))
        self.issues.extend(issues)

    def handle_endtag(self, tag):
        if self.tag_stack:
            self.tag_stack.pop()

    def _check_tag_accessibility(self, tag: str, attrs: dict[str, str]) -> list[dict[str, Any]]:
        """Check a specific tag for accessibility issues."""
        issues = []

        # Check for images without alt text
        if tag == "img" and ("alt" not in attrs or not attrs["alt"].strip()):
            issues.append(
                {
                    "severity": "high",
                    "category": "visual",
                    "description": "Image missing alt text",
                    "wcag_level": "A",
                    "suggestions": ["Add descriptive alt text to all images"],
                    "affected_elements": [f"<{tag} {dict(attrs)}>"],
                }
            )

        # Check for links without meaningful text
        if tag == "a" and ("title" not in attrs or not attrs["title"].strip()):
            if attrs.get("href", "").startswith(("http", "www")):
                link_text = attrs.get("text", "").strip()
                if link_text in ["click here", "here", "link", ""]:
                    issues.append(
                        {
                            "severity": "medium",
                            "category": "cognitive",
                            "description": "Link with non-descriptive text",
                            "wcag_level": "A",
                            "suggestions": [
                                "Use descriptive link text that makes sense out of context"
                            ],
                            "affected_elements": [f"<{tag} {dict(attrs)}>"],
                        }
                    )

        # Check for form inputs without labels
        if (tag in ["input", "textarea", "select"] and "type" not in attrs) or attrs.get(
            "type"
        ) != "hidden":
            if "aria-label" not in attrs and "aria-labelledby" not in attrs:
                # Check if previous element is a label
                if "id" in attrs:
                    # Would need to check for associated label - simplified for now
                    pass
                else:
                    issues.append(
                        {
                            "severity": "high",
                            "category": "motor",
                            "description": "Form input missing label or aria-label",
                            "wcag_level": "A",
                            "suggestions": ["Add a label element or use aria-label attribute"],
                            "affected_elements": [f"<{tag} {dict(attrs)}>"],
                        }
                    )

        # Check for color contrast (would need CSS analysis)
        if "style" in attrs and ("color" in attrs["style"] or "background" in attrs["style"]):
            # Simplified - would need actual color contrast checking
            pass

        return issues


class AccessibilityAgent:
    """Agent that ensures system accessibility for users with disabilities."""

    def __init__(self):
        self.name = "Accessibility Agent"
        self.token_deductor = TokenDeductor()
        self.accessibility_issues_key = "accessibility:issues"
        self.accessibility_reports_key = "accessibility:reports"
        self.max_reports = 50

        # Define accessibility standards
        self.wcag_standards = {
            "level_A": [
                "Non-text content has alternative text",
                "Audio and video have captions",
                "Color is not the only means of conveying info",
                "Keyboard accessible functionality",
                "Enough time to read and use content",
                "Seizure prevention",
                "Navigable interface",
                "Readable content",
                "Predictable behavior",
                "Input assistance",
            ],
            "level_AA": [
                "Contrast ratio of 4.5:1 for normal text",
                "Images of text are avoided",
                "Audio control",
                "Pause, stop, hide for moving content",
                "Labels describe purpose",
                "Consistent navigation",
                "Consistent identification",
                "Error suggestion",
                "Error prevention for legal/financial data",
            ],
            "level_AAA": [
                "Enhanced contrast ratio of 7:1",
                "Extended audio alternatives",
                "Content on demand",
                "Sign language interpretation",
                "Reading level clarification",
                "Unusual words definition",
                "Focus indicator enhancement",
                "Consistent help mechanism",
                "Accessible authentication",
                "Contextual help",
            ],
        }

        # Define disability categories and considerations
        self.disability_considerations = {
            "visual": {
                "issues": ["color_dependency", "small_text", "missing_alt_text", "poor_contrast"],
                "solutions": [
                    "screen_reader_support",
                    "high_contrast_mode",
                    "text_scaling",
                    "audio_alternatives",
                ],
            },
            "auditory": {
                "issues": ["audio_only_content", "missing_captions", "sound_based_feedback"],
                "solutions": ["captions", "transcripts", "visual_indicators", "sign_language"],
            },
            "motor": {
                "issues": ["keyboard_dependency", "small_targets", "timed_interactions"],
                "solutions": [
                    "keyboard_navigation",
                    "voice_control",
                    "customizable_timing",
                    "alternative_inputs",
                ],
            },
            "cognitive": {
                "issues": ["complex_language", "unexpected_behaviors", "too_much_information"],
                "solutions": [
                    "simple_language",
                    "consistent_design",
                    "clear_feedback",
                    "distraction_reduction",
                ],
            },
        }

    async def assess_content_accessibility(
        self, content: str, content_type: str = "html"
    ) -> AccessibilityReport:
        """
        Assess the accessibility of content.

        Args:
            content: Content to assess for accessibility
            content_type: Type of content (html, text, etc.)

        Returns:
            AccessibilityReport with assessment results
        """
        try:
            issues = []

            if content_type.lower() == "html":
                # Parse HTML for accessibility issues
                parser = HTMLAccessibilityParser()
                parser.feed(content)
                raw_issues = parser.issues

                # Convert raw issues to AccessibilityIssue objects
                for i, raw_issue in enumerate(raw_issues):
                    issue = AccessibilityIssue(
                        id=f"acc_issue_{i}_{int(datetime.utcnow().timestamp())}",
                        severity=raw_issue["severity"],
                        category=raw_issue["category"],
                        description=raw_issue["description"],
                        wcag_level=raw_issue["wcag_level"],
                        suggestions=raw_issue["suggestions"],
                        affected_elements=raw_issue["affected_elements"],
                        timestamp=datetime.utcnow(),
                    )
                    issues.append(issue)

            # For non-HTML content, perform text analysis
            else:
                issues.extend(await self._analyze_text_accessibility(content))

            # Calculate overall accessibility score
            score = self._calculate_accessibility_score(issues)

            # Determine compliance level
            compliance_level = self._determine_compliance_level(score)

            # Generate recommendations
            recommendations = await self._generate_recommendations(issues)

            # Create report
            report = AccessibilityReport(
                content_analyzed=content[:200] + "..." if len(content) > 200 else content,
                issues_found=issues,
                overall_score=score,
                compliance_level=compliance_level,
                recommendations=recommendations,
                timestamp=datetime.utcnow(),
            )

            # Store report in Redis
            await self._store_accessibility_report(report)

            logger.info(
                f"Accessibility assessment completed. Issues found: {len(issues)}, Score: {score}"
            )
            return report

        except Exception as e:
            logger.error(f"Error assessing content accessibility: {e}")
            # Return a neutral report in case of error
            return AccessibilityReport(
                content_analyzed=content[:200] + "..." if len(content) > 200 else content,
                issues_found=[],
                overall_score=0.5,
                compliance_level="not_compliant",
                recommendations=["Error occurred during accessibility assessment"],
                timestamp=datetime.utcnow(),
            )

    async def _analyze_text_accessibility(self, text: str) -> list[AccessibilityIssue]:
        """Analyze text content for accessibility issues."""
        issues = []

        # Check for complex sentences
        sentences = re.split(r"[.!?]+", text)
        complex_sentences = [s for s in sentences if len(s.split()) > 25]

        if len(complex_sentences) > len(sentences) * 0.3:  # More than 30% are complex
            issues.append(
                AccessibilityIssue(
                    id=f"acc_issue_complex_text_{int(datetime.utcnow().timestamp())}",
                    severity="medium",
                    category="cognitive",
                    description="High proportion of complex sentences",
                    wcag_level="AA",
                    suggestions=[
                        "Break down complex sentences",
                        "Use simpler vocabulary",
                        "Add bullet points or numbered lists",
                    ],
                    affected_elements=[
                        f"Found {len(complex_sentences)} complex sentences out of {len(sentences)} total"
                    ],
                    timestamp=datetime.utcnow(),
                )
            )

        # Check for jargon or complex terms
        jargon_patterns = [
            r"\b(?:utilize|endeavor|facilitate|leverage|synergy|paradigm|implement|optimize|strategize)\b",
            r"\b(?:therefore|however|moreover|nevertheless|consequently)\b",
        ]

        jargon_count = 0
        for pattern in jargon_patterns:
            jargon_count += len(re.findall(pattern, text, re.IGNORECASE))

        if jargon_count > len(text.split()) * 0.05:  # More than 5% are jargon
            issues.append(
                AccessibilityIssue(
                    id=f"acc_issue_jargon_{int(datetime.utcnow().timestamp())}",
                    severity="medium",
                    category="cognitive",
                    description="High frequency of complex terminology",
                    wcag_level="AA",
                    suggestions=[
                        "Replace jargon with simpler alternatives",
                        "Provide definitions for technical terms",
                        "Use plain language",
                    ],
                    affected_elements=[f"Found {jargon_count} potentially complex terms"],
                    timestamp=datetime.utcnow(),
                )
            )

        return issues

    def _calculate_accessibility_score(self, issues: list[AccessibilityIssue]) -> float:
        """Calculate overall accessibility score based on issues found."""
        if not issues:
            return 1.0  # Perfect score if no issues

        # Assign weights to severity levels
        severity_weights = {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}

        # Calculate weighted score deduction
        total_deduction = 0.0
        for issue in issues:
            weight = severity_weights.get(issue.severity, 0.2)
            # Each issue reduces score, with more severe issues having bigger impact
            total_deduction += weight * 0.1

        # Ensure score stays between 0 and 1
        score = max(0.0, 1.0 - total_deduction)
        return round(score, 2)

    def _determine_compliance_level(self, score: float) -> str:
        """Determine WCAG compliance level based on score."""
        if score >= 0.9:
            return "AAA"
        elif score >= 0.7:
            return "AA"
        elif score >= 0.5:
            return "A"
        else:
            return "not_compliant"

    async def _generate_recommendations(self, issues: list[AccessibilityIssue]) -> list[str]:
        """Generate recommendations based on identified issues."""
        recommendations = set()  # Use set to avoid duplicates

        # Group issues by category
        category_issues = {}
        for issue in issues:
            if issue.category not in category_issues:
                category_issues[issue.category] = []
            category_issues[issue.category].append(issue)

        # Generate recommendations for each category
        for category, _cat_issues in category_issues.items():
            if category == "visual":
                recommendations.add("Implement high contrast mode and support screen readers")
            elif category == "auditory":
                recommendations.add("Provide text alternatives for audio content")
            elif category == "motor":
                recommendations.add("Ensure full keyboard navigation support")
            elif category == "cognitive":
                recommendations.add("Simplify language and provide clear instructions")

        # Add specific recommendations based on issue types
        for issue in issues:
            recommendations.update(issue.suggestions)

        # Add general recommendations if no specific ones were found
        if not recommendations:
            recommendations.add("Review content for accessibility compliance")
            recommendations.add("Test with assistive technologies")
            recommendations.add("Follow WCAG 2.1 guidelines")

        return list(recommendations)

    async def check_interface_accessibility(
        self, interface_elements: list[dict[str, Any]]
    ) -> list[AccessibilityIssue]:
        """
        Check interface elements for accessibility issues.

        Args:
            interface_elements: List of interface elements with properties

        Returns:
            List of accessibility issues found
        """
        issues = []

        for i, element in enumerate(interface_elements):
            element_type = element.get("type", "")
            props = element.get("properties", {})

            # Check button accessibility
            if element_type == "button":
                if not props.get("label") and not props.get("aria-label"):
                    issues.append(
                        AccessibilityIssue(
                            id=f"btn_no_label_{i}_{int(datetime.utcnow().timestamp())}",
                            severity="high",
                            category="visual",
                            description=f"Button {i} missing accessible label",
                            wcag_level="A",
                            suggestions=["Add button text or aria-label attribute"],
                            affected_elements=[f"Button at index {i}"],
                            timestamp=datetime.utcnow(),
                        )
                    )

                # Check button size for motor impairments
                width = props.get("width", 0)
                height = props.get("height", 0)
                if width < 44 or height < 44:  # Minimum touch target size (WCAG 2.1)
                    issues.append(
                        AccessibilityIssue(
                            id=f"btn_small_{i}_{int(datetime.utcnow().timestamp())}",
                            severity="medium",
                            category="motor",
                            description=f"Button {i} too small for touch targets",
                            wcag_level="AA",
                            suggestions=[
                                "Make button at least 44x44 pixels or provide equivalent spacing"
                            ],
                            affected_elements=[f"Button at index {i} (size: {width}x{height}px)"],
                            timestamp=datetime.utcnow(),
                        )
                    )

            # Check form field accessibility
            elif element_type in ["input", "select", "textarea"]:
                if (
                    not props.get("label")
                    and not props.get("aria-label")
                    and not props.get("aria-labelledby")
                ):
                    issues.append(
                        AccessibilityIssue(
                            id=f"field_no_label_{i}_{int(datetime.utcnow().timestamp())}",
                            severity="high",
                            category="visual",
                            description=f"Form field {i} missing accessible label",
                            wcag_level="A",
                            suggestions=["Add associated label or use aria-label/aria-labelledby"],
                            affected_elements=[f"Form field at index {i}"],
                            timestamp=datetime.utcnow(),
                        )
                    )

        return issues

    async def generate_accessibility_plan(self, target_score: float = 0.9) -> dict[str, Any]:
        """
        Generate an accessibility improvement plan.

        Args:
            target_score: Target accessibility score to achieve

        Returns:
            Dictionary with improvement plan
        """
        try:
            # Get recent reports to understand current state
            recent_reports = await self.get_recent_reports(limit=5)

            if not recent_reports:
                return {
                    "status": "no_data",
                    "message": "No accessibility reports available to generate plan",
                    "steps": [
                        "Conduct initial accessibility audit",
                        "Assess current interface components",
                        "Document baseline accessibility score",
                    ],
                }

            # Analyze trends and common issues
            all_issues = []
            for report in recent_reports:
                all_issues.extend(report.issues_found)

            # Group issues by severity and category
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            category_counts = {"visual": 0, "auditory": 0, "motor": 0, "cognitive": 0}

            for issue in all_issues:
                severity_counts[issue.severity] += 1
                category_counts[issue.category] += 1

            # Generate prioritized improvement steps
            improvement_steps = []

            # Address critical and high severity issues first
            if severity_counts["critical"] > 0:
                improvement_steps.append(
                    {
                        "priority": "critical",
                        "description": "Address all critical accessibility issues immediately",
                        "estimated_time": "1-2 days",
                        "impact": "High - affects core functionality for users with disabilities",
                    }
                )

            if severity_counts["high"] > 0:
                improvement_steps.append(
                    {
                        "priority": "high",
                        "description": "Fix high severity issues affecting major user groups",
                        "estimated_time": "3-5 days",
                        "impact": "High - significantly impacts usability",
                    }
                )

            # Address issues by category
            for category, count in category_counts.items():
                if count > 0:
                    improvement_steps.append(
                        {
                            "priority": "medium",
                            "description": f"Improve {category}-related accessibility features",
                            "estimated_time": "1-2 weeks",
                            "impact": f"Addresses needs of users with {category} impairments",
                        }
                    )

            # Add ongoing measures
            improvement_steps.extend(
                [
                    {
                        "priority": "ongoing",
                        "description": "Implement automated accessibility testing in CI/CD pipeline",
                        "estimated_time": "1 week setup",
                        "impact": "Prevents regressions and catches issues early",
                    },
                    {
                        "priority": "ongoing",
                        "description": "Train team on accessibility best practices",
                        "estimated_time": "Ongoing",
                        "impact": "Builds accessibility awareness into development process",
                    },
                    {
                        "priority": "ongoing",
                        "description": "Regular accessibility audits and user testing",
                        "estimated_time": "Monthly",
                        "impact": "Ensures continued compliance and improvement",
                    },
                ]
            )

            plan = {
                "status": "generated",
                "target_score": target_score,
                "current_average_score": sum(r.overall_score for r in recent_reports)
                / len(recent_reports),
                "improvement_steps": improvement_steps,
                "estimated_completion": "2-4 weeks",
                "success_metrics": [
                    f"Achieve accessibility score of {target_score}",
                    "Resolve all critical and high severity issues",
                    "Meet WCAG 2.1 AA compliance",
                ],
            }

            return plan

        except Exception as e:
            logger.error(f"Error generating accessibility plan: {e}")
            return {"status": "error", "message": f"Error generating plan: {e!s}", "steps": []}

    async def _store_accessibility_report(self, report: AccessibilityReport):
        """Store accessibility report in Redis."""
        try:
            report_data = {
                "content_analyzed": report.content_analyzed,
                "overall_score": report.overall_score,
                "compliance_level": report.compliance_level,
                "recommendations": report.recommendations,
                "timestamp": report.timestamp.isoformat(),
                "issues_found": [
                    {
                        "id": issue.id,
                        "severity": issue.severity,
                        "category": issue.category,
                        "description": issue.description,
                        "wcag_level": issue.wcag_level,
                        "suggestions": issue.suggestions,
                        "affected_elements": issue.affected_elements,
                        "timestamp": issue.timestamp.isoformat(),
                    }
                    for issue in report.issues_found
                ],
            }

            # Get existing reports
            existing_reports = await redis_manager.get(self.accessibility_reports_key)
            if existing_reports:
                reports_list = json.loads(existing_reports)
            else:
                reports_list = []

            # Add new report
            reports_list.append(report_data)

            # Keep only the last N reports
            if len(reports_list) > self.max_reports:
                reports_list = reports_list[-self.max_reports :]

            await redis_manager.set_with_ttl(
                self.accessibility_reports_key,
                json.dumps(reports_list),
                ttl=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error storing accessibility report: {e}")

    async def get_recent_reports(self, limit: int = 10) -> list[AccessibilityReport]:
        """Retrieve recent accessibility reports."""
        try:
            reports_data = await redis_manager.get(self.accessibility_reports_key)
            if not reports_data:
                return []

            reports_list = json.loads(reports_data)
            reports = []

            for item in reversed(reports_list[-limit:]):  # Most recent first
                issues = []
                for issue_data in item["issues_found"]:
                    issues.append(
                        AccessibilityIssue(
                            id=issue_data["id"],
                            severity=issue_data["severity"],
                            category=issue_data["category"],
                            description=issue_data["description"],
                            wcag_level=issue_data["wcag_level"],
                            suggestions=issue_data["suggestions"],
                            affected_elements=issue_data["affected_elements"],
                            timestamp=datetime.fromisoformat(issue_data["timestamp"]),
                        )
                    )

                reports.append(
                    AccessibilityReport(
                        content_analyzed=item["content_analyzed"],
                        issues_found=issues,
                        overall_score=item["overall_score"],
                        compliance_level=item["compliance_level"],
                        recommendations=item["recommendations"],
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                    )
                )

            return reports
        except Exception as e:
            logger.error(f"Error retrieving accessibility reports: {e}")
            return []


# Global instance
accessibility_agent = AccessibilityAgent()
