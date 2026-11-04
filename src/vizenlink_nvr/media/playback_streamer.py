"""HTTP Byte-Range streaming response for video segment playback (PLAY-03, PLAY-04)."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse


class RangeFileResponse(StreamingResponse):
    """Streaming response supporting standard HTTP 206 Partial Content byte ranges."""

    CHUNK_SIZE = 64 * 1024  # 64 KB chunks

    def __init__(
        self,
        file_path: Path,
        range_header: str | None = None,
        media_type: str = "video/mp4",
    ) -> None:
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video segment file not found on disk",
            )

        file_size = file_path.stat().st_size
        self.file_path = file_path
        self.file_size = file_size

        if not range_header:
            # Full file response (200 OK)
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            }
            super().__init__(
                content=self._stream_full_file(),
                status_code=status.HTTP_200_OK,
                headers=headers,
                media_type=media_type,
            )
            return

        # Parse Range header: 'bytes=start-end' or 'bytes=start-' or 'bytes=-suffix'
        range_str = range_header.strip()
        if not range_str.startswith("bytes="):
            raise HTTPException(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail="Malformed Range header",
            )

        range_val = range_str[len("bytes=") :]
        parts = range_val.split("-")
        if len(parts) != 2:
            raise HTTPException(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail="Malformed Range header format",
            )

        start_str, end_str = parts[0].strip(), parts[1].strip()

        try:
            if start_str and end_str:
                start = int(start_str)
                end = int(end_str)
            elif start_str:
                start = int(start_str)
                end = file_size - 1
            elif end_str:
                # Suffix range: -N means last N bytes
                suffix_len = int(end_str)
                start = max(0, file_size - suffix_len)
                end = file_size - 1
            else:
                raise ValueError("Empty range")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail="Invalid Range values",
            ) from exc

        # Validate range boundary
        if start < 0 or start >= file_size or end < start:
            raise HTTPException(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}"},
                detail="Range outside file bounds",
            )

        # Clamp end to file_size - 1
        end = min(end, file_size - 1)
        content_length = (end - start) + 1

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
        }

        super().__init__(
            content=self._stream_file_range(start, content_length),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers,
            media_type=media_type,
        )

    def _stream_full_file(self) -> Generator[bytes, None, None]:
        with open(self.file_path, "rb") as f:
            while True:
                chunk = f.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    def _stream_file_range(self, start: int, length: int) -> Generator[bytes, None, None]:
        with open(self.file_path, "rb") as f:
            f.seek(start, os.SEEK_SET)
            bytes_left = length
            while bytes_left > 0:
                to_read = min(self.CHUNK_SIZE, bytes_left)
                chunk = f.read(to_read)
                if not chunk:
                    break
                bytes_left -= len(chunk)
                yield chunk
