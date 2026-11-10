export const PLAYBACK_COPY = {
  title: "Playback",
  emptyDay: "No footage on this day. Pick a day marked with a dot, or check that recording is on for this camera.",
  noFootageAtTime: "No footage at this time",
  loadingTimeline: "Loading timeline…",
  loadError: "Couldn't load playback. Check your connection and try again.",
  retryPlayback: "Retry playback",

  // Snapshot
  snapshotSaved: "Snapshot saved",
  snapshotError: "Couldn't save the snapshot. Check your connection and that the NVR has free storage, then try again.",
  retrySaveSnapshot: "Retry save snapshot",

  // Export
  exportClip: "Export clip",
  exportDialogTitle: "Export clip",
  exportSuccessToast: "Clip exported",
  openInGallery: "Open in Saved Media",
  keepEditingClip: "Keep editing clip",
  retryExportClip: "Retry export clip",
  exportError: "Couldn't export the clip. Check your connection and that the time range has footage, then try again.",
  formatMp4: "MP4",
  formatLabel: "Format",

  // Toolbar & Transport
  cameraLabel: "Camera",
  dateLabel: "Date",
  jumpToTime: "Jump to time",
  eventsLink: "Events",
  moreControls: "More playback controls",
  play: "Play",
  pause: "Pause",
  back10s: "Back 10 seconds",
  forward10s: "Forward 10 seconds",
  speed: "Speed",
  mute: "Mute",
  unmute: "Unmute",
  snapshot: "Take snapshot",
  markIn: "Set clip start",
  markOut: "Set clip end",
  fullscreen: "Toggle fullscreen",
} as const;
