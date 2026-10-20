"""src/services/voice_service.py — Zero-Compute High-Fidelity Bangla Voice Service.

Design notes (honesty + portability + boundary limits):
- ZERO-COMPUTE DOCTRINE: no local neural weights, no GPU, no megabytes of
  model files. Synthesis is LEASED over the Microsoft Edge Neural TTS
  WebSocket protocol by the optional third-party `edge-tts` client
  (pip install edge-tts). The runtime core stays stdlib-only: `edge_tts`
  is imported lazily and ONLY when real synthesis is requested. Without
  it the service degrades LOUDLY (VoiceServiceUnavailable) — exactly the
  Redis/KillSwitch precedent — never silently.
- STREAMING: `stream()` yields raw MP3 chunks as they arrive from the
  protocol; `synthesize()` assembles them into one bytes payload ready
  for a Telegram sendVoice upload.
- BANGLA-FIRST CATALOG: two bn-BD primaries (Pradeep = authoritative
  system broadcasts, Nabanita = conversational assistant) plus two bn-IN
  dialect fallbacks. Voice ids are validated fail-closed.
- PARAMETER SAFETY: rate (e.g. "+10%") and pitch (e.g. "+5Hz") are
  regex-validated before touching the wire; text length is capped.
- TIMEOUTS: every outbound call carries an explicit timeout
  (connect_timeout/receive_timeout into the protocol client plus a
  total-wall-clock asyncio.wait_for guard) — guard doctrine: no IO
  without a timeout.
- CACHE: an injected AudioCache (SHA-256 keyed) eliminates redundant
  network round-trips for repeated phrases (e.g. status summaries).
- TESTABILITY: the synthesizer coroutine is injectable, so the whole
  surface — validation, caching, streaming, error taxonomy — is unit
  testable fully offline with zero sockets and zero optional imports.

Public one-shot contract (skill schema: skills/voice/bangla_voice.yaml):
    await speak_bangla(text, voice="bn-BD-PradeepNeural") -> bytes  (MP3)
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Voice catalog — Bangla-first (bn-BD primary, bn-IN dialect fallbacks)
# ---------------------------------------------------------------------------

DEFAULT_VOICE = "bn-BD-PradeepNeural"

MAX_TEXT_CHARS = 4000  # abuse guard: one Telegram voice note, not an audiobook
DEFAULT_TOTAL_TIMEOUT_S = 60.0  # wall-clock guard for a full synthesis


@dataclass(frozen=True)
class VoiceSpec:
    """One neural voice in the catalog."""

    voice_id: str
    gender: str
    dialect: str
    role: str


VOICE_CATALOG: dict[str, VoiceSpec] = {
    spec.voice_id: spec
    for spec in (
        VoiceSpec(
            voice_id="bn-BD-PradeepNeural",
            gender="male",
            dialect="bn-BD",
            role="authoritative system broadcasts / status reports",
        ),
        VoiceSpec(
            voice_id="bn-BD-NabanitaNeural",
            gender="female",
            dialect="bn-BD",
            role="interactive conversational assistant",
        ),
        VoiceSpec(
            voice_id="bn-IN-BashkarNeural",
            gender="male",
            dialect="bn-IN",
            role="alternate dialect fallback",
        ),
        VoiceSpec(
            voice_id="bn-IN-TanishaaNeural",
            gender="female",
            dialect="bn-IN",
            role="alternate dialect fallback",
        ),
    )
}

# Aliases accepted by validate/resolve (short names -> canonical ids).
VOICE_ALIASES: dict[str, str] = {
    "pradeep": "bn-BD-PradeepNeural",
    "nabanita": "bn-BD-NabanitaNeural",
    "bashkar": "bn-IN-BashkarNeural",
    "tanishaa": "bn-IN-TanishaaNeural",
}

_RATE_RE = re.compile(r"^[+-]\d{1,3}%$")
_PITCH_RE = re.compile(r"^[+-]\d{1,4}Hz$")


# ---------------------------------------------------------------------------
# Error taxonomy — loud, specific, never silent
# ---------------------------------------------------------------------------


class VoiceRequestError(ValueError):
    """Raised for invalid text, unknown voice, or malformed rate/pitch."""


class VoiceServiceUnavailable(RuntimeError):
    """Raised when the optional edge-tts client is not installed.

    Degrades LOUDLY by contract (boundary limit: optional integrations
    degrade loudly, never silently) — the caller must tell the user.
    """


class VoiceSynthesisError(RuntimeError):
    """Raised when the remote synthesis protocol fails or times out."""


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceRequest:
    """A validated synthesis request."""

    text: str
    voice: str = DEFAULT_VOICE
    rate: str = "+0%"
    pitch: str = "+0Hz"
    total_timeout_s: float = DEFAULT_TOTAL_TIMEOUT_S

    @property
    def cache_key_fields(self) -> dict[str, str]:
        return {"voice": self.voice, "rate": self.rate, "pitch": self.pitch}


def resolve_voice(voice: str) -> str:
    """Resolve an alias or full voice id to its canonical id (fail-closed)."""
    candidate = (voice or "").strip()
    if candidate in VOICE_CATALOG:
        return candidate
    if candidate.lower() in VOICE_ALIASES:
        return VOICE_ALIASES[candidate.lower()]
    raise VoiceRequestError(
        "unknown voice {!r}; catalog: {}".format(
            voice, ", ".join(sorted(VOICE_CATALOG))
        )
    )


def validate_request(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    total_timeout_s: float = DEFAULT_TOTAL_TIMEOUT_S,
) -> VoiceRequest:
    """Validate every field fail-closed and return an immutable request."""
    body = (text or "").strip()
    if not body:
        raise VoiceRequestError("text must be a non-empty string")
    if len(body) > MAX_TEXT_CHARS:
        raise VoiceRequestError(
            f"text exceeds {MAX_TEXT_CHARS} characters (got {len(body)})"
        )
    canonical_voice = resolve_voice(voice)
    if not _RATE_RE.match(rate or ""):
        raise VoiceRequestError(
            f"rate {rate!r} malformed; expected sign+digits+%, e.g. '+10%' or '-5%'"
        )
    if not _PITCH_RE.match(pitch or ""):
        raise VoiceRequestError(
            f"pitch {pitch!r} malformed; expected sign+digits+Hz, e.g. '+5Hz' or '-10Hz'"
        )
    if total_timeout_s <= 0:
        raise VoiceRequestError("total_timeout_s must be > 0")
    return VoiceRequest(
        text=body,
        voice=canonical_voice,
        rate=rate,
        pitch=pitch,
        total_timeout_s=total_timeout_s,
    )


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class VoiceResult:
    """Assembled synthesis output (+ cache provenance for honest telemetry)."""

    audio: bytes
    request: VoiceRequest
    cached: bool = False
    chunk_count: int = 0

    @property
    def size_bytes(self) -> int:
        return len(self.audio)

    @property
    def mime_type(self) -> str:
        return "audio/mpeg"


# ---------------------------------------------------------------------------
# Synthesizer protocol (dependency-invertible edge)
# ---------------------------------------------------------------------------


async def _edge_tts_stream(request: VoiceRequest) -> AsyncIterator[bytes]:
    """Lease synthesis to the optional edge-tts client over its WebSocket
    protocol. Imported lazily: absent package -> VoiceServiceUnavailable."""
    try:
        import edge_tts  # optional third-party client (lazy, loud degradation)
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise VoiceServiceUnavailable(
            "edge-tts client is not installed; run: pip3 install edge-tts "
            "(zero-compute doctrine: synthesis is network-leased, never modeled locally)"
        ) from exc
    communicate = edge_tts.Communicate(
        request.text,
        request.voice,
        rate=request.rate,
        pitch=request.pitch,
        connect_timeout=10,
        receive_timeout=30,
    )
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data") or b""
                if data:
                    yield data
    except VoiceServiceUnavailable:
        raise
    except asyncio.TimeoutError as exc:
        raise VoiceSynthesisError("edge-tts protocol timed out") from exc
    except Exception as exc:
        raise VoiceSynthesisError(f"edge-tts synthesis failed: {exc}") from exc


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


class VoiceService:
    """Zero-compute Bangla voice adapter with ephemeral caching.

    `synthesizer` is injectable for offline tests: an async callable
    (request) -> AsyncIterator[bytes]. When omitted, the real edge-tts
    leased stream is used and requires the optional package.
    """

    def __init__(self, cache=None, synthesizer=None) -> None:
        # cache: src.utils.audio_cache.AudioCache or None (no caching)
        self._cache = cache
        self._synthesizer = synthesizer or _edge_tts_stream

    async def stream(self, request: VoiceRequest) -> AsyncIterator[bytes]:
        """Yield MP3 chunks (cache-miss path hits the leased protocol).

        Chunks are yielded to the consumer as they arrive AND buffered so
        the ephemeral cache can be populated without a second round-trip.
        """
        key = None
        if self._cache is not None:
            key = self._cache.key_for(request.text, **request.cache_key_fields)
            hit = self._cache.get(key)
            if hit is not None:
                yield hit
                return
        buffer = bytearray()
        async for chunk in self._synthesizer(request):
            buffer += chunk
            yield chunk
        if self._cache is not None and key is not None and buffer:
            self._cache.put(key, bytes(buffer))

    async def synthesize(self, request: VoiceRequest) -> VoiceResult:
        """Full synthesis with cache short-circuit and wall-clock guard.

        Accepts a validated VoiceRequest (build one via validate_request);
        anything else is rejected fail-closed with VoiceRequestError.
        """
        if not isinstance(request, VoiceRequest):
            raise VoiceRequestError(
                "synthesize() requires a VoiceRequest built via validate_request()"
            )
        key = None
        if self._cache is not None:
            key = self._cache.key_for(request.text, **request.cache_key_fields)
            hit = self._cache.get(key)
            if hit is not None:
                return VoiceResult(
                    audio=hit, request=request, cached=True, chunk_count=1
                )
        try:
            audio, chunk_count = await asyncio.wait_for(
                self._collect(self._synthesizer(request)),
                timeout=request.total_timeout_s,
            )
        except VoiceServiceUnavailable:
            raise
        except VoiceSynthesisError:
            raise
        except asyncio.TimeoutError as exc:
            raise VoiceSynthesisError(
                f"synthesis exceeded {request.total_timeout_s:.0f}s wall-clock guard"
            ) from exc
        except Exception as exc:
            raise VoiceSynthesisError(f"synthesis failed: {exc}") from exc
        if not audio:
            raise VoiceSynthesisError("synthesis returned zero audio bytes")
        if self._cache is not None and key is not None:
            self._cache.put(key, audio)
        return VoiceResult(
            audio=audio, request=request, cached=False, chunk_count=chunk_count
        )

    # -- internals ----------------------------------------------------------

    @staticmethod
    async def _collect(chunks: AsyncIterator[bytes]):
        buffer = bytearray()
        count = 0
        async for chunk in chunks:
            buffer += chunk
            count += 1
        return bytes(buffer), count


# ---------------------------------------------------------------------------
# Public one-shot contract (skill schema: speak_bangla)
# ---------------------------------------------------------------------------

_SHARED_CACHE = None  # lazily built process-wide cache (ephemeral by design)


async def speak_bangla(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    cache=None,
) -> bytes:
    """One-shot Bangla speech synthesis -> MP3 bytes.

    Skill contract (skills/voice/bangla_voice.yaml):
        speak_bangla(text: str, voice: str = "bn-BD-PradeepNeural") -> bytes
    """
    global _SHARED_CACHE
    if cache is None and _SHARED_CACHE is None:
        from ..utils.audio_cache import AudioCache

        _SHARED_CACHE = AudioCache()
    request = validate_request(text, voice=voice, rate=rate, pitch=pitch)
    service = VoiceService(cache=cache if cache is not None else _SHARED_CACHE)
    result = await service.synthesize(request)
    return result.audio
