/**
 * Capability gating helpers ported from the legacy view.
 * Mirrors tests/unit/test_camera_settings_ui.py.
 */

export interface ImagingCapabilities {
  wdr_supported?: boolean;
  night_vision_color_capable?: boolean;
  night_vision_smart_capable?: boolean;
}

export interface VideoEncoderResolution {
  width: number;
  height: number;
}

export interface VideoEncoderCapabilities {
  resolutions?: VideoEncoderResolution[];
}

/**
 * Determine whether WDR controls should render in the UI (SET-08).
 * Unsupported options are hidden, not disabled.
 */
export function isWdrVisible(options?: { wdr_supported?: boolean } | null): boolean {
  return Boolean(options?.wdr_supported);
}

/**
 * Filter available night vision choices based on sensor capability flags.
 * Returns ["grey"], ["grey", "color"], or ["grey", "color", "smart"].
 */
export function availableNightVisionTypes(status?: {
  color_capable?: boolean;
  smart_capable?: boolean;
  night_vision_color_capable?: boolean;
  night_vision_smart_capable?: boolean;
} | null): string[] {
  const types = ["grey"];
  const colorCapable = Boolean(status?.color_capable ?? status?.night_vision_color_capable);
  const smartCapable = Boolean(status?.smart_capable ?? status?.night_vision_smart_capable);

  if (colorCapable) {
    types.push("color");
  }
  if (smartCapable) {
    types.push("smart");
  }
  return types;
}

/**
 * Format available resolutions for the encoder dropdown selector in order reported.
 */
export function resolutionLabels(options?: {
  resolutions?: Array<{ width: number; height: number }>;
} | null): string[] {
  if (!options?.resolutions || options.resolutions.length === 0) {
    return [];
  }
  return options.resolutions.map((r) => `${r.width}x${r.height}`);
}

/**
 * Clamp setting value within allowed [min, max] range.
 */
export function clampSetting(value: number, minVal: number, maxVal: number): number {
  return Math.max(minVal, Math.min(maxVal, value));
}

/**
 * Verify role authorization for maintenance actions (reboot and factory reset).
 * Allowed for owner and operator, but not viewer or null/undefined.
 */
export function canPerformMaintenance(role?: string | null): boolean {
  return role === "owner" || role === "operator";
}
