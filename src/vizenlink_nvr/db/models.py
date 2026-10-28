"""Database ORM models for VizenLink NVR."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, LargeBinary, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


class Camera(Base):
    """Registered camera identity and configuration."""

    __tablename__ = "camera"

    serial: Mapped[str] = mapped_column(Text, primary_key=True)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    https_port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)
    mac: Mapped[str] = mapped_column(Text, nullable=False, default="")
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    group_tag: Mapped[str] = mapped_column(Text, nullable=False, default="")
    manufacturer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    firmware_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hardware_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tls_fingerprint_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    camera_id_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    added_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    host_updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    identity_synced_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    credential: Mapped["CameraCredential"] = relationship(
        "CameraCredential",
        back_populates="camera",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    capabilities: Mapped["CameraCapabilitiesRow"] = relationship(
        "CameraCapabilitiesRow",
        back_populates="camera",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    streams: Mapped[list["CameraStream"]] = relationship(
        "CameraStream",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'auth_failed', 'tls_changed', 'unreachable')",
            name="ck_camera_state",
        ),
    )


class CameraCredential(Base):
    """Encrypted credential envelope bound to camera serial."""

    __tablename__ = "camera_credential"

    serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    enc_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="credential")


class CameraCapabilitiesRow(Base):
    """Cached raw JSON capabilities discovered from camera."""

    __tablename__ = "camera_capabilities"

    serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        primary_key=True,
    )
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    probed_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    firmware_version_at_probe: Mapped[str] = mapped_column(Text, nullable=False)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="capabilities")


class CameraStream(Base):
    """Configured video stream endpoints for camera (main and sub)."""

    __tablename__ = "camera_stream"

    serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)
    profile_token: Mapped[str] = mapped_column(Text, nullable=False)
    profile_name: Mapped[str] = mapped_column(Text, nullable=False)
    venc_token: Mapped[str] = mapped_column(Text, nullable=False)
    codec: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    transport: Mapped[str] = mapped_column(Text, nullable=False)
    scheme: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    sub_is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    probed_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="streams")

    __table_args__ = (
        CheckConstraint("role IN ('main', 'sub')", name="ck_camera_stream_role"),
        CheckConstraint("source IN ('nuraeye', 'onvif_fallback')", name="ck_camera_stream_source"),
    )
