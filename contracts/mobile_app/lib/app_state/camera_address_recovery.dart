import 'dart:async';

import 'package:camera_api/camera_api.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_multicast_lock/flutter_multicast_lock.dart';

import 'camera_network.dart';
import 'camera_settings_cache.dart';
import 'homes_controller.dart';

/// Silent LAN self-healing for a camera whose IP address was handed to a
/// different device (`FR-MOB-116`). Ported from the senior engineer's
/// reference app (`nuraeye-rt` `features/onboarding/camera_address_recovery.dart`).
///
/// Every LAN request carries the camera's serial (`X-VizenLink-Camera-Id`,
/// see [CameraNetwork.forConnection]); a different device that now holds the
/// address answers HTTP 421, which `createCameraHttpClient` reports on
/// [CameraIdMismatchNotifier]. This listens for those events and, with
/// nothing shown to the user, finds the camera again by serial (WS-Discovery
/// multicast first, the unicast subnet sweep as fallback; each candidate is
/// asked for its `GetDeviceInformation` serial) and updates the saved
/// address. If the camera can't be found, or two devices claim the serial,
/// nothing changes and the next attempt waits longer (backoff), so a missing
/// camera can't cause a scan loop. WAN needs no recovery: it is addressed by
/// thing name.
///
/// **Also when the old address is simply silent (2026-10-16):** a camera that
/// was moved usually leaves its old address empty, so no 421 ever comes back.
/// A request that could not connect, or got no response headers for several
/// seconds, is reported as an *unreachable* event
/// (`CameraIdMismatchEvent.unreachable`); the Dashboard reports its failed
/// checks the same way ([noteUnreachable]). For those the stored address is
/// asked for its serial first (cheap): if it still answers as this camera,
/// nothing is searched (it is just busy or off); if not, the network is
/// searched as above — but only on Wi-Fi/Ethernet, never for a placeholder
/// address (`cloud-<serial>`, a camera restored from the cloud that has not
/// been found yet; the user-initiated [locate] covers that), and never faster
/// than the backoff.
///
/// One deliberate difference from the reference: candidates are probed with
/// **blank** credentials, not the camera's saved password — the serial query
/// answers without a login, and a saved password must never be sent to some
/// other device on the network (that is exactly the bug this exists to fix).
class CameraAddressRecovery {
  CameraAddressRecovery({
    required this.cameras,
    required this.updateHost,
    Future<List<WsDiscoveryCandidate>> Function({required bool thorough})?
    discover,
    Future<String?> Function(WsDiscoveryCandidate candidate)? readSerial,
    DateTime Function()? now,
    Future<bool> Function()? isOnLan,
    this.verifiedFor = const Duration(seconds: 60),
    this.baseBackoff = const Duration(seconds: 30),
    this.maxBackoff = const Duration(minutes: 10),
  }) : _discover = discover ?? _defaultDiscover,
       _readSerial = readSerial ?? _defaultReadSerial,
       _now = now ?? DateTime.now,
       _isOnLan = isOnLan ?? _defaultIsOnLan;

  /// Wires recovery to [homes]: reads saved connections from it and writes a
  /// recovered address back (dropping pooled state for the old address).
  factory CameraAddressRecovery.forHomes(HomesController homes) {
    return CameraAddressRecovery(
      cameras: () => [
        for (final home in homes.value.homes)
          for (final camera in home.cameras) ?camera.connection,
      ],
      updateHost: ({required cameraId, required oldHost, required newHost}) {
        for (final home in homes.value.homes) {
          for (final camera in home.cameras) {
            if (camera.thingName == cameraId && camera.host == oldHost) {
              homes.updateCamera(
                camera.id,
                (current) => current.copyWith(host: newHost),
              );
            }
          }
        }
        CameraNetwork.evictHost(oldHost);
        NetworkAnswerCache.clearForHost(oldHost);
        NuraeyeClient.clearSessionFor(oldHost);
      },
    );
  }

  /// The saved connections to watch.
  final List<CameraConnection> Function() cameras;

  /// Writes a recovered address back.
  final void Function({
    required String cameraId,
    required String oldHost,
    required String newHost,
  })
  updateHost;
  final Future<List<WsDiscoveryCandidate>> Function({required bool thorough})
  _discover;
  final Future<String?> Function(WsDiscoveryCandidate candidate) _readSerial;
  final DateTime Function() _now;
  final Future<bool> Function() _isOnLan;

