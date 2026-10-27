"""CLI tool to download and cache the pinned MediaMTX binary."""

import argparse
import sys
from pathlib import Path

from vizenlink_nvr.media.binary import fetch


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and verify pinned MediaMTX binary")
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Optional destination directory (defaults to platform user cache)",
    )
    args = parser.parse_args()

    try:
        bin_path = fetch(dest_dir=args.dest_dir)
        print(f"MediaMTX binary ready at: {bin_path}")
    except Exception as exc:
        print(f"Error fetching MediaMTX: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
