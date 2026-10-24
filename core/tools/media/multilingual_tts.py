import hashlib
import os
import time
from typing import Any, ClassVar

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.config import settings
from core.logging_config import logger

router = APIRouter(prefix="/tts", tags=["multilingual-tts"])

# ── ElevenLabs: per-language voice IDs ────────────────────────────────────────
# eleven_multilingual_v2 supports 29 languages with ONE voice
# Using "Rachel" (neutral, clear) as default for all languages
ELEVENLABS_VOICES: dict[str, str] = {
    "en": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "bn": "21m00Tcm4TlvDq8ikWAM",  # Bengali — same voice (multilingual v2)
    "ar": "21m00Tcm4TlvDq8ikWAM",
    "zh": "21m00Tcm4TlvDq8ikWAM",
    "es": "21m00Tcm4TlvDq8ikWAM",
    "fr": "21m00Tcm4TlvDq8ikWAM",
    "de": "21m00Tcm4TlvDq8ikWAM",
    "hi": "21m00Tcm4TlvDq8ikWAM",
    "ja": "21m00Tcm4TlvDq8ikWAM",
    "ko": "21m00Tcm4TlvDq8ikWAM",
    "pt": "21m00Tcm4TlvDq8ikWAM",
    "ru": "21m00Tcm4TlvDq8ikWAM",
    "it": "21m00Tcm4TlvDq8ikWAM",
    "tr": "21m00Tcm4TlvDq8ikWAM",
    "pl": "21m00Tcm4TlvDq8ikWAM",
    "nl": "21m00Tcm4TlvDq8ikWAM",
    "sv": "21m00Tcm4TlvDq8ikWAM",
    "da": "21m00Tcm4TlvDq8ikWAM",
    "fi": "21m00Tcm4TlvDq8ikWAM",
    "el": "21m00Tcm4TlvDq8ikWAM",
    "he": "21m00Tcm4TlvDq8ikWAM",
    "cs": "21m00Tcm4TlvDq8ikWAM",
    "sk": "21m00Tcm4TlvDq8ikWAM",
    "ro": "21m00Tcm4TlvDq8ikWAM",
    "hu": "21m00Tcm4TlvDq8ikWAM",
    "uk": "21m00Tcm4TlvDq8ikWAM",
    "id": "21m00Tcm4TlvDq8ikWAM",
    "ms": "21m00Tcm4TlvDq8ikWAM",
    "th": "21m00Tcm4TlvDq8ikWAM",
    "vi": "21m00Tcm4TlvDq8ikWAM",
}

# Unicode block ranges for language auto-detection
LANG_SCRIPTS = [
    ("bn", (0x0980, 0x09FF)),  # Bengali — highest priority
    ("ar", (0x0600, 0x06FF)),
    ("he", (0x0590, 0x05FF)),
    ("hi", (0x0900, 0x097F)),
    ("zh", (0x4E00, 0x9FFF)),
    ("ja", (0x3040, 0x309F)),
    ("ko", (0xAC00, 0xD7AF)),
    ("th", (0x0E00, 0x0E7F)),
    ("ru", (0x0400, 0x04FF)),
    ("el", (0x0370, 0x03FF)),
]

SUPPORTED_LANGUAGES = list(ELEVENLABS_VOICES.keys())


class TTSRequest(BaseModel):
    text: str
    language: str | None = None  # auto-detect if None
    voice_id: str | None = None  # override ElevenLabs voice
    provider: str | None = "auto"  # auto | elevenlabs | gtts | edge-tts
    stability: float = 0.5
    similarity_boost: float = 0.75
    output_format: str | None = "mp3"  # mp3 | wav


class TTSResponse(BaseModel):
    status: str
    language: str
    provider: str
    audio_url: str
    text_length: int
    cached: bool = False
    error: str | None = None


