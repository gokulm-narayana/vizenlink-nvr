import 'dart:convert';

import 'package:camera_api/camera_api.dart';
import 'package:camera_api/src/lan/onvif/soap_fault.dart';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

class _FakeTransport implements IotTransport {
  final List<Map<String, dynamic>> published = [];
  final List<Map<String, dynamic>> waited = [];
  final List<Map<String, dynamic>?> replies = [];

  @override
  Future<void> publish(String thingName, Map<String, dynamic> body) async => published.add(body);

  @override
  Future<Map<String, dynamic>?> publishAndWait(String thingName, Map<String, dynamic> body,
      {Duration timeout = const Duration(seconds: 12)}) async {
    waited.add(body);
    if (replies.isEmpty) return {'status': 'ok'};
    return replies.removeAt(0);
  }
}

const _admin = (username: 'admin', password: 'pw-admin');

const _insufficientFault =
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><s:Fault><s:Code><s:Value>s:Sender</s:Value>'
    '<s:Subcode><s:Value>ter:OperationProhibited</s:Value><s:Subcode><s:Value>ter:InsufficientUserLevel</s:Value></s:Subcode></s:Subcode></s:Code>'
    '<s:Reason><s:Text xml:lang="en">The authenticated user level is not permitted to perform this operation.</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>';

String _fault(String sub) =>
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><s:Fault><s:Code><s:Value>s:Receiver</s:Value>'
    '<s:Subcode><s:Value>ter:Action</s:Value><s:Subcode><s:Value>ter:$sub</s:Value></s:Subcode></s:Subcode></s:Code>'
    '<s:Reason><s:Text xml:lang="en">fault $sub</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>';

OnvifDeviceClient _onvif(Future<http.Response> Function(http.Request) handler) => OnvifDeviceClient(
      const CameraConnection(host: '192.168.1.50', username: 'admin', password: 'pw-admin'),
      httpClient: MockClient(handler),
    );

