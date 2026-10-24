#!/usr/bin/env python
"""
auto_refactor_suggester.py
==========================
Automatically suggests refactoring opportunities based on code analysis.

Uses various heuristics and code metrics to identify areas that could benefit
from refactoring, such as long methods, large classes, duplicate code, etc.

Environment Variables:
- TARGET_DIRS: Comma-separated list of directories to scan (default: backend,apps)
- OUTPUT_FILE: Path to output report (default: refactoring_suggestions.md)
- EXCLUDE: Comma-separated list of patterns to exclude (default: __init__.py,migrations,tests,test_*)
- THRESHOLD_LINES: Maximum lines per function before suggesting refactor (default: 50)
- THRESHOLD_PARAMETERS: Maximum parameters before suggesting refactor (default: 5)
- THRESHOLD_NESTING: Maximum nesting depth before suggesting refactor (default: 4)
"""

import ast
import logging
import os
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_DIRS = os.getenv("TARGET_DIRS", "backend,apps").split(",")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "refactoring_suggestions.md")
EXCLUDE = os.getenv("EXCLUDE", "__init__.py,migrations,tests,test_*").split(",")
THRESHOLD_LINES = int(os.getenv("THRESHOLD_LINES", "50"))
THRESHOLD_PARAMETERS = int(os.getenv("THRESHOLD_PARAMETERS", "5"))
THRESHOLD_NESTING = int(os.getenv("THRESHOLD_NESTING", "4"))

def should_exclude_file(file_path: Path) -> bool:
    """Check if a file should be excluded based on patterns."""
    for pattern in EXCLUDE:
        if "*" in pattern:
            # Simple glob matching
            import fnmatch
            if fnmatch.fnmatch(file_path.name, pattern):
                return True
        else:
            if pattern in str(file_path):
                return True
    return False

def get_python_files() -> list[Path]:
    """Get all Python files to analyze."""
    python_files = []

    for directory_str in TARGET_DIRS:
        directory = Path(directory_str)
        if not directory.exists():
            logger.warning(f"Directory {directory} does not exist, skipping")
            continue

        for py_file in directory.rglob("*.py"):
            if not should_exclude_file(py_file) and py_file.is_file():
                python_files.append(py_file)

    return python_files

def count_lines_in_node(node: ast.AST, source_lines: list[str]) -> int:
    """Count the number of physical lines in an AST node."""
    if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
        return node.end_lineno - node.lineno + 1
    return 0

def count_parameters(node: ast.FunctionDef) -> int:
    """Count the number of parameters in a function definition."""
    # Count regular args
    count = len(node.args.args)
    # Count *args
    if node.args.vararg:
        count += 1
    # Count **kwargs
    if node.args.kwarg:
        count += 1
    # Count keyword-only args
    count += len(node.args.kwonlyargs)
    return count

def calculate_nesting_depth(node: ast.AST, current_depth: int = 0) -> int:
    """Calculate the maximum nesting depth of control structures."""
    max_depth = current_depth

    # Increase depth for control flow statements
    if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While,
                        ast.With, ast.AsyncWith, ast.Try,
                        ast.ExceptHandler)):
        current_depth += 1

    # Check children
    for child in ast.iter_child_nodes(node):
        child_depth = calculate_nesting_depth(child, current_depth)
        max_depth = max(max_depth, child_depth)

    return max_depth

