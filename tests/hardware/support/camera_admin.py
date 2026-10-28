"""Administrative helper operations for real-camera mutation and recovery (D-20, D-24)."""

import asyncio
import time
from typing import Literal

from vizenlink_nvr.camera.connection import CameraConnection
from vizenlink_nvr.camera.http import CameraHttp, camera_ssl_context
from vizenlink_nvr.camera.onvif.device import DEVICE_SERVICE_PATH
from vizenlink_nvr.camera.onvif.soap import post_soap
from vizenlink_nvr.camera.result import CameraResult
from vizenlink_nvr.timeutil import SystemClock


async def soft_factory_reset(
    conn: CameraConnection,
    http: CameraHttp | None = None,
    timeout: float = 30.0,
) -> CameraResult[str]:
    """Execute ONVIF SetSystemFactoryDefault with FactoryDefault 'Soft' (D-20, D-24)."""
    if http is None:
        http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    body = (
        '<tds:SetSystemFactoryDefault xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        "<tds:FactoryDefault>Soft</tds:FactoryDefault>"
        "</tds:SetSystemFactoryDefault>"
    )
    return await post_soap(
        http,
        conn,
        DEVICE_SERVICE_PATH,
        body,
        clock=clock,
        timeout=timeout,
    )


async def create_user(
    conn: CameraConnection,
    username: str,
    password: str,
    level: Literal["Administrator", "Operator", "User", "Anonymous"] = "User",
    http: CameraHttp | None = None,
    timeout: float = 10.0,
) -> CameraResult[str]:
    """Create a new ONVIF user account via CreateUsers."""
    if http is None:
        http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    body = (
        '<tds:CreateUsers xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<tds:User>"
        f"<tt:Username>{username}</tt:Username>"
        f"<tt:Password>{password}</tt:Password>"
        f"<tt:UserLevel>{level}</tt:UserLevel>"
        "</tds:User>"
        "</tds:CreateUsers>"
    )
    return await post_soap(
        http,
        conn,
        DEVICE_SERVICE_PATH,
        body,
        clock=clock,
        timeout=timeout,
    )


async def delete_user(
    conn: CameraConnection,
    username: str,
    http: CameraHttp | None = None,
    timeout: float = 10.0,
) -> CameraResult[str]:
    """Delete an ONVIF user account via DeleteUsers."""
    if http is None:
        http = CameraHttp(ssl_context=camera_ssl_context(None))
    clock = SystemClock()
    body = (
        '<tds:DeleteUsers xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
        f"<tds:Username>{username}</tds:Username>"
        "</tds:DeleteUsers>"
    )
    return await post_soap(
        http,
        conn,
        DEVICE_SERVICE_PATH,
        body,
        clock=clock,
        timeout=timeout,
    )


async def wait_until_answering(
    host: str,
    port: int,
    timeout: float = 180.0,
) -> bool:
    """Poll host and port until TLS socket accepts connections."""
    start = time.monotonic()
    ssl_ctx = camera_ssl_context(None)

    while time.monotonic() - start < timeout:
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx),
                timeout=5.0,
            )
            w.close()
            await w.wait_closed()
            return True
        except Exception:
            await asyncio.sleep(2.0)

    return False
