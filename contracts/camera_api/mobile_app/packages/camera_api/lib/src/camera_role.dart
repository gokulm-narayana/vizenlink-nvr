import 'camera_result.dart';

/// The role of a camera account (`FR-CF-156`): the camera holds up to 5 accounts, exactly one
/// [administrator] (the owner; also the account a third-party NVR/VMS uses) and up to four
/// [operator]/[user] accounts. Every ONVIF action, REST route, WAN command and RTSP session is
/// authorised on the camera against this role — see `design/stages/camera-multi-user-accounts/DESIGN.md` §4.
///
/// Ordered by privilege: `user < operator < administrator`.
enum CameraRole {
  /// View live video and recordings, read settings and status.
  user('User'),

  /// Everything a [user] may, plus changing runtime behaviour: privacy mode, image/audio/event
  /// settings, deterrence (siren/spotlight), two-way talk.
  operator('Operator'),

  /// Everything, including accounts, network/time, storage, firmware and reset.
  administrator('Administrator');

  const CameraRole(this.wireValue);

  /// The ONVIF `UserLevel` / NuraEye JSON `role`/`level` value.
  final String wireValue;

  bool atLeast(CameraRole other) => index >= other.index;

  /// Roles that can be given to a non-administrator account (`CreateUsers`/`SetUser`).
  static const List<CameraRole> assignable = [operator, user];

  static CameraRole? tryParse(String? wire) {
    for (final role in CameraRole.values) {
      if (role.wireValue == wire) return role;
    }
    return null;
  }
}

/// One account on the camera, as listed by `GetUsers` (ONVIF) or `ListUsers` (WAN). Never carries a
/// password — the camera never returns one.
class CameraAccount {
  const CameraAccount({required this.username, required this.role});

  final String username;
  final CameraRole role;

  @override
  bool operator ==(Object other) =>
      other is CameraAccount && other.username == username && other.role == role;

  @override
  int get hashCode => Object.hash(username, role);

  @override
  String toString() => 'CameraAccount($username, ${role.wireValue})';
}

/// Maps the failure of an account-management call (ONVIF or WAN) to the reason a UI can act on.
AccountFailure accountFailureOf(CameraResult<Object?> result) {
  if (result is CameraForbidden) return AccountFailure.rolePermissionDenied;
  if (result is CameraBlocked) return AccountFailure.tooManyAttempts;
  if (result is CameraPasswordChangeRequired) return AccountFailure.passwordChangeRequired;
  if (result is CameraCredentialsMissing) return AccountFailure.credentialsMissing;
  if (result is! CameraFailure) return AccountFailure.other;
  final text = result.reason;
  if (text.contains('TooManyUsers') || text.contains('too_many_users')) return AccountFailure.tooManyUsers;
  if (text.contains('UsernameClash') || text.contains('username_exists')) return AccountFailure.usernameExists;
  if (text.contains('FixedUser') || text.contains('fixed_user')) return AccountFailure.fixedUser;
  if (text.contains('PasswordTooLong') || text.contains('password_too_long')) return AccountFailure.passwordTooLong;
  if (text.contains('PasswordNotAllowed') || text.contains('password_not_allowed')) return AccountFailure.passwordNotAllowed;
  if (text.contains('UsernameMissing') || text.contains('user_not_found')) return AccountFailure.userNotFound;
  if (text.contains('role_not_permitted')) return AccountFailure.rolePermissionDenied;
  if (text.contains('InvalidArgVal') || text.contains('invalid_value')) return AccountFailure.invalidValue;
  return AccountFailure.other;
}

/// Why a camera refused an account-management request, for the failures a caller can act on.
enum AccountFailure {
  tooManyUsers,
  usernameExists,
  fixedUser,
  passwordTooLong,

  /// The factory-default password (`password`) cannot be used by any account.
  passwordNotAllowed,

  /// Blocked after repeated failed sign-ins (`FR-CF-157`) — wait, do not retry in a loop.
  tooManyAttempts,

  /// The Administrator must first set a new password (`FR-CF-158`); everything else is refused until then.
  passwordChangeRequired,

  /// The app has no password for this account (not remembered, or the protected storage is locked) — ask the user.
  credentialsMissing,
  userNotFound,
  rolePermissionDenied,
  invalidValue,
  other,
}
