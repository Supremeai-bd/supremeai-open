# backend/core/llm/llm_gateway/completion.py
"""Main async completion interface (fallback chain, cache, cost guard).

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py into
the CompletionMixin used by LLMGateway (core/llm/llm_gateway/gateway.py).

NOTE (package-split seam): `acompletion` resolves `get_firestore_db` from THIS
module's globals, but tests patch it on the package namespace
(`patch("core.llm.llm_gateway.get_firestore_db")`, e.g.
tests/core/test_integration_phase3.py). The module-level proxy below forwards
through the package attribute at CALL time so that patch target keeps working
exactly as before the split; at runtime it resolves to the same
utils.firestore_helpers.get_firestore_db function.
"""

import asyncio
import contextlib
import json
import random
from dataclasses import replace
from typing import Any

import httpx

from core.errors.error_bus import with_error_bus
from core.llm.telemetry import track_llm_call
from core.logging_config import logger

from ...config import settings  # Fixed import path - using relative import
from ...cost_guard import CostGuard  # Fixed import path - using relative import
from ...health.self_healer import (
    SelfHealerService,  # Fixed import path - using relative import
)
from ...messaging.event_bus import (  # Fixed import path - using relative import
    ErrorContext,
    ErrorEvent,
    error_event_bus,
)
from ...observability.interfaces import PrivacyMode
from ...prompt_handler import (
    compress_prompt_messages,
    normalize_prompt,  # Fixed import path - using relative import
)
from ..interfaces import ExecutionMode
from .context import InferenceContext
from .errors import GatewayError
from .registry import _provider_key_pool, _resolve_litellm_target
from .spend_meter import settle_gateway_spend


def get_firestore_db(*args: Any, **kwargs: Any):
    """Package-split patch seam — see module docstring (task 4-a)."""
    from core.llm import llm_gateway as _package

    return _package.get_firestore_db(*args, **kwargs)


