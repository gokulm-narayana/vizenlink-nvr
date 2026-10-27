import 'package:camera_api/camera_api.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../utils/camera_account_rules.dart';
import 'camera_cloud_list.dart';

/// The add-camera flow's camera calls (`FEAT-226`, `FR-MOB-117`), shared by
/// the scan list (SCAN-010) and manual add (SCAN-020) so they can't drift
/// apart. Ported from the senior engineer's reference app
/// (`nuraeye-rt` `features/onboarding/add_camera_credentials_screen.dart`).
///
/// Replaces a flow that used ONVIF `GetDeviceInformation` both to guess
/// "configured" and to "verify" credentials. That call answers **without
/// checking credentials**, so every camera looked factory-fresh, the default
/// login was pre-filled for all of them, and any typed password was accepted
/// and saved — every later call then got HTTP 401 and tripped the camera's
/// sign-in lockout (found 2026-10-16).

void _log(String message) => debugPrint('[AddCamera] $message');

/// Outcome of the single automatic factory-login attempt.
enum FactoryProbeResult {
  /// `admin` / factory password accepted: the camera is still on it and the
  /// owner must set a new password before it can be added (SCAN-029).
  factoryPassword,

  /// Refused (401): the camera already has a password — ask for it.
  configured,

  /// The camera locked sign-ins after too many failures ([retryAfter]).
  blocked,

  /// No answer / not reachable.
  unreachable,
}

/// One login attempt with the factory Administrator credentials — the only
/// automatic attempt the flow makes, so it costs at most one entry on the
/// camera's lockout counter.
Future<({FactoryProbeResult result, Duration? retryAfter, String? detail})>
probeFactoryLogin(
  String host, {
  int httpsPort = 443,
  http.Client? httpClient,
}) async {
  // A cached session would answer without re-checking the password.
  NuraeyeClient.clearSessionFor(host);
  final connection = CameraConnection(
    host: host,
    username: 'admin',
    password: kFactoryCameraPassword,
    httpsPort: httpsPort,
  );
  final client = NuraeyeClient(connection, httpClient: httpClient);
  try {
    final gate = await client.isPasswordChangeRequired();
    _log('factory probe $host: $gate');
    return switch (gate) {
      // Logging in with the factory password worked => still on it.
      CameraSuccess() => (
        result: FactoryProbeResult.factoryPassword,
        retryAfter: null,
        detail: null,
      ),
      CameraBlocked(:final retryAfter) => (
        result: FactoryProbeResult.blocked,
        retryAfter: retryAfter,
        detail: null,
      ),
      CameraFailure(:final reason) when reason.contains('401') => (
        result: FactoryProbeResult.configured,
        retryAfter: null,
        detail: null,
      ),
      CameraFailure(:final reason) => (
        result: FactoryProbeResult.unreachable,
        retryAfter: null,
        detail: reason,
      ),
      CameraTimeout() => (
        result: FactoryProbeResult.unreachable,
        retryAfter: null,
        detail: 'timed out',
      ),
    };
  } finally {
    client.close();
  }
}

/// Whether [host] is a genuine NuraEye/VizenLink camera (manual entry only —
/// discovered cameras were already checked by the scan). Retries once: a
/// phone's first HTTPS request on a Wi-Fi network can lose to a single
/// short attempt.
Future<bool> isGenuineCamera(String host, {http.Client? httpClient}) async {
  final client = NuraeyeClient(
    CameraConnection(host: host, username: '', password: ''),
    httpClient: httpClient,
  );
  try {
    final result = await client.areYouNuraeyeDeviceWithRetry();
    _log('identity check $host: $result');
    return result is CameraSuccess<bool> && result.value;
  } finally {
    client.close();
  }
}

/// What a successful [verifyAndReadCamera] learned about the camera.
class VerifiedCamera {
  const VerifiedCamera({
    required this.connection,
    this.info,
    this.thingName,
    this.macAddress,
    this.capabilities,
    this.name,
  });

  /// The login that was just verified (carries [thingName] when known).
  final CameraConnection connection;
  final DeviceInformation? info;
  final String? thingName;
  final String? macAddress;
  final CameraCapabilities? capabilities;

