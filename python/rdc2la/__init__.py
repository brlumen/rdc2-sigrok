# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""rdc2la - host library and CLI for the ChipDip RDC2-0064 logic analyzer.

The protocol is documented in ``docs/protocol.md`` of the OpenLA repository.

Typical use::

    from rdc2la import Device

    with Device.open() as device:
        result = device.capture_buffer(100_000, 8, 10_000)
        print(result.sample_count, result.rate)
"""

from .device import (
    CaptureResult,
    Device,
    DeviceError,
    StreamCapture,
    StreamSummary,
    StuckFirmwareError,
    stream_to_writer,
)
from .protocol import SamplingMode, Trigger
from .srfile import BinWriter, SrWriter, writer_for_path
from .transport import FakeTransport, LoggingTransport, SerialTransport

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "CaptureResult",
    "Device",
    "DeviceError",
    "StuckFirmwareError",
    "StreamCapture",
    "StreamSummary",
    "stream_to_writer",
    "SamplingMode",
    "Trigger",
    "SrWriter",
    "BinWriter",
    "writer_for_path",
    "SerialTransport",
    "FakeTransport",
    "LoggingTransport",
]
