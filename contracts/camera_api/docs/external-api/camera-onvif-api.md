# VizenLink Camera — ONVIF API Reference

Version 1.0 · 2026-10-21 · describes camera firmware build 20261019 and later (the build number is the firmware version string that `GetDeviceInformation` reports).

This document is for NVR, VMS and other ONVIF client developers. It describes exactly what the VizenLink camera sends and accepts over ONVIF: every request and response below is a literal example, with the field names, element nesting and namespace prefixes the camera really uses. Example values (addresses, tokens, digests) are illustrative.

## What the camera implements

| Service | Endpoint | Notes |
|---|---|---|
| Device | `/onvif/device_service` | Information, network, time, users, firmware upgrade. |
| Media (ver10) | `/onvif/media_service` | Profiles, stream and snapshot URIs, encoder, OSD and privacy-mask configuration. H.264 oriented, see Known limitations. |
| Media2 (ver20) | `/onvif/media2_service` | Use this service for H.265. |
| Imaging | `/onvif/imaging_service` | Brightness, contrast, day/night, wide dynamic range, exposure, white balance. |
| Analytics | `/onvif/analytics_service` | Supported rules, rule options, and creating or deleting rules. |
| Events | `/onvif/events_service` | Pull-point event subscription. |
| Recording, Search, Replay Control | `/onvif/recording`, `/onvif/search`, `/onvif/replay` | Profile G style discovery and playback of clips recorded to the camera's SD card. The only write action is `DeleteRecording`. |
| WS-Discovery | UDP multicast `239.255.255.250:3702` | See section 2. |

