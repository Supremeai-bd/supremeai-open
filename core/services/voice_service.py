# SupremeAI 2.0 - Multimodal Voice Service Engine
# বাংলা মন্তব্য: এটি স্পিচ-টু-টেক্সট (Whisper STT) এবং টেক্সট-টু-স্পিচ (Bengali TTS) ভয়েস ইন্টারেকশন প্রসেস করে।

from __future__ import annotations

import os
import time
from typing import Any

from core.logging_config import logger

# Issue #445 doctrine (real work or loud failure, never fabricated success):
# the old implementation returned a FIXED Bengali transcript with confidence
# 0.96 for ANY audio and synthesized fake RIFF WAV bytes for ANY text. This
# service now performs REAL provider calls when configured — Groq Whisper
# (whisper-large-v3) for STT and edge-tts (free, no key) or ElevenLabs for
# TTS — and otherwise returns an explicit, honest "unavailable" status.
_stt_unavailable_announced = False
_tts_unavailable_announced = False

# Extension -> (mime, Groq-accepted format token)
_AUDIO_MIMES: dict[str, str] = {
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
}

# edge-tts neural voices (Bengali Bangladesh first, per the service's bn default)
_EDGE_TTS_VOICES: dict[str, str] = {
    "bn": "bn-BD-NabanitaNeural",
    "bn-BD": "bn-BD-NabanitaNeural",
    "bn-IN": "bn-IN-TanishaaNeural",
    "en": "en-US-AriaNeural",
    "hi": "hi-IN-SwaraNeural",
}


def _get_settings():
    from core.config import settings

    return settings


def _sniff_audio_mime(filename: str) -> str:
    lower = (filename or "").lower()
    for ext, mime in _AUDIO_MIMES.items():
        if lower.endswith(ext):
            return mime
    return "audio/wav"


