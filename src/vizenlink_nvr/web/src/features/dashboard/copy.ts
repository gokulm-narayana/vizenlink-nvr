export const DASHBOARD_COPY = {
  TITLE: "Dashboard",
  SUBTITLE: "System Health & Diagnostics",
  GLOBAL_OUTAGES: "Camera outage history",

  METRIC_RECORDER_STATUS: "Recorder status",
  METRIC_CAMERAS_ONLINE: "Cameras online",
  METRIC_RECORDING_NOW: "Recording enabled",
  METRIC_STORAGE_USED: "Storage used",
  METRIC_ACTIVE_ALERTS: "Active alerts",

  STORAGE_TITLE: "Storage",
  STORAGE_FREE: "Free space",
  STORAGE_ESTIMATED_RETENTION: "Estimated retention",
  STORAGE_RESERVE: "Reserve",
  STORAGE_PATH_COPY_LABEL: "Copy storage path",
  STORAGE_PATH_COPIED_TOAST: "Path copied",
  STORAGE_PATH_FALLBACK_CAPTION: "Press Ctrl+C or Cmd+C to copy.",

  ALERTS_TITLE: "Alerts",
  ALERTS_EMPTY: "All clear. No active alerts.",
  ALERTS_DISMISS: "Dismiss alert",

  CAMERAS_TITLE: "Cameras",
  CAMERAS_EMPTY_OPERATOR_TITLE: "No cameras yet",
  CAMERAS_EMPTY_OPERATOR_DESC: "Add a camera and its status appears here.",
  CAMERAS_EMPTY_VIEWER_TITLE: "No cameras assigned",
  CAMERAS_EMPTY_VIEWER_DESC: "Ask the NVR owner to give you access to a camera.",
  CAMERAS_ADD_BUTTON: "Add camera",
  VIEW_OUTAGE_HISTORY: "View outage history",

  OUTAGES_TITLE: "Camera outage history",
  OUTAGES_CAMERA_TITLE: (name: string) => `${name} outage history`,
  OUTAGES_EMPTY_FILTERED_TITLE: "No outages recorded",
  OUTAGES_EMPTY_FILTERED_DESC: (name: string) =>
    `${name} has had no recording gaps in this period.`,
  OUTAGES_EMPTY_GLOBAL_TITLE: "No outages recorded",
  OUTAGES_EMPTY_GLOBAL_DESC:
    "None of your cameras have had recording gaps in this period.",
  OUTAGES_CLOSE: "Close outage history",
  OUTAGES_CLOSE_ARIA: "Close outage history",

  LOAD_ERROR_MESSAGE: "Couldn't load the dashboard. Check your connection and try again.",
  LOAD_ERROR_ACTION: "Reload dashboard" as const,

  ADVANCED_SUBSYSTEMS: "Subsystem health",
  ADVANCED_UPTIME: "Recorder uptime",
  ADVANCED_RAW_DETAILS: "Raw health details",
} as const;
