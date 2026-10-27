import 'dart:async';

/// HTTP header carrying the camera's unique id (its serial number, `CameraConnection.thingName`) on every LAN request to a NuraEye
/// camera — `FR-MOB-116` / `FR-CF-155`. The camera compares it with its own serial before routing and authentication and answers a
/// mismatch with HTTP 421; a request without the header is never refused (generic ONVIF clients). Not sent on RTSP/RTSPS requests.
const String cameraIdHeaderName = 'X-VizenLink-Camera-Id';

/// HTTP status the camera uses for "this request was addressed to a different camera" (`FR-CF-155`).
const int cameraIdMismatchStatus = 421;

/// A LAN camera answered 421: the request carried the id of one camera but reached another (a router handed the first camera's IP to a
/// different device). Never shown to the user — the app listens for these and silently re-discovers the camera by serial
/// (`CameraAddressRecovery`, app layer); on WAN the camera simply shows as offline.
class CameraIdMismatchEvent {
  const CameraIdMismatchEvent({required this.host, required this.port, required this.expectedCameraId, this.unreachable = false});

  /// True when the stored address did not answer at all (connection refused, no route, or no response headers for several seconds) instead of
  /// answering 421. The camera may simply be off, or it may have moved to another address (2026-10-16): the listener first checks whether the
  /// stored address still answers as this camera before it searches the network.
  final bool unreachable;

  /// The address that answered 421 (now believed to belong to another camera).
  final String host;
  final int port;

  /// The id the request was addressed to — the camera that has to be found again.
  final String expectedCameraId;

  @override
  String toString() => 'CameraIdMismatchEvent($host:$port expected $expectedCameraId${unreachable ? ', unreachable' : ''})';
}

/// Process-wide broadcast of [CameraIdMismatchEvent]s, fed by [createCameraHttpClient]'s client whenever a response is 421. Pure Dart so
/// `camera_api` stays UI-free; whoever owns the stored camera list (the app) subscribes.
class CameraIdMismatchNotifier {
  CameraIdMismatchNotifier._();

  static final StreamController<CameraIdMismatchEvent> _controller = StreamController<CameraIdMismatchEvent>.broadcast();

  static Stream<CameraIdMismatchEvent> get events => _controller.stream;

  static void report(CameraIdMismatchEvent event) {
    if (!_controller.isClosed && _controller.hasListener) {
      _controller.add(event);
    }
  }
}