void main() {
  group('CameraRole', () {
    test('wire values, ordering and parsing', () {
      expect(CameraRole.tryParse('Administrator'), CameraRole.administrator);
      expect(CameraRole.tryParse('Operator'), CameraRole.operator);
      expect(CameraRole.tryParse('User'), CameraRole.user);
      expect(CameraRole.tryParse('Anonymous'), isNull);
      expect(CameraRole.tryParse(null), isNull);
      expect(CameraRole.administrator.atLeast(CameraRole.operator), isTrue);
      expect(CameraRole.operator.atLeast(CameraRole.operator), isTrue);
      expect(CameraRole.user.atLeast(CameraRole.operator), isFalse);
      expect(CameraRole.assignable, [CameraRole.operator, CameraRole.user]);
    });

    test('accountFailureOf maps camera reasons', () {
      expect(accountFailureOf(const CameraForbidden()), AccountFailure.rolePermissionDenied);
      expect(accountFailureOf(const CameraFailure('fault [ter:TooManyUsers]')), AccountFailure.tooManyUsers);
      expect(accountFailureOf(const CameraFailure('x [ter:UsernameClash]')), AccountFailure.usernameExists);
      expect(accountFailureOf(const CameraFailure('Command 85 failed on camera [fixed_user]')), AccountFailure.fixedUser);
      expect(accountFailureOf(const CameraFailure('[password_too_long]')), AccountFailure.passwordTooLong);
      expect(accountFailureOf(const CameraFailure('[user_not_found]')), AccountFailure.userNotFound);
      expect(accountFailureOf(const CameraFailure('x [ter:PasswordNotAllowed]')), AccountFailure.passwordNotAllowed);
      expect(accountFailureOf(const CameraFailure('[password_not_allowed]')), AccountFailure.passwordNotAllowed);
      expect(accountFailureOf(const CameraBlocked()), AccountFailure.tooManyAttempts);
      expect(accountFailureOf(const CameraFailure('something else')), AccountFailure.other);
      expect(accountFailureOf(const CameraTimeout<void>()), AccountFailure.other);
    });
  });

  group('SOAP fault helpers', () {
    test('role fault is recognised and is not the credentials fault', () {
      expect(soapFaultIsInsufficientUserLevel(_insufficientFault), isTrue);
      expect(soapFaultIsInsufficientUserLevel(_fault('TooManyUsers')), isFalse);
      expect(soapFaultSubcode(_insufficientFault), 'InsufficientUserLevel');
      expect(soapFaultSubcode(_fault('TooManyUsers')), 'TooManyUsers');
      expect(soapFaultSubcode('<x/>'), isNull);
    });
  });

  group('OnvifDeviceClient account management', () {
    test('getUsers parses every account with its role', () async {
      final client = _onvif((r) async {
        expect(r.body, contains('GetUsers'));
        return http.Response(
          '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><tds:GetUsersResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
          'xmlns:tt="http://www.onvif.org/ver10/schema">'
          '<tds:User><tt:Username>admin</tt:Username><tt:UserLevel>Administrator</tt:UserLevel></tds:User>'
          '<tds:User><tt:Username>kid</tt:Username><tt:UserLevel>User</tt:UserLevel></tds:User>'
          '<tds:User><tt:Username>mum</tt:Username><tt:UserLevel>Operator</tt:UserLevel></tds:User>'
          '</tds:GetUsersResponse></s:Body></s:Envelope>',
          200,
        );
      });
      final result = await client.getUsers();
      expect((result as CameraSuccess<List<CameraAccount>>).value, [
        const CameraAccount(username: 'admin', role: CameraRole.administrator),
        const CameraAccount(username: 'kid', role: CameraRole.user),
        const CameraAccount(username: 'mum', role: CameraRole.operator),
      ]);
    });

    test('createUser sends the role, escapes input and never offers Administrator', () async {
      String? body;
      final client = _onvif((r) async {
        body = r.body;
        return http.Response('<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><tds:CreateUsersResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>', 200);
      });
      final result = await client.createUser('kid', 'p&ss<1>', CameraRole.user);
      expect(result, isA<CameraSuccess<void>>());
      expect(body, contains('<tt:Username>kid</tt:Username>'));
      expect(body, contains('<tt:Password>p&amp;ss&lt;1&gt;</tt:Password>'));
      expect(body, contains('<tt:UserLevel>User</tt:UserLevel>'));

      body = null;
      final admin = await client.createUser('boss', 'x', CameraRole.administrator);
      expect(admin, isA<CameraFailure<void>>());
      expect(body, isNull, reason: 'must not even send the request');
    });

    test('a role fault becomes CameraForbidden, other faults keep their sub-code', () async {
      var fault = _insufficientFault;
      final client = _onvif((r) async => http.Response(fault, 400));
      expect(await client.createUser('a', 'b', CameraRole.user), isA<CameraForbidden<void>>());

      fault = _fault('TooManyUsers');
      final full = await client.createUser('a', 'b', CameraRole.user);
      expect(full, isA<CameraFailure<void>>());
      expect(full, isNot(isA<CameraForbidden<void>>()));
      expect(accountFailureOf(full), AccountFailure.tooManyUsers);

      fault = _fault('FixedUser');
      expect(accountFailureOf(await client.deleteUser('admin')), AccountFailure.fixedUser);
    });

    test('setUserPassword sends no UserLevel; setUserRole sends no Password', () async {
      final bodies = <String>[];
      final client = _onvif((r) async {
        bodies.add(r.body);
        return http.Response('<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body/></s:Envelope>', 200);
      });
      await client.setUserPassword('kid', 'newpass');
      await client.setUserRole('kid', CameraRole.operator);
      expect(bodies[0], contains('<tt:Password>newpass</tt:Password>'));
      expect(bodies[0], isNot(contains('UserLevel')));
      expect(bodies[1], contains('<tt:UserLevel>Operator</tt:UserLevel>'));
      expect(bodies[1], isNot(contains('<tt:Password>')));
      expect(await client.setUserRole('kid', CameraRole.administrator), isA<CameraFailure<void>>());
    });
  });

  group('WAN auth_credentials (FR-NE-130)', () {
    test('every command carries a digest of the explicit credentials, with a fresh nonce each time', () async {
      final transport = _FakeTransport();
      final client = IotCommandClient('VZL-CAM-000001', transport: transport, credentials: _admin);

      await client.sendCommandWithResponse(IotCommandClient.getVideoMode);
      await client.sendCommandWithResponse(IotCommandClient.getVideoMode);

      final a = transport.waited[0]['auth_credentials'] as Map<String, dynamic>;
      final b = transport.waited[1]['auth_credentials'] as Map<String, dynamic>;
      expect(a['username'], 'admin');
      expect(a['nonce'], isNot(b['nonce']), reason: 'the camera refuses a reused nonce');
      final expected = base64.encode(sha1
          .convert([...base64.decode(a['nonce'] as String), ...utf8.encode(a['created'] as String), ...utf8.encode('pw-admin')])
          .bytes);
      expect(a['password_digest'], expected);
    });

    test('credentials come from WanAuth.cameraCredentialsProvider when not given; unknown -> CameraCredentialsMissing and nothing is sent', () async {
      final transport = _FakeTransport();
      final client = IotCommandClient('VZL-CAM-000002', transport: transport);

      WanAuth.cameraCredentialsProvider = (thing) => thing == 'VZL-CAM-000002' ? (username: 'kid', password: 'kid-pw') : null;
      addTearDown(() => WanAuth.cameraCredentialsProvider = null);
      await client.sendCommandWithResponse(IotCommandClient.getVideoMode);
      expect((transport.waited.single['auth_credentials'] as Map)['username'], 'kid');

      WanAuth.cameraCredentialsProvider = (_) => null;
      final before = transport.waited.length;
      await expectLater(client.sendCommandWithResponse(IotCommandClient.getVideoMode), throwsA(isA<CameraCredentialsMissingException>()));
      expect(transport.waited.length, before, reason: 'a command the camera would refuse is not sent');
      // the Wan*Clients turn it into the typed result the UI acts on
      final users = await WanUsersClient('VZL-CAM-000002', iotCommandClient: client).listUsers();
      expect(users, isA<CameraCredentialsMissing<List<CameraAccount>>>());
      expect(accountFailureOf(users), AccountFailure.credentialsMissing);

      await client.sendStopCloudStreaming();
      expect(transport.published.single.containsKey('auth_credentials'), isFalse, reason: 'the fire-and-forget stop is still sent');
    });

    test('fire-and-forget StopCloudStreaming carries credentials too', () async {
      final transport = _FakeTransport();
      await IotCommandClient('VZL-CAM-000001', transport: transport, credentials: _admin).sendStopCloudStreaming();
      expect((transport.published.single['auth_credentials'] as Map)['username'], 'admin');
    });
  });

  roleFaultTests();
  blockedTests();
  passwordChangeRequiredTests();

  group('WanUsersClient', () {
    WanUsersClient make(_FakeTransport t) =>
        WanUsersClient('VZL-CAM-000001', iotCommandClient: IotCommandClient('VZL-CAM-000001', transport: t, credentials: _admin));

    test('listUsers parses output.users', () async {
      final t = _FakeTransport()
        ..replies.add({
          'status': 'ok',
          'output': {
            'max_users': 5,
            'users': [
              {'username': 'admin', 'level': 'Administrator'},
              {'username': 'kid', 'level': 'User'},
            ],
          },
        });
      final result = await make(t).listUsers();
      expect((result as CameraSuccess<List<CameraAccount>>).value.map((a) => a.username), ['admin', 'kid']);
      expect(t.waited.single['command'], 83);
    });

    test('create / delete / role / password send the right command and params', () async {
      final t = _FakeTransport();
      final client = make(t);
      await client.createUser('kid', 'pw', CameraRole.user);
      await client.deleteUser('kid');
      await client.setUserRole('kid', CameraRole.operator);
      await client.setUserPassword('kid', 'new');
      expect(t.waited.map((m) => m['command']), [84, 85, 86, 35]);
      expect(t.waited[0]['params'], {'username': 'kid', 'password': 'pw', 'level': 'User'});
      expect(t.waited[1]['params'], {'username': 'kid'});
      expect(t.waited[2]['params'], {'username': 'kid', 'level': 'Operator'});
      expect(t.waited[3]['params'], {'username': 'kid', 'new_password': 'new'});
      expect(await client.createUser('boss', 'x', CameraRole.administrator), isA<CameraFailure<void>>());
      expect(t.waited.length, 4, reason: 'an Administrator is never created');
    });

    test('role refusal is CameraForbidden; other reasons stay readable', () async {
      final t = _FakeTransport()
        ..replies.add({'status': 'error', 'output': {'error': 'not permitted for this user role', 'error_code': 403, 'reason': 'role_not_permitted'}})
        ..replies.add({'status': 'error', 'output': {'reason': 'too_many_users'}})
        ..replies.add({'status': 'error', 'output': {'error': 'unauthorized', 'error_code': 401}});
      final client = make(t);

      final forbidden = await client.createUser('a', 'b', CameraRole.user);
      expect(forbidden, isA<CameraForbidden<void>>());
      expect(accountFailureOf(forbidden), AccountFailure.rolePermissionDenied);

      final full = await client.createUser('a', 'b', CameraRole.user);
      expect(full, isNot(isA<CameraForbidden<void>>()));
      expect(accountFailureOf(full), AccountFailure.tooManyUsers);

      final unauthorized = await client.deleteUser('x');
      expect(unauthorized, isA<CameraFailure<void>>());
      expect(unauthorized, isNot(isA<CameraForbidden<void>>()), reason: '401 is a credentials problem, not a role problem');
    });
  });
}

