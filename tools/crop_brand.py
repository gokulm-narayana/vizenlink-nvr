#!/usr/bin/env python3
"""Crop and downscale VizenLink branding assets from the mobile app (D-03, D-04)."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def compute_sha256(path: Path) -> str:
    """Compute hex SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_alpha_bands(img: Image.Image) -> list[tuple[int, int]]:
    """Find continuous horizontal bands of rows containing non-transparent pixels."""
    w, h = img.size
    has_alpha = [False] * h
    # Check pixels per row
    for y in range(h):
        for x in range(w):
            if img.getpixel((x, y))[3] > 0:
                has_alpha[y] = True
                break

    bands: list[tuple[int, int]] = []
    in_band = False
    start = 0
    for y, px in enumerate(has_alpha):
        if px and not in_band:
            in_band = True
            start = y
        elif not px and in_band:
            in_band = False
            bands.append((start, y - 1))
    if in_band:
        bands.append((start, len(has_alpha) - 1))
    return bands


def get_band_bbox(img: Image.Image, y_start: int, y_end: int) -> tuple[int, int, int, int]:
    """Find bounding box (min_x, y_start, max_x, y_end) for non-transparent pixels in row range."""
    w, _ = img.size
    min_x = w
    max_x = 0
    for y in range(y_start, y_end + 1):
        for x in range(w):
            if img.getpixel((x, y))[3] > 0:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
    return (min_x, y_start, max_x, y_end)


def crop_brand_assets(src_dir: Path, out_dir: Path, favicon_path: Path) -> None:
    """Crop mark, wordmark, full lockup and favicon, then write provenance.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    favicon_path.parent.mkdir(parents=True, exist_ok=True)

    sources = {
        "light": src_dir / "vizenlink_light.png",
        "dark": src_dir / "vizenlink_dark.png",
    }

    source_hashes: dict[str, str] = {}
    for src_path in sources.values():
        if not src_path.exists():
            raise FileNotFoundError(f"Source image not found: {src_path}")
        source_hashes[src_path.name] = compute_sha256(src_path)

    outputs_meta: dict[str, dict[str, object]] = {}

    target_heights = {
        "mark": 128,
        "wordmark": 48,
        "full": 480,
    }

    mark_width_at_32 = 0.0
    wordmark_width_at_12 = 0.0

    for theme, src_path in sources.items():
        with Image.open(src_path) as img:
            img = img.convert("RGBA")
            w, h = img.size
            bands = find_alpha_bands(img)
            if len(bands) < 3:
                raise ValueError(f"Expected at least 3 bands in {src_path.name}, found {len(bands)}")

            # Band 0 = mark, Band 1 = wordmark, Band 2 = tagline
            mark_box = get_band_bbox(img, bands[0][0], bands[0][1])
            wordmark_box = get_band_bbox(img, bands[1][0], bands[1][1])
            full_box = get_band_bbox(img, bands[0][0], bands[-1][1])

            mark_crop = img.crop((mark_box[0], mark_box[1], mark_box[2] + 1, mark_box[3] + 1))
            wm_box = (wordmark_box[0], wordmark_box[1], wordmark_box[2] + 1, wordmark_box[3] + 1)
            wordmark_crop = img.crop(wm_box)
            full_crop = img.crop((full_box[0], full_box[1], full_box[2] + 1, full_box[3] + 1))

            crops = {
                "mark": mark_crop,
                "wordmark": wordmark_crop,
                "full": full_crop,
            }

            for asset_type, cropped in crops.items():
                cw, ch = cropped.size
                target_h = target_heights[asset_type]
                target_w = round(cw * target_h / ch)
                resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)

                out_filename = f"vizenlink-{asset_type}-{theme}.png"
                out_file = out_dir / out_filename
                resized.save(out_file, format="PNG", optimize=True)

                outputs_meta[out_filename] = {
                    "sha256": compute_sha256(out_file),
                    "width": target_w,
                    "height": target_h,
                    "source": src_path.name,
                }
                ar = target_w / target_h
                print(f"Saved {out_filename}: {target_w}x{target_h} (source {cw}x{ch}, aspect {ar:.2f})")

                if theme == "light":
                    if asset_type == "mark":
                        mark_width_at_32 = 32.0 * (cw / ch)
                    elif asset_type == "wordmark":
                        wordmark_width_at_12 = 12.0 * (cw / ch)

            # Generate 32x32 favicon from light mark
            if theme == "light":
                mark_cropped = crops["mark"]
                mc_w, mc_h = mark_cropped.size
                # Fit inside 32x32 transparent square
                fav_w = 32
                fav_h = round(mc_h * fav_w / mc_w)
                if fav_h > 32:
                    fav_h = 32
                    fav_w = round(mc_w * fav_h / mc_h)
                fav_mark = mark_cropped.resize((fav_w, fav_h), Image.Resampling.LANCZOS)

                fav_canvas = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                paste_x = (32 - fav_w) // 2
                paste_y = (32 - fav_h) // 2
                fav_canvas.paste(fav_mark, (paste_x, paste_y), fav_mark)
                fav_canvas.save(favicon_path, format="PNG", optimize=True)

                outputs_meta["favicon.png"] = {
                    "sha256": compute_sha256(favicon_path),
                    "width": 32,
                    "height": 32,
                    "source": src_path.name,
                }
                print(f"Saved favicon.png: 32x32 (mark resized to {fav_w}x{fav_h})")

    # Check sidebar header width fit (must be <= 208 px)
    total_sidebar_header_width = mark_width_at_32 + 8.0 + wordmark_width_at_12
    print(
        f"Sidebar fit: mark={mark_width_at_32:.1f}px + gap=8px + wordmark={wordmark_width_at_12:.1f}px "
        f"= {total_sidebar_header_width:.1f}px (limit: 208px)"
    )
    if total_sidebar_header_width > 208.0:
        raise ValueError(f"Sidebar header width {total_sidebar_header_width:.1f}px exceeds 208px limit!")

    # Write provenance.json
    provenance = {
        "source": {
            "repo": "mobilecctvapp",
            "dir": "assets/branding",
            "files": source_hashes,
        },
        "tool": "tools/crop_brand.py",
        "outputs": outputs_meta,
    }
    prov_file = out_dir / "provenance.json"
    with open(prov_file, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
    print(f"Saved {prov_file}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Crop branding assets from mobile app")
    parser.add_argument("--src", type=Path, required=True, help="Path to mobile assets/branding")
    parser.add_argument("--out", type=Path, required=True, help="Path to web src/assets/brand")
    parser.add_argument("--favicon", type=Path, required=True, help="Path to public/favicon.png")
    args = parser.parse_args()

    crop_brand_assets(args.src, args.out, args.favicon)


if __name__ == "__main__":
    main()