class MultilingualTTS:
    def __init__(self, provider: str = "auto", api_key: str | None = None):
        self.provider = provider
        self.api_key = api_key or getattr(settings, "elevenlabs_api_key", "")
        self.model_id = "eleven_multilingual_v2"
        logger.info(
            f"Initialized MultilingualTTS provider={self.provider} elevenlabs={'yes' if self.api_key else 'no'}"
        )

    # ── Language detection ────────────────────────────────────────────────────
    def _detect_language(self, text: str) -> str:
        for char in text:
            cp = ord(char)
            for lang, (lo, hi) in LANG_SCRIPTS:
                if lo <= cp <= hi:
                    return lang
        return "en"

    # ── Caching ───────────────────────────────────────────────────────────────
    def _output_path(self, text: str, lang: str, fmt: str = "mp3") -> str:
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tts"
        )
        os.makedirs(base_dir, exist_ok=True)
        h = hashlib.sha256(f"{text}:{lang}:{self.provider}".encode()).hexdigest()[:16]
        return os.path.join(base_dir, f"tts_{lang}_{h}.{fmt}")

    def _cache_hit(self, text: str, lang: str) -> str | None:
        ttl = int(getattr(settings, "tts_cache_ttl", "86400"))
        path = self._output_path(text, lang)
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl:
            return path
        return None

    # ── Main entry ────────────────────────────────────────────────────────────
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        language: str | None = None,
        output_path: str | None = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> dict[str, Any]:
        lang = language or self._detect_language(text)
        if lang not in SUPPORTED_LANGUAGES:
            logger.warning(f"Language '{lang}' not supported, falling back to 'en'")
            lang = "en"

        cached = self._cache_hit(text, lang)
        if cached:
            logger.info(f"TTS cache hit: lang={lang}")
            return {
                "status": "success",
                "language": lang,
                "provider": "cache",
                "audio_path": cached,
                "audio_url": f"/api/tts/audio/{os.path.basename(cached)}",
                "text_length": len(text),
                "cached": True,
            }

        out_path = output_path or self._output_path(text, lang)

        # Try ElevenLabs first
        if self.api_key and self.provider in ("auto", "elevenlabs"):
            result = await self._elevenlabs(
                text, out_path, lang, voice_id, stability, similarity_boost
            )
            if result["status"] == "success":
                result["audio_url"] = f"/api/tts/audio/{os.path.basename(out_path)}"
                return result

        # Try edge-tts (Microsoft TTS, free, good Bangla support)
        result = await self._edge_tts(text, out_path, lang)
        if result["status"] == "success":
            result["audio_url"] = f"/api/tts/audio/{os.path.basename(out_path)}"
            return result

        # Try gTTS (Google, free)
        result = await self._gtts(text, out_path, lang)
        if result["status"] == "success":
            result["audio_url"] = f"/api/tts/audio/{os.path.basename(out_path)}"
            return result

        return {
            "status": "error",
            "language": lang,
            "error": "All TTS providers failed.",
        }

    # ── ElevenLabs ────────────────────────────────────────────────────────────
    async def _elevenlabs(
        self,
        text: str,
        out_path: str,
        lang: str,
        voice_id: str | None,
        stability: float,
        similarity_boost: float,
    ) -> dict[str, Any]:
        v = voice_id or ELEVENLABS_VOICES.get(lang, ELEVENLABS_VOICES["en"])
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{v}"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(res.content)
                logger.info(f"ElevenLabs ✅ lang={lang} path={out_path}")
                return {
                    "status": "success",
                    "language": lang,
                    "provider": "elevenlabs",
                    "audio_path": out_path,
                    "text_length": len(text),
                    "voice_id": v,
                    "model_id": self.model_id,
                }
            logger.warning(f"ElevenLabs {res.status_code}: {res.text[:200]}")
            return {
                "status": "error",
                "language": lang,
                "error": f"ElevenLabs HTTP {res.status_code}",
            }
        except Exception as exc:
            logger.warning(f"ElevenLabs exception: {exc}")
            return {"status": "error", "language": lang, "error": str(exc)}

    # ── edge-tts (Microsoft, supports Bengali!) ───────────────────────────────
    async def _edge_tts(self, text: str, out_path: str, lang: str) -> dict[str, Any]:
        # Voice map for edge-tts — Bengali has excellent support
        EDGE_VOICES: ClassVar[Any] = {
            "bn": "bn-BD-NabanitaNeural",  # Bangla Female (Bangladesh)
            "hi": "hi-IN-SwaraNeural",
            "ar": "ar-SA-ZariyahNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ja": "ja-JP-NanamiNeural",
            "ko": "ko-KR-SunHiNeural",
            "en": "en-US-JennyNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "es": "es-ES-ElviraNeural",
            "pt": "pt-BR-FranciscaNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "it": "it-IT-ElsaNeural",
            "tr": "tr-TR-EmelNeural",
            "vi": "vi-VN-HoaiMyNeural",
            "id": "id-ID-GadisNeural",
            "th": "th-TH-PremwadeeNeural",
            "pl": "pl-PL-ZofiaNeural",
            "nl": "nl-NL-ColetteNeural",
            "sv": "sv-SE-SofieNeural",
        }
        voice = EDGE_VOICES.get(lang, "en-US-JennyNeural")
        mp3_path = out_path.replace(".wav", ".mp3")
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)
            logger.info(f"edge-tts ✅ lang={lang} voice={voice}")
            return {
                "status": "success",
                "language": lang,
                "provider": "edge-tts",
                "audio_path": mp3_path,
                "text_length": len(text),
                "voice": voice,
            }
        except ImportError:
            logger.debug("edge-tts not installed. Run: pip install edge-tts")
            return {
                "status": "error",
                "language": lang,
                "error": "edge-tts not installed",
            }
        except Exception as exc:
            logger.debug(f"edge-tts failed: {exc}")
            return {"status": "error", "language": lang, "error": str(exc)}

    # ── gTTS (Google, free) ───────────────────────────────────────────────────
    async def _gtts(self, text: str, out_path: str, lang: str) -> dict[str, Any]:
        try:
            from gtts import gTTS

            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(out_path)
            logger.info(f"gTTS ✅ lang={lang}")
            return {
                "status": "success",
                "language": lang,
                "provider": "gtts",
                "audio_path": out_path,
                "text_length": len(text),
            }
        except Exception as exc:
            logger.debug(f"gTTS failed: {exc}")
            return {"status": "error", "language": lang, "error": str(exc)}

    def sync_synthesize_stream(self, text: str, chunk_size: int = 200):
        """Yield text chunks for streaming TTS."""
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]

    # --- Streaming synthesis methods (ElevenLabs and edge-tts) ---

    async def _elevenlabs_stream(
        self,
        text: str,
        lang: str,
        voice_id: str | None,
        stability: float,
        similarity_boost: float,
    ):
        """Stream audio bytes from ElevenLabs TTS API."""
        v = voice_id or ELEVENLABS_VOICES.get(lang, ELEVENLABS_VOICES["en"])
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{v}"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

    async def _edge_tts_stream(self, text: str, lang: str):
        """Stream audio bytes from edge-tts."""
        try:
            import edge_tts
        except ImportError:
            logger.debug("edge-tts not installed. Run: pip install edge-tts")
            return  # Yield nothing

        EDGE_VOICES: ClassVar[Any] = {
            "bn": "bn-BD-NabanitaNeural",
            "hi": "hi-IN-SwaraNeural",
            "ar": "ar-SA-ZariyahNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ja": "ja-JP-NanamiNeural",
            "ko": "ko-KR-SunHiNeural",
            "en": "en-US-JennyNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "es": "es-ES-ElviraNeural",
            "pt": "pt-BR-FranciscaNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "it": "it-IT-ElsaNeural",
            "tr": "tr-TR-EmelNeural",
            "vi": "vi-VN-HoaiMyNeural",
            "id": "id-ID-GadisNeural",
            "th": "th-TH-PremwadeeNeural",
            "pl": "pl-PL-ZofiaNeural",
            "nl": "nl-NL-ColetteNeural",
            "sv": "sv-SE-SofieNeural",
        }
        voice = EDGE_VOICES.get(lang, "en-US-JennyNeural")
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                yield chunk["data"]

    async def synthesize_stream(
        self,
        text: str,
        language: str | None = None,
        voice_id: str | None = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ):
        """
        Stream audio bytes for the given text.
        Tries ElevenLabs first, then falls back to edge-tts.
        Yields audio bytes chunks.
        """
        lang = language or self._detect_language(text)
        if lang not in SUPPORTED_LANGUAGES:
            lang = "en"

        # Try ElevenLabs first if API key is available
        if self.api_key and self.provider in ("auto", "elevenlabs"):
            try:
                async for chunk in self._elevenlabs_stream(
                    text, lang, voice_id, stability, similarity_boost
                ):
                    yield chunk
                return  # Success, exit
            except Exception as e:
                logger.warning(f"ElevenLabs streaming failed: {e}. Falling back to edge-tts.")

        # Fallback to edge-tts
        async for chunk in self._edge_tts_stream(text, lang):
            yield chunk

    async def get_voices(self) -> dict[str, Any]:
        """List available ElevenLabs voices."""
        if not self.api_key:
            return {"status": "error", "error": "ElevenLabs API key not configured"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": self.api_key},
                )
            if res.status_code == 200:
                return {"status": "success", "voices": res.json().get("voices", [])}
            return {"status": "error", "error": f"HTTP {res.status_code}"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


# ── Singleton ─────────────────────────────────────────────────────────────────
_tts_tool_instance = None


def get_tts_tool() -> MultilingualTTS:
    global _tts_tool_instance
    if _tts_tool_instance is None:
        _tts_tool_instance = MultilingualTTS()
    return _tts_tool_instance


# ── REST Endpoints ────────────────────────────────────────────────────────────


@router.post("/synthesize", response_model=TTSResponse)
async def synthesize_text(request: TTSRequest):
    """Convert text to speech. Supports 29 languages. Auto-detects language."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(request.text) > 5000:
        raise HTTPException(status_code=400, detail="Text too long (max 5000 chars)")

    tool = get_tts_tool()
    result = await tool.synthesize(
        text=request.text,
        voice_id=request.voice_id,
        language=request.language,
        stability=request.stability,
        similarity_boost=request.similarity_boost,
    )
    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "TTS failed"))
    return TTSResponse(**{k: v for k, v in result.items() if k in TTSResponse.__fields__})


@router.post("/generate", response_model=dict[str, Any])
async def api_generate_tts(req: TTSRequest):
    try:
        tool = get_tts_tool()
        result = await tool.generate(
            text=req.text,
            language=req.language,
            voice_id=req.voice_id,
            provider=req.provider,
            stability=req.stability,
            similarity_boost=req.similarity_boost,
            output_format=req.output_format,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result.get("status") == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "TTS failed"))
    return result


@router.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve generated audio file."""
    base_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tts"
    )
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path) or not os.path.abspath(path).startswith(os.path.abspath(base_dir)):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/languages")
async def list_languages():
    """List all supported languages."""
    return {
        "supported_languages": SUPPORTED_LANGUAGES,
        "total": len(SUPPORTED_LANGUAGES),
        "bangla_priority": True,
        "notes": {
            "bn": "Bengali — supports edge-tts (bn-BD-NabanitaNeural) + ElevenLabs multilingual v2",
            "hi": "Hindi — edge-tts + ElevenLabs",
        },
    }


@router.get("/voices")
async def list_voices():
    """List available ElevenLabs voices (requires API key)."""
    tool = get_tts_tool()
    return await tool.get_voices()


@router.delete("/cache")
async def clear_cache():
    """Clear TTS audio cache."""
    base_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tts"
    )
    removed = 0
    if os.path.exists(base_dir):
        for f in os.listdir(base_dir):
            if f.startswith("tts_") and f.endswith((".mp3", ".wav")):
                try:
                    os.unlink(os.path.join(base_dir, f))
                    removed += 1
                except Exception as e:
                    try:
                        import loguru

                        loguru.logger.error(f"Tool execution error: {e}")
                    except Exception as e:
                        logger.warning(f"Exception suppressed: {e}")
                    pass
    return {"status": "success", "removed_files": removed}
