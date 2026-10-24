#!/usr/bin/env python
"""
auto_dead_code_remover.py
=========================
Automatically detects and reports dead code (unused functions, classes, variables)
using vulture and radon.

Generates a report that can be used to create a pull request for cleanup.

Environment Variables:
- TARGET_DIRS: Comma-separated list of directories to scan (default: backend,apps)
- OUTPUT_FILE: Path to output report (default: dead_code_report.md)
- EXCLUDE: Comma-separated list of patterns to exclude (default: __init__.py,migrations,tests,test_*)
- MIN_CONFIDENCE: Minimum confidence level for vulture (default: 80)
- CREATE_PR: Whether to create a pull request (default: false)
- GITHUB_REPOSITORY: The owner/repo slug for creating issues (e.g., 'my-org/my-repo')
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_DIRS = os.getenv("TARGET_DIRS", "backend,apps").split(",")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "dead_code_report.md")
EXCLUDE = os.getenv("EXCLUDE", "__init__.py,migrations,tests,test_*").split(",")
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "80"))
CREATE_ISSUE = os.getenv("CREATE_ISSUE", "false").lower() == "true"

def run_vulture() -> str:
    """Run vulture to detect dead code and return the output."""
    cmd = ["vulture"]

    # Add target directories
    for directory in TARGET_DIRS:
        if Path(directory).exists():
            cmd.append(directory)
        else:
            logger.warning(f"Directory {directory} does not exist, skipping")

    # Add exclusions
    for exclude_pattern in EXCLUDE:
        cmd.extend(["--exclude", exclude_pattern])

    # Add minimum confidence
    cmd.extend(["--min-confidence", str(MIN_CONFIDENCE)])

    # Add Python path
    cmd.extend(["--pythonpath", "."])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode not in [0, 1]:  # Vulture returns 1 when dead code is found
            logger.error(f"Vulture failed with exit code {result.returncode}")
            logger.error(f"Stderr: {result.stderr}")
            return ""

        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error("Vulture timed out after 5 minutes")
        return ""
    except FileNotFoundError:
        logger.error("Vulture not found. Install with: pip install vulture")
        return ""
    except Exception as e:
        logger.error(f"Error running vulture: {e}")
        return ""

def run_radon_cc() -> str:
    """Run radon complexity analysis to find overly complex functions."""
    cmd = ["radon", "cc", "--json"]

    # Add target directories
    for directory in TARGET_DIRS:
        if Path(directory).exists():
            cmd.append("--min=B")  # Show B and worse (B, C, D, E, F)
            cmd.append(directory)
        else:
            logger.warning(f"Directory {directory} does not exist, skipping")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout
        )

        if result.returncode not in [0, 1]:
            logger.error(f"Radon CC failed with exit code {result.returncode}")
            logger.error(f"Stderr: {result.stderr}")
            return ""

        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error("Radon CC timed out")
        return ""
    except FileNotFoundError:
        logger.error("Radon not found. Install with: pip install radon")
        return ""
    except Exception as e:
        logger.error(f"Error running radon cc: {e}")
        return ""

def run_radon_mi() -> str:
    """Run radon maintainability index analysis."""
    cmd = ["radon", "mi", "--json"]

    # Add target directories
    for directory in TARGET_DIRS:
        if Path(directory).exists():
            cmd.append(directory)
        else:
            logger.warning(f"Directory {directory} does not exist, skipping")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout
        )

        if result.returncode not in [0, 1]:
            logger.error(f"Radon MI failed with exit code {result.returncode}")
            logger.error(f"Stderr: {result.stderr}")
            return ""

        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error("Radon MI timed out")
        return ""
    except FileNotFoundError:
        logger.error("Radon not found. Install with: pip install radon")
        return ""
    except Exception as e:
        logger.error(f"Error running radon mi: {e}")
        return ""

def parse_vulture_output(output: str) -> list:
    """Parse vulture output into structured data."""
    dead_code = []

    if not output:
        return dead_code

    lines = output.strip().split('\n')
    for line in lines:
        if not line.strip():
            continue

        # Vulture output format: FILE:LINE: unused TYPE 'NAME' (CONFIDENCE% confidence)
        match = re.match(r"^(.+?):(\d+):\s+unused\s+(\w+)\s+'([^']+)'\s+\((\d+)%\s+confidence\)", line)
        if match:
            file_path, line_num, item_type, name, confidence = match.groups()
            dead_code.append({
                "file": file_path,
                "line": int(line_num),
                "confidence": int(confidence),
                "type": item_type,
                "name": name,
                "description": f"Unused {item_type.lower()} '{name}'"
            })

    return dead_code

def parse_radon_cc_output(output: str) -> list:
    """Parse radon cyclomatic complexity output."""
    complex_functions = []

    if not output:
        return complex_functions

    try:
        data = json.loads(output)
        for file_path, functions in data.items():
            for func_data in functions:
                grade = func_data.get("rank")
                # Only include grades D, E, F (complex)
                if grade and grade in ['D', 'E', 'F']:
                    complex_functions.append({
                        "file": file_path,
                        "line": func_data.get("lineno"),
                        "function": func_data.get("name"),
                        "class": func_data.get("classname"),
                        "complexity_grade": grade,
                        "description": f"Complex function '{func_data.get('name')}' (grade {grade})"
                    })
    except json.JSONDecodeError:
        logger.error("Failed to parse radon cc JSON output")

    return complex_functions

def parse_radon_mi_output(output: str) -> list:
    """Parse radon maintainability index output."""
    low_maintainability = []

    if not output:
        return low_maintainability

    try:
        data = json.loads(output)
        for file_path, metrics in data.items():
            grade = metrics.get("rank")
            mi_score = metrics.get("mi")
            # Only include grades D, E, F (low maintainability)
            if grade and grade in ['D', 'E', 'F']:
                low_maintainability.append({
                    "file": file_path,
                    "line": 1, # MI is per-file
                    "maintainability_index": mi_score,
                    "grade": grade,
                    "description": f"Low maintainability (MI: {mi_score:.2f}, grade {grade})"
                })
    except json.JSONDecodeError:
        logger.error("Failed to parse radon mi JSON output")

    return low_maintainability

def generate_report(dead_code: list, complex_functions: list, low_maintainability: list) -> str:
    """Generate a markdown report of the findings."""
    # ইউনিকোড (unicodeescape) এরর এড়াতে র-স্ট্রিং (raw string) ও f-string ব্যবহার করা হয়েছে
    report = fr"""# Dead Code and Code Quality Report

Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- **Dead Code Items**: {len(dead_code)}
- **Complex Functions**: {len(complex_functions)}
- **Low Maintainability Files**: {len(low_maintainability)}

