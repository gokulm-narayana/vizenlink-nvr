"""SQLAlchemy custom column types for VizenLink NVR."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import BigInteger, Dialect
from sqlalchemy.types import TypeDecorator

from vizenlink_nvr.timeutil import EPOCH, UTC


class UtcDateTime(TypeDecorator[datetime]):
    """Store aware UTC datetimes as integer microseconds since epoch."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Expected datetime, got {type(value).__name__}")
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("Naive datetime is not permitted; provide an aware datetime")
        return (value.astimezone(UTC) - EPOCH) // timedelta(microseconds=1)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return EPOCH + timedelta(microseconds=value)
