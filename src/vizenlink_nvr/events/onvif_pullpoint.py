"""ONVIF PullPoint event source client and XML notification parser (EVT-01, EVT-07, HLTH-09)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import defusedxml.ElementTree as Det

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.events import CameraEventBus
from vizenlink_nvr.camera.http import CameraHttp
from vizenlink_nvr.camera.onvif.soap import find_text, post_soap
from vizenlink_nvr.camera.result import Failure, Timeout
from vizenlink_nvr.events.source import EventSource, RawCameraEvent
from vizenlink_nvr.services.events import ClockSyncState
from vizenlink_nvr.timeutil import Clock, SystemClock, parse_iso_utc, utc_now

logger = logging.getLogger(__name__)

DRIFT_THRESHOLD_SECONDS = 5.0

PULLPOINT_SUBSCRIBE_XML = (
    '<tev:CreatePullPointSubscription xmlns:tev="http://www.onvif.org/ver10/events/wsdl">'
    "<tev:InitialTerminationTime>PT60S</tev:InitialTerminationTime>"
    "</tev:CreatePullPointSubscription>"
)

PULLPOINT_PULL_XML_TEMPLATE = (
    '<tev:PullMessages xmlns:tev="http://www.onvif.org/ver10/events/wsdl">'
    "<tev:Timeout>PT{timeout}S</tev:Timeout>"
    "<tev:MessageLimit>20</tev:MessageLimit>"
    "</tev:PullMessages>"
)

PULLPOINT_RENEW_XML_TEMPLATE = (
    '<wsnt:Renew xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">'
    "<wsnt:TerminationTime>PT{seconds}S</wsnt:TerminationTime>"
    "</wsnt:Renew>"
)

PULLPOINT_UNSUBSCRIBE_XML = '<wsnt:Unsubscribe xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"/>'


def parse_pullpoint_response_address(xml_text: str) -> str | None:
    """Extract subscription reference address from CreatePullPointSubscriptionResponse."""
    try:
        root = Det.fromstring(xml_text)
        addr = find_text(root, "Address")
        return addr if addr else None
    except Exception as exc:
        logger.warning("Failed to parse pullpoint address: %s", exc)
        return None


def parse_notification_messages(
    xml_text: str,
    camera_serial: str,
    now: datetime,
) -> list[RawCameraEvent]:
    """Parse wsnt:NotificationMessage elements from PullMessages response XML."""
    events: list[RawCameraEvent] = []
    try:
        root = Det.fromstring(xml_text)
    except Exception as exc:
        logger.warning("Malformed XML in PullMessages response: %s", exc)
        return events

    # Find all NotificationMessage nodes
    for msg in root.iter():
        local = msg.tag.split("}")[-1] if "}" in msg.tag else msg.tag
        if local != "NotificationMessage":
            continue

        topic = find_text(msg, "Topic")
        if not topic:
            continue

        # Look for UtcTime attribute in Message element
        event_time: datetime | None = None
        data_items: dict[str, Any] = {}

        for child in msg.iter():
            child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_local == "Message":
                utc_attr = child.attrib.get("UtcTime")
                if utc_attr:
                    try:
                        event_time = parse_iso_utc(utc_attr)
                    except Exception:
                        event_time = None
            elif child_local == "SimpleItem":
                name = child.attrib.get("Name")
                val = child.attrib.get("Value")
                if name and val is not None:
                    data_items[name] = val

        # Evaluate camera clock drift (HLTH-09 / EVT-07)
        drift_sec: float | None = None
        clock_state = ClockSyncState.SYNCED

        if event_time is not None:
            drift_sec = abs((event_time - now).total_seconds())
            if drift_sec > DRIFT_THRESHOLD_SECONDS:
                clock_state = ClockSyncState.UNCERTAIN
                # Re-stamp with NVR UTC time (EVT-07)
                event_time = now
        else:
            event_time = now

        events.append(
            RawCameraEvent(
                camera_serial=camera_serial,
                topic=topic,
                utc_time=event_time,
                data=data_items,
                source_name="onvif_pullpoint",
                clock_drift_seconds=drift_sec,
                clock_sync_state=clock_state,
            )
        )

    return events


class OnvifPullPointSource(EventSource):
    """ONVIF PullPoint subscription client implementation."""

    def __init__(
        self,
        camera_serial: str,
        conn: CameraConnection,
        http: CameraHttp | None = None,
        clock: Clock | None = None,
        event_service_path: str = "/onvif/event_service",
    ) -> None:
        self.camera_serial = camera_serial
        self.conn = conn
        self.http = http or CameraHttp(CameraEventBus())
        self.clock = clock or SystemClock()
        self.event_service_path = event_service_path
        self.subscription_url: str | None = None
        self.subscription_path: str | None = None

    async def subscribe(self) -> str:
        """Create PullPoint subscription and set subscription path."""
        res = await post_soap(
            http=self.http,
            conn=self.conn,
            path=self.event_service_path,
            body_xml=PULLPOINT_SUBSCRIBE_XML,
            clock=self.clock,
            timeout=8.0,
        )
        if isinstance(res, (Failure, Timeout)):
            raise RuntimeError(f"PullPoint subscription failed on {self.camera_serial}: {res}")

        addr = parse_pullpoint_response_address(res.value)
        if not addr:
            raise RuntimeError(f"Camera {self.camera_serial} did not return PullPoint Address in response")

        self.subscription_url = addr
        # Extract path component from URI for subsequent requests
        parsed = urlparse(addr)
        self.subscription_path = parsed.path
        if parsed.query:
            self.subscription_path += f"?{parsed.query}"

        return addr

    async def poll(self, timeout_seconds: float = 5.0) -> list[RawCameraEvent]:
        """Poll PullMessages from the active subscription."""
        if not self.subscription_path:
            raise RuntimeError("Cannot poll before calling subscribe()")

        body_xml = PULLPOINT_PULL_XML_TEMPLATE.format(timeout=int(timeout_seconds))
        res = await post_soap(
            http=self.http,
            conn=self.conn,
            path=self.subscription_path,
            body_xml=body_xml,
            clock=self.clock,
            timeout=timeout_seconds + 3.0,
        )
        if isinstance(res, Timeout):
            return []  # Normal long-polling timeout
        if isinstance(res, Failure):
            raise RuntimeError(f"PullMessages failed on {self.camera_serial}: {res.reason}")

        now = utc_now()
        return parse_notification_messages(res.value, self.camera_serial, now)

    async def renew(self, seconds: int = 60) -> bool:
        """Renew subscription termination time."""
        if not self.subscription_path:
            return False

        body_xml = PULLPOINT_RENEW_XML_TEMPLATE.format(seconds=seconds)
        res = await post_soap(
            http=self.http,
            conn=self.conn,
            path=self.subscription_path,
            body_xml=body_xml,
            clock=self.clock,
            timeout=6.0,
        )
        return not isinstance(res, (Failure, Timeout))

    async def unsubscribe(self) -> None:
        """Unsubscribe cleanly from camera."""
        if not self.subscription_path:
            return

        try:
            await post_soap(
                http=self.http,
                conn=self.conn,
                path=self.subscription_path,
                body_xml=PULLPOINT_UNSUBSCRIBE_XML,
                clock=self.clock,
                timeout=4.0,
            )
        except Exception as exc:
            logger.debug("Clean unsubscribe failed on %s: %s", self.camera_serial, exc)
        finally:
            self.subscription_path = None
            self.subscription_url = None
