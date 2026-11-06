import { describe, it, expect } from "vitest";
import {
  isWdrVisible,
  availableNightVisionTypes,
  resolutionLabels,
  clampSetting,
  canPerformMaintenance,
} from "./capabilities";

describe("Camera capabilities gating (mirrors test_camera_settings_ui.py)", () => {
  describe("isWdrVisible", () => {
    it("returns false when wdr_supported is false or missing", () => {
      expect(isWdrVisible({ wdr_supported: false })).toBe(false);
      expect(isWdrVisible({})).toBe(false);
      expect(isWdrVisible(null)).toBe(false);
    });

    it("returns true when wdr_supported is true", () => {
      expect(isWdrVisible({ wdr_supported: true })).toBe(true);
    });
  });

  describe("availableNightVisionTypes", () => {
    it("returns only grey for basic IR sensor", () => {
      expect(
        availableNightVisionTypes({
          color_capable: false,
          smart_capable: false,
        })
      ).toEqual(["grey"]);
    });

    it("returns [grey, color] for color capable sensor", () => {
      expect(
        availableNightVisionTypes({
          color_capable: true,
          smart_capable: false,
        })
      ).toEqual(["grey", "color"]);
    });

    it("returns [grey, color, smart] for full dual-mode sensor", () => {
      expect(
        availableNightVisionTypes({
          color_capable: true,
          smart_capable: true,
        })
      ).toEqual(["grey", "color", "smart"]);
    });

    it("supports night_vision_color_capable and night_vision_smart_capable property names", () => {
      expect(
        availableNightVisionTypes({
          night_vision_color_capable: true,
          night_vision_smart_capable: true,
        })
      ).toEqual(["grey", "color", "smart"]);
    });
  });

  describe("resolutionLabels", () => {
    it("formats resolution options in camera-reported order", () => {
      const opts = {
        resolutions: [
          { width: 2560, height: 1440 },
          { width: 1920, height: 1080 },
        ],
      };
      expect(resolutionLabels(opts)).toEqual(["2560x1440", "1920x1080"]);
    });

    it("handles single resolution", () => {
      const opts = {
        resolutions: [{ width: 640, height: 360 }],
      };
      expect(resolutionLabels(opts)).toEqual(["640x360"]);
    });

    it("returns empty array when resolutions missing or empty", () => {
      expect(resolutionLabels(null)).toEqual([]);
      expect(resolutionLabels({})).toEqual([]);
      expect(resolutionLabels({ resolutions: [] })).toEqual([]);
    });
  });

  describe("clampSetting", () => {
    it("clamps values within [min, max]", () => {
      expect(clampSetting(50, 0, 100)).toBe(50);
      expect(clampSetting(-10, 0, 100)).toBe(0);
      expect(clampSetting(150, 0, 100)).toBe(100);
    });
  });

  describe("canPerformMaintenance", () => {
    it("allows owner and operator", () => {
      expect(canPerformMaintenance("owner")).toBe(true);
      expect(canPerformMaintenance("operator")).toBe(true);
    });

    it("disallows viewer or empty roles", () => {
      expect(canPerformMaintenance("viewer")).toBe(false);
      expect(canPerformMaintenance("guest")).toBe(false);
      expect(canPerformMaintenance(null)).toBe(false);
      expect(canPerformMaintenance(undefined)).toBe(false);
    });
  });
});
