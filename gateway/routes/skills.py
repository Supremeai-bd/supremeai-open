# backend/api/routes/skills.py
import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_token
from core.logging_config import logger

router = APIRouter(
    prefix="/skills",
    tags=["Skill Catalog Infrastructure"],
    dependencies=[Depends(get_current_user_token)],
)

# বাংলা মন্তব্য: __file__ থেকে absolute path নির্ণয় — relative path CI-তে FileNotFoundError দেয়
# পুরনো: Path("backend/skills/manifests").resolve() — CWD-dependent, CI-তে ভাঙে
# নতুন: Path(__file__).resolve().parent থেকে নিরাপদ relative calculation
MANIFEST_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "manifests"

# ERR-H02 FIX (2026-09-16): installs used to be a no-op success — the endpoint
# claimed "installed" while persisting nothing (false assurance), and there
# was no uninstall route at all. Install state is now real and stored in a
# JSON state file next to the catalog. Atomic writes + a process lock keep
# concurrent admin calls consistent.
INSTALLED_STATE_PATH = Path(__file__).resolve().parent.parent.parent / "skills" / "installed.json"
_STATE_LOCK = threading.Lock()
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,80}$")


def _read_installed_state() -> dict[str, Any]:
    if not INSTALLED_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(INSTALLED_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"[skills] installed-state unreadable, treating as empty: {exc}")
        return {}


def _write_installed_state(state: dict[str, Any]) -> None:
    INSTALLED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = INSTALLED_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(INSTALLED_STATE_PATH)  # atomic on POSIX


def _manifest_payload(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@router.get("/catalog", response_model=list[dict[str, Any]])
async def get_active_skill_catalog():
    """
    ফাইল সিস্টেমের manifests/ ফোল্ডার স্ক্যান করে ড্যাশবোর্ডের জন্য
    সমস্ত ভেরিফাইড স্কিল ম্যানিফেস্ট ডাইনামিকালি রেন্ডার করে।
    """
    if not MANIFEST_DIR.exists():
        logger.error(f"Manifest directory not found at: {MANIFEST_DIR}")
        raise HTTPException(status_code=500, detail="Skill catalog repository is unavailable.")

    catalog = []

    # ডিরেক্টরির সমস্ত .json ম্যানিফেস্ট ফাইল রিড করা হচ্ছে
    for json_file in MANIFEST_DIR.glob("*.json"):
        try:
            # ডিফেন্সিভ চেক: পাথটি সত্যিই আমাদের ডিরেক্টরির ভেতরে কিনা
            if not json_file.resolve().is_relative_to(MANIFEST_DIR):
                logger.warning(f"Path traversal attempt blocked during catalog scan: {json_file}")
                continue

            manifest_data = json.loads(json_file.read_text(encoding="utf-8"))
            catalog.append(manifest_data)

        except json.JSONDecodeError as jde:
            logger.error(f"Malformed JSON schema detected in manifest {json_file.name}: {jde!s}")
            continue
        except Exception as e:
            logger.error(f"Failed to read manifest file {json_file.name}: {e!s}")
            continue

    logger.info(f"Successfully broadcasted {len(catalog)} active skills to the frontend dashboard.")
    return catalog


# বাংলা মন্তব্ত: AUDIT-018 ফিক্স — Studio Client-এর useAdminApi.ts এবং
# EnhancedSkillMarketplace.tsx-এর /api/skills/install এবং /api/skills/search
# কলগুলো এখন ব্যাকএন্ডে আছে (আগে 404 পেত)।
# CI FIX: frontend also calls GET /api/skills/search — added GET alias.
@router.get("/search", response_model=list[dict[str, Any]], tags=["Skill Catalog Infrastructure"])
@router.post("/search", response_model=list[dict[str, Any]], tags=["Skill Catalog Infrastructure"])
async def search_skills(query: str = "", installed_only: bool = False):
    """Search skill manifests by keyword query.

    ERR-H02 FIX: ``installed_only`` used to be accepted and silently ignored;
    it now really filters against the persisted install state.
    """
    if not MANIFEST_DIR.exists():
        raise HTTPException(status_code=500, detail="Skill catalog repository is unavailable.")
    installed_state = _read_installed_state() if installed_only else {}
    results = []
    for json_file in MANIFEST_DIR.glob("*.json"):
        try:
            manifest_data = json.loads(json_file.read_text(encoding="utf-8"))
            if query.lower() in json.dumps(manifest_data).lower():
                if installed_only and manifest_data.get("skill_id") not in installed_state:
                    continue
                results.append(manifest_data)
                if len(results) > 100:
                    break
        except Exception as e:
            logger.warning(f"[skills-search] Skipping malformed manifest '{json_file.name}': {e!s}")
            continue
    return results


@router.post("/install", tags=["Skill Catalog Infrastructure"])
async def install_skill(skill: str = ""):
    """Install a skill by its ID into the user workspace.

    ERR-H02 FIX: this used to return ``status: installed`` while persisting
    nothing — a fabricated success. The install is now recorded in the real
    install-state file (id + version + timestamp) so ``installed_only``
    searches and uninstall have a truthful source of truth.
    """
    if not skill:
        raise HTTPException(status_code=400, detail="Skill ID is required")
    manifest_path = MANIFEST_DIR / f"{skill}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill}' not found in catalog")
    try:
        manifest = _manifest_payload(manifest_path)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail=f"Skill manifest '{skill}' is malformed: {exc}"
        ) from exc
    version = str(manifest.get("version") or manifest.get("budget", {}).get("version") or "1")
    installed_at = datetime.now(UTC).isoformat()
    with _STATE_LOCK:
        state = _read_installed_state()
        state[skill] = {"version": version, "installed_at": installed_at}
        _write_installed_state(state)
    return {
        "status": "installed",
        "skill": skill,
        "version": version,
        "installed_at": installed_at,
        "message": f"Skill '{skill}' installed successfully",
    }


