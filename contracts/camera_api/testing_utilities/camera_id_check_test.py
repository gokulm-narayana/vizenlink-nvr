#!/usr/bin/env python3
"""
camera_id_check_test.py — the camera refuses requests addressed to a different camera, and ignores the check when no id is sent
(design/stages/camera-id-request-check/DESIGN.md; FR-CF-155, FR-OV-102, FR-NE-129)

A NuraeyeClient puts the camera's serial in `X-VizenLink-Camera-Id` (LAN) or `camera_id` (WAN MQTT). The camera compares it with its own
serial BEFORE routing/authentication and answers a mismatch with HTTP 421; a request without the id (a generic ONVIF NVR/VMS) is never
refused. The camera's real serial is read from ONVIF GetDeviceInformation; the "other camera" id is that serial with a suffix.

  CID-01  no header -> ONVIF GetDeviceInformation and REST /nuraeye/health answer normally; an EMPTY header counts as no header.
  CID-02  correct id -> both answer normally.
  CID-03  wrong id -> HTTP 421 on ONVIF (SOAP fault), REST (JSON error_code 421) and GET /snapshot; the body never contains the real serial.
  CID-04  wrong id + WRONG PASSWORD -> still 421, not 401 (the check runs before authentication, so the client can tell "wrong camera"
          from "wrong password" at the first reply).
  CID-05  a wrong-id state-changing request does nothing (POST /nuraeye/events/bbox-overlay with the inverted value; read back unchanged).
  CID-06  GET /nuraeye/capabilities reports camera_id_check = true.
  CID-07  WAN (MQTT, needs AWS config; SKIP otherwise): GetVideoMode with a wrong camera_id -> error response 421; with the right id and
          without any id -> normal.

Usage:
    python testing_utilities/camera_id_check_test.py [--wrong-id-suffix -OTHER]
Safe on a camera in normal use (the only write is reverted). Writes a report to
design/stages/camera-id-request-check/reports/camera_id_check_test_<ts>.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from day_night_mode_test import _MqttHarness, _mqtt_config, load_camera_env
from nuraeye_rest_client import NuraeyeRestClient, wan_auth_block
from onvif_client import _SESSION, _wsse_header, get_device_info

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "design/stages/camera-id-request-check/reports"
HDR = "X-VizenLink-Camera-Id"
GET_VIDEO_MODE = 2  # NuraeyeAwsIotCommand_GetVideoMode


def onvif(ip: str, user: str, pw: str, action: str, headers: dict | None = None) -> tuple[int, str]:
    """Authenticated (WS-UsernameToken) ONVIF device-service call with extra HTTP headers. -> (status, body)."""
    body = (f'<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">{_wsse_header(user, pw)}'
            f'<s:Body><tds:{action} xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>')
    h = {"Content-Type": "application/soap+xml; charset=utf-8"}
    h.update(headers or {})
    r = _SESSION.post(f"https://{ip}:443/onvif/device_service", data=body, headers=h, timeout=15, verify=False)
    return r.status_code, r.text


def rest(rc: NuraeyeRestClient, ip: str, method: str, path: str, headers: dict | None = None, payload: dict | None = None) -> tuple[int, str]:
    h = rc._authed_headers()  # noqa: SLF001 -- reuse the test client's bearer session
    h.update(headers or {})
    r = rc._session.request(method, f"https://{ip}{path}", headers=h, data=json.dumps(payload) if payload is not None else None,  # noqa: SLF001
                            timeout=15, verify=False)
    return r.status_code, r.text


def main() -> int:
    ap = argparse.ArgumentParser(description="Camera-ID request check (FR-CF-155)")
    ap.add_argument("--env-file", default=str(PROJECT_ROOT / "envs/.camera_env"))
    ap.add_argument("--wrong-id-suffix", default="-OTHER", help="appended to the real serial to make the 'other camera' id")
    args = ap.parse_args()

    env = load_camera_env(args.env_file)
    ip, user, pw = env.get("CAMERA_IP"), env.get("CAMERA_USER"), env.get("CAMERA_PASS")
    if not (ip and user and pw):
        print("Missing CAMERA_* in --env-file")
        return 2
    serial = get_device_info(ip, 443, user, pw, use_https=True).get("SerialNumber", "")
    if not serial:
        print("camera reports no SerialNumber (unprovisioned) -- the check is not enforced on such a camera")
        return 2
    wrong = serial + args.wrong_id_suffix
    rc = NuraeyeRestClient(ip, user, pw)
    results: list[tuple[str, str, str]] = []

    def rec(tid: str, status: str, note: str) -> None:
        results.append((tid, status, note))
        print(f"[{tid}] {status} — {note}")

    def ok(code: int) -> bool:
        return code == 200

    # CID-01
    a = onvif(ip, user, pw, "GetDeviceInformation")
    b = rest(rc, ip, "GET", "/nuraeye/health")
    c = onvif(ip, user, pw, "GetDeviceInformation", {HDR: ""})
    d = rest(rc, ip, "GET", "/nuraeye/health", {HDR: ""})
    rec("CID-01", "PASS" if all(ok(x[0]) for x in (a, b, c, d)) else "FAIL",
        f"no header: ONVIF {a[0]}, REST {b[0]}; empty header: ONVIF {c[0]}, REST {d[0]} (all must be 200)")
    # CID-02
    a = onvif(ip, user, pw, "GetDeviceInformation", {HDR: serial})
    b = rest(rc, ip, "GET", "/nuraeye/health", {HDR: serial})
    rec("CID-02", "PASS" if ok(a[0]) and ok(b[0]) else "FAIL", f"correct id: ONVIF {a[0]}, REST {b[0]}")
    # CID-03
    ao = onvif(ip, user, pw, "GetDeviceInformation", {HDR: wrong})
    ar = rest(rc, ip, "GET", "/nuraeye/health", {HDR: wrong})
    asn = rest(rc, ip, "GET", "/snapshot", {HDR: wrong})
    bodies = ao[1] + ar[1] + asn[1]
    good = (ao[0] == 421 and "Fault" in ao[1] and ar[0] == 421 and '"error_code": 421' in ar[1] and asn[0] == 421 and serial not in bodies)
    rec("CID-03", "PASS" if good else "FAIL",
        f"wrong id: ONVIF {ao[0]} ({'SOAP fault' if 'Fault' in ao[1] else ao[1][:40]!r}), REST {ar[0]}, /snapshot {asn[0]}; "
        f"real serial in any body: {'YES' if serial in bodies else 'no'}")
    # CID-04
    bad = onvif(ip, user, "definitely-not-the-password", "GetUsers", {HDR: wrong})
    nobad = onvif(ip, user, "definitely-not-the-password", "GetUsers")
    rec("CID-04", "PASS" if bad[0] == 421 and nobad[0] == 401 else "FAIL",
        f"wrong password + wrong id -> {bad[0]} (expect 421); wrong password, no id -> {nobad[0]} (expect 401, unchanged behaviour)")
    # CID-05
    st, body = rest(rc, ip, "GET", "/nuraeye/events/bbox-overlay")
    try:
        cur = bool(json.loads(body)["output"]["enabled"])
    except Exception:  # noqa: BLE001
        cur = None
    if cur is None:
        rec("CID-05", "FAIL", f"could not read bbox-overlay ({st})")
    else:
        w = rest(rc, ip, "POST", "/nuraeye/events/bbox-overlay", {HDR: wrong}, {"enabled": (not cur)})
        st2, body2 = rest(rc, ip, "GET", "/nuraeye/events/bbox-overlay")
        after = bool(json.loads(body2)["output"]["enabled"])
        if after != cur:   # never leave the camera changed
            rest(rc, ip, "POST", "/nuraeye/events/bbox-overlay", None, {"enabled": cur})
        rec("CID-05", "PASS" if w[0] == 421 and after == cur else "FAIL",
            f"POST with the inverted value and a wrong id -> {w[0]}; value before {cur}, after {after} (must be unchanged)")
    # CID-06
    st, body = rest(rc, ip, "GET", "/nuraeye/capabilities")
    try:
        flag = json.loads(body)["output"].get("camera_id_check")
    except Exception:  # noqa: BLE001
        flag = None
    rec("CID-06", "PASS" if flag is True else "FAIL", f"capabilities.camera_id_check = {flag}")
    # CID-07
    mqtt_cfg = _mqtt_config(env)
    if not mqtt_cfg:
        rec("CID-07", "SKIP", "no MQTT/AWS configuration in the env file")
    else:
        try:
            outs = {}
            for tag, params in (("wrong", {"camera_id": wrong}), ("right", {"camera_id": serial}), ("absent", {})):
                h = _MqttHarness(mqtt_cfg["thing_name"])
                try:
                    rid = f"cid-{tag}-{int(time.time() * 1000)}"
                    payload = {"command": GET_VIDEO_MODE, "request_id": rid, "auth_credentials": wan_auth_block(user, pw), **params}  # FR-NE-130: WAN commands carry the account digest
                    h.connection.publish(topic=h.command_topic, payload=json.dumps(payload), qos=h._mqtt.QoS.AT_LEAST_ONCE)  # noqa: SLF001
                    outs[tag] = h.wait_for_response(rid, timeout_s=15.0)
                finally:
                    h.close()
            w, r_, a_ = outs["wrong"], outs["right"], outs["absent"]
            good = (w is not None and w.get("status") == "error" and "camera id mismatch" in str(w) and "421" in str(w)
                    and r_ is not None and r_.get("status") == "ok" and a_ is not None and a_.get("status") == "ok")
            rec("CID-07", "PASS" if good else "FAIL", f"WAN wrong -> {str(w)[:90]}; right -> {(r_ or {}).get('status')}; absent -> {(a_ or {}).get('status')}")
        except Exception as e:  # noqa: BLE001
            rec("CID-07", "SKIP", f"MQTT harness unavailable: {type(e).__name__}: {e}")

    failed = [r for r in results if r[1] == "FAIL"]
    passed = not failed and any(r[1] == "PASS" for r in results)
    print(f"\nVERDICT: {'PASS' if passed else 'FAIL'}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rep = REPORT_DIR / f"camera_id_check_test_{stamp}.md"
    rep.write_text(f"# Camera-ID request check — {stamp}\n\n**Stage:** camera-id-request-check — FR-CF-155 / FR-OV-102 / FR-NE-129\n\n"
                   f"**Verdict: {'PASS' if passed else 'FAIL'}** — camera serial `{serial}`, wrong id `{wrong}`.\n\n"
                   + "\n".join(f"- {t}: {s} — {n}" for t, s, n in results) + "\n")
    print(f"Report saved: {rep}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
