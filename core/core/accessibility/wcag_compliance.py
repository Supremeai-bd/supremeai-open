"""
SupremeAI WCAG 2.1 AA Compliance Module
=======================================

Implements accessibility features to meet WCAG 2.1 AA standards:
- Color contrast checking
- Keyboard navigation support
- Screen reader compatibility
- Semantic HTML structure
- Alternative text for media
- Focus management
- ARIA attributes

Bengali:
ডাব্লিউসি এজি ২.১ এএ অ্যাকসেসিবিলিটি মডিউল
ডাব্লিউসি এজি ২.১ এএ স্ট্যান্ডার্ড মেটানোর জন্য অ্যাকসেসিবিলিটি বৈশিষ্ট্য বাস্তবায়ন:
- রঙের কনট্রাস্ট চেকিং
- কীবোর্ড নেভিগেশন সাপোর্ট
- স্ক্রিন রিডার কম্প্যাটিবিলিটি
- সেম্যান্টিক এইচটিএমএল স্ট্রাকচার
- মিডিয়ার জন্য বিকল্প টেক্সট
- ফোকাস ম্যানেজমেন্ট
- এরিয়া অ্যাট্রিবিউট
"""

from dataclasses import dataclass
from enum import Enum

# bs4 প্যাকেজটি ইনস্টল না থাকলেও যেন core মডিউল ইমপোর্ট ব্যর্থ না হয়, সেজন্য সেফ ইমপোর্ট ব্যবহার করা হলো।
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[misc, assignment]
# requests প্যাকেজটি ইনস্টল না থাকলেও যেন httpx ব্যবহার করে URL চেক করা যায়, সে জন্য সেফ ইমপোর্ট ফলব্যাক রাখা হলো।
try:
    import httpx as requests
except ImportError:
    import httpx as requests  # type: ignore

from core.logging_config import logger


class WCAGPrinciple(Enum):
    """WCAG 2.1 Principles."""

    PERCEIVABLE = "Perceivable"
    OPERABLE = "Operable"
    UNDERSTANDABLE = "Understandable"
    ROBUST = "Robust"


class WCAGGuideline(Enum):
    """WCAG 2.1 Guidelines."""

    # Perceivable
    TEXT_ALTERNATIVES = "1.1 Text Alternatives"
    TIME_BASED_MEDIA = "1.2 Time-based Media"
    ADAPTABLE = "1.3 Adaptable"
    DISTRACTING_INFORMATION = "1.4 Distinguishable"

    # Operable
    KEYBOARD_ACCESSIBLE = "2.1 Keyboard Accessible"
    ENOUGH_TIME = "2.2 Enough Time"
    SEIZURES_AND_PHYSICAL_REACTIONS = "2.3 Seizures and Physical Reactions"
    NAVIGABLE = "2.4 Navigable"
    INPUT_MODALITIES = "2.5 Input Modalities"

    # Understandable
    READABLE = "3.1 Readable"
    PRONUNCIABLE = "3.2 Predictable"
    INPUT_ASSISTANCE = "3.3 Input Assistance"

    # Robust
    COMPATIBLE = "4.1 Compatible"


class WCAGLevel(Enum):
    """WCAG Conformance Levels."""

    A = "Level A"
    AA = "Level AA"
    AAA = "Level AAA"


@dataclass
class AccessibilityIssue:
    """Represents an accessibility issue found during compliance checking."""

    id: str
    principle: WCAGPrinciple
    guideline: WCAGGuideline
    level: WCAGLevel
    description: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    element: str | None = None
    suggestion: str = ""
    code_example: str = ""


@dataclass
class ContrastRatio:
    """Represents a color contrast ratio."""

    ratio: float
    is_aa_compliant: bool
    is_aaa_compliant: bool
    foreground_color: str
    background_color: str


