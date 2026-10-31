import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "core"))

from core.adaptive_engine.intent_parser import IntentParser, MetaCognitiveAssessment


class _Router:
    pass


def test_destructive_routes_to_human_admin():
    p = IntentParser(model_router=_Router())
    r = p.parse_meta_cognition("Drop database and delete production backups")
    assert r.delegation_target == "human_admin"
    assert r.is_destructive_or_sensitive is True


def test_training_routes_to_kaggle():
    p = IntentParser(model_router=_Router())
    r = p.parse_meta_cognition("Fine-tune Llama with LoRA")
    assert r.delegation_target == "kaggle_gpu"


def test_local_task_routes_to_self():
    p = IntentParser(model_router=_Router())
    r = p.parse_meta_cognition("Add type hint to parse_tokens")
    assert r.delegation_target == "self"
    assert r.can_solve_locally is True
