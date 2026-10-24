"""Ecosystem multi-user auth — stdlib only (ROADMAP §50, ecosystem plan §3).

বাংলা: সম্পূর্ণ Python stdlib দিয়ে তৈরি — কোনো bcrypt / PyJWT dependency নেই।
- Password hashing: ``hashlib.pbkdf2_hmac("sha256", ...)`` (PBKDF2-HMAC-SHA256)
- JWT: HS256-style token signed via ``hmac.new(...).digest()`` + base64url
- Storage: SQLite tables ``ecosystem_users`` / ``ecosystem_sessions`` (same DB as other modules)
- Secret: env ``ECOSYSTEM_JWT_SECRET`` → fallback to auto-generated stable file
  at ``backend/data/.jwt_secret`` (created on first run).

Module exports a singleton ``get_user_store()`` + ``get_session_store()`` so the
FastAPI app can resolve them via ``Depends``.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import ensure_columns, get_conn, get_db_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths + config
# ---------------------------------------------------------------------------

_DATA_DIR: Path = get_db_path().parent
_SECRET_FILE: Path = _DATA_DIR / ".jwt_secret"

_DEFAULT_TTL = int(os.getenv("ECOSYSTEM_TOKEN_TTL_SECONDS", "86400") or 86400)


def _resolve_secret() -> str:
    """Return HS256 secret from env or a stable auto-generated file."""
    env_secret = os.getenv("ECOSYSTEM_JWT_SECRET", "").strip()
    if env_secret:
        return env_secret
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text().strip()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_urlsafe(48)
    _SECRET_FILE.write_text(new_secret)
    # Best-effort chmod — fine if it fails (e.g. Windows).
    try:
        _SECRET_FILE.chmod(0o600)
    except OSError as chmod_err:
        logger.debug(f"Could not chmod secret file: {chmod_err}")
    return new_secret


# ---------------------------------------------------------------------------
# Enum + Pydantic models
# ---------------------------------------------------------------------------


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


class User(BaseModel):
    """User record (password_hash is intentionally excluded from API responses)."""

    user_id: str
    email: str
    name: str = ""
    role: UserRole = UserRole.USER
    tenant_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_login_at: str | None = None


class Session(BaseModel):
    """Stored session row — companion to a single JWT."""

    session_id: str
    user_id: str
    issued_at: str
    expires_at: str
    user_agent: str = ""
    ip_address: str = ""
    user: User | None = None  # joined for convenience


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16
_HASH_BYTES = 32
_PREFIX = "pbkdf2_sha256$"


def hash_password(plain: str) -> str:
    """Return ``pbkdf2_sha256$<iter>$<salt_b64>$<hash_b64>``."""
    if not plain:
        raise ValueError("password cannot be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, _PBKDF2_ITERATIONS, _HASH_BYTES)
    return f"{_PREFIX}{_PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(plain: str, stored: str) -> bool:
    """Constant-time verify a password against a stored PBKDF2 hash."""
    if not stored or not stored.startswith(_PREFIX):
        return False
    try:
        _, iter_s, salt_b64, hash_b64 = stored.split("$", 3)
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    computed = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(computed, expected)


# ---------------------------------------------------------------------------
# JWT (HS256-style) — stdlib only
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


class JWTError(Exception):
    """Raised when a JWT cannot be decoded or is invalid."""


def issue_jwt(
    session_id: str,
    user_id: str,
    role: UserRole,
    expires_at: int,
    *,
    issued_at: int | None = None,
    secret: str | None = None,
) -> str:
    """Encode a compact HS256-style JWT (header.payload.signature)."""
    header = {"alg": "HS256", "typ": "JWT"}
    iat = issued_at if issued_at is not None else int(time.time())
    payload = {
        "sub": user_id,
        "sid": session_id,
        "role": str(role.value if isinstance(role, UserRole) else role),
        "iat": iat,
        "exp": expires_at,
    }
    header_b = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_b = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_b}.{payload_b}".encode("ascii")
    key = (secret or _resolve_secret()).encode("utf-8")
    sig = hmac.new(key, signing_input, hashlib.sha256).digest()
    return f"{header_b}.{payload_b}.{_b64url_encode(sig)}"


def decode_jwt(token: str, *, secret: str | None = None) -> dict[str, Any]:
    """Decode + verify signature + exp. Raises ``JWTError`` on any failure."""
    if not token:
        raise JWTError("empty token")
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("malformed token")
    header_b, payload_b, sig_b = parts
    signing_input = f"{header_b}.{payload_b}".encode("ascii")
    key = (secret or _resolve_secret()).encode("utf-8")
    expected = hmac.new(key, signing_input, hashlib.sha256).digest()
    try:
        provided = _b64url_decode(sig_b)
    except Exception as exc:  # pragma: no cover — defensive
        raise JWTError("bad signature encoding") from exc
    if not hmac.compare_digest(expected, provided):
        raise JWTError("signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b).decode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise JWTError("bad payload encoding") from exc
    if not isinstance(payload, dict):
        raise JWTError("payload not an object")
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        raise JWTError("token expired")
    return payload


# ---------------------------------------------------------------------------
# UserStore
# ---------------------------------------------------------------------------


class UserExistsError(Exception):
    """Raised when registering an email that already exists."""


class UserNotFoundError(Exception):
    """Raised when a user_id is unknown."""


class UserStore:
    """SQLite-backed user store. ``ecosystem_users`` table (single shared DB)."""

    TABLE = "ecosystem_users"

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(f"""CREATE TABLE IF NOT EXISTS {self.TABLE} (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT DEFAULT '',
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                tenant_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT)""")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_email ON {self.TABLE}(email)"
            )
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_role  ON {self.TABLE}(role)")
            conn.commit()

    # -- core API ---------------------------------------------------------

    def register(self, email: str, password: str, name: str = "") -> User:
        """Create a user. First user ever created becomes ADMIN."""
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("invalid email")
        if not password:
            raise ValueError("password cannot be empty")
        with get_conn() as conn:
            existing = conn.execute(
                f"SELECT user_id FROM {self.TABLE} WHERE email=?", (email,)
            ).fetchone()
            if existing:
                raise UserExistsError(f"email already registered: {email}")
            count = conn.execute(f"SELECT COUNT(*) AS n FROM {self.TABLE}").fetchone()["n"]
            role = UserRole.ADMIN if count == 0 else UserRole.USER
            now = datetime.now(UTC).isoformat()
            user_id = f"usr-{uuid.uuid4().hex[:16]}"
            conn.execute(
                f"INSERT INTO {self.TABLE} "
                "(user_id, email, name, password_hash, role, tenant_id, "
                "created_at, updated_at, last_login_at) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL)",
                (
                    user_id,
                    email,
                    name.strip(),
                    hash_password(password),
                    role.value,
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(user_id)  # type: ignore[return-value]

    def authenticate(self, email: str, password: str) -> User | None:
        email = (email or "").strip().lower()
        if not email or not password:
            return None
        with get_conn() as conn:
            r = conn.execute(f"SELECT * FROM {self.TABLE} WHERE email=?", (email,)).fetchone()
        if not r:
            # Always run a dummy verify to keep timing roughly constant.
            verify_password(password, hash_password("dummy"))
            return None
        if not verify_password(password, r["password_hash"]):
            return None
        return self._from(r)

    def get(self, user_id: str) -> User | None:
        with get_conn() as conn:
            r = conn.execute(f"SELECT * FROM {self.TABLE} WHERE user_id=?", (user_id,)).fetchone()
        return self._from(r) if r else None

    def get_by_email(self, email: str) -> User | None:
        email = (email or "").strip().lower()
        with get_conn() as conn:
            r = conn.execute(f"SELECT * FROM {self.TABLE} WHERE email=?", (email,)).fetchone()
        return self._from(r) if r else None

    def list_users(self) -> list[User]:
        with get_conn() as conn:
            rows = conn.execute(f"SELECT * FROM {self.TABLE} ORDER BY created_at ASC").fetchall()
        return [self._from(r) for r in rows]

    def set_role(self, user_id: str, role: UserRole) -> User:
        if not isinstance(role, UserRole):
            try:
                role = UserRole(role)
            except ValueError as exc:
                raise ValueError(f"invalid role: {role}") from exc
        now = datetime.now(UTC).isoformat()
        with get_conn() as conn:
            cur = conn.execute(
                f"UPDATE {self.TABLE} SET role=?, updated_at=? WHERE user_id=?",
                (role.value, now, user_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise UserNotFoundError(user_id)
        return self.get(user_id)  # type: ignore[return-value]

    def touch_last_login(self, user_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET last_login_at=? WHERE user_id=?",
                (now, user_id),
            )
            conn.commit()

    # -- internals --------------------------------------------------------

    @staticmethod
    def _from(r: sqlite3.Row | Any) -> User:
        return User(
            user_id=r["user_id"],
            email=r["email"],
            name=r["name"] or "",
            role=UserRole(r["role"]),
            tenant_id=r["tenant_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            last_login_at=r["last_login_at"],
        )


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """SQLite-backed session store (one row per issued JWT)."""

    TABLE = "ecosystem_sessions"

    def __init__(self, *, user_store: UserStore | None = None) -> None:
        self._ensure_schema()
        self._users = user_store

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(f"""CREATE TABLE IF NOT EXISTS {self.TABLE} (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES ecosystem_users(user_id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                user_agent TEXT DEFAULT '',
                ip_address TEXT DEFAULT '')""")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_user ON {self.TABLE}(user_id)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_exp ON {self.TABLE}(expires_at)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_token ON {self.TABLE}(token_hash)"
            )
            conn.commit()

    # -- core API ---------------------------------------------------------

    def issue(
        self,
        user: User,
        *,
        ua: str = "",
        ip: str = "",
        ttl: int = _DEFAULT_TTL,
    ) -> tuple[str, Session]:
        """Create a session row + signed JWT. Returns ``(jwt_str, session)``."""
        if ttl <= 0:
            ttl = _DEFAULT_TTL
        session_id = f"ses-{uuid.uuid4().hex[:24]}"
        now = int(time.time())
        expires_at = now + ttl
        token = issue_jwt(session_id, user.user_id, user.role, expires_at)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        issued_iso = datetime.fromtimestamp(now, UTC).isoformat()
        expires_iso = datetime.fromtimestamp(expires_at, UTC).isoformat()
        with get_conn() as conn:
            conn.execute(
                f"INSERT INTO {self.TABLE} "
                "(session_id, user_id, token_hash, issued_at, expires_at, user_agent, ip_address) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, user.user_id, token_hash, issued_iso, expires_iso, ua or "", ip or ""),
            )
            conn.commit()
        return token, Session(
            session_id=session_id,
            user_id=user.user_id,
            issued_at=issued_iso,
            expires_at=expires_iso,
            user_agent=ua or "",
            ip_address=ip or "",
            user=user,
        )

    def validate(self, jwt_str: str) -> Session | None:
        """Validate JWT signature + expiry + DB existence. Returns None on failure."""
        try:
            payload = decode_jwt(jwt_str)
        except JWTError:
            return None
        session_id = payload.get("sid")
        if not isinstance(session_id, str):
            return None
        token_hash = hashlib.sha256(jwt_str.encode("utf-8")).hexdigest()
        with get_conn() as conn:
            r = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE session_id=? AND token_hash=?",
                (session_id, token_hash),
            ).fetchone()
            if not r:
                return None
            # Expiry already checked in decode_jwt, but double-check the stored ISO row too.
            try:
                exp_dt = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                exp_dt = datetime.now(UTC)
            if exp_dt < datetime.now(UTC):
                # Stale — purge quietly.
                conn.execute(f"DELETE FROM {self.TABLE} WHERE session_id=?", (session_id,))
                conn.commit()
                return None
            user_id = r["user_id"]
            user_row = conn.execute(
                "SELECT * FROM ecosystem_users WHERE user_id=?", (user_id,)
            ).fetchone()
        if not user_row:
            return None
        user = UserStore._from(user_row)
        return Session(
            session_id=session_id,
            user_id=user_id,
            issued_at=r["issued_at"],
            expires_at=r["expires_at"],
            user_agent=r["user_agent"] or "",
            ip_address=r["ip_address"] or "",
            user=user,
        )

    def revoke(self, session_id: str) -> bool:
        with get_conn() as conn:
            cur = conn.execute(f"DELETE FROM {self.TABLE} WHERE session_id=?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    def revoke_by_token(self, jwt_str: str) -> bool:
        try:
            payload = decode_jwt(jwt_str)
        except JWTError:
            return False
        session_id = payload.get("sid")
        if not isinstance(session_id, str):
            return False
        token_hash = hashlib.sha256(jwt_str.encode("utf-8")).hexdigest()
        with get_conn() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.TABLE} WHERE session_id=? AND token_hash=?",
                (session_id, token_hash),
            )
            conn.commit()
            return cur.rowcount > 0

    def revoke_all_for_user(self, user_id: str) -> int:
        with get_conn() as conn:
            cur = conn.execute(f"DELETE FROM {self.TABLE} WHERE user_id=?", (user_id,))
            conn.commit()
            return cur.rowcount

    def refresh(self, jwt_str: str, *, ttl: int = _DEFAULT_TTL) -> tuple[str, Session] | None:
        """Rotate ``sessions.exp`` for the current session and issue a new JWT.

        The old token's row is deleted; a new row with a new session_id is created.
        Returns ``None`` if the token is invalid / expired / revoked.
        """
        sess = self.validate(jwt_str)
        if not sess or not sess.user:
            return None
        # Delete the old session row.
        self.revoke(sess.session_id)
        # Issue a fresh one.
        return self.issue(sess.user, ua=sess.user_agent, ip=sess.ip_address, ttl=ttl)


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_user_store: UserStore | None = None
_session_store: SessionStore | None = None


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def ensure_users_schema() -> None:
    """Idempotent — called from ``standalone_app`` lifespan to create tables."""
    get_user_store()
    get_session_store()


__all__ = [
    "UserRole",
    "User",
    "Session",
    "UserStore",
    "SessionStore",
    "UserExistsError",
    "UserNotFoundError",
    "JWTError",
    "hash_password",
    "verify_password",
    "issue_jwt",
    "decode_jwt",
    "get_user_store",
    "get_session_store",
    "ensure_users_schema",
]
