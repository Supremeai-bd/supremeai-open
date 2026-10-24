from __future__ import annotations

import os
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext


class VisionAgent:
    def __init__(self, languages: list[str] | None = None) -> None:
        self.languages = languages or ["en", "bn"]

    def analyze_image(self, image_path: str) -> dict[str, Any]:
        try:
            import easyocr  # type: ignore[import-untyped]
        except Exception as exc:
            logger.error(f"EasyOCR is not available: {exc}")
            return {"success": False, "error": str(exc), "text": "", "structured": {}}

        reader: Any | None = None
        try:
            reader = easyocr.Reader(self.languages, gpu=False)
            raw_results = reader.readtext(image_path, detail=1, paragraph=False)
            text_lines = [
                {"text": text, "confidence": confidence}
                for (_bbox, text, confidence) in raw_results
            ]
            full_text = "\n".join(item["text"] for item in text_lines)
            return {
                "success": True,
                "text": full_text,
                "lines": text_lines,
                "structured": self._structure(text_lines),
            }
        except Exception as exc:
            logger.error(f"Vision image analysis failed: {exc}")
            return {"success": False, "error": str(exc), "text": "", "structured": {}}

    def analyze_pdf(self, pdf_path: str) -> dict[str, Any]:
        try:
            text_pages = self._extract_pdf_text(pdf_path)
            cover_text = self._summarize(text_pages[:2]) if text_pages else ""
            return {
                "success": True,
                "path": pdf_path,
                "pages": len(text_pages),
                "text": "\n\n".join(text_pages),
                "summary": cover_text,
                "structured": {"pages": len(text_pages)},
            }
        except Exception as exc:
            logger.error(f"Vision PDF analysis failed: {exc}")
            return {"success": False, "error": str(exc), "text": "", "structured": {}}

    def analyze_chart(self, image_path: str) -> dict[str, Any]:
        result = self.analyze_image(image_path)
        if not result.get("success"):
            return result
        lines = result.get("lines", [])
        chart_hints = [
            ln["text"]
            for ln in lines
            if any(
                k in ln["text"].lower()
                for k in ["data", "axis", "value", "x:", "y:", "legend", "label"]
            )
        ]
        structured = dict(result.get("structured", {}))
        structured.update({"chart_hints": chart_hints, "estimated_labels": len(chart_hints)})
        return {
            "success": True,
            "text": result["text"],
            "lines": lines,
            "structured": structured,
        }

    @staticmethod
    def _structure(lines: list[dict[str, Any]]) -> dict[str, Any]:
        entry = {
            "line_count": len(lines),
            "average_confidence": 0.0,
            "languages": ["en"],
        }
        if not lines:
            return entry
        confidences = [ln["confidence"] for ln in lines]
        entry["average_confidence"] = round(sum(confidences) / len(confidences), 4)
        return entry

    @staticmethod
    @with_error_bus("_extract_pdf_text")
    def _extract_pdf_text(pdf_path: str) -> list[str]:
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            return [page.get_text("text") for page in doc if not page.is_closed]
        except ImportError as e:
            logger.exception(f"❌ Critical task failure in vision_agent.py: {e}")
            from core.messaging.event_bus import ErrorEvent, error_event_bus

            error_event_bus.emit(
                ErrorEvent(
                    module="backend.tools.vision_agent",
                    error_type=type(e).__name__,
                    message=str(e),
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"action": "extract_pdf_text_fitz"},
                )
            )
        try:
            import pdfplumber

            pages = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    pages.append(page.extract_text() or "")
            return pages
        except ImportError as e:
            logger.exception(f"❌ Critical task failure in vision_agent.py: {e}")
            from core.messaging.event_bus import ErrorEvent, error_event_bus

            error_event_bus.emit(
                ErrorEvent(
                    module="backend.tools.vision_agent",
                    error_type=type(e).__name__,
                    message=str(e),
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"action": "extract_pdf_text_pdfplumber"},
                )
            )
        logger.warning("Neither PyMuPDF nor pdfplumber is available for PDF extraction.")
        stub_path = os.path.splitext(pdf_path)[0] + ".txt"
        if os.path.exists(stub_path):
            with open(stub_path, encoding="utf-8") as f:
                return [f.read()]
        return [f"[stub] PDF text extraction unavailable for: {pdf_path}"]

    @staticmethod
    def _summarize(texts: list[str]) -> str:
        joined = " ".join(texts).strip()
        return joined[:800] + ("..." if len(joined) > 800 else "")
