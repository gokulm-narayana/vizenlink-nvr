export const ADD_CAMERA_COPY = {
  TITLE: "Add camera",
  PAGE_NOTE:
    "Enter the camera's details yourself. The web app can't scan your network; to find cameras automatically, run `nvr cameras scan` on the NVR host.",
  PAGE_NOTE_PRE:
    "Enter the camera's details yourself. The web app can't scan your network; to find cameras automatically, run ",
  PAGE_NOTE_CMD: "nvr cameras scan",
  PAGE_NOTE_POST: " on the NVR host.",
  STEP_CAPTION: (current: number, total: number = 3) => `Step ${current} of ${total}`,
  STEPS: ["Camera", "Details", "Streams"] as const,

  // Step 1: Camera
  SERIAL_LABEL: "Serial number",
  SERIAL_HELPER:
    "The camera's serial number. It becomes the camera ID and can't be changed later.",
  SERIAL_REQUIRED: "Serial number is required",
  SERIAL_INVALID:
    "Serial must be 1 to 64 characters (letters, digits, '.', '_', '-') and not 'add'",
  SERIAL_EXISTS: (serial: string) =>
    `A camera with serial ${serial} already exists. Check the serial number, or open the existing camera.`,
  OPEN_EXISTING_CAMERA: (serial: string) => `Open camera ${serial}`,

  HOST_LABEL: "IP address or hostname",
  HOST_REQUIRED: "IP address or hostname is required",

  PORT_LABEL: "HTTPS port",
  PORT_INVALID: "Port must be an integer between 1 and 65535",

  USERNAME_LABEL: "Camera username",
  USERNAME_REQUIRED: "Username is required",

  PASSWORD_LABEL: "Camera password",
  PASSWORD_HELPER: "The NVR stores it encrypted and never shows it again.",
  PASSWORD_REQUIRED: "Password is required",

  // Step 2: Details
  NAME_LABEL: "Name",
  NAME_HELPER: "Optional name. Defaults to the serial number if left empty.",
  LOCATION_LABEL: "Location",
  LOCATION_HELPER: "Optional physical location (e.g. Front Door, Warehouse).",
  GROUP_LABEL: "Group",
  GROUP_HELPER: "Optional group tag for organizing cameras.",

  // Step 3: Streams
  MAIN_STREAM_TITLE: "High-quality video (main stream)",
  SCHEME_LABEL: "Scheme",
  PATH_LABEL: "Path",
  STREAM_PORT_LABEL: "Port",
  SUB_STREAM_TOGGLE: "Use a lower-bandwidth stream for the camera grid",
  SUB_STREAM_TITLE: "Sub stream",
  SUB_PATH_REQUIRED: "Enter the camera's sub stream path.",
  SUB_PATH_HELPER: "Enter the camera's sub stream path.",

  // Advanced Stream Details
  STREAM_DETAILS_TITLE: "Stream details",
  CODEC_LABEL: "Codec",
  WIDTH_LABEL: "Width",
  HEIGHT_LABEL: "Height",
  TRANSPORT_LABEL: "Transport",
  PROFILE_TOKEN_LABEL: "Profile token",
  ENCODER_TOKEN_LABEL: "Encoder token",

  // Review List
  REVIEW_TITLE: "Review camera details",
  REVIEW_SERIAL: "Serial",
  REVIEW_ADDRESS: "Address",
  REVIEW_NAME: "Name",
  REVIEW_LOCATION: "Location",
  REVIEW_GROUP: "Group",
  REVIEW_STREAMS: "Streams",
  REVIEW_PASSWORD: "Password",

  // Buttons
  CONTINUE_TO_DETAILS: "Continue to details",
  CONTINUE_TO_STREAMS: "Continue to streams",
  BACK_TO_CAMERA: "Back to camera",
  BACK_TO_DETAILS: "Back to details",
  ADD_CAMERA_BUTTON: "Add camera",
  DISCARD_BUTTON: "Discard new camera",

  // Discard Dialog
  DISCARD_TITLE: "Discard this new camera?",
  DISCARD_BODY: "The details you entered will be lost.",
  KEEP_EDITING_BUTTON: "Keep editing camera",

  // Success & Error Feedback
  SUCCESS_TOAST: (name: string) =>
    `Added ${name}. It appears on Live once the NVR connects to it.`,
  VAULT_UNAVAILABLE_ERROR:
    "Couldn't add the camera. The NVR can't store camera passwords securely right now. Ask the NVR owner to check the NVR service, then try again.",
  GENERIC_ADD_ERROR:
    "Couldn't add the camera. Check your connection and the camera details, then try again.",
  RETRY_ADD: "Retry add camera" as const,
} as const;
