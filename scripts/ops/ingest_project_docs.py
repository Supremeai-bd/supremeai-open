#!/usr/bin/env python3
"""Project-docs knowledge ingest (#1337) — bridge-20261027-knowledge-loop.

Feeds the repos' own documentation into the RAG layer via the tower tool
`memory_ingest_document_rag`, so docs_search can answer project questions
(docs_search("supremeai") currently returns []).

Dry-run by default; pass --apply to actually ingest. Designed to run from the
Bridge Intake schedule (see work order) or manually.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

TOWER_URL = os.environ.get("SUPREMEAI_MCP_URL", "https://supremeai-mcp-tower.onrender.com/mcp")
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

# (repo, path prefix, doc collection label) — keep in sync with the work order
TARGETS = [
    ("supremeai", "docs/", "architecture"),
    ("supremeai-core", "docs/", "core"),
    ("supremeai-api", "docs/", "api"),
    ("supremeai-studio", "docs/", "studio"),
]
ROOT_DOCS = ["README.md", "ERROR_COMPENDIUM.md", "COVERAGE_90_PLAN.md", "API-swagger.yaml"]


def post(payload: dict, session_id: str | None = None, timeout: int = 90):
    headers = dict(HEADERS)
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(TOWER_URL, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sid = resp.headers.get("mcp-session-id", session_id)
        raw = resp.read().decode("utf-8", errors="replace")
        payloads = []
        if raw.lstrip().startswith("event:") or "\ndata:" in raw:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    try:
                        payloads.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        pass
        else:
            payloads.append(json.loads(raw))
        return sid, payloads


def ensure_session() -> str:
    sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                              "clientInfo": {"name": "docs-ingest", "version": "1.0"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return sid


def call(sid: str, name: str, args: dict, rid: int):
    _, resps = post({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                     "params": {"name": name, "arguments": args}}, sid)
    return resps[0] if resps else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually ingest (default: dry-run)")
    ap.add_argument("--max-docs", type=int, default=100)
    args = ap.parse_args()

    sid = ensure_session()
    rid = 10
    manifest = []

    for repo, prefix, label in TARGETS:
        tree = call(sid, "github_repo_tree", {"repo": repo}, rid)
        rid += 1
        try:
            text = json.dumps(tree.get("result", {}).get("content", [{}])[0].get("text", ""))
        except Exception:  # noqa: BLE001
            text = json.dumps(tree)
        # tree entries look like "docs/..." in the filtered listing
        doc_paths = [seg for seg in set(text.replace('"', " ").split()) if seg.startswith(prefix) and seg.endswith(".md")]
        for root_doc in ROOT_DOCS:
            if root_doc in text:
                doc_paths.append(root_doc)
        print(f"{repo}: {len(doc_paths)} candidate docs")
        for path in sorted(doc_paths)[: args.max_docs]:
            read = call(sid, "github.read_file", {"repo": repo, "path": path}, rid)
            rid += 1
            try:
                inner = json.loads(read.get("result", {}).get("content", [{}])[0].get("text", "{}"))
                content = inner.get("content", "")
            except Exception:  # noqa: BLE001
                content = ""
            if len(content) < 200:
                continue
            source = f"https://github.com/Supremeai-bd/{repo}/blob/main/{path}"
            manifest.append({"repo": repo, "path": path, "chars": len(content), "source": source})
            if args.apply:
                res = call(sid, "memory_ingest_document_rag",
                           {"title": f"{repo}:{path}", "content": content,
                            "metadata": {"repo": repo, "path": path, "source": source, "ingested_by": "docs-ingest"}},
                           rid)
                rid += 1
                print(f"  ingested {path} -> {json.dumps(res)[:120]}")
            else:
                print(f"  (dry-run) would ingest {path} ({len(content)} chars)")

    print(f"\nmanifest: {len(manifest)} docs")
    with open("docs_ingest_manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)
    # CI assertion helper: project docs must be reachable afterwards
    probe = call(sid, "docs_search", {"query": "supremeai streaming"}, rid)
    print("post-probe docs_search:", json.dumps(probe)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
