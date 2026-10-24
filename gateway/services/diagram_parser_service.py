"""
SupremeAI — Diagram Parser Service
==================================

Dedicated diagram parsing service supporting multiple formats:
- PNG/SVG images (vision model analysis)
- Mermaid text diagrams
- PlantUML diagrams
- Draw.io XML diagrams
- Component relationship extraction
- Caching layer for performance
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.logging_config import logger
from services.config_service import ConfigService

# ── Constants ────────────────────────────────────────────────────────────────
DIAGRAM_CACHE_TTL = 3600  # 1 hour
MAX_DIAGRAM_SIZE = 10 * 1024 * 1024  # 10MB

router = APIRouter(prefix="/diagram-parser", tags=["diagram-parser"])


class DiagramType(StrEnum):
    IMAGE = "image"
    MERMAID = "mermaid"
    PLANTUML = "plantuml"
    DRAWIO = "drawio"
    AUTO = "auto"


@dataclass(frozen=True)
class ComponentNode:
    """A node in a diagram's component graph."""

    id: str
    label: str
    component_type: str
    properties: dict[str, Any]
    position: tuple[int, int] | None


@dataclass(frozen=True)
class ComponentEdge:
    """An edge/relationship between components."""

    source: str
    target: str
    label: str | None
    edge_type: str


class MermaidParser:
    """
    Parses Mermaid text diagrams into structured components and relationships.
    Supports flowchart, sequence, class, and state diagrams.
    """

    # Regex patterns for Mermaid syntax
    NODE_PATTERN = re.compile(r"(\w+)\s*(\[.*?\]|\(.*?\)|\{.*?\}|\(.*\))")
    EDGE_PATTERN = re.compile(r"(\w+)(-->|---|->|==>|..>|--o|o-->)\s*(\w+)\s*(:.*)?")
    SUBGRAPH_PATTERN = re.compile(r"subgraph\s+(\w+)", re.IGNORECASE)

    @classmethod
    def parse(cls, content: str) -> tuple[list[ComponentNode], list[ComponentEdge]]:
        nodes: list[ComponentNode] = []
        edges: list[ComponentEdge] = []
        node_ids = set()

        # Extract subgraphs (for grouping)
        subgraphs = cls.SUBGRAPH_PATTERN.findall(content)

        # Parse nodes
        for match in cls.NODE_PATTERN.finditer(content):
            node_id = match.group(1)
            label = match.group(2).strip("[](){}").strip()
            if node_id and node_id not in node_ids:
                nodes.append(
                    ComponentNode(
                        id=node_id,
                        label=label or node_id,
                        component_type="node",
                        properties={"subgraph": subgraphs[0] if subgraphs else None},
                        position=None,
                    )
                )
                node_ids.add(node_id)

        # Parse edges
        for match in cls.EDGE_PATTERN.finditer(content):
            source = match.group(1)
            arrow = match.group(2)
            target = match.group(3)
            label = match.group(4).lstrip(":").strip() if match.group(4) else None

            edges.append(
                ComponentEdge(
                    source=source,
                    target=target,
                    label=label,
                    edge_type=cls._normalize_edge_type(arrow),
                )
            )

        return nodes, edges

    @staticmethod
    def _normalize_edge_type(arrow: str) -> str:
        """Normalize Mermaid arrow syntax to edge type."""
        mapping = {
            "-->": "directed",
            "---": "undirected",
            "->": "directed",
            "==>": "dashed_directed",
            "..>": "dotted_directed",
            "--o": "aggregation",
            "o-->": "composition",
        }
        return mapping.get(arrow, "unknown")


class PlantUMLParser:
    """
    Parses PlantUML diagrams into structured components.
    Supports component, class, and deployment diagrams.
    """

    COMPONENT_PATTERN = re.compile(r"\[(.*?)\]\s*(.*)")
    RELATIONSHIP_PATTERN = re.compile(r"(.*)\s*[-.~]+(o*|>)?\s*(.*)")
    NOTE_PATTERN = re.compile(r"note\s+(right|left|top|bottom)\s+of\s+(\w+)", re.IGNORECASE)

    @classmethod
    def parse(cls, content: str) -> tuple[list[ComponentNode], list[ComponentEdge]]:
        nodes: list[ComponentNode] = []
        edges: list[ComponentEdge] = []
        node_ids = set()

        # Parse components
        for match in cls.COMPONENT_PATTERN.finditer(content):
            label = match.group(1)
            component_id = label.replace(" ", "_").lower()[:30]
            if component_id not in node_ids:
                nodes.append(
                    ComponentNode(
                        id=component_id,
                        label=label,
                        component_type="component",
                        properties={"description": match.group(2).strip()},
                        position=None,
                    )
                )
                node_ids.add(component_id)

        # Parse relationships
        for match in cls.RELATIONSHIP_PATTERN.finditer(content):
            source = match.group(1).strip().replace(" ", "_").lower()[:30]
            target = match.group(3).strip().replace(" ", "_").lower()[:30]
            if source and target:
                edges.append(
                    ComponentEdge(
                        source=source,
                        target=target,
                        label=None,
                        edge_type="association",
                    )
                )

        return nodes, edges


