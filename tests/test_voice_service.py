"""tests/test_voice_service.py — 3-tier verification (tier 3, unit) for the
Zero-Compute High-Fidelity Bangla Voice Service (issue #540).

Minimum contract: 8 passing. Suite ships 33. Fully offline: synthesis is
exercised through injected fake streams, the cache through injectable
clocks/temp dirs, and the Telegram layer through fakes — zero sockets,
zero optional imports (edge_tts is never required to run this suite).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncIterator, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from command.services.voice_service import (  # noqa: E402
        DEFAULT_VOICE,
        VOICE_CATALOG,
        VoiceRequest,
        VoiceRequestError,
        VoiceService,
        VoiceServiceUnavailable,
        VoiceSynthesisError,
        validate_request,
    )
    from command.telegram_bot import (  # noqa: E402
        CommandRouter,
        TelegramUpdate,
        VoiceOutcome,
        build_voice_status_summary,
        sync_voice_synthesizer,
    )
    from command.utils.audio_cache import AudioCache, AudioCacheError  # noqa: E402
    from command.config import CommandConfig  # noqa: E402
except ImportError:  # satellite layout (supremeai-command: src/ package)
    from src.services.voice_service import (  # noqa: E402
        DEFAULT_VOICE,
        VOICE_CATALOG,
        VoiceRequest,
        VoiceRequestError,
        VoiceService,
        VoiceServiceUnavailable,
        VoiceSynthesisError,
        validate_request,
    )
    from src.telegram_bot import (  # noqa: E402
        CommandRouter,
        TelegramUpdate,
        VoiceOutcome,
        build_voice_status_summary,
        sync_voice_synthesizer,
    )
    from src.utils.audio_cache import AudioCache, AudioCacheError  # noqa: E402
    from src.config import CommandConfig  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes (offline synthesizer + clock)
# ---------------------------------------------------------------------------


class FakeClock:
    """Injectable monotonic clock for TTL tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSynthesizer:
    """Deterministic offline stand-in for the edge-tts leased stream."""

    def __init__(self, fail: Optional[Exception] = None, chunk_size: int = 4) -> None:
        self.calls: List[VoiceRequest] = []
        self.fail = fail
        self.chunk_size = chunk_size

    async def __call__(self, request: VoiceRequest) -> AsyncIterator[bytes]:
        self.calls.append(request)
        if self.fail is not None:
            raise self.fail
        payload = ("voice:%s|rate:%s|pitch:%s|" % (request.voice, request.rate, request.pitch)).encode("utf-8") * 3
        for i in range(0, len(payload), self.chunk_size):
            yield payload[i : i + self.chunk_size]


def make_router(synthesize_voice=None) -> CommandRouter:
    config = CommandConfig(
        telegram_bot_token="123456:TEST-ONLY",
        superadmin_chat_id="424242",
        hmac_secret="x" * 32,
    )
    return CommandRouter(
        config=config,
        fetch_status=lambda: "🏰 Control Tower: reachable\n🌉 queued work orders: 2",
        dispatch_issue=lambda url: "🛰️ dispatched",
        arm_kill_switch=lambda: "🛑 armed",
        synthesize_voice=synthesize_voice,
    )


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Request validation (fail-closed)
# ---------------------------------------------------------------------------


def test_validate_rejects_empty_text():
    try:
        validate_request("   ")
    except VoiceRequestError as exc:
        assert "non-empty" in str(exc)
        return
    raise AssertionError("empty text must be rejected")


def test_validate_rejects_unknown_voice():
    try:
        validate_request("hello", voice="bn-XX-NobodyNeural")
    except VoiceRequestError as exc:
        assert "unknown voice" in str(exc)
        return
    raise AssertionError("unknown voice must be rejected")


def test_validate_accepts_all_four_catalog_voices():
    assert len(VOICE_CATALOG) == 4
    for voice_id in VOICE_CATALOG:
        request = validate_request("শুনছি", voice=voice_id)
        assert request.voice == voice_id


def test_validate_resolves_aliases_to_canonical_ids():
    assert validate_request("x", voice="pradeep").voice == "bn-BD-PradeepNeural"
    assert validate_request("x", voice="NABANITA").voice == "bn-BD-NabanitaNeural"
    assert validate_request("x", voice="bashkar").voice == "bn-IN-BashkarNeural"
    assert validate_request("x", voice="tanishaa").voice == "bn-IN-TanishaaNeural"