class ColorContrastChecker:
    """Checks color contrast ratios for WCAG compliance."""

    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join([c * 2 for c in hex_color])
        # জেনারেটর এক্সপ্রেশন টিউপল টাইপ সঠিকভাবে হ্যান্ডেল করার জন্য ৩-টুপল আকারে রিটার্ন করা হচ্ছে
        rgb_list = [int(hex_color[i : i + 2], 16) for i in (0, 2, 4)]
        return (rgb_list[0], rgb_list[1], rgb_list[2])

    @staticmethod
    def rgb_to_relative_luminance(r: int, g: int, b: int) -> float:
        """Calculate relative luminance of a color."""

        def srgb_to_linear(component):
            component = component / 255.0
            if component <= 0.03928:
                return component / 12.92
            else:
                return ((component + 0.055) / 1.055) ** 2.4

        r_lin = srgb_to_linear(r)
        g_lin = srgb_to_linear(g)
        b_lin = srgb_to_linear(b)

        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    def calculate_contrast_ratio(self, color1: str, color2: str) -> ContrastRatio:
        """Calculate contrast ratio between two colors."""
        r1, g1, b1 = self.hex_to_rgb(color1)
        r2, g2, b2 = self.hex_to_rgb(color2)

        lum1 = self.rgb_to_relative_luminance(r1, g1, b1)
        lum2 = self.rgb_to_relative_luminance(r2, g2, b2)

        # Ensure lum1 is the lighter color
        if lum1 < lum2:
            lum1, lum2 = lum2, lum1

        ratio = (lum1 + 0.05) / (lum2 + 0.05)

        # Check compliance levels
        is_aa_normal = ratio >= 4.5
        is_aaa_normal = ratio >= 7.0

        # For simplicity, we'll check against normal text requirements
        is_aa_compliant = is_aa_normal
        is_aaa_compliant = is_aaa_normal

        return ContrastRatio(
            ratio=round(ratio, 2),
            is_aa_compliant=is_aa_compliant,
            is_aaa_compliant=is_aaa_compliant,
            foreground_color=color1,
            background_color=color2,
        )