class DrawIOParser:
    """
    Parses Draw.io XML diagrams into structured components.
    Extracts objects and connections from mxfile format.
    """

    @classmethod
    def parse(cls, xml_content: str) -> tuple[list[ComponentNode], list[ComponentEdge]]:
        # বাংলা মন্তব্য: SECURITY FIX — user-uploaded diagram content stdlib
        # xml.etree.ElementTree দিয়ে পার্স করা হলে XXE (XML External Entity)
        # আক্রমণের ঝুঁকি থাকে। defusedxml ব্যবহার করা হলো, যেটা external
        # entity resolution ও DTD-ভিত্তিক আক্রমণ ব্লক করে দেয়।
        from defusedxml import ElementTree as ET

        nodes: list[ComponentNode] = []
        edges: list[ComponentEdge] = []

        try:
            root = ET.fromstring(xml_content)

            # Find all cells with style (shapes)
            for cell in root.iter():
                if cell.get("style") and cell.get("value"):
                    node_id = cell.get("id", "")
                    value = cell.get("value", "")
                    style = cell.get("style", "")

                    nodes.append(
                        ComponentNode(
                            id=node_id,
                            label=value,
                            component_type=cls._extract_component_type(style),
                            properties={"style": style},
                            position=cls._extract_position(cell),
                        )
                    )

                # Extract edges
                if cell.get("source") and cell.get("target"):
                    edges.append(
                        ComponentEdge(
                            source=cell.get("source", ""),
                            target=cell.get("target", ""),
                            label=cell.get("value"),
                            edge_type=cls._extract_edge_type(cell.get("style", "")),
                        )
                    )
        except ET.ParseError as e:
            logger.error(f"Failed to parse Draw.io XML: {e}")

        return nodes, edges

    @staticmethod
    def _extract_component_type(style: str) -> str:
        """Extract component type from Draw.io style string."""
        if "ellipse" in style:
            return "terminal"
        if "shape=umlClass" in style:
            return "class"
        if "shape=process" in style:
            return "process"
        if "shape=cloud" in style:
            return "cloud"
        return "component"

    @staticmethod
    def _extract_position(cell: Any) -> tuple[int, int] | None:
        """Extract position from cell geometry."""
        try:
            x = int(float(cell.get("x", "0") or "0"))
            y = int(float(cell.get("y", "0") or "0"))
            return (x, y)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_edge_type(style: str) -> str:
        """Extract edge type from style."""
        if "dashed" in style:
            return "dashed"
        if "dotted" in style:
            return "dotted"
        return "directed"


