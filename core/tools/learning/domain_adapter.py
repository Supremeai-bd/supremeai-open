import json
import os
from typing import Any, ClassVar

from core.logging_config import logger
from database.supabase_client import db


class DomainAdapter:
    """
    Domain-specific prompt tuning: legal, medical, finance, code.
    Stores domain embeddings/configs → plugs into model_router.py.
    Closes Gap #28
    """

    DOMAINS: ClassVar[Any] = {
        "legal": {
            "system_prompt": (
                "You are a legal analyst assistant. Analyze documents for risk, compliance, and clarity. "
                "Always include a brief disclaimer: this is informational, not legal advice. "
                "Flag: liability clauses, jurisdiction issues, missing signatures, ambiguous terms."
            ),
            "temperature": 0.2,
            "max_tokens": 4000,
            "disclaimer": "Disclaimer: This output is for informational purposes only and does not constitute legal advice.",
        },
        "medical": {
            "system_prompt": (
                "You are a medical information assistant (NOT a doctor). "
                "Always begin with a strong disclaimer. Never diagnose or prescribe. "
                "Provide evidence-based general information with sources where possible."
            ),
            "temperature": 0.1,
            "max_tokens": 2000,
            "disclaimer": "Disclaimer: This is general medical information, not a diagnosis or medical advice. Consult a licensed physician.",
        },
        "finance": {
            "system_prompt": (
                "You are a financial analysis assistant. Provide data-driven market analysis, risk assessment, and "
                "portfolio theory guidance. Include standard risk disclosures."
            ),
            "temperature": 0.3,
            "max_tokens": 3000,
            "disclaimer": "Disclaimer: This is not financial advice. Investments carry risk. Consult a licensed financial advisor.",
        },
        "code": {
            "system_prompt": (
                "You are a senior code reviewer and architecture advisor. Focus on correctness, security, performance, "
                "and maintainability. Cite specific lines and explain impact."
            ),
            "temperature": 0.1,
            "max_tokens": 4000,
            "disclaimer": "",
        },
    }

    def __init__(self):
        self._profiles: dict[str, dict[str, Any]] = {}
        self._load_profiles()
        logger.info(f"Initialized DomainAdapter with {len(self._profiles)} domain profiles")

    def _local_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "data", "domain_profiles.json")

    def _load_profiles(self) -> None:
        if db.client:
            try:
                res = db.client.table("domain_profiles").select("*").execute()
                for row in res.data or []:
                    self._profiles[row["domain"]] = row  # type: ignore
            except Exception as exc:
                logger.debug(f"Domain profiles DB load failed: {exc}")
        try:
            with open(self._local_path(), encoding="utf-8") as f:
                data = json.load(f)
            self._profiles.update(data)
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            pass
        for domain, defaults in self.DOMAINS.items():
            self._profiles.setdefault(domain, defaults)

    def _save_profile(self, domain: str, profile: dict[str, Any]) -> None:
        self._profiles[domain] = profile
        if db.client:
            try:
                db.client.table("domain_profiles").upsert({"domain": domain, **profile}).execute()
            except Exception as exc:
                logger.debug(f"Domain profile save failed: {exc}")
        try:
            os.makedirs(os.path.dirname(self._local_path()), exist_ok=True)
            with open(self._local_path(), "w", encoding="utf-8") as f:
                json.dump(self._profiles, f, indent=2, default=str)
        except Exception as exc:
            logger.debug(f"Local domain profile save failed: {exc}")

    def get_prompt(
        self, domain: str, user_prompt: str, context: str | None = None
    ) -> dict[str, Any]:
        profile = self._profiles.get(domain) or self.DOMAINS.get("code", {})
        system_prompt = profile.get("system_prompt", "")
        full_prompt = user_prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuery:\n{user_prompt}"
        disclaimer = profile.get("disclaimer", "")
        if disclaimer:
            full_prompt = f"{disclaimer}\n\n{full_prompt}"
        return {
            "domain": domain,
            "system_prompt": system_prompt,
            "user_prompt": full_prompt,
            "temperature": profile.get("temperature", 0.2),
            "max_tokens": profile.get("max_tokens", 2000),
            "disclaimer": disclaimer,
        }

    def adapt_request(
        self, domain: str, user_prompt: str, context: str | None = None
    ) -> dict[str, Any]:
        prompt_pkg = self.get_prompt(domain, user_prompt, context=context)
        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            prompt = f"System: {prompt_pkg['system_prompt']}\n\nUser: {prompt_pkg['user_prompt']}\n\nRespond concisely with actionable detail."
            result = router.route_and_generate(
                prompt, task_type="coding" if domain == "code" else "reasoning"
            )
            text = result.get("text", "") if isinstance(result, dict) else str(result)
            return {
                "domain": domain,
                "response": text,
                "disclaimer": prompt_pkg.get("disclaimer", ""),
                "model": result.get("model", "unknown"),
                "provider": result.get("provider", "unknown"),
            }
        except Exception as exc:
            logger.error(f"DomainAdapter generation failed: {exc}")
            return {
                "domain": domain,
                "response": f"[Error] Domain adaptation failed: {exc}",
                "disclaimer": prompt_pkg.get("disclaimer", ""),
            }

    def register_domain(self, domain: str, profile: dict[str, Any]) -> dict[str, Any]:
        base = self.DOMAINS.get(domain, {})
        merged = {**base, **profile}
        self._save_profile(domain, merged)
        return {"status": "success", "domain": domain, "profile": merged}

    def list_domains(self) -> list[str]:
        return list(self.DOMAINS.keys()) + [d for d in self._profiles if d not in self.DOMAINS]
