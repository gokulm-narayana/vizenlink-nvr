import 'dart:async';
import 'dart:io';

import 'package:camera_api/camera_api.dart';
import 'package:http/http.dart' as http;
import 'package:test/test.dart';

/// `FR-MOB-116` / `FR-CF-155`: every LAN request to a NuraEye camera carries `X-VizenLink-Camera-Id` (the camera's serial), the header
/// keeps its exact case on the wire (the camera looks headers up case-sensitively, `BUG-005`/`BUG-008`), a 421 reply is reported to
/// [CameraIdMismatchNotifier], and WAN commands carry `camera_id`. As in `case_preserving_http_client_test.dart` a raw `ServerSocket`
/// is used because only it shows the literal bytes on the wire.

void main() {
  test('createCameraHttpClient(cameraId:) sends X-VizenLink-Camera-Id verbatim on the wire', () async {
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final rawFuture = server.first.then((socket) async {
      final bytes = <int>[];
      await for (final chunk in socket) {
        bytes.addAll(chunk);
        if (String.fromCharCodes(bytes).contains('\r\n\r\n')) break;
      }
      socket.add('HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'.codeUnits);
      await socket.flush();
      await socket.close();
      return String.fromCharCodes(bytes);
    });
    final client = createCameraHttpClient(cameraId: 'VZL-CAM-000001');
    addTearDown(client.close);
    unawaited(client.get(Uri.http('127.0.0.1:${server.port}', '/p')).catchError((_) => http.Response('', 200)));
    final raw = await rawFuture.timeout(const Duration(seconds: 5));
    await server.close();
    expect(raw, contains('X-VizenLink-Camera-Id: VZL-CAM-000001'));
    expect(raw, isNot(contains('x-vizenlink-camera-id')));
  });

  test('no cameraId (or empty) sends no header at all', () async {
    for (final id in <String?>[null, '']) {
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final rawFuture = server.first.then((socket) async {
        final bytes = <int>[];
        await for (final chunk in socket) {
          bytes.addAll(chunk);
          if (String.fromCharCodes(bytes).contains('\r\n\r\n')) break;
        }
        socket.add('HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'.codeUnits);
        await socket.flush();
        await socket.close();
        return String.fromCharCodes(bytes);
      });
      final client = createCameraHttpClient(cameraId: id);
      addTearDown(client.close);
      unawaited(client.get(Uri.http('127.0.0.1:${server.port}', '/p')).catchError((_) => http.Response('', 200)));
      final raw = await rawFuture.timeout(const Duration(seconds: 5));
      await server.close();
      expect(raw.toLowerCase(), isNot(contains('camera-id')), reason: 'cameraId: "$id"');
    }
  });

  test('a 421 reply is reported once on CameraIdMismatchNotifier with the host and the expected id', () async {
    final events = <CameraIdMismatchEvent>[];
    final sub = CameraIdMismatchNotifier.events.listen(events.add);
    addTearDown(sub.cancel);

    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    unawaited(server.first.then((socket) async {
      final bytes = <int>[];
      await for (final chunk in socket) {
        bytes.addAll(chunk);
        if (String.fromCharCodes(bytes).contains('\r\n\r\n')) break;
      }
      socket.add('HTTP/1.1 421 Misdirected Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'.codeUnits);
      await socket.flush();
      await socket.close();
    }));
    final client = createCameraHttpClient(cameraId: 'VZL-CAM-000001');
    addTearDown(client.close);
    final response = await client.get(Uri.http('127.0.0.1:${server.port}', '/nuraeye/health'));
    await server.close();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(response.statusCode, 421, reason: 'the caller still gets the 421 and treats it as a failed call');
    expect(events, hasLength(1));
    expect(events.single.host, '127.0.0.1');
    expect(events.single.expectedCameraId, 'VZL-CAM-000001');
  });

  test('a 421 without a cameraId (nothing was addressed) is not reported', () async {
    final events = <CameraIdMismatchEvent>[];
    final sub = CameraIdMismatchNotifier.events.listen(events.add);
    addTearDown(sub.cancel);
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    unawaited(server.first.then((socket) async {
      await socket.first;
      socket.add('HTTP/1.1 421 Misdirected Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'.codeUnits);
      await socket.close();
    }));
    final client = createCameraHttpClient();
    addTearDown(client.close);
    await client.get(Uri.http('127.0.0.1:${server.port}', '/x')).catchError((_) => http.Response('', 421));
    await server.close();
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(events, isEmpty);
  });

  test('CameraConnection.copyWithHost keeps everything except the host', () {
    const c = CameraConnection(
        host: '192.168.1.10', username: 'admin', password: 'pw', thingName: 'VZL-CAM-000001', macAddress: 'AA:BB:CC:DD:EE:FF');
    final moved = c.copyWithHost('192.168.1.99');
    expect(moved.host, '192.168.1.99');
    expect(moved.thingName, 'VZL-CAM-000001');
    expect(moved.macAddress, 'AA:BB:CC:DD:EE:FF');
    expect(moved.username, 'admin');
    expect(moved.identityKey, c.identityKey, reason: 'the MAC keeps the identity stable across the address change');
  });
}
