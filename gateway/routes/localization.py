"""API routes for Layer 4: Localization & UX (BhashaBot & VoiceDidi)."""

# বাংলা মন্তব্য: ভাষা-বট ও ভয়েস-দিদি এপিআই এন্ডপয়েন্টসমূহ।

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.localization.bhasha_bot import BhashaBot
from core.localization.voice_didi import VoiceDidi

router = APIRouter(prefix="/localization", tags=["localization"])


class TranslationRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str
    context: str = ""
    use_cache: bool = True
    force_llm: bool = False


class VoiceCommandRequest(BaseModel):
    audio_base64: str | None = None
    audio_duration_ms: int | None = None
    transcript_hint: str = ""
    user_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] | None = None


# Dependency helpers
def get_bhasha_bot() -> BhashaBot:
    return BhashaBot()


def get_voice_didi() -> VoiceDidi:
    return VoiceDidi()


class AITranslateRequest(BaseModel):
    key: str
    target_lang: str = "bn"
    source_lang: str = "en"
    context: str = ""


@router.post("/ai-translate")
async def ai_translate(
    payload: AITranslateRequest,
    bot: BhashaBot = Depends(get_bhasha_bot),
):
    """ADVANCED: Dynamic runtime AI translation with semantic caching for mobile and web clients."""
    # Try bot / semantic cache translation
    try:
        res = await bot.translate(
            text=payload.key,
            source_lang=payload.source_lang,
            target_lang=payload.target_lang,
            context=payload.context,
            use_cache=True,
            force_llm=False,
        )
        translated_text = res.get("translated_text") or res.get("translation") or payload.key
        return {
            "translation": translated_text,
            "source": res.get("source", "bhasha_bot"),
            "cached": res.get("cached", False),
        }
    except Exception as e:
        return {"translation": payload.key, "error": str(e), "fallback": True}


@router.post("/translate")
async def translate_text(
    payload: TranslationRequest,
    bot: BhashaBot = Depends(get_bhasha_bot),
):
    """Translate text between English, Bengali, and Banglish."""
    # বাংলা মন্তব্য: ভাষা-বটের সাহায্যে অনুবাদের এন্ডপয়েন্ট
    result = await bot.translate(
        text=payload.text,
        source_lang=payload.source_lang,
        target_lang=payload.target_lang,
        context=payload.context,
        use_cache=payload.use_cache,
        force_llm=payload.force_llm,
    )
    return result


@router.post("/voice-command")
async def process_voice_command(
    payload: VoiceCommandRequest,
    didi: VoiceDidi = Depends(get_voice_didi),
):
    """Process voice command and trigger business logic/intents."""
    # বাংলা মন্তব্য: ভয়েস-দিদির মাধ্যমে বাংলা ভয়েস কম্যান্ড প্রসেসিং এন্ডপয়েন্ট
    result = await didi.process_voice_command(
        audio_base64=payload.audio_base64,
        audio_duration_ms=payload.audio_duration_ms,
        transcript_hint=payload.transcript_hint,
        user_id=payload.user_id,
        session_id=payload.session_id,
        metadata=payload.metadata,
    )
    return result
