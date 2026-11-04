# Phase 06: Camera Settings - Technical Research & Wire Protocols

## Protocols & Endpoint Mapping

### 1. Device Identity & Information (SET-01, SET-07)
- **Read Device Information:**
  - ONVIF Device service `GetDeviceInformation`: returns `Manufacturer`, `Model`, `FirmwareVersion`, `SerialNumber`, `HardwareId`.
- **Identity (Name & Location):**
  - ONVIF Scopes: `SetScopes` with `onvif://www.onvif.org/name/{urlencoded}` and `onvif://www.onvif.org/location/{urlencoded}`.
- **Time Zone:**
  - Catalog of supported timezones: NuraEye REST `/nuraeye/network/timezones` or standard Olson database.
  - Setting timezone: ONVIF Device service `SetSystemDateAndTime` (time zone string).
- **Camera Password:**
  - ONVIF Device service `SetUser`: updates password for user `admin`.
  - NVR updates its locally stored credential secret for that camera.

### 2. Video Encoder Settings (SET-02, SET-08)
- **Profiles Discovery:**
  - ONVIF Media2 `GetProfiles`: returns profiles (`Profile_1`, `Profile_2`, `Profile_3`) and their `VideoEncoderConfiguration` tokens.
- **Configuration & Options:**
  - `GetVideoEncoderConfigurations`: returns current resolution (`Width`, `Height`), `Encoding` (H264 / H265), `Quality`, `RateControl` (BitrateLimit, FrameRateLimit), and encoding profile.
  - `GetVideoEncoderConfigurationOptions`: returns ranges for FrameRate, Bitrate, Quality, supported Resolutions list, and supported Encodings.
  - `SetVideoEncoderConfiguration`: sends the full configuration structure targeting the specified token.

### 3. Imaging & ISP Settings (SET-03, SET-08)
- **Day/Night Mode:**
  - ONVIF Imaging service `GetImagingSettings` / `SetImagingSettings`: `IrCutFilterMode` (`AUTO`, `ON`, `OFF`).
  - Options: `GetImagingOptions` → `IrCutFilterModes`.
- **Night Vision Type:**
  - NuraEye REST `/nuraeye/video/night-vision`: types `grey`, `color`, `smart`.
  - Flags: `colorCapable`, `smartCapable`.
- **WDR (Wide Dynamic Range):**
  - ONVIF Imaging `WideDynamicRange`: `Mode` (`ON`/`OFF`), `Level` (0-100).
  - Gate: `ImagingOptions.wdrSupported`. Note: toggling WDR mode on certain sensors reboots the camera.
- **Image Quality (ISP sliders):**
  - ONVIF Imaging: `Brightness`, `ColorSaturation`, `Contrast`, `Sharpness`, `Exposure` mode/time/gain, `WhiteBalance`.
- **Mirror/Flip:**
  - NuraEye REST `/nuraeye/video/mirror-flip`: `off`, `mirror`, `flip`, `both`.
- **Anti-Flicker:**
  - NuraEye REST `/nuraeye/video/anti-flicker`: `50Hz`, `60Hz`, `Auto`.

### 4. OSD (On-Screen Display) Overlays (SET-04)
- ONVIF Media2 OSD service: `GetOSDs`, `SetOSD`, `CreateOSD`, `DeleteOSD`, `GetOSDOptions`.
- Supported types: DateAndTime (timestamp) and Plain (text).

### 5. Device Management: Reboot & Factory Reset (SET-05, SET-06)
- **Reboot:**
  - ONVIF Device service `SystemReboot`. Triggers async restart (~5s delay).
- **Factory Reset:**
  - ONVIF Device service `SetSystemFactoryDefault`:
    - `Soft`: erases user configuration (imaging, names, OSD, etc.) while preserving network setup.
    - `Hard`: erases all configuration including network credentials (reverts to AP mode). Requires double-confirmation dialog in UI and Operator/Owner role.

