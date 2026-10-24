"""Implements the evolutionary learning and adaptation engine for the AI system.

This module is responsible for recording task outcomes, detecting patterns of
failure (e.g., repeated task failures, underperforming prompts), and
proposing improvements such as new skills or optimized prompts via LLM
interaction. It also manages user feedback and persists all evolutionary
data using a dual-storage strategy (Supabase and local SQLite).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from brain.model_router import ModelRouter
from core.logging_config import logger

try:
    from prometheus_client import Counter

    evolution_write_failures = Counter(
        "evolution_write_failures_total",
        "Number of failures while reading/writing evolution databases",
    )
except ImportError:
    evolution_write_failures = None


class EvolutionEngine:
    """Persists task outcomes, detects repeated failures, proposes and auto-generates skills."""

    def __init__(
        self,
        db_path: str | None = None,
        model_router: ModelRouter | None = None,
        fitness_engine: Any | None = None,
    ):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = db_path or os.getenv(
            "EVOLUTION_DB_PATH", os.path.join(base, "data", "evolution.db")
        )
        self.model_router = model_router or ModelRouter()
        # SELF-EVOLVE FIX: connect EvolutionEngine to FitnessEngine so that
        # every learn_from_success/failure call updates the fitness metrics.
        # This closes the self-evolution loop:
        #   LLM call → learn_from_success → fitness_engine.track_execution →
        #   SelfEvolutionAgent._tick reads metrics → _trigger_refactor →
        #   AutoSkillCreator generates improved skill
        # Previously: EvolutionEngine wrote to DB but FitnessEngine.metrics
        # stayed empty (only populated by AutoSkillCreator after skill execution).
        self.fitness_engine = fitness_engine

        # বাংলা মন্তব্য: P2 Fix — Production Cloud Run-এ local SQLite নিষিদ্ধ।
        # /data/ directory ephemeral — container restart-এ সব data হারায়।
        # শুধু Supabase (persistent) ব্যবহার করুন বা Cloud Storage FUSE mount (/mnt/) দিন।
        from core.config import settings

        env = settings.env
        if env == "production" and "/data/" in str(self.db_path):
            gcs_path = os.getenv("EVOLUTION_DB_PATH_GCS")
            if not gcs_path:
                raise RuntimeError(
                    "🛑 FATAL: ephemeral SQLite disallowed in production. "
                    "Set EVOLUTION_DB_PATH=/mnt/gcs/evolution.db (Cloud Storage FUSE) "
                    "or route through Supabase-only mode (EVOLUTION_STORAGE=supabase)."
                )
            self.db_path = gcs_path

        os.makedirs(os.path.dirname(str(self.db_path)), exist_ok=True)
        self._ensure_schema()

    # Issue #1700 (thread-unsafe SQLite): all connections were opened with
    # check_same_thread=False and no mutual exclusion — concurrent callers
    # (async tasks + worker threads) could interleave writes and hit SQLite
    # "database is locked" corruption windows. A re-entrant lock now
    # serializes every connection's full lifetime (acquire → work → close),
    # and a busy_timeout gives honest waiting instead of instant lock errors.
    # বাংলা: প্রতিটি কানেকশনের সম্পূর্ণ জীবনকাল জুড়ে RLock ধরে রাখা হয়,
    # ফলে একাধিক থ্রেড/টাস্ক একসাথে একই SQLite ফাইলে লিখতে পারে না।
    _db_lock = threading.RLock()

    def _acquire_connection(self) -> sqlite3.Connection:
        """Open a connection while holding the class DB lock (issue #1700)."""
        self._db_lock.acquire()
        try:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA busy_timeout = 30000")
            return conn
        except BaseException:
            self._db_lock.release()
            raise

    @staticmethod
    def _release_connection(conn: sqlite3.Connection) -> None:
        """Close the connection and drop the DB lock (always pair in finally)."""
        conn.close()
        EvolutionEngine._db_lock.release()

    def _ensure_schema(self) -> None:
        conn = self._acquire_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    approach TEXT NOT NULL,
                    result TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prompt_optimizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_hash TEXT NOT NULL,
                    original_prompt TEXT,
                    optimized_prompt TEXT,
                    improvement REAL,
                    applied INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    source_pattern TEXT,
                    generated_code TEXT,
                    status TEXT DEFAULT 'proposed',
                    created_at TEXT NOT NULL,
                    registered_at TEXT
                );
                CREATE TABLE IF NOT EXISTS feedback_loop (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    query TEXT,
                    retrieved_chunks TEXT,
                    user_rating REAL,
                    adjusted INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
            """)
            conn.commit()
        finally:
            self._release_connection(conn)

    def learn_from_success(self, task: str, approach: str, result: str) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        supabase_success = False
        try:
            from database.supabase_client import db

            if db.client:
                db.insert_task_history(task, approach, result, True, created_at)
                supabase_success = True
            # বাংলা মন্তব্য: P1 Fix — else branch-এ supabase_success = True সরানো হলো।
            # db.client None হলে supabase_success False থাকবে — এটিই সঠিক behavior।
            # আগে: else: supabase_success = True — এটি false positive তৈরি করতো।
            else:
                logger.warning(
                    "Supabase client is None. Task history will only be stored in local SQLite."
                )
        except Exception as e:
            logger.warning(f"Failed to insert success to Supabase: {e}")
            if evolution_write_failures:
                evolution_write_failures.inc()

        # বাংলা মন্তব্য: Supabase fail হলেও local SQLite-তে store করা হবে (degraded mode)
        # আগে: supabase fail হলে SQLite skip করা হতো — data loss হতো
        conn = self._acquire_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO task_history (task, approach, result, success, created_at) VALUES (?, ?, ?, ?, ?)",
                (task, approach, result, 1, created_at),
            )
            conn.commit()
            return {
                "stored": True,
                "supabase_synced": supabase_success,
                "task": task,
                "approach": approach,
                "result": result,
            }
        except sqlite3.Error as db_err:
            logger.error(f"SQLite write also failed: {db_err}")
            if evolution_write_failures:
                evolution_write_failures.inc()
            return {
                "stored": False,
                "supabase_synced": supabase_success,
                "sqlite_error": str(db_err),
            }
        finally:
            self._release_connection(conn)
            # SELF-EVOLVE FIX: update FitnessEngine so _tick() can evaluate
            # the "approach" (model name) and trigger refactors if needed.
            if self.fitness_engine is not None:
                try:
                    self.fitness_engine.track_execution(
                        skill_name=approach, success=True, latency=0.0
                    )
                except Exception as fit_err:
                    logger.debug(f"fitness_engine.track_execution skipped: {fit_err}")

    def learn_from_failure(self, task: str, approach: str, result: str) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        supabase_success = False
        db = None
        try:
            from database.supabase_client import db

            if db.client:
                db.insert_task_history(task, approach, result, False, created_at)
                supabase_success = True
            else:
                logger.warning(
                    "Supabase client is not initialized, fallback to SQLite only for failure data."
                )
        except Exception as e:
            logger.warning(f"Failed to insert failure to Supabase: {e}")
            if evolution_write_failures:
                evolution_write_failures.inc()

        # বাংলা মন্তব্য: যদি Supabase ক্লায়েন্ট ইনিশিয়ালাইজড থাকে কিন্তু রাইট ফেইল করে, তবেই কেবল সাগা রোলব্যাক (SQLite এভয়েড) করা হবে।
        # কিন্তু যদি ক্লায়েন্ট না থাকে (যেমন টেস্ট বা লোকাল রান), তবে লোকাল SQLite ডেটা স্টোর চলতে দেওয়া হবে।
        if not supabase_success and (db is not None and db.client):
            return {
                "stored": False,
                "error": "Supabase write failed. Saga rollback: skipping SQLite.",
            }

        conn = self._acquire_connection()
        try:
            # বাংলা মন্তব্য: P1+P3 Fix — INSERT OR IGNORE দিয়ে idempotency নিশ্চিত।
            conn.execute(
                "INSERT OR IGNORE INTO task_history (task, approach, result, success, created_at) VALUES (?, ?, ?, ?, ?)",
                (task, approach, result, 0, created_at),
            )
            conn.commit()
            return {
                "stored": True,
                "task": task,
                "approach": approach,
                "result": result,
            }
        except sqlite3.Error as db_err:
            logger.error(f"SQLite write failed after Supabase success for task '{task}': {db_err}")
            if evolution_write_failures:
                evolution_write_failures.inc()
            return {
                "stored": False,
                "partial": True,
                "supabase_ok": True,
                "sqlite_error": str(db_err),
                "task": task,
            }
        finally:
            self._release_connection(conn)
            # SELF-EVOLVE FIX: update FitnessEngine with failure to close the loop.
            if self.fitness_engine is not None:
                try:
                    self.fitness_engine.track_execution(
                        skill_name=approach, success=False, latency=0.0
                    )
                except Exception as fit_err:
                    logger.debug(f"fitness_engine.track_execution skipped: {fit_err}")

    def detect_repeated_failures(self, min_occurrences: int = 3) -> list[dict[str, Any]]:
        try:
            from database.supabase_client import db

            if db.client:
                failures = db.get_repeated_failures(min_occurrences=min_occurrences)
                if failures:
                    return failures
        except Exception as e:
            logger.warning(f"Failed to query repeated failures from Supabase: {e}")
            if evolution_write_failures:
                evolution_write_failures.inc()

        conn = self._acquire_connection()
        try:
            cursor = conn.execute(
                """
                SELECT task, approach, COUNT(*) as failures, MAX(created_at) as last_failed
                FROM task_history
                WHERE success = 0
                GROUP BY task, approach
                HAVING failures >= ?
                ORDER BY failures DESC
                """,
                (min_occurrences,),
            )
            return [
                {
                    "task": row[0],
                    "approach": row[1],
                    "failures": row[2],
                    "last_failed": row[3],
                }
                for row in cursor.fetchall()
            ]
        finally:
            self._release_connection(conn)

    def detect_underperforming_prompts(
        self, min_occurrences: int = 5, min_failure_rate: float = 0.5
    ) -> list[dict[str, Any]]:
        conn = self._acquire_connection()
        try:
            # বাংলা মন্তব্য: এখানে আমরা টাস্কের নাম (প্রম্পট) দ্বারা গ্রুপ করে ব্যর্থতার হার বিশ্লেষণ করছি।
            cursor = conn.execute(
                """
                SELECT
                    task,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_count,
                    COUNT(*) as total_count,
                    CAST(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) as failure_rate
                FROM task_history
                GROUP BY task
                HAVING total_count >= ? AND failure_rate >= ?
                ORDER BY failure_rate DESC, failed_count DESC
                """,
                (min_occurrences, min_failure_rate),
            )
            return [
                {
                    "task": row[0],
                    "failures": row[1],
                    "total": row[2],
                    "failure_rate": row[3],
                }
                for row in cursor.fetchall()
            ]
        finally:
            self._release_connection(conn)

    async def propose_prompt_optimization(
        self, original_prompt: str, failure_data: dict[str, Any]
    ) -> dict[str, Any]:
        task_hash = hashlib.sha256(original_prompt.encode()).hexdigest()

        # বাংলা মন্তব্য: LLM ব্যবহার করে উন্নত প্রম্পট তৈরির জন্য একটি প্রম্পট তৈরি করা হচ্ছে।
        optimization_prompt = f"""
System: You are a Prompt Optimization specialist. Your task is to rewrite a failing prompt to improve its success rate.

Original Prompt:
"{original_prompt}"

This prompt has a failure rate of {failure_data["failure_rate"]:.2%} after {failure_data["total"]} attempts.

Based on the prompt, rewrite it to be more precise, clear, and effective. Provide only the new prompt, without any explanation or extra text.
"""

        try:
            import asyncio

            response = await asyncio.to_thread(
                self.model_router.route_and_generate,
                optimization_prompt,
                task_type="analysis",
            )
            optimized_prompt = response.get("text", "").strip()

            if not optimized_prompt or optimized_prompt == original_prompt:
                return {"status": "no_change_generated"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

        created_at = datetime.now(UTC).isoformat()
        conn = self._acquire_connection()
        try:
            conn.execute(
                """
                INSERT INTO prompt_optimizations (task_hash, original_prompt, optimized_prompt, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_hash, original_prompt, optimized_prompt, created_at),
            )
            conn.commit()
            return {
                "task_hash": task_hash,
                "original_prompt": original_prompt,
                "optimized_prompt": optimized_prompt,
                "status": "proposed",
            }
        finally:
            self._release_connection(conn)

    async def propose_new_skill(self, pattern: str) -> dict[str, Any]:
        """
        বাংলা মন্তব্য: আগে এই মেথড একটা hardcoded boilerplate ক্লাস টেমপ্লেট জেনারেট করত
        (`return {'skill': ..., 'status': 'ok'}`) — যেটা আসলে কোনো প্যাটার্ন থেকে কিছুই শেখেনি,
        শুধু একটা fake placeholder ছিল, ইনপুট pattern যাই হোক না কেন একই কোড বেরোতো।
        এখন এটি প্রজেক্টে ইতিমধ্যে বিদ্যমান real self-evolution ইঞ্জিন AutoSkillCreator
        (core/evolution/auto_skill_creator.py) ব্যবহার করে — যেটা LLM দিয়ে আসল কোড জেনারেট করে,
        AST security sandbox-এ validate করে, তারপর সফল হলে লাইভ ডিপ্লয় করে।
        """
        skill_name = f"auto_{pattern.strip().replace(' ', '_').lower()}"
        created_at = datetime.now(UTC).isoformat()

        try:
            from core.self_evolution.auto_skill_creator import AutoSkillCreator

            creator = AutoSkillCreator()
            result = await creator.generate_and_deploy_skill(
                user_demand=pattern, skill_name=skill_name
            )
        except Exception as e:
            # বাংলা মন্তব্য: AutoSkillCreator instantiation/call ব্যর্থ হলেও পুরো daily evolution
            # run crash করবে না — failed status সহ রেকর্ড হয়ে পরের সাইকেলে retry হবে।
            logger.error(f"AutoSkillCreator failed for pattern '{pattern}': {e}")
            result = {"success": False, "error": str(e)}

        status = "deployed" if result.get("success") else "failed"
        generated_code = result.get("generated_code", "")
        error_note = result.get("error", "")

        try:
            from database.supabase_client import db

            if db.client:
                db.insert_skill_proposal(skill_name, pattern, generated_code, status, created_at)
        except Exception as e:
            logger.warning(f"Failed to insert skill proposal to Supabase: {e}")
            if evolution_write_failures:
                evolution_write_failures.inc()

        conn = self._acquire_connection()
        try:
            conn.execute(
                "INSERT INTO skill_proposals (skill_name, source_pattern, generated_code, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (skill_name, pattern, generated_code, status, created_at),
            )
            conn.commit()
            return {
                "skill_name": skill_name,
                "source_pattern": pattern,
                "status": status,
                "generated_code": generated_code,
                "generated_at": created_at,
                "error": error_note,
            }
        finally:
            self._release_connection(conn)

    def record_feedback(
        self, session_id: str, query: str, retrieved_chunks: str, user_rating: float
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        try:
            from database.supabase_client import db

            if db.client:
                db.insert_feedback(
                    session_id,
                    query,
                    retrieved_chunks,
                    user_rating,
                    created_at,
                )
        except Exception as e:
            logger.warning(f"Failed to insert feedback to Supabase: {e}")
            if evolution_write_failures:
                evolution_write_failures.inc()

        conn = self._acquire_connection()
        try:
            conn.execute(
                "INSERT INTO feedback_loop (session_id, query, retrieved_chunks, user_rating, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, query, retrieved_chunks, user_rating, created_at),
            )
            conn.commit()
            return {"recorded": True, "session_id": session_id, "rating": user_rating}
        finally:
            self._release_connection(conn)

    async def run_daily_evolution(self, task_history: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(task_history)
        successful = sum(1 for t in task_history if t.get("success"))
        success_rate = (successful / total * 100.0) if total > 0 else 100.0

        # Skill proposal based on repeated failures
        failures = self.detect_repeated_failures()
        failed_tasks = [f["task"] for f in failures]
        new_skills_proposed = []
        for task in failed_tasks:
            proposal = await self.propose_new_skill(task)
            new_skills_proposed.append(proposal["skill_name"])

        # Prompt optimization proposals
        underperforming_prompts = self.detect_underperforming_prompts()
        prompt_optimizations_proposed = []
        for prompt_data in underperforming_prompts:
            proposal = await self.propose_prompt_optimization(prompt_data["task"], prompt_data)
            if proposal.get("status") == "proposed":
                prompt_optimizations_proposed.append(proposal)

        optimizations = (
            ["Increase RAG context depth to reduce hallucination."] if success_rate < 95 else []
        )

        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_tasks_processed": total,
            "success_rate": success_rate,
            "repeated_failures": len(failures),
            "new_skills_proposed": new_skills_proposed,
            "prompt_optimizations_proposed": len(prompt_optimizations_proposed),
            "optimizations": optimizations,
        }
        try:
            from database.supabase_client import db

            if db.client:
                db.append_evolution_log(report)
        except Exception as e:
            logger.warning(f"Failed to append evolution log to Supabase: {e}")
            if evolution_write_failures:
                evolution_write_failures.inc()
        return report
