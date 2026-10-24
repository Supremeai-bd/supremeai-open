# FILE_PATH: backend/core/pgbouncer_pool.py

import asyncio
import os
import ssl
from contextlib import asynccontextmanager

from core.logging_config import logger

try:
    import asyncpg
    from asyncpg.connection import Connection
except ImportError:
    asyncpg = None  # type: ignore[assignment]
    Connection = None  # type: ignore[assignment]


# বাংলা মন্তব্য: User ও Admin — দুই আলাদা Render instance একই Supabase PgBouncer পুলে
# কানেক্ট করে। database/session.py-এর SQLAlchemy engine ইতিমধ্যে SERVICE_ROLE অনুযায়ী
# pool ভাগ করে (user: 2+13=15, admin: 1+2=3), কিন্তু এই raw-asyncpg pool আগে হার্ডকোডেড
# min=5/max=30 ব্যবহার করত — উভয় role-এর instance যোগ করলে ৩০+১৫=৪৫ বা তার বেশি
# কানেকশন claim করতে পারত, যা Supabase ফ্রি-টিয়ার PgBouncer pool exhaust করতে পারে।
# একই role-aware bracket এখানে পুনরায় ব্যবহার করা হলো, যোগফল হিসাব করে (এই pool +
# session.py engine) instance প্রতি মোট কানেকশন যুক্তিসঙ্গত রাখা হয়েছে।
_ROLE_POOL_BRACKETS: dict[str, tuple[int, int]] = {
    "admin": (1, 2),  # low-traffic internal panel
    "user": (1, 5),  # high-traffic client-facing — trimmed from (3, 12) to
    # reduce per-instance connection count/memory on Render Free tier (512 MiB).
    # Combined with SQLAlchemy engine's own pool (session.py: 2+13), the previous
    # bracket allowed up to 2+13+3+12=30 simultaneous connections per instance —
    # unnecessarily high and a contributor to memory pressure. Root-cause fix for
    # DuplicatePreparedStatementError (statement_cache_size=0) already applied
    # separately, so this is now a safe, isolated resource-sizing change.
}


def _role_pool_sizes() -> tuple[int, int]:
    role = os.getenv("SERVICE_ROLE", "user").lower()
    return _ROLE_POOL_BRACKETS.get(role, _ROLE_POOL_BRACKETS["user"])


def _supabase_ssl_context() -> ssl.SSLContext:
    from core.db_ssl import build_supabase_ssl_context

    return build_supabase_ssl_context()


def _random_name_connection_class():
    """asyncpg-এর ডিফল্ট sequential prepared-statement নামের বদলে UUID-based random
    নাম — PgBouncer transaction pooling-এ নাম-সংঘর্ষ এড়াতে (দেখুন
    database/session.py-এর একই fix, একই root cause বিশ্লেষণ)।"""
    from uuid import uuid4

    class RandomNameConnection(Connection):
        def _get_unique_id(self, prefix: str) -> str:
            return f"__asyncpg_{prefix}_{uuid4().hex}__"

    return RandomNameConnection


