import 'package:camera_api/camera_api.dart';
import 'package:flutter_multicast_lock/flutter_multicast_lock.dart';

import '../models/scanned_camera.dart';

const _multicastLockName = 'com.onchiptech.mobilecctvapp.camera_scan';

/// Runs one full LAN discovery pass and returns every genuine VizenLink/
/// NuraEye camera found, verified/probed exactly as documented in
/// `docs/screens/scan/scan_cameras_screen.md`'s Notes — extracted here (out
/// of `ScannedDevicesScreen`) so the Dashboard's scanning popup and this
/// screen's own initial-load/rescan both run the *same* real scan rather
/// than duplicating (or worse, re-running) it.
///
/// Holds an Android `WifiManager.MulticastLock` (via `flutter_multicast_lock`
/// — a no-op on iOS/other platforms) for the multicast phase only: without
/// it, the Wi-Fi radio's power-saving filter can silently drop incoming
/// multicast packets, which is exactly the failure mode the unicast
/// fallback below exists to recover from — holding the lock makes that
/// fallback less often necessary. Released immediately after (success or
/// failure) rather than for the whole scan, since holding it disables Wi-Fi
/// power saving for as long as it's held.
Future<List<ScannedCamera>> scanForCameras() async {
  final discovery = WsDiscoveryClient();
  final multicastLock = FlutterMulticastLock();

  List<WsDiscoveryCandidate> candidates;
  try {
    try {
      await multicastLock.acquireMulticastLock(lockName: _multicastLockName);
    } catch (_) {
      // Best-effort — scanning still works without it, just less reliably
      // on some devices.
    }
    candidates = await discovery.scanMulticast();
  } finally {
    try {
      await multicastLock.releaseMulticastLock();
    } catch (_) {
      // Nothing to do if there was never a lock to release.
    }
  }

  if (candidates.isEmpty) {
    candidates = await discovery.scanUnicast();
  }
  final probed = await Future.wait(candidates.map(_probeCandidate));
  return probed.nonNulls.toList();
}

Future<ScannedCamera?> _probeCandidate(WsDiscoveryCandidate candidate) async {
  final nuraeyeClient = NuraeyeClient(
    CameraConnection(host: candidate.host, username: '', password: ''),
  );
  final identityResult = await nuraeyeClient.areYouNuraeyeDevice(
    timeout: const Duration(seconds: 3),
  );
  nuraeyeClient.close();
  final isNuraeyeDevice = switch (identityResult) {
    CameraSuccess(:final value) => value,
    CameraFailure() || CameraTimeout() => false,
  };
  if (!isNuraeyeDevice) return null;

  // The camera's display name: its configured GetScopes name, else the
  // model. Both answer without signing in, so blank credentials are sent —
  // never the factory login, which used to go to every camera on every scan
  // (and whose "success" was misread as "unconfigured").
  final deviceClient = OnvifDeviceClient(
    CameraConnection(
      host: candidate.host,
      username: '',
      password: '',
      httpsPort: candidate.port,
    ),
  );
  String name = 'Camera at ${candidate.host}';
  try {
    final identity = await deviceClient.getDeviceIdentity(
      timeout: const Duration(seconds: 3),
    );
    if (identity case CameraSuccess(:final value) when value.name.isNotEmpty) {
      name = value.name;
    } else if (await deviceClient.getDeviceInformation(
          timeout: const Duration(seconds: 3),
        )
        case CameraSuccess(:final value) when value.model.isNotEmpty) {
      name = value.model;
    }
  } finally {
    deviceClient.close();
  }
  return ScannedCamera(
    id: candidate.host,
    name: name,
    ipAddress: candidate.host,
    httpsPort: candidate.port,
  );
}
