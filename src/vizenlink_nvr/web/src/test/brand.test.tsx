import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import React from "react";
import { BrandLogo } from "../components/BrandLogo";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function getPngDimensions(buf: Buffer): { width: number; height: number } {
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  return { width, height };
}

function computeSha256(buf: Buffer): string {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

describe("Brand assets and provenance verification", () => {
  const brandDir = path.resolve(__dirname, "../assets/brand");
  const faviconPath = path.resolve(__dirname, "../../public/favicon.png");
  const provPath = path.join(brandDir, "provenance.json");

  it("six brand PNGs exist, are non-empty, and their aspect ratios match contract within ±0.25", () => {
    const assets = [
      { name: "vizenlink-mark-light.png", expectedAspect: 1.47 },
      { name: "vizenlink-mark-dark.png", expectedAspect: 1.47 },
      { name: "vizenlink-wordmark-light.png", expectedAspect: 10.3 },
      { name: "vizenlink-wordmark-dark.png", expectedAspect: 10.3 },
      { name: "vizenlink-full-light.png", expectedAspect: 1.3 },
      { name: "vizenlink-full-dark.png", expectedAspect: 1.3 },
    ];

    for (const a of assets) {
      const filePath = path.join(brandDir, a.name);
      expect(fs.existsSync(filePath), `Missing ${a.name}`).toBe(true);
      const buf = fs.readFileSync(filePath);
      expect(buf.length).toBeGreaterThan(0);

      const { width, height } = getPngDimensions(buf);
      const aspect = width / height;
      expect(Math.abs(aspect - a.expectedAspect)).toBeLessThanOrEqual(0.25);
    }
  });

  it("provenance.json matches source repo and hashes all committed outputs exactly", () => {
    expect(fs.existsSync(provPath)).toBe(true);
    const prov = JSON.parse(fs.readFileSync(provPath, "utf8"));

    expect(prov.source.repo).toBe("mobilecctvapp");
    expect(prov.source.dir).toBe("assets/branding");
    expect(prov.source.files["vizenlink_light.png"]).toBeDefined();
    expect(prov.source.files["vizenlink_dark.png"]).toBeDefined();

    // Verify all files in brandDir are listed in provenance.json
    const brandFiles = fs.readdirSync(brandDir).filter((f) => f.endsWith(".png"));
    const outputKeys = Object.keys(prov.outputs);

    for (const f of brandFiles) {
      expect(outputKeys).toContain(f);
    }

    // Verify each output's SHA-256 and dimensions
    for (const [filename, meta] of Object.entries(prov.outputs) as [string, any][]) {
      const filePath = filename === "favicon.png" ? faviconPath : path.join(brandDir, filename);
      expect(fs.existsSync(filePath), `Missing output file ${filename}`).toBe(true);
      const buf = fs.readFileSync(filePath);

      const hash = computeSha256(buf);
      expect(hash).toBe(meta.sha256);

      const { width, height } = getPngDimensions(buf);
      expect(width).toBe(meta.width);
      expect(height).toBe(meta.height);

      expect(["vizenlink_light.png", "vizenlink_dark.png"]).toContain(meta.source);
    }
  });

  it("optional mobile source re-hash when NVR_MOBILE_BRANDING_DIR is set", () => {
    const mobileDir = process.env.NVR_MOBILE_BRANDING_DIR;
    if (mobileDir && fs.existsSync(mobileDir)) {
      const prov = JSON.parse(fs.readFileSync(provPath, "utf8"));
      for (const [srcName, expectedHash] of Object.entries(prov.source.files)) {
        const srcPath = path.join(mobileDir, srcName);
        expect(fs.existsSync(srcPath), `Missing mobile source ${srcName}`).toBe(true);
        const buf = fs.readFileSync(srcPath);
        const hash = computeSha256(buf);
        expect(hash).toBe(expectedHash);
      }
    }
  });

  it("BrandLogo variant=lockup renders theme-swap classes and empty alt", () => {
    const { container } = render(<BrandLogo variant="lockup" />);
    const imgs = container.querySelectorAll("img");
    expect(imgs.length).toBe(4); // light mark, dark mark, light wordmark, dark wordmark

    for (const img of Array.from(imgs)) {
      expect(img.getAttribute("decoding")).toBe("async");
      expect(img.getAttribute("alt")).toBe("");
      expect(img.hasAttribute("width")).toBe(true);
      expect(img.hasAttribute("height")).toBe(true);
    }
  });

  it("BrandLogo variant=full renders alt='VizenLink'", () => {
    render(<BrandLogo variant="full" />);
    const imgs = screen.getAllByAltText("VizenLink");
    expect(imgs.length).toBe(2); // light and dark full lockups
  });
});
