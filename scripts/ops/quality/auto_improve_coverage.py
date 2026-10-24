#!/usr/bin/env python3
"""
Auto Improve Coverage Script
Automatically runs tests with coverage, identifies gaps, and generates tests to improve coverage.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Add the parent directory of backend to the path so we can import backend.tools
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

# বাংলা মন্তব্য:devops অটो কভারেজ ইমপ্রুভার ইম্পোর্ট করা হলো
from backend.tools.devops.auto_coverage_improver import AutoCoverageImprover


def extract_source_directories(coverage_report_path):
    """Extract source directories from coverage.xml report."""
    try:
        tree = ET.parse(coverage_report_path)
        root = tree.getroot()

        sources = []
        sources_element = root.find(".//sources")
        if sources_element is not None:
            for source_element in sources_element.findall("source"):
                source_path = source_element.text.strip()
                if source_path and os.path.isdir(source_path):
                    sources.append(source_path)

        return sources
    except Exception as e:
        print(f"Warning: Could not extract source directories from coverage report: {e}")
        return []


def resolve_file_path(filename, source_directories):
    """Resolve a filename to an absolute path by searching in source directories."""
    # If it's already an absolute path and exists, return it
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename

    # Try to find the file in each source directory
    for source_dir in source_directories:
        potential_path = os.path.join(source_dir, filename)
        if os.path.exists(potential_path):
            return potential_path

    # If not found, return the original (will be handled by caller)
    return filename


def run_tests_with_coverage(coverage_report_filename="coverage.xml"):
    """Run tests with coverage and generate coverage report."""
    print("Running tests with coverage...")

    # Change to backend directory where pyproject.toml is
    backend_dir = Path(__file__).parent.parent.parent / "backend"
    coverage_report_path = backend_dir / coverage_report_filename

    # বাংলা মন্তব্য: poetry যদি উপলব্ধ না থাকে তবে ভার্চুয়াল এনভায়রনমেন্ট বা সিস্টেম পাইথন ব্যবহার করে pytest রান করানোর ফলব্যাক যুক্ত করা হলো
    import shutil
    if shutil.which("poetry"):
        cmd = [
            "poetry", "run", "pytest",
            "--cov=backend",
            f"--cov-report=xml:{coverage_report_path}",
            "--cov-report=term-missing",
            "-q"
        ]
    else:
        venv_python = backend_dir.parent / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = backend_dir.parent / ".venv" / "bin" / "python"
        if not venv_python.exists():
            venv_python = Path(sys.executable)
        cmd = [
            str(venv_python), "-m", "pytest",
            "--cov=backend",
            f"--cov-report=xml:{coverage_report_path}",
            "--cov-report=term-missing",
            "-q"
        ]

    try:
        result = subprocess.run(
            cmd,
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        print("Test output:")
        print(result.stdout)
        if result.stderr:
            print("Test errors:")
            print(result.stderr)

        return result.returncode == 0, str(coverage_report_path)
    except subprocess.TimeoutExpired:
        print("Tests timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"Error running tests: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(
        description="Automatically improve test coverage by generating tests for uncovered code"
    )
    parser.add_argument(
        "--coverage-target",
        type=float,
        default=100.0,
        help="Minimum coverage percentage to aim for (default: 100.0)"
    )
    parser.add_argument(
        "--coverage-report",
        default="coverage.xml",
        help="Path to coverage report file (default: coverage.xml)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Identify gaps and generate tests without saving files or running tests"
    )
    parser.add_argument(
        "--skip-test-run",
        action="store_true",
        help="Skip running tests, only generate based on existing coverage report"
    )

    args = parser.parse_args()

    # Change to project root directory
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)

    print(f"Working in: {project_root}")
    print(f"Coverage target: {args.coverage_target}%")
    print(f"Dry run: {args.dry_run}")
    print(f"Skip test run: {args.skip_test_run}")
    print("-" * 50)

    # Step 1: Run tests with coverage (unless skipping)
    coverage_report_path = project_root / "backend" / args.coverage_report
    if not args.skip_test_run:
        success, report_path = run_tests_with_coverage(args.coverage_report)
        coverage_report_path = Path(report_path) if success else coverage_report_path
        if not success:
            print("Warning: Tests had failures or errors, but continuing with coverage analysis...")
    else:
        if not coverage_report_path.exists():
            print(f"Error: Coverage report not found at {coverage_report_path}")
            print("Run without --skip-test-run to generate a coverage report first.")
            return 1
        print(f"Using existing coverage report: {coverage_report_path}")

    # Extract source directories from coverage report
    source_directories = extract_source_directories(str(coverage_report_path))
    if source_directories:
        print(f"Found {len(source_directories)} source directories in coverage report")
    else:
        print("Warning: Could not extract source directories from coverage report")
        # Fallback to common directories
        source_directories = [
            str(project_root / "backend" / "api"),
            str(project_root / "backend" / "brain"),
            str(project_root / "backend" / "core"),
            str(project_root / "backend" / "memory"),
            str(project_root / "backend" / "tools")
        ]
        # Filter to only existing directories
        source_directories = [d for d in source_directories if os.path.isdir(d)]

    # Step 2: Use auto coverage improver to find gaps and generate tests
    print("\nAnalyzing coverage gaps and generating tests...")

    improver = AutoCoverageImprover()

    # Get gaps from auditor
    gaps = improver.auditor.find_gaps(str(coverage_report_path), min_coverage=args.coverage_target)

    if not gaps:
        print("No coverage gaps found. Excellent work!")
        result = {"status": "success", "message": "No coverage gaps found.", "gaps_found": 0, "tests_generated": 0}
    else:
        print(f"Found {len(gaps)} file(s) with coverage below {args.coverage_target}%.")

        generation_results = []
        for gap in gaps:
            # Resolve the file path using source directories
            resolved_path = resolve_file_path(gap.file_path, source_directories)

            print(f"Attempting to generate tests for '{gap.file_path}' (Coverage: {gap.coverage}%)")
            if not os.path.exists(resolved_path):
                print(f"Warning: Source file not found, skipping: {gap.file_path}")
                # Try to show what we looked for
                if resolved_path != gap.file_path:
                    print(f"  Resolved to: {resolved_path}")
                continue

            result = await improver.generator.generate_and_save(resolved_path, run_tests=not args.dry_run)
            generation_results.append(result)

        result = {
            "status": "completed",
            "gaps_found": len(gaps),
            "tests_generated": sum(1 for r in generation_results if r.get("status") == "success"),
            "results": generation_results,
        }

    # Step 3: Report results
    print("\n" + "="*50)
    print("COVERAGE IMPROVEMENT RESULTS")
    print("="*50)
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Message: {result.get('message', 'N/A')}")
    print(f"Gaps found: {result.get('gaps_found', 0)}")
    print(f"Tests generated: {result.get('tests_generated', 0)}")

    if result.get('results'):
        print("\nDetailed results:")
        for i, res in enumerate(result['results'], 1):
            status = res.get('status', 'unknown')
            file_path = res.get('file_path', 'unknown')
            print(f"  {i}. {file_path}: {status}")

    print("="*50)

    if result.get('status') == 'completed' and result.get('tests_generated', 0) > 0:
        print("\nNext steps:")
        print("1. Review the generated test files")
        print("2. Run the tests to verify they pass")
        print("3. Run coverage again to see improved coverage")

        if not args.dry_run:
            print("\nTo run tests with coverage again:")
            print("  cd backend && poetry run pytest --cov=backend --cov-report=term-missing")

    return 0 if result.get('status') in ['success', 'completed'] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