class CompletionMixin:
    """Main completion method for LLMGateway (verbatim move)."""

    @with_error_bus("acompletion")
    async def acompletion(
        self,
        prompt: str | list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
        task_type: str = "general",
        stream: bool = False,
        timeout: float = 12.0,
        model: str | None = None,
        provider: str | None = None,
        tenant_id: str | None = None,
        tier: str | None = None,
        context: InferenceContext | None = None,
        **kwargs,
    ) -> Any:
        """বাংলা মন্তব্ব: Main async completion interface।

        M03 P0-পূর্ণাংশ: serving route-গুলো ``context=InferenceContext(...)``
        বাধ্যতামূলকভাবে পাস করে (scripts/ci/check_gateway_context.py ratchet) —
        টেন্যান্ট/টাস্ক/টিয়ার/ট্রেস অ্যাট্রিবিউশন এখন এক-কাঠামোয় আসে, ফলে
        CostGuard-বাইপাসড অদৃশ্য-খরচ পথ কাঠামোগতভাবে বন্ধ।
        """
        import asyncio

        self._ensure_litellm_ready()

        import litellm  # lazy import

        # বাংলা মন্তব্য: context এলে সেটিই একক-সত্যের উৎস — attribution-যাচাই
        # ব্যর্থ হলে fail-closed লাউড এরর (নীরব অজানা-টেন্যান্ট খরচ নিষিদ্ধ)।
        if context is not None:
            attribution_errors = context.validate_attribution()
            if attribution_errors:
                raise GatewayError(
                    f"InferenceContext attribution contract violation: {attribution_errors}"
                )
            # Issue #685 (Domain 15): propagate the request correlation id into
            # the inference context via the EXISTING context hook — no new
            # provider-SDK params. When the serving route did not set one,
            # default to the id the tracing middleware established
            # (X-Request-ID / X-Correlation-ID), so the gateway's
            # ``to_log_fields()`` telemetry line and durable learning events
            # carry the same id as the API request logs.
            if context.correlation_id is None:
                from core.request_context import get_correlation_id

                _corr_id = get_correlation_id()
                if _corr_id:
                    context = replace(context, correlation_id=_corr_id)
            if context.prompt is not None:
                prompt = context.prompt
            elif context.messages is not None:
                messages = list(context.messages)
                if prompt is None:
                    prompt = messages
            task_type = context.task_type
            stream = context.stream
            if context.tenant_id and context.tenant_id != "anonymous":
                tenant_id = context.tenant_id
            if context.tier:
                tier = context.tier
            logger.info(f"[LLMGateway] inference-context: {context.to_log_fields()}")

        if messages is not None and prompt is None:
            prompt = messages

        prompt_text = normalize_prompt(prompt)

        # বাংলা মন্তব্ব: Semantic cache check — API call আগে cost-zero response
        if prompt_text and not stream:
            cached = await self.cache.query_similar(prompt_text, task_type=task_type)
            if cached:
                # Sprint 3 (learning loop): durable cache-hit observation — evidence
                # for cache-effectiveness measurement (plan §13.1). Best-effort.
                try:
                    from core.learning import record_llm_event as _cache_hit_event

                    _cache_hit_event(
                        provider="semantic-cache",
                        model=str(getattr(cached, "model", "") or "unknown"),
                        task_type=task_type,
                        success=True,
                        latency_ms=0,
                        cache_hit=True,
                        session_id=str(tenant_id or ""),
                    )
                except Exception as exc:  # best-effort telemetry — never block cache-hit
                    logger.warning("[LLMGateway] cache-hit telemetry record failed: %s", exc)
                return {
                    "success": True,
                    "text": cached.response,
                    "model": cached.model,
                    "cost": 0.0,
                    "cached": True,
                }

        # বাংলা মন্তব্ব: Pre-flight cost guard
        if tenant_id:
            db = get_firestore_db()
            if db:
                cost_guard = CostGuard(db)
                try:
                    from core.prompt_handler import estimate_tokens

                    tokens = estimate_tokens(prompt_text)
                    estimated_cost = tokens * getattr(settings, "llm_cost_per_token", 0.00001)
                except Exception:  # Safe fallback cost on token estimate failure
                    estimated_cost = 0.01
                await cost_guard.check_budget(tenant_id, estimated_cost)

        # বাংলা মন্তব্জ: Tier 0 Fast-Path — deterministic tasks bypass ALL LLM calls (Needle 2-inspired).
        # ConfidenceGatedDispatcher (reusing AdvancedModelRouter) evaluates prompt confidence;
        # if >= threshold and pattern-matched, returns immediately with zero token cost.
        from core.llm.advanced_model_router import get_advanced_router

        decision = await asyncio.to_thread(
            get_advanced_router().route_with_confidence, prompt_text, task_type
        )
        if decision.is_deterministic and decision.deterministic_result:
            logger.info(
                f"[LLMGateway] Tier 0 bypass: pattern={decision.matched_pattern} "
                f"confidence={decision.confidence:.2f} — skipping LLM call chain"
            )
            return {
                "success": True,
                "text": json.dumps(decision.deterministic_result, indent=2),
                "model": "tier0-deterministic",
                "cost": 0.0,
                "cached": False,
                "tier0_bypass": True,
            }

        # Use performance optimizer to select best model if not specified
        if not model:
            model = await self.performance_optimizer.optimize_model_selection(
                task_type, prompt_text
            )

        call_chain = self._build_call_chain(model, provider, task_type)

        # Sprint 5 (§8.2): evidence-driven EXPLORATION — append at most ONE
        # measured alternative candidate to the chain TAIL for limited
        # measurement. The head of the chain (explicit routing policy) is
        # never reordered; flag-gated; snapshot is refreshed by the
        # LearningLoopAgent (no network here). Bounded + reversible.
        try:
            from core.learning.provider_scorer import (
                exploration_candidate,
                get_adaptive_routing_enabled,
                score_snapshot,
            )

            if get_adaptive_routing_enabled() and score_snapshot:
                _explorer = exploration_candidate(score_snapshot)
                if _explorer is not None and _explorer.model not in call_chain:
                    call_chain.append(_explorer.model)
                    logger.info(
                        f"[LLMGateway] adaptive exploration candidate appended: "
                        f"{_explorer.model} (score={_explorer.score})"
                    )
        except Exception as exc:  # best-effort adaptive routing — never block main call
            logger.warning("[LLMGateway] adaptive routing scorer failed: %s", exc)

        if isinstance(prompt, list):
            messages_payload = prompt
        else:
            messages_payload = [{"role": "user", "content": prompt}]

        # Apply OmniRoute Caveman-lite compression to save tokens
        messages_payload = compress_prompt_messages(messages_payload)

        # ──────────────────────────────────────────────────────────────────
        # R5 FIX: TokenJuice — content-aware pruning for HTML/JSON/logs/git_diff
        # Saves 60-80% tokens on bulky tool outputs (Playwright DOM, API JSON,
        # terminal logs, git diffs) before sending to LLM.
        # Rollback: set env TOKEN_JUICE_ENABLED=false to disable.
        # ──────────────────────────────────────────────────────────────────
        if settings.token_juice_enabled:
            try:
                from engine.compression.token_juice import TokenJuice

                _juicer = TokenJuice()
                _TOKEN_JUICE_MIN_CHARS = 800  # skip small payloads (overhead > savings)
                _tokens_saved_by_juice = 0

                for _idx, _msg in enumerate(messages_payload):
                    _content = _msg.get("content") if isinstance(_msg, dict) else None
                    if not isinstance(_content, str) or len(_content) < _TOKEN_JUICE_MIN_CHARS:
                        continue
                    _detected = _juicer.detect_content_type(_content)
                    if _detected in {"html", "dom", "json", "log", "terminal", "git_diff"}:
                        _result = _juicer.compress(_content, content_type=_detected)
                        if _result.compression_ratio > 0.20:  # only apply if >=20% saved
                            messages_payload[_idx] = {
                                **_msg,
                                "content": _result.compressed_text,
                                "_juice_meta": {
                                    "orig_chars": _result.original_chars,
                                    "comp_chars": _result.compressed_chars,
                                    "ratio": round(_result.compression_ratio, 3),
                                    "type": _detected,
                                },
                            }
                            _tokens_saved_by_juice += (
                                _result.estimated_original_tokens
                                - _result.estimated_compressed_tokens
                            )

                if _tokens_saved_by_juice > 0:
                    logger.info(
                        f"[LLMGateway] TokenJuice saved ~{_tokens_saved_by_juice} tokens "
                        f"on this call (env TOKEN_JUICE_ENABLED=true)"
                    )
            except Exception as _juice_err:
                # TokenJuice should never break the LLM call path
                logger.debug(f"[LLMGateway] TokenJuice skipped: {_juice_err}")

        if stream:
            # M16 P-A: streaming-এও একই accounting অর্থবোধ — tenant/tier context
            # generator-এ পাঠানো হচ্ছে যেন stream শেষে বাস্তব usage থেকে খরচ
            # meter হয় (non-streaming-এর সাথে parity)।
            return self._stream_completion(
                messages_payload,
                call_chain,
                timeout,
                tenant_id=tenant_id,
                tier=tier,
                task_type=task_type,
            )

        # Sprint 5 (§13.3): single-flight request coalescing — identical
        # in-flight requests share one upstream call. Flag-gated (default off);
        # bounded map + bounded follower wait; any failure degrades to
        # executing normally, so dedup can never reduce availability.
        _coalescer = None
        _dedup_k = None
        _is_leader = False
        from core.learning.dedup import dedup_key, get_request_coalescer, request_dedup_enabled

        if request_dedup_enabled() and call_chain:
            _coalescer = get_request_coalescer()
            _dedup_k = dedup_key(call_chain[0], task_type, messages_payload)
            _leader_entry = _coalescer.try_claim(_dedup_k)
            if _leader_entry is not None:
                _shared = await _coalescer.wait_for_leader(_leader_entry)
                if _shared is not None:
                    _shared["deduplicated"] = True
                    logger.info("[LLMGateway] request coalesced onto in-flight duplicate")
                    return _shared
            _is_leader = _leader_entry is None

        last_exception: Exception | None = None
        mode = kwargs.pop("mode", getattr(self, "mode", ExecutionMode.AUTO))

        if mode in (ExecutionMode.LOCAL, ExecutionMode.AUTO):
            if self.local_adapter is not None and await self.local_adapter.health_check():
                local_model = kwargs.pop("local_model", "llama3.2")
                try:
                    logger.info(f"[LLMGateway] Attempting LOCAL execution with {local_model}")
                    response = await self.local_adapter.generate(
                        model=local_model,
                        messages=messages_payload,
                        temperature=kwargs.get("temperature", 0.7),
                        max_tokens=kwargs.get("max_tokens"),
                        timeout=timeout,
                    )
                    _local_result = {
                        "success": True,
                        "text": response["choices"][0]["message"]["content"],
                        "model": local_model,
                        "cost": 0.0,
                    }
                    if _is_leader and _coalescer is not None and _dedup_k:
                        with contextlib.suppress(Exception):
                            _coalescer.publish_success(_dedup_k, _local_result)
                    return _local_result
                except Exception as e:
                    logger.warning(f"[LLMGateway] Local execution failed: {e}")
                    if mode == ExecutionMode.LOCAL:
                        raise e
                else:
                    await self.observability.trace_generation(
                        model=local_model,
                        prompt=messages_payload,
                        response_text=response["choices"][0]["message"]["content"],
                        cost=0.0,
                        privacy_mode=PrivacyMode.METADATA_ONLY,
                    )
            elif mode == ExecutionMode.LOCAL:
                raise RuntimeError("Local execution requested but Ollama is not healthy.")

        # Sprint 3: pre-call token estimate so actual-vs-estimated can be
        # calibrated per provider/model (bounded EMA, see core.learning.calibration).
        _estimated_tokens: int | None = None
        try:
            from core.prompt_handler import estimate_tokens as _estimate_tokens

            _estimated_tokens = int(_estimate_tokens(prompt_text))
        except Exception:
            _estimated_tokens = None

        # FIX (P2, review 2026-09-12): pop BYOK key once, BEFORE the chain loop,
        # so every fallback attempt can reuse the caller's custom key.
        _byok_api_key = kwargs.pop("api_key", None)

        for _chain_index, current_model in enumerate(call_chain):
            # FINAL-TEST FIX (2026-09-13): skip models verified retired at
            # their provider, and resolve OpenAI-compatible routers (BYNARA,
            # BAI) to their litellm target + base URL up front.
            try:
                _litellm_model, _api_base = _resolve_litellm_target(current_model)
            except ValueError as retired_err:
                logger.warning(f"[LLMGateway] Skipping {current_model}: {retired_err}")
                continue
            # Circuit Breaker check
            cb = self._get_or_create_circuit_breaker(current_model)
            if not cb.allow_request():
                logger.warning(
                    f"[LLMGateway] Circuit breaker OPEN for {current_model}. Skipping..."
                )
                continue

            try:
                logger.info(f"[LLMGateway] Attempting: {current_model}")
                # বাংলা মন্তব্ব: api_key per-call pass — os.environ injection সম্পূর্ণ নিষিদ্ধ।
                # কাস্টম api_key পাস করা হলে সেটি ব্যবহার করা হবে, অন্যথায় মডেলের ডিফল্ট কী ব্যবহার হবে।
                api_key = _byok_api_key or await self._get_api_key_for_model(current_model)
                session_id = kwargs.pop("session_id", "") or str(tenant_id or "")
                provider_name = current_model.split("/")[0] if "/" in current_model else "unknown"
                # Issue #685 (Domain 15): thread the request correlation id into
                # the telemetry record's EXISTING ``request_id`` field — it is
                # already merged by track_llm_call and flows into both the JSON
                # telemetry log line and the durable learning_events sink.
                if context is not None and context.correlation_id:
                    _request_id: str | None = context.correlation_id
                else:
                    from core.request_context import get_correlation_id

                    _request_id = get_correlation_id() or None
                async with track_llm_call(
                    session_id=session_id,
                    provider=provider_name,
                    model=current_model,
                    task_type=task_type,
                    metadata={
                        "fallback_count": _chain_index,
                        "estimated_tokens": _estimated_tokens,
                        "request_id": _request_id,
                    },
                ) as rec:
                    rec.estimated_tokens = _estimated_tokens
                    response = await self.cloud_adapter.generate(
                        model=_litellm_model,
                        messages=messages_payload,
                        timeout=timeout,
                        api_key=api_key,
                        api_base=_api_base,
                        **kwargs,
                    )
                    cost = response.get("cost", 0.0)
                    rec.cost_usd = cost
                    if "usage" in response:
                        rec.tokens_prompt = response["usage"].get("prompt_tokens")
                        rec.tokens_completion = response["usage"].get("completion_tokens")
                    cb.mark_success()

                    # Sprint 4: always-on learning-loop feed — record the execution in
                    # the SHARED FitnessEngine metrics store so SelfEvolutionAgent._tick()
                    # sees real traffic even when ENABLE_EVOLUTION_LEARNING is off.
                    try:
                        from api.deps import get_fitness_engine

                        get_fitness_engine().track_execution(
                            skill_name=task_type,
                            success=True,
                            latency=rec.latency_ms,
                            token_cost=float(rec.tokens_completion or 0),
                        )
                    except Exception as fit_err:
                        logger.debug(f"FitnessEngine.track_execution skipped: {fit_err}")

                    # FIX (ANALYSIS-D): Wire EvolutionEngine.learn_from_success into
                    # the success path. Original code never called this method, so
                    # the auto-learning was write-only (ExperienceDatabase.record_experience
                    # in task.py) and never fed back into the evolution engine.
                    # Gated behind env ENABLE_EVOLUTION_LEARNING (default false) so
                    # admins can opt-in after verifying the EvolutionEngine works.
                    if settings.enable_evolution_learning:
                        try:
                            # SELF-EVOLVE FIX (real): wire EvolutionEngine to the SHARED
                            # FitnessEngine singleton (from api.deps.get_fitness_engine).
                            # Previously EvolutionEngine() was called with no args, so
                            # self.fitness_engine was always None → learn_from_success
                            # wrote to DB but never called track_execution →
                            # SelfEvolutionAgent._tick() always saw empty metrics →
                            # no auto-refactor ever triggered (the "loop" was NOT closed).
                            # Now both EvolutionEngine AND SelfEvolutionAgent use the
                            # SAME FitnessEngine singleton, so metrics are shared.
                            from api.deps import get_fitness_engine
                            from core.self_evolution.evolution_engine import EvolutionEngine

                            _evolution_engine = EvolutionEngine(fitness_engine=get_fitness_engine())
                            _evolution_engine.learn_from_success(
                                task=prompt_text,
                                approach=current_model,
                                result=response["choices"][0]["message"]["content"],
                            )
                        except Exception as evo_err:
                            logger.debug(f"EvolutionEngine.learn_from_success skipped: {evo_err}")

                    await self.observability.trace_generation(
                        model=current_model,
                        prompt=messages_payload,
                        response_text=response["choices"][0]["message"]["content"],
                        usage=response.get("usage"),
                        cost=cost,
                        session_id=session_id,
                        metadata={"task_type": task_type},
                        privacy_mode=PrivacyMode.FULL,
                    )

                    _result = {
                        "success": True,
                        "text": response["choices"][0]["message"]["content"],
                        "model": current_model,
                        "cost": cost,
                    }
                    # M16 P-A: বাস্তব খরচ meter — successful call-এর provider usage
                    # থেকে record_spend ফিড (ড্যাশবোর্ডের চিরস্থায়ী $0-র অবসান)।
                    # metering ব্যর্থ হলেও inference ফলাফল অক্ষত থাকে।
                    await settle_gateway_spend(
                        tenant_id=tenant_id,
                        tier=tier,
                        model=current_model,
                        task_type=task_type,
                        path="completion",
                        usage=response.get("usage"),
                        actual_cost=cost,
                    )
                    # Issue #438: a successful call proves the key is healthy —
                    # reset any auth-error cooldown escalation for it.
                    try:
                        await _provider_key_pool.mark_success(provider_name, api_key)
                    except Exception as pool_exc:
                        logger.warning(
                            f"[LLMGateway] key-pool mark_success failed for {provider_name}: {pool_exc}"
                        )
                    if _is_leader and _coalescer is not None and _dedup_k:
                        with contextlib.suppress(Exception):
                            _coalescer.publish_success(_dedup_k, _result)
                    return _result
            except asyncio.CancelledError:
                # বাংলা মন্তব্ব: CancelledError re-raise — কখনো suppress করা যাবে না
                logger.warning(f"[LLMGateway] acompletion cancelled during model {current_model}")
                raise
            except httpx.HTTPStatusError as exc:
                # Handle specific HTTP status codes like 429 (rate limit)
                if exc.response.status_code == 429:
                    # FIX (P0): put this provider key on short cooldown so key
                    # rotation picks a healthy sibling on the next attempt.
                    try:
                        await _provider_key_pool.mark_error(provider_name, api_key, 429)
                    except Exception as pool_exc:
                        logger.warning(
                            f"[LLMGateway] key-pool mark_error failed for {provider_name}: {pool_exc}"
                        )
                    # Try to handle rate limit with backoff and Retry-After header
                    handled = await self._handle_rate_limit_error(current_model, exc)
                    if handled:
                        # Retry the same model after backoff instead of moving to next in chain
                        logger.info(
                            f"[LLMGateway] Retrying {current_model} after rate limit backoff..."
                        )
                        try:
                            response = await self.cloud_adapter.generate(
                                model=_litellm_model,
                                messages=messages_payload,
                                timeout=timeout,
                                api_key=api_key or await self._get_api_key_for_model(current_model),
                                api_base=_api_base,
                                **kwargs,
                            )
                            cb.mark_success()
                            # Sprint 3: record the successful 429-retry as its own
                            # telemetry event (error_class="rate_limit" so provider
                            # metrics can count rate-limit frequency per plan §8.1).
                            try:
                                from core.learning import record_llm_event as _retry_event

                                _retry_event(
                                    provider=provider_name,
                                    model=current_model,
                                    task_type=task_type,
                                    success=True,
                                    latency_ms=None,
                                    input_tokens=(response.get("usage") or {}).get("prompt_tokens"),
                                    output_tokens=(response.get("usage") or {}).get(
                                        "completion_tokens"
                                    ),
                                    actual_cost=response.get("cost") or None,
                                    error_class="rate_limit",
                                    session_id=str(tenant_id or ""),
                                    metadata={"retry_after_backoff": True},
                                )
                            except (
                                Exception
                            ) as exc:  # best-effort telemetry — never block retry success
                                logger.warning(
                                    "[LLMGateway] retry telemetry record failed: %s", exc
                                )
                            # M16 P-A: 429-retry-ও একটি বাস্তব successful call — একই
                            # accounting অর্থবোধে খরচ meter হবে (parity)।
                            await settle_gateway_spend(
                                tenant_id=tenant_id,
                                tier=tier,
                                model=current_model,
                                task_type=task_type,
                                path="completion-429-retry",
                                usage=response.get("usage"),
                                actual_cost=response.get("cost"),
                            )
                            return {
                                "success": True,
                                "text": response["choices"][0]["message"]["content"],
                                "model": current_model,
                                "cost": response.get("cost", 0.0),
                            }
                        except Exception as retry_exc:
                            logger.warning(
                                f"[LLMGateway] Retry failed for {current_model}: {retry_exc}"
                            )
                            # Continue to next model in chain if retry also fails

                # Handle other HTTP errors (5xx, etc.) with specific backoff
                elif exc.response.status_code >= 500:
                    logger.warning(
                        f"[LLMGateway] Server error {exc.response.status_code} for {current_model}, applying short backoff..."
                    )
                    await asyncio.sleep(random.uniform(0.5, 1.5))  # Short backoff for server errors

                # Handle auth errors (401, 403) - don't retry, skip to next model immediately
                elif exc.response.status_code in (401, 403):
                    logger.warning(
                        f"[LLMGateway] Auth error {exc.response.status_code} for {current_model}, skipping to next model..."
                    )
                    # FIX (P0): long cooldown for auth errors (key likely invalid)
                    try:
                        await _provider_key_pool.mark_error(
                            provider_name, api_key, exc.response.status_code
                        )
                    except Exception as pool_exc:
                        logger.warning(
                            f"[LLMGateway] key-pool mark_error failed for {provider_name}: {pool_exc}"
                        )
                    cb.mark_failure()
                    continue

                last_exception = exc
                cb.mark_failure()
                logger.opt(exception=True).warning(
                    f"[LLMGateway] Model {current_model} failed with status {exc.response.status_code}. Trying next in chain..."
                )
                continue
            except Exception as exc:
                last_exception = exc
                cb.mark_failure()
                logger.opt(exception=True).warning(
                    f"[LLMGateway] Model {current_model} failed. Trying next in chain..."
                )
                continue

        # বাংলা মন্তব্ব: সব fallbacks exhausted — self healer trigger এবং error emit
        final_exception = last_exception or RuntimeError(
            "All routing models failed to produce a completion."
        )
        if _is_leader and _coalescer is not None and _dedup_k:
            with contextlib.suppress(Exception):
                _coalescer.publish_failure(_dedup_k, final_exception)
        if tenant_id:
            db = get_firestore_db()
            if db:
                healer = SelfHealerService(db)
                await healer.propose_fix(
                    tenant_id=tenant_id,
                    error_pattern=f"LLMGateway all-fail: {str(final_exception)[:100]}",
                    proposed_fix="Check fallback model API keys and routing policy.",
                    impact_score=0.2,
                    dependency_tree=["core.llm_gateway"],
                )
        error_event_bus.emit(
            ErrorEvent(
                module="llm_gateway",
                error_type="ALL_MODELS_FAILED",
                message=str(final_exception)[:500],
                severity="CRITICAL",
                structured_context=ErrorContext(module="auto_fixed"),
                context={"tenant_id": tenant_id, "call_chain": call_chain},
            )
        )
        raise final_exception
