export const DEVICES_COPY = {
  EMPTY_HEADING: "No mobile devices paired",
  EMPTY_BODY:
    "Open VizenLink on your phone, choose Add NVR, then scan the code from Pair mobile device.",
  PAIR_DEVICE: "Pair mobile device",
  COPY_CODE: "Copy pairing code",
  CODE_COPIED_TOAST: "Code copied",
  HTTP_FALLBACK: "Press Ctrl+C or Cmd+C to copy.",
  GENERATE_NEW_CODE: "Generate new code",
  CLOSE_PAIRING: "Close pairing",
  INIT_FAILED: "Couldn't generate a pairing code. Check your connection and try again.",
  RETRY_INIT: "Retry generate pairing code",
  REVOKE_TITLE: (name: string) => `Revoke ${name}?`,
  REVOKE_BODY: (name: string) =>
    `Revoke ${name}? It will be signed out and refused until it pairs again.`,
  REVOKE_ACTION: "Revoke device",
  KEEP_PAIRED: "Keep device paired",
  REVOKE_FAILED: (name: string) =>
    `Couldn't revoke ${name}. Check your connection and try again.`,
  RETRY_REVOKE: "Retry revoke device",
  LOAD_ERROR: "Couldn't load devices. Check your connection and try again.",
  RELOAD_DEVICES: "Reload devices",
} as const;
