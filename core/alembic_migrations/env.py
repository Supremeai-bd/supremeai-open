import logging
import os
import sys
from logging.config import fileConfig

# বাংলা মন্তব্য: প্রোজেক্টের রুট পাথ যুক্ত করা হচ্ছে যাতে core.config মডিউলটি ইম্পোর্ট করা যায়
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import engine_from_config, pool

# Import all models to ensure they are registered with Base.metadata before autogenerate
from alembic import context
from core.config import settings
from models.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

import socket
import urllib.parse

logger = logging.getLogger(__name__)

# বাংলা মন্তব্য: মাইগ্রেশনের জন্য ডিরেক্ট রাইটার (SUPABASE_DATABASE_URL_WRITER) অগ্রাধিকার পাবে,
# কারণ PgBouncer ট্রানজ্যাকশন পুলে DDL / মাইগ্রেশন লকিং স্টেটমেন্ট প্রত্যাখ্যাত হতে পারে।
raw_migration_url = (
    os.getenv("SUPABASE_DATABASE_URL_WRITER")
    or getattr(settings, "database_url", None)
    or getattr(settings, "supabase_database_url", None)
)
if not raw_migration_url:
    raise RuntimeError(
        "Database URL is required for Alembic. Set SUPABASE_DATABASE_URL_WRITER "
        "or the canonical database URL setting before running migrations."
    )


def _resolve_reachable_url(url: str) -> str:
    """Ensure endpoint is reachable over IPv4 (GitHub Actions runners lack IPv6 egress).

    If the endpoint is a Supabase direct host (db.<ref>.supabase.co) that cannot be
    resolved over IPv4, fallback to Supavisor Pooler on port 5432 (Session mode),
    which supports IPv4 and standard DDL / Alembic migrations.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
        hostname = parsed.hostname or ""
        if "supabase.co" in hostname:
            can_ipv4 = False
            try:
                res = socket.getaddrinfo(hostname, parsed.port or 5432, socket.AF_INET)
                if res:
                    can_ipv4 = True
            except OSError as exc:
                # DNS resolution failure is expected on IPv6-only hosts — the
                # pooler fallback below is exactly the remedy. Kept observable
                # (Constitution REL-002) without failing the migration run.
                logger.warning(
                    "IPv4 resolution failed for %s (%s); trying Supavisor pooler fallback",
                    hostname,
                    exc,
                )
                can_ipv4 = False

            if not can_ipv4:
                parts = hostname.split(".")
                ref = parts[1] if len(parts) > 1 else ""
                user = parsed.username or "postgres"
                if ref and not user.endswith(f".{ref}"):
                    user = f"{user}.{ref}"
                pooler_host = os.getenv(
                    "SUPABASE_POOLER_HOST", "aws-0-ap-southeast-1.pooler.supabase.com"
                )
                netloc = (
                    f"{user}:{parsed.password}@{pooler_host}:5432"
                    if parsed.password
                    else f"{user}@{pooler_host}:5432"
                )
                return urllib.parse.urlunsplit(
                    (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
                )
    except Exception:
        # REL-001 (Constitution): never swallow silently — log with traceback
        # and fall back to the caller-provided URL. The fallback preserves the
        # pre-fix behavior (migrations proceed with the raw URL); the log line
        # makes the degradation visible in CI and production logs.
        logger.exception(
            "Supabase reachability probe failed; migrations will use the URL as provided"
        )
    return url


migration_url = _resolve_reachable_url(raw_migration_url)
config.set_main_option("sqlalchemy.url", migration_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _sync_psycopg2_ssl_args() -> dict:
    """psycopg2-compatible SSL args mirroring build_supabase_ssl_context().

    বাংলা: psycopg2-তে Python SSLContext অবজেক্ট পাঠানো যায় না — connect_args-এর
    অজানা key DSN option হিসেবে ঢুকে যায় → `invalid dsn: invalid connection
    option "sslcontext"` (Production Deploy/Migration Gate fail, 2026-09-20)।
    asyncpg-এর `sslcontext`-এর psycopg2-সমতুল্য হলো file-based `sslrootcert`
    + `sslmode=verify-full` (host verify সহ)।

    Trust priority (db_ssl-এর মতোই):
    ১. SUPABASE_DB_CA_CERT (vault/CI env) — সত্যিকারের verify-full। Supabase
       pooler-এর সার্ট public CA-সাইন করা না, তাই certifi-verify অবশ্যই ব্যর্থ হয়
       (`SSL error: certificate verify failed`) — তাই certifi fallback নেই।
    ২. CA অনুপস্থিত হলে `sslmode=require` — এনক্রিপশন নিশ্চিত, verify ছাড়া
       (CI-র one-shot migration-এর জন্য গ্রহণযোগ্য ডিগ্রেডেশন; runtime-এ সবসময়
       explicit CA সেট থাকে)।
    """
    import logging
    import tempfile

    ca_pem = getattr(settings, "supabase_db_ca_cert", None) or ""
    is_valid_pem = "-----BEGIN CERTIFICATE-----" in ca_pem and "-----END CERTIFICATE-----" in ca_pem
    if is_valid_pem:
        fd, ca_path = tempfile.mkstemp(prefix="supabase-ca-", suffix=".pem")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(ca_pem)
        return {"sslmode": "verify-full", "sslrootcert": ca_path}

    if ca_pem:
        logging.getLogger(__name__).warning(
            "SUPABASE_DB_CA_CERT is set but not a valid PEM block — "
            "falling back to sslmode=require for the migration connection."
        )
    else:
        logging.getLogger(__name__).warning(
            "SUPABASE_DB_CA_CERT not set for alembic — using sslmode=require "
            "(encrypted, unverified). Set the CA secret for verify-full."
        )
    return {"sslmode": "require"}


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connect_args = {}
    migration_url = config.get_main_option("sqlalchemy.url") or ""
    if "postgresql" in migration_url:
        connect_args["connect_timeout"] = 10
        if "asyncpg" in migration_url:
            # asyncpg accepts a Python SSLContext object directly.
            from core.db_ssl import build_supabase_ssl_context

            connect_args["sslcontext"] = build_supabase_ssl_context()
        else:
            # psycopg2 (sync alembic driver): file-based SSL args only.
            connect_args.update(_sync_psycopg2_ssl_args())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
