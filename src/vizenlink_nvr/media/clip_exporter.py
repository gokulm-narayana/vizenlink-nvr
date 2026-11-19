"""MP4 clip export and lossless fMP4 stream copying engine (PLAY-06)."""

from __future__ import annotations

import logging
import os
import shutil
import struct
import subprocess
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
    def transcode_to_playable_mp4(input_path: Path, output_path: Path) -> bool:
        """Normalize a clip into H.264 + AAC faststart MP4 when ffmpeg is available."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin is None or not input_path.exists() or input_path.stat().st_size < 512:
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp4 = output_path.with_name(f"{output_path.name}.tmp_{uuid.uuid4().hex[:8]}.mp4")
        cmd = [
            ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale='min(1280,iw)':-2",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(tmp_mp4),
        ]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0 and tmp_mp4.exists() and tmp_mp4.stat().st_size > 0:
                if os.name == "posix":
                    os.chmod(tmp_mp4, 0o640)
                tmp_mp4.replace(output_path)
                logger.info(
                    "Transcoded clip %s to playable H.264 MP4 (%d bytes)",
                    output_path,
                    output_path.stat().st_size,
                )
                return True
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ffmpeg transcode skipped for %s: %s", input_path, exc)
        finally:
            if tmp_mp4.exists():
                tmp_mp4.unlink(missing_ok=True)
        return False

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
            ClipExporter.transcode_to_playable_mp4(output_path, output_path)
            logger.info(
                "Successfully exported clip to %s (%d bytes)",
                output_path,
                output_path.stat().st_size,
            )
            return output_path
        finally:
            if tmp_output.exists():
                tmp_output.unlink(missing_ok=True)

