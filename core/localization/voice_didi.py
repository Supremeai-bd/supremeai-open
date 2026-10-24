"""VoiceDidi - Bengali voice command processor for low-literate users.

VoiceDidi processes Bengali voice commands, converts speech to text,
detects intent, and executes actions. Designed for accessibility with
minimal literacy requirements.
"""

# বাংলা মন্তব্য: ভয়েস-দিদি — স্বল্প-শিক্ষিত ব্যবহারকারীদের জন্য সহজে ভয়েস কম্যান্ড প্রসেসিং ও ইন্টেন্ট সনাক্তকরণ মডিউল।

from __future__ import annotations

import os
import uuid
from typing import Any

from core.logging_config import logger

try:
    from core.config import settings
except ImportError:
    settings = None  # type: ignore[misc,assignment]

try:
    from brain.model_router import ModelRouter
except ImportError:
    ModelRouter = None  # type: ignore[misc,assignment]

try:
    from core.localization.bhasha_bot import BhashaBot
except ImportError:
    BhashaBot = None  # type: ignore[misc,assignment]


# --- Config and Constants ---
VOICE_CONFIDENCE_THRESHOLD = settings.voice_didi_confidence
MAX_AUDIO_DURATION_SEC = settings.voice_didi_max_duration
SUPPORTED_INTENTS = settings.voice_didi_intents.split(",")


