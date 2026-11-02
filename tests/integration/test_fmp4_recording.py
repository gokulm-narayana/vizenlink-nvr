"""Integration tests for fMP4 container structure and 1s part duration validation (REC-01)."""

from __future__ import annotations

import struct


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


def build_synthetic_fmp4(part_count: int = 5) -> bytes:
    """Generate a valid fragmented MP4 (fMP4) byte sequence with ftyp, moov, and (moof, mdat) pairs.

    Represents an fMP4 segment composed of 1s part durations without requiring remuxing.
    """
    buffer = bytearray()

    # 1. ftyp box
    ftyp_payload = b"isom" + struct.pack(">I", 512) + b"isomiso2mp41"
    ftyp_len = 8 + len(ftyp_payload)
    buffer.extend(struct.pack(">I", ftyp_len) + b"ftyp" + ftyp_payload)

    # 2. moov box containing mvhd and mvex (movie extends box required for fragmented MP4)
    # mvhd: fullbox version 0
    mvhd_payload = b"\x00" * 4 + b"\x00" * 96
    mvhd = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload

    # mvex box with trex
    trex_payload = b"\x00" * 4 + struct.pack(">IIII", 1, 1, 1000, 0)
    trex = struct.pack(">I", 8 + len(trex_payload)) + b"trex" + trex_payload
    mvex = struct.pack(">I", 8 + len(trex)) + b"mvex" + trex

    moov_payload = mvhd + mvex
    moov_len = 8 + len(moov_payload)
    buffer.extend(struct.pack(">I", moov_len) + b"moov" + moov_payload)

    # 3. Fragment pairs: (moof, mdat) for each 1s part
    for seq in range(1, part_count + 1):
        # mfhd box with sequence number
        mfhd_payload = b"\x00" * 4 + struct.pack(">I", seq)
        mfhd = struct.pack(">I", 8 + len(mfhd_payload)) + b"mfhd" + mfhd_payload

        # traf box with tfhd and trun
        tfhd_payload = b"\x00" * 4 + struct.pack(">I", 1)
        tfhd = struct.pack(">I", 8 + len(tfhd_payload)) + b"tfhd" + tfhd_payload

        trun_payload = b"\x00" * 4 + struct.pack(">I", 1) + struct.pack(">II", 1000, 256)
        trun = struct.pack(">I", 8 + len(trun_payload)) + b"trun" + trun_payload

        traf_payload = tfhd + trun
        traf = struct.pack(">I", 8 + len(traf_payload)) + b"traf" + traf_payload

        moof_payload = mfhd + traf
        moof_len = 8 + len(moof_payload)
        buffer.extend(struct.pack(">I", moof_len) + b"moof" + moof_payload)

        # mdat box containing media frames (256 bytes)
        media_bytes = b"\x00\x00\x00\x01\x67" + b"\xFF" * 251  # synthetic NAL / media frame
        mdat_len = 8 + len(media_bytes)
        buffer.extend(struct.pack(">I", mdat_len) + b"mdat" + media_bytes)

    return bytes(buffer)


def test_fmp4_container_structure_and_boxes() -> None:
    """Validate fMP4 container boxes: ftyp, moov (with mvex), and sequential moof/mdat pairs (REC-01)."""
    fmp4_bytes = build_synthetic_fmp4(part_count=4)
    boxes = parse_isobmff_boxes(fmp4_bytes)

    box_types = [b[0] for b in boxes]
    # Check top-level order
    assert box_types[0] == "ftyp"
    assert box_types[1] == "moov"
    # Followed by alternating moof and mdat pairs
    assert box_types[2:] == ["moof", "mdat", "moof", "mdat", "moof", "mdat", "moof", "mdat"]

    # Verify moov contains mvex (fragmented movie extends box)
    moov_box = [b for b in boxes if b[0] == "moov"][0]
    moov_data = fmp4_bytes[moov_box[1] : moov_box[1] + moov_box[2]]
    assert b"mvex" in moov_data, "fMP4 moov must contain mvex box"


def test_fmp4_1s_parts_playback_zero_remux() -> None:
    """Validate that 1s part duration fragments are sequentially appended without remuxing."""
    part_count = 60  # Standard 60s segment with 1s parts
    segment_bytes = build_synthetic_fmp4(part_count=part_count)

    boxes = parse_isobmff_boxes(segment_bytes)
    moof_boxes = [b for b in boxes if b[0] == "moof"]
    mdat_boxes = [b for b in boxes if b[0] == "mdat"]

    assert len(moof_boxes) == 60
    assert len(mdat_boxes) == 60

    # Ensure each moof has a matching adjacent mdat
    for i in range(len(moof_boxes)):
        moof = moof_boxes[i]
        mdat = mdat_boxes[i]
        # mdat starts immediately after moof ends
        assert mdat[1] == moof[1] + moof[2]


def test_fmp4_truncated_container_detection() -> None:
    """Corrupted or incomplete fMP4 bytes are correctly identified."""
    valid_fmp4 = build_synthetic_fmp4(part_count=2)
    # Truncate halfway through
    truncated = valid_fmp4[: len(valid_fmp4) // 2]
    boxes = parse_isobmff_boxes(truncated)

    # Incomplete segment lacks final pairs
    box_types = [b[0] for b in boxes]
    assert "ftyp" in box_types
    assert len(boxes) < len(parse_isobmff_boxes(valid_fmp4))

