"""Ghost Tower - web-AI relay engine (Playwright-based).

Provides a persistent-browser relay for Gemini/ChatGPT/Claude/DeepSeek web UIs,
a credential vault, multi-account SSO runner, and a FastAPI bridge server.

Transit surface for the supremeai-browser satellite (browser/ghost_tower/*).
"""
__all__ = [
    "GeminiWebEngine",
    "CredentialVault",
]
