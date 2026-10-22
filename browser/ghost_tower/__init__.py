"""Ghost Tower - web-AI relay engine (Playwright-based).

Provides a persistent-browser relay for Gemini/ChatGPT/Claude/DeepSeek web UIs,
a credential vault, multi-account SSO runner, and a FastAPI bridge server.

Transit surface for the supremeai-browser satellite (browser/ghost_tower/*).
"""

from .credential_vault import CredentialVault
from .gemini_web_engine import GeminiWebEngine

__all__ = [
    "CredentialVault",
    "GeminiWebEngine",
]
