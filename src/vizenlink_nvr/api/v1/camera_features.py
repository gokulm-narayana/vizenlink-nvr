"""Camera LAN settings API, using only server-allowlisted operations."""

import asyncio
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from vizenlink_nvr.api.dependencies import CurrentUser, DbSession, RequireOperator, verify_camera_access
from vizenlink_nvr.api.v1.camera_settings import SettingsServiceDep, VaultDep
from vizenlink_nvr.camera.onvif.masks import OnvifMaskClient
from vizenlink_nvr.db.models import Camera
from vizenlink_nvr.services.audit import AuditService
from vizenlink_nvr.services.camera_features import (
    CATALOG,
    GROUPS,
    CameraFeaturesService,
    camera_connection,
    require_success,
)

camera_features_router = APIRouter(prefix="/cameras/{serial}/features", tags=["camera-features"])


def get_features(request: Request, settings: SettingsServiceDep) -> CameraFeaturesService:
    if not hasattr(request.app.state, "camera_features"):
        request.app.state.camera_features = CameraFeaturesService(settings)
    return cast(CameraFeaturesService, request.app.state.camera_features)


FeaturesDep = Annotated[CameraFeaturesService, Depends(get_features)]


class CameraActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    confirmation: str | None = None


class MaskPoint(BaseModel):
    x: float = Field(ge=-1, le=1, allow_inf_nan=False)
    y: float = Field(ge=-1, le=1, allow_inf_nan=False)


class MaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    polygon: list[MaskPoint] = Field(min_length=4, max_length=4)
    type: str | None = None
    enabled: bool = True


@camera_features_router.get("")
async def feature_groups(serial: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    verify_camera_access(serial, user)
    if await db.get(Camera, serial) is None:
        raise HTTPException(404, "Camera not found")
    return {
        "source": CATALOG["source"],
        "groups": [
            {"id": key, "title": group["title"], "description": group["description"]}
            for key, group in GROUPS.items()
        ],
    }


@camera_features_router.get("/{group}")
async def feature_state(
    serial: str, group: str, user: CurrentUser, db: DbSession, vault: VaultDep, service: FeaturesDep
) -> dict[str, Any]:
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    if is_sim_camera(cam):
        return SIM_CAMERAS.feature_state(cam, group, service.catalog(group))
    return await service.state(db, vault, serial, group)


@camera_features_router.post("/actions/{operation}")
async def feature_action(
    serial: str,
    operation: str,
    body: CameraActionRequest,
    user: CurrentUser,
    db: DbSession,
    vault: VaultDep,
    service: FeaturesDep,
) -> dict[str, Any]:
    from vizenlink_nvr.services.camera_features import CONFIRM, INTERNAL, OPERATIONS, validate
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    if is_sim_camera(cam):
        if operation in INTERNAL or operation not in {o for g in GROUPS.values() for o in g["operations"]}:
            raise HTTPException(404, "Camera operation is not exposed to the browser")
        op = OPERATIONS[operation]
        read_only = op["method"] == "GET" or operation in {"queryAlertRule", "getLiveStreamUri", "getTalkUri"}
        if not read_only and user.role not in ("owner", "operator"):
            raise HTTPException(403, "Camera changes require Operator or Owner access")
        if operation in CONFIRM and body.confirmation != serial:
            raise HTTPException(409, "Review and confirm this camera action first")
        validate(body.payload, op["schema"])
        result = SIM_CAMERAS.execute_feature_action(cam, operation, body.payload, body.query)
        if not read_only:
            await AuditService.record_event(
                session=db,
                action=f"camera.api.{operation}",
                resource_type="camera",
                resource_id=serial,
                actor_id=user.id,
                actor_username=user.username,
                details={"fields": list(body.payload)},
                commit=True,
            )
        return result
    return await service.execute(
        db, vault, serial, operation, body.payload, body.query, user, body.confirmation
    )


@camera_features_router.get("/privacy/masks")
async def list_masks(
    serial: str, user: CurrentUser, db: DbSession, vault: VaultDep, settings: SettingsServiceDep
) -> dict[str, Any]:
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    if is_sim_camera(cam):
        return SIM_CAMERAS.list_masks(cam)
    conn = await camera_connection(db, vault, serial)
    client = OnvifMaskClient(conn, settings.http, settings.clock)
    options = require_success(await client.options())
    masks = require_success(await client.masks())
    return {"options": options, "masks": masks}


@camera_features_router.post("/privacy/masks")
@camera_features_router.put("/privacy/masks/{token}")
async def save_mask(
    serial: str,
    body: MaskRequest,
    user: RequireOperator,
    db: DbSession,
    vault: VaultDep,
    settings: SettingsServiceDep,
    service: FeaturesDep,
    token: str | None = None,
) -> dict[str, Any]:
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    if is_sim_camera(cam):
        result = SIM_CAMERAS.save_mask(cam, [p.model_dump() for p in body.polygon], body.type, body.enabled, token)
        await AuditService.record_event(
            session=db,
            action="camera.mask.save",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            details={"token": result.get("token")},
            commit=True,
        )
        return result
    conn = await camera_connection(db, vault, serial)
    client = OnvifMaskClient(conn, settings.http, settings.clock)
    async with service.locks.setdefault(serial, asyncio.Lock()):
        options = require_success(await client.options())
        masks = require_success(await client.masks())
        if token and not any(m["token"] == token for m in masks):
            raise HTTPException(404, "Privacy zone not found")
        if not token and len(masks) >= options["max_masks"]:
            raise HTTPException(422, "The camera's privacy-zone limit has been reached")
        xs, ys = {p.x for p in body.polygon}, {p.y for p in body.polygon}
        if len(xs) != 2 or len(ys) != 2 or len({(p.x, p.y) for p in body.polygon}) != 4:
            raise HTTPException(422, "Privacy zones must be non-empty rectangles")
        mask_type = body.type or next(iter(options["types"]), None)
        if not isinstance(mask_type, str) or mask_type not in options["types"]:
            raise HTTPException(422, "Choose a mask type reported by this camera")
        color = next(iter(options["colors"]), None)
        result = require_success(
            await client.save([p.model_dump() for p in body.polygon], mask_type, body.enabled, token, color)
        )
    await AuditService.record_event(
        session=db,
        action="camera.mask.save",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"token": result.get("token")},
        commit=True,
    )
    return result


@camera_features_router.delete("/privacy/masks/{token}")
async def delete_mask(
    serial: str,
    token: str,
    user: RequireOperator,
    db: DbSession,
    vault: VaultDep,
    settings: SettingsServiceDep,
) -> dict[str, Any]:
    from vizenlink_nvr.services.sim_camera import SIM_CAMERAS, is_sim_camera

    verify_camera_access(serial, user)
    cam = await db.get(Camera, serial)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    if is_sim_camera(cam):
        result = SIM_CAMERAS.delete_mask(cam, token)
        await AuditService.record_event(
            session=db,
            action="camera.mask.delete",
            resource_type="camera",
            resource_id=serial,
            actor_id=user.id,
            actor_username=user.username,
            details={"token": token},
            commit=True,
        )
        return result
    conn = await camera_connection(db, vault, serial)
    client = OnvifMaskClient(conn, settings.http, settings.clock)
    result = require_success(await client.delete(token))
    await AuditService.record_event(
        session=db,
        action="camera.mask.delete",
        resource_type="camera",
        resource_id=serial,
        actor_id=user.id,
        actor_username=user.username,
        details={"token": token},
        commit=True,
    )
    return result