  /// After the stored address has just answered as the right camera, further
  /// "unreachable" reports for it are ignored for this long.
  final Duration verifiedFor;
  final Map<String, DateTime> _verifiedUntil = {};

  /// First wait after a failed recovery; doubles per consecutive failure up
  /// to [maxBackoff].
  final Duration baseBackoff;
  final Duration maxBackoff;

  StreamSubscription<CameraIdMismatchEvent>? _sub;
  final Set<String> _inFlight = {};
  final Map<String, int> _failures = {};
  final Map<String, DateTime> _notBefore = {};

  /// Subscribes to [CameraIdMismatchNotifier]. Idempotent.
  void start() {
    _sub ??= CameraIdMismatchNotifier.events.listen(
      (e) => unawaited(handle(e)),
    );
  }

  Future<void> stop() async {
    await _sub?.cancel();
    _sub = null;
  }

  /// Handles one mismatch event. Returns true only when the saved address of
  /// that camera was changed.
  Future<bool> handle(CameraIdMismatchEvent event) async {
    final id = event.expectedCameraId;
    final stored = cameras()
        .where((c) => c.thingName == id && c.host == event.host)
        .toList();
    if (stored.isEmpty) return false; // already moved, or removed meanwhile
    if (_inFlight.contains(id)) return false;
    final notBefore = _notBefore[id];
    if (notBefore != null && _now().isBefore(notBefore)) return false;
    _inFlight.add(id);
    try {
      final camera = stored.first;
      if (event.unreachable) {
        // The old address did not answer: a camera that merely is busy or off
        // must not start a network search.
        if (camera.host.startsWith('cloud-')) return false;
        final verified = _verifiedUntil[id];
        if (verified != null && _now().isBefore(verified)) return false;
        if (!await _isOnLan()) return false;
        final serialThere = await _readSerial(
          WsDiscoveryCandidate(
            scheme: 'https',
            host: camera.host,
            port: event.port,
          ),
        );
        if (serialThere == id) {
          _verifiedUntil[id] = _now().add(verifiedFor);
          _failures.remove(id);
          _notBefore.remove(id);
          return false;
        }
      }
      final found = await _findBySerial(camera);
      if (found == null) {
        _scheduleRetry(id);
        return false;
      }
      updateHost(cameraId: id, oldHost: camera.host, newHost: found);
      _failures.remove(id);
      _notBefore.remove(id);
      debugPrint('[CameraAddressRecovery] $id moved ${camera.host} -> $found');
      return true;
    } catch (e) {
      debugPrint('[CameraAddressRecovery] $id recovery failed: $e');
      _scheduleRetry(id);
      return false;
    } finally {
      _inFlight.remove(id);
    }
  }

  /// Called when the user opens a camera (`FR-MOB-116`, amended 2026-11-02):
  /// makes sure the stored address still belongs to this camera *before* the
  /// screen opens, instead of letting the first request fail and the
  /// background recovery catch up later. Returns the connection to use: the
  /// same one when the stored address answers as this camera (remembered for
  /// [verifiedFor]), when no search is possible (not on Wi-Fi/Ethernet, no
  /// serial known, a `cloud-<serial>` placeholder) or when the camera is not
  /// found anywhere; the updated one (new address, same password) when it was
  /// found elsewhere by serial. Unlike the background path this ignores the
  /// retry backoff, because the user just asked for this camera.
  Future<CameraConnection> ensureReachable(CameraConnection camera) async {
    final id = camera.thingName;
    if (id == null || camera.host.startsWith('cloud-')) return camera;
    final verified = _verifiedUntil[id];
    if (verified != null && _now().isBefore(verified)) return camera;
    if (!await _isOnLan()) return camera;
    final serialThere = await _readSerial(
      WsDiscoveryCandidate(
        scheme: 'https',
        host: camera.host,
        port: camera.httpsPort,
      ),
    );
    if (serialThere == id) {
      _verifiedUntil[id] = _now().add(verifiedFor);
      _failures.remove(id);
      _notBefore.remove(id);
      return camera;
    }
    debugPrint(
      '[CameraAddressRecovery] ensureReachable $id: ${camera.host} answered '
      '"$serialThere" -> searching the network',
    );
    final moved = await locate(camera);
    return moved ?? camera;
  }