def analyze_function(func_node: ast.FunctionDef, class_name: str | None,
                    source_lines: list[str], file_path: Path) -> list[dict[str, Any]]:
    """Analyze a function for refactoring opportunities."""
    suggestions = []

    # Get function location
    start_line = func_node.lineno
    end_line = getattr(func_node, 'end_lineno', start_line)
    lines_count = end_line - start_line + 1

    # Check function length
    if lines_count > THRESHOLD_LINES:
        suggestions.append({
            "type": "Long Function",
            "priority": "High" if lines_count > THRESHOLD_LINES * 2 else "Medium",
            "file": str(file_path),
            "line": start_line,
            "function": f"{class_name + '.' if class_name else ''}{func_node.name}",
            "issue": f"Function has {lines_count} lines (threshold: {THRESHOLD_LINES})",
            "suggestion": "Break down into smaller, focused functions"
        })

    # Check parameter count
    param_count = count_parameters(func_node)
    if param_count > THRESHOLD_PARAMETERS:
        suggestions.append({
            "type": "Too Many Parameters",
            "priority": "Medium",
            "file": str(file_path),
            "line": start_line,
            "function": f"{class_name + '.' if class_name else ''}{func_node.name}",
            "issue": f"Function has {param_count} parameters (threshold: {THRESHOLD_PARAMETERS})",
            "suggestion": "Consider using a data class or dictionary to group related parameters"
        })

    # Check nesting depth
    nesting_depth = calculate_nesting_depth(func_node)
    if nesting_depth > THRESHOLD_NESTING:
        suggestions.append({
            "type": "Deep Nesting",
            "priority": "Medium",
            "file": str(file_path),
            "line": start_line,
            "function": f"{class_name + '.' if class_name else ''}{func_node.name}",
            "issue": f"Function has nesting depth of {nesting_depth} (threshold: {THRESHOLD_NESTING})",
            "suggestion": "Extract nested blocks into separate functions or use early returns"
        })

    return suggestions

def analyze_class(class_node: ast.ClassDef, source_lines: list[str],
                 file_path: Path) -> list[dict[str, Any]]:
    """Analyze a class for refactoring opportunities."""
    suggestions = []

    # Get class location
    start_line = class_node.lineno
    end_line = getattr(class_node, 'end_lineno', start_line)
    lines_count = end_line - start_line + 1

    # Count methods
    method_count = sum(1 for node in class_node.body if isinstance(node, ast.FunctionDef))

    # Check class size
    if lines_count > 300:  # Arbitrary large class threshold
        suggestions.append({
            "type": "Large Class",
            "priority": "Medium",
            "file": str(file_path),
            "line": start_line,
            "class": class_node.name,
            "issue": f"Class has {lines_count} lines and {method_count} methods",
            "suggestion": "Consider splitting into smaller, more focused classes"
        })

    # Check for too many methods (God Class symptom)
    if method_count > 20:
        suggestions.append({
            "type": "Too Many Methods",
            "priority": "Medium",
            "file": str(file_path),
            "line": start_line,
            "class": class_node.name,
            "issue": f"Class has {method_count} methods",
            "suggestion": "Consider applying Single Responsibility Principle - split into multiple classes"
        })

    return suggestions

def detect_duplicate_code(file_paths: list[Path]) -> list[dict[str, Any]]:
    """Detect duplicate code blocks using simple hashing (basic implementation)."""
    # This is a simplified version - for production, consider using tools like copy-paste-duplicate-finder
    # or more sophisticated algorithms
    suggestions = []

    # For now, we'll skip this as it's complex to implement well in a short script
    # In a real implementation, you would:
    # 1. Extract function bodies
    # 2. Normalize them (remove whitespace, rename variables)
    # 3. Hash them and look for duplicates
    # 4. Report similarities above a threshold

    return suggestions

def analyze_file(file_path: Path) -> list[dict[str, Any]]:
    """Analyze a single Python file for refactoring opportunities."""
    suggestions = []

    try:
        content = file_path.read_text(encoding="utf-8")
        source_lines = content.splitlines()
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError) as e:
        logger.warning(f"Could not parse {file_path}: {e}")
        return suggestions
    except Exception as e:
        logger.warning(f"Error reading {file_path}: {e}")
        return suggestions

    # Walk through the AST
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Top-level function
            suggestions.extend(
                analyze_function(node, None, source_lines, file_path)
            )
        elif isinstance(node, ast.ClassDef):
            # Class
            suggestions.extend(
                analyze_class(node, source_lines, file_path)
            )
            # Also analyze methods within the class
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    suggestions.extend(
                        analyze_function(child, node.name, source_lines, file_path)
                    )

    return suggestions

