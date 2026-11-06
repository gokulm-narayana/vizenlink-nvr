export const USERS_COPY = {
  TITLE: "Users",
  CREATE_USER_BUTTON: "Create user",
  RELOAD_USERS: "Reload users" as const,
  LOAD_ERROR: "Couldn't load users. Check your connection and try again.",

  // Table
  COL_USERNAME: "Username",
  COL_ROLE: "Role",
  COL_STATUS: "Status",
  COL_CAMERAS: "Cameras",
  COL_CREATED: "Created",
  YOU_BADGE: "You",
  ALL_CAMERAS: "All cameras",
  NO_CAMERAS: "No cameras",
  NO_CAMERAS_TITLE: "This viewer can't see any camera",
  CAMERAS_COUNT: (count: number) => `${count} ${count === 1 ? "camera" : "cameras"}`,
  ACTIONS_LABEL: (username: string) => `Actions for ${username}`,

  // Actions
  ACTION_EDIT_ACCESS: "Edit access",
  ACTION_ENABLE_USER: "Enable user",
  ACTION_DISABLE_USER: "Disable user",
  ACTION_RESET_PASSWORD: "Reset password",
  ACTION_CHANGE_PASSWORD: "Change your password",

  // Empty
  EMPTY_HEADING: "No users found",
  EMPTY_BODY: "Create a user to give someone access to this NVR.",

  // Create User Dialog
  CREATE_TITLE: "Create user",
  USERNAME_LABEL: "Username",
  PASSWORD_LABEL: "Password",
  CONFIRM_PASSWORD_LABEL: "Confirm password",
  PASSWORD_HELPER: "At least 8 characters.",
  ROLE_LABEL: "Role",
  DISCARD_NEW_USER: "Discard new user",
  DISCARD_DIALOG_TITLE: "Discard this new user?",
  DISCARD_DIALOG_BODY: "The details you entered will be lost.",
  KEEP_EDITING_USER: "Keep editing user",
  USERNAME_REQUIRED: "Username is required",
  PASSWORD_REQUIRED: "Password is required",
  PASSWORD_TOO_SHORT: "Password must be at least 8 characters.",
  PASSWORD_MISMATCH: "Passwords don't match. Re-enter both and try again.",
  USERNAME_TAKEN: (username: string) =>
    `A user named ${username} already exists. Choose a different username.`,
  CREATE_FAILED: (username: string) =>
    `Couldn't create the user ${username}. Check your connection and try again.`,
  RETRY_CREATE: "Retry create user" as const,
  USER_CREATED_TOAST: "User created",

  // Camera Checklist
  ASSIGNED_CAMERAS_LABEL: "Assigned cameras",
  CAMERA_CHECKLIST_HELPER:
    "Viewers see only the cameras you tick. With none ticked they see nothing.",
  SELECT_ALL_CAMERAS: "Select all cameras",
  CLEAR_ALL_CAMERAS: "Clear all cameras",

  // Edit Access Dialog
  EDIT_ACCESS_TITLE: (username: string) => `Edit access for ${username}`,
  SAVE_ACCESS_BUTTON: "Save access",
  DISCARD_ACCESS_CHANGES: "Discard access changes",
  ACCESS_SAVED_TOAST: (username: string) => `Access saved for ${username}`,
  STALE_CAMERAS_ERROR:
    "One or more selected cameras no longer exist. Reload the camera list and choose again.",
  RELOAD_CAMERAS: "Reload cameras" as const,
  SAVE_ACCESS_FAILED: (username: string) =>
    `Couldn't save access for ${username}. Check your connection and try again.`,
  RETRY_SAVE_ACCESS: "Retry save user access" as const,

  // Enable / Disable User
  DISABLE_TITLE: (username: string) => `Disable ${username}?`,
  DISABLE_DESCRIPTION: (username: string) =>
    `Disable ${username}? They are signed out everywhere and can't sign in until you enable the account again.`,
  DISABLE_BUTTON: "Disable user",
  KEEP_ENABLED_BUTTON: "Keep user enabled",
  DISABLED_TOAST: (username: string) => `Disabled ${username}`,
  ENABLED_TOAST: (username: string) => `Enabled ${username}`,
  DISABLE_FAILED: (username: string) =>
    `Couldn't disable ${username}. Check your connection and try again.`,
  ENABLE_FAILED: (username: string) =>
    `Couldn't enable ${username}. Check your connection and try again.`,
  RETRY_DISABLE: "Retry disable user" as const,
  RETRY_ENABLE: "Retry enable user" as const,

  // Reset Password Dialog
  RESET_PASSWORD_TITLE: (username: string) => `Reset password for ${username}`,
  RESET_PASSWORD_HELPER: (username: string) =>
    `At least 8 characters. ${username} is signed out everywhere and must use the new password.`,
  NEW_PASSWORD_LABEL: "New password",
  KEEP_CURRENT_PASSWORD: "Keep current password",
  RESET_PASSWORD_BUTTON: "Reset password",
  PASSWORD_RESET_TOAST: (username: string) => `Password reset for ${username}`,
  RESET_PASSWORD_FAILED: (username: string) =>
    `Couldn't reset the password for ${username}. Check your connection and try again.`,
  RETRY_RESET_PASSWORD: "Retry reset password" as const,

  // Self Protection Tooltips
  CANNOT_DISABLE_SELF: "You can't disable your own account.",
  CANNOT_CHANGE_OWN_ROLE: "You can't change your own role.",
} as const;
