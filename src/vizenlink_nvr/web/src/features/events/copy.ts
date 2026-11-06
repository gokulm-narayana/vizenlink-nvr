export const EVENTS_COPY = {
  TITLE: "Events",
  FILTER_ALL_CAMERAS: "All cameras",
  FILTER_ALL_TYPES: "All types",
  FILTER_DATE_RANGE: "Select dates",
  FILTER_CLEAR: "Clear filters",
  FILTER_UNREAD_ONLY: "Unread only",

  EMPTY_NO_MATCH_TITLE: "No events match",
  EMPTY_NO_MATCH_DESCRIPTION:
    "No events match. Try a wider date range or clear the camera and type filters.",
  EMPTY_NO_EVENTS_TITLE: "No events yet",
  EMPTY_NO_EVENTS_DESCRIPTION:
    "No events yet. Events from your cameras show up here as they happen.",

  LOAD_MORE: "Load more events",
  LOAD_ERROR_MESSAGE: "Couldn't load events. Check your connection and try again.",
  LOAD_ERROR_ACTION: "Reload events" as const,

  PLAY_FOOTAGE: "Play footage",
  LOCK_LABEL: "Lock event",
  LOCK_ERROR_MESSAGE: "Couldn't lock the event. Check your connection and try again.",
  LOCK_ERROR_ACTION: "Retry lock event" as const,
  UNLOCK_ERROR_MESSAGE: "Couldn't unlock the event. Check your connection and try again.",
  UNLOCK_ERROR_ACTION: "Retry unlock event" as const,

  CLOSE_SHEET_LABEL: "Close event details",
  UNREAD_LABEL: "Unread",

  CLOCK_SYNCED: "Camera clock synced",
  CLOCK_UNCERTAIN: "Camera clock uncertain - NVR time used",
  NO_SNAPSHOT: "No snapshot available",

  DETAILS_TIME: "Time",
  DETAILS_CAMERA: "Camera",
  DETAILS_TYPE: "Event type",
  DETAILS_RAW_TOPIC: "Raw topic",
  DETAILS_CLOCK_SYNC: "Clock sync",
  DETAILS_ID: "Event ID",
} as const;
