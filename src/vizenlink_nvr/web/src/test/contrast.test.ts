import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

interface RGB {
  r: number;
  g: number;
  b: number;
  a: number;
}

export function parseTokens(css: string): { light: Record<string, string>; dark: Record<string, string> } {
  const rootMatch = css.match(/:root\s*\{([^}]+)\}/);
  const darkMatch = css.match(/\.dark\s*\{([^}]+)\}/);
  if (!rootMatch || !darkMatch) {
    throw new Error("Could not find :root or .dark blocks in tokens.css");
  }

  function extract(str: string): Record<string, string> {
    const map: Record<string, string> = {};
    for (const line of str.split("\n")) {
      const m = line.match(/--([\w-]+):\s*([^;]+);/);
      if (m) {
        map[m[1].trim()] = m[2].trim();
      }
    }
    return map;
  }

  return { light: extract(rootMatch[1]), dark: extract(darkMatch[1]) };
}

export function parseRgb(color: string, base: RGB = { r: 255, g: 255, b: 255, a: 1 }): RGB {
  if (color.startsWith("#")) {
    let hex = color.slice(1);
    if (hex.length === 3) {
      hex = hex.split("").map((c) => c + c).join("");
    }
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
      a: 1,
    };
  }

  const m = color.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/);
  if (m) {
    const fg: RGB = {
      r: parseInt(m[1], 10),
      g: parseInt(m[2], 10),
      b: parseInt(m[3], 10),
      a: m[4] !== undefined ? parseFloat(m[4]) : 1,
    };
    if (fg.a < 1) {
      return {
        r: Math.round(fg.r * fg.a + base.r * (1 - fg.a)),
        g: Math.round(fg.g * fg.a + base.g * (1 - fg.a)),
        b: Math.round(fg.b * fg.a + base.b * (1 - fg.a)),
        a: 1,
      };
    }
    return fg;
  }
  throw new Error("Cannot parse color: " + color);
}