The camera is designed to the requirements of ONVIF Profiles S, T and G. This document is not a conformance declaration: check the behaviour you depend on against the official ONVIF specifications and WSDLs, which remain the authoritative definition of every message:
[`devicemgmt.wsdl`](https://www.onvif.org/ver10/device/wsdl/devicemgmt.wsdl),
[`media.wsdl`](https://www.onvif.org/ver10/media/wsdl/media.wsdl),
[`media2.wsdl`](https://www.onvif.org/ver20/media/wsdl/media.wsdl),
[`recording.wsdl`](https://www.onvif.org/ver10/recording.wsdl),
[`search.wsdl`](https://www.onvif.org/ver10/search.wsdl),
[`replay.wsdl`](https://www.onvif.org/ver10/replay.wsdl).
No separate machine-readable file is provided for ONVIF, because the WSDLs already are one.

## Before you start

* **Transport.** HTTPS on port 443 with a **self-signed certificate**. Your client must accept it. The camera's TLS stack offers a modern ECDHE/AES-GCM suite; clients that enforce a high minimum security level (for example the OpenSSL 3.2+ default) may fail the handshake and need that level lowered for connections to the camera.
* **Authentication.** WS-Security UsernameToken with a password digest (section "Shared envelope" below). The factory Administrator account is `admin`; in production firmware, a camera whose Administrator still has the factory-default password serves only a small set of calls (the unauthenticated information calls and the Administrator's own password change) and refuses the rest with HTTP `428 Precondition Required` until the password is changed.
* **Accounts and roles.** Up to five accounts: one `Administrator` and up to four `Operator` or `User` accounts. Each action has a minimum role; a lower role gets an `InsufficientUserLevel` fault, not an authentication failure.
* **Digest inputs.** Send a fresh random nonce and the current UTC time as `Created` with every request. `GetSystemDateAndTime` needs no authentication and returns the camera's own time.
* **Streams.** Live and recorded video is not carried over SOAP. `GetStreamUri` and `GetReplayUri` return RTSPS URIs that you open with any RTSP client (sections 3 and 4).

---

## Shared envelope (every response below omits this wrapper for brevity)

Opening of every response:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" xmlns:timg="http://www.onvif.org/ver20/imaging/wsdl" xmlns:tan="http://www.onvif.org/ver20/analytics/wsdl" xmlns:tev="http://www.onvif.org/ver10/events/wsdl" xmlns:tns1="http://www.onvif.org/ver10/topics" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:wstop="http://docs.oasis-open.org/wsn/t-1" xmlns:wsa5="http://www.w3.org/2005/08/addressing">
<SOAP-ENV:Body>
<!-- ...Response body shown per-action below goes here... -->
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>
```

**SOAP Fault** (narrower namespace set than success, no XML
declaration):

```xml
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:wsa5="http://www.w3.org/2005/08/addressing" xmlns:wsrf-rw="http://docs.oasis-open.org/wsrf/rw-2" xmlns:wsntw="http://docs.oasis-open.org/wsn/bw-2" xmlns:ter="http://www.onvif.org/ver10/error">
<SOAP-ENV:Body>
<SOAP-ENV:Fault>
<SOAP-ENV:Code>
<SOAP-ENV:Value>SOAP-ENV:Sender</SOAP-ENV:Value>
<SOAP-ENV:Subcode>
<SOAP-ENV:Value>ter:NotAuthorized</SOAP-ENV:Value>
</SOAP-ENV:Subcode>
</SOAP-ENV:Code>
<SOAP-ENV:Reason>
<SOAP-ENV:Text xml:lang="en">Sender not Authorized</SOAP-ENV:Text>
</SOAP-ENV:Reason>
<SOAP-ENV:Node>http://www.w3.org/2003/05/soap-envelope/node/ultimateReceiver</SOAP-ENV:Node>
<SOAP-ENV:Role>http://www.w3.org/2003/05/soap-envelope/role/ultimateReceiver</SOAP-ENV:Role>
<SOAP-ENV:Detail>
<SOAP-ENV:Text>The action requested requires authorization and the sender is not authorized.</SOAP-ENV:Text>
</SOAP-ENV:Detail>
</SOAP-ENV:Fault>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>
```
(Some errors nest a second `Subcode` inside the first: for example an unsupported service answers outer `ter:ActionNotSupported`, inner `ter:NoSuchService`.)

**Auth header expected in every authenticated request** (the camera matches local element names regardless of prefix; all four leaves are mandatory):

```xml
<SOAP-ENV:Header>
<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd" xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
<wsse:UsernameToken>
<wsse:Username>admin</wsse:Username>
<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-username-token-profile-1.0#PasswordDigest">Z8n1c8b3s7fLp9k1x2y3zA4B5c6=</wsse:Password>
<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">MTIzNDU2Nzg5MGFiY2RlZg==</wsse:Nonce>
<wsu:Created>2026-07-31T10:15:00.000Z</wsu:Created>
</wsse:UsernameToken>
</wsse:Security>
</SOAP-ENV:Header>
```
Digest: `Password = Base64( SHA1( Base64Decode(Nonce) + Created + <device password> ) )`.
Required for every action except (Device service): `GetDeviceInformation`,
`GetSystemDateAndTime`, `GetEndpointReference`, `GetWsdlUrl`, `GetHostname`, `GetServices`,
`GetServiceCapabilities`, `GetCapabilities`.

## Fault for a request addressed to another camera (camera-ID check)

A NuraEye client (the mobile app) may add the HTTP header `X-VizenLink-Camera-Id: <SerialNumber>` to any ONVIF
request. The camera compares it with its own serial **before routing and before WS-Security authentication** (one check for every service). Absent or empty header -> processed exactly as specified elsewhere in this document (a generic
third-party NVR/VMS never sends it, so it is unaffected); equal -> processed; **different** -> HTTP **`421 Misdirected Request`** with a SOAP 1.2 fault and
nothing executed:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
<s:Body><s:Fault><s:Code><s:Value>s:Receiver</s:Value></s:Code>
<s:Reason><s:Text xml:lang="en">Camera ID mismatch</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>
```
The header is an HTTP transport extension outside the ONVIF schemas, not part of the SOAP message. The camera's serial is never in the reply. A wrong
camera with a different password also answers `421` (not `401`), so a client can tell "wrong camera" from "wrong password". RTSP/RTSPS requests are not checked.

## Fault while a firmware upgrade is in progress

From the moment a firmware upload really starts (`POST /onvif/firmware_upload` with a valid token) until the camera reboots, **every
other ONVIF request is refused**, whatever the service or action, with HTTP `500` and a SOAP 1.2
`Receiver` fault:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:ter="http://www.onvif.org/ver10/error">
<s:Body><s:Fault><s:Code><s:Value>s:Receiver</s:Value><s:Subcode><s:Value>ter:Action</s:Value>
<s:Subcode><s:Value>ter:ConfigurationConflict</s:Value></s:Subcode></s:Subcode></s:Code>
<s:Reason><s:Text xml:lang="en">Firmware upgrade in progress</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>
```
The state ends only by a reboot (upload finished, failed or aborted; also when no upload data arrives for 60 s). NVR/VMS clients should retry after
the camera is back (~45 s). **To be confirmed**: the `ter:Action`/`ter:ConfigurationConflict` subcode pair against the ONVIF Core fault table (not yet
checked against the spec text).

## 1.1 Device service

**GetDeviceInformation** — no auth. Request: `<tds:GetDeviceInformation/>`.
Response:
```xml
<tds:GetDeviceInformationResponse>
<tds:Manufacturer>OnChip Technologies</tds:Manufacturer>
<tds:Model>VizenLink-Pro2</tds:Model>
<tds:FirmwareVersion>1.4.2</tds:FirmwareVersion>
<tds:SerialNumber>OC2026073100123</tds:SerialNumber>
<tds:HardwareId>RTL8735B-Rev2</tds:HardwareId>
</tds:GetDeviceInformationResponse>
```

**GetSystemUris** — no auth, no request fields. Response: empty
(`<tds:GetSystemUrisResponse></tds:GetSystemUrisResponse>`).

**GetSystemDateAndTime** — no auth. Response:
```xml
<tds:GetSystemDateAndTimeResponse>
<tds:SystemDateAndTime>
<tt:DateTimeType>Manual</tt:DateTimeType>
<tt:DaylightSavings>false</tt:DaylightSavings>
<tt:TimeZone>
<tt:TZ>UTC</tt:TZ>
</tt:TimeZone>
<tt:UTCDateTime>
<tt:Time>
<tt:Hour>10</tt:Hour>
<tt:Minute>15</tt:Minute>
<tt:Second> 5</tt:Second>
</tt:Time>
<tt:Date>
<tt:Year>2026</tt:Year>
<tt:Month> 7</tt:Month>
<tt:Day>31</tt:Day>
</tt:Date>
</tt:UTCDateTime>
</tds:SystemDateAndTime>
</tds:GetSystemDateAndTimeResponse>
```
> Single-digit `Second`/`Month` render with a literal leading space (`"%2d"` format).

**SetSystemDateAndTime** — request (`NTP` type rejected with
`OnvifError_NtpServerUndefined`):
```xml
<tds:SetSystemDateAndTime>
<tds:DateTimeType>Manual</tds:DateTimeType>
<tds:DaylightSavings>false</tds:DaylightSavings>
<tds:TimeZone><tt:TZ>UTC</tt:TZ></tds:TimeZone>
<tds:UTCDateTime>
<tt:Time><tt:Hour>10</tt:Hour><tt:Minute>15</tt:Minute><tt:Second>5</tt:Second></tt:Time>
<tt:Date><tt:Year>2026</tt:Year><tt:Month>7</tt:Month><tt:Day>31</tt:Day></tt:Date>
</tds:UTCDateTime>
</tds:SetSystemDateAndTime>
```
Response: empty.

**SetSystemFactoryDefault** — request (`FactoryDefault` = `Hard`/`Soft`):
```xml
<tds:SetSystemFactoryDefault><tds:FactoryDefault>Soft</tds:FactoryDefault></tds:SetSystemFactoryDefault>
```
Triggers `onvif_config_reset` + async reboot. Response: empty.

**SystemReboot** — response:
```xml
<tds:SystemRebootResponse><tt:Message>Rebooting in 5 seconds</tt:Message></tds:SystemRebootResponse>
```

**StartFirmwareUpgrade** — response:
```xml
<tds:StartFirmwareUpgradeResponse>
<tds:UploadUri>https://192.0.2.50/onvif/firmware_upload?token=9a295077bb984ae56740acd2c53e21a7</tds:UploadUri>
<tds:UploadDelay>PT0S</tds:UploadDelay>
<tds:ExpectedDownTime>PT60S</tds:ExpectedDownTime>
</tds:StartFirmwareUpgradeResponse>
```
The `token` is 16 bytes from the secure random generator as **32 lowercase hex characters** (firmware 20261006130344 and later; earlier firmware returned a token that could need URL encoding). It needs no URL
encoding. Only one upgrade can be pending: a second `StartFirmwareUpgrade` before the first upload (or its 30 s timeout) is rejected.

See [Camera-REST-API.md](camera-rest-api.md) §2.4 for the upload itself.

**GetScopes** — response:
```xml
<tds:GetScopesResponse>
<tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/Profile/Streaming</tt:ScopeItem></tds:Scopes>
<tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/MAC/AA-BB-CC-DD-EE-FF</tt:ScopeItem></tds:Scopes>
<tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/hardware/VizenLink-Pro2</tt:ScopeItem></tds:Scopes>
<tds:Scopes><tt:ScopeDef>Configurable</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/name/VizenLink%20Front%20Door</tt:ScopeItem></tds:Scopes>
<tds:Scopes><tt:ScopeDef>Configurable</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/location/Front%20Porch</tt:ScopeItem></tds:Scopes>
</tds:GetScopesResponse>
```

**SetScopes** — request:
```xml
<tds:SetScopes>
<tds:Scopes>onvif://www.onvif.org/name/VizenLink%20Front%20Door</tds:Scopes>
<tds:Scopes>onvif://www.onvif.org/location/Front%20Porch</tds:Scopes>
</tds:SetScopes>
```
Response: empty.

**GetDiscoveryMode**:
```xml
<tds:GetDiscoveryModeResponse><tt:DiscoveryMode>Discoverable</tt:DiscoveryMode></tds:GetDiscoveryModeResponse>
```

**GetHostname**:
```xml
<tds:GetHostNameResponse>
<tds:HostnameInformation><tt:FromDHCP>false</tt:FromDHCP><tt:Name>vizenlink-front-door</tt:Name></tds:HostnameInformation>
</tds:GetHostNameResponse>
```

**GetDNS** (`tt:DNSFromDHCP` is genuinely a self-closing empty tag):
```xml
<tds:GetDNSResponse>
<tds:DNSInformation><tt:FromDHCP>true</tt:FromDHCP><tt:DNSFromDHCP/></tds:DNSInformation>
</tds:GetDNSResponse>
```

**GetNTP** (same empty-tag pattern for `tt:NTPManual`):
```xml
<tds:GetNTPResponse>
<tds:NTPInformation><tt:FromDHCP>true</tt:FromDHCP><tt:NTPManual/></tds:NTPInformation>
</tds:GetNTPResponse>
```

**GetNetworkInterfaces**:
```xml
<tds:GetNetworkInterfacesResponse>
<tds:NetworkInterfaces token="eth0">
<tt:Enabled>true</tt:Enabled>
<tt:Info><tt:Name>eth0</tt:Name><tt:HwAddress>AA-BB-CC-DD-EE-FF</tt:HwAddress><tt:MTU>1500</tt:MTU></tt:Info>
<tt:IPv4>
<tt:Enabled>true</tt:Enabled>
<tt:Config>
<tt:FromDHCP><tt:Address>192.0.2.50</tt:Address><tt:PrefixLength>24</tt:PrefixLength></tt:FromDHCP>
<tt:DHCP>true</tt:DHCP>
</tt:Config>
</tt:IPv4>
</tds:NetworkInterfaces>
</tds:GetNetworkInterfacesResponse>
```
> Note `tt:FromDHCP` here wraps `Address`/`PrefixLength` — a different usage of the same tag
> name from GetDNS/GetNTP's self-closing form above.

**GetNetworkDefaultGateway**:
```xml
<tds:GetNetworkDefaultGatewayResponse><tds:NetworkGateway><tt:IPv4Address>192.0.2.1</tt:IPv4Address></tds:NetworkGateway></tds:GetNetworkDefaultGatewayResponse>
```

**GetZeroConfiguration**:
```xml
<tds:GetZeroConfigurationResponse><tds:ZeroConfiguration><tt:Enabled>true</tt:Enabled><tt:InterfaceToken>eth0</tt:InterfaceToken></tds:ZeroConfiguration></tds:GetZeroConfigurationResponse>
```

**Accounts** — the camera holds up to **5 accounts**: exactly one `Administrator` (slot 0; also the account a third-party NVR/VMS uses)
and up to four `Operator`/`User` accounts. `GetServiceCapabilities` reports `MaxUsers=5`, `MaxUserNameLength=32`, `MaxPasswordLength=32` (was 16), `DefaultAccessPolicy=true`.
Names: 1-32 printable ASCII characters without spaces or `"<>&`; passwords: 1-32 characters. These four actions act for the authenticated caller; the camera checks the caller's name and role:

**GetUsers** (Administrator only; password never echoed) — response lists every account with its real level:
```xml
<tds:GetUsersResponse>
<tds:User><tt:Username>admin</tt:Username><tt:UserLevel>Administrator</tt:UserLevel></tds:User>
<tds:User><tt:Username>kid</tt:Username><tt:UserLevel>User</tt:UserLevel></tds:User>
</tds:GetUsersResponse>
```

**CreateUsers** (Administrator only) — request (one `User` per request; `UserLevel` must be `Operator` or `User`):
```xml
<tds:CreateUsers><tds:User><tt:Username>kid</tt:Username><tt:Password>Sup3rSecret</tt:Password><tt:UserLevel>User</tt:UserLevel></tds:User></tds:CreateUsers>
```
Response: empty. Faults: `ter:TooManyUsers` (6th account), `ter:UsernameClash` (HTTP 400), `ter:InvalidArgVal` (bad name, `Administrator`/`Anonymous` level), `ter:PasswordTooLong`.

**DeleteUsers** (Administrator only) — request:
```xml
<tds:DeleteUsers><tds:Username>kid</tds:Username></tds:DeleteUsers>
```
Response: empty. Faults: `ter:FixedUser` (the Administrator cannot be deleted, HTTP 400), `ter:UsernameMissing` (no such account). Ends that account's REST sessions and RTSP connections.

**SetUser** — request (`Password` and `UserLevel` are both optional; an omitted one is left alone):
```xml
<tds:SetUser><tds:User><tt:Username>kid</tt:Username><tt:Password>NewSecurePass123</tt:Password></tds:User></tds:SetUser>
```
Response: empty. Rules: the Administrator may change any account's password and a non-administrator's level (`Operator`<->`User`); any other account may change **only its own password**
(a deliberate deviation from the ONVIF default policy, which makes `SetUser` administrator-only) and never a level, otherwise the role fault below; the Administrator's level is fixed
(`ter:FixedUser`). The Administrator is **always named `admin`** and cannot be renamed (an unknown username -> `ter:UsernameMissing`; creating `admin` in any letter case ->
`ter:UsernameClash`). **No account may be given the factory-default password `password`** (any letter case): `CreateUsers`/`SetUser` answer HTTP 400 `ter:InvalidArgVal` /
`ter:PasswordNotAllowed`. Changing the Administrator's password ends every session; changing another account's ends only that account's.

**Fault while the Administrator still has the factory-default password** — in a build that forces the first password change (always in production) every authenticated action except the
Administrator's own `SetUser` is refused with **HTTP 428** and a SOAP `Sender` fault `ter:OperationProhibited` / `ter:PasswordChangeRequired` ("The Administrator must set a new password before this camera can be used; only that
password change is accepted until then."). The no-login actions (`GetDeviceInformation`, `GetCapabilities`, `GetServices`, `GetSystemDateAndTime`, `GetHostname`,...) are unaffected. The new password may not be `password`.

**Fault after repeated failed sign-ins** — 5 consecutive failures for one account from one address block it (60 s, doubling to 15 minutes; the Administrator 15 s, at most 30 s). While blocked the camera
refuses every request for that account without checking the password, **HTTP 429** with a SOAP `Sender` fault `ter:OperationProhibited` / `ter:TooManyAttempts` ("Too many failed sign-in attempts... temporarily blocked.
Try again later."). NVRs should back off; a correct password does not help until the block ends. The ONVIF `AuthFailureWarning*` configuration commands are not implemented.

**Fault for an authenticated account whose role is too low** — every ONVIF action carries a minimum user level (ONVIF Core §5.12.2.3 Table 7: `READ_SYSTEM`/`READ_MEDIA`
-> User, `ACTUATE` -> Operator, everything else, including anything not classified, -> Administrator). A request below it is answered **HTTP 400** with a
SOAP `Sender` fault `ter:OperationProhibited` / `ter:InsufficientUserLevel`, deliberately **not** `ter:NotAuthorized`/401 (which clients read as "wrong password"):
```xml
<SOAP-ENV:Fault><SOAP-ENV:Code><SOAP-ENV:Value>SOAP-ENV:Sender</SOAP-ENV:Value><SOAP-ENV:Subcode><SOAP-ENV:Value>ter:OperationProhibited</SOAP-ENV:Value>
<SOAP-ENV:Subcode><SOAP-ENV:Value>ter:InsufficientUserLevel</SOAP-ENV:Value></SOAP-ENV:Subcode></SOAP-ENV:Subcode></SOAP-ENV:Code>
<SOAP-ENV:Reason><SOAP-ENV:Text xml:lang="en">The authenticated user level is not permitted to perform this operation.</SOAP-ENV:Text></SOAP-ENV:Reason></SOAP-ENV:Fault>
```
Wrong username or password stays `HTTP 401` (`ter:NotAuthorized`). 

**GetServices** — request (`IncludeCapability` required, its value is otherwise ignored):
```xml
<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>
```
Response (per enabled service):
```xml
<tds:GetServicesResponse>
<tds:Service>
<tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace>
<tds:XAddr>https://192.0.2.50/onvif/device_service</tds:XAddr>
<tds:Version><tt:Major>02</tt:Major><tt:Minor>05</tt:Minor></tds:Version>
</tds:Service>
<tds:Service>
<tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>
<tds:XAddr>https://192.0.2.50/onvif/media_service</tds:XAddr>
<tds:Version><tt:Major>02</tt:Major><tt:Minor>60</tt:Minor></tds:Version>
</tds:Service>
</tds:GetServicesResponse>
```

**GetCapabilities** — request: `<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>`.
Response (per-category blocks conditionally included; shown with all present):
```xml
<tds:GetCapabilitiesResponse>
<tds:Capabilities>
<tt:Device>
<tt:XAddr>https://192.0.2.50/onvif/device_service</tt:XAddr>
<tt:Network>
<tt:IPFilter>false</tt:IPFilter>
<tt:ZeroConfiguration>true</tt:ZeroConfiguration>
<tt:IPVersion6>false</tt:IPVersion6>
<tt:DynDNS>false</tt:DynDNS>
<tt:Extension><tt:Dot11Configuration>false</tt:Dot11Configuration></tt:Extension>
</tt:Network>
<tt:System>
<tt:DiscoveryResolve>false</tt:DiscoveryResolve>
<tt:DiscoveryBye>true</tt:DiscoveryBye>
<tt:RemoteDiscovery>false</tt:RemoteDiscovery>
<tt:SystemBackup>false</tt:SystemBackup>
<tt:SystemLogging>false</tt:SystemLogging>
<tt:FirmwareUpgrade>true</tt:FirmwareUpgrade>
<tt:SupportedVersions><tt:Major>02</tt:Major><tt:Minor>05</tt:Minor></tt:SupportedVersions>
<tt:Extension>
<tt:HttpFirmwareUpgrade>true</tt:HttpFirmwareUpgrade>
<tt:HttpSystemBackup>false</tt:HttpSystemBackup>
<tt:HttpSystemLogging>false</tt:HttpSystemLogging>
<tt:HttpSupportInformation>false</tt:HttpSupportInformation>
</tt:Extension>
</tt:System>
<tt:IO>
<tt:InputConnectors>0</tt:InputConnectors>
<tt:RelayOutputs>0</tt:RelayOutputs>
<tt:Extension>
<tt:Auxiliary>true</tt:Auxiliary>
<tt:AuxiliaryCommands>octi:IRLampOn</tt:AuxiliaryCommands>
<tt:AuxiliaryCommands>octi:IRLampOff</tt:AuxiliaryCommands>
</tt:Extension>
</tt:IO>
<tt:Security>
<tt:TLS1.1>false</tt:TLS1.1>
<tt:TLS1.2>true</tt:TLS1.2>
<tt:OnboardKeyGeneration>false</tt:OnboardKeyGeneration>
<tt:AccessPolicyConfig>false</tt:AccessPolicyConfig>
<tt:X.509Token>false</tt:X.509Token>
<tt:SAMLToken>false</tt:SAMLToken>
<tt:KerberosToken>false</tt:KerberosToken>
<tt:RELToken>false</tt:RELToken>
<tt:Extension>
<tt:TLS1.0>false</tt:TLS1.0>
<tt:Extension><tt:Dot1X>false</tt:Dot1X><tt:RemoteUserHandling>false</tt:RemoteUserHandling></tt:Extension>
</tt:Extension>
</tt:Security>
</tt:Device>
<tt:Media>
<tt:XAddr>https://192.0.2.50/onvif/media_service</tt:XAddr>
<tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP><tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities>
<tt:Extension><tt:ProfileCapabilities><tt:MaximumNumberOfProfiles>3</tt:MaximumNumberOfProfiles></tt:ProfileCapabilities></tt:Extension>
</tt:Media>
<tt:Events>
<tt:XAddr>https://192.0.2.50/onvif/events_service</tt:XAddr>
<tt:WSPullPointSupport>true</tt:WSPullPointSupport>
<tt:WSSubscriptionPolicySupport>false</tt:WSSubscriptionPolicySupport>
<tt:WSPausableSubscriptionManagerInterfaceSupport>false</tt:WSPausableSubscriptionManagerInterfaceSupport>
</tt:Events>
<tt:Analytics>
<tt:XAddr>https://192.0.2.50/onvif/analytics_service</tt:XAddr>
<tt:RuleSupport>true</tt:RuleSupport>
<tt:AnalyticsModuleSupport>false</tt:AnalyticsModuleSupport>
</tt:Analytics>
<tt:Imaging><tt:XAddr>https://192.0.2.50/onvif/imaging_service</tt:XAddr></tt:Imaging>
</tds:Capabilities>
</tds:GetCapabilitiesResponse>
```

**GetServiceCapabilities**:
```xml
<tds:GetServiceCapabilitiesResponse>
<tds:Capabilities>
<tds:Network IPFilter="false" ZeroConfiguration="true" IPVersion6="false" DynDNS="false" Dot11Configuration="false" Dot1XConfigurations="0" HostnameFromDHCP="false" NTP="1" DHCPv6="false"/>
<tds:Security TLS1.0="false" TLS1.1="false" TLS1.2="true" OnboardKeyGeneration="false" AccessPolicyConfig="false" DefaultAccessPolicy="false" Dot1X="false" RemoteUserHandling="false" X.509Token="false" SAMLToken="false" KerberosToken="false" UsernameToken="true" HttpDigest="true" RELToken="false" JsonWebToken="false" MaxUsers="1" MaxUserNameLength="32" MaxPasswordLength="32" SecurityPolicies="Basic256Sha256" MaxPasswordHistory="0" HashingAlgorithms="SHA-256"/>
<tds:System DiscoveryResolve="false" DiscoveryBye="true" RemoteDiscovery="false" SystemBackup="false" SystemLogging="false" FirmwareUpgrade="true" HttpFirmwareUpgrade="true" HttpSystemBackup="false" HttpSystemLogging="false" HttpSupportInformation="false" StorageConfiguration="false" MaxStorageConfigurations="0" NetworkConfigNotSupported="false" UserConfigNotSupported="true"/>
<tds:Misc AuxiliaryCommands="octi:IRLampOn octi:IRLampOff octi:ColorLampOn octi:ColorLampOff"/>
</tds:Capabilities>
</tds:GetServiceCapabilitiesResponse>
```
> `Dot1XConfigurations`/`NTP` are numeric-string attributes sitting among boolean ones
>; `SupportedEAPMethods` is omitted entirely when not applicable
> (`:130-133,157`) rather than emitted empty.

**SendAuxiliaryCommand** — request:
```xml
<tds:SendAuxiliaryCommand><tds:AuxiliaryCommand>tt:IRLampOn</tds:AuxiliaryCommand></tds:SendAuxiliaryCommand>
```
Response for a status-query command (`octi:` prefix + `|` separator
built only for the three `*_Status` cases — a plain set-command like `IRLampOn` echoes back
unmodified, no `octi:` prefix):
```xml
<tds:SendAuxiliaryCommandResponse><tt:AuxiliaryCommandResponse>octi:IRLamp|On</tt:AuxiliaryCommandResponse></tds:SendAuxiliaryCommandResponse>
```

**Not implemented** (answered with a SOAP Fault):
`SetHostname`, `SetDNS`, `SetNTP`, `IPAddressFilter*`, `AccessPolicy*`, `StorageConfiguration*`,
`RelayOutput*`, `GeoLocation*`, `PasswordComplexity*/History*`, `AuthFailureWarning*`,
`DynamicDNS*`, `SystemBackup`/`Restore`, `SystemLog`.

## 1.2 Media service v10

> **The camera runs three physical video streams, but ONVIF describes only two.** `Profile_1` (main) and `Profile_2` (sub) are the complete ONVIF set. A third stream (fixed 720p, RTSPS only, port 556) has no ONVIF profile and no `GetStreamUri` equivalent; it is offered through the proprietary REST API, `POST /nuraeye/live-stream-uri` with `profile_token: "Profile_3"` (see [camera-rest-api.md](camera-rest-api.md)).

**GetProfile** / **GetProfiles** — request: `<trt:GetProfile><trt:ProfileToken>Profile_1</trt:ProfileToken></trt:GetProfile>`.
Response (note this
generator uses its own narrower envelope, only `SOAP-ENV`/`trt`/`tt` namespaces):
```xml
<trt:GetProfileResponse>
<trt:Profile token="Profile_1" fixed="true">
<tt:Name>MainStream</tt:Name>
<tt:VideoSourceConfiguration token="VideoSourceConfig_1">
<tt:Name>VideoSourceConfig</tt:Name>
<tt:UseCount>2</tt:UseCount>
<tt:SourceToken>VideoSource_1</tt:SourceToken>
<tt:Bounds x="0" y="0" width="1920" height="1080"/>
</tt:VideoSourceConfiguration>
<tt:AudioSourceConfiguration token="AudioSourceConfig_1">
<tt:Name>AudioSourceConfig</tt:Name>
<tt:UseCount>2</tt:UseCount>
<tt:SourceToken>AudioSource_1</tt:SourceToken>
</tt:AudioSourceConfiguration>
<tt:AudioOutputConfiguration token="AudioOutputConfig_1">
<tt:Name>AudioOutputConfig</tt:Name>
<tt:UseCount>1</tt:UseCount>
<tt:OutputToken>AudioOutput_1</tt:OutputToken>
<tt:OutputLevel>70</tt:OutputLevel>
</tt:AudioOutputConfiguration>
<tt:VideoEncoderConfiguration token="VideoEncoderConfig_1" encoding="H264">
<tt:Name>VideoEncoderConfig1</tt:Name>
<tt:UseCount>1</tt:UseCount>
<tt:SessionTimeout>PT0S</tt:SessionTimeout>
<tt:Encoding>H264</tt:Encoding>
<tt:H264><tt:GovLength>30</tt:GovLength><tt:H264Profile>High</tt:H264Profile></tt:H264>
<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
<tt:Quality>5</tt:Quality>
<tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit><tt:BitrateLimit>4096</tt:BitrateLimit><tt:EncodingInterval>1</tt:EncodingInterval></tt:RateControl>
<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type></tt:Address><tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>
</tt:VideoEncoderConfiguration>
<tt:VideoAnalyticsConfiguration token="VideoAnalyticsConfig_1"><tt:Name>VideoAnalyticsConfig</tt:Name><tt:UseCount>1</tt:UseCount></tt:VideoAnalyticsConfiguration>
</trt:Profile>
</trt:GetProfileResponse>
```
`GetProfiles` repeats this content per profile under root tag `trt:Profiles` in the normal
shared envelope. `CreateProfile` and `DeleteProfile` are always refused: the profile set is fixed.

**GetStreamUri** — request:
```xml
<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>Profile_1</trt:ProfileToken></trt:GetStreamUri>
```
Response (scheme is `rtsp://` on non-HTTPS builds,
`rtsps://`/`https://` tunnel depending on build+`Protocol`):
```xml
<trt:GetStreamUriResponse>
<trt:MediaUri>
<tt:Uri>rtsps://192.0.2.50:8554/live/ch0</tt:Uri>
<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
<tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
<tt:Timeout>PT0S</tt:Timeout>
</trt:MediaUri>
</trt:GetStreamUriResponse>
```

**GetSnapshotUri**:
```xml
<trt:GetSnapshotUriResponse>
<trt:MediaUri>
<tt:Uri>https://192.0.2.50/onvif/snapshot/ch0.jpg</tt:Uri>
<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
<tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
<tt:Timeout>PT0S</tt:Timeout>
</trt:MediaUri>
</trt:GetSnapshotUriResponse>
```

**SetSynchronizationPoint** — request: `<trt:SetSynchronizationPoint><trt:ProfileToken>Profile_1</trt:ProfileToken></trt:SetSynchronizationPoint>`. Forces an I-frame. Response: empty.

**SetVideoEncoderConfiguration** — request (Media v1 uses a nested `tt:H264` element for `GovLength`/`Profile`):
```xml
<trt:SetVideoEncoderConfiguration>
<trt:Configuration token="VideoEncoderConfig_1">
<tt:Name>VideoEncoderConfig1</tt:Name>
<tt:Encoding>H264</tt:Encoding>
<tt:H264><tt:GovLength>60</tt:GovLength><tt:H264Profile>High</tt:H264Profile></tt:H264>
<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
<tt:Quality>6</tt:Quality>
<tt:RateControl><tt:FrameRateLimit>20</tt:FrameRateLimit><tt:BitrateLimit>6144</tt:BitrateLimit></tt:RateControl>
</trt:Configuration>
<trt:ForcePersistence>true</trt:ForcePersistence>
</trt:SetVideoEncoderConfiguration>
```
Response: empty.

**GetVideoEncoderConfiguration** / **GetVideoEncoderConfigurations** /
**GetCompatibleVideoEncoderConfigurations** — these three actions return the same content and differ only in the root and response tag names:
```xml
<trt:GetVideoEncoderConfigurationResponse>
<trt:Configuration token="VideoEncoderConfig_1">
<tt:Name>VideoEncoderConfig1</tt:Name>
<tt:UseCount>1</tt:UseCount>
<tt:Encoding>H264</tt:Encoding>
<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
<tt:Quality>5</tt:Quality>
<tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit><tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl>
<tt:H264><tt:GovLength>30</tt:GovLength><tt:H264Profile>High</tt:H264Profile></tt:H264>
<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type></tt:Address><tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>
<tt:SessionTimeout>PT0S</tt:SessionTimeout>
</trt:Configuration>
</trt:GetVideoEncoderConfigurationResponse>
```
(For non-H264 encodings, `tt:GovLength` is still emitted but hardcoded to `0`.)

**GetVideoEncoderConfigurationOptions** — **the exact resolutions differ by which video encoder configuration token is queried and, for the main stream only, by sensor model.** `ResolutionsAvailable` always lists the stream's native
resolution first, then its lower option(s) if any:

*Main stream (`VideoEncoderConfig_1`, `Profile_1`), GC4663 sensor (native ~4 MP plus a ~2 MP option; HDR-mode default frame rate 20 fps):*
```xml
<trt:GetVideoEncoderConfigurationOptionsResponse>
<trt:Options>
<tt:QualityRange><tt:Min>1</tt:Min><tt:Max>5</tt:Max></tt:QualityRange>
<tt:H264>
<tt:ResolutionsAvailable><tt:Width>2560</tt:Width><tt:Height>1440</tt:Height></tt:ResolutionsAvailable>
<tt:ResolutionsAvailable><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:ResolutionsAvailable>
<tt:GovLengthRange><tt:Min>20</tt:Min><tt:Max>100</tt:Max></tt:GovLengthRange>
<tt:FrameRateRange><tt:Min>1</tt:Min><tt:Max>20</tt:Max></tt:FrameRateRange>
<tt:EncodingIntervalRange><tt:Min>1</tt:Min><tt:Max>1</tt:Max></tt:EncodingIntervalRange>
<tt:H264ProfilesSupported>Baseline</tt:H264ProfilesSupported>
<tt:H264ProfilesSupported>Main</tt:H264ProfilesSupported>
<tt:H264ProfilesSupported>High</tt:H264ProfilesSupported>
</tt:H264>
<tt:Extension><tt:H264><tt:BitrateRange><tt:Min>32</tt:Min><tt:Max>8192</tt:Max></tt:BitrateRange></tt:H264></tt:Extension>
</trt:Options>
</trt:GetVideoEncoderConfigurationOptionsResponse>
```
`GovLengthRange`/`FrameRateRange` scale directly with
(`{fps, fps*5}` and `{1, fps}` respectively) — on a
build (24fps, no HDR mode) the same two `ResolutionsAvailable` entries appear, but
`GovLengthRange` is `24`-`120` and `FrameRateRange` is `1`-`24` instead. On
builds, the main stream's native resolution is already
1920×1080 — there's no lower distinct option to offer, so this same response carries exactly one
`ResolutionsAvailable` (1920×1080) instead of two (`FrameRateRange`/`GovLengthRange` follow
those sensors' own, /).

*Sub stream (`VideoEncoderConfig_2`, `Profile_2`) — every sensor build (native 720p, plus a
360p option):*
```xml
<trt:GetVideoEncoderConfigurationOptionsResponse>
<trt:Options>
<tt:QualityRange><tt:Min>1</tt:Min><tt:Max>5</tt:Max></tt:QualityRange>
<tt:H264>
<tt:ResolutionsAvailable><tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:ResolutionsAvailable>
<tt:ResolutionsAvailable><tt:Width>640</tt:Width><tt:Height>360</tt:Height></tt:ResolutionsAvailable>
<tt:GovLengthRange><tt:Min>15</tt:Min><tt:Max>75</tt:Max></tt:GovLengthRange>
<tt:FrameRateRange><tt:Min>1</tt:Min><tt:Max>15</tt:Max></tt:FrameRateRange>
<tt:EncodingIntervalRange><tt:Min>1</tt:Min><tt:Max>1</tt:Max></tt:EncodingIntervalRange>
<tt:H264ProfilesSupported>Baseline</tt:H264ProfilesSupported>
<tt:H264ProfilesSupported>Main</tt:H264ProfilesSupported>
<tt:H264ProfilesSupported>High</tt:H264ProfilesSupported>
</tt:H264>
<tt:Extension><tt:H264><tt:BitrateRange><tt:Min>32</tt:Min><tt:Max>8192</tt:Max></tt:BitrateRange></tt:H264></tt:Extension>
</trt:Options>
</trt:GetVideoEncoderConfigurationOptionsResponse>
```
(One `trt:Options` block per enabled encoding; a non-H264 block omits `ResolutionsAvailable`/`H264ProfilesSupported` but still carries an empty `<tt:H264></tt:H264>` wrapper regardless of actual codec. `QualityRange`/`GovLengthRange`/`FrameRateRange`/`BitrateRange` above are the real values from 's `venc_cfg_options`, not the placeholder ranges the previous version of this example used — `GovLengthRange`/`FrameRateRange` scale with each stream's own configured frame rate, e.g..)

**H.265 encoding block (main stream, `VideoEncoderConfig_1`, GC4663 sensor)** — the second `trt:Options` block of the same response, immediately after the main-stream example above:
```xml
<trt:Options>
<tt:QualityRange><tt:Min>1</tt:Min><tt:Max>5</tt:Max></tt:QualityRange>
<tt:H264>
<tt:GovLengthRange><tt:Min>20</tt:Min><tt:Max>100</tt:Max></tt:GovLengthRange>
<tt:FrameRateRange><tt:Min>1</tt:Min><tt:Max>20</tt:Max></tt:FrameRateRange>
<tt:EncodingIntervalRange><tt:Min>1</tt:Min><tt:Max>1</tt:Max></tt:EncodingIntervalRange>
</tt:H264>
<tt:Extension><tt:H264><tt:BitrateRange><tt:Min>32</tt:Min><tt:Max>8192</tt:Max></tt:BitrateRange></tt:H264></tt:Extension>
</trt:Options>
```
For a non-H264 encoding there is no `ResolutionsAvailable` or `H264ProfilesSupported`, and the wrapper tag is still `<tt:H264>`: Media v1 has no `<tt:H265>` element (use Media2 for H.265). `FrameRateRange` is a real descending list from the stream's maximum frame rate down to 1, so `FrameRateRange.Min` is `1`.



**GetVideoSources**:
```xml
<trt:GetVideoSourcesResponse>
<trt:VideoSources token="VideoSource_1">
<tt:Framerate>15</tt:Framerate>
<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
<tt:Imaging/>
</trt:VideoSources>
</trt:GetVideoSourcesResponse>
```

**GetVideoSourceConfiguration(s)** / **GetCompatibleVideoSourceConfigurations**:
```xml
<trt:GetVideoSourceConfigurationResponse>
<trt:Configuration token="VideoSourceConfig_1">
<tt:Name>VideoSourceConfig</tt:Name>
<tt:UseCount>3</tt:UseCount>
<tt:SourceToken>VideoSource_1</tt:SourceToken>
<tt:Bounds x="0" y="0" width="1920" height="1080"/>
</trt:Configuration>
</trt:GetVideoSourceConfigurationResponse>
```

**GetAudioSources** / **GetAudioOutputs** (empty response if the camera has no microphone/speaker):
```xml
<trt:GetAudioSourcesResponse><trt:AudioSources token="AudioSource_1"><tt:Channels>1</tt:Channels></trt:AudioSources></trt:GetAudioSourcesResponse>
```
```xml
<trt:GetAudioOutputsResponse><trt:AudioOutputs token="AudioOutput_1"/></trt:GetAudioOutputsResponse>
```

**GetAudioSourceConfigurations** / **GetAudioOutputConfigurations**:
```xml
<trt:GetAudioSourceConfigurationsResponse><trt:Configurations token="AudioSourceConfig_1"><tt:Name>AudioSourceConfig</tt:Name><tt:UseCount>3</tt:UseCount><tt:SourceToken>AudioSource_1</tt:SourceToken></trt:Configurations></trt:GetAudioSourceConfigurationsResponse>
```
```xml
<trt:GetAudioOutputConfigurationsResponse><trt:Configurations token="AudioOutputConfig_1"><tt:Name>AudioOutputConfig</tt:Name><tt:UseCount>1</tt:UseCount><tt:OutputToken>AudioOutput_1</tt:OutputToken><tt:OutputLevel>70</tt:OutputLevel></trt:Configurations></trt:GetAudioOutputConfigurationsResponse>
```

**SetAudioOutputConfiguration** — request (only `token` + `OutputLevel` actually applied):
```xml
<trt:SetAudioOutputConfiguration><trt:Configuration token="AudioOutputConfig_1"><tt:Name>AudioOutputConfig</tt:Name><tt:OutputToken>AudioOutput_1</tt:OutputToken><tt:OutputLevel>85</tt:OutputLevel></trt:Configuration></trt:SetAudioOutputConfiguration>
```
Response: empty.

**GetAudioOutputConfigurationOptions** (the Media2 version returns the same body, see §1.3):
```xml
<trt:GetAudioOutputConfigurationOptionsResponse>
<trt:Options><tt:OutputTokensAvailable>AudioOutput_1</tt:OutputTokensAvailable><tt:OutputLevelRange><tt:Min>0</tt:Min><tt:Max>100</tt:Max></tt:OutputLevelRange></trt:Options>
</trt:GetAudioOutputConfigurationOptionsResponse>
```

**CreateOSD** / **SetOSD** — request:
```xml
<trt:SetOSD>
<trt:OSD token="OSDConfig_1">
<tt:VideoSourceConfigurationToken>VideoSourceConfig_1</tt:VideoSourceConfigurationToken>
<tt:Type>Text</tt:Type>
<tt:Position><tt:Type>Custom</tt:Type><tt:Pos x="0.20" y="-0.90"/></tt:Position>
<tt:TextString>
<tt:Type>DateAndTime</tt:Type>
<tt:DateFormat>M/d/yyyy</tt:DateFormat>
<tt:TimeFormat>h:mm:ss tt</tt:TimeFormat>
<tt:FontColor><tt:Color X="1.00" Y="1.00" Z="1.00" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/></tt:FontColor>
</tt:TextString>
</trt:OSD>
</trt:SetOSD>
```
`CreateOSD` response: `<trt:CreateOSDResponse><trt:OSDToken>OSDConfig_2</trt:OSDToken></trt:CreateOSDResponse>`.
`SetOSD` response: empty. Type/text-string-type are immutable once created.

**DeleteOSD** — request is `<trt:DeleteOSD><trt:OSDToken>OSDConfig_1</trt:OSDToken></trt:DeleteOSD>`, response empty.

**GetOSDs** / **GetOSD** (root tag `trt:OSDs` for GetOSDs, `trt:OSD` for GetOSD):
```xml
<trt:GetOSDsResponse>
<trt:OSDs token="OSDConfig_1">
<tt:VideoSourceConfigurationToken>VideoSourceConfig_1</tt:VideoSourceConfigurationToken>
<tt:Type>Text</tt:Type>
<tt:Position><tt:Type>Custom</tt:Type><tt:Pos x="0.20" y="-0.90"/></tt:Position>
<tt:TextString IsPersistentText="false">
<tt:FontSize>16</tt:FontSize>
<tt:Type>DateAndTime</tt:Type>
<tt:FontColor Transparent="0"><tt:Color X="1.00" Y="1.00" Z="1.00" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/></tt:FontColor>
<tt:DateFormat>M/d/yyyy</tt:DateFormat>
<tt:TimeFormat>h:mm:ss tt</tt:TimeFormat>
</tt:TextString>
</trt:OSDs>
</trt:GetOSDsResponse>
```

**GetOSDOptions** (truncated to one text-type example):
```xml
<trt:GetOSDOptionsResponse>
<trt:OSDOptions>
<tt:MaximumNumberOfOSDs Total="4" Image="0" PlainText="2" Date="1" Time="1" DateAndTime="1"/>
<tt:Type>Text</tt:Type>
<tt:PositionOption>UpperLeft</tt:PositionOption>
<tt:PositionOption>Custom</tt:PositionOption>
<tt:TextOption>
<tt:Type>PlainText</tt:Type>
<tt:Type>DateAndTime</tt:Type>
<tt:FontSizeRange><tt:Min>8</tt:Min><tt:Max>32</tt:Max></tt:FontSizeRange>
<tt:DateFormat>M/d/yyyy</tt:DateFormat>
<tt:TimeFormat>h:mm:ss tt</tt:TimeFormat>
<tt:FontColor><tt:Color><tt:ColorList X="1.00" Y="1.00" Z="1.00" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/></tt:Color><tt:Transparent><tt:Min>0</tt:Min><tt:Max>255</tt:Max></tt:Transparent></tt:FontColor>
</tt:TextOption>
</trt:OSDOptions>
</trt:GetOSDOptionsResponse>
```

**Not implemented:** `GetVideoSourceMode`/`SetVideoSourceMode`,
`GetVideoSourceConfigurationOptions`, `GetGuaranteedNumberOfVideoEncoderInstances`.

## 1.3 Media2 service ver20

**GetServiceCapabilities**:
```xml
<tr2:GetServiceCapabilitiesResponse>
<tr2:Capabilities SnapshotUri="true" Rotation="false" VideoSourceMode="false" OSD="true" TemporaryOSDText="false" Mask="true" SourceMask="false" WebRTC="1">
<tr2:ProfileCapabilities MaximumNumberOfProfiles="3"/>
<tr2:StreamingCapabilities RTPMulticast="false" RTP_RTSP_TCP="true" NonAggregateControl="false" RTSPStreaming="true" AutoStartMulticast="false" SecureRTSPStreaming="true"/>
<tr2:MediaSigningCapabilities MediaSigningSupported="false"/>
</tr2:Capabilities>
</tr2:GetServiceCapabilitiesResponse>
```

**GetVideoSourceConfigurations** — request: `<tr2:GetVideoSourceConfigurations><tr2:ConfigurationToken>VideoSourceConfig_1</tr2:ConfigurationToken></tr2:GetVideoSourceConfigurations>` (or `tr2:ProfileToken` — both optional). Response reuses the v1 snippet, root `tr2:Configurations`:
```xml
<tr2:GetVideoSourceConfigurationsResponse>
<tr2:Configurations token="VideoSourceConfig_1">
<tt:Name>VideoSourceConfig</tt:Name>
<tt:UseCount>3</tt:UseCount>
<tt:SourceToken>VideoSource_1</tt:SourceToken>
<tt:Bounds x="0" y="0" width="1920" height="1080"/>
</tr2:Configurations>
</tr2:GetVideoSourceConfigurationsResponse>
```
(empty response if neither token is supplied)

**GetAudioSourceConfigurations** / **GetAudioOutputConfigurations** — same as v1, `tr2:` prefixed, empty (not fault) if no mic/speaker.

**SetAudioOutputConfiguration** — request, same fields as v1 (only `token` + `OutputLevel`
actually applied), `tr2:` prefixed (behaves exactly like the Media v1 action, so a change made through either namespace is visible through the other and over WAN):
```xml
<tr2:SetAudioOutputConfiguration><tr2:Configuration token="AudioOutputConfig_1"><tt:Name>AudioOutputConfig</tt:Name><tt:OutputToken>AudioOutput_1</tt:OutputToken><tt:OutputLevel>85</tt:OutputLevel></tr2:Configuration></tr2:SetAudioOutputConfiguration>
```
Response: empty.

**GetAudioOutputConfigurationOptions** — same `OutputTokensAvailable`/`OutputLevelRange` shape as
v1, `tr2:` prefixed. Both versions return the same body, wrapped in `trt:` (Media v1) or `tr2:` (Media2) response elements:
```xml
<tr2:GetAudioOutputConfigurationOptionsResponse>
<tr2:Options><tt:OutputTokensAvailable>AudioOutput_1</tt:OutputTokensAvailable><tt:OutputLevelRange><tt:Min>0</tt:Min><tt:Max>100</tt:Max></tt:OutputLevelRange></tr2:Options>
</tr2:GetAudioOutputConfigurationOptionsResponse>
```

**GetVideoEncoderConfigurations** — Media2 carries `GovLength` and `Profile` as **root-tag attributes** instead of a nested `tt:H264` block. The default encoder is H.265 on all three streams, and `Profile` for an H.265 configuration is `"Main"` (the only valid H.265 profile on this firmware), not `"High"`:
```xml
<tr2:GetVideoEncoderConfigurationsResponse>
<tr2:Configurations token="VideoEncoderConfig_1" encoding="H265" GovLength="30" Profile="Main">
<tt:Name>VideoEncoderConfig1</tt:Name>
<tt:UseCount>1</tt:UseCount>
<tt:Encoding>H265</tt:Encoding>
<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
<tt:Quality>5</tt:Quality>
<tt:RateControl ConstantBitRate="false"><tt:FrameRateLimit>15</tt:FrameRateLimit><tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl>
<tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type></tt:Address><tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast>
</tr2:Configurations>
</tr2:GetVideoEncoderConfigurationsResponse>
```
> Media2 always emits a plain `<tt:Encoding>` for any codec, so it is the right choice for H.265 clients; Media v1 still labels non-H264 configurations as H.264 (see Known limitations).

**GetVideoEncoderConfigurationOptions** — attributes live on the `tr2:Options` tag itself
one `tr2:Options` block per enabled encoding (the same values as Media v1's `GetVideoEncoderConfigurationOptions` above: real per-stream, per-sensor resolution and frame-rate values).
`FrameRatesSupported` is every individual supported rate, space-separated, counting down from
the stream's max fps to 1. Main
stream (`VideoEncoderConfig_1`), build (20fps HDR default), both enabled
codecs shown (both codecs offer the same resolution list):
```xml
<tr2:GetVideoEncoderConfigurationOptionsResponse>
<tr2:Options GovLengthRange="20 100" FrameRatesSupported="20 19 18 17 16 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1" ProfilesSupported="Baseline Main High" ConstantBitRateSupported="true">
<tt:Encoding>H264</tt:Encoding>
<tt:QualityRange><tt:Min>1</tt:Min><tt:Max>5</tt:Max></tt:QualityRange>
<tt:BitrateRange><tt:Min>32</tt:Min><tt:Max>1536</tt:Max></tt:BitrateRange>
<tt:ResolutionsAvailable><tt:Width>2560</tt:Width><tt:Height>1440</tt:Height></tt:ResolutionsAvailable>
<tt:ResolutionsAvailable><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:ResolutionsAvailable>
</tr2:Options>
<tr2:Options GovLengthRange="20 100" FrameRatesSupported="20 19 18 17 16 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1" ProfilesSupported="Main" ConstantBitRateSupported="true">
<tt:Encoding>H265</tt:Encoding>
<tt:QualityRange><tt:Min>1</tt:Min><tt:Max>5</tt:Max></tt:QualityRange>
<tt:BitrateRange><tt:Min>32</tt:Min><tt:Max>1536</tt:Max></tt:BitrateRange>
<tt:ResolutionsAvailable><tt:Width>2560</tt:Width><tt:Height>1440</tt:Height></tt:ResolutionsAvailable>
<tt:ResolutionsAvailable><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:ResolutionsAvailable>
</tr2:Options>
</tr2:GetVideoEncoderConfigurationOptionsResponse>
```
Same per-sensor/per-stream variation as the Media v1 example above (`GC4653`: `GovLengthRange`
`24 120`, `FrameRatesSupported` counts down from 24; `IMX662`/`F37`/sub-stream: their own frame-rate and resolution lists, and
only a single resolution for H265 too on those sensors, mirroring H264); see the Media v1 example above.

**SetVideoEncoderConfiguration** — request (`GovLength`/`Profile` as **attributes** on
`tr2:Configuration`):
```xml
<tr2:SetVideoEncoderConfiguration>
<tr2:Configuration token="VideoEncoderConfig_1" GovLength="60" Profile="High" ConstantBitRate="false">
<tt:Name>VideoEncoderConfig1</tt:Name>
<tt:Encoding>H264</tt:Encoding>
<tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
<tt:Quality>6</tt:Quality>
<tt:RateControl><tt:FrameRateLimit>20</tt:FrameRateLimit><tt:BitrateLimit>6144</tt:BitrateLimit></tt:RateControl>
</tr2:Configuration>
</tr2:SetVideoEncoderConfiguration>
```
Response: empty.

**GetProfiles** — request: `<tr2:GetProfiles><tr2:Token>Profile_1</tr2:Token><tr2:Type>All</tr2:Type></tr2:GetProfiles>` (both optional, default `All`). Response wraps configs in a
`tr2:Configurations` element per profile:
```xml
<tr2:GetProfilesResponse>
<tr2:Profiles token="Profile_1" fixed="true">
<tt:Name>MainStream</tt:Name>
<tr2:Configurations>
<tr2:VideoSource token="VideoSourceConfig_1">...</tr2:VideoSource>
<tr2:AudioSource token="AudioSourceConfig_1">...</tr2:AudioSource>
<tr2:AudioOutput token="AudioOutputConfig_1">...</tr2:AudioOutput>
<tr2:VideoEncoder token="VideoEncoderConfig_1" encoding="H264" GovLength="30" Profile="High">...</tr2:VideoEncoder>
<tr2:Analytics token="VideoAnalyticsConfig_1"><tt:Name>VideoAnalyticsConfig</tt:Name><tt:UseCount>1</tt:UseCount></tr2:Analytics>
</tr2:Configurations>
</tr2:Profiles>
</tr2:GetProfilesResponse>
```

**GetSnapshotUri** / **GetStreamUri** — flatter shape than v1, no `MediaUri` wrapper:
```xml
<tr2:GetSnapshotUriResponse><tt:Uri>https://192.0.2.50/onvif/snapshot/ch0.jpg</tt:Uri></tr2:GetSnapshotUriResponse>
```
```xml
<tr2:GetStreamUriResponse><tt:Uri>rtsps://192.0.2.50:8554/live/ch0</tt:Uri></tr2:GetStreamUriResponse>
```

**CreateOSD** / **SetOSD** — same request shape as v1, `tr2:` prefix:
```xml
<tr2:SetOSD>
<tr2:OSD token="OSDConfig_1">
<tt:VideoSourceConfigurationToken>VideoSourceConfig_1</tt:VideoSourceConfigurationToken>
<tt:Type>Text</tt:Type>
<tt:Position><tt:Type>UpperLeft</tt:Type></tt:Position>
<tt:TextString><tt:Type>Plain</tt:Type><tt:PlainText>Front Door</tt:PlainText></tt:TextString>
</tr2:OSD>
</tr2:SetOSD>
```
`CreateOSD` response: `<tr2:CreateOSDResponse><tr2:OSDToken>OSDConfig_2</tr2:OSDToken></tr2:CreateOSDResponse>`.

**GetOSDs** — root tag `tr2:OSDs`, same body shape as v1's example above.

**GetMaskOptions**:
```xml
<tr2:GetMaskOptionsResponse>
<tr2:Options RectangleOnly="true" SingleColorOnly="false">
<tr2:MaxMasks>4</tr2:MaxMasks>
<tr2:MaxPoints>4</tr2:MaxPoints>
<tr2:Types>Color</tr2:Types>
<tr2:Color><tt:ColorList X="0.00" Y="0.00" Z="0.00" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/></tr2:Color>
</tr2:Options>
</tr2:GetMaskOptionsResponse>
```
> The color entries inside `tr2:Color` use `tt:ColorList`/`tt:ColorspaceRange`, a mixed-namespace quirk of this firmware.

**CreateMask** / **SetMask** — request:
```xml
<tr2:SetMask>
<tr2:Mask token="Mask_1">
<tr2:ConfigurationToken>VideoSourceConfig_1</tr2:ConfigurationToken>
<tr2:Polygon>
<tt:Point x="-0.500000" y="-0.500000"/>
<tt:Point x="0.500000" y="-0.500000"/>
<tt:Point x="0.500000" y="0.500000"/>
<tt:Point x="-0.500000" y="0.500000"/>
</tr2:Polygon>
<tr2:Type>Color</tr2:Type>
<tr2:Color X="0.00" Y="0.00" Z="0.00" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/>
<tr2:Enabled>true</tr2:Enabled>
</tr2:Mask>
</tr2:SetMask>
```
`CreateMask` response: `<tr2:CreateMaskResponse><tr2:Token>Mask_2</tr2:Token></tr2:CreateMaskResponse>`.

**GetMasks**:
```xml
<tr2:GetMasksResponse>
<tr2:Masks token="Mask_1">
<tr2:ConfigurationToken>VideoSourceConfig_1</tr2:ConfigurationToken>
<tr2:Polygon><tt:Point x="-0.500000" y="-0.500000"/><tt:Point x="0.500000" y="-0.500000"/><tt:Point x="0.500000" y="0.500000"/><tt:Point x="-0.500000" y="0.500000"/></tr2:Polygon>
<tr2:Type>Color</tr2:Type>
<tr2:Color X="0.00" Y="0.00" Z="0.00" Colorspace="http://www.onvif.org/ver10/colorspace/RGB"/>
<tr2:Enabled>true</tr2:Enabled>
</tr2:Masks>
</tr2:GetMasksResponse>
```

OSD/Mask actions fault if `media.capabilities.osd`/`media2.capabilities.mask` are disabled at
build time. **Not implemented:** `GetVideoSourceMode`/`SetVideoSourceMode`,
`GetVideoSourceConfigurationOptions`, `SetVideoSourceConfiguration`, `DeleteOSD`/`DeleteMask`
request bodies not independently confirmed (single generic-token parse, see Coverage gaps).

## 1.4 Imaging service

**GetServiceCapabilities**:
```xml
<timg:GetServiceCapabilitiesResponse><timg:Capabilities ImageStabilization="false" Presets="false" AdaptablePresets="false"/></timg:GetServiceCapabilitiesResponse>
```

**GetImagingSettings** — request: `<timg:GetImagingSettings><timg:VideoSourceToken>VideoSource_1</timg:VideoSourceToken></timg:GetImagingSettings>`.
Response:
```xml
<timg:GetImagingSettingsResponse>
<timg:ImagingSettings>
<tt:Brightness>50.00</tt:Brightness>
<tt:ColorSaturation>50.00</tt:ColorSaturation>
<tt:Contrast>50.00</tt:Contrast>
<tt:Exposure><tt:Mode>AUTO</tt:Mode></tt:Exposure>
<tt:IrCutFilter>AUTO</tt:IrCutFilter>
<tt:Sharpness>50.00</tt:Sharpness>
<tt:WideDynamicRange><tt:Mode>OFF</tt:Mode></tt:WideDynamicRange>
<tt:WhiteBalance><tt:Mode>AUTO</tt:Mode></tt:WhiteBalance>
</timg:ImagingSettings>
</timg:GetImagingSettingsResponse>
```
> When `Exposure.Mode=Manual`, `tt:ExposureTime`/`tt:Gain` are additionally emitted inside
> `tt:Exposure` (`:294-301`); when `WideDynamicRange.Mode=On`, `tt:Level` is added (`:325-329`);
> when `WhiteBalance.Mode=Manual`, `tt:CrGain`/`tt:CbGain` are added (`:345-352`). The `"AUTO"`/`"OFF"` mode strings follow the ONVIF enumerations.

**SetImagingSettings** — request (all fields optional/partial-update):
```xml
<timg:SetImagingSettings>
<timg:VideoSourceToken>VideoSource_1</timg:VideoSourceToken>
<timg:ImagingSettings>
<tt:Brightness>60</tt:Brightness>
<tt:Contrast>55</tt:Contrast>
<tt:IrCutFilter>OFF</tt:IrCutFilter>
<tt:WideDynamicRange><tt:Mode>ON</tt:Mode><tt:Level>40</tt:Level></tt:WideDynamicRange>
<tt:Exposure><tt:Mode>MANUAL</tt:Mode><tt:ExposureTime>10000</tt:ExposureTime><tt:Gain>20</tt:Gain></tt:Exposure>
<tt:WhiteBalance><tt:Mode>MANUAL</tt:Mode><tt:CrGain>1.20</tt:CrGain><tt:CbGain>1.10</tt:CbGain></tt:WhiteBalance>
</timg:ImagingSettings>
<timg:ForcePersistence>true</timg:ForcePersistence>
</timg:SetImagingSettings>
```
`IrCutFilter=Off` also triggers. Response: empty.

**GetOptions**:
```xml
<timg:GetOptionsResponse>
<timg:ImagingOptions>
<tt:Brightness><tt:Min>0.00</tt:Min><tt:Max>100.00</tt:Max></tt:Brightness>
<tt:ColorSaturation><tt:Min>0.00</tt:Min><tt:Max>100.00</tt:Max></tt:ColorSaturation>
<tt:Contrast><tt:Min>0.00</tt:Min><tt:Max>100.00</tt:Max></tt:Contrast>
<tt:Exposure>
<tt:Mode>AUTO</tt:Mode>
<tt:Mode>MANUAL</tt:Mode>
<tt:ExposureTime><tt:Min>100.00</tt:Min><tt:Max>40000.00</tt:Max></tt:ExposureTime>
<tt:Gain><tt:Min>0.00</tt:Min><tt:Max>100.00</tt:Max></tt:Gain>
</tt:Exposure>
<tt:IrCutFilterModes>ON</tt:IrCutFilterModes>
<tt:IrCutFilterModes>OFF</tt:IrCutFilterModes>
<tt:IrCutFilterModes>AUTO</tt:IrCutFilterModes>
<tt:Sharpness><tt:Min>0.00</tt:Min><tt:Max>100.00</tt:Max></tt:Sharpness>
<tt:WideDynamicRange>
<tt:Mode>OFF</tt:Mode>
<tt:Mode>ON</tt:Mode>
<tt:Level><tt:Min>0.00</tt:Min><tt:Max>100.00</tt:Max></tt:Level>
</tt:WideDynamicRange>
<tt:WhiteBalance>
<tt:Mode>AUTO</tt:Mode>
<tt:Mode>MANUAL</tt:Mode>
<tt:YrGain><tt:Min>0.00</tt:Min><tt:Max>4.00</tt:Max></tt:YrGain>
<tt:YbGain><tt:Min>0.00</tt:Min><tt:Max>4.00</tt:Max></tt:YbGain>
</tt:WhiteBalance>
</timg:ImagingOptions>
</timg:GetOptionsResponse>
```
(`tt:WideDynamicRange` block omitted entirely if the device reports zero WDR modes — `:218-233`.)

**Not implemented:** Presets, `Move`/`Stop`/`GetMoveOptions`/`GetStatus` (PTZ-style focus/iris).

## 1.5 Analytics service

**GetServiceCapabilities**:
```xml
<tan:GetServiceCapabilitiesResponse><tan:Capabilities AnalyticsModuleSupport="false" AnalyticsModuleOptionsSupported="false" RuleSupport="true" RuleOptionsSupported="true" CellBasedSceneDescriptionSupported="false" SupportedMetadata="false"/></tan:GetServiceCapabilitiesResponse>
```

**GetSupportedRules** — request: `<tan:GetSupportedRules><tan:ConfigurationToken>VideoAnalyticsConfig_1</tan:ConfigurationToken></tan:GetSupportedRules>`.
Response:
```xml
<tan:GetSupportedRulesResponse>
<tan:SupportedRules Limit="4">
<tt:RuleDescription Name="PersonDetector" fixed="false" maxInstances="1">
<tt:Parameters><tt:SimpleItemDescription Name="Sensitivity" Type="xs:int"/></tt:Parameters>
<tt:Messages IsProperty="false">
<tt:Source><tt:SimpleItemDescription Name="VideoSourceConfigurationToken" Type="tt:ReferenceToken"/></tt:Source>
<tt:Data><tt:SimpleItemDescription Name="PersonCount" Type="xs:int"/></tt:Data>
<tt:ParentTopic>tns1:RuleEngine/PersonDetector/Person</tt:ParentTopic>
</tt:Messages>
</tt:RuleDescription>
</tan:SupportedRules>
</tan:GetSupportedRulesResponse>
```

**GetRuleOptions**:
```xml
<tan:GetRuleOptionsResponse><tan:RuleOptions Name="Sensitivity" RuleType="PersonDetector"><tt:IntRange><tt:Min>1</tt:Min><tt:Max>10</tt:Max></tt:IntRange></tan:RuleOptions></tan:GetRuleOptionsResponse>
```

**GetRules**:
```xml
<tan:GetRulesResponse>
<tt:Rule Name="MyPersonDetectorRule" Type="PersonDetector"><tt:Parameters><tt:SimpleItem Name="Sensitivity" Value="7"/></tt:Parameters></tt:Rule>
</tan:GetRulesResponse>
```

**CreateRules** — request:
```xml
<tan:CreateRules>
<tan:ConfigurationToken>VideoAnalyticsConfig_1</tan:ConfigurationToken>
<tan:Rule><tt:Rule Name="MyPersonDetectorRule" Type="PersonDetector"><tt:Parameters><tt:SimpleItem Name="Sensitivity" Value="7"/></tt:Parameters></tt:Rule></tan:Rule>
</tan:CreateRules>
```
Response: empty. `PersonDetector` type toggles `bsp_camera_setObjectDetection(true)`.

**DeleteRules** — request: `<tan:DeleteRules><tan:ConfigurationToken>VideoAnalyticsConfig_1</tan:ConfigurationToken><tan:RuleName>MyPersonDetectorRule</tan:RuleName></tan:DeleteRules>`. Response: empty; `PersonDetector` type toggles `bsp_camera_setObjectDetection(false)`.

`ModifyAnalyticsModules`/`ModifyRules`/`CreateAnalyticsModules`/`DeleteAnalyticsModules`/
`GetAnalyticsModules`/`GetAnalyticsModuleOptions`/`GetSupportedAnalyticsModules` follow the same
shapes as their Rules counterparts above. **Not implemented:** `GetSupportedMetadata`.

## 1.6 Events service

**GetEventProperties**:
```xml
<tev:GetEventPropertiesResponse>
<tev:TopicNamespaceLocation>http://www.onvif.org/onvif/ver10/topics/topicns.xml</tev:TopicNamespaceLocation>
<wsnt:FixedTopicSet>true</wsnt:FixedTopicSet>
<wstop:TopicSet>
<tns1:RuleEngine>
<PersonDetector>
<Person wstop:topic="true">
<tt:MessageDescription IsProperty="false">
<tt:Source><tt:SimpleItemDescription Name="VideoSourceConfigurationToken" Type="tt:ReferenceToken"/></tt:Source>
<tt:Data><tt:SimpleItemDescription Name="PersonCount" Type="xs:int"/></tt:Data>
</tt:MessageDescription>
</Person>
</PersonDetector>
</tns1:RuleEngine>
</wstop:TopicSet>
<wsnt:TopicExpressionDialect>http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet</wsnt:TopicExpressionDialect>
<tev:MessageContentFilterDialect>http://www.onvif.org/ver10/tev/messageContentFilter/ItemFilter</tev:MessageContentFilterDialect>
</tev:GetEventPropertiesResponse>
```
(`PersonDetector`/`Person` sub-tags are derived by splitting each rule's `ParentTopic` string on
`/` — `:154-224` — so the exact element names track configured rules, not a fixed vocabulary.)

**CreatePullPointSubscription** — request: `<tev:CreatePullPointSubscription><tev:InitialTerminationTime>PT1H</tev:InitialTerminationTime></tev:CreatePullPointSubscription>` (both fields optional, default 1h, min 60s).
Response:
```xml
<tev:CreatePullPointSubscriptionResponse>
<tev:SubscriptionReference><wsa5:Address>https://192.0.2.50/onvif/events_service?subscriptionId=1</wsa5:Address></tev:SubscriptionReference>
<wsnt:CurrentTime>2026-07-31T10:15:05Z</wsnt:CurrentTime>
<wsnt:TerminationTime>2026-07-31T11:15:05Z</wsnt:TerminationTime>
</tev:CreatePullPointSubscriptionResponse>
```
(the `?subscriptionId=` suffix is what 's fix in strips off before
service-path matching on subsequent `PullMessages`/`Renew`/`Unsubscribe` calls.)

**PullMessages** — request, POSTed to `<events_url>?subscriptionId=1`: `<tev:PullMessages><tev:Timeout>PT2S</tev:Timeout><tev:MessageLimit>1</tev:MessageLimit></tev:PullMessages>` (Timeout clamped ≤10s, MessageLimit clamped ≤2).
Response — one `NotificationMessage` per event:
```xml
<tev:PullMessagesResponse>
<wsnt:NotificationMessage>
<wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/PersonDetector/Person</wsnt:Topic>
<wsnt:Message>
<tt:Message UtcTime="2026-07-31T10:15:03Z">
<tt:Source>
<tt:SimpleItem Name="VideoAnalyticsConfigurationToken" Value="VideoAnalyticsConfig_1"/>
<tt:SimpleItem Name="VideoSourceConfigurationToken" Value="VideoSourceConfig_1"/>
<tt:SimpleItem Name="Rule" Value="MyPersonDetectorRule"/>
</tt:Source>
<tt:Data><tt:SimpleItem Name="PersonCount" Value="1"/></tt:Data>
</tt:Message>
</wsnt:Message>
</wsnt:NotificationMessage>
<wsnt:CurrentTime>2026-07-31T10:15:05Z</wsnt:CurrentTime>
<wsnt:TerminationTime>2026-07-31T11:15:05Z</wsnt:TerminationTime>
</tev:PullMessagesResponse>
```
A day/night change notification instead
carries topic `tns1:VideoSource/ImagingSettings/IrCutFilterChanged`, one `Source` SimpleItem
(`VideoSourceConfigurationToken`), and one `Data` SimpleItem `Name="IrCutFilter"
Value="ON"/"OFF"`. Unknown `subscriptionId` → bare HTTP 404, no body.

**Renew** — request (to `?subscriptionId=1`): `<tev:Renew><tev:TerminationTime>PT30M</tev:TerminationTime></tev:Renew>`.
Response:
```xml
<tev:RenewResponse><wsnt:CurrentTime>2026-07-31T10:20:00Z</wsnt:CurrentTime><wsnt:TerminationTime>2026-07-31T10:50:00Z</wsnt:TerminationTime></tev:RenewResponse>
```

**Unsubscribe** — request (to `?subscriptionId=1`): `<tev:Unsubscribe/>`. Response: empty; unknown `subscriptionId` → bare 404, no body.

**Not implemented:** `AddEventBroker`/`DeleteEventBroker`/`GetEventBrokers`, `Seek`,
`SetSynchronizationPoint` (Events).

---

## 1.7 Recording, Search & ReplayControl services (Profile G)

These three services let an NVR/VMS **discover and play back** clips the camera has already recorded. Recording is not controlled over ONVIF: creating or configuring a recording job is not supported (recording is always on and managed by the camera's own storage pipeline). The one write action is `DeleteRecording`, which removes a single stored clip (Administrator only, see below). Playback uses `GetReplayUri` with `PLAY`/`Range` (§ 4.1 below).

### Recording service

**GetServiceCapabilities**:
```xml
<trc:GetServiceCapabilitiesResponse>
<trc:Capabilities DynamicRecordings="false" DynamicTracks="false" Options="true"
MaxRecordings="500" MaxRecordingJobs="0"/>
</trc:GetServiceCapabilitiesResponse>
```
`DynamicRecordings`/`DynamicTracks` are always `false` — no client-driven recording-job creation
is supported (see below). `MaxRecordings` mirrors the same (500)
cap `GetRecordings`/'s REST equivalent already enforces.

**GetRecordings** — no request body. Response, one `trc:RecordingItem` per stored clip:
```xml
<trc:GetRecordingsResponse>
<trc:RecordingItem>
<trc:RecordingToken>1788529649</trc:RecordingToken>
<trc:Value>
<tt:RecordingConfiguration>
<tt:Source>
<tt:SourceId>VideoSource_1</tt:SourceId>
<tt:Name>Front Door</tt:Name>
<tt:Location>Porch</tt:Location>
</tt:Source>
<tt:Content>ObjectDetected</tt:Content>
<tt:MaximumRetentionTime>PT604800S</tt:MaximumRetentionTime>
</tt:RecordingConfiguration>
<trc:TrackList>
<trc:Track>
<trc:TrackToken>VideoTrack_1</trc:TrackToken>
<tt:TrackConfiguration>
<tt:TrackType>Video</tt:TrackType>
<tt:Description>H.264 video track</tt:Description>
</tt:TrackConfiguration>
</trc:Track>
<trc:Track><!-- present only when this build has AUDIO_ENABLED -->
<trc:TrackToken>AudioTrack_1</trc:TrackToken>
<tt:TrackConfiguration>
<tt:TrackType>Audio</tt:TrackType>
<tt:Description>Audio track</tt:Description>
</tt:TrackConfiguration>
</trc:Track>
</trc:TrackList>
</trc:Value>
</trc:RecordingItem>
<!-- one item per stored clip, up to MP4_HELPER_MAX_RECORDINGS (500) -->
</trc:GetRecordingsResponse>
```
`RecordingToken` is the clip's `epoch_start` as a decimal string — the same identity the proprietary REST API uses for clips (`GET /nuraeye/recordings`). `tt:Content`
is a free-text trigger description, taken from the camera's event history for the clip's time window; it falls back to
`"Continuous recording"` when no event landed inside that window. If the clip count is very large the response is truncated rather than overflowing.

**GetRecordingOptions** — no request body (this device has no per-recording configurability to
report; the response is the same fixed shape for any/every recording). Response:
```xml
<trc:GetRecordingOptionsResponse>
<trc:Options>
<trc:Job><trc:Spare>0</trc:Spare></trc:Job>
<trc:Track><trc:SpareTotal>0</trc:SpareTotal><trc:SpareVideo>0</trc:SpareVideo>
<trc:SpareAudio>0</trc:SpareAudio><trc:SpareMetadata>0</trc:SpareMetadata></trc:Track>
</trc:Options>
</trc:GetRecordingOptionsResponse>
```
Always reports zero spare capacity — this device never accepts a client-created recording job
regardless.

#### DeleteRecording

Removes **one** stored clip — the same operation as the REST `POST /nuraeye/recordings/delete`, so both paths behave identically. `RecordingToken` is the
clip's UTC epoch-start decimal. **Administrator only** (the ONVIF default for Recording create/delete/set). Bulk delete stays on the REST call: ONVIF deletes one recording per request.

**Request:**
```xml
<trc:DeleteRecording xmlns:trc="http://www.onvif.org/ver10/recording/wsdl">
  <trc:RecordingToken>1755962400</trc:RecordingToken>
</trc:DeleteRecording>
```

**Response:**
```xml
<trc:DeleteRecordingResponse></trc:DeleteRecordingResponse>
```

**Faults**: unknown or non-numeric
token → HTTP 400 `ter:InvalidArgVal` / `ter:NoRecording` (recording.wsdl); the clip still being
recorded → HTTP 400 `ter:OperationProhibited` / `ter:RecordingInProgress`; a non-Administrator →
`ter:InsufficientUserLevel`.

**Not implemented — explicit `ActionNotSupported` fault, not a silent no-op**
: `CreateRecording`, `SetRecordingConfiguration`, `CreateTrack`,
`DeleteTrack`, `SetTrackConfiguration`, `CreateRecordingJob`, `DeleteRecordingJob`,
`SetRecordingJobMode`.

### Search service

Job-polling model per the ONVIF spec: a `Find*` call starts a job and returns a `SearchToken`
immediately; the job itself already runs to completion synchronously before that response goes
out (this device has no background search worker — the whole "job" is one blocking scan), so
every subsequent `GetSearchState` for that token always reports `Completed` and every
`Get*SearchResults` call just pages through the already-fully-computed result set.

**GetServiceCapabilities**:
```xml
<tse:GetServiceCapabilitiesResponse>
<tse:Capabilities MetadataSearch="true" GeneralStartEvents="false" NLSearch="false"
ImageSearch="false"/>
</tse:GetServiceCapabilitiesResponse>
```

**FindRecordings** — request carries an optional `<tse:StartPoint>`/`<tse:EndPoint>` time range
(parsed leniently, missing tags tolerated) and a `<tse:Scope>` (accepted but not filtered on —
this device has exactly one recording source). Response
: `<tse:FindRecordingsResponse><tse:SearchToken>1</tse:SearchToken></tse:FindRecordingsResponse>`.

**GetRecordingSearchResults** — request: `<tse:GetRecordingSearchResults><tse:SearchToken>1</tse:SearchToken><tse:MaxResults>10</tse:MaxResults></tse:GetRecordingSearchResults>`.
Response, one `tt:RecordingInformation` per matched clip, paged via the job's own
`returned_count` cursor:
```xml
<tse:GetRecordingSearchResultsResponse>
<tse:ResultList>
<tt:RecordingInformation>
<tt:RecordingToken>1788529649</tt:RecordingToken>
<tt:EarliestRecording>2026-09-04T13:47:29Z</tt:EarliestRecording>
<tt:LatestRecording>2026-09-04T13:48:29Z</tt:LatestRecording>
<tt:Content>Continuous recording</tt:Content>
<tt:RecordingStatus>Stopped</tt:RecordingStatus>
<tt:Track>
<tt:TrackToken>VideoTrack_1</tt:TrackToken>
<tt:TrackType>Video</tt:TrackType>
<tt:DataFrom>2026-09-04T13:47:29Z</tt:DataFrom>
<tt:DataTo>2026-09-04T13:48:29Z</tt:DataTo>
</tt:Track>
</tt:RecordingInformation>
<!-- ... up to MaxResults ... -->
</tse:ResultList>
<tse:SearchState>Completed</tse:SearchState>
</tse:GetRecordingSearchResultsResponse>
```
`RecordingStatus` is `Recording` only for the one clip currently being actively written
(`p_clip->is_active`), `Stopped` for every completed clip.

**FindEvents**/**GetEventSearchResults** — same job-token shape as the recording pair above, over
this device's event-history ring buffer instead of clips. Each
result's `RecordingToken` attribute is left empty (`""`) — events aren't currently correlated
back to a specific clip token in this pass.

**GetSearchState**/**EndSearch** — `GetSearchState` always returns `Completed`
(searches complete immediately). `EndSearch` echoes the
current time back as `tse:Endpoint` and otherwise no-ops — there's no live job to
actually cancel.

**GetRecordingSummary** — aggregate earliest/latest recording time and
total count across all stored clips.

### ReplayControl service

**GetServiceCapabilities**:
```xml
<trp:GetServiceCapabilitiesResponse>
<trp:Capabilities ReversePlayback="false" RTP_RTSP_TCP="true"/>
<trp:SessionTimeoutRange>60</trp:SessionTimeoutRange>
</trp:GetServiceCapabilitiesResponse>
```
`RTP_RTSP_TCP="true"` — 's playback listener is TCP-interleaved only, same as
live view. `ReversePlayback` is always `false` (not supported). `SessionTimeoutRange` is a
`tt:FloatList` (min/max pair) per the real `replay.wsdl` — this device reports one fixed value as
both bounds, no per-session negotiation.

**GetReplayUri** — request: `<trp:GetReplayUri><trp:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trp:StreamSetup><trp:RecordingToken>1788529649</trp:RecordingToken></trp:GetReplayUri>`
(`StreamSetup` is optional/lenient, same rules as Media's own `GetStreamUri` — a missing
`Stream`/`Protocol` tag is tolerated, not rejected; `Protocol` accepts `RTSP`, or `HTTP`/
`RtspOverHttp` on an `USE_HTTPS` build to request the tunneled playback listener instead — see
§ 4.1 below for what that changes).
Response:
```xml
<trp:GetReplayUriResponse>
<trp:Uri>rtsps://192.0.2.50:558/playback/1788529649</trp:Uri>
</trp:GetReplayUriResponse>
```
(`rtsp://` on a non-`USE_HTTPS` build, or `https://192.0.2.50:559/playback/<token>` when the
request asked for the tunneled transport). A `RecordingToken` that does not resolve to a real clip → SOAP Fault `ter:NoConfig` (closest
existing fault code to "no such recording" — there's no dedicated one). **Every `GetReplayUri`
call evicts whichever playback client is currently connected, on either transport** — direct
product decision, this device does not support concurrent playback clients
(`PlaybackPipeline_EvictActiveSession`) — see § 4.1's own note on
what this means for a client mid-session.

**Not implemented:** none — both actions this service's WSDL defines are implemented.

---

## 2. WS-Discovery (UDP multicast, port `3702`)

Not part of the six SOAP services above — a separate protocol (WS-Discovery, not any ONVIF
service WSDL) that lets an NVR/VMS/mobile app find the camera on the LAN without knowing its IP
first. No HTTP, no auth: plain SOAP-over-UDP to/from multicast group
`239.255.255.250:3702`. 

**Hello** — sent once, unsolicited, at boot — announces the camera's presence without a client having to probe
first:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:SOAP-ENC="http://www.w3.org/2003/05/soap-encoding" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:wsdd="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:tdn="http://www.onvif.org/ver10/network/wsdl">
<SOAP-ENV:Body>
<wsdd:Hello>
<wsa:EndpointReference><wsa:Address>urn:uuid:12345678-90ab-cdef-1234-567890abcdef</wsa:Address></wsa:EndpointReference>
<wsdd:Types>tdn:Device tdn:NetworkVideoTransmitter</wsdd:Types>
<wsdd:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/Profile/Streaming onvif://www.onvif.org/Profile/T onvif://www.onvif.org/MAC/AA:BB:CC:DD:EE:FF onvif://www.onvif.org/hardware/NuraEye-Cam1 onvif://www.onvif.org/name/vizenlink-front-door onvif://www.onvif.org/location/Front%20Door</wsdd:Scopes>
<wsdd:XAddrs>https://192.0.2.50/onvif/device_service</wsdd:XAddrs>
<wsdd:MetadataVersion>1</wsdd:MetadataVersion>
</wsdd:Hello>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>
```
`Scopes` is rebuilt identically for Hello/ResolveMatches/ProbeMatches by a shared helper
 — only the enclosing tag's namespace prefix
differs between the three. Name/Location are URL-encoded into the `name=`/`location=` scope
entries. No **Bye** is ever sent — the camera doesn't announce a clean
shutdown, so an NVR/app relies on Hello (on next boot) or its own reachability timeout to notice
the camera left.

**Probe** — client → camera, multicast:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header>
<w:MessageID>uuid:3f9a2b7c-1e4d-4a6b-9c0d-8f21a4b5c6d7</w:MessageID>
<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
</e:Header>
<e:Body>
<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>
</e:Body>
</e:Envelope>
```
The camera parses only `MessageID` off any Probe/Resolve:
**`Types`/`Scopes` filtering is not implemented**; the camera answers every Probe regardless of
what it asks for. A client that wants to filter results does so itself after
receiving `ProbeMatches`.

**ProbeMatches** — camera → client, sent **unicast** back to the requester's address (not multicast), terse `s`/`a`/`d`
namespace prefixes, no `ReplyTo` header element:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:tdn="http://www.onvif.org/ver10/network/wsdl">
<s:Header>
<a:MessageID>uuid:8a1b2c3d-4e5f-6789-0abc-def123456789</a:MessageID>
<a:RelatesTo>uuid:3f9a2b7c-1e4d-4a6b-9c0d-8f21a4b5c6d7</a:RelatesTo>
<a:To s:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</a:To>
<a:Action s:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action>
<d:AppSequence InstanceId="0" MessageNumber="1"/>
</s:Header>
<s:Body>
<d:ProbeMatches>
<d:ProbeMatch>
<a:EndpointReference><a:Address>urn:uuid:12345678-90ab-cdef-1234-567890abcdef</a:Address></a:EndpointReference>
<d:Types>tdn:Device tdn:NetworkVideoTransmitter</d:Types>
<d:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/Profile/Streaming onvif://www.onvif.org/Profile/T onvif://www.onvif.org/MAC/AA:BB:CC:DD:EE:FF onvif://www.onvif.org/hardware/NuraEye-Cam1 onvif://www.onvif.org/name/vizenlink-front-door onvif://www.onvif.org/location/Front%20Door</d:Scopes>
<d:XAddrs>https://192.0.2.50/onvif/device_service</d:XAddrs>
<d:MetadataVersion>1</d:MetadataVersion>
</d:ProbeMatch>
</d:ProbeMatches>
</s:Body>
</s:Envelope>
```
`MessageNumber` is a monotonically increasing counter, shared across every Hello/ProbeMatches/ResolveMatches the camera
sends since boot, never reset per-request.

**Resolve** — same shape as Probe, but `<d:Probe>` becomes `<d:Resolve><a:EndpointReference>
<a:Address>urn:uuid:...</a:Address></a:EndpointReference></d:Resolve>`, asking the camera to
confirm one specific endpoint reference rather than "anything matching Types." The camera checks
the requested `Address` against its own endpoint UUID and silently drops the request (no
response sent) on a mismatch.

**ResolveMatches** — same fields as ProbeMatches, but verbose `SOAP-ENV`/`wsa`/`wsdd` namespace
prefixes (matching Hello's) and an extra `wsa:ReplyTo` header element ProbeMatches doesn't carry:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:SOAP-ENC="http://www.w3.org/2003/05/soap-encoding" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:wsdd="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:tdn="http://www.onvif.org/ver10/network/wsdl">
<SOAP-ENV:Header>
<wsa:MessageID>uuid:8a1b2c3d-4e5f-6789-0abc-def123456789</wsa:MessageID>
<wsa:RelatesTo>uuid:3f9a2b7c-1e4d-4a6b-9c0d-8f21a4b5c6d7</wsa:RelatesTo>
<wsa:ReplyTo SOAP-ENV:mustUnderstand="true"><wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address></wsa:ReplyTo>
<wsa:To SOAP-ENV:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>
<wsa:Action SOAP-ENV:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
<wsdd:AppSequence InstanceId="0" MessageNumber="2"/>
</SOAP-ENV:Header>
<SOAP-ENV:Body>
<wsdd:ResolveMatches>
<wsdd:ResolveMatch>
<wsa:EndpointReference><wsa:Address>urn:uuid:12345678-90ab-cdef-1234-567890abcdef</wsa:Address></wsa:EndpointReference>
<wsdd:Types>tdn:Device tdn:NetworkVideoTransmitter</wsdd:Types>
<wsdd:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/Profile/Streaming onvif://www.onvif.org/Profile/T onvif://www.onvif.org/MAC/AA:BB:CC:DD:EE:FF onvif://www.onvif.org/hardware/NuraEye-Cam1 onvif://www.onvif.org/name/vizenlink-front-door onvif://www.onvif.org/location/Front%20Door</wsdd:Scopes>
<wsdd:XAddrs>https://192.0.2.50/onvif/device_service</wsdd:XAddrs>
<wsdd:MetadataVersion>1</wsdd:MetadataVersion>
</wsdd:ResolveMatch>
</wsdd:ResolveMatches>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>
```
Note `wsa:Action`'s value is literally `.../discovery/ProbeMatches` even in a ResolveMatches
response, a long-standing quirk of this firmware.

**Bye** — never sent (see Hello above). 

---

## 3. `/snapshot`

Not a fixed path — matched by substring against each configured profile's
`p_snapshot_url_path`. Canonical discovery is ONVIF `GetSnapshotUri`/Media2 `GetSnapshotUri`
(§1.2/§1.3 above), which return the exact URI to GET.

**Request**:
```
GET /onvif/snapshot/ch0.jpg&timestamp=1785578400000 HTTP/1.1
Host: 192.0.2.50
Authorization: Digest username="admin", nonce="MTIzNDU2Nzg5MGFiY2RlZg==", created="2026-07-31T10:15:00.000Z", response="Z8n1c8b3s7fLp9k1x2y3zA4B5c6="
```
(`response = Base64(SHA1(Base64Decode(nonce) + created + password))`; the parser only greps for
`field="value"` substrings, so the leading scheme token itself isn't validated. Missing
header/field or mismatch → `401` with `WWW-Authenticate: Digest...`.)

**Success response**: `Content-Type: image/jpeg`, `Content-Length: <n>`, raw JPEG bytes
 Blocks up
to 5000ms for a frame; timeout/failure → `500`.

---

## 4. RTSP / RTSPS streams (ports `554`/`555`/`556`, `558`/`559`)

### Authentication (shared by live-view and playback streams)

The URI returned by `GetStreamUri`/Media2 `GetStreamUri` (§1.2/§1.3 above) itself requires
authentication once connected — this is a separate credential check from ONVIF SOAP's
WS-Security scheme (§ Shared envelope above) and from `/snapshot`'s scheme (§3 above): real RTSP
clients (VLC, ffmpeg, NVR/VMS software) only implement classic RFC 2617 HTTP Digest, not either
of those two ONVIF-specific schemes, so RTSP uses that standard instead
(implemented for plain RTSPS and for the RTSP-over-HTTPS tunnel used for `Protocol=HTTP`/`https://` URIs). Every method except `OPTIONS` is gated.

**Challenge** (server → client, on a request with a missing/invalid `Authorization` header):
```
RTSP/1.0 401 Unauthorized
CSeq: 2
WWW-Authenticate: Digest realm="ONVIF", nonce="a1b2c3...(32 hex chars)", algorithm=MD5
```
(realm matches, the same realm ONVIF SOAP and `/snapshot`
present — one consistent value across every auth challenge this device issues, even though the
hash/construction differs per scheme.)

**Authenticated retry** (client → server):
```
DESCRIBE rtsp://192.0.2.50:554/live/ch0 RTSP/1.0
CSeq: 3
Authorization: Digest username="admin", realm="ONVIF", nonce="a1b2c3...", uri="rtsp://192.0.2.50:554/live/ch0", response="9f86d0..."
```
`response = MD5(HA1:nonce:HA2)` where `HA1 = MD5(username:realm:password)` and
`HA2 = MD5(method:uri)` — the nonce and uri used in the comparison are read back from the
client's own header, not reconstructed independently, so verification only needs the request
method. The nonce is per-connection (freshly generated on `client_connected`), so a stale or
replayed nonce is rejected and re-challenged with a new one, same as a bad credential.

Credentials are the device's ONVIF user (`admin`/configured password) — pushed to both modules
at boot from the ONVIF user config, and refreshed live via
on every password-change path ('s `SetUser`, 's
`SetUserPassword`), which also force-disconnects any already-authenticated client so a changed
password can't still be used on an existing connection.



### 4.1 Playback streams — RTSP method reference (ports `558`/`559`)

 The URI `GetReplayUri` (§ 1.7 above) returns points at a **separate**
listener from live view's own `554`/`555`/`556` — port 558 (plain RTSPS) or port 559 (RTSP-over-HTTPS tunnel, selected with `Protocol=HTTP`/`RtspOverHttp` on the `GetReplayUri` request, § 1.7). Both share the same Digest-auth scheme
described above and the same single underlying playback engine — **only one playback client is ever
served at a time, across both ports and regardless of transport**; a fresh `GetReplayUri` always
evicts whatever was previously connected (§ 1.7's own `GetReplayUri` note).

This listener implements **exactly five** RTSP methods — confirmed directly from its own
`OPTIONS` response:
```
RTSP/1.0 200 OK
CSeq: 1
Public: OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN
```
Notably **no `PAUSE`, no `GET_PARAMETER`/`SET_PARAMETER`** — a client wanting pause-like behavior
has to implement it itself (remember the position, `TEARDOWN`, later re-`DESCRIBE`/`SETUP`/
`PLAY` at that position) rather than relying on any server-side primitive. 

| Method | What it does | Use case |
|---|---|---|
| `OPTIONS` | Returns the method list above. Only request allowed before auth. | Client capability probe before starting a session. |
| `DESCRIBE` | Extracts the `RecordingToken` from the URL path, binds that clip into the shared demuxer (`PlaybackBind_BindAndStartClip`, offset 0 — purely to read its real SPS/PPS/audio info), returns the SDP. `RecordingToken` not found → `404 Not Found`. | First request of a session — "I want to watch this clip," tells the client what codec/tracks exist. |
| `SETUP` | Negotiates the RTP interleaved-channel numbers for one track, called once per track — video gets `interleaved=0-1`, audio (when the SETUP URL's `streamid=1`) gets `interleaved=2-3`. Response: `Transport: RTP/AVP/TCP;unicast;interleaved=<n>-<n+1>`. | Per-track transport negotiation — standard RTSP, not playback-specific. |
| `PLAY` | Re-binds the clip (**always** a full close+reopen, even mid-session) and starts the shared playback engine feeding frames. A `Range: clock=<start>-<end>` header sets the playback offset. Out-of-range `start` (further into the clip than any clip could ever be, per ) → `457 Invalid Range`. | Two real use cases in one method: **(a)** the initial "start playing" after `SETUP`, and **(b) seeking** — there is no separate `SEEK` method; a seek is just another `PLAY` with a different `Range`, sent on the **same already-open connection**, reusing the existing `SETUP`'d RTP channels — no new `GetReplayUri`, no re-`DESCRIBE`, no re-`SETUP` needed. |
| `TEARDOWN` | Stops the playback engine, unbinds the demuxer. Also runs automatically on an unexpected disconnect (network drop, client crash), so a dropped connection never leaks the demuxer bind. | "I'm done watching" — clean session end. |

**Session tracking is effectively none** — every response (including `TEARDOWN`'s) sends back a
hardcoded literal `Session: 12345678`; there is no real per-client session
ID validated against, so a follow-up request is identified purely by arriving on the same TCP
connection, not by any `Session` header value.

**Intended use:** standard ONVIF Profile G playback for third-party NVR/VMS software.

---


## Known limitations

* **Media (ver10) labels every current video encoder configuration as H.264.** `GetVideoEncoderConfiguration`, `GetVideoEncoderConfigurations` and `GetCompatibleVideoEncoderConfigurations` always emit the `<tt:H264>` / `<tt:H264Profile>` elements for the current configuration, even when the stream is H.265 (only `GovLength` becomes `0`). A Media (ver10) client can therefore see `<tt:Encoding>H265</tt:Encoding>` next to an H.264 block. Use Media2 for H.265 streams; it reports the codec correctly.
* **Fixed profiles.** Exactly two ONVIF profiles exist (`Profile_1` main and `Profile_2` sub). `CreateProfile` and `DeleteProfile` are always refused.
* **Request examples.** `DeleteOSD`, `DeleteMask`, `GetOSDOptions`, `GetMaskOptions` and `GetCompatibleVideoEncoderConfigurations` are described by their response and behaviour. Build the request as the ONVIF WSDL specifies.
* **WS-Discovery filtering.** `Types` and `Scopes` in a Probe are ignored; the camera answers every Probe. Filter the `ProbeMatches` yourself.
* **Recording control.** Recording jobs cannot be created or configured over ONVIF (recording is always on and managed by the camera). Bulk deletion is not offered over ONVIF; use the REST API.
* **One playback client.** Only one playback (replay) client is served at a time; a new `GetReplayUri` evicts the previous client.
* **Imaging mode strings** (`AUTO`, `OFF`, and so on) follow the ONVIF enumerations; the structure around them is as shown in the examples.