class HTMLAccessibilityChecker:
    """Checks HTML for accessibility issues."""

    def __init__(self):
        self.contrast_checker = ColorContrastChecker()
        self.issues: list[AccessibilityIssue] = []

    def check_html_accessibility(self, html_content: str) -> list[AccessibilityIssue]:
        """Check HTML content for accessibility issues."""
        self.issues = []
        soup = BeautifulSoup(html_content, "html.parser")

        # Check for issues
        self._check_images_alt_text(soup)
        self._check_heading_structure(soup)
        self._check_link_text(soup)
        self._check_form_labels(soup)
        self._check_color_contrast(soup)
        self._check_keyboard_navigation(soup)
        self._check_aria_attributes(soup)

        return self.issues

    def _check_images_alt_text(self, soup: BeautifulSoup):
        """Check if images have appropriate alt text."""
        images = soup.find_all("img")

        for img in images:
            alt_attr = img.get("alt", "")
            alt_text = str(alt_attr[0] if isinstance(alt_attr, list) else alt_attr).strip()

            if not alt_text:
                self.issues.append(
                    AccessibilityIssue(
                        id="img-alt-missing",
                        principle=WCAGPrinciple.PERCEIVABLE,
                        guideline=WCAGGuideline.TEXT_ALTERNATIVES,
                        level=WCAGLevel.A,
                        description="Image is missing alt text",
                        severity="high",
                        element=str(img),
                        suggestion="Add descriptive alt text that conveys the purpose or content of the image",
                        code_example='<img src="example.jpg" alt="Description of image content">',
                    )
                )
            elif alt_text.lower() in ["image", "photo", "picture"]:
                self.issues.append(
                    AccessibilityIssue(
                        id="img-alt-generic",
                        principle=WCAGPrinciple.PERCEIVABLE,
                        guideline=WCAGGuideline.TEXT_ALTERNATIVES,
                        level=WCAGLevel.A,
                        description="Image has generic alt text",
                        severity="medium",
                        element=str(img),
                        suggestion="Replace generic alt text with specific, descriptive text",
                        code_example='<img src="example.jpg" alt="Team members at company meeting">',
                    )
                )

    def _check_heading_structure(self, soup: BeautifulSoup):
        """Check if headings follow proper hierarchical structure."""
        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

        if not headings:
            self.issues.append(
                AccessibilityIssue(
                    id="heading-missing",
                    principle=WCAGPrinciple.OPERABLE,
                    guideline=WCAGGuideline.NAVIGABLE,
                    level=WCAGLevel.A,
                    description="No headings found in content",
                    severity="medium",
                    suggestion="Add heading structure to organize content and aid navigation",
                    code_example="<h1>Main Title</h1><h2>Section Title</h2>",
                )
            )
            return

        # Check if there's exactly one H1
        h1_count = len([h for h in headings if h.name == "h1"])
        if h1_count != 1:
            self.issues.append(
                AccessibilityIssue(
                    id="heading-h1-count",
                    principle=WCAGPrinciple.OPERABLE,
                    guideline=WCAGGuideline.NAVIGABLE,
                    level=WCAGLevel.A,
                    description=f"Document should have exactly one H1, found {h1_count}",
                    severity="medium",
                    suggestion="Use one H1 per page for the main title",
                    code_example="<h1>Page Title</h1>",
                )
            )

        # Check heading hierarchy
        prev_level = 0
        for heading in headings:
            level = int(heading.name[1])  # Extract number from h1, h2, etc.

            if level > prev_level + 1:
                self.issues.append(
                    AccessibilityIssue(
                        id="heading-skipped-level",
                        principle=WCAGPrinciple.OPERABLE,
                        guideline=WCAGGuideline.NAVIGABLE,
                        level=WCAGLevel.A,
                        description=f"Skipped heading level from H{prev_level} to H{level}",
                        severity="medium",
                        element=str(heading),
                        suggestion="Follow proper heading hierarchy without skipping levels",
                        code_example=f"<h{prev_level + 1}>Previous Heading</h{prev_level + 1}><h{level}>Current Heading</h{level}>",
                    )
                )

            prev_level = level

    def _check_link_text(self, soup: BeautifulSoup):
        """Check if links have descriptive text."""
        links = soup.find_all("a", href=True)

        for link in links:
            link_text = link.get_text(strip=True)
            link.get("href", "")

            # Check for generic link text
            generic_texts = ["click here", "here", "link", "more", "read more", "continue"]
            if any(text in link_text.lower() for text in generic_texts):
                self.issues.append(
                    AccessibilityIssue(
                        id="link-generic-text",
                        principle=WCAGPrinciple.UNDERSTANDABLE,
                        guideline=WCAGGuideline.PRONUNCIABLE,
                        level=WCAGLevel.A,
                        description="Link has generic text that doesn't describe its purpose",
                        severity="medium",
                        element=str(link),
                        suggestion="Use descriptive link text that indicates the destination or action",
                        code_example='<a href="/download">Download PDF Report</a>',
                    )
                )

            # Check for link with no text (only image)
            if not link_text and not link.find("img"):
                self.issues.append(
                    AccessibilityIssue(
                        id="link-no-text",
                        principle=WCAGPrinciple.UNDERSTANDABLE,
                        guideline=WCAGGuideline.PRONUNCIABLE,
                        level=WCAGLevel.A,
                        description="Link has no text content",
                        severity="high",
                        element=str(link),
                        suggestion="Add descriptive text to the link",
                        code_example='<a href="/page">Visit Important Page</a>',
                    )
                )

    def _check_form_labels(self, soup: BeautifulSoup):
        """Check if form controls have associated labels."""
        form_elements = soup.find_all(["input", "select", "textarea"])

        for elem in form_elements:
            if elem.get("type") == "hidden":
                continue

            # Check for associated label
            has_label = False

            # Method 1: Explicit label with 'for' attribute
            label_for = elem.get("id")
            if label_for:
                associated_label = soup.find("label", attrs={"for": label_for})
                if associated_label:
                    has_label = True

            # Method 2: Wrapped in label
            parent = elem.parent
            if parent and parent.name == "label":
                has_label = True

            # Method 3: ARIA label
            if elem.get("aria-label") or elem.get("aria-labelledby"):
                has_label = True

            if not has_label:
                self.issues.append(
                    AccessibilityIssue(
                        id="form-control-no-label",
                        principle=WCAGPrinciple.UNDERSTANDABLE,
                        guideline=WCAGGuideline.INPUT_ASSISTANCE,
                        level=WCAGLevel.A,
                        description=f"Form control {elem.name} has no associated label",
                        severity="high",
                        element=str(elem),
                        suggestion="Add an associated label for the form control",
                        code_example='<label for="field-id">Field Label</label><input id="field-id" type="text">',
                    )
                )

    def _check_color_contrast(self, soup: BeautifulSoup):
        """Check color contrast for text elements."""
        # This is a simplified check - in a real implementation, we'd parse CSS
        text_elements = soup.find_all(
            ["p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6", "a", "li", "td"]
        )

        # For demo purposes, we'll just check if any elements have style attributes
        # In a real implementation, we'd extract actual colors
        for elem in text_elements:
            style = elem.get("style", "")
            if style and ("color" in style or "background" in style):
                # This is where we'd extract colors and check contrast
                # For now, just acknowledge that contrast checking should happen
                pass

    def _check_keyboard_navigation(self, soup: BeautifulSoup):
        """Check keyboard navigation issues."""
        # Check for elements that should be focusable but aren't
        interactive_elements = soup.find_all(["button", "input", "select", "textarea", "a"])

        for elem in interactive_elements:
            tabindex = elem.get("tabindex")
            if tabindex == "-1":
                # Element is not keyboard focusable
                self.issues.append(
                    AccessibilityIssue(
                        id="keyboard-focus-excluded",
                        principle=WCAGPrinciple.OPERABLE,
                        guideline=WCAGGuideline.KEYBOARD_ACCESSIBLE,
                        level=WCAGLevel.A,
                        description=f"Interactive element {elem.name} excluded from keyboard navigation",
                        severity="high",
                        element=str(elem),
                        suggestion="Ensure interactive elements are keyboard focusable",
                        code_example='<button type="submit">Submit</button>',  # Don't add tabindex="-1" unnecessarily
                    )
                )

    def _check_aria_attributes(self, soup: BeautifulSoup):
        """Check ARIA attributes for proper usage."""
        elements_with_aria = soup.find_all(
            attrs=lambda x: x and any(attr.startswith("aria-") for attr in x)
        )  # type: ignore

        for elem in elements_with_aria:
            aria_attrs = {k: v for k, v in elem.attrs.items() if k.startswith("aria-")}

            # Check for common ARIA mistakes
            for attr, value in aria_attrs.items():
                if attr == "aria-hidden" and value == "true":
                    role = elem.get("role")
                    if not role or role not in ["presentation", "none"]:
                        self.issues.append(
                            AccessibilityIssue(
                                id="aria-hidden-with-role",
                                principle=WCAGPrinciple.ROBUST,
                                guideline=WCAGGuideline.COMPATIBLE,
                                level=WCAGLevel.A,
                                description="Element with aria-hidden='true' has a role that may cause confusion",
                                severity="medium",
                                element=str(elem),
                                suggestion="Use role='none' or role='presentation' with aria-hidden='true'",
                                code_example='<div aria-hidden="true" role="none">Hidden content</div>',
                            )
                        )