  /// The camera's own configured name (ONVIF GetScopes), if set.
  final String? name;
}

/// FR-MOB-121: claims the camera for the signed-in account **before** it is
/// stored locally. Only the camera's owner (the `admin` login) claims it; a
/// family member's login adds the camera to this phone only — the cloud keeps
/// one owner per camera and sharing goes through the cloud list. Returns a
/// message to show when the camera belongs to another account (do not add
/// it), else null. Offline / not signed in still adds the camera: it is
/// queued and claimed when the network returns.
Future<String?> claimCameraForAccount(CameraConnection connection) async {
  if (connection.username != 'admin') return null;
  final outcome = await CameraCloudList.instance.registerBeforeAdd(connection);
  _log('claim ${connection.thingName}: $outcome');
  return outcome == RegisterOutcome.alreadyRegistered
      ? 'This camera is registered to another account. Ask its owner to '
            'remove it from their account, or reset the camera.'
      : null;
}

sealed class VerifyOutcome {
  const VerifyOutcome();
}

class VerifyOk extends VerifyOutcome {
  const VerifyOk(this.camera);
  final VerifiedCamera camera;
}

/// The camera still wants its factory password replaced (SCAN-029).
class VerifyNeedsNewPassword extends VerifyOutcome {
  const VerifyNeedsNewPassword();
}

class VerifyFailed extends VerifyOutcome {
  const VerifyFailed(this.message);

  /// Plain language for the form's error text.
  final String message;
}

/// The real credential check: an authenticated call every role may make
/// (`GetCapabilities`), which answers HTTP 401 for a wrong password and so
/// distinguishes it from an unreachable camera. Only on success does it read
/// the serial (= WAN thing name), MAC, device info, capabilities and name —
/// all best-effort, none blocks the add.
Future<VerifyOutcome> verifyAndReadCamera(
  CameraConnection connection, {
  http.Client? httpClient,
}) async {
  // The real check must log in again, never reuse a cached session.
  NuraeyeClient.clearSessionFor(connection.host);
  final nuraeye = NuraeyeClient(connection, httpClient: httpClient);
  try {
    final check = await nuraeye.call('GetCapabilities');
    switch (check) {
      case CameraSuccess():
        break;
      case CameraPasswordChangeRequired():
        return const VerifyNeedsNewPassword();
      case CameraBlocked(:final retryAfter):
        return VerifyFailed(cameraBlockedMessage(retryAfter));
      case CameraFailure(:final reason):
        _log('credential check ${connection.host} failed: $reason');
        return VerifyFailed(
          reason.contains('401')
              ? 'Incorrect username or password.'
              : 'Could not reach the camera — check the connection and try '
                    'again.',
        );
      case CameraTimeout():
        return const VerifyFailed(
          'Could not reach the camera — check the connection and try again.',
        );
    }

    final device = OnvifDeviceClient(connection, httpClient: httpClient);
    try {
      String? thingName;
      if (await device.getSerialNumber() case CameraSuccess(
        :final value,
      ) when value.isNotEmpty) {
        thingName = value;
      }
      String? mac;
      if (await device.getNetworkInterfaceInfo() case CameraSuccess(
        :final value,
      ) when value.macAddress.isNotEmpty) {
        mac = value.macAddress;
      }
      DeviceInformation? info;
      if (await device.getDeviceInformation() case CameraSuccess(
        :final value,
      )) {
        info = value;
      }
      String? name;
      if (await device.getDeviceIdentity() case CameraSuccess(
        :final value,
      ) when value.name.isNotEmpty) {
        name = value.name;
      }
      CameraCapabilities? capabilities;
      if (await CapabilitiesClient(nuraeye).getCapabilities()
          case CameraSuccess(:final value)) {
        capabilities = value;
      }
      return VerifyOk(
        VerifiedCamera(
          connection: thingName == null
              ? connection
              : connection.copyWithThingName(thingName),
          info: info,
          thingName: thingName,
          macAddress: mac,
          capabilities: capabilities,
          name: name,
        ),
      );
    } finally {
      device.close();
    }
  } finally {
    nuraeye.close();
  }
}