// ---- every ONVIF client keeps "role too low" distinct (FR-OV-103) -------------------------------------------------------------------------
void roleFaultTests() {
  const conn = CameraConnection(host: '192.168.1.50', username: 'kid', password: 'pw');
  final endpoint = Uri.parse('https://192.168.1.50/onvif/media2_service');

  http.Client faulting() => MockClient((request) async => http.Response(_insufficientFault, 400));

  final calls = <String, Future<CameraResult<Object?>> Function()>{
    'OnvifDeviceClient': () => OnvifDeviceClient(conn, httpClient: faulting()).getDeviceInformation(),
    'OnvifImagingClient': () => OnvifImagingClient(conn, httpClient: faulting()).getImagingSettings(),
    'OnvifRecordingClient': () => OnvifRecordingClient(conn, httpClient: faulting()).getRecordings(),
    'OnvifSearchClient': () => OnvifSearchClient(conn, httpClient: faulting()).getServiceCapabilities(),
    'OnvifReplayControlClient': () => OnvifReplayControlClient(conn, httpClient: faulting()).getServiceCapabilities(),
    'Media2CapabilitiesClient': () => Media2CapabilitiesClient(conn, httpClient: faulting()).getServiceCapabilities(),
    'MaskClient': () => MaskClient(conn, httpClient: faulting(), endpoint: endpoint).getMasks(),
    'OsdClient': () => OsdClient(conn, httpClient: faulting(), endpoint: endpoint).getOsds(),
    'AudioCapabilityClient': () => AudioCapabilityClient(conn, httpClient: faulting(), endpoint: endpoint).getAudioCapability(),
    'OnvifVideoEncoderClient': () => OnvifVideoEncoderClient(conn, httpClient: faulting(), endpoint: endpoint).getVideoEncoderSettings(),
    'SpeakerVolumeClient': () => SpeakerVolumeClient(conn, httpClient: faulting(), endpoint: endpoint).getSpeakerVolume(),
  };

  group('role fault is CameraForbidden in every ONVIF client', () {
    calls.forEach((name, call) {
      test(name, () async {
        final result = await call();
        expect(result, isA<CameraForbidden<Object?>>(), reason: '$name turned the role fault into: $result');
      });
    });
  });

  group('SnapshotClient', () {
    test('403 is CameraForbidden, other statuses keep the HTTP <code> text', () {
      expect(SnapshotClient.failureForStatus(403), isA<CameraForbidden<Object?>>());
      final other = SnapshotClient.failureForStatus(401);
      expect(other, isNot(isA<CameraForbidden<Object?>>()));
      expect(other.reason, contains('HTTP 401'));
    });
  });
}

