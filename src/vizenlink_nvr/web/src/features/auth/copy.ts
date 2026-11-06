export const AUTH_COPY = {
  // Primary CTAs
  SIGN_IN: "Sign in",
  CREATE_OWNER_ACCOUNT: "Create owner account",

  // Page titles
  TITLE_SIGN_IN: "Sign in",
  TITLE_SETUP: "Set up VizenLink NVR",

  // Setup helpers & fields
  PASSWORD_HELPER: "At least 8 characters.",
  SITE_TIMEZONE_LABEL: "Site time zone",
  RECORDING_STORAGE_LABEL: "Recording storage directory",
  ALLOW_SYSTEM_DISK_LABEL: "Allow recordings on the system disk (testing only)",
  ALLOW_SYSTEM_DISK_HELPER: "Leave this off on a real NVR. Recordings belong on a separate drive.",

  // Error states
  LOGIN_ERROR: "Incorrect username or password. Check your username and password, then try again.",
  LOCKOUT_ERROR: "Too many failed attempts. Try again in 15 minutes.",
  PASSWORD_MISMATCH: "Passwords don't match. Re-enter both and try again.",
  PASSWORD_TOO_SHORT: "At least 8 characters.",
  SETUP_FAILURE:
    "Couldn't create the owner account. Check that the recording storage directory exists and the NVR can write to it, then try again.",
  RETRY_SETUP: "Retry create owner account",

  // Session & Sign-out
  SESSION_ENDED: "Your session ended. Sign in again to continue.",
  SIGN_OUT_FAILURE:
    "Couldn't end your session on the NVR. You're signed out on this device, but the session stays active on the NVR until it expires.",
  RETRY_SIGN_OUT: "Retry sign-out request",

  // NVR Unreachable
  NVR_UNREACHABLE_TITLE: "Can't reach the NVR",
  NVR_UNREACHABLE_BODY:
    "Can't reach the NVR. Check that the NVR service is running and you're on the same network, then retry.",
  RETRY_CONNECTION: "Retry connection",
} as const;
