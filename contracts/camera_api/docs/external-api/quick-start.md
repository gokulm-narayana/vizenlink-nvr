# Quick start

Version 1.0 · 2026-10-21

Five short steps with a camera on your local network. Replace `192.0.2.50` with your camera's address, and the account with one you created on the camera (a new camera has the Administrator account `admin`).

## 1. Find the camera

Cameras answer WS-Discovery: send a Probe to UDP multicast `239.255.255.250:3702` and each camera replies with its address ([ONVIF API, section 2](camera-onvif-api.md)). Or just use the address from your DHCP server.

## 2. Check what it is (no login needed)

```bash
curl -sk -X POST https://192.0.2.50/onvif/device_service \
  -H 'Content-Type: application/soap+xml' \
  -d '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>'
```

The reply carries `Manufacturer`, `Model`, `FirmwareVersion`, `SerialNumber` and `HardwareId`. `-k` accepts the camera's self-signed certificate.

## 3. Sign in to the REST API

The password is never sent. You send a digest of it: `Base64( SHA1( Base64Decode(nonce) + created + password ) )`, where `nonce` is 16 random bytes (Base64 encoded) and `created` is the current UTC time.

```python
import base64, hashlib, os, ssl, requests, urllib3
from datetime import datetime, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

class CameraTLS(HTTPAdapter):
    """Accept the camera's self-signed certificate; lower the minimum TLS security level if your TLS library needs it."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context(ciphers="DEFAULT:@SECLEVEL=0")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

urllib3.disable_warnings()
BASE = "https://192.0.2.50"
USER, PASSWORD = "admin", "<your password>"
http = requests.Session()
http.verify = False                       # the camera certificate is self-signed
http.mount("https://", CameraTLS())

nonce = os.urandom(16)
created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + PASSWORD.encode()).digest()).decode()

login = http.post(f"{BASE}/nuraeye/session/login", json={
    "auth_credentials": {"username": USER, "password_digest": digest,
                         "nonce": base64.b64encode(nonce).decode(), "created": created}}).json()
token = login["output"]["token"]
auth = {"Authorization": f"Bearer {token}"}

caps = http.get(f"{BASE}/nuraeye/capabilities", headers=auth).json()["output"]
print(caps)
```

`capabilities` tells you what this camera supports (storage, recording modes, deterrence outputs, value ranges). Build your user interface from it. If the login reply says `password_change_required`, change the Administrator password first.

## 4. Watch live video

Ask the camera where the stream is, then open it with any RTSP client. The stream is RTSPS (RTSP over TLS) with HTTP Digest authentication using the camera account.

```python
uri = http.post(f"{BASE}/nuraeye/live-stream-uri", headers=auth, json={"profile_token": "Profile_1"}).json()["output"]["url"]
print(uri)   # rtsps://192.0.2.50:554/high
```

```bash
ffplay -rtsp_transport tcp "rtsps://admin:<your password>@192.0.2.50:554/high"
```

`Profile_1` is the main stream, `Profile_2` the sub stream and `Profile_3` a small stream for phones. An ONVIF client gets the same URIs from `GetStreamUri` ([ONVIF API](camera-onvif-api.md)).

## 5. Browse and play recordings

With an SD card, the REST API lists clips (`GET /nuraeye/recordings`, `GET /nuraeye/recordings/dates`) and downloads them (`GET /nuraeye/recordings/{id}/clip`). An NVR instead uses the ONVIF Recording, Search and Replay Control services (`GetRecordings`, `GetReplayUri`, then RTSP `PLAY` with a `Range` header); see [ONVIF API, section 1.7](camera-onvif-api.md).

## Going further

* Every setting and action: [REST API](camera-rest-api.md).
* Not on the same network: [remote control over MQTT](camera-wan-mqtt-api.md) and [cloud video playback](cloud-video-playback-api.md).
