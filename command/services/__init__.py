"""src/services/__init__.py — service-layer package for supremeai-command.

Voice domain services (zero-compute, network-leased capabilities):
    voice_service - Edge Neural TTS adapter (Bangla-first, optional edge-tts)
"""

from .voice_service import (  # noqa: F401
    DEFAULT_VOICE,
    VOICE_CATALOG,
    VoiceRequest,
    VoiceRequestError,
    VoiceService,
    VoiceServiceUnavailable,
    VoiceSynthesisError,
    VoiceResult,
    speak_bangla,
)

__all__ = [
    "DEFAULT_VOICE",
    "VOICE_CATALOG",
    "VoiceRequest",
    "VoiceRequestError",
    "VoiceService",
    "VoiceServiceUnavailable",
    "VoiceSynthesisError",
    "VoiceResult",
    "speak_bangla",
]