class PgBouncerConnectionPool:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool = None

    async def connect(self):
        """Initializes the asyncpg connection pool, sized by SERVICE_ROLE."""
        min_size, max_size = _role_pool_sizes()
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=min_size,
            max_size=max_size,
            max_inactive_connection_lifetime=300,
            # বাংলা মন্তব্য: Supabase (PgBouncer pooler 6543 এবং direct 5432 — উভয়ই) কানেকশনের
            # জন্য TLS/SSL বাধ্যতামূলক। asyncpg ডিফল্টভাবে SSL চালু করে না, তাই স্পষ্টভাবে SSL কনটেক্সট
            # দিতে হবে — নাহলে 'db: down' / PRODUCTION DB UNAVAILABLE হবে। psycopg2 পাথের সাথে সামঞ্জস্য
            # রেখে sslmode=require-এর সমতুল্য কনটেক্সট ব্যবহার করা হয়েছে (এনক্রিপ্ট করে, CA ভেরিফাই করে না)।
            ssl=_supabase_ssl_context(),
            # বাংলা মন্তব্য: PgBouncer (transaction/statement mode) এর সাথে সামঞ্জস্যের জন্য
            # statement_cache_size=0 — asyncpg-এর FAQ অনুযায়ী prepared statement cache
            # বন্ধ করলে 'DuplicatePreparedStatementError' পুরোপুরি প্রতিরোধ যায়।
            # (নোট: asyncpg 0.30.0-এ prepared_statement_name_func প্যারামিন
            # নেই; এটি create_pool()-এর **connect_kwargs হয়ে connect()-এ গিয়ে
            # TypeError সৃষ্টি করে। statement_cache_size=0 যথেষ্ট।)
            statement_cache_size=0,
            connection_class=_random_name_connection_class(),
            command_timeout=30,
        )
        logger.info(
            f"PgBouncer connection pool initialized (min_size={min_size}, max_size={max_size}, role={os.getenv('SERVICE_ROLE', 'user')})."
        )

    async def acquire(self) -> Connection:
        """Acquires a connection from the pool."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized. Call connect() first.")
        return await self._pool.acquire()

    async def release(self, conn: Connection):
        """Releases a connection back to the pool."""
        if self._pool:
            await self._pool.release(conn)

    @asynccontextmanager
    async def connection(self):
        """Async context manager to safely acquire and release a connection."""
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)

    # asyncpg.Pool এর মেথডগুলোকে সরাসরি কল করার জন্য proxy মেথডগুলো যুক্ত করা হলো
    # যাতে কোডবেসে pool.execute() বা pool.fetch() কল করলে কোনো Attribute Error না দেয়।
    async def execute(self, query: str, *args, **kwargs):
        """Executes a query using the pool."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized.")
        return await self._pool.execute(query, *args, **kwargs)

    async def fetch(self, query: str, *args, **kwargs):
        """Fetches rows using the pool."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized.")
        return await self._pool.fetch(query, *args, **kwargs)

    async def fetchrow(self, query: str, *args, **kwargs):
        """Fetches a single row using the pool."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized.")
        return await self._pool.fetchrow(query, *args, **kwargs)

    async def fetchval(self, query: str, *args, **kwargs):
        """Fetches a single value using the pool."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized.")
        return await self._pool.fetchval(query, *args, **kwargs)

    async def close(self):
        """Closes the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("PgBouncer connection pool closed.")
            self._pool = None


_db_pool_instance = None
_pool_lock = asyncio.Lock()


async def get_db_pool() -> PgBouncerConnectionPool:
    """Provides a singleton instance of the PgBouncerConnectionPool.

    RuntimeError is raised if the pool has not been initialized yet.
    """
    if _db_pool_instance is None:
        raise RuntimeError(
            "DB pool was accessed before app startup initialized it. Call init_db_pool() explicitly during the FastAPI lifespan."
        )
    return _db_pool_instance


async def init_db_pool(dsn: str) -> PgBouncerConnectionPool:
    """Initializes the DB pool singleton and returns it."""
    global _db_pool_instance
    async with _pool_lock:
        if _db_pool_instance is None:
            pool = PgBouncerConnectionPool(dsn)
            await pool.connect()
            _db_pool_instance = pool
        return _db_pool_instance


async def get_db_pool_with_retry(
    max_retries: int = 3, initial_delay: float = 1.0
) -> PgBouncerConnectionPool:
    """ডাটাবেস কানেকশন পুল প্রারম্ভে এক্সপোনেনশিয়াল ব্যাক-অফ রিট্রাই। (Bangla: DB Pool Retry)"""
    for attempt in range(1, max_retries + 1):
        try:
            return await get_db_pool()
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"❌ [DB Pool] Max connection retries reached: {e}")
                raise e from e
            delay = initial_delay * (2 ** (attempt - 1))
            logger.warning(
                f"⚠️ [DB Pool] Connection attempt {attempt} failed. Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)
    raise RuntimeError("Failed to acquire DB pool after retries.")


async def dispose_db_pool() -> None:
    """ডাটাবেস কানেকশন পুল মেমরি ও কানেকশন লিক রোধে সার্ভার বন্ধের সময় পুল ডিসপোজাল মেথড। (Bangla: DB Pool Teardown)"""
    global _db_pool_instance
    async with _pool_lock:
        if _db_pool_instance is not None:
            await _db_pool_instance.close()
            _db_pool_instance = None
            logger.info("✅ [DB Pool] Database connection pool successfully disposed and freed.")


async def run_cpu_bound_task_safely(func, *args, **kwargs):
    """সিঙ্ক্রোনাস বা ভারী সিপিইউ টাস্ককে মেইন ইভেন্ট লুপ আটকানো ছাড়া অফলোড করা। (Bangla: Thread offloader)"""
    return await asyncio.to_thread(func, *args, **kwargs)