export function relLuminance(rgb: RGB): number {
  const sRGB = [rgb.r, rgb.g, rgb.b].map((v) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * sRGB[0] + 0.7152 * sRGB[1] + 0.0722 * sRGB[2];
}

export function contrastRatio(fgHex: string | RGB, bgHex: string | RGB, base?: RGB): number {
  const fg = typeof fgHex === "string" ? parseRgb(fgHex, base) : fgHex;
  const bg = typeof bgHex === "string" ? parseRgb(bgHex, base) : bgHex;
  const l1 = relLuminance(fg);
  const l2 = relLuminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("WCAG 2.2 Contrast Verification against tokens.css", () => {
  const tokensPath = path.resolve(__dirname, "../styles/tokens.css");
  const css = fs.readFileSync(tokensPath, "utf8");
  const tokens = parseTokens(css);

  interface TableRow {
    name: string;
    fg: string;
    bg: string;
    lightExpected: number;
    darkExpected: number;
    isText: boolean;
  }

  const rows: TableRow[] = [
    { name: "--foreground on --background", fg: "foreground", bg: "background", lightExpected: 16.06, darkExpected: 13.98, isText: true },
    { name: "--foreground on --card", fg: "foreground", bg: "card", lightExpected: 17.40, darkExpected: 12.55, isText: true },
    { name: "--foreground on --muted", fg: "foreground", bg: "muted", lightExpected: 15.52, darkExpected: 10.58, isText: true },
    { name: "--muted-foreground on --card", fg: "muted-foreground", bg: "card", lightExpected: 6.05, darkExpected: 7.64, isText: true },
    { name: "--muted-foreground on --background", fg: "muted-foreground", bg: "background", lightExpected: 5.58, darkExpected: 8.51, isText: true },
    { name: "--muted-foreground on --muted", fg: "muted-foreground", bg: "muted", lightExpected: 5.39, darkExpected: 6.44, isText: true },
    { name: "--primary-foreground on --primary", fg: "primary-foreground", bg: "primary", lightExpected: 6.44, darkExpected: 8.01, isText: true },
    { name: "--primary-foreground on --primary-hover", fg: "primary-foreground", bg: "primary-hover", lightExpected: 8.86, darkExpected: 10.14, isText: true },
    { name: "--primary-text on --card", fg: "primary-text", bg: "card", lightExpected: 6.44, darkExpected: 7.48, isText: true },
    { name: "--primary-text on --background", fg: "primary-text", bg: "background", lightExpected: 5.94, darkExpected: 8.33, isText: true },
    { name: "--primary-text on --selected", fg: "primary-text", bg: "selected", lightExpected: 5.64, darkExpected: 6.61, isText: true },
    { name: "--foreground on --selected", fg: "foreground", bg: "selected", lightExpected: 15.24, darkExpected: 11.09, isText: true },
    { name: "--ring against --card", fg: "ring", bg: "card", lightExpected: 6.44, darkExpected: 9.47, isText: false },
    { name: "--ring against --background", fg: "ring", bg: "background", lightExpected: 5.94, darkExpected: 10.55, isText: false },
    { name: "--primary fill against --card", fg: "primary", bg: "card", lightExpected: 6.44, darkExpected: 7.48, isText: false },
    { name: "--input control border against --card", fg: "input", bg: "card", lightExpected: 4.65, darkExpected: 4.80, isText: false },
    { name: "--input control border against --background", fg: "input", bg: "background", lightExpected: 4.29, darkExpected: 5.35, isText: false },
    { name: "--input control border against --muted", fg: "input", bg: "muted", lightExpected: 4.15, darkExpected: 4.05, isText: false },
    { name: "Retention span (--input) against canvas --card", fg: "input", bg: "card", lightExpected: 4.65, darkExpected: 4.80, isText: false },
    { name: "--destructive-foreground on --destructive", fg: "destructive-foreground", bg: "destructive", lightExpected: 5.62, darkExpected: 5.08, isText: true },
    { name: "--success text on --card", fg: "success", bg: "card", lightExpected: 5.48, darkExpected: 8.62, isText: true },
    { name: "--success text on --background", fg: "success", bg: "background", lightExpected: 5.06, darkExpected: 9.60, isText: true },
    { name: "--success text on own subtle fill", fg: "success", bg: "success-subtle", lightExpected: 4.90, darkExpected: 7.47, isText: true },
    { name: "--offline text on --card", fg: "offline", bg: "card", lightExpected: 6.29, darkExpected: 6.16, isText: true },
    { name: "--offline text on --background", fg: "offline", bg: "background", lightExpected: 5.80, darkExpected: 6.86, isText: true },
    { name: "--offline text on own subtle fill", fg: "offline", bg: "offline-subtle", lightExpected: 5.48, darkExpected: 5.56, isText: true },
    { name: "--warning text on --card", fg: "warning", bg: "card", lightExpected: 7.09, darkExpected: 7.72, isText: true },
    { name: "--warning text on --background", fg: "warning", bg: "background", lightExpected: 6.54, darkExpected: 8.59, isText: true },
    { name: "--warning text on own subtle fill", fg: "warning", bg: "warning-subtle", lightExpected: 6.28, darkExpected: 6.19, isText: true },
    { name: "--info text on --card", fg: "info", bg: "card", lightExpected: 5.36, darkExpected: 9.17, isText: true },
    { name: "--info text on --background", fg: "info", bg: "background", lightExpected: 4.94, darkExpected: 10.21, isText: true },
    { name: "--info text on own subtle fill", fg: "info", bg: "info-subtle", lightExpected: 4.81, darkExpected: 7.69, isText: true },
    { name: "--critical text on --card", fg: "critical", bg: "card", lightExpected: 5.62, darkExpected: 6.51, isText: true },
    { name: "--critical text on --background", fg: "critical", bg: "background", lightExpected: 5.19, darkExpected: 7.25, isText: true },
    { name: "--critical text on own subtle fill", fg: "critical", bg: "critical-subtle", lightExpected: 4.96, darkExpected: 5.91, isText: true },
    { name: "--rec dot against --card", fg: "rec", bg: "card", lightExpected: 5.62, darkExpected: 5.38, isText: false },
    { name: "--primary-foreground playhead over --primary recorded span", fg: "primary-foreground", bg: "primary", lightExpected: 6.44, darkExpected: 8.01, isText: false },
  ];

  describe.each(rows)("$name", ({ fg, bg, lightExpected, darkExpected, isText }) => {
    it("meets light-theme ratio and thresholds", () => {
      const ratio = contrastRatio(tokens.light[fg], tokens.light[bg]);
      expect(Math.abs(ratio - lightExpected)).toBeLessThanOrEqual(0.1);
      const minThreshold = isText ? 4.5 : 3.0;
      expect(ratio).toBeGreaterThanOrEqual(minThreshold);
    });

    it("meets dark-theme ratio and thresholds", () => {
      const ratio = contrastRatio(tokens.dark[fg], tokens.dark[bg]);
      expect(Math.abs(ratio - darkExpected)).toBeLessThanOrEqual(0.1);
      const minThreshold = isText ? 4.5 : 3.0;
      expect(ratio).toBeGreaterThanOrEqual(minThreshold);
    });
  });

  describe("video-overlay rows (worst-case white frame compositing)", () => {
    // Composite rgba(0,0,0,0.72) over #FFFFFF (= #474747)
    const worstCaseOverlay = parseRgb("rgba(0, 0, 0, 0.72)", { r: 255, g: 255, b: 255, a: 1 });

    it("--video-fg on worst-case --video-overlay meets 9.3:1 in both themes", () => {
      for (const theme of ["light", "dark"] as const) {
        const ratio = contrastRatio(tokens[theme]["video-fg"], worstCaseOverlay);
        expect(Math.abs(ratio - 9.3)).toBeLessThanOrEqual(0.1);
        expect(ratio).toBeGreaterThanOrEqual(4.5);
      }
    });

    const statusIcons = [
      { name: "online / success", token: "success", expected: 4.8 },
      { name: "offline", token: "offline", expected: 3.5 },
      { name: "warning", token: "warning", expected: 4.3 },
      { name: "rec", token: "rec", expected: 3.0 },
      { name: "info", token: "info", expected: 5.1 },
    ];

    describe.each(statusIcons)("Status icon $name on worst-case overlay", ({ token, expected }) => {
      it("uses dark-theme status tokens in both themes and meets non-text threshold 3.0:1", () => {
        // Video chrome is fixed dark, so status icons use dark tokens in both themes
        const darkIconColor = tokens.dark[token];
        const ratio = contrastRatio(darkIconColor, worstCaseOverlay);
        expect(Math.abs(ratio - expected)).toBeLessThanOrEqual(0.1);
        expect(ratio).toBeGreaterThanOrEqual(3.0);
      });
    });
  });

  describe("Negative control", () => {
    it("flags decorative --border on --card as below 3.0:1", () => {
      const lightBorderRatio = contrastRatio(tokens.light["border"], tokens.light["card"]);
      expect(lightBorderRatio).toBeLessThan(3.0);
      const darkBorderRatio = contrastRatio(tokens.dark["border"], tokens.dark["card"]);
      expect(darkBorderRatio).toBeLessThan(3.0);
    });
  });
});
