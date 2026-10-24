import logging
import ssl

from core.config import settings

logger = logging.getLogger(__name__)


def build_supabase_ssl_context() -> ssl.SSLContext:
    """Builds a shared SSLContext for Supabase connections (asyncpg and SQLAlchemy).

    Loads the explicit Supabase CA certificate (SUPABASE_DB_CA_CERT) if provided,
    falling back to certifi as a base trust store. This enforces verify-full SSL.
    """
    import certifi

    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    supabase_ca = settings.supabase_db_ca_cert
    if supabase_ca:
        try:
            ctx.load_verify_locations(cadata=supabase_ca)
            logger.info("✅ Loaded explicit Supabase CA certificate for Verify-Full SSL.")
        except Exception as e:
            logger.error(f"❌ Failed to load explicit Supabase CA certificate: {e}")
    else:
        logger.warning(
            "⚠️ SUPABASE_DB_CA_CERT is not set. Relying only on certifi for SSL verification."
        )

    return ctx