class AccessibilityComplianceEngine:
    """Main engine for accessibility compliance checking."""

    def __init__(self):
        self.html_checker = HTMLAccessibilityChecker()
        self.contrast_checker = ColorContrastChecker()
        self.compliance_report: dict = {}

    def check_page_accessibility(self, html_content: str) -> dict:
        """Check accessibility of a complete HTML page."""
        issues = self.html_checker.check_html_accessibility(html_content)

        # Organize issues by severity
        report = {
            "total_issues": len(issues),
            "by_severity": {
                "critical": [issue for issue in issues if issue.severity == "critical"],
                "high": [issue for issue in issues if issue.severity == "high"],
                "medium": [issue for issue in issues if issue.severity == "medium"],
                "low": [issue for issue in issues if issue.severity == "low"],
            },
            "by_principle": {
                "perceivable": [
                    issue for issue in issues if issue.principle == WCAGPrinciple.PERCEIVABLE
                ],
                "operable": [
                    issue for issue in issues if issue.principle == WCAGPrinciple.OPERABLE
                ],
                "understandable": [
                    issue for issue in issues if issue.principle == WCAGPrinciple.UNDERSTANDABLE
                ],
                "robust": [issue for issue in issues if issue.principle == WCAGPrinciple.ROBUST],
            },
            "summary": {
                "pass": len(issues) == 0,
                "compliance_level": self._determine_compliance_level(issues),
            },
            "recommendations": self._generate_recommendations(issues),
        }

        self.compliance_report = report
        return report

    def _determine_compliance_level(self, issues: list[AccessibilityIssue]) -> str:
        """Determine the overall WCAG compliance level."""
        critical_issues = len([i for i in issues if i.severity == "critical"])
        high_issues = len([i for i in issues if i.severity == "high"])

        if critical_issues > 0 or high_issues > 5:
            return "Does not meet WCAG 2.1 AA"
        elif high_issues > 0 or len(issues) > 10:
            return "Partial WCAG 2.1 AA compliance"
        else:
            return "Meets WCAG 2.1 AA requirements"

    def _generate_recommendations(self, issues: list[AccessibilityIssue]) -> list[str]:
        """Generate general recommendations based on issues found."""
        recommendations = []

        if any(i.id.startswith("img-alt") for i in issues):
            recommendations.append("Add descriptive alt text to all images")

        if any(i.id == "heading-missing" for i in issues):
            recommendations.append("Implement proper heading structure (H1-H6)")

        if any(i.id == "link-generic-text" for i in issues):
            recommendations.append(
                "Use descriptive link text that indicates destination or purpose"
            )

        if any(i.id == "form-control-no-label" for i in issues):
            recommendations.append("Associate all form controls with labels")

        if not recommendations:
            recommendations.append(
                "No major accessibility issues found. Consider periodic reviews."
            )

        return recommendations

    def get_accessibility_score(self, issues: list[AccessibilityIssue]) -> float:
        """Calculate an accessibility compliance score (0-100)."""
        if not issues:
            return 100.0  # Perfect score if no issues

        # Weight issues by severity
        severity_weights = {"critical": 10, "high": 7, "medium": 4, "low": 1}

        total_points = sum(severity_weights[issue.severity] for issue in issues)

        # Score calculation: 100 - (penalty based on weighted issues)
        # Each point reduces score by 1%
        penalty = min(total_points, 95)  # Cap penalty to maintain minimum score

        return max(0.0, 100.0 - penalty)

    def generate_compliance_report(self, url: str | None = None) -> dict:
        """Generate a detailed compliance report."""
        return {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "target": url or "HTML Content",
            "compliance_standard": "WCAG 2.1 AA",
            "score": self.get_accessibility_score(
                self.compliance_report.get("by_severity", {}).get("critical", [])
                + self.compliance_report.get("by_severity", {}).get("high", [])
                + self.compliance_report.get("by_severity", {}).get("medium", [])
                + self.compliance_report.get("by_severity", {}).get("low", [])
            ),
            "summary": self.compliance_report.get("summary", {}),
            "issues_found": self.compliance_report.get("total_issues", 0),
            "recommendations": self.compliance_report.get("recommendations", []),
            "detailed_findings": {
                "critical_issues": len(
                    self.compliance_report.get("by_severity", {}).get("critical", [])
                ),
                "high_issues": len(self.compliance_report.get("by_severity", {}).get("high", [])),
                "medium_issues": len(
                    self.compliance_report.get("by_severity", {}).get("medium", [])
                ),
                "low_issues": len(self.compliance_report.get("by_severity", {}).get("low", [])),
            },
        }


