import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'camera_id_mismatch.dart';

/// This camera's LAN HTTPS endpoints (`/nuraeye`, `/onvif/*`) are served with a self-signed
/// certificate by design — there is no CA-issued cert for a LAN-only IP address, and no
/// certificate-pinning scheme exists yet. The existing Python reference tooling
/// (`testing_utilities/onvif_client.py`'s `_LegacyTLSAdapter`) already establishes this same
/// trust bypass for exactly this reason. `dart:io`'s default `HttpClient` rejects an untrusted
/// cert outright, which is the real cause of the "LAN unavailable" state seen when connecting
/// to a real camera — this client accepts it instead.
///
/// **Deliberately narrow:** this bypasses certificate *trust* only (the camera's cert isn't
/// signed by a CA this device trusts) — it does not disable TLS itself, and it is only ever
/// used for camera LAN connections, never a general-purpose HTTP client. If a future device
/// gets a real CA-issued cert, this can be made conditional on [CameraConnection] without
/// touching any `camera_api` call site (DESIGN.md §3's additive-evolution rule).
///
/// **Preserves outgoing header-name case (`BUG-005`, `BUG-008` Iteration 3)** — `package:http`'s
/// own `IOClient` calls `HttpHeaders.set(name, value)` without `preserveHeaderCase: true`, and
/// `dart:io` lowercases every custom header name by default when serializing a request. This
/// camera's embedded HTTP server (`bsp_http_server_getRequestHeader()` →
/// `httpd_request_get_header_field()`) looks up header names case-sensitively — first found for
/// `GET /snapshot`'s `Authorization` digest header (`BUG-005`), then again for the REST API's
/// `Authorization: Bearer <token>` header (`BUG-008` Iteration 3) once `NuraeyeClient` started
/// sending one. Fixed once, here, for every current and future `camera_api` LAN client that goes
/// through this factory — not per call site.
///
/// **Camera-ID check (`FR-MOB-116`, `FR-CF-155`):** pass [cameraId] (the camera's serial, `CameraConnection.thingName`) and every request
/// carries `X-VizenLink-Camera-Id: <cameraId>`; the camera refuses a request meant for another camera with HTTP 421, which this client
/// reports on [CameraIdMismatchNotifier] (the caller still gets the 421 response and treats it as a failed call). A null/empty [cameraId]
/// sends no header — the camera then performs no comparison.
http.Client createCameraHttpClient({String? cameraId}) => _CasePreservingHttpClient(cameraId);

class _CasePreservingHttpClient extends http.BaseClient {
  _CasePreservingHttpClient(String? cameraId)
      : _cameraId = (cameraId == null || cameraId.isEmpty) ? null : cameraId,
        _inner = HttpClient() {
    _inner.badCertificateCallback = (X509Certificate cert, String host, int port) => true;
  }

  final HttpClient _inner;
  final String? _cameraId;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final host = request.url.host;
    final port = request.url.hasPort ? request.url.port : 443;
    void reportUnreachable() {
      if (_cameraId != null) {
        CameraIdMismatchNotifier.report(CameraIdMismatchEvent(host: host, port: port, expectedCameraId: _cameraId, unreachable: true));
      }
    }

    // [FR-MOB-116, 2026-10-16] A camera that moved to another address leaves its old one silent, so no 421 ever comes back. Report that as
    // "unreachable" so the app can look for the camera by serial: on a refused/no-route socket error at once, and when no response headers arrive
    // for [_silentAfter] (the caller's own timeout is unchanged and still decides what the caller sees). The listener only checks and searches --
    // false alarms from a merely slow camera cost one cheap check.
    final silentTimer = Timer(_silentAfter, reportUnreachable);
    try {
      return await _send(request, host, port);
    } on SocketException {
      reportUnreachable();
      rethrow;
    } finally {
      silentTimer.cancel();
    }
  }

  /// No response headers for this long counts as "the address is silent" (see [send]).
  static const Duration _silentAfter = Duration(seconds: 8);

  Future<http.StreamedResponse> _send(http.BaseRequest request, String host, int port) async {
    final ioRequest = await _inner.openUrl(request.method, request.url);
    request.headers.forEach((name, value) {
      ioRequest.headers.set(name, value, preserveHeaderCase: true);
    });
    if (_cameraId != null && !request.headers.keys.any((k) => k.toLowerCase() == cameraIdHeaderName.toLowerCase())) {
      ioRequest.headers.set(cameraIdHeaderName, _cameraId, preserveHeaderCase: true);
    }

    if (request is http.Request && request.bodyBytes.isNotEmpty) {
      ioRequest.contentLength = request.bodyBytes.length;
      ioRequest.add(request.bodyBytes);
    } else if (request.contentLength != null) {
      ioRequest.contentLength = request.contentLength!;
    }

    final ioResponse = await ioRequest.close();
    if (ioResponse.statusCode == cameraIdMismatchStatus && _cameraId != null) {
      CameraIdMismatchNotifier.report(CameraIdMismatchEvent(host: host, port: port, expectedCameraId: _cameraId));
    }
    final headers = <String, String>{};
    ioResponse.headers.forEach((name, values) => headers[name] = values.join(', '));

    return http.StreamedResponse(
      ioResponse,
      ioResponse.statusCode,
      contentLength: ioResponse.contentLength == -1 ? null : ioResponse.contentLength,
      headers: headers,
      isRedirect: ioResponse.isRedirect,
      persistentConnection: ioResponse.persistentConnection,
      reasonPhrase: ioResponse.reasonPhrase,
      request: request,
    );
  }

  @override
  void close() => _inner.close(force: true);
}