@router.delete("/uninstall", tags=["Skill Catalog Infrastructure"])
async def uninstall_skill(skill: str = ""):
    """Remove a previously installed skill (ERR-H02 FIX: route did not exist)."""
    if not skill:
        raise HTTPException(status_code=400, detail="Skill ID is required")
    manifest_path = MANIFEST_DIR / f"{skill}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill}' not found in catalog")
    with _STATE_LOCK:
        state = _read_installed_state()
        if skill not in state:
            raise HTTPException(status_code=404, detail=f"Skill '{skill}' is not installed")
        removed = state.pop(skill)
        _write_installed_state(state)
    return {
        "status": "uninstalled",
        "skill": skill,
        "removed_install": removed,
        "message": f"Skill '{skill}' uninstalled successfully",
    }


class BlueprintDeployRequest(BaseModel):
    """Payload sent by EvolutionForge 'deploy to marketplace'."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    agents: list[str] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    category: str = Field(default="automation", max_length=60)


@router.post("/deploy-blueprint", status_code=201, tags=["Skill Catalog Infrastructure"])
async def deploy_blueprint(payload: BlueprintDeployRequest):
    """Deploy an Evolution Forge blueprint as a real skill manifest.

    ERR-H02 FIX: the frontend called this route but it did not exist (404).
    A blueprint is now written into the real manifest catalog directory, so
    it immediately shows up in ``GET /api/skills/catalog`` like every other
    skill — not a fabricated deployment.
    """
    if not MANIFEST_DIR.exists():
        raise HTTPException(status_code=500, detail="Skill catalog repository is unavailable.")
    slug = payload.name.strip().lower().replace(" ", "_")
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail="Blueprint name must slugify to [a-z0-9_.-] (max 81 chars)",
        )
    manifest_path = MANIFEST_DIR / f"{slug}.json"
    if manifest_path.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{slug}' already exists in the catalog")
    manifest = {
        "skill_id": slug,
        "owner": "Evolution_Forge",
        "description": payload.description,
        "category": payload.category,
        "agents": payload.agents,
        "workflow": {"nodes": payload.nodes, "edges": payload.edges},
        "allowed_roles": ["Admin", "Manager", "Standard_User"],
        "human_approval_points": {"on_ingestion": False, "on_execution": True},
        "created_at": datetime.now(UTC).isoformat(),
        "source": "evolution_forge",
    }
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to write blueprint manifest: {exc}"
        ) from exc
    logger.info(f"[skills] deployed Evolution Forge blueprint '{slug}' to the catalog")
    return {"status": "deployed", "skill_id": slug, "manifest": manifest}