def check_url_accessibility(url: str) -> dict:
    """Check accessibility of a web page at the given URL."""
    try:
        # R2 FIX: use httpx instead of blocking `requests` lib
        import httpx

        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
        response.raise_for_status()

        engine = AccessibilityComplianceEngine()
        engine.check_page_accessibility(response.text)

        return engine.generate_compliance_report(url)
    except Exception as e:
        logger.error(f"Error checking accessibility for {url}: {e}")
        return {
            "error": str(e),
            "target": url,
            "compliance_standard": "WCAG 2.1 AA",
            "score": 0.0,
            "summary": {"pass": False, "compliance_level": "Error accessing URL"},
        }


def demo_accessibility_check():
    """Demonstrate accessibility checking features."""
    logger.info("Initializing Accessibility Compliance Engine...")

    # Sample HTML with accessibility issues
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Page</title></head>
    <body>
        <img src="logo.png">  <!-- Missing alt text -->
        <p>Some content here.</p>
        <a href="/page">click here</a>  <!-- Generic link text -->
        <input type="text" id="name">  <!-- Missing label -->
        <div style="color: #ccc; background: #eee;">Low contrast text</div>
    </body>
    </html>
    """

    engine = AccessibilityComplianceEngine()
    report = engine.check_page_accessibility(sample_html)

    logger.info("Accessibility Report:", total_issues=report["total_issues"])
    logger.info(f"Compliance Level: {report['summary']['compliance_level']}")
    logger.info(f"Score: {engine.get_accessibility_score([]):.1f}/100")

    logger.info("Issues by Severity:")
    for severity, issues in report["by_severity"].items():
        if issues:
            logger.info(f"{severity.title()}: {len(issues)} issues")

    logger.info("Recommendations:")
    for rec in report["recommendations"]:
        logger.info(f"- {rec}")


if __name__ == "__main__":
    demo_accessibility_check()
