"""Camera-local ONVIF accounts, distinct from recorder users."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from vizenlink_nvr.api.dependencies import DbSession, RequireOwner, verify_camera_access
from vizenlink_nvr.api.v1.camera_features import FeaturesDep
from vizenlink_nvr.api.v1.camera_settings import VaultDep
from vizenlink_nvr.camera.connection import DEVICE_SERVICE_PATH
from vizenlink_nvr.camera.nuraeye.client import NuraeyeClient
from vizenlink_nvr.camera.onvif.device import OnvifDeviceClient
from vizenlink_nvr.camera.onvif.soap import find_text, parse_xml, post_soap, xml_escape
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.camera_features import CameraFeaturesService, require_success

camera_accounts_router = APIRouter(prefix="/cameras/{serial}/accounts", tags=["camera-accounts"])


class AccountAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["create", "role", "password", "delete"]
    username: str = Field(min_length=1, max_length=32)
    password: SecretStr | None = Field(default=None, min_length=1, max_length=32)
    role: Literal["Operator", "User"] | None = None
    confirmation: str


async def account_state(camera: NuraeyeClient, service: CameraFeaturesService) -> dict[str, Any]:
    caps = require_success(await camera.request("GET", "/nuraeye/capabilities"))
    if caps.get("multi_user") is not True:
        raise HTTPException(422, "This camera does not support multiple accounts")
    result = require_success(
        await post_soap(
            service.settings.http,
            camera.conn,
            DEVICE_SERVICE_PATH,
            '<tds:GetUsers xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
            clock=service.settings.clock,
            timeout=8,
        )
    )
    try:
        users = [
            {"username": find_text(item, "Username"), "role": find_text(item, "UserLevel")}
            for item in parse_xml(result).findall(".//{*}User")
            if find_text(item, "Username")
        ]
    except Exception as exc:
        raise HTTPException(502, "Camera returned an invalid account list") from exc
    return {
        "accounts": users,
        "current_username": camera.conn.username,
        "roles": [role for role in caps.get("user_roles", []) if role in ("Operator", "User")],
        "max_users": caps.get("max_users", 0),
    }


@camera_accounts_router.get("")
async def list_accounts(
    serial: str, user: RequireOwner, db: DbSession, vault: VaultDep, service: FeaturesDep
) -> dict[str, Any]:
    from vizenlink_nvr.db.models import Camera
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        return SIM_CAMERAS.list_accounts(cam)
    return await account_state(await service.client(db, vault, serial), service)


@camera_accounts_router.post("")
async def change_account(
    serial: str, body: AccountAction, user: RequireOwner, db: DbSession, vault: VaultDep, service: FeaturesDep
) -> dict[str, str]:
    from vizenlink_nvr.db.models import Camera
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    if body.confirmation != serial:
        raise HTTPException(409, "Confirm the camera account change first")
    cam = await db.get(Camera, serial)
    if is_sim_camera(cam) and cam is not None:
        result = SIM_CAMERAS.change_account(cam, body.action, body.username, body.role)
        await AuditService.record_event(
            session=db,
            action=f"camera.account.{body.action}",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            details={"username": body.username, "role": body.role},
            commit=True,
        )
        return result
    camera = await service.client(db, vault, serial)
    state = await account_state(camera, service)
    existing = next((u for u in state["accounts"] if u["username"] == body.username), None)
    if body.action == "create":
        if existing:
            raise HTTPException(409, "This camera account already exists")
        if len(state["accounts"]) >= state["max_users"]:
            raise HTTPException(422, "The camera's account limit has been reached")
    elif not existing:
        raise HTTPException(404, "Camera account not found")
    elif existing["role"] == "Administrator" or body.username == camera.conn.username:
        raise HTTPException(
            422, "This account is protected. Change the recorder's camera password in Details."
        )
    if body.action in ("create", "role") and body.role not in state["roles"]:
        raise HTTPException(422, "Choose a camera-reported account role")
    if body.action in ("create", "password") and body.password is None:
        raise HTTPException(422, "A new camera password is required")
    if body.action == "password" and body.password is not None:
        require_success(
            await OnvifDeviceClient(
                camera.conn, service.settings.http, service.settings.clock
            ).set_user_password(body.username, body.password)
        )
    else:
        operation = {"create": "CreateUsers", "role": "SetUser", "delete": "DeleteUsers"}[body.action]
        name = xml_escape(body.username)
        content = (
            f"<tds:Username>{name}</tds:Username>"
            if body.action == "delete"
            else (
                f"<tds:User><tt:Username>{name}</tt:Username>"
                + (
                    f"<tt:Password>{xml_escape(body.password.get_secret_value())}</tt:Password>"
                    if body.password
                    else ""
                )
                + f"<tt:UserLevel>{xml_escape(body.role or '')}</tt:UserLevel></tds:User>"
            )
        )
        require_success(
            await post_soap(
                service.settings.http,
                camera.conn,
                DEVICE_SERVICE_PATH,
                f'<tds:{operation} xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
                f'xmlns:tt="http://www.onvif.org/ver10/schema">{content}</tds:{operation}>',
                clock=service.settings.clock,
                timeout=8,
            )
        )
    service.settings.sessions.clear_session_for(camera.conn.host)
    await AuditService.record_event(
        session=db,
        action=f"camera.account.{body.action}",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"username": body.username, "role": body.role},
        commit=True,
    )
    return {"status": "ok"}
