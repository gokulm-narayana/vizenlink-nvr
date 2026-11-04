"""Database ORM models for VizenLink NVR."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from vizenlink_nvr.db.types import UtcDateTime
from vizenlink_nvr.timeutil import utc_now


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
    recording_settings: Mapped["RecordingSettings | None"] = relationship(
        "RecordingSettings",
        back_populates="camera",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    segments: Mapped[list["Segment"]] = relationship(
        "Segment",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    user_permissions: Mapped[list["UserCameraPermission"]] = relationship(
        "UserCameraPermission",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    outages: Mapped[list["CameraOutage"]] = relationship(
        "CameraOutage",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events: Mapped[list["Event"]] = relationship(
        "Event",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    subscription: Mapped["EventSubscription | None"] = relationship(
        "EventSubscription",
        back_populates="camera",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    gallery_items: Mapped[list["GalleryItem"]] = relationship(
        "GalleryItem",
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


class RecordingSettings(Base):
    """Per-camera recording configuration and retention policies."""

    __tablename__ = "recording_settings"

    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="continuous")
    schedule_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    audio_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_max_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pre_roll_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    post_roll_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="recording_settings")

    __table_args__ = (
        CheckConstraint(
            "mode IN ('continuous', 'scheduled', 'event', 'off')",
            name="ck_recording_settings_mode",
        ),
    )


class Segment(Base):
    """Indexed recording segment stored on disk."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stream_type: Mapped[str] = mapped_column(Text, nullable=False, default="main")
    file_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    start_time: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    is_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="segments")

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'missing', 'truncated')",
            name="ck_segment_status",
        ),
    )


class StorageSettings(Base):
    """System-wide recording storage path and safety thresholds."""

    __tablename__ = "storage_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    allow_system_disk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reserve_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10 * 1024 * 1024 * 1024)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


class User(Base):
    """Local user account with role-based access control."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cognito_sub: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    permissions: Mapped[list["UserCameraPermission"]] = relationship(
        "UserCameraPermission",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    gallery_items: Mapped[list["GalleryItem"]] = relationship(
        "GalleryItem",
        back_populates="user",
    )
    paired_devices: Mapped[list["PairedDevice"]] = relationship(
        "PairedDevice",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    qr_pairing_sessions: Mapped[list["QRPairingSession"]] = relationship(
        "QRPairingSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'operator', 'viewer')",
            name="ck_user_role",
        ),
    )


class UserCameraPermission(Base):
    """Explicit camera access grant for restricted users."""

    __tablename__ = "user_camera_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="permissions")
    camera: Mapped["Camera"] = relationship("Camera", back_populates="user_permissions")

    __table_args__ = (
        UniqueConstraint("user_id", "camera_serial", name="uq_user_camera_permission"),
    )


class Session(Base):
    """Authenticated user web session token."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    last_active_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class AuditLog(Base):
    """Append-only audit trail for administrative and operational events."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class CameraOutage(Base):
    """Historical camera disconnection and recovery record."""

    __tablename__ = "camera_outages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="outages")


class Event(Base):
    """Camera trigger event record."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="onvif_pullpoint")
    start_time: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    end_time: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    clock_sync_state: Mapped[str] = mapped_column(Text, nullable=False, default="synced")
    raw_topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="events")

    __table_args__ = (
        CheckConstraint(
            "clock_sync_state IN ('synced', 'uncertain', 'drift_detected')",
            name="ck_event_clock_sync_state",
        ),
    )


class EventSubscription(Base):
    """Camera event subscription state and health metrics."""

    __tablename__ = "event_subscriptions"

    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False, default="idle")
    subscription_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_renewed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    clock_drift_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="subscription")

    __table_args__ = (
        CheckConstraint(
            "state IN ('idle', 'subscribing', 'active', 'reconnecting', 'failed')",
            name="ck_event_subscription_state",
        ),
    )


class GalleryItem(Base):
    """Media gallery record for snapshots, manual clips, and exported clips."""

    __tablename__ = "gallery_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(Text, nullable=False)
    camera_serial: Mapped[str] = mapped_column(
        Text,
        ForeignKey("camera.serial", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="gallery_items")
    user: Mapped["User | None"] = relationship("User", back_populates="gallery_items")

    __table_args__ = (
        CheckConstraint(
            "item_type IN ('snapshot', 'manual_clip', 'export_clip')",
            name="ck_gallery_item_type",
        ),
        Index("ix_gallery_items_camera_captured", "camera_serial", "captured_at"),
        Index("ix_gallery_items_type", "item_type"),
    )


class PairedDevice(Base):
    """Registered mobile device paired to an NVR user account."""

    __tablename__ = "paired_devices"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    device_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    paired_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    access_token_expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    refresh_token_expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="paired_devices")


class QRPairingSession(Base):
    """Ephemeral pairing session for mobile QR code enrollment."""

    __tablename__ = "qr_pairing_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pairing_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    claimed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="qr_pairing_sessions")