def test_validate_rejects_malformed_rate_and_pitch():
    for bad_rate in ("ten%", "+10", "10%", "++10%"):
        try:
            validate_request("x", rate=bad_rate)
            raise AssertionError("rate %r must be rejected" % bad_rate)
        except VoiceRequestError:
            pass
    for bad_pitch in ("+5hz", "5Hz", "+Hz", "+5"):
        try:
            validate_request("x", pitch=bad_pitch)
            raise AssertionError("pitch %r must be rejected" % bad_pitch)
        except VoiceRequestError:
            pass


def test_validate_accepts_wellformed_rate_and_pitch():
    request = validate_request("x", rate="+15%", pitch="-20Hz")
    assert request.rate == "+15%" and request.pitch == "-20Hz"


def test_validate_caps_text_length():
    try:
        validate_request("x" * 4001)
    except VoiceRequestError as exc:
        assert "4000" in str(exc)
        return
    raise AssertionError("oversized text must be rejected")


def test_default_voice_is_bd_pradeep():
    assert DEFAULT_VOICE == "bn-BD-PradeepNeural"
    assert validate_request("x").voice == "bn-BD-PradeepNeural"


# ---------------------------------------------------------------------------
# 2. Audio cache (SHA-256, TTL, LRU, temp backend)
# ---------------------------------------------------------------------------


def test_cache_key_is_deterministic_and_input_sensitive():
    k1 = AudioCache.key_for("সিস্টেম সম্পূর্ণ স্বাভাবিক আছে", voice="bn-BD-PradeepNeural", rate="+0%", pitch="+0Hz")
    k2 = AudioCache.key_for("সিস্টেম সম্পূর্ণ স্বাভাবিক আছে", voice="bn-BD-PradeepNeural", rate="+0%", pitch="+0Hz")
    k3 = AudioCache.key_for("সিস্টেম সম্পূর্ণ স্বাভাবিক আছে", voice="bn-BD-NabanitaNeural", rate="+0%", pitch="+0Hz")
    assert k1 == k2 and k1 != k3
    assert len(k1) == 64  # sha256 hex
    k4 = AudioCache.key_for("ab", "c")  # field-boundary guard
    k5 = AudioCache.key_for("a", "bc")
    assert k4 != k5


def test_cache_memory_roundtrip_and_stats():
    cache = AudioCache()
    key = cache.key_for("hello", voice="v")
    assert cache.get(key) is None and cache._misses == 1
    cache.put(key, b"MP3DATA")
    assert cache.get(key) == b"MP3DATA" and cache._hits == 1
    stats = cache.stats()
    assert stats["entries"] == 1 and stats["cached_bytes"] == 7


def test_cache_ttl_expiry_via_injected_clock():
    clock = FakeClock()
    cache = AudioCache(ttl_s=10.0, clock=clock)
    key = cache.key_for("phrase")
    cache.put(key, b"data")
    assert cache.get(key) == b"data"
    clock.advance(9.9)
    assert cache.get(key) == b"data"
    clock.advance(0.2)  # past ttl
    assert cache.get(key) is None  # expired


def test_cache_lru_eviction_respects_max_entries():
    cache = AudioCache(max_entries=2)
    for i in range(4):
        cache.put(cache.key_for("phrase-%d" % i), b"x" * (i + 1))
    stats = cache.stats()
    assert stats["entries"] == 2  # only the 2 most recent survive
    assert cache.get(cache.key_for("phrase-0")) is None
    assert cache.get(cache.key_for("phrase-3")) is not None


def test_cache_temp_backend_roundtrip_and_cleanup():
    cache = AudioCache(backend="temp")
    key = cache.key_for("temp phrase", voice="bn-IN-BashkarNeural")
    cache.put(key, b"TEMPAUDIO")
    assert cache.get(key) == b"TEMPAUDIO"
    cache.close()
    try:
        cache.put(cache.key_for("post-close"), b"x")
        raise AssertionError("put after close must fail loudly")
    except AudioCacheError:
        pass