// ---- blocked after repeated failed sign-ins (FR-CF-157) ----------------------------------------------------------------------------------
const _tooManyFault =
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><s:Fault><s:Code><s:Value>s:Sender</s:Value>'
    '<s:Subcode><s:Value>ter:OperationProhibited</s:Value><s:Subcode><s:Value>ter:TooManyAttempts</s:Value></s:Subcode></s:Subcode></s:Code>'
    '<s:Reason><s:Text xml:lang="en">Too many failed sign-in attempts for this account from this address.</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>';

void blockedTests() {
  const conn = CameraConnection(host: '192.168.1.50', username: 'kid', password: 'pw');
  final endpoint = Uri.parse('https://192.168.1.50/onvif/media2_service');
  http.Client blocked() => MockClient((request) async => http.Response(_tooManyFault, 429));

  group('CameraBlocked (FR-CF-157)', () {
    test('parseRetryAfter reads the seconds out of the camera message', () {
      expect(CameraBlocked.parseRetryAfter('Too many failed sign-in attempts (retry in 60 s)'), const Duration(seconds: 60));
      expect(CameraBlocked.parseRetryAfter('no seconds here'), isNull);
    });

    test('ONVIF: a 429 fault is CameraBlocked in the device client and the others; a bare 429 too', () async {
      expect(await OnvifDeviceClient(conn, httpClient: blocked()).getUsers(), isA<CameraBlocked<List<CameraAccount>>>());
      expect(await OnvifImagingClient(conn, httpClient: blocked()).getImagingSettings(), isA<CameraBlocked<ImagingSettings>>());
      expect(await MaskClient(conn, httpClient: blocked(), endpoint: endpoint).getMasks(), isA<CameraBlocked<List<MaskEntry>>>());
      final bare = await OnvifDeviceClient(conn, httpClient: MockClient((r) async => http.Response('', 429))).getUsers();
      expect(bare, isA<CameraBlocked<List<CameraAccount>>>());
      expect(bare, isNot(isA<CameraForbidden<List<CameraAccount>>>()));
    });

    test('snapshot 429 is CameraBlocked', () {
      expect(SnapshotClient.failureForStatus(429), isA<CameraBlocked<Object?>>());
    });

    test('WAN: error_code 429 becomes CameraBlocked with the retry time; not CameraForbidden', () async {
      final t = _FakeTransport()
        ..replies.add({'status': 'error', 'output': {'error': 'too many failed sign-in attempts', 'error_code': 429, 'retry_after_seconds': 45}});
      final client = WanUsersClient('VZL-CAM-000001',
          iotCommandClient: IotCommandClient('VZL-CAM-000001', transport: t, credentials: _admin));
      final result = await client.listUsers();
      expect(result, isA<CameraBlocked<List<CameraAccount>>>());
      expect((result as CameraBlocked).retryAfter, const Duration(seconds: 45));
      expect(accountFailureOf(result), AccountFailure.tooManyAttempts);
    });

    test('retypeFailure keeps CameraBlocked and its retry time', () {
      final out = retypeFailure<int>(const CameraBlocked<String>('x', Duration(seconds: 7)));
      expect(out, isA<CameraBlocked<int>>());
      expect((out as CameraBlocked).retryAfter, const Duration(seconds: 7));
    });
  });
}

