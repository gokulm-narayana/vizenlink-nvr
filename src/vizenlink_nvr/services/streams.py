"""Stream selection and resolution for camera video profiles."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.nuraeye.live_stream_uri import MOBILE_ONLY_PROFILE_TOKEN
from vizenlink_nvr.camera.onvif.media2 import MediaProfile, OnvifMedia2Client
from vizenlink_nvr.camera.result import Failure, FailureKind, Timeout


@dataclass(frozen=True)
class StreamRecord:
    """Resolved stream connection and encoder metadata."""

    role: str
    profile_token: str
    profile_name: str
    venc_token: str
    codec: str
    width: int
    height: int
    transport: str
    scheme: str
    port: int
    path: str
    source: str
    sub_is_main: bool


@dataclass(frozen=True)
class StreamSelection:
    """Selected main and sub profile candidates."""

    main: MediaProfile
    sub: MediaProfile
    sub_is_main: bool


def natural_token_key(token: str) -> list[int | str]:
    """Sort key splitting alphanumeric strings to natural order (Profile_2 < Profile_10)."""
    parts = re.split(r"(\d+)", token)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def select_streams(profiles: list[MediaProfile]) -> StreamSelection | None:
    """Select main and sub streams: largest resolution main, next sub, never Profile_3."""
    eligible = [p for p in profiles if p.token != MOBILE_ONLY_PROFILE_TOKEN and p.width > 0 and p.height > 0]
    if not eligible:
        return None

    # Sort descending by resolution (width * height), then ascending by natural token name
    eligible.sort(key=lambda p: (-(p.width * p.height), natural_token_key(p.token)))

    main = eligible[0]
    if len(eligible) >= 2:
        sub = eligible[1]
        sub_is_main = False
    else:
        sub = main
        sub_is_main = True

    return StreamSelection(main=main, sub=sub, sub_is_main=sub_is_main)


async def resolve_streams(
    nuraeye: NuraeyeClient,
    media2: OnvifMedia2Client,
    timeout: float = 8.0,
) -> list[StreamRecord] | Failure | Timeout:
    """Resolve stream endpoints for main and sub roles via REST and ONVIF fallback."""
    profiles_res = await media2.get_profiles(timeout=timeout)
    if isinstance(profiles_res, (Failure, Timeout)):
        return profiles_res

    selection = select_streams(profiles_res.value)
    if selection is None:
        return Failure(
            kind=FailureKind.BAD_RESPONSE,
            reason="No usable video streams found on camera",
        )

    records: list[StreamRecord] = []
    targets = [("main", selection.main), ("sub", selection.sub)]

    for role, profile in targets:
        sub_is_main = selection.sub_is_main if role == "sub" else False

        live_res = await nuraeye.get_live_stream_uri(profile.token, timeout=timeout)
        if isinstance(live_res, (Failure, Timeout)):
            return live_res

        live_uri = live_res.value
        if live_uri.transport == "webrtc":
            # WebRTC mode fallback to ONVIF Media2 GetStreamUri (D-23, LST-04)
            uri_res = await media2.get_stream_uri(profile.token, timeout=timeout)
            if isinstance(uri_res, (Failure, Timeout)):
                return uri_res

            parsed = urlsplit(uri_res.value)
            scheme = parsed.scheme.lower() if parsed.scheme else "rtsps"
            port = parsed.port if parsed.port is not None else 554
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            transport = "rtsp"
            source = "onvif_fallback"
        else:
            parsed = urlsplit(live_uri.url)
            scheme = parsed.scheme.lower() if parsed.scheme else "rtsps"
            port = parsed.port if parsed.port is not None else 554
            path = parsed.path
            if parsed.query:
                path = f"{path}?{parsed.query}"
            transport = live_uri.transport
            source = "nuraeye"

        records.append(
            StreamRecord(
                role=role,
                profile_token=profile.token,
                profile_name=profile.name,
                venc_token=profile.venc_token,
                codec=profile.encoding,
                width=profile.width,
                height=profile.height,
                transport=transport,
                scheme=scheme,
                port=port,
                path=path,
                source=source,
                sub_is_main=sub_is_main,
            )
        )

    return records
