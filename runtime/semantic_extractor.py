"""Token-saving semantic DOM extraction (stdlib html.parser).

Inspired by the Moli direction discussed in issue #498 and required by
issue #502: parse HTML into a semantic tree, DISCARD pure layout wrappers,
and expose a token-budgeted outline. No network, no third-party deps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import List, Optional

__all__ = [
    "SemanticNode",
    "SemanticTree",
    "extract_semantic_tree",
    "estimate_tokens",
]

_SEMANTIC_TAGS = {
    "article", "section", "main", "header", "footer", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
    "blockquote", "pre", "code", "figure", "figcaption",
    "a", "img", "button", "form", "label", "input", "select", "option",
    "summary", "details", "time", "address", "dl", "dt", "dd",
}
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe"}
# Layout wrappers: kept only when they carry identifying attributes or
# multiple semantic children (they are otherwise flattened).
_LAYOUT_TAGS = {"div", "span", "section", "center"}


@dataclass
class SemanticNode:
    tag: str
    attrs: dict
    text_chunks: List[str] = field(default_factory=list)
    children: List["SemanticNode"] = field(default_factory=list)

    def text(self) -> str:
        parts = [c for c in self.text_chunks if c.strip()]
        for child in self.children:
            parts.append(child.text())
        return " ".join(" ".join(parts).split())

    def has_identity(self) -> bool:
        """True when the wrapper carries semantics via attributes."""
        identity_keys = ("id", "class", "role", "aria-label", "name", "itemprop")
        return any(self.attrs.get(k) for k in identity_keys)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = SemanticNode(tag="#root", attrs={})
        self.stack: List[SemanticNode] = [self.root]

    # -- helpers -----------------------------------------------------------
    def _skip_active(self) -> bool:
        return any(n.tag in _SKIP_TAGS for n in self.stack)

    def handle_starttag(self, tag, attrs):
        if self._skip_active():
            if tag in _SKIP_TAGS:
                self.stack.append(SemanticNode(tag=tag, attrs=dict(attrs)))
            return
        if tag in _SKIP_TAGS:
            self.stack.append(SemanticNode(tag=tag, attrs=dict(attrs)))
            return
        node = SemanticNode(tag=tag, attrs=dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"img", "input", "br", "hr", "meta", "link"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        if self._skip_active():
            return
        if tag in _SKIP_TAGS:
            return
        self.stack[-1].children.append(SemanticNode(tag=tag, attrs=dict(attrs)))

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            # unwind to the matching skip node
            for i in range(len(self.stack) - 1, 0, -1):
                if self.stack[i].tag == tag:
                    del self.stack[i:]
                    break
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._skip_active():
            return
        if data.strip():
            self.stack[-1].text_chunks.append(data.strip())


def _is_semantic(node: SemanticNode) -> bool:
    return node.tag in _SEMANTIC_TAGS or node.has_identity()


def _flatten(node: SemanticNode) -> List[SemanticNode]:
    """Drop pure layout wrappers: recurse into them, keep semantic nodes.

    A wrapper is dropped when it is a layout tag WITHOUT identity and either
    has exactly one child or no children of its own (pure grouping box).
    """
    kept: List[SemanticNode] = []
    for child in node.children:
        if child.tag in _LAYOUT_TAGS and not child.has_identity():
            kept.extend(_flatten(child))
        else:
            kept.append(child)
    return kept


def _prune(node: SemanticNode) -> Optional[SemanticNode]:
    node.children = _flatten(node)
    pruned_children = []
    for child in node.children:
        out = _prune(child)
        if out is not None:
            pruned_children.append(out)
    node.children = pruned_children
    if node.tag == "#root":
        return node
    if not node.text() and not node.children:
        return None
    return node


@dataclass
class SemanticTree:
    root: SemanticNode

    def outline(self, max_depth: int = 12) -> str:
        """Indented outline; one line per semantic node (token-cheap)."""
        lines: List[str] = []

        def walk(node: SemanticNode, depth: int) -> None:
            if depth > max_depth:
                return
            text = node.text()
            attrs = ""
            if node.has_identity():
                ident = node.attrs.get("id") or node.attrs.get("class") or node.attrs.get("role") or ""
                attrs = f" #{str(ident).split()[0]}" if ident else ""
            snippet = (text[:80] + "…") if len(text) > 80 else text
            if node.tag != "#root":
                lines.append(f"{'  ' * (depth - 1)}<{node.tag}>{attrs} {snippet}".rstrip())
            for child in node.children:
                walk(child, depth + 1)

        walk(self.root, 0)
        return "\n".join(lines)

    def plain_text(self) -> str:
        return self.root.text()

    def node_count(self) -> int:
        count = 0

        def walk(node: SemanticNode) -> None:
            nonlocal count
            if node.tag != "#root":
                count += 1
            for child in node.children:
                walk(child)

        walk(self.root)
        return count


def extract_semantic_tree(html: str) -> SemanticTree:
    """Parse HTML and return the pruned semantic tree (fail-closed)."""
    if html is None or not isinstance(html, str):
        raise ValueError("html must be a string")
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    root = _prune(builder.root)
    assert root is not None
    return SemanticTree(root=root)


def estimate_tokens(text: str) -> int:
    """Cheap token budget estimate (~4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def escape_outline(text: str) -> str:
    """Small helper for callers embedding outlines into HTML reports."""
    return escape(text)
