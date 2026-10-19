"""src/utils/__init__.py — utility package for supremeai-command.

Cross-cutting helpers with zero business authority:
    audio_cache - ephemeral SHA-256 keyed audio cache (memory or temp-file)
"""

from .audio_cache import AudioCache, AudioCacheError

__all__ = ["AudioCache", "AudioCacheError"]
