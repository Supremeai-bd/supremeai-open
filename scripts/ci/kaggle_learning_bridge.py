#!/usr/bin/env python3
"""Kaggle Intelligent Learning Bridge — Empirical Machine Learning to System Brain.

Bridges Kaggle GPU/TPU compute pool into SupremeAI's long-term memory.
Focuses strictly on cognitive, causal intelligence:
  NOT just 'WHAT happened' (e.g. loss=0.23),
  BUT 'WHY it happened' (e.g. why learning rate 2e-5 stabilized attention vs 1e-4 collapse),
  'WHY alternative approaches failed', and 'Actionable heuristics for agents'.

Pushes distilled empirical knowledge to:
  1. Supabase knowledge_base (full experimental record & causal analysis)
  2. Supabase learned_facts (actionable heuristics & warnings for agents)
  3. Qdrant supremeai_memory (768-dim semantic search index)

Stdlib-only, fail-soft, cross-platform (Linux/Windows/macOS).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"


def parse_kaggle_auth(token: str) -> str:
    """Return HTTP Authorization header value from token."""
    token = token.strip()
    if token.startswith("KGAT_"):
        return f"Bearer {token}"
    return f"Basic {base64.b64encode(token.encode('utf-8')).decode('ascii')}"


def extract_kaggle_tokens() -> List[str]:
    """Extract Kaggle tokens from environment variables."""
    raw = os.getenv("KAGGLE_API_TOKENS") or ""
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        for i in range(1, 7):
            val = os.getenv(f"KAGGLE_API_TOKEN_{i}")
            if val and val.strip():
                tokens.append(val.strip())
    if not tokens:
        single = os.getenv("KAGGLE_API_TOKEN") or os.getenv("KAGGLE_KEY")
        user = os.getenv("KAGGLE_USERNAME")
        if single and user:
            tokens.append(f"{user}:{single}")
        elif single:
            tokens.append(single.strip())
    return tokens


class KaggleLearningEngine:
    def __init__(
        self,
        tokens: Optional[List[str]] = None,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        qdrant_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
    ):
        self.tokens = tokens if tokens is not None else extract_kaggle_tokens()
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL")
        self.qdrant_key = qdrant_key or os.getenv("QDRANT_API_KEY")
        self.gemini_key = gemini_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def _kaggle_request(self, endpoint: str, data: Optional[dict] = None, method: str = "GET") -> Tuple[int, Any]:
        """Execute Kaggle API call rotating through the key pool on rate limits."""
        if not self.tokens:
            return 401, {"error": "No Kaggle API tokens configured"}

        url = f"{KAGGLE_API_BASE}/{endpoint.lstrip('/')}"
        last_error = "Unknown error"

        for token in self.tokens:
            auth_header = parse_kaggle_auth(token)
            req_data = json.dumps(data).encode("utf-8") if data else None
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_body = resp.read().decode("utf-8")
                    try:
                        return resp.status, json.loads(resp_body)
                    except json.JSONDecodeError:
                        return resp.status, resp_body
            except urllib.error.HTTPError as err:
                status = err.code
                err_body = err.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {status}: {err_body[:200]}"
                if status in (429, 403) and len(self.tokens) > 1:
                    continue  # Try next token in pool
                return status, {"error": last_error}
            except Exception as err:
                last_error = str(err)
                continue

        return 500, {"error": last_error}

    def trigger_kernel(
        self,
        username: str,
        slug: str,
        title: str,
        code_or_notebook: str,
        is_notebook: bool = False,
        enable_gpu: bool = True,
    ) -> Tuple[bool, str]:
        """Push a kernel to Kaggle and start execution."""
        payload = {
            "id": f"{username}/{slug}",
            "title": title,
            "text": code_or_notebook,
            "language": "python",
            "kernel_type": "notebook" if is_notebook else "script",
            "is_private": True,
            "enable_gpu": enable_gpu,
            "enable_internet": True,
        }
        status, res = self._kaggle_request("kernels/push", data=payload, method="POST")
        if status in (200, 201):
            return True, f"Kernel {username}/{slug} started successfully"
        return False, f"Failed to push kernel ({status}): {res}"

    def check_kernel_status(self, username: str, slug: str) -> Dict[str, Any]:
        """Check status of a running Kaggle kernel."""
        status, res = self._kaggle_request(f"kernels/status?userName={username}&kernelSlug={slug}")
        if status == 200 and isinstance(res, dict):
            return res
        return {"status": "unknown", "error": res}

    def distill_why_knowledge(self, raw_result: dict) -> dict:
        """
        Extract deep causal intelligence from experimental results:
        NOT just WHAT (metrics), but WHY it succeeded or failed,
        and what alternatives were rejected with empirical reasons.
        """
        task_name = raw_result.get("experiment_name", "Empirical Evaluation")
        hypothesis = raw_result.get("hypothesis", "Evaluating architectural optimization")
        metrics = raw_result.get("metrics", {})
        why_worked = raw_result.get("why_it_worked", "Not specified")
        why_alternatives_failed = raw_result.get("why_alternatives_failed", [])
        anti_patterns = raw_result.get("anti_patterns_discovered", [])
        distilled_rules = raw_result.get("distilled_heuristics", [])

        return {
            "experiment": task_name,
            "hypothesis": hypothesis,
            "metrics_summary": metrics,
            "causal_mechanism": {
                "why_this_design_succeeded": why_worked,
                "why_alternatives_failed": why_alternatives_failed,
                "anti_patterns_to_avoid": anti_patterns,
            },
            "distilled_heuristics_for_agents": distilled_rules,
            "distilled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def ingest_into_learning_memory(self, distilled_knowledge: dict, dry_run: bool = False) -> bool:
        """Store distilled empirical knowledge into Supabase and Qdrant."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        exp_name = distilled_knowledge.get("experiment", "kaggle_experiment")
        key = f"kaggle-{uuid.uuid4().hex[:8]}"

        # 1. Supabase knowledge_base record
        kb_record = {
            "id": str(uuid.uuid4()),
            "knowledge_key": key,
            "title": f"[Kaggle Empirical Learning] {exp_name}",
            "domain": "ml_empirical",
            "namespace": "kaggle_distillation",
            "content": json.dumps(distilled_knowledge, indent=2),
            "source": "kaggle_compute_pool",
            "confidence": 1.0,
            "risk_level": "low",
            "status": "active",
            "metadata": {
                "experiment": exp_name,
                "distilled_at": now,
                "source_type": "empirical_training",
            },
            "updated_at": now,
        }

        # 2. Supabase learned_facts
        facts = []
        for rule in distilled_knowledge.get("distilled_heuristics_for_agents", []):
            facts.append({
                "id": str(uuid.uuid4()),
                "content": f"[Kaggle Empirical Rule]: {rule}",
                "tags": ["kaggle_learning", "empirical_heuristic", "system_rule"],
                "created_at": now,
            })

        for alt in distilled_knowledge.get("causal_mechanism", {}).get("why_alternatives_failed", []):
            alt_text = alt if isinstance(alt, str) else json.dumps(alt)
            facts.append({
                "id": str(uuid.uuid4()),
                "content": f"[Kaggle Alternative Rejection Reason]: {alt_text}",
                "tags": ["kaggle_learning", "rejected_alternative"],
                "created_at": now,
            })

        # 3. Semantic text for Qdrant
        causal = distilled_knowledge.get("causal_mechanism", {})
        semantic_summary = (
            f"Kaggle Empirical Experiment: {exp_name}\n"
            f"Hypothesis: {distilled_knowledge.get('hypothesis')}\n"
            f"Why It Succeeded: {causal.get('why_this_design_succeeded')}\n"
            f"Anti-patterns: {json.dumps(causal.get('anti_patterns_to_avoid'))}\n"
            f"Heuristics: {json.dumps(distilled_knowledge.get('distilled_heuristics_for_agents'))}"
        )

        if dry_run:
            print("\n--- DRY RUN: Kaggle knowledge_base record ---")
            print(json.dumps(kb_record, indent=2))
            print(f"\n--- DRY RUN: {len(facts)} Kaggle learned_facts ---")
            for f in facts:
                print(f"- {f['content']}")
            print("\n--- DRY RUN: Semantic Summary ---")
            print(semantic_summary[:300] + "...")
            return True

        # Live Ingestion
        if self.supabase_url and self.supabase_key:
            self._post_supabase("knowledge_base", kb_record)
            for f in facts:
                self._post_supabase("learned_facts", f)
            print(f"[OK] Ingested experiment '{exp_name}' into Supabase")
        else:
            print("::notice::Supabase credentials not configured; skipped Supabase write")

        if self.qdrant_url and self.gemini_key:
            embedding = self._get_gemini_embedding(semantic_summary, dim=768)
            if embedding:
                point = {
                    "id": str(uuid.uuid4()),
                    "vector": embedding,
                    "payload": {
                        "experiment": exp_name,
                        "source": "kaggle_pool",
                        "summary": semantic_summary[:1200],
                        "timestamp": now,
                    },
                }
                self._upsert_qdrant("supremeai_memory", point)
                print(f"[OK] Upserted experiment '{exp_name}' into Qdrant supremeai_memory")
            else:
                print("::warning::Could not generate vector embedding for Kaggle result")
        else:
            print("::notice::Qdrant or Gemini credentials not configured; skipped Qdrant write")

        return True

    def _post_supabase(self, table: str, record: dict) -> bool:
        url = f"{self.supabase_url.rstrip('/')}/rest/v1/{urllib.parse.quote(table)}"
        req = urllib.request.Request(
            url,
            data=json.dumps(record).encode("utf-8"),
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.status in (200, 201)
        except Exception as err:
            print(f"::warning::Supabase write failed on {table}: {err}", file=sys.stderr)
            return False

    def _get_gemini_embedding(self, text: str, dim: int = 768) -> Optional[List[float]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.gemini_key}"
        payload = {
            "content": {"parts": [{"text": text[:8000]}]},
            "outputDimensionality": dim,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("embedding", {}).get("values")
        except Exception as err:
            print(f"::warning::Gemini embedding failed: {err}", file=sys.stderr)
            return None

    def _upsert_qdrant(self, collection: str, point: dict) -> bool:
        url = f"{self.qdrant_url.rstrip('/')}/collections/{urllib.parse.quote(collection)}/points?wait=true"
        headers = {"Content-Type": "application/json"}
        if self.qdrant_key:
            headers["api-key"] = self.qdrant_key
        req = urllib.request.Request(
            url,
            data=json.dumps({"points": [point]}).encode("utf-8"),
            headers=headers,
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.status == 200
        except Exception as err:
            print(f"::warning::Qdrant upsert failed: {err}", file=sys.stderr)
            return False


def run_self_test() -> int:
    """Offline self-test for Kaggle learning bridge."""
    print("Running KaggleLearningEngine self-tests...")

    # Mock tokens
    engine = KaggleLearningEngine(tokens=["mock_user:mock_key1", "mock_user:mock_key2"])
    assert len(engine.tokens) == 2, "Token parsing failed"

    # Test auth header generation
    h1 = parse_kaggle_auth("user:key")
    assert h1.startswith("Basic "), "Basic auth header failed"
    h2 = parse_kaggle_auth("KGAT_abcdef123456")
    assert h2.startswith("Bearer "), "Bearer auth header failed"

    # Test cognitive distillation
    sample_raw = {
        "experiment_name": "Attention Head LoRA Convergence",
        "hypothesis": "Low rank (r=8) adaptation on Q/V projections converges faster than dense fine-tuning on consumer T4 GPU",
        "metrics": {"eval_loss": 0.42, "gpu_hours": 1.2, "throughput_tokens_sec": 840},
        "why_it_worked": "Focusing adaptation strictly on query/key projections preserves frozen base representations while preventing representation collapse in MLP layers.",
        "why_alternatives_failed": [
            "Dense fine-tuning suffered from catastrophic forgetting and OOM on 16GB VRAM",
            "Adapting all linear layers (r=32) doubled training latency with zero perplexity gain",
        ],
        "anti_patterns_discovered": [
            "Do NOT unfreeze embedding matrix on small datasets — causes immediate gradient explosion",
        ],
        "distilled_heuristics": [
            "For coding agent task specialization, rank r=8 on attention heads is 4x faster and retains 99.4% base reasoning integrity",
        ],
    }

    distilled = engine.distill_why_knowledge(sample_raw)
    assert distilled["experiment"] == "Attention Head LoRA Convergence"
    assert "why_this_design_succeeded" in distilled["causal_mechanism"]
    assert len(distilled["causal_mechanism"]["why_alternatives_failed"]) == 2
    assert len(distilled["distilled_heuristics_for_agents"]) == 1

    # Test dry run ingestion
    ok = engine.ingest_into_learning_memory(distilled, dry_run=True)
    assert ok, "Dry-run memory ingestion failed"

    print("PASS: KaggleLearningEngine self-tests completed successfully!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Kaggle Intelligent Learning Bridge")
    parser.add_argument("--self-test", action="store_true", help="Run offline contract tests")
    parser.add_argument("--dry-run", action="store_true", help="Perform distillation without database writes")
    parser.add_argument("--ingest-file", type=str, help="Path to JSON file containing experimental results to distill")
    parser.add_argument("--trigger", action="store_true", help="Trigger a kernel run on Kaggle")
    parser.add_argument("--username", type=str, help="Kaggle username")
    parser.add_argument("--slug", type=str, help="Kaggle kernel slug")
    parser.add_argument("--code-file", type=str, help="Script/notebook file to push")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    engine = KaggleLearningEngine()

    if args.ingest_file:
        with open(args.ingest_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        distilled = engine.distill_why_knowledge(data)
        ok = engine.ingest_into_learning_memory(distilled, dry_run=args.dry_run)
        return 0 if ok else 1

    if args.trigger:
        if not args.username or not args.slug or not args.code_file:
            print("Error: --username, --slug, and --code-file are required for --trigger", file=sys.stderr)
            return 1
        with open(args.code_file, "r", encoding="utf-8") as fh:
            code = fh.read()
        is_nb = args.code_file.endswith(".ipynb")
        ok, msg = engine.trigger_kernel(args.username, args.slug, args.slug, code, is_notebook=is_nb)
        print(msg)
        return 0 if ok else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
