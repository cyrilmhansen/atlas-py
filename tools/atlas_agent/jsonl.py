"""Streaming JSONL primitives with an explicit per-line memory bound."""
from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_JSONL_LINE_BYTES = 1 * 1024 * 1024


def iter_bounded_jsonl(path: Path, max_line_bytes: int = DEFAULT_MAX_JSONL_LINE_BYTES):
    """Yield ``(line_without_newline, oversized)`` without buffering a huge line.

    ``max_line_bytes`` bounds the bytes retained for one complete line.  An
    oversized line is discarded through its newline and yielded as
    ``(b"", True)``; its fragment is never presented as a JSONL record.
    A final unterminated line is yielded normally (or oversized) at EOF.
    """
    if type(max_line_bytes) is not int or max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be a positive integer")
    with Path(path).open("rb") as stream:
        buffer = bytearray()
        oversized = False
        while True:
            chunk = stream.read(8192)
            if not chunk:
                if buffer or oversized:
                    yield bytes(buffer), oversized
                return
            start = 0
            while start < len(chunk):
                newline = chunk.find(b"\n", start)
                end = len(chunk) if newline < 0 else newline
                part = chunk[start:end]
                if not oversized:
                    room = max_line_bytes - len(buffer)
                    if len(part) <= room:
                        buffer.extend(part)
                    else:
                        # Keep at most the configured bound, then discard the
                        # rest of this physical line until its newline.
                        if room > 0:
                            buffer.extend(part[:room])
                        oversized = True
                if newline >= 0:
                    yield bytes(buffer) if not oversized else b"", oversized
                    buffer.clear()
                    oversized = False
                    start = newline + 1
                else:
                    start = end
                    break
