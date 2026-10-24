import json
import os
from dataclasses import dataclass

import defusedxml.ElementTree as ET  # -- standard idiom (mirrors stdlib xml.etree.ElementTree as ET)

from core.logging_config import logger


@dataclass
class CoverageGap:
    file_path: str
    coverage: float
    uncovered_lines: list[int]


class CoverageAuditor:
    def find_gaps(self, report_path: str, min_coverage: float = 80.0) -> list[CoverageGap]:
        if not os.path.exists(report_path):
            logger.warning(f"Coverage report not found: {report_path}")
            return []

        try:
            if report_path.endswith(".xml"):
                return self._parse_xml(report_path, min_coverage)
            elif report_path.endswith(".json"):
                return self._parse_json(report_path, min_coverage)
            else:
                logger.warning(f"Unsupported coverage report format: {report_path}")
                return []
        except Exception as e:
            logger.error(f"Failed to parse coverage report {report_path}: {e}")
            return []

    def _parse_xml(self, report_path: str, min_coverage: float) -> list[CoverageGap]:
        gaps = []
        tree = ET.parse(report_path)
        root = tree.getroot()
        for class_node in root.findall(".//class"):
            line_rate_str = class_node.get("line-rate")
            if line_rate_str is None:
                continue

            coverage = float(line_rate_str) * 100
            if coverage < min_coverage:
                file_path = class_node.get("filename")
                if not file_path:
                    continue

                uncovered_lines = [
                    int(line.get("number"))
                    for line in class_node.findall(".//line")
                    if line.get("hits") == "0"
                ]
                gaps.append(
                    CoverageGap(
                        file_path=file_path,
                        coverage=round(coverage, 2),
                        uncovered_lines=uncovered_lines,
                    )
                )
        return gaps

    def _parse_json(self, report_path: str, min_coverage: float) -> list[CoverageGap]:
        gaps = []
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)

        # Handle Istanbul JSON summary format
        if "total" in data and isinstance(data, dict):
            for file_path, summary in data.items():
                if file_path == "total":
                    continue

                lines_pct = summary.get("lines", {}).get("pct", 100.0)
                if lines_pct < min_coverage:
                    uncovered_lines = summary.get("uncovered_lines", []) or summary.get(
                        "lines", {}
                    ).get("uncovered_lines", [])
                    gaps.append(
                        CoverageGap(
                            file_path=file_path,
                            coverage=round(lines_pct, 2),
                            uncovered_lines=uncovered_lines,
                        )
                    )
        return gaps
