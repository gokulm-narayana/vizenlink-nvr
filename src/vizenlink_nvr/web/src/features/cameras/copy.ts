export const CAMERAS_COPY = {
  EMPTY_HEADING: "No cameras yet",
  EMPTY_BODY:
    "Add a camera by entering its details. The web app can't scan your network, so to find cameras automatically, run `nvr cameras scan` on the NVR host.",
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
} as const;