class VoiceService:
    """
    Multimodal Voice Interaction Service Engine.
    Handles Speech-to-Text (STT) transcription and Text-to-Speech (TTS) audio synthesis.
    """

    def __init__(self, tts_provider: str = "auto"):
        self.tts_provider = tts_provider

    async def speech_to_text(
        self, audio_bytes: bytes, filename: str = "input.wav"
    ) -> dict[str, Any]:
        """
        Transcribe raw audio bytes via the dynamic STT provider cascade.

        বাংলা: ডায়নামিক ক্যাসকেড (Groq -> OpenAI -> HuggingFace) — যেকোনো একটি কী
        থাকলে সেটি দিয়ে আসল কল; প্রোভাইডার এরর দিলে পরবর্তীতে অটো-সুইচ; কোনো কী না
        থাকলে সৎ "unavailable"; কোনো বানানো ট্রান্সক্রিপ্ট নয় (issue #445, #466)।
        """
        global _stt_unavailable_announced
        try:
            if not audio_bytes:
                return {
                    "status": "error",
                    "transcript": "",
                    "error": "EMPTY_AUDIO",
                    "message": "No audio bytes were provided for transcription.",
                }

            # Dynamic STT provider discovery ($0..N) — vendor-agnostic cascade
            # (Groq -> OpenAI -> HuggingFace). Provider errors auto-switch to the
            # next configured provider (Issue #466 fallback chain).
            provider_chain: list[tuple[str, str]] = []
            groq_key = os.getenv("GROQ_API_KEY") or getattr(_get_settings(), "groq_api_key", "")
            if groq_key:
                provider_chain.append(("groq", groq_key))
            openai_key = os.getenv("OPENAI_API_KEY") or getattr(
                _get_settings(), "openai_api_key", ""
            )
            if openai_key:
                provider_chain.append(("openai", openai_key))
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if gemini_key:
                provider_chain.append(("gemini", gemini_key))
            hf_key = (
                os.getenv("HUGGINGFACE_API_KEY")
                or os.getenv("HF_API_KEY")
                or getattr(_get_settings(), "hf_api_key", "")
            )
            if hf_key:
                provider_chain.append(("huggingface", hf_key))

            # N = 0: Zero keys configured — Honest, graceful degradation (Issue #445, #466)
            if not provider_chain:
                if not _stt_unavailable_announced:
                    _stt_unavailable_announced = True
                    logger.warning(
                        "Speech-to-text UNAVAILABLE: No STT provider key configured "
                        "(Groq, OpenAI, Gemini, HF) — returning honest 'unavailable' "
                        "status instead of a placeholder transcript."
                    )
                return {
                    "status": "unavailable",
                    "reason": "STT_NOT_CONFIGURED",
                    "transcript": "",
                    "message": (
                        "No speech-to-text provider is configured on this deployment "
                        "(awaiting GROQ_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or "
                        "HF_API_KEY), so the audio was NOT transcribed."
                    ),
                }

            # Fallback chain: attempt each configured provider in priority order;
            # only a provider-level error (bad key, 5xx, quota) advances the chain.
            _stt_handlers = {
                "groq": self._transcribe_with_groq,
                "openai": self._transcribe_with_openai,
                "gemini": self._transcribe_with_gemini,
                "huggingface": self._transcribe_with_huggingface,
            }
            last_error: dict[str, Any] | None = None
            for provider_name, provider_key in provider_chain:
                result = await _stt_handlers[provider_name](audio_bytes, filename, provider_key)
                if result.get("status") == "success":
                    return result
                last_error = result
                logger.warning(
                    "STT provider '%s' failed (error=%s) — auto-switching to the next configured provider.",
                    provider_name,
                    result.get("error", "unknown"),
                )
            return last_error or {
                "status": "error",
                "transcript": "",
                "error": "STT_PROVIDER_ERROR",
                "message": "All configured STT providers failed.",
            }
        except Exception as e:
            logger.error(f"STT Transcription failed: {e}")
            return {"status": "error", "transcript": "", "error": str(e)}

    # Alias for caller ergonomics
    transcribe = speech_to_text

    async def _transcribe_with_groq(
        self, audio_bytes: bytes, filename: str, api_key: str
    ) -> dict[str, Any]:
        """Real Groq Whisper API call (same provider/contract as websocket_voice)."""
        import httpx

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        mime = _sniff_audio_mime(filename)

        files = {"file": (filename or "input.wav", audio_bytes, mime)}
        data = {"model": "whisper-large-v3", "response_format": "json"}

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, files=files, data=data)
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code != 200:
            logger.error("Groq STT failed: HTTP %s: %s", response.status_code, response.text[:200])
            return {
                "status": "error",
                "transcript": "",
                "error": "STT_PROVIDER_ERROR",
                "provider_status": response.status_code,
                "message": response.text[:300],
            }

        transcript = (response.json() or {}).get("text", "")
        if not transcript:
            return {
                "status": "error",
                "transcript": "",
                "error": "EMPTY_TRANSCRIPT",
                "message": "STT provider returned an empty transcript.",
            }

        logger.info(
            "STT transcription completed via Groq (%d bytes audio, %dms)",
            len(audio_bytes),
            latency_ms,
        )
        return {
            "status": "success",
            "transcript": transcript,
            "language": None,
            "model": "whisper-large-v3",
            "latency_ms": latency_ms,
        }

    async def _transcribe_with_openai(
        self, audio_bytes: bytes, filename: str, api_key: str
    ) -> dict[str, Any]:
        """Real OpenAI Whisper API call (dynamic fallback)."""
        import httpx

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        mime = _sniff_audio_mime(filename)

        files = {"file": (filename or "input.wav", audio_bytes, mime)}
        data = {"model": "whisper-1", "response_format": "json"}

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, files=files, data=data)
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code != 200:
            logger.error(
                "OpenAI STT failed: HTTP %s: %s", response.status_code, response.text[:200]
            )
            return {
                "status": "error",
                "transcript": "",
                "error": "STT_PROVIDER_ERROR",
                "provider_status": response.status_code,
                "message": response.text[:300],
            }

        transcript = (response.json() or {}).get("text", "")
        if not transcript:
            return {
                "status": "error",
                "transcript": "",
                "error": "EMPTY_TRANSCRIPT",
                "message": "STT provider returned an empty transcript.",
            }

        logger.info(
            "STT transcription completed via OpenAI (%d bytes audio, %dms)",
            len(audio_bytes),
            latency_ms,
        )
        return {
            "status": "success",
            "transcript": transcript,
            "language": None,
            "model": "whisper-1",
            "latency_ms": latency_ms,
        }

    async def _transcribe_with_gemini(
        self, audio_bytes: bytes, filename: str, api_key: str
    ) -> dict[str, Any]:
        """Real Gemini audio transcription call (Issue #466 cascade position 3)."""
        import base64

        import httpx

        model_name = "gemini-2.5-flash"
        mime = _sniff_audio_mime(filename)
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": audio_b64,
                            }
                        },
                        {
                            "text": (
                                "Transcribe this audio exactly. Reply with the "
                                "transcript text only, nothing else."
                            )
                        },
                    ]
                }
            ]
        }

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code != 200:
            logger.error(
                "Gemini STT failed: HTTP %s: %s", response.status_code, response.text[:200]
            )
            return {
                "status": "error",
                "transcript": "",
                "error": "STT_PROVIDER_ERROR",
                "provider_status": response.status_code,
                "message": response.text[:300],
            }

        data = response.json() or {}
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        transcript = (parts[0].get("text", "") if parts else "").strip()
        if not transcript:
            return {
                "status": "error",
                "transcript": "",
                "error": "EMPTY_TRANSCRIPT",
                "message": "STT provider returned an empty transcript.",
            }

        logger.info(
            "STT transcription completed via Gemini (%d bytes audio, %dms)",
            len(audio_bytes),
            latency_ms,
        )
        return {
            "status": "success",
            "transcript": transcript,
            "language": None,
            "model": model_name,
            "latency_ms": latency_ms,
        }

    async def _transcribe_with_huggingface(
        self, audio_bytes: bytes, filename: str, api_key: str
    ) -> dict[str, Any]:
        """Real Hugging Face Whisper inference API call (dynamic fallback)."""
        import httpx

        url = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
        headers = {"Authorization": f"Bearer {api_key}"}

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, content=audio_bytes)
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code != 200:
            logger.error(
                "HuggingFace STT failed: HTTP %s: %s", response.status_code, response.text[:200]
            )
            return {
                "status": "error",
                "transcript": "",
                "error": "STT_PROVIDER_ERROR",
                "provider_status": response.status_code,
                "message": response.text[:300],
            }

        transcript = (response.json() or {}).get("text", "")
        if not transcript:
            return {
                "status": "error",
                "transcript": "",
                "error": "EMPTY_TRANSCRIPT",
                "message": "STT provider returned an empty transcript.",
            }

        logger.info(
            "STT transcription completed via HuggingFace (%d bytes audio, %dms)",
            len(audio_bytes),
            latency_ms,
        )
        return {
            "status": "success",
            "transcript": transcript,
            "language": None,
            "model": "hf/whisper-large-v3",
            "latency_ms": latency_ms,
        }

    async def text_to_speech(self, text: str, lang: str = "bn") -> dict[str, Any]:
        """
        Synthesize text into audio bytes (TTS response).

        বাংলা: edge-tts ইনস্টল থাকলে আসল নিউরাল TTS (ফ্রি, কী-লেস); ElevenLabs
        কী থাকলে সেটাও ব্যবহারযোগ্য। কোনোটাই না থাকলে সৎ "unavailable" — কখনো
        ফাঁকা RIFF বাইট নয় (issue #445)।
        """
        global _tts_unavailable_announced
        try:
            if not text or not text.strip():
                return {
                    "status": "error",
                    "error": "EMPTY_TEXT",
                    "message": "No text was provided for synthesis.",
                }

            eleven_key = os.getenv("ELEVENLABS_API_KEY") or getattr(
                _get_settings(), "elevenlabs_api_key", ""
            )
            if eleven_key and self.tts_provider in ("auto", "elevenlabs"):
                result = await self._tts_with_elevenlabs(text, lang, eleven_key)
                if result.get("status") == "success":
                    return result
                logger.warning(
                    "ElevenLabs TTS failed (%s) — falling back to edge-tts if available",
                    result.get("error"),
                )

            result = await self._tts_with_edge(text, lang)
            if result.get("status") == "success":
                return result

            if not _tts_unavailable_announced:
                _tts_unavailable_announced = True
                logger.warning(
                    "Text-to-speech UNAVAILABLE: no TTS provider reachable (edge-tts "
                    "not installed and ELEVENLABS_API_KEY missing) — returning honest "
                    "'unavailable' status instead of placeholder audio bytes (issue #445)."
                )
            return {
                "status": "unavailable",
                "reason": "TTS_NOT_CONFIGURED",
                "message": (
                    "No text-to-speech provider is available on this deployment "
                    "(edge-tts not installed and ELEVENLABS_API_KEY missing), so NO "
                    "audio was synthesized."
                ),
                "detail": result.get("error"),
            }
        except Exception as e:
            logger.error(f"TTS Synthesis failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _tts_with_edge(self, text: str, lang: str) -> dict[str, Any]:
        """Real neural TTS via edge-tts (free Microsoft Edge voices, no API key)."""
        try:
            import edge_tts  # type: ignore[import-untyped]
        except ImportError:
            return {"status": "unavailable", "error": "edge_tts not installed"}

        voice = _EDGE_TTS_VOICES.get(lang) or _EDGE_TTS_VOICES.get(str(lang).split("-")[0])
        if not voice:
            voice = "en-US-AriaNeural"

        communicate = edge_tts.Communicate(text, voice)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk.get("data", b""))
        audio = b"".join(chunks)
        if not audio:
            return {"status": "error", "error": "edge-tts returned no audio"}

        logger.info("TTS synthesis completed via edge-tts (%s, %d bytes)", voice, len(audio))
        return {
            "status": "success",
            "audio_bytes": audio,
            "audio_bytes_length": len(audio),
            "mime_type": "audio/mpeg",
            "voice": voice,
        }

    async def _tts_with_elevenlabs(self, text: str, lang: str, api_key: str) -> dict[str, Any]:
        """Real TTS via ElevenLabs (requires ELEVENLABS_API_KEY)."""
        import httpx

        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": "eleven_multilingual_v2"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return {
                "status": "error",
                "error": f"ELEVENLABS_HTTP_{response.status_code}",
                "message": response.text[:200],
            }
        audio = response.content
        logger.info("TTS synthesis completed via ElevenLabs (%d bytes)", len(audio))
        return {
            "status": "success",
            "audio_bytes": audio,
            "audio_bytes_length": len(audio),
            "mime_type": "audio/mpeg",
            "voice": voice_id,
        }


# ── Module-level singleton factory (Issue #466) ──────────────────────────────
# বাংলা: websocket_voice.py-সহ সব কলার get_voice_service() দিয়ে একটিই shared
# VoiceService instance পাবে — per-call নতুন instance তৈরির অপচয় এড়াতে।
_voice_service_singleton: VoiceService | None = None


def get_voice_service() -> VoiceService:
    """Return the shared VoiceService instance (vendor-agnostic STT/TTS facade)."""
    global _voice_service_singleton
    if _voice_service_singleton is None:
        _voice_service_singleton = VoiceService()
    return _voice_service_singleton