def test_cache_rejects_bad_backend_and_empty_payload():
    for kwargs in ({"backend": "disk"}, {"max_entries": 0}, {"ttl_s": 0}):
        try:
            AudioCache(**kwargs)
            raise AssertionError("AudioCache(%s) must be rejected" % kwargs)
        except AudioCacheError:
            pass
    cache = AudioCache()
    cache.put(cache.key_for("empty"), b"")
    assert cache.stats()["entries"] == 0  # empty payloads are never cached


# ---------------------------------------------------------------------------
# 3. Voice service (synthesis, streaming, caching, error taxonomy)
# ---------------------------------------------------------------------------


def test_service_synthesizes_and_second_call_hits_cache():
    fake = FakeSynthesizer()
    cache = AudioCache()
    service = VoiceService(cache=cache, synthesizer=fake)
    request = validate_request("সিস্টেম সম্পূর্ণ স্বাভাবিক আছে")
    first = run(service.synthesize(request))
    assert first.audio and not first.cached
    assert first.mime_type == "audio/mpeg"
    second = run(service.synthesize(request))
    assert second.cached and second.audio == first.audio
    assert len(fake.calls) == 1  # network round-trip eliminated


def test_service_cache_key_includes_rate_and_pitch():
    fake = FakeSynthesizer()
    service = VoiceService(cache=AudioCache(), synthesizer=fake)
    run(service.synthesize(validate_request("x", rate="+0%", pitch="+0Hz")))
    run(service.synthesize(validate_request("x", rate="+10%", pitch="+0Hz")))
    assert len(fake.calls) == 2  # different params -> different key


def test_service_streams_chunks_in_order():
    fake = FakeSynthesizer(chunk_size=5)
    service = VoiceService(synthesizer=fake)
    request = validate_request("stream me")
    chunks: List[bytes] = []

    async def consume():
        async for chunk in service.stream(request):
            chunks.append(chunk)

    run(consume())
    assert len(chunks) > 1  # genuinely streamed, not a single blob
    # exact-order check against the fake's deterministic payload
    expected = ("voice:bn-BD-PradeepNeural|rate:+0%|pitch:+0Hz|" * 3).encode("utf-8")
    assert b"".join(chunks) == expected


def test_service_loud_degradation_without_edge_tts():
    async def broken_stream(request):
        raise VoiceServiceUnavailable("edge-tts client is not installed")
        yield b""  # pragma: no cover - makes this an async generator

    service = VoiceService(synthesizer=broken_stream)
    try:
        run(service.synthesize(validate_request("hello")))
    except VoiceServiceUnavailable as exc:
        assert "not installed" in str(exc)
        return
    raise AssertionError("absent optional client must degrade loudly")


def test_service_maps_synthesizer_failure_to_synthesis_error():
    fake = FakeSynthesizer(fail=RuntimeError("websocket exploded"))
    service = VoiceService(synthesizer=fake)
    try:
        run(service.synthesize(validate_request("hello")))
    except VoiceSynthesisError as exc:
        assert "websocket exploded" in str(exc)
        return
    raise AssertionError("synthesizer failure must surface as VoiceSynthesisError")


def test_service_rejects_non_voice_request():
    service = VoiceService()
    try:
        run(service.synthesize("not a request"))
    except VoiceRequestError:
        return
    raise AssertionError("raw string input must be rejected fail-closed")


def test_service_passes_rate_pitch_through_to_synthesizer():
    fake = FakeSynthesizer()
    service = VoiceService(synthesizer=fake)
    run(service.synthesize(validate_request("x", voice="nabanita", rate="-5%", pitch="+7Hz")))
    sent = fake.calls[0]
    assert sent.voice == "bn-BD-NabanitaNeural"
    assert sent.rate == "-5%" and sent.pitch == "+7Hz"


# ---------------------------------------------------------------------------
# 4. Telegram integration (/voice, toggle, transport)
# ---------------------------------------------------------------------------


def test_router_voice_command_returns_voice_audio():
    outcome = VoiceOutcome(audio=b"MP3", voice_used="bn-BD-PradeepNeural", size_bytes=3)
    router = make_router(synthesize_voice=lambda text: outcome)
    reply = router.route(TelegramUpdate("424242", "/voice শুনুন"))
    assert reply.allowed and reply.voice_audio == b"MP3"
    assert reply.action == "voice" and "voice note ready" in reply.text