  /// Reports that [camera]'s stored address did not answer (a failed LAN
  /// check on the Dashboard, for instance). Same handling as an unreachable
  /// event from the HTTP client; safe to call often (one search per camera at
  /// a time, with backoff).
  Future<bool> noteUnreachable(CameraConnection camera) {
    final id = camera.thingName;
    if (id == null) return Future.value(false);
    return handle(
      CameraIdMismatchEvent(
        host: camera.host,
        port: camera.httpsPort,
        expectedCameraId: id,
        unreachable: true,
      ),
    );
  }

  static Future<bool> _defaultIsOnLan() async {
    try {
      final results = await Connectivity().checkConnectivity();
      return results.contains(ConnectivityResult.wifi) ||
          results.contains(ConnectivityResult.ethernet);
    } catch (_) {
      return true; // cannot tell: allow the (bounded) search
    }
  }

  /// User-initiated search for a restored camera that has no address yet
  /// (`cloud-<serial>` placeholder): ignores the retry backoff and returns the
  /// stored connection with its new address, or null if the camera was not
  /// found on this network. Waits for a background search of the same camera.
  Future<CameraConnection?> locate(CameraConnection camera) async {
    final id = camera.thingName;
    if (id == null) return null;
    _notBefore.remove(id);
    _failures.remove(id);
    for (var i = 0; i < 20 && _inFlight.contains(id); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
    if (cameras()
        .where((c) => c.thingName == id)
        .every((c) => c.host == camera.host)) {
      await handle(
        CameraIdMismatchEvent(
          host: camera.host,
          port: camera.httpsPort,
          expectedCameraId: id,
        ),
      );
    }
    final now = cameras().where((c) => c.thingName == id).toList();
    return (now.isNotEmpty && now.first.host != camera.host)
        ? now.first.copyWithPassword(camera.password)
        : null;
  }

  void _scheduleRetry(String id) {
    final n = (_failures[id] ?? 0) + 1;
    _failures[id] = n;
    var wait = baseBackoff * (1 << (n - 1).clamp(0, 10));
    if (wait > maxBackoff) wait = maxBackoff;
    _notBefore[id] = _now().add(wait);
  }

  /// The new address of [camera]'s serial, or null if not found or ambiguous.
  Future<String?> _findBySerial(CameraConnection camera) async {
    final id = camera.thingName!;
    for (final thorough in [false, true]) {
      final candidates = await _discover(thorough: thorough);
      final matches = <String>{};
      for (final candidate in candidates) {
        // That address belongs to the other device now.
        if (candidate.host == camera.host) continue;
        if (await _readSerial(candidate) == id) matches.add(candidate.host);
      }
      if (matches.length == 1) return matches.single;
      if (matches.length > 1) {
        debugPrint(
          '[CameraAddressRecovery] $id: ${matches.length} devices claim this '
          'serial — leaving the camera unreachable',
        );
        return null;
      }
    }
    return null;
  }

  static Future<List<WsDiscoveryCandidate>> _defaultDiscover({
    required bool thorough,
  }) async {
    final client = WsDiscoveryClient();
    if (thorough) return client.scanUnicast();
    // Android drops multicast replies without a MulticastLock (same as
    // camera_scan.dart).
    final lock = FlutterMulticastLock();
    try {
      try {
        await lock.acquireMulticastLock(
          lockName: 'com.onchiptech.mobilecctvapp.address_recovery',
        );
      } catch (_) {}
      return await client.scanMulticast();
    } finally {
      try {
        await lock.releaseMulticastLock();
      } catch (_) {}
    }
  }

  static Future<String?> _defaultReadSerial(
    WsDiscoveryCandidate candidate,
  ) async {
    final probe = CameraConnection(
      host: candidate.host,
      username: '',
      password: '',
      httpsPort: candidate.port,
    );
    final client = OnvifDeviceClient(probe);
    try {
      final result = await client.getSerialNumber(
        timeout: const Duration(seconds: 4),
      );
      return result is CameraSuccess<String> ? result.value : null;
    } finally {
      client.close();
    }
  }
}
