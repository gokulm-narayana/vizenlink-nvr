/// Typed result of every `camera_api` call — the API-stability contract (DESIGN.md §3) commits
/// to returning structured values, never a formatted string or a UI-specific exception, so a
/// human UI and a future in-app agent can consume the exact same return value.
sealed class CameraResult<T> {
  const CameraResult();
}

class CameraSuccess<T> extends CameraResult<T> {
  const CameraSuccess(this.value);
  final T value;

  // Real gap found 2026-08-13: none of these three classes overrode toString(), so every
  // existing `'...: $result'`-style debug/log interpolation across the app (discovery_screen.dart,
  // add_camera_credentials_screen.dart, etc.) silently printed "Instance of 'CameraFailure<bool>'"
  // instead of the actual reason — the exact information those log lines existed to capture.
  @override
  String toString() => 'CameraSuccess<$T>($value)';
}

/// A request the camera actively rejected or failed to service (HTTP error, SOAP Fault,
/// MQTT error response) — distinct from [CameraTimeout], since a rejection is informative
/// (e.g. "Smart night vision not wired yet") while a timeout only means "no answer".
class CameraFailure<T> extends CameraResult<T> {
  const CameraFailure(this.reason);
  final String reason;

  @override
  String toString() => 'CameraFailure<$T>($reason)';
}

/// A [CameraFailure] the camera produced **on purpose, for a reason a caller can act on** and that must never be mistaken for "wrong password" or
/// "unreachable": [CameraForbidden], [CameraBlocked], [CameraPasswordChangeRequired]. Client code that passes a failed inner call on to its own result
/// type calls [retype], which keeps the subtype (re-wrapping with `CameraFailure(reason)` would turn it back into an ordinary failure).
abstract class CameraRejection<T> extends CameraFailure<T> {
  const CameraRejection(super.reason);

  /// The same rejection for a different result type.
  CameraFailure<R> retype<R>();
}

/// The camera understood the request and the credentials were fine, but this account's role may not
/// do it (`FR-CF-156`: ONVIF `ter:InsufficientUserLevel`, REST `403`/`role_not_permitted`, WAN
/// `error_code` 403). It is *not* a credentials problem: the session and the stored credentials are
/// fine, so do not ask the user to log in again, and do not retry. Typical handling: hide or disable the
/// control for roles below the one it needs.
class CameraForbidden<T> extends CameraRejection<T> {
  const CameraForbidden([super.reason = 'Not permitted for this user role']);

  @override
  CameraFailure<R> retype<R>() => CameraForbidden<R>(reason);

  @override
  String toString() => 'CameraForbidden<$T>($reason)';
}

/// The camera blocked this account after too many failed sign-ins (`FR-CF-157`: HTTP/WAN 429). Even the correct password is refused until the block
/// ends, so **do not retry in a loop** — wait [retryAfter] (when known), tell the user plainly, and let them try again later. Not a wrong-password
/// result and not a role refusal ([CameraForbidden]).
class CameraBlocked<T> extends CameraRejection<T> {
  const CameraBlocked([super.reason = 'Too many failed sign-in attempts', this.retryAfter]);

  /// How long until the block ends, when the camera said (REST login and WAN do; the ONVIF fault text carries no number).
  final Duration? retryAfter;

  /// Reads the seconds out of a camera message such as "... (retry in 60 s)", else null.
  static Duration? parseRetryAfter(String text) {
    final m = RegExp(r'retry in (\d+) s').firstMatch(text);
    return m == null ? null : Duration(seconds: int.parse(m.group(1)!));
  }

  @override
  CameraFailure<R> retype<R>() => CameraBlocked<R>(reason, retryAfter);

  @override
  String toString() => 'CameraBlocked<$T>($reason, retryAfter: $retryAfter)';
}

/// The camera is still on the factory-default Administrator password and refuses every request except the Administrator setting a new one
/// (`FR-CF-158`: HTTP 428 / WAN `error_code` 428 / ONVIF `ter:PasswordChangeRequired`). The login itself works (and says so:
/// `NuraeyeClient.isPasswordChangeRequired()`); the fix is `OnvifDeviceClient.setUserPassword('admin', newPassword)` — then everything else works.
class CameraPasswordChangeRequired<T> extends CameraRejection<T> {
  const CameraPasswordChangeRequired([super.reason = 'Set a new Administrator password first']);

  @override
  CameraFailure<R> retype<R>() => CameraPasswordChangeRequired<R>(reason);

  @override
  String toString() => 'CameraPasswordChangeRequired<$T>($reason)';
}

/// The library has no password for the account it was asked to use (not in memory, not in the secure store, or the protected storage is locked), so
/// it did **not** send the request. Not a wrong password and not an unreachable camera: the caller (UI or agent) asks for the password, hands it
/// back with `CameraCredentials.rememberForSession` / `save`, and repeats the call.
class CameraCredentialsMissing<T> extends CameraRejection<T> {
  const CameraCredentialsMissing([super.reason = 'No password is known for this camera account']);

  @override
  CameraFailure<R> retype<R>() => CameraCredentialsMissing<R>(reason);

  @override
  String toString() => 'CameraCredentialsMissing<$T>($reason)';
}

/// No response arrived within the call's bounded timeout. Kept distinct from [CameraFailure]
/// per FR-NE-053's WAN contract: "no response within the bounded timeout is treated as
/// failed/undelivered" — callers (UI or agent) may want to retry a timeout, but should never
/// retry an explicit rejection the same way.
class CameraTimeout<T> extends CameraResult<T> {
  const CameraTimeout();

  @override
  String toString() => 'CameraTimeout<$T>()';
}

/// Re-types a failure for a different result type while keeping its subtype (see [CameraRejection]) — for clients that pass a failed inner call's
/// outcome on as their own.
CameraFailure<R> retypeFailure<R>(CameraFailure<Object?> failure) =>
    failure is CameraRejection ? failure.retype<R>() : CameraFailure<R>(failure.reason);
