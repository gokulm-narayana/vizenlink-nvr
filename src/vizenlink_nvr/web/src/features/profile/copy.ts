export const ROLE_DESCRIPTIONS: Record<string, string> = {
  viewer: "Watches the cameras you choose.",
  operator: "Watches every camera, saves snapshots and clips, adds and edits cameras.",
  owner: "Full access, including users and mobile devices.",
};

export const PROFILE_COPY = {
  CHANGE_PASSWORD_TITLE: "Change password",
  NEW_PASSWORD_HELPER: "At least 8 characters.",
  CHANGE_PASSWORD_ACTION: "Change password",
  KEEP_PASSWORD_ACTION: "Keep current password",
  PASSWORD_MISMATCH: "Passwords don't match. Re-enter both and try again.",
  PASSWORD_TOO_SHORT:
    "New password must be at least 8 characters. Use a longer password and try again.",
  WRONG_CURRENT_PASSWORD: "Current password is incorrect. Check it and try again.",
  CHANGE_PASSWORD_FAILED:
    "Couldn't change your password. Check your connection and try again.",
  RETRY_CHANGE_PASSWORD: "Retry change password",
  PASSWORD_CHANGED_TOAST:
    "Password changed. Your other devices were signed out.",

  ACCOUNT_TITLE: "Account",
  SECURITY_TITLE: "Security",
  SECURITY_CAPTION: "Changing your password signs out your other devices.",
  PREFERENCES_TITLE: "Preferences",
  PREFERENCES_CAPTION: "Saved in this browser only.",
  CAMERAS_YOU_CAN_VIEW: "Cameras you can view",
  ALL_CAMERAS: "All cameras",
  NO_CAMERAS_VIEWER:
    "None yet. Ask the NVR owner to give you access to a camera.",
  LOAD_ERROR: "Couldn't load profile. Check your connection and try again.",
  RELOAD_PROFILE: "Reload profile",
  SIGN_OUT: "Sign out",
} as const;