// ---- first-password gate (FR-CF-158) ------------------------------------------------------------------------------------------------------
const _changeRequiredFault =
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><s:Fault><s:Code><s:Value>s:Sender</s:Value>'
    '<s:Subcode><s:Value>ter:OperationProhibited</s:Value><s:Subcode><s:Value>ter:PasswordChangeRequired</s:Value></s:Subcode></s:Subcode></s:Code>'
    '<s:Reason><s:Text xml:lang="en">The Administrator must set a new password first.</s:Text></s:Reason></s:Fault></s:Body></s:Envelope>';

void passwordChangeRequiredTests() {
  const conn = CameraConnection(host: '192.168.1.50', username: 'admin', password: 'password');
  final endpoint = Uri.parse('https://192.168.1.50/onvif/media2_service');
  http.Client gated() => MockClient((request) async => http.Response(_changeRequiredFault, 428));

  group('CameraPasswordChangeRequired (FR-CF-158)', () {
    test('an ONVIF 428 fault is CameraPasswordChangeRequired in the device client and the others, not a plain failure', () async {
      expect(await OnvifDeviceClient(conn, httpClient: gated()).getUsers(), isA<CameraPasswordChangeRequired<List<CameraAccount>>>());
      expect(await OnvifImagingClient(conn, httpClient: gated()).getImagingSettings(), isA<CameraPasswordChangeRequired<ImagingSettings>>());
      expect(await OsdClient(conn, httpClient: gated(), endpoint: endpoint).getOsds(), isA<CameraPasswordChangeRequired<List<OsdEntry>>>());
      final bare = await OnvifDeviceClient(conn, httpClient: MockClient((r) async => http.Response('', 428))).getUsers();
      expect(bare, isA<CameraPasswordChangeRequired<List<CameraAccount>>>());
      expect(accountFailureOf(bare), AccountFailure.passwordChangeRequired);
    });

    test('snapshot 428 and WAN error_code 428 are CameraPasswordChangeRequired', () async {
      expect(SnapshotClient.failureForStatus(428), isA<CameraPasswordChangeRequired<Object?>>());
      final t = _FakeTransport()
        ..replies.add({'status': 'error', 'output': {'error': 'set a new Administrator password first', 'error_code': 428, 'reason': 'password_change_required'}});
      final client = WanUsersClient('VZL-CAM-000001',
          iotCommandClient: IotCommandClient('VZL-CAM-000001', transport: t, credentials: _admin));
      expect(await client.listUsers(), isA<CameraPasswordChangeRequired<List<CameraAccount>>>());
    });

    test('retypeFailure keeps it; it is distinct from Forbidden and Blocked', () {
      final out = retypeFailure<int>(const CameraPasswordChangeRequired<String>('x'));
      expect(out, isA<CameraPasswordChangeRequired<int>>());
      expect(out, isNot(isA<CameraForbidden<int>>()));
      expect(out, isNot(isA<CameraBlocked<int>>()));
    });

    test('setUserPassword for the Administrator is an ordinary SetUser with just the password (what the first change sends)', () async {
      String? body;
      final c = OnvifDeviceClient(conn, httpClient: MockClient((r) async {
        body = r.body;
        return http.Response('<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body/></s:Envelope>', 200);
      }));
      expect(await c.setUserPassword('admin', 'Brand-new-pass-1'), isA<CameraSuccess<void>>());
      expect(body, contains('<tt:Username>admin</tt:Username>'));
      expect(body, contains('<tt:Password>Brand-new-pass-1</tt:Password>'));
      expect(body, isNot(contains('UserLevel')));
    });
  });
}
