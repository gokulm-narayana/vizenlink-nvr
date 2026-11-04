"""MP4 clip export and lossless fMP4 stream copying engine (PLAY-06)."""

from __future__ import annotations

import logging
import os
import struct
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_isobmff_boxes(raw_bytes: bytes) -> list[tuple[str, int, int]]:
    """Parse top-level ISOBMFF / MP4 boxes: returns list of (box_type, offset, box_length)."""
    offset = 0
    boxes: list[tuple[str, int, int]] = []
    total_len = len(raw_bytes)

    while offset + 8 <= total_len:
        size = struct.unpack(">I", raw_bytes[offset : offset + 4])[0]
        box_type = raw_bytes[offset + 4 : offset + 8].decode("ascii", errors="replace")

        if size == 0:
            box_len = total_len - offset
        elif size == 1:
            if offset + 16 > total_len:
                break
            box_len = struct.unpack(">Q", raw_bytes[offset + 8 : offset + 16])[0]
        else:
            box_len = size

        boxes.append((box_type, offset, box_len))
        if box_len <= 0:
            break
        offset += box_len

    return boxes


class ClipExporter:
    """Exports MP4 video clips from recording segments via lossless container assembly."""

    @staticmethod
    def export_fmp4_clip(
        segment_files: list[Path],
        output_path: Path,
    ) -> Path:
        """Concatenate contiguous fMP4 segment files into a single playable MP4 clip.

        Uses atomic temp-then-rename to ensure file integrity.
        """
        if not segment_files:
            raise ValueError("No segment files provided for clip export")

        valid_files = [f for f in segment_files if f.exists() and f.stat().st_size > 0]
        if not valid_files:
            raise ValueError("None of the provided segment files exist on disk")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_output = output_path.with_name(f"{output_path.name}.tmp_{uuid.uuid4().hex[:8]}")

        out_buffer = bytearray()
        header_written = False

        for fpath in valid_files:
            raw = fpath.read_bytes()
            boxes = parse_isobmff_boxes(raw)

            if not header_written:
                # Write ftyp and moov from first segment
                for b_type, b_offset, b_len in boxes:
                    if b_type in ("ftyp", "moov"):
                        out_buffer.extend(raw[b_offset : b_offset + b_len])
                header_written = True

            # Write all fragment boxes (moof, mdat, sidx)
            for b_type, b_offset, b_len in boxes:
                if b_type in ("moof", "mdat", "sidx"):
                    out_buffer.extend(raw[b_offset : b_offset + b_len])

        # If input files didn't have standard ISOBMFF boxes, fallback to raw concatenation
        if not header_written or len(out_buffer) == 0:
            for fpath in valid_files:
                out_buffer.extend(fpath.read_bytes())

        # Atomic temp-then-rename
        try:
            tmp_output.write_bytes(out_buffer)
            if os.name == "posix":
                os.chmod(tmp_output, 0o640)
            tmp_output.replace(output_path)
            logger.info("Successfully exported clip to %s (%d bytes)", output_path, len(out_buffer))
            return output_path
        finally:
            if tmp_output.exists():
                tmp_output.unlink(missing_ok=True)