class VisionAnalyzer:
    """
    Analyzes image-based diagrams using vision model.
    Extracted components and relationships from screenshots.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()
        self.cache = get_cache()

    def _cache_key(self, image_path: str) -> str:
        stat = os.stat(image_path) if os.path.exists(image_path) else None
        stat_str = f"{stat.st_mtime}" if stat else ""
        return f"diagram_vision:{hashlib.sha256((image_path + stat_str).encode()).hexdigest()[:16]}"

    async def analyze(
        self, image_path: str, diagram_type: DiagramType = DiagramType.IMAGE
    ) -> tuple[list[ComponentNode], list[ComponentEdge]]:
        """
        Analyze an image diagram using vision model.

        Args:
            image_path: Path to image file.
            diagram_type: Expected diagram type (for prompt tuning).

        Returns:
            Tuple of (nodes, edges) extracted from the diagram.
        """
        cache_key = self._cache_key(image_path)
        cached = await self.cache.get(cache_key)
        if cached:
            return tuple(
                ComponentNode(**n) if isinstance(n, dict) else n for n in cached[0]
            ), tuple(  # type: ignore
                ComponentEdge(**e) if isinstance(e, dict) else e for e in cached[1]
            )

        # Encode image
        import base64

        # NOTE (issue #2249): the base64 payload previously fed the legacy
        # `images=[...]` kwarg, which NO provider in the retired services/llm
        # stack ever consumed (payloads were text-only). The read is kept for
        # exact file-validation parity; the kwarg is no longer forwarded.
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")  # noqa: F841 — see note above

        # Build prompt based on diagram type
        prompts = {
            DiagramType.IMAGE: (
                "Analyze this architecture diagram and extract all components (servers, "
                "databases, APIs, services) and their connections. Return JSON: "
                '{"nodes": [{"id", "label", "type", "position"}], "edges": [{"source", "target", "label"}]}'
            ),
            DiagramType.CLASS: (
                "Analyze this UML class diagram and extract all classes, their attributes, "
                "methods, and relationships. Return JSON: "
                '{"nodes": [{"id", "label", "type"}], "edges": [{"source", "target", "type"}]}'
            ),
            DiagramType.SEQUENCE: (
                "Analyze this sequence diagram and extract all participants and their "
                "message flows. Return JSON: "
                '{"nodes": [{"id", "label", "type"}], "edges": [{"source", "target", "label"}]}'
            ),
        }

        prompt = prompts.get(
            diagram_type,
            "Analyze this diagram and extract components and connections as JSON.",
        )

        try:
            max_tokens = await ConfigService.get_config(None, "llm_max_tokens_diagram", 1500)
            result = await self.llm_router.async_route_and_generate(
                prompt=prompt,
                task_type="vision",
                max_tokens=max_tokens,
                # NOTE (issue #2249): the legacy `images=[...]` kwarg was dropped
                # here — git archaeology on the retired providers.py confirms NO
                # provider ever consumed it (payload built text-only parts), so
                # removing it is a zero-capability-change cleanup.
            )

            text = result.get("text", "") if isinstance(result, dict) else ""
            # Clean JSON
            text = re.sub(r"^```(?:json)?\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            nodes = [
                ComponentNode(
                    id=n.get("id", f"n_{i}"),
                    label=n.get("label", ""),
                    component_type=n.get("type", "component"),
                    properties={},
                    position=(tuple(n.get("position", (0, 0))) if n.get("position") else None),
                )
                for i, n in enumerate(data.get("nodes", []))
            ]
            edges = [
                ComponentEdge(
                    source=e.get("source", ""),
                    target=e.get("target", ""),
                    label=e.get("label"),
                    edge_type=e.get("type", "directed"),
                )
                for e in data.get("edges", [])
            ]

            await self.cache.set(
                cache_key,
                ([n.__dict__ for n in nodes], [e.__dict__ for e in edges]),
                ttl=DIAGRAM_CACHE_TTL,
            )

            return nodes, edges

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return [], []


class DiagramParserService:
    """
    Unified diagram parsing service with multiple backend support.
    Automatically detects format and routes to appropriate parser.
    """

    def __init__(self) -> None:
        self.mermaid = MermaidParser()
        self.plantuml = PlantUMLParser()
        self.drawio = DrawIOParser()
        self.vision = VisionAnalyzer()
        self.cache = get_cache()

    def detect_format(self, content: str | None, filename: str | None = None) -> DiagramType:
        """Detect diagram format from content or filename."""
        if content:
            if "graph TD" in content or "graph LR" in content:
                return DiagramType.MERMAID
            if "@startuml" in content.lower():
                return DiagramType.PLANTUML
            if content.strip().startswith("<?xml") or "<mxfile" in content:
                return DiagramType.DRAWIO

        if filename:
            ext = Path(filename).suffix.lower()
            if ext in (".mmd", ".mermaid"):
                return DiagramType.MERMAID
            if ext == ".puml":
                return DiagramType.PLANTUML
            if ext == ".drawio":
                return DiagramType.DRAWIO

        return DiagramType.IMAGE

    async def parse(
        self,
        content: str | None = None,
        image_path: str | None = None,
        filename: str | None = None,
    ) -> tuple[list[ComponentNode], list[ComponentEdge]]:
        """
        Parse a diagram into structured components.

        Args:
            content: Text content for text-based diagrams.
            image_path: Path to image for vision-based analysis.
            filename: Filename hint for format detection.

        Returns:
            Tuple of (nodes, edges) components.
        """
        if content and not image_path:
            diagram_type = self.detect_format(content, filename)

            if diagram_type == DiagramType.MERMAID:
                return self.mermaid.parse(content)
            if diagram_type == DiagramType.PLANTUML:
                return self.plantuml.parse(content)
            if diagram_type == DiagramType.DRAWIO:
                return self.drawio.parse(content)

        if image_path:
            diagram_type = self.detect_format(None, filename) or DiagramType.IMAGE
            return await self.vision.analyze(image_path, diagram_type)

        return [], []

    async def to_infrastructure(
        self,
        nodes: list[ComponentNode],
        edges: list[ComponentEdge],
        provider: str = "aws",
        iac_tool: str = "terraform",
    ) -> dict[str, Any]:
        """Convert parsed components to infrastructure code."""
        # This integrates with the existing diagram_to_architecture

        # Build approximate diagram representation
        diagram_description = self._build_description(nodes, edges)

        # Generate via LLM (Phase-2.1 #2249: canonical facade)
        llm = ModelRouter()
        prompt = (
            f"Generate {iac_tool} code for {provider} based on this architecture: "
            f"{diagram_description}. Return only valid {iac_tool} code, no markdown."
        )

        try:
            max_tokens = await ConfigService.get_config(None, "llm_max_tokens_diagram", 2000)
            result = await llm.async_route_and_generate(
                prompt=prompt,
                task_type="generation",
                max_tokens=max_tokens,
            )
            return {
                "status": "success",
                "iac_tool": iac_tool,
                "provider": provider,
                "code": result.get("text", ""),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _build_description(self, nodes: list[ComponentNode], edges: list[ComponentEdge]) -> str:
        """Build human-readable description of diagram."""
        desc = f"Components: {', '.join(n.label for n in nodes)}"
        if edges:
            desc += f". Connections: {len(edges)} relationships."
        return desc


# Singleton
_service_instance: DiagramParserService | None = None


def get_diagram_parser() -> DiagramParserService:
    """Get or create the singleton DiagramParserService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DiagramParserService()
    return _service_instance
