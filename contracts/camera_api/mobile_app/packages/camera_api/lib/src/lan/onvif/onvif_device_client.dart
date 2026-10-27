import 'package:http/http.dart' as http;
import 'package:xml/xml.dart';

import '../../camera_connection.dart';
import '../../camera_result.dart';
import '../../camera_role.dart';
import '../../device_reset_types.dart';
import '../insecure_camera_http_client.dart';
import '../wsse_digest.dart';
import 'soap_fault.dart';

/// `onvif_types.h`'s `ONVIF_CONFIG_SCOPE_NAME_PREFIX`/`ONVIF_CONFIG_SCOPE_LOCATION_PREFIX`.
const _kScopeNamePrefix = 'onvif://www.onvif.org/name/';
const _kScopeLocationPrefix = 'onvif://www.onvif.org/location/';

/// `onvif_types.h`'s `ONVIF_MAX_CAMERA_NAME_LEN`/`ONVIF_MAX_LOCATION_LEN` — both 32. Enforced
/// client-side (`CameraInfoScreen`'s name/location fields) so a request is never even sent with
/// a value the camera would silently truncate.
const kMaxDeviceNameLength = 32;
const kMaxDeviceLocationLength = 32;

/// Camera account passwords are 1-32 characters since the multi-user firmware (`FR-CF-156`: `onvif_types.h`'s `ONVIF_MAX_PASSWORD_LEN` is 33, i.e. 32 usable
/// plus the terminator; it was 16/15 before). A longer password is refused by the camera (`AccountFailure.passwordTooLong`), never truncated.
/// **Firmware that predates `FR-CF-156` still has the old limit of 15.**
const kMaxDevicePasswordLength = 32;

/// ONVIF Device service — `GetDeviceInformation` (needed for its `SerialNumber` field, which is
/// also this fleet's AWS IoT thing name/KVS stream name — `bsp_provisioning_ameba.c`'s dev LUT
/// sets both fields to the identical string for every entry, confirmed by reading the firmware
/// source directly, same convention `kvs_livestream_test.py`'s `load_firmware_credentials()`
/// already assumes — used at camera onboarding time (`AddCameraCredentialsScreen`) to populate
/// `CameraConnection.thingName` so WAN live view (`IotCommandClient`/`KvsMediaViewerCredentialsClient`) has
/// something to address the camera with), `GetServices` (endpoint discovery), and the device
/// identity trio (`GetScopes`/`SetScopes` for camera name + location, `GetSystemDateAndTime`/
/// `SetSystemDateAndTime` for time zone — added 2026-08-04, `DeviceIdentityScreen`). Wire format
/// mirrors `testing_utilities/network_stability_tests.py`'s `_get_device_info()`/`_get_scopes()`/
/// `_set_scopes()`, per `.claude/rules/mobile-app.md`'s Python-script-is-the-reference
/// convention.
/// One `GetServices` entry — [namespace] is the ONVIF service WSDL namespace (e.g.
/// `http://www.onvif.org/ver20/media/wsdl` for Media2), [xAddr] the actual endpoint URL to POST
/// that service's requests to on this specific device.
class OnvifServiceEntry {
  const OnvifServiceEntry({required this.namespace, required this.xAddr});
  final String namespace;
  final Uri xAddr;
}

/// The camera's current display name and physical-location label — the ONVIF `Scope_Name`/
/// `Scope_Location` values (`onvif://www.onvif.org/name/<value>`,
/// `.../location/<value>`), URI-decoded. Either can independently come back empty
/// (`onvif_user_config.c`'s default `location` is `""`).
class DeviceIdentity {
  const DeviceIdentity({required this.name, required this.location});
  final String name;
  final String location;

  @override
  bool operator ==(Object other) =>
      other is DeviceIdentity && other.name == name && other.location == location;
  @override
  int get hashCode => Object.hash(name, location);
}

