export const LIVE_COPY = {
  TITLE: "Live",
  TOOLBAR_LAYOUT: "Layout:",
  CAMERAS_COUNT: (count: number) => `${count} camera${count === 1 ? "" : "s"}`,
  PAGE_INDICATOR: (current: number, total: number) => `Page ${current} of ${total}`,
  PREV_PAGE: "Previous page",
  NEXT_PAGE: "Next page",

  // Empty states
  EMPTY_HEADING_OPERATOR: "No cameras yet",
  EMPTY_BODY_OPERATOR:
    "Connect your first camera to start watching. Search the recorder's network or enter the camera details yourself.",
  EMPTY_ACTION_ADD: "Add camera",
  EMPTY_HEADING_VIEWER: "No cameras assigned",
  EMPTY_BODY_VIEWER: "Ask the NVR owner to give you access to a camera.",

  // Stream states and errors
  STREAM_ERROR_MESSAGE: "Can't play this stream. Retrying…",
  RETRY_STREAM_ACTION: "Retry stream",
  OFFLINE_BADGE: "Offline",
  LIVE_BADGE: "LIVE",
  CONNECTING_BADGE: "Connecting…",
  RECONNECTING_BADGE: "Reconnecting…",
  REC_BADGE: "REC",
  LAST_SEEN: (relative: string) => `Last seen ${relative}`,

  // Actions / Tooltips
  SNAPSHOT_LABEL: "Take snapshot",
  MUTE_LABEL: "Mute audio",
  UNMUTE_LABEL: "Unmute audio",
  MAXIMIZE_LABEL: "Maximize tile",
  MINIMIZE_LABEL: "Close maximized tile",
};
