import argparse
import asyncio
import os
from typing import Any

from core.logging_config import logger
from tools.code.auto_test_generator import AutoTestGenerator
from tools.devops.coverage_auditor import CoverageAuditor


class AutoCoverageImprover:
    """
    Orchestrates coverage analysis and automatic test generation
    to improve overall test coverage of a project.
    """

    def __init__(self):
        self.auditor = CoverageAuditor()
        self.generator = AutoTestGenerator()
        logger.info("Initialized AutoCoverageImprover")

    async def run(
        self,
        coverage_report_path: str,
        min_coverage_target: float = 80.0,  # লক্ষ্যমাত্রা ৮০% এ উন্নীত করা হলো
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Analyzes a coverage report, identifies gaps, and generates tests to fill them.

        Args:
            coverage_report_path: Path to the coverage.xml or coverage.json file.
            min_coverage_target: The minimum coverage percentage to aim for.
            dry_run: If True, will not write any files to disk.

        Returns:
            A report of the actions taken.
        """
        logger.info(f"Starting coverage improvement run for report: {coverage_report_path}")

        gaps = self.auditor.find_gaps(coverage_report_path, min_coverage=min_coverage_target)

        if not gaps:
            logger.info("No coverage gaps found. Excellent work!")
            return {
                "status": "success",
                "message": "No coverage gaps found.",
                "gaps_found": 0,
                "tests_generated": 0,
            }

        logger.info(f"Found {len(gaps)} file(s) with coverage below {min_coverage_target}%.")

        generation_results = []
        for gap in gaps:
            logger.info(
                f"Attempting to generate tests for '{gap.file_path}' (Coverage: {gap.coverage}%)"
            )
            if not os.path.exists(gap.file_path):
                logger.warning(f"Source file not found, skipping: {gap.file_path}")
                continue

            result = await self.generator.generate_and_save(gap.file_path, run_tests=not dry_run)
            generation_results.append(result)

        return {
            "status": "completed",
            "gaps_found": len(gaps),
            "tests_generated": sum(1 for r in generation_results if r.get("status") == "success"),
            "results": generation_results,
        }


async def main():
    """Command-line interface for the AutoCoverageImprover."""
    parser = argparse.ArgumentParser(description="Automatically find and fix test coverage gaps.")
    parser.add_argument(
        "coverage_report", help="Path to the coverage.xml or coverage.json report file."
    )
    parser.add_argument(
        "--min-target",
        type=float,
        default=80.0,  # ডিফল্ট লক্ষ্যমাত্রা ৮০% করা হলো
        help="The minimum coverage percentage to aim for. Default: 80.0",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, will identify gaps and generate tests without saving files or running tests.",
    )
    args = parser.parse_args()

    improver = AutoCoverageImprover()
    report = await improver.run(
        coverage_report_path=args.coverage_report,
        min_coverage_target=args.min_target,
        dry_run=args.dry_run,
    )
    logger.info(f"Run completed. Report: {report}")


if __name__ == "__main__":
    asyncio.run(main())