def generate_report(suggestions: list[dict[str, Any]]) -> str:
    """Generate a markdown report of refactoring suggestions."""
    from datetime import datetime

    if not suggestions:
        return f"""# Refactoring Suggestions Report

Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
🎉 Excellent! No refactoring suggestions found based on the configured thresholds.

## Configuration
- Function line threshold: {THRESHOLD_LINES}
- Parameter threshold: {THRESHOLD_PARAMETERS}
- Nesting depth threshold: {THRESHOLD_NESTING}
- Target directories: {', '.join(TARGET_DIRS)}
"""

    # Group by type
    by_type = {}
    for suggestion in suggestions:
        s_type = suggestion["type"]
        if s_type not in by_type:
            by_type[s_type] = []
        by_type[s_type].append(suggestion)

    # Sort types by priority and count
    type_order = sorted(by_type.keys(),
                       key=lambda t: (
                           -len([s for s in by_type[t] if s.get("priority") == "High"]),
                           -len([s for s in by_type[t] if s.get("priority") == "Medium"]),
                           -len(by_type[t])
                       ))

    report = f"""# Refactoring Suggestions Report

Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- **Total Suggestions**: {len(suggestions)}
- **High Priority**: {len([s for s in suggestions if s.get('priority') == 'High'])}
- **Medium Priority**: {len([s for s in suggestions if s.get('priority') == 'Medium'])}
- **Low Priority**: {len([s for s in suggestions if s.get('priority') == 'Low'])}

## Configuration
- Function line threshold: {THRESHOLD_LINES}
- Parameter threshold: {THRESHOLD_PARAMETERS}
- Nesting depth threshold: {THRESHOLD_NESTING}
- Target directories: {', '.join(TARGET_DIRS)}
"""

    # Add sections for each type
    for suggestion_type in type_order:
        suggestions_list = by_type[suggestion_type]

        # Count by priority
        high_count = len([s for s in suggestions_list if s.get('priority') == 'High'])
        medium_count = len([s for s in suggestions_list if s.get('priority') == 'Medium'])
        low_count = len([s for s in suggestions_list if s.get('priority') == 'Low'])

        priority_text = []
        if high_count > 0:
            priority_text.append(f"{high_count} High")
        if medium_count > 0:
            priority_text.append(f"{medium_count} Medium")
        if low_count > 0:
            priority_text.append(f"{low_count} Low")

        priority_str = ", ".join(priority_text) if priority_text else "No priority specified"

        report += f"\n## {suggestion_type} ({len(suggestions_list)} items - {priority_str})\n\n"

        # Create table
        if suggestions_list:
            # Determine columns based on what's present
            sample = suggestions_list[0]
            columns = ["File", "Line"]
            if "function" in sample:
                columns.append("Function")
            if "class" in sample:
                columns.append("Class")
            columns.extend(["Issue", "Suggestion"])

            # Add priority column if present
            if "priority" in sample:
                columns.insert(-2, "Priority")  # Insert before Suggestion

            # Create header
            header = "| " + " | ".join(columns) + " |"
            separator = "|" + "|".join(["---" for _ in columns]) + "|"
            report += header + "\n" + separator + "\n"

            # Add rows (limit to 50 per section to keep report readable)
            for suggestion in suggestions_list[:50]:
                row_data = [
                    suggestion.get("file", ""),
                    str(suggestion.get("line", ""))
                ]

                if "function" in sample:
                    row_data.append(suggestion.get("function", ""))

                if "class" in sample:
                    row_data.append(suggestion.get("class", ""))

                if "priority" in suggestion:
                    priority = suggestion["priority"]
                    # Add emoji for visual cue
                    priority_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
                    emoji = priority_emoji.get(priority, "⚪")
                    row_data.append(f"{emoji} {priority}")

                row_data.extend([
                    suggestion.get("issue", ""),
                    suggestion.get("suggestion", "")
                ])

                # Escape pipe characters
                row_data = [str(cell).replace("|", "\\|") for cell in row_data]

                row = "| " + " | ".join(row_data) + " |"
                report += row + "\n"

            if len(suggestions_list) > 50:
                report += f"\n*... and {len(suggestions_list) - 50} more items*\n"

        # Add summary and recommendations for this type
        if suggestion_type == "Long Function":
            report += "\n### Recommendations:\n"
            report += "1. Apply the Extract Method refactoring technique\n"
            report += "2. Look for logical groupings of statements that can become separate functions\n"
            report += "3. Consider using early returns to reduce nesting\n"
        elif suggestion_type == "Too Many Parameters":
            report += "\n### Recommendations:\n"
            report += "1. Introduce Parameter Object: group related parameters into a class\n"
            report += "2. Preserve Whole Object: if parameters come from same object, pass the object\n"
            report += "3. Remove Setting Method: if some parameters are used to set state, use setter methods\n"
        elif suggestion_type == "Deep Nesting":
            report += "\n### Recommendations:\n"
            report += "1. Use guard clauses for early returns\n"
            report += "2. Extract nested logic into separate functions\n"
            report += "3. Consider using the Strategy Pattern for complex conditional logic\n"
        elif suggestion_type == "Large Class":
            report += "\n### Recommendations:\n"
            report += "1. Apply Extract Class: group related fields and methods into a new class\n"
            report += "2. Use Superclass Extraction if there's common behavior\n"
            report += "3. Consider if the class is trying to do too much (Single Responsibility Principle)\n"
        elif suggestion_type == "Too Many Methods":
            report += "\n### Recommendations:\n"
            report += "1. Look for clusters of methods that work on similar data\n"
            report += "2. Apply Extract Class to group related functionality\n"
            report += "3. Consider using Facade or Mediator patterns if this is a complex interface\n"

    return report

