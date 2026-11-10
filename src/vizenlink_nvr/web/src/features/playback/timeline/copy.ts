export const TIMELINE_COPY = {
  LABEL_TIMELINE: "Timeline",
  LEGEND_RECORDED: "Recorded",
  LEGEND_OUTAGE: "Recording outage",
  LEGEND_RETENTION: "Removed by retention",
  LEGEND_EVENT: "Event",
  LEGEND_LOCKED: "Locked",

  TABLE_CAPTION: "Recorded video spans for this day",
  TABLE_HEADER_START: "Start Time",
  TABLE_HEADER_END: "End Time",
  TABLE_HEADER_DURATION: "Duration",

  MARKERS_LABEL: "Clip selection:",
  MARKER_SET_IN: "Set clip start",
  MARKER_SET_OUT: "Set clip end",
  MARKER_CLEAR: "Clear clip selection",

  TOOLTIP_RECORDED: "Recorded",
  TOOLTIP_OUTAGE: "Recording outage",
  TOOLTIP_RETENTION: "Removed by retention",
  TOOLTIP_EVENT: (type: string) => `Event: ${type}`,
  TOOLTIP_NO_FOOTAGE: "No footage",
};