/// The camera's current UTC clock + POSIX-style time zone string (`bsp_camera_ameba.c`'s
/// `p_device->timezone`, e.g. `"IST-5:30"`, `"UTC"`) — `GetSystemDateAndTime`'s full response.
/// `year`/`month`/.../`second` are the camera's own UTC clock, not user-editable through
/// [DeviceIdentityScreen]'s time zone card; they're only carried so [setTimeZone] can echo them
/// straight back unchanged (`onvif_device.c`'s `SetSystemDateAndTime` handler has no NTP mode
/// and requires a full Manual date/time on every call, so changing the time zone alone still
/// means resending the whole struct).
class DeviceDateTime {
  const DeviceDateTime({
    required this.timezone,
    required this.daylightSavings,
    required this.year,
    required this.month,
    required this.day,
    required this.hour,
    required this.minute,
    required this.second,
  });
  final String timezone;
  final bool daylightSavings;
  final int year;
  final int month;
  final int day;
  final int hour;
  final int minute;
  final int second;

  @override
  bool operator ==(Object other) =>
      other is DeviceDateTime &&
      other.timezone == timezone &&
      other.daylightSavings == daylightSavings &&
      other.year == year &&
      other.month == month &&
      other.day == day &&
      other.hour == hour &&
      other.minute == minute &&
      other.second == second;
  @override
  int get hashCode =>
      Object.hash(timezone, daylightSavings, year, month, day, hour, minute, second);
}

/// `GetDeviceInformation`'s full field set — read-only, shown on `CameraInfoScreen`'s "Device
/// Information" card. [serialNumber] alone is also what [OnvifDeviceClient.getSerialNumber]
/// returns (kept as its own method too — used at onboarding time before this fuller call is
/// ever needed).
class DeviceInformation {
  const DeviceInformation({
    required this.manufacturer,
    required this.model,
    required this.firmwareVersion,
    required this.serialNumber,
    required this.hardwareId,
  });
  final String manufacturer;
  final String model;
  final String firmwareVersion;
  final String serialNumber;
  final String hardwareId;
}

/// `GetNetworkInterfaces`'s active-interface summary — [interfaceName] is literally `"wlan"` or
/// `"eth"` (`bsp_ameba.c`'s `bsp_getNetworkInterfaceAddresses()` — not a generic OS interface
/// name, a fixed two-value enum in practice), which is how [isWireless] tells them apart.
class NetworkInterfaceInfo {
  const NetworkInterfaceInfo({
    required this.interfaceName,
    required this.macAddress,
    required this.ipv4Address,
  });
  final String interfaceName;
  final String macAddress;
  final String ipv4Address;

  bool get isWireless => interfaceName.toLowerCase().contains('wlan');
}

class OnvifDeviceClient {
  OnvifDeviceClient(this.connection, {http.Client? httpClient})
    : _http = httpClient ?? createCameraHttpClient(cameraId: connection.thingName);

  final CameraConnection connection;
  final http.Client _http;