def test_router_voice_without_text_shows_usage_and_skips_synthesis():
    calls = []

    def spy(text):
        calls.append(text)
        return VoiceOutcome(audio=b"x")

    router = make_router(synthesize_voice=spy)
    reply = router.route(TelegramUpdate("424242", "/voice"))
    assert reply.voice_audio is None and "requires text" in reply.text
    assert calls == []


def test_router_voice_denied_for_non_superadmin():
    calls = []

    def spy(text):
        calls.append(text)
        return VoiceOutcome(audio=b"x")

    router = make_router(synthesize_voice=spy)
    reply = router.route(TelegramUpdate("999999", "/voice শুনুন"))
    assert not reply.allowed and reply.voice_audio is None
    assert calls == []  # RBAC fires before any synthesis


def test_router_voice_unwired_is_loud_not_silent():
    router = make_router(synthesize_voice=None)
    reply = router.route(TelegramUpdate("424242", "/voice শুনুন"))
    assert reply.allowed and "not wired" in reply.text


def test_router_voice_failure_degrades_to_text():
    def failing(text):
        return VoiceOutcome(error="service unavailable: edge-tts missing")

    router = make_router(synthesize_voice=failing)
    reply = router.route(TelegramUpdate("424242", "/voice শুনুন"))
    assert reply.voice_audio is None
    assert "voice synthesis failed" in reply.text and "service unavailable" in reply.text


def test_router_voice_toggle_gates_status_voice_notes():
    outcome = VoiceOutcome(audio=b"AUDIO", voice_used="bn-BD-PradeepNeural", size_bytes=5)
    seen = []

    def spy(text):
        seen.append(text)
        return outcome

    router = make_router(synthesize_voice=spy)
    plain = router.route(TelegramUpdate("424242", "/status"))
    assert plain.voice_audio is None and seen == []
    router.route(TelegramUpdate("424242", "/voiceon"))
    voiced = router.route(TelegramUpdate("424242", "/status"))
    assert voiced.voice_audio == b"AUDIO" and len(seen) == 1
    assert "সিস্টেম সম্পূর্ণ স্বাভাবিক আছে" in seen[0]
    router.route(TelegramUpdate("424242", "/voiceoff"))
    muted = router.route(TelegramUpdate("424242", "/status"))
    assert muted.voice_audio is None


def test_router_status_voice_failure_appends_warning_not_crash():
    def failing(text):
        return VoiceOutcome(error="synthesis timed out")

    router = make_router(synthesize_voice=failing)
    router.route(TelegramUpdate("424242", "/voiceon"))
    reply = router.route(TelegramUpdate("424242", "/status"))
    assert "reachable" in reply.text  # text runway still flows
    assert "voice alert unavailable" in reply.text


def test_router_status_voice_without_synthesizer_warns_loudly():
    router = make_router(synthesize_voice=None)
    router.route(TelegramUpdate("424242", "/voiceon"))
    reply = router.route(TelegramUpdate("424242", "/status"))
    assert "no synthesizer is wired" in reply.text


def test_build_voice_status_summary_is_deterministic():
    healthy = build_voice_status_summary("🏰 Control Tower: reachable\nBridge: 1")
    down = build_voice_status_summary("🏰 Control Tower: unreachable")
    assert healthy == build_voice_status_summary("🏰 Control Tower: reachable\nBridge: 1")
    assert healthy != down
    assert "সিস্টেম সম্পূর্ণ স্বাভাবিক আছে" in healthy
    assert "পৌঁছানো যাচ্ছে না" in down


def test_sync_voice_synthesizer_wraps_service_loudly():
    class BoomService:
        async def synthesize(self, request):
            raise VoiceServiceUnavailable("edge-tts client is not installed")

    synth = sync_voice_synthesizer(BoomService())
    outcome = synth("শুনুন")
    assert not outcome.ok and "service unavailable" in (outcome.error or "")


def test_sync_voice_synthesizer_validation_error_never_raises():
    class OkService:
        async def synthesize(self, request):
            raise AssertionError("must not be reached")

    synth = sync_voice_synthesizer(OkService())
    outcome = synth("")  # invalid: empty text
    assert not outcome.ok and "invalid request" in (outcome.error or "")


def test_help_text_documents_voice_commands():
    router = make_router()
    reply = router.route(TelegramUpdate("424242", "/help"))
    for token in ("/voice", "/voiceon", "/voiceoff"):
        assert token in reply.text
