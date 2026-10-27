import 'package:camera_api/camera_api.dart';

/// App policy: the camera itself accepts 1-[kMaxDevicePasswordLength]
/// characters, but a camera password guards a live video feed, so the app
/// asks for at least this many.
const kMinCameraPasswordLength = 8;

/// The camera's factory-default password. No account may keep or be given it
/// (`OnvifDeviceClient.setUserPassword`'s doc, `FR-CF-158`).
const kFactoryCameraPassword = 'password';

/// The most accounts a camera holds: one Administrator plus four Operator /
/// User accounts (`FR-CF-156`).
const kMaxCameraAccounts = 5;

/// A new camera account password: [kMinCameraPasswordLength]-32 characters,
/// never the factory default.
String? validateNewCameraPassword(String? value) {
  final password = value ?? '';
  if (password.isEmpty) return 'Enter a new password';
  if (password.length < kMinCameraPasswordLength) {
    return 'Use at least $kMinCameraPasswordLength characters';
  }
  if (password.length > kMaxDevicePasswordLength) {
    return 'Use $kMaxDevicePasswordLength characters or fewer';
  }
  if (password.toLowerCase() == kFactoryCameraPassword) {
    return "The factory password can't be used";
  }
  return null;
}

/// A new family-member account name (`FR-MOB-119`): 1-32 printable
/// characters, no spaces or `"<>&`, never `admin` (the Administrator's fixed
/// name, in any case). The camera enforces the same rules; same check as the
/// reference app's `validateNewAccountName`.
String? validateNewAccountName(String? value) {
  final name = value?.trim() ?? '';
  if (name.isEmpty) return 'Enter a name';
  if (name.length > 32) return 'Use 32 characters or fewer';
  if (name.toLowerCase() == 'admin') {
    return '"admin" is reserved for the camera\'s owner account';
  }
  if (RegExp(r'[^\x21-\x7E]|["<>&]').hasMatch(name)) {
    return 'Use letters, digits and simple punctuation, without spaces';
  }
  return null;
}

/// Plain-language text for a failed camera-account call (ONVIF or WAN).
String accountFailureMessage(CameraResult<Object?> result) {
  if (result is CameraTimeout) {
    return "The camera didn't respond. Check it's reachable and try again.";
  }
  if (result is CameraBlocked) {
    return cameraBlockedMessage(result.retryAfter);
  }
  return switch (accountFailureOf(result)) {
    AccountFailure.tooManyUsers =>
      'This camera already has the maximum of $kMaxCameraAccounts accounts.',
    AccountFailure.usernameExists =>
      'An account with that name already exists on this camera.',
    AccountFailure.fixedUser =>
      "The camera's owner account (admin) can't be removed or renamed.",
    AccountFailure.passwordTooLong =>
      'That password is too long. Use $kMaxDevicePasswordLength characters '
          'or fewer.',
    AccountFailure.passwordNotAllowed =>
      "The camera doesn't allow that password. Choose a different one.",
    AccountFailure.rolePermissionDenied =>
      "Only the camera's admin account can manage accounts.",
    AccountFailure.passwordChangeRequired =>
      'This camera is still on its factory password. Set a new one first.',
    AccountFailure.userNotFound =>
      'That account no longer exists on the camera.',
    AccountFailure.invalidValue => 'The camera refused that value.',
    _ => switch (result) {
      CameraFailure(:final reason) => 'The camera refused: $reason',
      _ => 'Something went wrong. Try again.',
    },
  };
}

/// Plain-language text for a camera that locked the account after too many
/// failed sign-ins ([CameraBlocked], `FR-CF-157`). Shown instead of retrying:
/// even the right password is refused until the block ends.
String cameraBlockedMessage(Duration? retryAfter) {
  if (retryAfter == null) {
    return 'This camera is locked after too many failed sign-ins. '
        'Try again in a few minutes.';
  }
  final minutes = (retryAfter.inSeconds / 60).ceil();
  final wait = minutes <= 1 ? 'about a minute' : 'about $minutes minutes';
  return 'This camera is locked after too many failed sign-ins. '
      'Try again in $wait.';
}
