import datetime
import json

import httpx

from adaptive_engine.registry import PlatformProfile, PlatformRegistry
from brain.model_router import ModelRouter
from core.logging_config import logger


class PlatformLearner:
    def __init__(self, model_router: ModelRouter, registry: PlatformRegistry):
        self.model_router = model_router
        self.registry = registry

    async def learn_from_docs(self, platform_name: str, docs_url: str) -> PlatformProfile:
        logger.info(f"Learning platform '{platform_name}' from documentation: {docs_url}")

        # 1. Fetch documentation content (with a fallback)
        html_content = ""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(docs_url, follow_redirects=True)
                if res.status_code == 200:
                    html_content = res.text[
                        :15000
                    ]  # Take first 15k characters to fit context limits
                else:
                    html_content = f"Failed to fetch content, status code: {res.status_code}"
        except Exception as e:
            logger.warning(
                f"Failed to fetch live documentation: {e}. Falling back to LLM general knowledge."
            )
            html_content = f"Unreachable URL: {docs_url}. Please use general knowledge to guess the API structure."

        # 2. Extract API spec and platform capabilities using LLM
        prompt = f"""You are a Platform Learning Engine for an Adaptive AI System.
Given the platform name "{platform_name}", the documentation URL "{docs_url}", and \
a sample of the fetched documentation text below, parse the capabilities, \
authentication methods, deployment methods, and generate a Python SDK client stub.

Documentation Snippet:
{html_content}

Return ONLY a JSON response in the following format (no markdown blocks, no text around it):
{{
  "display_name": "Human-readable name of the platform",
  "category": "git, hosting, cloud, or database",
  "auth_methods": ["list", "of", "auth", "methods", "e.g.", "oauth2, pat, api_key, service_account"],
  "capabilities": ["list of capabilities, e.g. hosting, functions, db, repository"],
  "deploy_methods": ["list of deployment methods, e.g. git_push, api_upload, cli_deploy"],
  "sdk_code": "Python code block representing the generated SDK client class",
  "api_endpoints": {{"endpoint_name": "path_or_description"}}
}}
"""
        response = await self.model_router.async_route_and_generate(
            prompt, task_type="general", max_cost=0.015
        )
        text = response.get("text", "{}").strip()

        # Clean markdown code block wraps
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse learned platform JSON: {e}")
            # Fallback structure
            data = {
                "display_name": platform_name.capitalize(),
                "category": "hosting",
                "auth_methods": ["api_key"],
                "capabilities": ["web_hosting"],
                "deploy_methods": ["git_push"],
                "sdk_code": f"class {platform_name.capitalize()}Client:\n    pass",
                "api_endpoints": {},
            }

        profile = PlatformProfile(
            name=platform_name.lower(),
            display_name=data.get("display_name", platform_name.capitalize()),
            category=data.get("category", "hosting"),
            auth_methods=data.get("auth_methods", ["api_key"]),
            capabilities=data.get("capabilities", ["web_hosting"]),
            deploy_methods=data.get("deploy_methods", ["git_push"]),
            sdk_code=data.get("sdk_code", ""),
            api_endpoints=data.get("api_endpoints", {}),
            docs_url=docs_url,
            status="beta",
            learned_at=datetime.datetime.now(datetime.UTC),
            last_updated=datetime.datetime.now(datetime.UTC),
            success_rate=1.0,
        )

        self.registry.register_platform(profile)

        # 3. Save knowledge to Firestore via AgentKnowledgeStore
        try:
            from tools.learning.agent_knowledge_store import AgentKnowledgeStore

            store = AgentKnowledgeStore()
            store.save_agent_knowledge(
                agent_name=platform_name,
                best_skill=", ".join(data.get("capabilities", [])),
                workflow_knowledge=json.dumps(data.get("api_endpoints", {})),
                best_practices=data.get("deploy_methods", []),
                code_snippet_example=data.get("sdk_code", ""),
            )
        except Exception as store_err:
            logger.warning(f"Failed to persist platform knowledge: {store_err}")

        return profile
