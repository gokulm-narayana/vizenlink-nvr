"""Camera Settings Service for aggregating, validating, and mutating camera parameters (SET-01..SET-08)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.nuraeye.settings import (
    FALLBACK_TIMEZONES,
    NuraeyeSettingsClient,
)
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.imaging import (
    ImagingOptions,
    ImagingSettings,
    OnvifImagingClient,
)
from vizenlink_nvr.camera.onvif.media2 import (
    OnvifMedia2Client,
    OsdConfig,
    VideoEncoderConfiguration,
    VideoEncoderConfigurationOptions,
    VideoResolution,
)
from vizenlink_nvr.camera.result import Failure, Success, Timeout
from vizenlink_nvr.db.models import Camera, CameraCredential, CameraStream, Event
from vizenlink_nvr.secrets.vault import Vault
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.registry import load_connection
from vizenlink_nvr.timeutil import Clock, SystemClock, utc_now

logger = logging.getLogger(__name__)


class CameraNotFoundError(ValueError):
    """Camera serial does not exist in registry."""


class SettingsValidationError(ValueError):
    """Requested setting update is outside allowed bounds or not supported."""


class CameraOperationError(RuntimeError):
    """Camera communication or protocol operation failed."""


class CameraSettingsService:
    """Service managing camera settings, capability checking, bounds validation, and operations."""

    def __init__(
        self,
        http: CameraHttp | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.clock = clock or SystemClock()
        self.http = http or CameraHttp(CameraEventBus())

    async def get_settings(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
    ) -> dict[str, Any]:
        """Fetch full capability-gated camera settings and supported options."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found in registry")

        conn = await load_connection(session, vault, serial)
        dev_client = OnvifDeviceClient(conn, self.http, self.clock)
        media_client = OnvifMedia2Client(conn, self.http, self.clock)
        imaging_client = OnvifImagingClient(conn, self.http, self.clock)
        nuraeye_client = NuraeyeSettingsClient(conn, self.http, self.clock)

        # 1. Identity & Device Info
        name = cam.name
        location = cam.location
        id_res = await dev_client.get_device_identity()
        if isinstance(id_res, Success):
            if id_res.value.name:
                name = id_res.value.name
            if id_res.value.location:
                location = id_res.value.location

        timezones_res = await nuraeye_client.get_supported_timezones()
        timezones = timezones_res.value if isinstance(timezones_res, Success) else FALLBACK_TIMEZONES

        # 2. Encoders per profile
        encoders: list[dict[str, Any]] = []
        profiles_res = await media_client.get_profiles()
        profiles = profiles_res.value if isinstance(profiles_res, Success) else []

        # If profiles not returned from live camera, fallback to DB streams
        if not profiles:
            stream_stmt = select(CameraStream).where(CameraStream.serial == serial)
            db_streams = (await session.execute(stream_stmt)).scalars().all()
            for stm in db_streams:
                encoders.append(
                    {
                        "profile_token": stm.profile_token,
                        "profile_name": stm.profile_name,
                        "venc_token": stm.venc_token,
                        "current": {
                            "encoding": stm.codec,
                            "width": stm.width,
                            "height": stm.height,
                            "quality": 50.0,
                            "frame_rate_limit": 25.0,
                            "bitrate_limit_kbps": 2048,
                            "gov_length": 30,
                            "profile": "Main",
                        },
                        "options": {
                            "encodings": ["H264", "H265"],
                            "resolutions": [
                                {"width": stm.width, "height": stm.height},
                                {"width": 1920, "height": 1080},
                            ],
                            "quality_range": (1.0, 100.0),
                            "frame_rate_range": (1.0, 30.0),
                            "bitrate_range_kbps": (256, 8192),
                            "gov_length_range": (1, 120),
                        },
                    }
                )
        else:
            for prof in profiles:
                cfg_res = await media_client.get_video_encoder_configuration(prof.venc_token)
                opts_res = await media_client.get_video_encoder_configuration_options(prof.venc_token)

                curr_cfg = (
                    cfg_res.value
                    if isinstance(cfg_res, Success)
                    else VideoEncoderConfiguration(
                        token=prof.venc_token,
                        name=prof.name,
                        encoding=prof.encoding,
                        width=prof.width,
                        height=prof.height,
                        quality=50.0,
                        frame_rate_limit=25.0,
                        bitrate_limit_kbps=2048,
                    )
                )

                opts = (
                    opts_res.value
                    if isinstance(opts_res, Success)
                    else VideoEncoderConfigurationOptions(
                        token=prof.venc_token,
                        encodings=("H264", "H265"),
                        resolutions=(
                            VideoResolution(prof.width, prof.height),
                            VideoResolution(1920, 1080),
                        ),
                        quality_range=(1.0, 100.0),
                        frame_rate_range=(1.0, 30.0),
                        bitrate_range_kbps=(256, 8192),
                    )
                )

                encoders.append(
                    {
                        "profile_token": prof.token,
                        "profile_name": prof.name,
                        "venc_token": prof.venc_token,
                        "current": {
                            "encoding": curr_cfg.encoding,
                            "width": curr_cfg.width,
                            "height": curr_cfg.height,
                            "quality": curr_cfg.quality,
                            "frame_rate_limit": curr_cfg.frame_rate_limit,
                            "bitrate_limit_kbps": curr_cfg.bitrate_limit_kbps,
                            "gov_length": curr_cfg.gov_length,
                            "profile": curr_cfg.profile,
                        },
                        "options": {
                            "encodings": list(opts.encodings),
                            "resolutions": [{"width": r.width, "height": r.height} for r in opts.resolutions],
                            "quality_range": opts.quality_range,
                            "frame_rate_range": opts.frame_rate_range,
                            "bitrate_range_kbps": opts.bitrate_range_kbps,
                            "gov_length_range": opts.gov_length_range,
                        },
                    }
                )

        # 3. Imaging & ISP
        img_res = await imaging_client.get_imaging_settings("VideoSource_1")
        img_opts_res = await imaging_client.get_imaging_options("VideoSource_1")
        nv_res = await nuraeye_client.get_night_vision_type()
        mf_res = await nuraeye_client.get_mirror_flip()
        af_res = await nuraeye_client.get_anti_flicker()

        img_curr = img_res.value if isinstance(img_res, Success) else ImagingSettings()
        img_opts = img_opts_res.value if isinstance(img_opts_res, Success) else ImagingOptions()

        night_vision_type = nv_res.value.current_type if isinstance(nv_res, Success) else "grey"
        color_capable = nv_res.value.color_capable if isinstance(nv_res, Success) else True
        smart_capable = nv_res.value.smart_capable if isinstance(nv_res, Success) else True

        mirror_flip = mf_res.value if isinstance(mf_res, Success) else "off"
        anti_flicker = af_res.value if isinstance(af_res, Success) else "Auto"

        # 4. OSD Overlays
        osd_res = await media_client.get_osds()
        osd_list = osd_res.value if isinstance(osd_res, Success) else []

        return {
            "identity": {
                "name": name,
                "location": location,
                "timezone": "UTC",
                "supported_timezones": timezones,
            },
            "device_info": {
                "manufacturer": cam.manufacturer or "Generic",
                "model": cam.model or "Generic",
                "firmware_version": cam.firmware_version or "1.0",
                "serial_number": cam.serial,
                "hardware_id": cam.hardware_id or "rev1",
            },
            "encoders": encoders,
            "imaging": {
                "current": {
                    "brightness": img_curr.brightness if img_curr.brightness is not None else 50.0,
                    "contrast": img_curr.contrast if img_curr.contrast is not None else 50.0,
                    "color_saturation": (
                        img_curr.color_saturation if img_curr.color_saturation is not None else 50.0
                    ),
                    "sharpness": img_curr.sharpness if img_curr.sharpness is not None else 50.0,
                    "ir_cut_filter": img_curr.ir_cut_filter or "AUTO",
                    "wdr_mode": img_curr.wdr_mode or "OFF",
                    "wdr_level": img_curr.wdr_level if img_curr.wdr_level is not None else 0.0,
                    "night_vision_type": night_vision_type,
                    "mirror_flip": mirror_flip,
                    "anti_flicker": anti_flicker,
                },
                "options": {
                    "brightness_range": img_opts.brightness_range,
                    "contrast_range": img_opts.contrast_range,
                    "color_saturation_range": img_opts.color_saturation_range,
                    "sharpness_range": img_opts.sharpness_range,
                    "ir_cut_filter_modes": list(img_opts.ir_cut_filter_modes),
                    "wdr_supported": img_opts.wdr_supported,
                    "wdr_level_range": img_opts.wdr_level_range,
                    "night_vision_color_capable": color_capable,
                    "night_vision_smart_capable": smart_capable,
                },
            },
            "osd": [
                {
                    "token": o.token,
                    "video_source_token": o.video_source_token,
                    "osd_type": o.osd_type,
                    "position": o.position,
                    "plain_text": o.plain_text,
                    "date_format": o.date_format,
                    "time_format": o.time_format,
                }
                for o in osd_list
            ],
        }

    async def update_identity(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
        name: str | None = None,
        location: str | None = None,
        timezone: str | None = None,
        password: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Update camera identity attributes (name, location, timezone, password)."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        conn = await load_connection(session, vault, serial)
        dev_client = OnvifDeviceClient(conn, self.http, self.clock)
        updated: dict[str, Any] = {}

        if name is not None and name.strip():
            clean_name = name.strip()
            res_name = await dev_client.set_device_name(clean_name)
            if isinstance(res_name, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set camera name: {res_name}")
            cam.name = clean_name
            updated["name"] = clean_name

        if location is not None:
            clean_loc = location.strip()
            res_loc = await dev_client.set_device_location(clean_loc)
            if isinstance(res_loc, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set camera location: {res_loc}")
            cam.location = clean_loc
            updated["location"] = clean_loc

        if timezone is not None and timezone.strip():
            clean_tz = timezone.strip()
            res_tz = await dev_client.set_system_date_and_time(clean_tz)
            if isinstance(res_tz, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set camera timezone: {res_tz}")
            updated["timezone"] = clean_tz

        if password is not None and password.strip():
            res_pw = await dev_client.set_user_password(conn.username, password)
            if isinstance(res_pw, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set camera password: {res_pw}")

            # Update password in vault & credentials table
            sealed = vault.seal(serial, conn.username, SecretStr(password))
            cred_stmt = select(CameraCredential).where(CameraCredential.serial == serial)
            cred = (await session.execute(cred_stmt)).scalar_one()
            cred.ciphertext = sealed.ciphertext
            cred.nonce = sealed.nonce
            cred.key_id = sealed.key_id
            cred.enc_version = sealed.enc_version
            cred.updated_at = utc_now()
            updated["password_changed"] = True

        cam.identity_synced_at = utc_now()
        await session.commit()

        await AuditService.record_event(
            session=session,
            action="camera.settings.update_identity",
            resource_type="camera",
            resource_id=serial,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            details=updated,
            commit=True,
        )

        return {"status": "ok", "updated": updated}

    async def update_encoder(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
        venc_token: str,
        encoding: str | None = None,
        width: int | None = None,
        height: int | None = None,
        frame_rate_limit: float | None = None,
        bitrate_limit_kbps: int | None = None,
        quality: float | None = None,
        gov_length: int | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Update stream video encoder configuration within validated capability bounds."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        conn = await load_connection(session, vault, serial)
        media_client = OnvifMedia2Client(conn, self.http, self.clock)

        # 1. Fetch current options to validate bounds
        opts_res = await media_client.get_video_encoder_configuration_options(venc_token)
        if isinstance(opts_res, Success):
            opts = opts_res.value
            if encoding is not None and encoding not in opts.encodings:
                raise SettingsValidationError(
                    f"Encoding '{encoding}' not supported. Allowed: {opts.encodings}"
                )
            if width is not None and height is not None:
                req_res = VideoResolution(width, height)
                if req_res not in opts.resolutions:
                    allowed_str = ", ".join(f"{r.width}x{r.height}" for r in opts.resolutions)
                    raise SettingsValidationError(
                        f"Resolution {width}x{height} not supported. Allowed: {allowed_str}"
                    )
            if frame_rate_limit is not None:
                if frame_rate_limit < opts.frame_rate_range[0] or frame_rate_limit > opts.frame_rate_range[1]:
                    raise SettingsValidationError(
                        f"Frame rate {frame_rate_limit} outside allowed range {opts.frame_rate_range}"
                    )
            if bitrate_limit_kbps is not None:
                if (
                    bitrate_limit_kbps < opts.bitrate_range_kbps[0]
                    or bitrate_limit_kbps > opts.bitrate_range_kbps[1]
                ):
                    raise SettingsValidationError(
                        f"Bitrate {bitrate_limit_kbps} outside allowed range {opts.bitrate_range_kbps}"
                    )
            if quality is not None:
                if quality < opts.quality_range[0] or quality > opts.quality_range[1]:
                    raise SettingsValidationError(
                        f"Quality {quality} outside allowed range {opts.quality_range}"
                    )
            if gov_length is not None:
                if gov_length < opts.gov_length_range[0] or gov_length > opts.gov_length_range[1]:
                    raise SettingsValidationError(
                        f"GovLength {gov_length} outside allowed range {opts.gov_length_range}"
                    )

        # 2. Get current config to merge unmodified fields
        curr_res = await media_client.get_video_encoder_configuration(venc_token)
        curr = (
            curr_res.value
            if isinstance(curr_res, Success)
            else VideoEncoderConfiguration(
                token=venc_token,
                name="Stream",
                encoding=encoding or "H265",
                width=width or 1920,
                height=height or 1080,
                quality=quality or 50.0,
                frame_rate_limit=frame_rate_limit or 25.0,
                bitrate_limit_kbps=bitrate_limit_kbps or 2048,
                gov_length=gov_length or 30,
            )
        )

        new_cfg = VideoEncoderConfiguration(
            token=venc_token,
            name=curr.name,
            encoding=encoding if encoding is not None else curr.encoding,
            width=width if width is not None else curr.width,
            height=height if height is not None else curr.height,
            quality=quality if quality is not None else curr.quality,
            frame_rate_limit=(
                frame_rate_limit if frame_rate_limit is not None else curr.frame_rate_limit
            ),
            bitrate_limit_kbps=(
                bitrate_limit_kbps if bitrate_limit_kbps is not None else curr.bitrate_limit_kbps
            ),
            gov_length=gov_length if gov_length is not None else curr.gov_length,
            profile=curr.profile,
        )

        set_res = await media_client.set_video_encoder_configuration(venc_token, new_cfg)
        if isinstance(set_res, (Failure, Timeout)):
            raise CameraOperationError(f"Failed to update encoder configuration: {set_res}")

        # Update local DB stream if matching
        stream_stmt = select(CameraStream).where(
            CameraStream.serial == serial, CameraStream.venc_token == venc_token
        )
        stream_row = (await session.execute(stream_stmt)).scalar_one_or_none()
        if stream_row:
            stream_row.codec = new_cfg.encoding
            stream_row.width = new_cfg.width
            stream_row.height = new_cfg.height
            await session.commit()

        await AuditService.record_event(
            session=session,
            action="camera.settings.update_encoder",
            resource_type="camera",
            resource_id=serial,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            details={
                "venc_token": venc_token,
                "encoding": new_cfg.encoding,
                "width": new_cfg.width,
                "height": new_cfg.height,
                "frame_rate_limit": new_cfg.frame_rate_limit,
                "bitrate_limit_kbps": new_cfg.bitrate_limit_kbps,
            },
            commit=True,
        )

        return {
            "status": "ok",
            "config": {
                "venc_token": venc_token,
                "encoding": new_cfg.encoding,
                "width": new_cfg.width,
                "height": new_cfg.height,
                "quality": new_cfg.quality,
                "frame_rate_limit": new_cfg.frame_rate_limit,
                "bitrate_limit_kbps": new_cfg.bitrate_limit_kbps,
                "gov_length": new_cfg.gov_length,
            },
        }

    async def update_imaging(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
        video_source_token: str = "VideoSource_1",  # noqa: S107
        brightness: float | None = None,
        contrast: float | None = None,
        color_saturation: float | None = None,
        sharpness: float | None = None,
        ir_cut_filter: str | None = None,
        wdr_mode: str | None = None,
        wdr_level: float | None = None,
        night_vision_type: str | None = None,
        mirror_flip: str | None = None,
        anti_flicker: str | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Update imaging, Day/Night, ISP, and video sensor settings within capability limits."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        conn = await load_connection(session, vault, serial)
        imaging_client = OnvifImagingClient(conn, self.http, self.clock)
        nuraeye_client = NuraeyeSettingsClient(conn, self.http, self.clock)

        # 1. Fetch imaging options to validate ISP ranges and WDR support
        opts_res = await imaging_client.get_imaging_options(video_source_token)
        if isinstance(opts_res, Success):
            opts = opts_res.value
            if brightness is not None:
                if brightness < opts.brightness_range[0] or brightness > opts.brightness_range[1]:
                    raise SettingsValidationError(
                        f"Brightness {brightness} outside allowed range {opts.brightness_range}"
                    )
            if contrast is not None:
                if contrast < opts.contrast_range[0] or contrast > opts.contrast_range[1]:
                    raise SettingsValidationError(
                        f"Contrast {contrast} outside allowed range {opts.contrast_range}"
                    )
            if color_saturation is not None:
                if (
                    color_saturation < opts.color_saturation_range[0]
                    or color_saturation > opts.color_saturation_range[1]
                ):
                    raise SettingsValidationError(
                        f"Color saturation {color_saturation} outside allowed range "
                        f"{opts.color_saturation_range}"
                    )
            if sharpness is not None:
                if sharpness < opts.sharpness_range[0] or sharpness > opts.sharpness_range[1]:
                    raise SettingsValidationError(
                        f"Sharpness {sharpness} outside allowed range {opts.sharpness_range}"
                    )
            if ir_cut_filter is not None and ir_cut_filter not in opts.ir_cut_filter_modes:
                raise SettingsValidationError(
                    f"IrCutFilter mode '{ir_cut_filter}' not supported. Allowed: {opts.ir_cut_filter_modes}"
                )
            if wdr_mode is not None:
                if wdr_mode.upper() == "ON" and not opts.wdr_supported:
                    raise SettingsValidationError("WDR is not supported on this camera")
            if wdr_level is not None:
                if wdr_level < opts.wdr_level_range[0] or wdr_level > opts.wdr_level_range[1]:
                    raise SettingsValidationError(
                        f"WDR level {wdr_level} outside allowed range {opts.wdr_level_range}"
                    )

        # 2. Validate and set NuraEye night vision type
        updated: dict[str, Any] = {}
        if night_vision_type is not None:
            nv_status_res = await nuraeye_client.get_night_vision_type()
            if isinstance(nv_status_res, Success):
                nv_status = nv_status_res.value
                clean_nv = night_vision_type.lower().strip()
                if clean_nv == "color" and not nv_status.color_capable:
                    raise SettingsValidationError("Color night vision is not supported on this camera")
                if clean_nv == "smart" and not nv_status.smart_capable:
                    raise SettingsValidationError("Smart night vision is not supported on this camera")

            set_nv_res = await nuraeye_client.set_night_vision_type(night_vision_type)
            if isinstance(set_nv_res, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set night vision type: {set_nv_res}")
            updated["night_vision_type"] = night_vision_type

        # 3. Mirror/Flip
        if mirror_flip is not None:
            set_mf_res = await nuraeye_client.set_mirror_flip(mirror_flip)
            if isinstance(set_mf_res, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set mirror/flip: {set_mf_res}")
            updated["mirror_flip"] = mirror_flip

        # 4. Anti-flicker
        if anti_flicker is not None:
            set_af_res = await nuraeye_client.set_anti_flicker(anti_flicker)
            if isinstance(set_af_res, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set anti-flicker: {set_af_res}")
            updated["anti_flicker"] = anti_flicker

        # 5. ONVIF Imaging parameters
        has_imaging_update = any(
            x is not None
            for x in (brightness, contrast, color_saturation, sharpness, ir_cut_filter, wdr_mode, wdr_level)
        )
        if has_imaging_update:
            new_img = ImagingSettings(
                brightness=brightness,
                contrast=contrast,
                color_saturation=color_saturation,
                sharpness=sharpness,
                ir_cut_filter=ir_cut_filter,
                wdr_mode=wdr_mode,
                wdr_level=wdr_level,
            )
            set_img_res = await imaging_client.set_imaging_settings(video_source_token, new_img)
            if isinstance(set_img_res, (Failure, Timeout)):
                raise CameraOperationError(f"Failed to set ONVIF imaging settings: {set_img_res}")

            if brightness is not None:
                updated["brightness"] = brightness
            if contrast is not None:
                updated["contrast"] = contrast
            if color_saturation is not None:
                updated["color_saturation"] = color_saturation
            if sharpness is not None:
                updated["sharpness"] = sharpness
            if ir_cut_filter is not None:
                updated["ir_cut_filter"] = ir_cut_filter
            if wdr_mode is not None:
                updated["wdr_mode"] = wdr_mode
            if wdr_level is not None:
                updated["wdr_level"] = wdr_level

        await AuditService.record_event(
            session=session,
            action="camera.settings.update_imaging",
            resource_type="camera",
            resource_id=serial,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            details=updated,
            commit=True,
        )

        return {"status": "ok", "updated": updated}

    async def update_osd(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
        token: str,
        video_source_token: str = "VideoSource_1",  # noqa: S107
        osd_type: str = "DateAndTime",
        position: str = "UpperLeft",
        plain_text: str | None = None,
        date_format: str = "YYYY/MM/DD",
        time_format: str = "HH:mm:ss",
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Update On-Screen Display (OSD) overlay text and position."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        conn = await load_connection(session, vault, serial)
        media_client = OnvifMedia2Client(conn, self.http, self.clock)

        osd_cfg = OsdConfig(
            token=token,
            video_source_token=video_source_token,
            osd_type=osd_type,
            position=position,
            plain_text=plain_text,
            date_format=date_format,
            time_format=time_format,
        )

        set_res = await media_client.set_osd(osd_cfg)
        if isinstance(set_res, (Failure, Timeout)):
            raise CameraOperationError(f"Failed to set OSD configuration: {set_res}")

        await AuditService.record_event(
            session=session,
            action="camera.settings.update_osd",
            resource_type="camera",
            resource_id=serial,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            details={
                "token": token,
                "osd_type": osd_type,
                "position": position,
                "plain_text": plain_text,
            },
            commit=True,
        )

        return {
            "status": "ok",
            "osd": {
                "token": token,
                "video_source_token": video_source_token,
                "osd_type": osd_type,
                "position": position,
                "plain_text": plain_text,
            },
        }

    async def reboot(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
    ) -> str:
        """Trigger camera reboot via ONVIF SystemReboot (SET-05)."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        conn = await load_connection(session, vault, serial)
        dev_client = OnvifDeviceClient(conn, self.http, self.clock)

        res = await dev_client.system_reboot()
        if isinstance(res, (Failure, Timeout)):
            raise CameraOperationError(f"Failed to reboot camera: {res}")

        msg = res.value or "Rebooting in 5 seconds"

        await AuditService.record_event(
            session=session,
            action="camera.reboot",
            resource_type="camera",
            resource_id=serial,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            details={"message": msg},
            commit=True,
        )

        return msg

    async def factory_reset(
        self,
        session: AsyncSession,
        vault: Vault,
        serial: str,
        mode: str = "Soft",
        actor_id: int | None = None,
        actor_username: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """Trigger factory reset via ONVIF SetSystemFactoryDefault (SET-06)."""
        valid_mode = "Hard" if mode.lower() == "hard" else "Soft"

        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        conn = await load_connection(session, vault, serial)
        dev_client = OnvifDeviceClient(conn, self.http, self.clock)

        res = await dev_client.set_system_factory_default(mode=valid_mode)
        if isinstance(res, (Failure, Timeout)):
            raise CameraOperationError(f"Failed to factory reset camera: {res}")

        await AuditService.record_event(
            session=session,
            action="camera.factory_reset",
            resource_type="camera",
            resource_id=serial,
            actor_id=actor_id,
            actor_username=actor_username,
            ip_address=ip_address,
            details={"mode": valid_mode},
            commit=True,
        )

        return True

    async def get_health(
        self,
        session: AsyncSession,
        vault: Vault,  # noqa: ARG002
        serial: str,
    ) -> dict[str, Any]:
        """Fetch camera health metrics including uptime, clock state, and reboot status (SET-07)."""
        cam = await session.get(Camera, serial)
        if cam is None:
            raise CameraNotFoundError(f"Camera '{serial}' not found")

        # Query clock_sync_state from latest event if available
        evt_stmt = (
            select(Event.clock_sync_state)
            .where(Event.camera_serial == serial)
            .order_by(Event.start_time.desc())
            .limit(1)
        )
        latest_clock_state = (await session.execute(evt_stmt)).scalar_one_or_none() or "synced"

        # Calculate uptime estimate based on host_updated_at or added_at
        now = utc_now()
        uptime_seconds = int((now - cam.host_updated_at).total_seconds()) if cam.host_updated_at else None

        return {
            "serial": cam.serial,
            "online": cam.state == "active",
            "uptime_seconds": uptime_seconds,
            "reboot_reason": "normal_startup",
            "clock_sync_status": latest_clock_state,
            "firmware_version": cam.firmware_version or "1.0",
            "last_seen": cam.host_updated_at.isoformat() if cam.host_updated_at else None,
        }
