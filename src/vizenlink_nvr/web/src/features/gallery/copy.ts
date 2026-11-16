export const GALLERY_COPY = {
  TITLE: "Gallery",
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
  SHARE_QR: "Share QR",
  HIDE_QR: "Hide QR",
  SHARE_QR_TITLE: "Scan QR code on mobile",
  SHARE_QR_DESCRIPTION:
    "Scan with your phone on the same Wi-Fi or LAN to open or download this file.",
  COPY_SHARE_LINK: "Copy share link",
  SHARE_LINK_COPIED_TOAST: "Share link copied",
  SHARE_ERROR_MESSAGE:
    "Couldn't generate QR share link. Check your connection and try again.",
  SHARE_ERROR_ACTION: "Retry QR share" as const,
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
