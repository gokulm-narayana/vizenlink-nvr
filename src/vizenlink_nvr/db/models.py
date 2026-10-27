"""Database ORM models for VizenLink NVR."""

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from vizenlink_nvr.db.types import UtcDateTime


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    type_annotation_map = {
        datetime: UtcDateTime,
    }


class AppSetting(Base):
    """Key-value setting storage with JSON text values."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
