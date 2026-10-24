import uuid

from sqlalchemy import types

try:
    from uuid6 import uuid7
except ImportError:
    from uuid import uuid4 as uuid7


class UUIDv7(types.TypeDecorator):
    """
    Custom SQLAlchemy type for UUIDv7 (Time-ordered UUIDs).
    """

    impl = types.Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        # Ensure it is a uuid.UUID instance if backend expects it
        if isinstance(value, str):
            return uuid.UUID(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value


def generate_uuid7():
    """Generates a UUIDv7."""
    return uuid7()