def main() -> int:
    """Main function to run refactoring analysis."""
    print("🔍 Starting refactoring analysis...")
    print(f"📂 Scanning directories: {', '.join(TARGET_DIRS)}")
    print(f"🚫 Excluding patterns: {', '.join(EXCLUDE)}")
    print(f"📏 Function line threshold: {THRESHOLD_LINES}")
    print(f"🔢 Parameter threshold: {THRESHOLD_PARAMETERS}")
    print(f"🔀 Nesting depth threshold: {THRESHOLD_NESTING}")

    # Get Python files
    python_files = get_python_files()
    print(f"📄 Found {len(python_files)} Python files to analyze")

    if not python_files:
        print("⚠️  No Python files found to analyze")
        return 1

    # Analyze each file
    all_suggestions = []
    for i, file_path in enumerate(python_files, 1):
        if i % 50 == 0 or i == len(python_files):
            print(f"🔍 Analyzing file {i}/{len(python_files)}: {file_path}")

        suggestions = analyze_file(file_path)
        all_suggestions.extend(suggestions)

    # Generate report
    print("📝 Generating report...")
    report = generate_report(all_suggestions)

    # Save report
    output_path = Path(OUTPUT_FILE)
    output_path.write_text(report, encoding="utf-8")
    print(f"📄 Report saved to: {output_path}")

    # Print summary
    print("\n📈 Summary:")
    print(f"   📄 Files analyzed: {len(python_files)}")
    print(f"   💡 Suggestions found: {len(all_suggestions)}")

    if all_suggestions:
        high_priority = len([s for s in all_suggestions if s.get('priority') == 'High'])
        medium_priority = len([s for s in all_suggestions if s.get('priority') == 'Medium'])
        low_priority = len([s for s in all_suggestions if s.get('priority') == 'Low'])
        print(f"   🔴 High priority: {high_priority}")
        print(f"   🟡 Medium priority: {medium_priority}")
        print(f"   🟢 Low priority: {low_priority}")

        if high_priority > 0:
            print("\n💡 Recommendation: Address high-priority items first")
    else:
        print("   🎉 No refactoring suggestions found!")

    print("\n✅ Analysis complete!")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
