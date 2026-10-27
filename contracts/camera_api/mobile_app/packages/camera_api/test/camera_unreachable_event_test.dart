import 'dart:async';
import 'dart:io';

import 'package:camera_api/camera_api.dart';
import 'package:test/test.dart';

/// `FR-MOB-116` (2026-10-16): a request that cannot connect is reported as an *unreachable* event so the app can look for a camera that moved.
void main() {
  test('a refused connection is reported as unreachable for the camera id, and still throws to the caller', () async {
    final probe = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = probe.port;
    await probe.close(); // nothing listens on this port any more
    final events = <CameraIdMismatchEvent>[];
    final sub = CameraIdMismatchNotifier.events.listen(events.add);
    final client = createCameraHttpClient(cameraId: 'VZL-CAM-000042');
    await expectLater(
      () => client.get(Uri.https('127.0.0.1:$port', '/nuraeye/ping')),
      throwsA(isA<Exception>()),
    );
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(events.length, 1);
    expect(events.single.unreachable, isTrue);
    expect(events.single.expectedCameraId, 'VZL-CAM-000042');
    expect(events.single.host, '127.0.0.1');
    expect(events.single.port, port);
    await sub.cancel();
    client.close();
  });

  test('no camera id, no event (a generic client, or a camera that was never identified)', () async {
    final probe = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = probe.port;
    await probe.close();
    final events = <CameraIdMismatchEvent>[];
    final sub = CameraIdMismatchNotifier.events.listen(events.add);
    final client = createCameraHttpClient();
    await expectLater(() => client.get(Uri.https('127.0.0.1:$port', '/x')), throwsA(isA<Exception>()));
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(events, isEmpty);
    await sub.cancel();
    client.close();
  });

  test('a normal answer reports nothing', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((r) {
      r.response
        ..write('ok')
        ..close();
    });
    final events = <CameraIdMismatchEvent>[];
    final sub = CameraIdMismatchNotifier.events.listen(events.add);
    final client = createCameraHttpClient(cameraId: 'VZL-CAM-000042');
    final resp = await client.get(Uri.http('127.0.0.1:${server.port}', '/x'));
    expect(resp.statusCode, 200);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(events, isEmpty);
    await sub.cancel();
    client.close();
    await server.close(force: true);
  });
}
