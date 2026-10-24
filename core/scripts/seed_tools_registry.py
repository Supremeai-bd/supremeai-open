"""
Seed the tools_registry table in Supabase with metadata for all 76 backend tools.
Run: python backend/scripts/seed_tools_registry.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.logging_config import logger
from database.supabase_client import db

TOOLS = [
    # (id, name, file_path, category, description, cost_per_call)
    (
        "browser_agent",
        "Browser Agent",
        "tools/browser_agent.py",
        "automation",
        "Playwright-based web browser automation",
        0.005,
    ),
    (
        "vision_agent",
        "Vision Agent",
        "tools/vision_agent.py",
        "multimodal",
        "Image and PDF analysis using vision models",
        0.01,
    ),
    (
        "voice_coder",
        "Voice Coder",
        "tools/voice_coder.py",
        "voice",
        "Whisper STT + code generation from voice commands",
        0.008,
    ),
    (
        "image_to_code",
        "Image to Code",
        "tools/image_to_code.py",
        "multimodal",
        "Convert UI screenshots to React/Tailwind code",
        0.015,
    ),
    (
        "self_planner",
        "Self Planner",
        "tools/self_planner.py",
        "agentic",
        "LLM-generated DAG task planning and execution",
        0.02,
    ),
    (
        "collaborative_editor",
        "Collaborative Editor",
        "tools/collaborative_editor.py",
        "collaboration",
        "Real-time WebSocket multi-user code editor",
        0.0,
    ),
    (
        "offline_mode",
        "Offline Mode",
        "tools/offline_mode.py",
        "resilience",
        "Ollama local fallback with cloud sync queue",
        0.0,
    ),
    (
        "ai_pair_programmer",
        "AI Pair Programmer",
        "tools/ai_pair_programmer.py",
        "collaboration",
        "Issue → plan → code → PR automation",
        0.05,
    ),
    (
        "pr_reviewer",
        "PR Reviewer",
        "tools/pr_reviewer.py",
        "code_quality",
        "GitHub PR diff analysis, security scan, comment posting",
        0.01,
    ),
    (
        "pre_commit_ai",
        "Pre-Commit AI Gate",
        "tools/pre_commit_ai.py",
        "code_quality",
        "Git hook AI gate — blocks commits on critical issues",
        0.005,
    ),
    (
        "code_smell_detector",
        "Code Smell Detector",
        "tools/code_smell_detector.py",
        "code_quality",
        "Cyclomatic complexity, duplication, coupling analysis",
        0.003,
    ),
    (
        "model_trainer",
        "Model Trainer",
        "tools/model_trainer.py",
        "ml_training",
        "RunPod/Modal LoRA fine-tuning pipeline",
        0.5,
    ),
    (
        "rlhf_pipeline",
        "RLHF Pipeline",
        "tools/rlhf_pipeline.py",
        "ml_training",
        "HuggingFace TRL DPO/PPO reward model training",
        1.0,
    ),
    (
        "cloud_sandbox_orchestrator",
        "Cloud Sandbox",
        "tools/cloud_sandbox_orchestrator.py",
        "infrastructure",
        "RunPod persistent VM for agentic code execution",
        0.1,
    ),
    (
        "auto_pr_pipeline",
        "Auto PR Pipeline",
        "tools/auto_pr_pipeline.py",
        "automation",
        "Full Git flow: branch → commit → push → PR",
        0.01,
    ),
    (
        "viral_referral_engine",
        "Viral Referral Engine",
        "tools/viral_referral_engine.py",
        "growth",
        "Referral codes + reward tiers + Stripe payouts",
        0.001,
    ),
    (
        "sso_integrator",
        "SSO Integrator",
        "tools/sso_integrator.py",
        "enterprise",
        "SAML 2.0 / OIDC for Okta, Azure AD, Google Workspace",
        0.0,
    ),
    (
        "tenant_rate_limiter",
        "Tenant Rate Limiter",
        "tools/tenant_rate_limiter.py",
        "enterprise",
        "Per-organization rate limits with billing tier integration",
        0.0,
    ),
    (
        "style_learner",
        "Style Learner",
        "tools/style_learner.py",
        "personalization",
        "AST pattern extraction for personal coding style learning",
        0.005,
    ),
    (
        "diagram_to_architecture",
        "Diagram to Architecture",
        "tools/diagram_to_architecture.py",
        "multimodal",
        "Excalidraw/whiteboard → Terraform + FastAPI code",
        0.015,
    ),
    (
        "bangla_nlp",
        "Bengali NLP",
        "tools/bangla_nlp.py",
        "language",
        "Bengali language processing and translation",
        0.003,
    ),
    (
        "bangla_voice",
        "Bengali Voice",
        "tools/bangla_voice.py",
        "voice",
        "Bengali speech recognition and synthesis",
        0.005,
    ),
    (
        "telegram_bot",
        "Telegram Bot",
        "tools/telegram_bot.py",
        "integration",
        "Telegram bot for SupremeAI commands",
        0.0,
    ),
    (
        "github_agent",
        "GitHub Agent",
        "tools/github_agent.py",
        "integration",
        "GitHub repo analysis, PR creation, issue management",
        0.01,
    ),
    (
        "cost_auditor",
        "Cost Auditor",
        "tools/cost_auditor.py",
        "monitoring",
        "Real-time API cost tracking and optimization",
        0.0,
    ),
    (
        "knowledge_base_indexer",
        "Knowledge Base Indexer",
        "tools/knowledge_base_indexer.py",
        "knowledge",
        "Document indexing for RAG retrieval",
        0.005,
    ),
    (
        "auto_test_generator",
        "Auto Test Generator",
        "tools/auto_test_generator.py",
        "code_quality",
        "Generates pytest unit tests from source code",
        0.01,
    ),
    (
        "git_knowledge_extractor",
        "Git Knowledge Extractor",
        "tools/git_knowledge_extractor.py",
        "knowledge",
        "Extracts patterns and conventions from Git history",
        0.003,
    ),
    (
        "video_generator",
        "Video Generator",
        "tools/video_generator.py",
        "media",
        "AI video content generation",
        0.05,
    ),
    (
        "image_generator",
        "Image Generator",
        "tools/image_generator.py",
        "media",
        "AI image generation",
        0.02,
    ),
    (
        "multilingual_tts",
        "Multilingual TTS",
        "tools/multilingual_tts.py",
        "voice",
        "29-language text-to-speech using ElevenLabs/Coqui",
        0.01,
    ),
    (
        "docker_sandbox",
        "Docker Sandbox",
        "tools/docker_sandbox.py",
        "security",
        "Isolated Docker container for untrusted code execution",
        0.02,
    ),
    (
        "cot_reasoner",
        "Chain-of-Thought Reasoner",
        "tools/cot_reasoner.py",
        "reasoning",
        "Multi-step reasoning with self-critique loop",
        0.03,
    ),
    (
        "coverage_auditor",
        "Coverage Auditor",
        "tools/coverage_auditor.py",
        "code_quality",
        "Test coverage analysis and gap detection",
        0.002,
    ),
    (
        "multi_account_rotator",
        "Multi-Account Rotator",
        "tools/multi_account_rotator.py",
        "cost_optimization",
        "API key rotation across providers for zero-cost ops",
        0.0,
    ),
    (
        "vpn_switcher",
        "VPN Switcher",
        "tools/vpn_switcher.py",
        "security",
        "Provider rotation and geo-routing",
        0.0,
    ),
    (
        "pdf_to_sdk",
        "PDF to SDK",
        "tools/pdf_to_sdk.py",
        "multimodal",
        "API documentation PDF → client SDK generation",
        0.02,
    ),
    (
        "health_checker",
        "Health Checker",
        "tools/health_checker.py",
        "monitoring",
        "Service health checking and alerting",
        0.0,
    ),
    (
        "checkpoint_manager",
        "Checkpoint Manager",
        "tools/checkpoint_manager.py",
        "agentic",
        "Task checkpoint save/resume for long-running agents",
        0.0,
    ),
]


def seed_tools():
    if not db.client:
        logger.error("Supabase not connected. Set SUPABASE_URL and SUPABASE_KEY.")
        return False

    logger.info(f"Seeding {len(TOOLS)} tools to tools_registry...")
    records = []
    for tool_id, name, file_path, category, description, cost_per_call in TOOLS:
        records.append(
            {
                "id": tool_id,
                "name": name,
                "file_path": file_path,
                "category": category,
                "description": description,
                "cost_per_call": cost_per_call,
                "status": "active",
                "dependencies": [],
            }
        )

    try:
        db.service_client.table("tools_registry").upsert(records).execute()
        logger.success(f"✅ Seeded {len(records)} tools successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to seed tools: {e}")
        return False


if __name__ == "__main__":
    success = seed_tools()
    sys.exit(0 if success else 1)
