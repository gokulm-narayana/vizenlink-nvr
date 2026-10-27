# VizenLink Camera and Cloud API Documentation

Version 1.0 · 2026-10-21 · camera firmware build 20261019 and later

Documentation for developers who integrate with VizenLink cameras: NVR / VMS vendors, and mobile, desktop or server developers who build their own client. Start with the [quick start](quick-start.md).

## Which document do I need?

| I am building... | Read |
|---|---|
| An NVR / VMS / ONVIF client on the local network | [Camera ONVIF API](camera-onvif-api.md) |
| An app that configures a camera on the local network (recording, alerts, deterrence, audio, health) | [Camera REST API](camera-rest-api.md) · [OpenAPI file](camera-rest-api.openapi.yaml) |
| Remote control of a camera over the internet | [Remote control over MQTT](camera-wan-mqtt-api.md) · [AsyncAPI file](camera-wan-mqtt-api.asyncapi.yaml) |
| Remote live view, clip playback or export | [Cloud video playback](cloud-video-playback-api.md) · [OpenAPI file](cloud-video-playback-api.openapi.yaml) |
| Your own sign-up, sign-in and profile screens (username, email, phone, name, date of birth) | [Cloud account identity](cloud-account-identity-api.md) · [OpenAPI file](cloud-account-identity-api.openapi.yaml) |
| A camera list that follows the user, and family sharing | [Cloud camera list](cloud-camera-registry-api.md) · [OpenAPI file](cloud-camera-registry-api.openapi.yaml) |

## The pieces and how they fit

```
                     local network                                  internet
 your client ──ONVIF (SOAP) / REST (JSON) over HTTPS──► camera     your client ──► VizenLink cloud
              RTSPS for video, audio and clips                                   (Cognito sign-in)
                                                                                    │
                                                    MQTT commands via AWS IoT ◄─────┤
                                                    video via Kinesis Video Streams ◄┘
```

* **On the local network** a client talks to the camera directly over HTTPS (ONVIF SOAP and the REST API) and opens RTSPS streams for video, recorded clips and two-way talk. No cloud account is needed.
* **Over the internet** a client signs in to the VizenLink cloud, sends commands to the camera through AWS IoT, and receives video through Amazon Kinesis Video Streams. The camera does not need to be reachable from the internet: it keeps an outbound connection to AWS IoT.

## Common facts

* **Camera identity.** Each camera has a serial number (`VZL-CAM-nnnnnn`). It is the ONVIF `SerialNumber`, the AWS IoT thing name and the prefix of the cloud stream names.
* **Camera accounts.** Every camera has up to five accounts: one `Administrator` (`admin`) and up to four `Operator` or `User` accounts. Roles decide what a caller may do. Camera accounts are separate from cloud (VizenLink) accounts.
* **Self-signed certificate.** A camera serves HTTPS and RTSPS with a self-signed certificate, so clients accept it explicitly. A client can confirm it is talking to the camera it expects by sending `X-VizenLink-Camera-Id: <serial>`; a different camera answers `421`.
* **First password.** In production firmware a camera that still has its factory password serves only a small set of calls until the Administrator password is changed (HTTP `428`).
* **Examples.** Addresses in examples are from the documentation range `192.0.2.0/24`. Identifiers in angle brackets (for example `<user-pool-id>`) are issued by VizenLink.

## Cloud access

The cloud services are operated by VizenLink and require credentials issued to integration partners (a user pool account, and the base URL, app client and identity pool for it). Contact: `<integration-contact>`.

## Versioning

These documents describe firmware by its build number (a date-time such as `20261019...`), which a camera reports as `FirmwareVersion`. Clients should ignore fields they do not recognise, because firmware may add fields. Changes to these documents are listed in the [change log](CHANGELOG.md).
