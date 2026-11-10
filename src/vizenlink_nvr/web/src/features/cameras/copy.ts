export const CAMERAS_COPY = {
  EMPTY_HEADING: "No cameras yet",
  EMPTY_BODY:
    "Connect your first camera. Find cameras on the recorder's network or enter their details yourself.",
  EMPTY_ACTION: "Add camera",
  LIST_CAPTION: "Cameras",
  ADD_CAMERA: "Add camera",
  NOT_CONNECTED_TITLE: (name: string) => `${name} hasn't connected yet`,
  NOT_CONNECTED_BODY: "Check the address and credentials, then edit the camera's details.",
  EDIT_DETAILS: "Edit camera details",
  SETTINGS_SAVED: "Settings saved",
  SAVE_FAILED: (name: string) =>
    `Couldn't save settings for ${name}. Check that the camera is online and the values are in range, then try again.`,
  RETRY_SAVE: "Retry save settings",
  DISCARD_CHANGES: "Discard changes",
  SAVE_CHANGES: "Save changes",
  WDR_WARNING: "Changing WDR switches the sensor mode and may restart the camera briefly.",

  // Health
  HEALTH_HEADING: "Camera health",
  HEALTH_LOAD_ERROR: "Couldn't load camera health. Check your connection and try again.",
  RETRY_LOAD_HEALTH: "Reload camera health",
  UPTIME_LABEL: "Uptime",
  REBOOT_REASON_LABEL: "Last reboot reason",
  CLOCK_SYNC_LABEL: "Clock sync",
  FIRMWARE_LABEL: "Firmware",

  // Maintenance & Reboot & Factory Reset
  MAINTENANCE_HEADING: "Maintenance",
  REBOOT_BUTTON: "Reboot camera",
  KEEP_RUNNING_BUTTON: "Keep camera running",
  REBOOT_TITLE: (name: string) => `Reboot ${name}?`,
  REBOOT_DESCRIPTION:
    "It will go offline for about a minute. Recording resumes automatically.",
  REBOOT_FAILED: (name: string) =>
    `Couldn't reboot ${name}. Check that the camera is online and try again.`,
  RETRY_REBOOT: "Retry reboot camera" as const,
  REBOOT_STARTED: (name: string) => `Reboot started for ${name}`,
  FACTORY_RESET_BUTTON: "Factory reset camera",
  KEEP_SETTINGS_BUTTON: "Keep camera settings",
  CONTINUE_RESET_BUTTON: "Continue factory reset",
  RESET_MODE_LABEL: "Reset mode",
  SOFT_RESET_TITLE: "Soft reset (keep network)",
  SOFT_RESET_DESC: (name: string) =>
    `Erases the camera name, location, image, overlay and other camera settings on ${name} and returns them to factory defaults. Wi-Fi and network settings are kept, so the camera stays at the same address.`,
  HARD_RESET_TITLE: "Hard reset (erase all)",
  HARD_RESET_DESC: (name: string) =>
    `Erases all settings on ${name}, including its name, location and Wi-Fi and network credentials. The camera goes offline and restarts in AP provisioning mode, so recording stops until you set it up again. Its address changes after you set it up again, so update the camera's address in the NVR afterwards.`,
  TYPE_RESET_LABEL: "Type RESET to confirm",
  TYPE_RESET_HELPER: "Type RESET to enable the button.",
  SOFT_RESET_CONFIRM: (name: string) =>
    `Soft reset ${name}? Its name, location, image, overlay and other camera settings are erased and return to factory defaults. Network settings are kept.`,
  HARD_RESET_CONFIRM: (name: string) =>
    `Hard reset ${name}? All its settings, including its name, location and Wi-Fi and network credentials, are erased and it restarts in AP provisioning mode. Recording stops until you set it up again, and its address changes, so update the camera's address in the NVR afterwards.`,
  SOFT_RESET_ACTION: "Soft reset camera",
  HARD_RESET_ACTION: "Hard reset camera",
  BACK_TO_RESET_MODE: "Back to reset mode",
  RESET_FAILED: (name: string) =>
    `Couldn't factory reset ${name}. Check that the camera is online and try again.`,
  RETRY_RESET: "Retry factory reset camera" as const,
  SOFT_RESET_STARTED: (name: string) => `Soft reset started for ${name}`,
  HARD_RESET_STARTED: (name: string) => `Hard reset started for ${name}`,
} as const;
