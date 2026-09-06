# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Byte transports for the RDC2-0064.

``SerialTransport`` talks to the real CDC-ACM device, ``FakeTransport``
emulates the firmware state machine closely enough for tests, and
``LoggingTransport`` wraps either of them to hex-dump the wire traffic.
"""

from __future__ import annotations

import logging
import struct
import time
from typing import Protocol

from . import protocol as pr

__all__ = ["Transport", "SerialTransport", "FakeTransport", "LoggingTransport"]

log = logging.getLogger(__name__)
wire_log = logging.getLogger("rdc2la.wire")

#: Serial read granularity while waiting for a long transfer.
_POLL_INTERVAL = 0.05


class Transport(Protocol):
    """Minimal byte transport used by :class:`rdc2la.device.Device`."""

    def write_packet(self, data: bytes) -> None: ...

    def read_exact(self, size: int, timeout: float) -> bytes: ...

    def drain(self, timeout: float) -> bytes: ...

    def close(self) -> None: ...


class SerialTransport:
    """pyserial based transport for ``/dev/cu.usbmodem*`` / ``/dev/ttyACM*``."""

    def __init__(self, port: str, *, write_timeout: float = 2.0) -> None:
        import serial  # imported lazily so the pure protocol layer stays dependency free

        self.port = port
        kwargs = dict(
            baudrate=115200,  # line coding is ignored by the firmware
            timeout=_POLL_INTERVAL,
            write_timeout=write_timeout,
            rtscts=False,
            dsrdtr=False,
            xonxoff=False,
        )
        try:
            self._serial = serial.Serial(port, exclusive=True, **kwargs)
        except (TypeError, ValueError):  # exclusive= is POSIX only
            self._serial = serial.Serial(port, **kwargs)
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        self._timeout = _POLL_INTERVAL

    def _set_timeout(self, value: float) -> None:
        # Assigning Serial.timeout reconfigures the tty, so only do it when the
        # value actually changes.
        if value != self._timeout:
            self._serial.timeout = value
            self._timeout = value

    def write_packet(self, data: bytes) -> None:
        """Write one command packet in a single ``write()`` (spec 2.1)."""
        if len(data) != pr.CMD_PACKET_SIZE:
            raise ValueError(
                f"command packets are {pr.CMD_PACKET_SIZE} bytes, got {len(data)}"
            )
        written = self._serial.write(data)
        if written != len(data):
            raise OSError(f"short write: {written} of {len(data)} bytes")
        self._serial.flush()

    def read_exact(self, size: int, timeout: float) -> bytes:
        """Read exactly ``size`` bytes or raise :class:`TimeoutError`."""
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while len(buf) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"timed out after {timeout:g} s with {len(buf)} of {size} bytes"
                )
            self._set_timeout(min(remaining, _POLL_INTERVAL * 4))
            chunk = self._serial.read(size - len(buf))
            if chunk:
                buf += chunk
        return bytes(buf)

    def drain(self, timeout: float, quiet: float = 0.3) -> bytes:
        """Read and return whatever arrives within ``timeout`` seconds.

        Returns early once the device has been quiet for ``quiet`` seconds
        after sending something.
        """
        buf = bytearray()
        deadline = time.monotonic() + timeout
        last = time.monotonic()
        while time.monotonic() < deadline:
            self._set_timeout(_POLL_INTERVAL)
            chunk = self._serial.read(pr.REPLY_SIZE)
            if chunk:
                buf += chunk
                last = time.monotonic()
            elif buf and time.monotonic() - last >= quiet:
                break
        return bytes(buf)

    def close(self) -> None:
        try:
            self._serial.close()
        except Exception:  # pragma: no cover - closing must never raise
            log.debug("closing %s failed", self.port, exc_info=True)


class LoggingTransport:
    """Wrapper that hex-dumps every packet through ``rdc2la.wire`` (DEBUG)."""

    def __init__(self, inner: Transport, max_bytes: int = 64) -> None:
        self._inner = inner
        self.max_bytes = max_bytes
        self.history: list[tuple[str, bytes]] = []

    @staticmethod
    def _hex(data: bytes, limit: int) -> str:
        head = data[:limit].hex(" ")
        return head if len(data) <= limit else f"{head} ... ({len(data)} bytes)"

    def write_packet(self, data: bytes) -> None:
        self.history.append(("tx", bytes(data)))
        wire_log.debug("tx %s", self._hex(data, self.max_bytes))
        self._inner.write_packet(data)

    def read_exact(self, size: int, timeout: float) -> bytes:
        data = self._inner.read_exact(size, timeout)
        self.history.append(("rx", bytes(data)))
        wire_log.debug("rx %s", self._hex(data, self.max_bytes))
        return data

    def drain(self, timeout: float) -> bytes:
        data = self._inner.drain(timeout)
        self.history.append(("rx", bytes(data)))
        wire_log.debug("drain %s", self._hex(data, self.max_bytes))
        return data

    def close(self) -> None:
        self._inner.close()


# --------------------------------------------------------------------------
# Fake device
# --------------------------------------------------------------------------


def pattern_sample(index: int, channels: int) -> int:
    """Deterministic synthetic sample value used by :class:`FakeTransport`."""
    low = (index * 7 + 1) & 0xFFFF
    if channels == 8:
        return low & 0xFF
    if channels == 16:
        return low
    return low | (((index * 13 + 5) & 0xFFFF) << 16)


class FakeConfig:
    """Parsed ``LA_CMD_CONFIG`` packet, as the firmware would see it."""

    __slots__ = (
        "mode", "channels", "sample_count", "clock_source", "psc_reg", "arr1",
        "n_streams", "triggers_active", "triggers", "edge_trigger", "raw",
    )

    def __init__(self, packet: bytes) -> None:
        self.raw = bytes(packet)
        self.mode = pr.SamplingMode(packet[pr.OFF_LA_MODE])
        self.channels = packet[pr.OFF_LA_CHANNELS]
        self.sample_count = struct.unpack_from("<I", packet, pr.OFF_LA_SAMPLE_COUNT)[0]
        self.clock_source = packet[pr.OFF_LA_CLOCK_SOURCE]
        self.psc_reg = struct.unpack_from("<H", packet, pr.OFF_LA_TIM_PSC)[0]
        self.arr1 = struct.unpack_from("<H", packet, pr.OFF_LA_TIM_ARR)[0]
        self.n_streams = packet[pr.OFF_LA_DMA_STREAMS]
        self.triggers_active = bool(packet[pr.OFF_LA_TRIG_ACTIVE])
        self.triggers = bytes(packet[pr.OFF_LA_TRIGGERS:pr.OFF_LA_TRIGGERS + 32])
        self.edge_trigger = packet[pr.OFF_LA_EDGE_TRIGGER]


class FakeTransport:
    """In-memory emulation of the RDC2-0064 firmware state machine.

    Only what the host code needs is emulated, but the byte layouts are exactly
    those of ``docs/protocol.md`` so the tests double as a spec check.
    """

    def __init__(
        self,
        *,
        controller_id: int = pr.CONTROLLER_ID,
        firmware: tuple[int, int, int, int] = (0, 2, 0, 0),
        hardware: int = 1,
        memory_size: int = 0,
        status_polls: int = 2,
        stream_valid_packets: int | None = None,
        overflow: bool = False,
        stream_stall_after: int | None = None,
        pwm_input_ticks: tuple[int, int] = (0, 0),
        fill: int = 0xA5,
    ) -> None:
        self.controller_id = controller_id
        self.firmware = firmware
        self.hardware = hardware
        self.memory_size = memory_size
        self.status_polls = max(1, status_polls)
        self.stream_valid_packets = stream_valid_packets
        self.overflow = overflow
        self.stream_stall_after = stream_stall_after
        self.pwm_input_ticks = pwm_input_ticks
        self.fill = fill

        self.rx = bytearray()
        self.written: list[bytes] = []
        self.config: FakeConfig | None = None
        self.pwm_packets: list[bytes] = []
        self.pwm_input_psc: int | None = None
        self.pwm_input_running = False
        self.stream_active = False
        self.stream_packets_sent = 0
        self.stop_reports = 0
        self.hung = False
        self.closed = False
        self._polls = 0

    # -- transport interface ------------------------------------------------

    def write_packet(self, data: bytes) -> None:
        if len(data) != pr.CMD_PACKET_SIZE:
            raise ValueError(
                f"command packets are {pr.CMD_PACKET_SIZE} bytes, got {len(data)}"
            )
        self.written.append(bytes(data))
        if self.hung:
            return
        module = data[pr.OFF_MODULE]
        cmd = data[pr.OFF_CMD]
        if module == pr.Module.SYSTEM:
            self._handle_system(cmd)
        elif module == pr.Module.LA:
            self._handle_la(cmd, data)
        elif module == pr.Module.PWM:
            self.pwm_packets.append(bytes(data))
        elif module == pr.Module.PWM_INPUT:
            self._handle_pwm_input(cmd, data)
        else:
            raise AssertionError(f"unknown module {module}")

    def read_exact(self, size: int, timeout: float) -> bytes:
        if len(self.rx) < size:
            raise TimeoutError(
                f"timed out after {timeout:g} s with {len(self.rx)} of {size} bytes"
            )
        data = bytes(self.rx[:size])
        del self.rx[:size]
        return data

    def drain(self, timeout: float) -> bytes:
        data = bytes(self.rx)
        self.rx.clear()
        return data

    def close(self) -> None:
        self.closed = True

    # -- command handlers ---------------------------------------------------

    def _reply(self, payload: bytes) -> None:
        reply = bytearray(pr.REPLY_SIZE)
        reply[: len(payload)] = payload
        self.rx += reply

    def _handle_system(self, cmd: int) -> None:
        if cmd == pr.SysCmd.GET_ID:
            payload = bytearray(pr.OFF_ID_HARDWARE + 1)
            payload[pr.OFF_MODULE] = pr.Module.SYSTEM
            payload[pr.OFF_CMD] = pr.SysCmd.GET_ID
            payload[pr.OFF_ID_CONTROLLER] = self.controller_id
            payload[pr.OFF_ID_FIRMWARE:pr.OFF_ID_FIRMWARE + 4] = bytes(self.firmware)
            payload[pr.OFF_ID_MEMORY:pr.OFF_ID_MEMORY + 2] = struct.pack(
                "<H", self.memory_size
            )
            payload[pr.OFF_ID_HARDWARE] = self.hardware
            self._reply(bytes(payload))
        elif cmd == pr.SysCmd.GET_STATUS:
            self._reply(self._status_payload())
        else:
            raise AssertionError(f"unknown SYSTEM command {cmd}")

    def _status_payload(self) -> bytes:
        payload = bytearray(pr.OFF_STATUS_NDTR + 2)
        payload[pr.OFF_MODULE] = pr.Module.SYSTEM
        payload[pr.OFF_CMD] = pr.SysCmd.GET_STATUS
        cfg = self.config
        if cfg is None or cfg.mode is not pr.SamplingMode.BUFFER:
            return bytes(payload)
        self._polls += 1
        per_stream = cfg.sample_count // max(1, cfg.n_streams)
        if self._polls >= self.status_polls:
            payload[pr.OFF_STATUS_BITS] = pr.STATUS_SAMPLING_CMP
            remaining = 0
        else:
            remaining = per_stream * (self.status_polls - self._polls) // self.status_polls
        payload[pr.OFF_STATUS_NDTR:pr.OFF_STATUS_NDTR + 2] = struct.pack("<H", remaining)
        return bytes(payload)

    def _handle_la(self, cmd: int, data: bytes) -> None:
        if cmd == pr.LaCmd.CONFIG:
            self.config = FakeConfig(data)
            self._polls = 0
            self.stream_packets_sent = 0
            self.stream_active = self.config.mode is pr.SamplingMode.STREAM
        elif cmd == pr.LaCmd.GET_SAMPLES:
            cfg = self.config
            if cfg is not None and cfg.mode is pr.SamplingMode.STREAM:
                if not self.stream_active:
                    # Firmware bug: spins in the main loop forever (spec 7.3).
                    self.hung = True
                    return
                if (
                    self.stream_stall_after is not None
                    and self.stream_packets_sent >= self.stream_stall_after
                ):
                    return  # nothing ready: the host must time out
                self.rx += self._stream_packet()
                self.stream_packets_sent += 1
            else:
                self.rx += self._sample_buffer()
        elif cmd == pr.LaCmd.SAMPLE_STOP:
            self.stream_active = False
            self.stop_reports += 1
            valid = self.stream_packets_sent
            overflow = self.overflow
            if self.stream_valid_packets is not None:
                valid = min(valid, self.stream_valid_packets)
                overflow = overflow or valid < self.stream_packets_sent
            payload = bytearray(pr.OFF_STOP_PACKETS + 4)
            payload[pr.OFF_STOP_OVERFLOW] = 1 if overflow else 0
            payload[pr.OFF_STOP_PACKETS:pr.OFF_STOP_PACKETS + 4] = struct.pack("<I", valid)
            self._reply(bytes(payload))
        else:
            raise AssertionError(f"unknown LA command {cmd}")

    def _handle_pwm_input(self, cmd: int, data: bytes) -> None:
        if cmd == pr.PwmInputCmd.CONFIG:
            self.pwm_input_psc = struct.unpack_from("<H", data, pr.OFF_PWM_INPUT_PSC)[0]
            self.pwm_input_running = True
        elif cmd == pr.PwmInputCmd.GET_DATA:
            period, width = self.pwm_input_ticks
            payload = struct.pack("<HH", period, width)
            self._reply(payload)
        elif cmd == pr.PwmInputCmd.STOP:
            self.pwm_input_running = False
        else:
            raise AssertionError(f"unknown PWM_INPUT command {cmd}")

    # -- synthetic sample data ---------------------------------------------

    def _sample_buffer(self) -> bytes:
        """Full 240 640-byte buffer with the parts laid out per spec 6.1."""
        cfg = self.config
        assert cfg is not None
        channels = cfg.channels
        count = cfg.sample_count
        n = max(1, cfg.n_streams)
        bps = pr.buffer_transfer_size(channels)
        per_part = count // n
        part_size = per_part * bps
        buf = bytearray([self.fill]) * pr.BUFFER_SIZE
        for k in range(n):
            part = b"".join(
                (pattern_sample(i * n + k, channels) & (0xFF if bps == 1 else 0xFFFF))
                .to_bytes(bps, "little")
                for i in range(per_part)
            )
            buf[k * part_size:(k + 1) * part_size] = part
        if channels == 32:
            high = b"".join(
                ((pattern_sample(i * n, channels) >> 16) & 0xFFFF).to_bytes(2, "little")
                for i in range(per_part)
            )
            buf[n * part_size:(n + 1) * part_size] = high
        return bytes(buf)

    def _stream_packet(self) -> bytes:
        """One 16 KiB stream packet in device layout (spec 6.2)."""
        cfg = self.config
        assert cfg is not None
        channels = cfg.channels
        unit = pr.bytes_per_sample(channels)
        per_packet = pr.STREAM_PACKET_SIZE // unit
        start = self.stream_packets_sent * per_packet
        values = [pattern_sample(start + i, channels) for i in range(per_packet)]
        if channels == 8:
            return bytes(v & 0xFF for v in values)
        if channels == 16:
            return b"".join((v & 0xFFFF).to_bytes(2, "little") for v in values)
        low = b"".join((v & 0xFFFF).to_bytes(2, "little") for v in values)
        high = b"".join(((v >> 16) & 0xFFFF).to_bytes(2, "little") for v in values)
        return low + high
