# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Writers for captured logic data.

``SrWriter`` produces a sigrok session file (``.sr``): a ZIP archive holding
``version``, ``metadata`` and the ``logic-1-N`` data chunks that libsigrok's
srzip module reads.  ``BinWriter`` writes the plain concatenated samples the
vendor application saves as ``.bin``.

Both writers are incremental (``append`` / ``truncate`` / ``close``) so a long
stream capture never has to be held in memory.  ``SrWriter`` spools the sample
data to a temporary file next to the target and packs it on ``close()``, which
keeps memory flat and still allows the final truncation to the valid sample
count that only ``LA_CMD_SAMPLE_STOP`` reveals.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Protocol

from .protocol import bytes_per_sample

__all__ = [
    "LogicWriter", "SrWriter", "BinWriter", "writer_for_path",
    "build_metadata", "format_samplerate", "SIGROK_VERSION", "CHUNK_SIZE",
]

#: Version string put into the ``metadata`` file; libsigrok only logs it.
SIGROK_VERSION = "0.5.2"
#: Maximum size of one ``logic-1-N`` chunk, as written by sigrok itself.
CHUNK_SIZE = 4 * 1024 * 1024
#: Content of the ``version`` member: session format version 2.
SESSION_FORMAT_VERSION = "2"


def format_samplerate(rate_hz: float) -> str:
    """Format a sample rate the way libsigrok's size-string parser expects."""
    return f"{int(round(rate_hz))} Hz"


def build_metadata(
    channels: int,
    samplerate_hz: float,
    *,
    channel_names: list[str] | None = None,
    capturefile: str = "logic-1",
    sigrok_version: str = SIGROK_VERSION,
) -> str:
    """Build the ``metadata`` INI file of a sigrok session."""
    unitsize = bytes_per_sample(channels)
    names = channel_names or [f"D{i}" for i in range(channels)]
    if len(names) != channels:
        raise ValueError(f"expected {channels} channel names, got {len(names)}")
    lines = [
        "[global]",
        f"sigrok version={sigrok_version}",
        "",
        "[device 1]",
        f"capturefile={capturefile}",
        f"total probes={channels}",
        f"samplerate={format_samplerate(samplerate_hz)}",
        "total analog=0",
    ]
    lines += [f"probe{i + 1}={name}" for i, name in enumerate(names)]
    lines.append(f"unitsize={unitsize}")
    return "\n".join(lines) + "\n"


class LogicWriter(Protocol):
    """Incremental sink for raw logic samples."""

    def append(self, data: bytes) -> None: ...

    def truncate(self, size: int) -> None: ...

    def close(self) -> None: ...


class _BaseWriter:
    unitsize: int
    _bytes_written: int

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def sample_count(self) -> int:
        return self._bytes_written // self.unitsize

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class BinWriter(_BaseWriter):
    """Raw sample dump, byte-compatible with the vendor ``.bin`` export."""

    def __init__(self, path: str | os.PathLike[str], channels: int) -> None:
        self.path = Path(path)
        self.channels = channels
        self.unitsize = bytes_per_sample(channels)
        self._file = open(self.path, "wb")
        self._bytes_written = 0

    def append(self, data: bytes) -> None:
        if not data:
            return
        self._file.write(data)
        self._bytes_written += len(data)

    def truncate(self, size: int) -> None:
        if size >= self._bytes_written:
            return
        self._file.flush()
        self._file.truncate(size)
        self._file.seek(size)
        self._bytes_written = size

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()


class SrWriter(_BaseWriter):
    """sigrok session file writer (ZIP + ``version`` + ``metadata`` + chunks)."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        channels: int,
        samplerate_hz: float,
        *,
        channel_names: list[str] | None = None,
        chunk_size: int = CHUNK_SIZE,
        capturefile: str = "logic-1",
        sigrok_version: str = SIGROK_VERSION,
    ) -> None:
        self.path = Path(path)
        self.channels = channels
        self.samplerate_hz = samplerate_hz
        self.unitsize = bytes_per_sample(channels)
        self.capturefile = capturefile
        self.sigrok_version = sigrok_version
        self.channel_names = channel_names
        self.chunk_size = max(self.unitsize, chunk_size - chunk_size % self.unitsize)
        self._bytes_written = 0
        self._closed = False
        directory = self.path.parent if str(self.path.parent) else Path(".")
        directory.mkdir(parents=True, exist_ok=True)
        fd, spool = tempfile.mkstemp(dir=directory, prefix=self.path.name + ".", suffix=".part")
        self._spool_path = Path(spool)
        self._spool = os.fdopen(fd, "w+b")

    def append(self, data: bytes) -> None:
        if not data:
            return
        self._spool.write(data)
        self._bytes_written += len(data)

    def truncate(self, size: int) -> None:
        if size >= self._bytes_written:
            return
        self._spool.flush()
        self._spool.truncate(size)
        self._spool.seek(size)
        self._bytes_written = size

    def close(self) -> None:
        """Pack the spooled samples into the ``.sr`` archive."""
        if self._closed:
            return
        self._closed = True
        try:
            usable = self._bytes_written - self._bytes_written % self.unitsize
            self._spool.flush()
            self._spool.seek(0)
            metadata = build_metadata(
                self.channels,
                self.samplerate_hz,
                channel_names=self.channel_names,
                capturefile=self.capturefile,
                sigrok_version=self.sigrok_version,
            )
            with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("version", SESSION_FORMAT_VERSION)
                archive.writestr("metadata", metadata)
                index = 1
                remaining = usable
                while remaining > 0:
                    todo = min(self.chunk_size, remaining)
                    with archive.open(f"{self.capturefile}-{index}", "w") as member:
                        written = 0
                        while written < todo:
                            block = self._spool.read(min(1 << 20, todo - written))
                            if not block:
                                break
                            member.write(block)
                            written += len(block)
                    remaining -= todo
                    index += 1
        finally:
            self._spool.close()
            self._spool_path.unlink(missing_ok=True)


def writer_for_path(
    path: str | os.PathLike[str], channels: int, samplerate_hz: float
) -> LogicWriter:
    """Pick a writer from the file extension (``.sr`` or ``.bin``)."""
    suffix = Path(path).suffix.lower()
    if suffix == ".sr":
        return SrWriter(path, channels, samplerate_hz)
    if suffix == ".bin":
        return BinWriter(path, channels)
    raise ValueError(f"unsupported output format '{suffix}', use .sr or .bin")
