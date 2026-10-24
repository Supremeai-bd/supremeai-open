"""run_scope — M06 P-A: universal run-creation context manager (flag-gated).

বাংলা: প্রতিটি execution-unit (চ্যাট-ডিসপ্যাচ/টুল-নির্বাহ/…) ক্যানোনিকাল
``runs`` টেবিলে পর্যবেক্ষিত হবে — কিন্তু কখনোই আয়োজক-নির্বাহকে ব্লক করবে না।
চুক্তি (Plan Section 10 নীতি):

- **ফ্ল্যাগ-গেট** — ``SUPREMEAI_RUN_FABRIC_UNIVERSAL=true`` ছাড়া এটি
  no-op (``None`` yield; আজকের আচরণ byte-সমতুল্য)। অজানা মানও OFF।
- **লাইফসাইকেল-আইন** — create → REQUESTED→POLICY_CHECKED→PLANNED→RUNNING
  (স্টেট-মেশিনের skip-ahead এজ নিষিদ্ধতা সম্মানে ধাপে ধাপে) → terminal
  (SUCCEEDED/FAILED/CANCELLED)।
- **best-effort** — run-fabric ব্যর্থতা লাউড warning-এ প্রকাশিত হয় এবং
  ``None`` হিসেবে পর্যবেক্ষণ-অনুপস্থিতি জানায়; কখনো ভান নয়, কখনো raise নয়।
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from core.logging_config import logger

_RUN_ACTOR = "run-scope"


def run_fabric_universal() -> bool:
    """Flag-gate: কেবল ``SUPREMEAI_RUN_FABRIC_UNIVERSAL=true``-এই সত্য।"""
    return os.environ.get("SUPREMEAI_RUN_FABRIC_UNIVERSAL", "").strip().lower() == "true"


class RunContext:
    """run_scope দ্বারা yield হওয়া হ্যান্ডেল — terminal নিয়ন্ত্রণের চুক্তি।"""

    def __init__(self, run: Any, service: Any, session: Any) -> None:
        self.run = run
        self._service = service
        self._session = session
        self.terminal: str | None = None

    @property
    def run_id(self) -> Any:
        return getattr(self.run, "id", None)

    def finish(self, terminal: str) -> None:
        """স্বাভাবিক-সমাপ্তির terminal নির্ধারণ (succeeded/failed/cancelled)।"""
        self.terminal = terminal


@contextlib.asynccontextmanager
async def run_scope(
    session: Any,
    service: Any,
    *,
    run_type: str,
    user_id: str,
    title: str | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
    **budget_limits: Any,
) -> AsyncIterator[RunContext | None]:
    """Wrap one execution unit with a canonical run (best-effort, flag-gated)."""
    if not run_fabric_universal():
        yield None
        return

    from runs.state_machine import PLANNED, POLICY_CHECKED, RUNNING

    run = None
    try:
        run = await service.create_run(
            session,
            run_type=run_type,
            user_id=user_id,
            title=title,
            source_type=source_type,
            source_ref=source_ref,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            **budget_limits,
        )
        for state, note in (
            (POLICY_CHECKED, "run_scope: host pre-authorized"),
            (PLANNED, "run_scope: recorded"),
            (RUNNING, "run_scope: started"),
        ):
            await service.transition(
                session, run.id, state, actor=_RUN_ACTOR, detail={"note": note}
            )
        await session.commit()
    except Exception as exc:
        logger.warning(f"⚠️ run_scope create/activate skipped: {exc!r} — host execution unaffected")
        run = None

    ctx = RunContext(run, service, session) if run is not None else None

    if ctx is None:
        yield None
        return

    from runs.state_machine import CANCELLED, FAILED, SUCCEEDED

    try:
        yield ctx
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await service.transition(
                session, ctx.run_id, CANCELLED, actor=_RUN_ACTOR, detail={"note": "host cancelled"}
            )
            await session.commit()
        raise
    except Exception as exc:
        # বাংলা: আয়োজক ব্যর্থ হলে run-ও FAILED হয় (সত্য প্রতিফলন); কিন্তু
        # settle-ব্যর্থতা নিজেই লাউড warning ছাড়া কিছু লুকায় না।
        try:
            await service.transition(
                session,
                ctx.run_id,
                FAILED,
                actor=_RUN_ACTOR,
                detail={"error": str(exc)[:512]},
            )
            await session.commit()
        except Exception as settle_exc:
            logger.warning(f"⚠️ run_scope settle (FAILED) skipped: {settle_exc!r}")
        raise

    terminal = ctx.terminal or "succeeded"
    target = {"failed": FAILED, "cancelled": CANCELLED}.get(terminal, SUCCEEDED)
    try:
        await service.transition(
            session, ctx.run_id, target, actor=_RUN_ACTOR, detail={"note": "run_scope settled"}
        )
        await session.commit()
    except Exception as settle_exc:
        logger.warning(f"⚠️ run_scope settle ({target}) skipped: {settle_exc!r}")


@contextlib.asynccontextmanager
async def observe_run(
    *,
    run_type: str,
    user_id: str = "system",
    title: str | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    correlation_id: str | None = None,
    **budget_limits: Any,
) -> AsyncIterator[RunContext | None]:
    """Self-contained run-observation wrapper (M06 P-A ৮/৮ RunType adoption).

    বাংলা: নিজস্ব DB-session-এ ক্যানোনিকাল run তৈরি করে — আয়োজকের
    ট্রানজেকশন-স্কোপ স্পর্শ করে না (extend, not replace)। চুক্তি:

    - flag-off → ``None`` yield (byte-নিরপেক্ষ no-op);
    - session/service অনুপস্থিতি → লাউড warning + ``None`` (আয়োজক অপ্রভাবিত);
    - আয়োজক-ব্যতিক্রম কখনো গিলে না — run-টি FAILED-এ settle হয়ে ব্যতিক্রম
      আয়োজকের কাছেই যায় (সত্য প্রতিফলন)।
    """
    if not run_fabric_universal():
        yield None
        return

    session_cm: Any = None
    try:
        from database.session import get_db_session_context
        from runs.service import RunService

        session_cm = get_db_session_context()
        session = await session_cm.__aenter__()
        service = RunService()
    except Exception as exc:
        logger.warning(
            f"⚠️ observe_run({run_type}) session/service unavailable: {exc!r} — "
            "host execution unaffected"
        )
        yield None
        return

    try:
        async with run_scope(
            session,
            service,
            run_type=run_type,
            user_id=user_id,
            title=title,
            source_type=source_type,
            source_ref=source_ref,
            correlation_id=correlation_id,
            **budget_limits,
        ) as ctx:
            yield ctx
    finally:
        with contextlib.suppress(Exception):
            if session_cm is not None:
                await session_cm.__aexit__(None, None, None)
