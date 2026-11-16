---
quick_id: 261113-q9c
status: complete
date: 2026-11-13
commit: none (working tree only)
---

# Summary: live snapshot is stored on the NVR and shown in the Gallery

## Changed
- `web/src/features/live/VideoTile.tsx`: the snapshot button and the right-click "Take snapshot" now save a JPEG to the recorder via `POST /api/v1/playback/snapshot` and refresh the Gallery list. No file is downloaded. Source is the live video frame when WebRTC is playing, otherwise the camera's own high-profile snapshot. Failures show a toast (the old code swallowed them, and produced a black image when the video was not playing).
- No backend or API change.

## Verified
- Chromium against a simulated camera: toast shown, Gallery count +1, no browser download, stored file is a real JPEG (62,967 bytes), "Open Gallery" navigates to the Gallery.
- Vitest 439 passed, typecheck, gates, build OK.

## Not verified
- A real camera with live WebRTC video (the video-frame path); the simulated camera exercises the camera-snapshot path.

## Open: manual recording (not built)
The old VMS had a Record button on the single-camera view (5-minute limit with "extend", stops when leaving the page). The NVR has nothing equivalent. Not built in this task because it touches the recording path and cannot be verified without a real camera stream; needs owner decisions (see session reply).
