export const GALLERY_COPY = {
  TITLE: "Saved Media",
  TAB_SNAPSHOTS: "Snapshots",
  TAB_CLIPS: "Clips",

  FILTER_ALL_CAMERAS: "All cameras",
  FILTER_DATE_RANGE: "Select dates",
  FILTER_CLEAR: "Clear filters",
  FILTER_USER: "User",
  FILTER_USER_ANYONE: "Anyone",
  FILTER_USER_ME: "Me",

  EMPTY_TITLE: "Nothing saved yet",
  EMPTY_DESCRIPTION:
    "Nothing saved yet. Save a snapshot from Live or Playback, or export a clip, and it will appear here.",

  LOAD_MORE: "Load more items",
  LOAD_ERROR_MESSAGE: "Couldn't load the gallery. Check your connection and try again.",
  LOAD_ERROR_ACTION: "Reload gallery" as const,

  PREVIEW_CLOSE_LABEL: "Close preview",
  DOWNLOAD_SNAPSHOT: "Download snapshot",
  DOWNLOAD_CLIP: "Download clip",
  OPEN_IN_PLAYBACK: "Open in Playback",

  DELETE_SNAPSHOT: "Delete snapshot",
  DELETE_CLIP: "Delete clip",
  DELETE_CONFIRM_TITLE: (type: "snapshot" | "clip") => `Delete this ${type}?`,
  DELETE_CONFIRM_DESCRIPTION:
    "This permanently removes the file from the NVR and can't be undone.",
  DELETE_CONFIRM_ACTION: (type: "snapshot" | "clip") => `Delete ${type}`,
  DELETE_CANCEL_ACTION: (type: "snapshot" | "clip") => `Keep ${type}`,
  DELETE_ERROR_MESSAGE: (type: "snapshot" | "clip") =>
    `Couldn't delete the ${type}. Check your connection and try again.`,
  DELETE_ERROR_ACTION: (type: "snapshot" | "clip") =>
    `Retry delete ${type}` as `Retry delete ${string}`,

  METADATA_CAMERA: "Camera",
  METADATA_TIME: "Captured",
  METADATA_FILE_SIZE: "File size",
  METADATA_DURATION: "Duration",
} as const;
