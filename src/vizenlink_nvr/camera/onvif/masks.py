"""Media2 privacy masks, mirrored from camera_api MaskClient's current wire contract."""

from typing import Any

from vizenlink_nvr.camera.onvif.media2 import MEDIA2_NAMESPACE, OnvifMedia2Client
from vizenlink_nvr.camera.onvif.soap import find_text, parse_xml, post_soap, xml_escape
from vizenlink_nvr.camera.result import CameraResult, Failure, FailureKind, Success


class OnvifMaskClient(OnvifMedia2Client):
    async def call(self, body: str) -> CameraResult[str]:
        endpoint = await self.resolve_endpoint()
        if not isinstance(endpoint, Success):
            return endpoint
        return await post_soap(self.http, self.conn, endpoint.value, body, clock=self.clock, timeout=8)

    async def options(self) -> CameraResult[dict[str, Any]]:
        result = await self.call(
            f'<tr2:GetMaskOptions xmlns:tr2="{MEDIA2_NAMESPACE}">'
            "<tr2:ConfigurationToken>VideoSourceCfg_1</tr2:ConfigurationToken></tr2:GetMaskOptions>"
        )
        if not isinstance(result, Success):
            return result
        try:
            element = parse_xml(result.value).find(".//{*}Options")
            if element is None:
                return Failure(FailureKind.BAD_RESPONSE, "Camera did not report mask options")
            colors = [
                {k.lower(): (float(v) if k in ("X", "Y", "Z") else v) for k, v in e.attrib.items()}
                for e in element.findall(".//{*}ColorList")
            ]
            return Success(
                {
                    "rectangle_only": element.get("RectangleOnly") == "true",
                    "single_color_only": element.get("SingleColorOnly") == "true",
                    "max_masks": int(find_text(element, "MaxMasks") or 0),
                    "max_points": int(find_text(element, "MaxPoints") or 4),
                    "types": [e.text.strip() for e in element.findall("{*}Types") if e.text],
                    "colors": colors,
                }
            )
        except Exception as exc:
            return Failure(FailureKind.BAD_RESPONSE, f"Invalid mask options: {exc}")

    async def masks(self) -> CameraResult[list[dict[str, Any]]]:
        result = await self.call(f'<tr2:GetMasks xmlns:tr2="{MEDIA2_NAMESPACE}"/>')
        if not isinstance(result, Success):
            return result
        try:
            masks = []
            for mask in parse_xml(result.value).findall(".//{*}Masks"):
                points = [
                    {"x": float(p.get("x", "0")), "y": float(p.get("y", "0"))}
                    for p in mask.findall("{*}Polygon/{*}Point")
                ]
                masks.append(
                    {
                        "token": mask.get("token", ""),
                        "polygon": points,
                        "type": find_text(mask, "Type"),
                        "enabled": find_text(mask, "Enabled") == "true",
                    }
                )
            return Success(masks)
        except Exception as exc:
            return Failure(FailureKind.BAD_RESPONSE, f"Invalid masks response: {exc}")

    async def save(
        self,
        points: list[dict[str, float]],
        mask_type: str,
        enabled: bool,
        token: str | None = None,
        color: dict[str, Any] | None = None,
    ) -> CameraResult[dict[str, Any]]:
        operation = "SetMask" if token else "CreateMask"
        polygon = "".join(f'<tt:Point x="{p["x"]}" y="{p["y"]}"/>' for p in points)
        color_xml = ""
        if color:
            color_xml = (
                f'<tr2:Color X="{float(color["x"])}" Y="{float(color["y"])}" '
                f'Z="{float(color["z"])}" Colorspace="{xml_escape(color["colorspace"])}"/>'
            )
        body = (
            f'<tr2:{operation} xmlns:tr2="{MEDIA2_NAMESPACE}" xmlns:tt="http://www.onvif.org/ver10/schema">'
            f'<tr2:Mask token="{xml_escape(token or "")}">'
            "<tr2:ConfigurationToken>VideoSourceCfg_1</tr2:ConfigurationToken>"
            f"<tr2:Polygon>{polygon}</tr2:Polygon><tr2:Type>{xml_escape(mask_type)}</tr2:Type>"
            f"{color_xml}<tr2:Enabled>{str(enabled).lower()}</tr2:Enabled></tr2:Mask></tr2:{operation}>"
        )
        result = await self.call(body)
        if not isinstance(result, Success):
            return result
        try:
            saved_token = token or find_text(parse_xml(result.value), "Token")
            if not saved_token:
                return Failure(FailureKind.BAD_RESPONSE, "Camera did not return a privacy zone token")
            return Success({"token": saved_token})
        except Exception as exc:
            return Failure(FailureKind.BAD_RESPONSE, f"Invalid mask response: {exc}")

    async def delete(self, token: str) -> CameraResult[dict[str, Any]]:
        result = await self.call(
            f'<tr2:DeleteMask xmlns:tr2="{MEDIA2_NAMESPACE}">'
            f"<tr2:Token>{xml_escape(token)}</tr2:Token></tr2:DeleteMask>"
        )
        return Success({"deleted": token}) if isinstance(result, Success) else result