  Future<CameraResult<String>> getSerialNumber({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      final el = doc.findAllElements('SerialNumber', namespace: '*');
      return el.isEmpty ? '' : el.first.innerText.trim();
    });
  }

  /// Full `GetDeviceInformation` — see [DeviceInformation]'s doc for why this exists alongside
  /// [getSerialNumber].
  Future<CameraResult<DeviceInformation>> getDeviceInformation({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      String text(String tag) {
        final el = doc.findAllElements(tag, namespace: '*');
        return el.isEmpty ? '' : el.first.innerText.trim();
      }

      return DeviceInformation(
        manufacturer: text('Manufacturer'),
        model: text('Model'),
        firmwareVersion: text('FirmwareVersion'),
        serialNumber: text('SerialNumber'),
        hardwareId: text('HardwareId'),
      );
    });
  }

  /// The camera's active network interface (`GetNetworkInterfaces`) — see
  /// [NetworkInterfaceInfo]'s doc for the wired/wireless distinction.
  Future<CameraResult<NetworkInterfaceInfo>> getNetworkInterfaceInfo({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetNetworkInterfaces xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      String text(String tag) {
        final el = doc.findAllElements(tag, namespace: '*');
        return el.isEmpty ? '' : el.first.innerText.trim();
      }

      return NetworkInterfaceInfo(
        interfaceName: text('Name'),
        macAddress: text('HwAddress'),
        ipv4Address: text('Address'),
      );
    });
  }

  /// `GetServices` (`IncludeCapabilities: false` — this app only needs the `XAddr`, not each
  /// service's inline capabilities block) — the real ONVIF way to discover a service's actual
  /// endpoint URL per this device, rather than a client assuming a fixed path. Confirmed via
  /// `onvif_device_get_services.c`: the response only lists a service if it's actually enabled
  /// on this build (`p_server->media2.enabled`, etc.), so an absent entry is a genuine "this
  /// camera doesn't offer this service" signal, not just a missing URL. Every caller resolving a
  /// service endpoint (e.g. `Media2CapabilitiesClient`) should go through this rather than
  /// hardcoding `CameraConnection.onvifMedia2Endpoint`-style paths.
  Future<CameraResult<List<OnvifServiceEntry>>> getServices({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetServices xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
      '<tds:IncludeCapability>false</tds:IncludeCapability>'
      '</tds:GetServices>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      final entries = <OnvifServiceEntry>[];
      for (final serviceEl in doc.findAllElements('Service', namespace: '*')) {
        final namespaceEl = serviceEl.findElements('Namespace', namespace: '*');
        final xAddrEl = serviceEl.findElements('XAddr', namespace: '*');
        if (namespaceEl.isEmpty || xAddrEl.isEmpty) continue;
        final xAddr = Uri.tryParse(xAddrEl.first.innerText.trim());
        if (xAddr == null) continue;
        entries.add(
          OnvifServiceEntry(namespace: namespaceEl.first.innerText.trim(), xAddr: xAddr),
        );
      }
      return entries;
    });
  }

  /// Reads the camera's current display name and location — the `Scope_Name`/`Scope_Location`
  /// entries in `GetScopes`'s response (`onvif_device_get_scopes.c`). Either can come back empty
  /// (unset location is the factory default).
  Future<CameraResult<DeviceIdentity>> getDeviceIdentity({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetScopes xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      var name = '';
      var location = '';
      for (final el in doc.findAllElements('ScopeItem', namespace: '*')) {
        final raw = el.innerText.trim();
        if (raw.startsWith(_kScopeNamePrefix)) {
          name = Uri.decodeComponent(raw.substring(_kScopeNamePrefix.length));
        } else if (raw.startsWith(_kScopeLocationPrefix)) {
          location = Uri.decodeComponent(raw.substring(_kScopeLocationPrefix.length));
        }
      }
      return DeviceIdentity(name: name, location: location);
    });
  }

  /// Sets the camera's display name (`FR-CF-015`'s `Scope_Name` — surfaced to VMS/NVR clients
  /// and shown in this app's own camera list). `onvif_device.c`'s `SetScopes` handler parses at
  /// most `ONVIF_MAX_CONFIG_SCOPES` (2) `<tds:Scopes>` entries per request and only updates
  /// whichever of Name/Location it recognizes by prefix — leaving the other untouched — so name
  /// and location can each be set independently, one `<tds:Scopes>` entry at a time.
  Future<CameraResult<void>> setDeviceName(
    String name, {
    Duration timeout = const Duration(seconds: 10),
  }) => _setScope(_kScopeNamePrefix, name, timeout);

  /// Sets the camera's physical-location label (`Scope_Location`) — see [setDeviceName] for why
  /// this is independent of the name.
  Future<CameraResult<void>> setDeviceLocation(
    String location, {
    Duration timeout = const Duration(seconds: 10),
  }) => _setScope(_kScopeLocationPrefix, location, timeout);

  Future<CameraResult<void>> _setScope(String prefix, String value, Duration timeout) async {
    final scopeUri = '$prefix${Uri.encodeComponent(value)}';
    final bodyResult = await _post(
      '<tds:SetScopes xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
      '<tds:Scopes>$scopeUri</tds:Scopes>'
      '</tds:SetScopes>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  /// Reads the camera's current UTC clock and POSIX-style time zone string. See
  /// [DeviceDateTime]'s doc for why the clock fields are carried even though only the time zone
  /// is user-editable.
  Future<CameraResult<DeviceDateTime>> getSystemDateAndTime({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetSystemDateAndTime xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      String text(String tag) {
        final el = doc.findAllElements(tag, namespace: '*');
        return el.isEmpty ? '' : el.first.innerText.trim();
      }

      return DeviceDateTime(
        timezone: text('TZ'),
        daylightSavings: text('DaylightSavings').toLowerCase() == 'true',
        year: int.tryParse(text('Year')) ?? 1970,
        month: int.tryParse(text('Month')) ?? 1,
        day: int.tryParse(text('Day')) ?? 1,
        hour: int.tryParse(text('Hour')) ?? 0,
        minute: int.tryParse(text('Minute')) ?? 0,
        second: int.tryParse(text('Second')) ?? 0,
      );
    });
  }

  /// Changes only the time zone. `onvif_device.c`'s `SetSystemDateAndTime` handler rejects
  /// `DateTimeType: NTP` (`OnvifError_NtpServerUndefined` — not supported by this firmware) and
  /// requires a full Manual UTC date/time on every call, so there's no "just send the new TZ"
  /// request — this first re-reads the camera's current clock via [getSystemDateAndTime] and
  /// echoes it straight back unchanged alongside the new [tz], rather than risk the caller
  /// supplying a stale or guessed date. The round trip costs at most a couple hundred
  /// milliseconds of clock drift, which only affects the *reported* local time (not any
  /// time-critical firmware path) — an accepted, cosmetic-only caveat.
  Future<CameraResult<void>> setTimeZone(
    String tz, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final currentResult = await getSystemDateAndTime(timeout: timeout);
    if (currentResult is! CameraSuccess<DeviceDateTime>) {
      return switch (currentResult) {
        CameraForbidden(:final reason) => CameraForbidden(reason),
        CameraFailure(:final reason) => CameraFailure(reason),
        CameraTimeout() => CameraTimeout(),
        CameraSuccess() => const CameraFailure('unreachable'),
      };
    }
    final current = currentResult.value;
    final bodyResult = await _post(
      '<tds:SetSystemDateAndTime xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
      'xmlns:tt="http://www.onvif.org/ver10/schema">'
      '<tds:DateTimeType>Manual</tds:DateTimeType>'
      '<tds:DaylightSavings>${current.daylightSavings}</tds:DaylightSavings>'
      '<tds:TimeZone><tt:TZ>$tz</tt:TZ></tds:TimeZone>'
      '<tds:UTCDateTime>'
      '<tt:Time><tt:Hour>${current.hour}</tt:Hour><tt:Minute>${current.minute}</tt:Minute>'
      '<tt:Second>${current.second}</tt:Second></tt:Time>'
      '<tt:Date><tt:Year>${current.year}</tt:Year><tt:Month>${current.month}</tt:Month>'
      '<tt:Day>${current.day}</tt:Day></tt:Date>'
      '</tds:UTCDateTime>'
      '</tds:SetSystemDateAndTime>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  /// Changes one camera account's password (`SetUser`, `FR-OV-103`). The camera holds up to 5
  /// accounts (`FR-CF-156`): the Administrator may change any account's password, every other
  /// account only its own — otherwise the result is a [CameraForbidden]. Passwords are 1-32
  /// characters; a longer one is refused (`PasswordTooLong`), never truncated. No `UserLevel` is
  /// sent, so the account's level is left alone.
  ///
  /// The Administrator is always named `admin` and cannot be renamed; **no account may be given the
  /// factory-default password `password`** (refused: [AccountFailure.passwordNotAllowed]) — the app's forced
  /// first-time change on adding a camera is exactly this call with a different password. **Callers must update
  /// their own stored [CameraConnection.password] on success** when they changed the account they are logged in
  /// as: this client keeps using whatever it was constructed with.
  Future<CameraResult<void>> setUserPassword(
    String username,
    String newPassword, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:SetUser xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
      'xmlns:tt="http://www.onvif.org/ver10/schema">'
      '<tds:User>'
      '<tt:Username>${_escape(username)}</tt:Username>'
      '<tt:Password>${_escape(newPassword)}</tt:Password>'
      '</tds:User>'
      '</tds:SetUser>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  /// Lists every account on the camera with its real role (`GetUsers`, `FR-OV-103`). Administrator
  /// only — any other account gets a [CameraForbidden] (use the role returned by the session
  /// login instead to know your own).
  Future<CameraResult<List<CameraAccount>>> getUsers({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:GetUsers xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      final accounts = <CameraAccount>[];
      for (final user in doc.findAllElements('User', namespace: '*')) {
        final name = user.findElements('Username', namespace: '*');
        final level = user.findElements('UserLevel', namespace: '*');
        if (name.isEmpty) continue;
        final role = CameraRole.tryParse(level.isEmpty ? null : level.first.innerText.trim());
        if (role == null) continue;
        accounts.add(CameraAccount(username: name.first.innerText.trim(), role: role));
      }
      return accounts;
    });
  }

  /// Creates an [CameraRole.operator] or [CameraRole.user] account (`CreateUsers`, `FR-OV-103`).
  /// Administrator only. The camera holds at most 5 accounts (one Administrator): a full camera
  /// answers [AccountFailure.tooManyUsers], a duplicate name [AccountFailure.usernameExists].
  /// See [accountFailureOf] to map a [CameraFailure] to the reason.
  Future<CameraResult<void>> createUser(
    String username,
    String password,
    CameraRole role, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    if (role == CameraRole.administrator) {
      return const CameraFailure('A camera has exactly one Administrator; it cannot be created');
    }
    final bodyResult = await _post(
      '<tds:CreateUsers xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
      'xmlns:tt="http://www.onvif.org/ver10/schema">'
      '<tds:User>'
      '<tt:Username>${_escape(username)}</tt:Username>'
      '<tt:Password>${_escape(password)}</tt:Password>'
      '<tt:UserLevel>${role.wireValue}</tt:UserLevel>'
      '</tds:User>'
      '</tds:CreateUsers>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  /// Deletes an account (`DeleteUsers`, `FR-OV-103`) — Administrator only. Takes effect at once:
  /// that account's sessions and RTSP connections end, which is how a shared camera is un-shared.
  /// The Administrator cannot be deleted ([AccountFailure.fixedUser]).
  Future<CameraResult<void>> deleteUser(
    String username, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:DeleteUsers xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
      '<tds:Username>${_escape(username)}</tds:Username>'
      '</tds:DeleteUsers>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  /// Changes a non-administrator's role between [CameraRole.operator] and [CameraRole.user]
  /// (`SetUser` with a `UserLevel`) — Administrator only; the Administrator's own role is fixed.
  Future<CameraResult<void>> setUserRole(
    String username,
    CameraRole role, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    if (role == CameraRole.administrator) {
      return const CameraFailure('A camera has exactly one Administrator; nobody can be promoted to it');
    }
    final bodyResult = await _post(
      '<tds:SetUser xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
      'xmlns:tt="http://www.onvif.org/ver10/schema">'
      '<tds:User>'
      '<tt:Username>${_escape(username)}</tt:Username>'
      '<tt:UserLevel>${role.wireValue}</tt:UserLevel>'
      '</tds:User>'
      '</tds:SetUser>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  /// Reboots the camera (`SystemReboot`, `FR-CF-112`) — `onvif_device.c` responds with a
  /// `tt:Message` (typically `"Rebooting in 5 seconds"`) and calls `bsp_rebootAsync()`
  /// **before** the response is even generated, so this call succeeding does not mean the
  /// device is back yet — the caller should expect a real connectivity gap of several seconds.
  /// No confirmation/undo: the caller owns any "are you sure?" prompt before invoking this.
  Future<CameraResult<String>> reboot({Duration timeout = const Duration(seconds: 10)}) async {
    final bodyResult = await _post(
      '<tds:SystemReboot xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>',
      timeout,
    );
    return bodyResult.map((body) {
      final doc = XmlDocument.parse(body);
      final el = doc.findAllElements('Message', namespace: '*');
      return el.isEmpty ? '' : el.first.innerText.trim();
    });
  }

  /// Resets the camera to factory defaults (`SetSystemFactoryDefault`, `FR-CF-111`) — see
  /// [FactoryResetMode]'s doc for the Soft/Hard distinction. Response is empty on success; the
  /// camera reboots automatically afterward (`bsp_rebootAsync()`), same connectivity-gap caveat
  /// as [reboot]. **[FactoryResetMode.hard] wipes WiFi credentials** — the caller must warn the
  /// user this camera will need full re-provisioning/re-onboarding, not just a reconnect.
  Future<CameraResult<void>> factoryReset(
    FactoryResetMode mode, {
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final bodyResult = await _post(
      '<tds:SetSystemFactoryDefault xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
      '<tds:FactoryDefault>${mode.wireValue}</tds:FactoryDefault>'
      '</tds:SetSystemFactoryDefault>',
      timeout,
    );
    return bodyResult.map((_) {});
  }

  String _escape(String text) => text
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');

  Future<CameraResult<String>> _post(String bodyXml, Duration timeout) async {
    final digest = WsseDigest.generate(connection.password);
    final envelope =
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        '<s:Header>'
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        '<wsse:UsernameToken>'
        '<wsse:Username>${connection.username}</wsse:Username>'
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        '${digest.digestBase64}</wsse:Password>'
        '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        '${digest.nonceBase64}</wsse:Nonce>'
        '<wsu:Created xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        '${digest.createdIso}</wsu:Created>'
        '</wsse:UsernameToken>'
        '</wsse:Security>'
        '</s:Header>'
        '<s:Body>$bodyXml</s:Body>'
        '</s:Envelope>';

    try {
      final response = await _http
          .post(
            connection.onvifDeviceEndpoint,
            headers: const {'Content-Type': 'application/soap+xml; charset=utf-8'},
            body: envelope,
          )
          .timeout(timeout);

      // [AI Fix] 2026-09-24: SOAP-fault check moved before the status-code check -- real bug
      // found via RecordingTimelineScreen's single-playback-session rejection (module_rtsps.c
      // via OperationProhibited/409): this firmware returns a real <Fault> body on a non-200
      // status for some rejections (unlike the Media2-validation-error case soapFaultReason's
      // own doc describes, which is HTTP 200), and the old ordering returned the raw XML fault
      // body as the error string before soapFaultReason() ever got a chance to parse it --
      // exactly the "SOAP response dumped in the UI" symptom this fixes. A fault is checked for
      // on every response regardless of status; the raw "HTTP <code>: <body>" fallback now only
      // fires for a genuinely non-SOAP failure (e.g. a proxy's own 502/503 HTML page).
      final faultReason = soapFaultReason(response.body);
      if (faultReason != null) {
        // FR-OV-103 / FR-CF-157: "role too low" (CameraForbidden) and "blocked after repeated failures" (CameraBlocked) are not credentials
        // problems -- keep them distinct; other faults keep their sub-code in the text.
        if (soapFaultIsInsufficientUserLevel(response.body) ||
            response.body.contains('TooManyAttempts') ||
            response.body.contains('PasswordChangeRequired')) {
          return soapFaultFailure(response.body, faultReason);
        }
        final sub = soapFaultSubcode(response.body);
        return CameraFailure(sub != null ? '$faultReason [ter:$sub]' : faultReason);
      }

      if (response.statusCode == 429) return const CameraBlocked();
      if (response.statusCode == 428) return const CameraPasswordChangeRequired();
      if (response.statusCode != 200) {
        return CameraFailure('HTTP ${response.statusCode}: ${response.body}');
      }

      return CameraSuccess(response.body);
    } on Exception catch (e) {
      return CameraFailure(e.toString());
    }
  }

  void close() {
    _http.close();
  }
}

extension _ResultMap<T> on CameraResult<T> {
  CameraResult<R> map<R>(R Function(T value) f) {
    return switch (this) {
      CameraSuccess(:final value) => CameraSuccess<R>(f(value)),
      // Keep the CameraForbidden subtype (FR-OV-103) -- re-wrapping it as a plain CameraFailure would turn "role too low" back into an ambiguous error.
      CameraRejection rejection => rejection.retype<R>(), // keeps CameraForbidden / CameraBlocked / CameraPasswordChangeRequired
      CameraFailure(:final reason) => CameraFailure<R>(reason),
      CameraTimeout() => CameraTimeout<R>(),
    };
  }
}