class VoiceDidi:
    """Bengali voice command AI for accessible e-commerce interaction."""

    def __init__(
        self,
        model_router: Any | None = None,
        bhasha_bot: Any | None = None,
    ) -> None:
        if model_router is None:
            if ModelRouter is None:
                raise RuntimeError("ModelRouter import failed")
            model_router = ModelRouter()
        self.model_router = model_router

        if bhasha_bot is None:
            if BhashaBot is None:
                raise RuntimeError("BhashaBot import failed")
            bhasha_bot = BhashaBot()
        self.bhasha_bot = bhasha_bot

        self.confidence_threshold = VOICE_CONFIDENCE_THRESHOLD
        self.max_duration = MAX_AUDIO_DURATION_SEC
        self.supported_intents = [i.strip() for i in SUPPORTED_INTENTS]

    def _validate_audio(self, audio_duration_ms: int | None) -> dict[str, Any]:
        """Validate audio input parameters."""
        # বাংলা মন্তব্য: অডিও ফাইলের দৈর্ঘ্য ও বৈধতা যাচাই করা
        if audio_duration_ms is None:
            return {"valid": False, "error": "audio_duration_ms_required"}

        duration_sec = audio_duration_ms / 1000
        if duration_sec > self.max_duration:
            return {
                "valid": False,
                "error": "audio_too_long",
                "max_allowed_sec": self.max_duration,
                "received_sec": duration_sec,
            }

        if duration_sec < 0.5:
            return {
                "valid": False,
                "error": "audio_too_short",
                "min_allowed_sec": 0.5,
                "received_sec": duration_sec,
            }

        return {"valid": True, "duration_sec": duration_sec}

    def _build_stt_prompt(self, audio_transcript_hint: str) -> str:
        """Build prompt for Bengali speech-to-text correction/enhancement."""
        # বাংলা মন্তব্য: এএসআর টেক্সট কারেকশন ও ইন্টেন্ট এক্সট্রাকশনের জন্য এলএলএম প্রম্পট
        return f"""You are VoiceDidi, a Bengali speech understanding specialist.

The user has spoken in Bengali. A rough transcription hint is provided:
\"{audio_transcript_hint}\"

Your tasks:
1. Correct the transcription to proper Bengali (বাংলা)
2. Identify the user's intent from: {", ".join(self.supported_intents)}
3. Extract any key entities (product names, locations, quantities, prices)

Respond in this EXACT JSON format:
{{
    \"corrected_text_bn\": \"সঠিক বাংলা ট্রান্সক্রিপশন\",
    \"intent\": \"identified_intent\",
    \"confidence\": 0.95,
    \"entities\": [
        {{\"type\": \"product\", \"value\": \"...\",
        \"type\": \"quantity\", \"value\": \"...\"}}
    ],
    \"suggested_action\": \"describe what action to take\"
}}

Respond ONLY with the JSON. No other text.
"""

    def _build_intent_prompt(self, text_bn: str) -> str:
        """Build intent classification prompt for Bengali text."""
        # বাংলা মন্তব্য: বাংলা কম্যান্ডের টাইপ ক্লাসিফিকেশনের প্রম্পট
        return f"""Classify the following Bengali text into one of these intents:
{", ".join(self.supported_intents)}

Text: \"{text_bn}\"

Also determine if this is a request for:
- product_search
- place_order
- ask_price
- ask_location
- cancel_order
- general_help
- repeat_request

Respond ONLY with the intent name (single word from the list above).
"""

    async def process_voice_command(
        self,
        audio_base64: str | None = None,
        audio_duration_ms: int | None = None,
        transcript_hint: str = "",
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a Bengali voice command end-to-end.

        Args:
            audio_base64: Base64-encoded audio (optional if transcript_hint provided)
            audio_duration_ms: Audio duration in milliseconds
            transcript_hint: Preliminary transcription from ASR service
            user_id: User identifier
            session_id: Session identifier
            metadata: Additional context (device, noise level, etc.)

        Returns:
            Full processing result with intent, action, and confidence
        """
        # বাংলা মন্তব্য: ভয়েস কম্যান্ডের সম্পূর্ণ এন্ট্রো-এন্ড প্রসেসিং (ভ্যালিডেশন -> এলএলএম জেনারেশন -> ইন্টেন্ট ক্লাসিফিকেশন)
        session_id = session_id or str(uuid.uuid4())

        # Validate audio
        validation = self._validate_audio(audio_duration_ms)
        if not validation["valid"]:
            return {
                "success": False,
                "session_id": session_id,
                "error": validation["error"],
                "action_taken": None,
            }

        # If no transcript hint, we need ASR (degraded mode - return guidance)
        if not transcript_hint:
            return {
                "success": False,
                "session_id": session_id,
                "error": "transcript_required",
                "message": "Please provide audio transcript. Full ASR integration pending.",
                "action_taken": None,
            }

        # Step 1: Enhance/correct transcription with LLM
        try:
            import asyncio

            stt_prompt = self._build_stt_prompt(transcript_hint)
            stt_response = await asyncio.to_thread(
                self.model_router.route_and_generate,
                stt_prompt,
                task_type="voice_processing",
            )

            # Parse LLM response
            import json

            try:
                parsed = json.loads(stt_response.get("text", "{}"))
            except json.JSONDecodeError:
                # Fallback: treat raw text as corrected transcription
                parsed = {
                    "corrected_text_bn": stt_response.get("text", transcript_hint),
                    "intent": "unknown",
                    "confidence": 0.3,
                    "entities": [],
                    "suggested_action": "request_clarification",
                }

            corrected_text = parsed.get("corrected_text_bn", transcript_hint)
            confidence = float(parsed.get("confidence", 0.0))
            intent = parsed.get("intent", "unknown")
            entities = parsed.get("entities", [])
            parsed.get("suggested_action", "")

            # Step 2: Low confidence → request clarification
            if confidence < self.confidence_threshold:
                return {
                    "success": True,
                    "session_id": session_id,
                    "clarification_needed": True,
                    "recognized_text_bn": corrected_text,
                    "confidence": confidence,
                    "message": "আমি ঠিক বুঝতে পারিনি। অনুগ্রহ করে আবার বলুন।",
                    "action_taken": "request_clarification",
                    "entities": entities,
                }

            # Step 3: Map intent to action
            action_result = await self._execute_intent_action(
                intent=intent,
                entities=entities,
                user_id=user_id,
                session_id=session_id,
            )

            return {
                "success": True,
                "session_id": session_id,
                "recognized_text_bn": corrected_text,
                "intent": intent,
                "confidence": confidence,
                "entities": entities,
                "action_taken": action_result.get("action"),
                "action_result": action_result,
                "message": self._generate_response_message(intent, action_result),
            }

        except Exception as e:
            logger.error(f"VoiceDidi processing failed: {e}")
            return {
                "success": False,
                "session_id": session_id,
                "error": "processing_failed",
                "details": str(e),
                "action_taken": "error_fallback",
            }

    async def _execute_intent_action(
        self,
        intent: str,
        entities: list[dict[str, Any]],
        user_id: str | None,
        session_id: str,
    ) -> dict[str, Any]:
        """Execute action based on detected intent."""
        # These would integrate with Commerce layer (Layer 3)
        # For now, return structured action plan
        action_map = {
            "search": {"action": "product_search", "needs": ["product"]},
            "order": {"action": "initiate_order", "needs": ["product", "quantity"]},
            "help": {"action": "show_help", "needs": []},
            "price": {"action": "show_price", "needs": ["product"]},
            "location": {"action": "show_location", "needs": ["location"]},
            "cancel": {"action": "cancel_order", "needs": ["order_id"]},
            "repeat": {"action": "repeat_last", "needs": []},
        }

        action_def = action_map.get(intent, {"action": "unknown", "needs": []})
        missing = [
            need for need in action_def["needs"] if not any(e.get("type") == need for e in entities)
        ]

        return {
            "action": action_def["action"],
            "intent": intent,
            "entities_provided": entities,
            "missing_required": missing,
            "can_proceed": len(missing) == 0,
            "session_id": session_id,
            "user_id": user_id,
        }

    def _generate_response_message(
        self,
        intent: str,
        action_result: dict[str, Any],
    ) -> str:
        """Generate Bengali response message for user."""
        # বাংলা মন্তব্য: ব্যবহারকারীকে ফেরত পাঠানোর জন্য বাংলা প্রতিক্রিয়া তৈরি করা
        if not action_result.get("can_proceed"):
            missing = action_result.get("missing_required", [])
            missing_str = ", ".join(missing)
            return f"আমি আপনাকে সাহায্য করতে চাই। অনুগ্রহ করে {missing_str} সম্পর্কে আরও তথ্য দিন।"

        messages = {
            "product_search": "আপনার জন্য পণ্য খুঁজে দেখছি...",
            "initiate_order": "আপনার অর্ডার প্রস্তুত করা হচ্ছে...",
            "show_help": "আমি কীভাবে সাহায্য করতে পারি? আপনি পণ্য খুঁজতে, অর্ডার করতে, বা দাম জানতে পারেন।",
            "show_price": "এই পণ্যের দাম দেখানো হচ্ছে...",
            "show_location": "আপনার নিকটস্থ দোকানের তথ্য দেখানো হচ্ছে...",
            "cancel_order": "আপনার অর্ডার বাতিল করা হচ্ছে...",
            "repeat_last": "আবার বলছি...",
        }

        return messages.get(
            action_result.get("action", ""),
            "আমি বুঝতে পেরেছি। আরও কিছু করতে চান?",
        )

    async def text_to_speech_guidance(
        self,
        text_bn: str,
        speed: str = "normal",
    ) -> dict[str, Any]:
        """Generate TTS guidance for voice responses (placeholder for TTS integration)."""
        # Production: Integrate with Google Cloud TTS, Amazon Polly, or Coqui TTS
        return {
            "text": text_bn,
            "speed": speed,
            "tts_available": False,
            "message": "TTS integration pending. Text response provided.",
            "fallback_text": text_bn,
        }
