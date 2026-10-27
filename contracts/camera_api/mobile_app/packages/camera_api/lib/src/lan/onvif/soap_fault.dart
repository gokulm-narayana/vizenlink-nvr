import 'package:xml/xml.dart';

import '../../camera_result.dart';

/// True when [body] is the camera's "authenticated, but this account's role may not do this" fault
/// (`ter:OperationProhibited` / `ter:InsufficientUserLevel`, `FR-OV-103`) — deliberately not
/// `ter:NotAuthorized`, which means wrong credentials.
bool soapFaultIsInsufficientUserLevel(String body) => body.contains('InsufficientUserLevel');

/// The vendor sub-code of a SOAP fault (`ter:TooManyUsers`, `ter:UsernameClash`, `ter:FixedUser`,
/// `ter:PasswordTooLong`, `ter:UsernameMissing`, ...), or `null` when there is none.
String? soapFaultSubcode(String body) {
  final m = RegExp(r'<[^>]*Subcode[^>]*>\s*<[^>]*Value[^>]*>\s*ter:([A-Za-z]+)').allMatches(body).toList();
  if (m.isEmpty) return null;
  return m.last.group(1);
}

/// The failure to return for a SOAP fault found in [body] (its [reason] from [soapFaultReason]): a [CameraForbidden] when the camera
/// refused because the account's role is too low (`FR-OV-103`), else a plain [CameraFailure]. Every ONVIF client's request function uses
/// this, so "not allowed for your role" is distinguishable from "failed" without reading text.
CameraFailure<T> soapFaultFailure<T>(String body, String reason) => soapFaultIsInsufficientUserLevel(body)
    ? CameraForbidden<T>(reason)
    : body.contains('TooManyAttempts')
        ? CameraBlocked<T>(reason)
        : body.contains('PasswordChangeRequired')
            ? CameraPasswordChangeRequired<T>(reason)
            : CameraFailure<T>(reason);

/// Returns the SOAP fault reason text if [body] contains a `<Fault>` element, `null` otherwise.
///
/// **Why this exists:** every ONVIF client here used to only check the HTTP status code before
/// treating a response as success — but this firmware's fault responses don't use one consistent
/// HTTP status. Media2 validation errors (e.g. `SetOSD` rejecting an out-of-range color via
/// `ter:InvalidArgVal`) come back as `HTTP 200` with a `<s:Fault>` body, which was silently
/// parsed as if it were the real response, hiding a real rejection from the caller. Other faults
/// (e.g. `GetReplayUri`'s `OperationProhibited`/409 rejection of a second concurrent playback
/// client, `onvif_replaycontrol.c`) come back on a genuinely non-200 status *with* a real
/// `<Fault>` body — a second bug, found 2026-09-24, where every `_post()` checked status first
/// and returned the raw XML as the error string before this function ever ran, surfacing as an
/// unparsed SOAP fault dumped straight into a screen's error text.
///
/// Every `_post()`-style method must call this on the raw response body **before** checking the
/// HTTP status code, not after — a robust SOAP client can never rely on HTTP status alone, in
/// either direction, to detect a fault. Fall back to a raw `HTTP <code>: <body>` failure message
/// only once this returns `null` (a genuinely non-SOAP failure, e.g. a proxy's own 502/503 HTML
/// page) — never skip calling this first just because the status already looked like success or
/// already looked like failure.
String? soapFaultReason(String body) {
  try {
    final doc = XmlDocument.parse(body);
    if (doc.findAllElements('Fault', namespace: '*').isEmpty) return null;
    final reasonText = doc.findAllElements('Text', namespace: '*');
    return reasonText.isNotEmpty
        ? reasonText.first.innerText.trim()
        : 'SOAP fault (no reason given)';
  } on Exception {
    return null;
  }
}
