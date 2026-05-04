"""Library-side subtitle resolution and serving for the compat endpoint.

DO NOT import from bazarr.subtitles.manual, bazarr.subtitles.indexer, or
bazarr/api/subtitles/*. The compat surface is isolated by design (see
bazarr/compat/__init__.py); this module re-implements the small slice of
DB lookup and path-safety logic it needs inline.
"""
from __future__ import annotations

import os
import struct


_CHUNK_SIZE = 64 * 1024  # 64 KB - OpenSubtitles algorithm constant


def _opensubtitles_hash(path: str) -> str:
    """Compute the OpenSubtitles file hash.

    Algorithm: read first 64KB and last 64KB, sum as little-endian uint64
    chunks plus the file size, mod 2^64. Returns 16-char lowercase hex.
    """
    size = os.path.getsize(path)
    h = size & 0xFFFFFFFFFFFFFFFF

    with open(path, "rb") as f:
        head = f.read(min(_CHUNK_SIZE, size))
        for i in range(0, len(head) - 7, 8):
            h = (h + struct.unpack_from("<Q", head, i)[0]) & 0xFFFFFFFFFFFFFFFF
        if size > _CHUNK_SIZE:
            f.seek(max(0, size - _CHUNK_SIZE))
            tail = f.read(_CHUNK_SIZE)
            for i in range(0, len(tail) - 7, 8):
                h = (h + struct.unpack_from("<Q", tail, i)[0]) & 0xFFFFFFFFFFFFFFFF

    return f"{h:016x}"
