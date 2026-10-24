from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_platform_admin
from core.logging_config import logger
from tools.code.code_smell_detector import CodeSmellDetector
from tools.devops.on_premise_deployer import OnPremiseDeployer
from tools.learning.domain_adapter import DomainAdapter
from tools.learning.skill_recommender import SkillRecommender
from tools.security_tools.vulnerability_predictor import VulnerabilityPredictor


def _require_admin(payload: dict = Depends(get_current_platform_admin)) -> dict:
    """Gate DevOps/deploy tooling behind an authenticated admin role.

    বাংলা মন্তব্য: এই রাউটারে ফাইল-সিস্টেম রিড (smell/vuln scan) এবং ডিপ্লয়মেন্ট
    ফাইল-রাইট (docker-compose/helm) অপারেশন আছে, যা আগে কোনো auth ছাড়াই User-facing
    API-তে এক্সপোজড ছিল (route-leakage: এই মডিউলটি `_admin_paths`-এ ছিল না)।
    এখন প্রতিটি এন্ডপয়েন্টে admin-role JWT বাধ্যতামূলক করা হলো।
    """
    if payload.get("role") != "admin":
        logger.warning(
            f"🚫 Unauthorized tools-ops access attempt by {payload.get('sub', 'unknown')}"
        )
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


router = APIRouter(prefix="/tools", tags=["tools-ops"], dependencies=[Depends(_require_admin)])


class SmellCheckRequest(BaseModel):
    path: str
    thresholds: dict[str, int] | None = None


class SmellCheckResponse(BaseModel):
    path: str
    smells: list[dict[str, Any]]
    summary: dict[str, int]


class VulnCheckRequest(BaseModel):
    file_path: str | None = None
    diff: str | None = None


class VulnCheckResponse(BaseModel):
    file: str
    vulnerability_score: float
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    findings: list[dict[str, Any]]
    recommendation: str


class SkillRecRequest(BaseModel):
    user_id: str
    task_description: str
    top_k: int = 5


class SkillRecResponse(BaseModel):
    user_id: str
    task: str
    recommendations: list[dict[str, Any]]
    count: int


class DomainAdaptRequest(BaseModel):
    domain: str
    prompt: str
    context: str | None = None


class DomainAdaptResponse(BaseModel):
    domain: str
    response: str
    disclaimer: str
    model: str
    provider: str


class DeployComposeRequest(BaseModel):
    overrides: dict[str, Any] | None = None


class DeployHelmRequest(BaseModel):
    release_name: str = "supremeai"
    namespace: str = "default"
    replicas: int = 3
    image_tag: str = "latest"


class DeployResponse(BaseModel):
    output_path: str
    format: str


@router.post("/smell-check", response_model=SmellCheckResponse)
async def smell_check(payload: SmellCheckRequest):
    if not os.path.exists(payload.path):
        raise HTTPException(status_code=404, detail="Path not found")

    detector = CodeSmellDetector()
    if os.path.isdir(payload.path):
        result = detector.analyze_directory(payload.path, thresholds=payload.thresholds)
        all_smells = [smell for smells in result.values() for smell in smells]
    else:
        all_smells = detector.analyze_python_file(payload.path, thresholds=payload.thresholds)
        if payload.path.endswith((".js", ".ts", ".jsx", ".tsx")):
            all_smells.extend(
                detector.analyze_js_ts_file(payload.path, thresholds=payload.thresholds)
            )

    by_severity: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
    for s in all_smells:
        sev = s.get("severity", "info")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return SmellCheckResponse(path=payload.path, smells=all_smells, summary=by_severity)


@router.post("/vulnerability-check", response_model=VulnCheckResponse)
async def vulnerability_check(payload: VulnCheckRequest):
    predictor = VulnerabilityPredictor()
    if payload.diff:
        result = predictor.predict_diff(payload.diff)
    elif payload.file_path:
        if not os.path.exists(payload.file_path):
            raise HTTPException(status_code=404, detail="file not found")
        result = predictor.predict(payload.file_path)
    else:
        raise HTTPException(status_code=400, detail="Provide file_path or diff")
    return VulnCheckResponse(**result)


@router.post("/skills/recommend", response_model=SkillRecResponse)
async def recommend_skills(payload: SkillRecRequest):
    recommender = SkillRecommender()
    result = recommender.record_and_recommend(
        payload.user_id, payload.task_description, top_k=payload.top_k
    )
    return SkillRecResponse(**result)


@router.post("/domain/adapt", response_model=DomainAdaptResponse)
async def domain_adapt(payload: DomainAdaptRequest):
    adapter = DomainAdapter()
    result = adapter.adapt_request(payload.domain, payload.prompt, context=payload.context)
    return DomainAdaptResponse(
        domain=payload.domain,
        response=result.get("response", ""),
        disclaimer=result.get("disclaimer", ""),
        model=result.get("model", "unknown"),
        provider=result.get("provider", "unknown"),
    )


@router.post("/deploy/compose", response_model=DeployResponse)
async def deploy_compose(payload: DeployComposeRequest):
    deployer = OnPremiseDeployer()
    path = deployer.write_compose(overrides=payload.overrides)
    return DeployResponse(output_path=path, format="docker-compose")


@router.post("/deploy/helm", response_model=DeployResponse)
async def deploy_helm(payload: DeployHelmRequest):
    deployer = OnPremiseDeployer()
    path = deployer.write_helm()
    return DeployResponse(output_path=path, format="helm-chart")