---

## 🐛 Dead Code Detected

{("No dead code found!" if not dead_code else f"Found {len(dead_code)} potential dead code items:")}

"""

    if dead_code:
        report += "| File | Line | Type | Name | Confidence | Description |\n"
        report += "|------|------|------|------|------------|-------------|\n"
        for item in dead_code[:50]:  # Limit to top 50 to keep report readable
            report += f"| {item['file']} | {item['line']} | {item['type']} | {item['name']} | {item['confidence']}% | {item['description']} |\n"

        if len(dead_code) > 50:
            report += f"\n*... and {len(dead_code) - 50} more items*\n"

    report += "\n---\n\n"

    ## Complex Functions
    report += r"## ⚠️ Complex Functions (High Cyclomatic Complexity)" + "\n\n"
    report += f"({('None found' if not complex_functions else f'Found {len(complex_functions)} complex functions')})\n\n"

    if complex_functions:
        report += "| File | Line | Function | Class | Complexity | Description |\n"
        report += "|------|------|----------|-------|------------|-------------|\n"
        for item in complex_functions[:50]:
            class_name = item['class'] or '-'
            report += f"| {item['file']} | {item['line']} | {item['function']} | {class_name} | {item['complexity_grade']} | {item['description']} |\n"

        if len(complex_functions) > 50:
            report += f"\n*... and {len(complex_functions) - 50} more items*\n"

    report += "\n---\n\n"

    ## Low Maintainability
    report += r"## 📉 Low Maintainability Index" + "\n\n"
    report += f"({('None found' if not low_maintainability else f'Found {len(low_maintainability)} files with low maintainability')})\n\n"

    if low_maintainability:
        report += "| File | Line | MI Score | Grade | Description |\n"
        report += "|------|------|----------|-------|-------------|\n"
        for item in low_maintainability[:50]:
            report += f"| {item['file']} | {item['line']} | {item['maintainability_index']:.1f} | {item['grade']} | {item['description']} |\n"

        if len(low_maintainability) > 50:
            report += f"\n*... and {len(low_maintainability) - 50} more items*\n"

    report += "\n---\n\n"

    ## Recommendations
    report += r"## 🔧 Recommendations" + "\n\n"

    if dead_code:
        report += "### Dead Code Removal\n"
        review_items = [item for item in dead_code if item['confidence'] >= 90]
        if review_items:
            report += f"1. **High confidence items** ({len(review_items)}): Review and consider removing these items immediately.\n"
        else:
            report += "1. Review all items manually before removal as some may be falsely identified.\n"
        report += "2. Use `vulture --make-whitelist` to create a whitelist of false positives.\n"
        report += "3. Consider running tests after removal to ensure nothing breaks.\n\n"

    if complex_functions:
        report += "### Complex Function Refactoring\n"
        report += "1. Consider breaking down complex functions into smaller, more manageable units.\n"
        report += "2. Apply the Single Responsibility Principle (SRP).\n"
        report += "3. Look for opportunities to extract helper functions or classes.\n\n"

    if low_maintainability:
        report += "### Maintainability Improvement\n"
        report += "1. Focus on files with lowest MI scores first.\n"
        report += "2. Improve code readability, add comments, reduce nesting.\n"
        report += "3. Consider splitting large files into multiple modules.\n\n"

    if not any([dead_code, complex_functions, low_maintainability]):
        report += r"🎉 Excellent! No significant code quality issues detected." + "\n"

    return report

def create_github_issue(report_content: str) -> bool:
    """Create a GitHub issue with the report (if GitHub CLI is available)."""
    github_repo = os.getenv("GITHUB_REPOSITORY")
    try:
        # Check if gh is available
        subprocess.run(["gh", "--version"], capture_output=True, check=True)

        # Create issue
        title = f"Code Quality Report: {datetime.now().strftime('%Y-%m-%d')}"

        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", report_content,
            "--label", "tech-debt,autogenerated"
        ]

        if github_repo:
            cmd.extend(["--repo", github_repo])

        # Create issue
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info(f"✅ Created GitHub issue: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"❌ Failed to create GitHub issue: {result.stderr}")
            return False

    except FileNotFoundError:
        logger.warning("GitHub CLI ('gh') not found. Skipping issue creation.")
        return False
    except Exception as e:
        logger.error(f"❌ Error creating GitHub issue: {e}")
        return False

def main() -> int:
    """Main function to run dead code detection and generate report."""
    print(r"🔍 Starting dead code and code quality analysis...")
    print(fr"📂 Scanning directories: {', '.join(TARGET_DIRS)}")
    print(fr"🚫 Excluding patterns: {', '.join(EXCLUDE)}")
    print(fr"🎯 Minimum confidence: {MIN_CONFIDENCE}%")

    # Run analysis tools
    print(r"\n📊 Running vulture (dead code detection)...")
    vulture_output = run_vulture()

    print(r"📊 Running radon cc (cyclomatic complexity)...")
    radon_cc_output = run_radon_cc()

    print(r"📊 Running radon mi (maintainability index)...")
    radon_mi_output = run_radon_mi()

    # Parse results
    print(r"\n🔍 Parsing results...")
    dead_code = parse_vulture_output(vulture_output)
    complex_functions = parse_radon_cc_output(radon_cc_output)
    low_maintainability = parse_radon_mi_output(radon_mi_output)

    # Generate report
    print(r"📝 Generating report...")
    report = generate_report(dead_code, complex_functions, low_maintainability)

    # Save report
    output_path = Path(OUTPUT_FILE)
    output_path.write_text(report, encoding="utf-8")
    print(fr"📄 Report saved to: {output_path}")

    # Print summary
    print(r"\n📈 Summary:")
    print(fr"   🐛 Dead code items: {len(dead_code)}")
    print(fr"   ⚠️  Complex functions: {len(complex_functions)}")
    print(fr"   📉 Low maintainability: {len(low_maintainability)}")

    # Optionally create GitHub issue
    if CREATE_ISSUE:
        print(r"\n🐙 Creating GitHub issue...")
        create_github_issue(report)

    print(r"\n✅ Analysis complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
