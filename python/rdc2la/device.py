# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""High level access to the RDC2-0064.

The :class:`Device` class owns a transport and implements the command
sequences of ``docs/protocol.md`` section 7, including the quirks that must be
designed around (strict request/response, no ``GET_STATUS`` during a stream
capture, no ``GET_SAMPLES`` without a running stream).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping, Sequence

from . import protocol as pr
from .protocol import SamplingMode, Trigger
from .transport import (
    LoggingTransport,
    SerialTransport,
    Transport,
    UsbTransport,
    find_usb_devices,
    is_usb_port,
    usb_selector,
)

__all__ = [
    "Device", "DeviceError", "StuckFirmwareError", "CaptureResult",
    "StreamCapture", "StreamSummary", "stream_to_writer", "NO_DEVICE_MESSAGE",
]

log = logging.getLogger(__name__)

#: Timeout for the small 512-byte replies.
REPLY_TIMEOUT = 2.0
#: Timeout for the 240 640-byte buffer transfer.
BUFFER_READ_TIMEOUT = 15.0
#: Status polling interval during a buffer capture (spec 7.1).
STATUS_POLL_INTERVAL = 0.1
#: How long to wait for leftovers during the open sequence (spec 7.3).
OPEN_DRAIN_TIMEOUT = 2.0
#: Extra time added to the theoretical stream packet time.
STREAM_TIMEOUT_MARGIN = 2.0
#: Timeout used while a trigger is armed and nothing has been captured yet.
ARMED_TIMEOUT = 86_400.0
#: Shown when neither transport sees a device.
NO_DEVICE_MESSAGE = (
    f"no RDC2-0064 (USB {pr.USB_VID:04x}:{pr.USB_PID:04x}) found on a serial port "
    "or via libusb; on Windows install the vendor libusb driver or bind usbser"
)


class DeviceError(Exception):
    """Something went wrong while talking to the device."""


class StuckFirmwareError(DeviceError):
    """The firmware does not answer any more; only a replug recovers it."""


@dataclass
class CaptureResult:
    """Result of a buffer capture: contiguous samples plus metadata."""

    data: bytes
    channels: int
    sample_count: int
    rate: float
    requested_rate: float
    mode: SamplingMode = SamplingMode.BUFFER
    n_streams: int = 1

    @property
    def unitsize(self) -> int:
        return pr.bytes_per_sample(self.channels)

    @property
    def duration(self) -> float:
        return self.sample_count / self.rate if self.rate else 0.0


@dataclass
class StreamSummary:
    """What a stream capture ended up doing."""

    channels: int
    rate: float
    packets_read: int = 0
    samples_read: int = 0
    valid_packets: int = 0
    valid_samples: int = 0
    overflow: bool = False
    cancelled: bool = False
    timed_out: bool = False
    written_samples: int = 0
    truncated: bool = False

    @property
    def unitsize(self) -> int:
        return pr.bytes_per_sample(self.channels)


class Device:
    """A single RDC2-0064 attached to a serial or libusb transport."""

    def __init__(self, transport: Transport, *, port: str | None = None) -> None:
        self._transport = transport
        self.port = port
        self._lock = threading.RLock()
        self.device_id: pr.DeviceId | None = None
        self._stream_active = False
        self._closed = False
        self._measure_range: pr.PwmInputRange | None = None

    # -- discovery / lifetime ----------------------------------------------

    @staticmethod
    def find_ports() -> list[str]:
        """Serial ports that look like an RDC2-0064 (VID 0483, PID A210)."""
        from serial.tools import list_ports

        devices = [
            port.device
            for port in list_ports.comports()
            if port.vid == pr.USB_VID and port.pid == pr.USB_PID
        ]
        # macOS exposes both /dev/cu.* and /dev/tty.*; the callout device is the
        # one to use, so drop a tty.* entry when its cu.* twin is present.
        callouts = {name for name in devices if "/cu." in name}
        filtered = [
            name
            for name in devices
            if "/cu." in name or name.replace("/tty.", "/cu.") not in callouts
        ]
        return sorted(filtered, key=lambda name: ("/cu." not in name, name))

    @staticmethod
    def find_usb() -> list[str]:
        """Devices reachable through libusb, as ``usb:<bus>.<address>``.

        Only devices no kernel CDC-ACM driver owns are listed; those are
        served by :meth:`find_ports`.
        """
        return [usb_selector(device) for device in find_usb_devices()]

    @classmethod
    def open(
        cls,
        port: str | None = None,
        *,
        transport: Transport | None = None,
        log_packets: bool = False,
    ) -> "Device":
        """Open a device and run the recommended start-up sequence (spec 7.3).

        ``port`` is a serial port name, ``usb`` (first libusb device) or
        ``usb:<bus>.<address>``.  Without it, serial ports are tried first
        and libusb devices after them.
        """
        if transport is None:
            if port is None:
                candidates = cls.find_ports() + cls.find_usb()
                if not candidates:
                    raise DeviceError(NO_DEVICE_MESSAGE)
                port = candidates[0]
                if len(candidates) > 1:
                    log.info("several devices found, using %s", port)
            if is_usb_port(port):
                transport = cls._open_usb(port)
                port = transport.port
            else:
                transport = SerialTransport(port)
            if log_packets:
                transport = LoggingTransport(transport)
        device = cls(transport, port=port)
        device._handshake()
        return device

    @staticmethod
    def _open_usb(port: str) -> UsbTransport:
        """Open the libusb device a ``usb[:bus.address]`` selector names."""
        devices = find_usb_devices(port)
        if not devices:
            raise DeviceError(
                f"no RDC2-0064 reachable through libusb at {port!r}; "
                "is pyusb installed and a libusb/WinUSB driver bound?"
            )
        if len(devices) > 1:
            log.info("several USB devices found, using %s", usb_selector(devices[0]))
        return UsbTransport(devices[0])

    def _handshake(self) -> None:
        """SAMPLE_STOP, discard leftovers, GET_ID, verify the controller id."""
        with self._lock:
            self._transport.write_packet(pr.build_sample_stop())
            leftovers = self._transport.drain(OPEN_DRAIN_TIMEOUT)
            if not leftovers:
                raise StuckFirmwareError(
                    "the device did not answer SAMPLE_STOP within "
                    f"{OPEN_DRAIN_TIMEOUT:g} s. Firmware v0.2 hangs when "
                    "GET_SAMPLES is sent without a running stream capture "
                    "(spec 7.3) - unplug and replug the device."
                )
            log.debug("discarded %d bytes left over from a previous session", len(leftovers))
            self._stream_active = False
            device_id = self.get_id()
            if device_id.controller_id != pr.CONTROLLER_ID:
                raise DeviceError(
                    f"unexpected controller id {device_id.controller_id}, "
                    f"expected {pr.CONTROLLER_ID} (RDC2-0064)"
                )
            self.device_id = device_id

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._transport.close()

    def __enter__(self) -> "Device":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- primitives ---------------------------------------------------------

    def _request(self, packet: bytes, size: int, timeout: float) -> bytes:
        with self._lock:
            self._transport.write_packet(packet)
            return self._transport.read_exact(size, timeout)

    def get_id(self) -> pr.DeviceId:
        """``SYS_CMD_GET_ID`` (spec 4.1)."""
        return pr.parse_id_reply(
            self._request(pr.build_get_id(), pr.REPLY_SIZE, REPLY_TIMEOUT)
        )

    def get_status(self) -> pr.DeviceStatus:
        """``SYS_CMD_GET_STATUS`` (spec 4.2). Never call during a stream capture."""
        if self._stream_active:
            raise DeviceError(
                "GET_STATUS must not be sent while a stream capture runs (spec 7.2)"
            )
        return pr.parse_status_reply(
            self._request(pr.build_get_status(), pr.REPLY_SIZE, REPLY_TIMEOUT)
        )

    def stop(self) -> pr.StopReport:
        """``LA_CMD_SAMPLE_STOP`` (spec 5.5): stop sampling, read the report."""
        with self._lock:
            report = pr.parse_stop_reply(
                self._request(pr.build_sample_stop(), pr.REPLY_SIZE, REPLY_TIMEOUT)
            )
            self._stream_active = False
            return report

    # -- buffer capture (spec 7.1) -----------------------------------------

    def capture_buffer(
        self,
        rate: float,
        channels: int,
        samples: int,
        *,
        triggers: Mapping[int, int] | Sequence[int] | None = None,
        edge_trigger: int = Trigger.NONE,
        progress: Callable[[int, int], None] | None = None,
        unsafe: bool = False,
        timeout: float | None = None,
        read_timeout: float = BUFFER_READ_TIMEOUT,
        poll_interval: float = STATUS_POLL_INTERVAL,
    ) -> CaptureResult:
        """Run one buffer capture and return the de-interleaved samples."""
        if self._stream_active:
            raise DeviceError("a stream capture is still running; stop it first")
        clock = pr.resolve_samplerate(
            rate, SamplingMode.BUFFER, channels, samples, unsafe=unsafe
        )
        count = pr.normalise_sample_count(samples, channels, clock.n_streams)
        config = pr.build_la_config(
            mode=SamplingMode.BUFFER,
            channels=channels,
            sample_count=count,
            psc_reg=clock.psc_reg,
            arr1=clock.arr1,
            n_streams=clock.n_streams,
            triggers=triggers,
            edge_trigger=edge_trigger,
        )
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            self._transport.write_packet(config)
            try:
                while True:
                    status = self.get_status()
                    if status.sampling_complete:
                        break
                    if progress is not None:
                        done = max(0, count - status.ndtr * clock.n_streams)
                        progress(min(done, count), count)
                    if deadline is not None and time.monotonic() > deadline:
                        self.stop()
                        raise TimeoutError(
                            f"buffer capture did not finish within {timeout:g} s "
                            "(waiting for a trigger?)"
                        )
                    time.sleep(poll_interval)
            except KeyboardInterrupt:
                self.stop()
                raise
            if progress is not None:
                progress(count, count)
            raw = self._request(pr.build_get_samples(), pr.BUFFER_SIZE, read_timeout)
        data = pr.deinterleave_buffer(raw, count, channels, clock.n_streams)
        return CaptureResult(
            data=data[: count * pr.bytes_per_sample(channels)],
            channels=channels,
            sample_count=count,
            rate=clock.actual_rate,
            requested_rate=float(rate),
            mode=SamplingMode.BUFFER,
            n_streams=clock.n_streams,
        )

    # -- stream capture (spec 7.2) -----------------------------------------

    def capture_stream(
        self,
        rate: float,
        channels: int,
        *,
        samples: int | None = None,
        duration: float | None = None,
        triggers: Mapping[int, int] | Sequence[int] | None = None,
        edge_trigger: int = Trigger.NONE,
        unsafe: bool = False,
        packet_timeout: float | None = None,
    ) -> "StreamCapture":
        """Prepare a stream capture; iterate the result to receive samples."""
        if self._stream_active:
            raise DeviceError("a stream capture is already running")
        if samples is None and duration is not None:
            samples = int(rate * duration)
        clock = pr.resolve_samplerate(
            rate, SamplingMode.STREAM, channels, unsafe=unsafe
        )
        config = pr.build_la_config(
            mode=SamplingMode.STREAM,
            channels=channels,
            sample_count=min(samples or 0, 0xFFFFFFFF),
            psc_reg=clock.psc_reg,
            arr1=clock.arr1,
            n_streams=clock.n_streams,
            triggers=triggers,
            edge_trigger=edge_trigger,
        )
        if packet_timeout is None:
            packet_time = pr.stream_packet_time(clock.actual_rate, channels)
            packet_timeout = max(REPLY_TIMEOUT, 2.0 * packet_time + STREAM_TIMEOUT_MARGIN)
        armed = bool(triggers) or int(edge_trigger) != Trigger.NONE
        return StreamCapture(
            self,
            config=config,
            channels=channels,
            rate=clock.actual_rate,
            requested_rate=float(rate),
            sample_limit=samples,
            packet_timeout=packet_timeout,
            first_packet_timeout=ARMED_TIMEOUT if armed else packet_timeout,
        )

    # -- PWM generator (spec 8) --------------------------------------------

    def pwm_set(
        self,
        freq_hz: float,
        duties: Mapping[str, float],
        freq2_hz: float | None = None,
    ) -> tuple[pr.PwmTimerSetup, pr.PwmTimerSetup]:
        """Configure the PWM outputs; returns the setup of both timers."""
        unknown = set(duties) - set(pr.PWM_CHANNELS)
        if unknown:
            raise ValueError(
                f"unknown PWM outputs {sorted(unknown)}; "
                f"available: {', '.join(pr.PWM_CHANNELS)}"
            )
        split: dict[int, dict[str, float]] = {1: {}, 2: {}}
        for name, duty in duties.items():
            timer, _ = pr.PWM_CHANNELS[name]
            split[timer][name] = duty
        setup1 = pr.plan_pwm_timer(1, freq_hz, split[1])
        setup2 = pr.plan_pwm_timer(2, freq2_hz if freq2_hz is not None else freq_hz, split[2])
        with self._lock:
            self._transport.write_packet(pr.build_pwm_packet(setup1, setup2))
        return setup1, setup2

    def pwm_off(self) -> None:
        """Stop both PWM timers; all outputs go low (spec 8)."""
        with self._lock:
            self._transport.write_packet(pr.build_pwm_off_packet())

    # -- frequency meter (spec 9) ------------------------------------------

    def measure_start(self, rng: pr.PwmInputRange | int | str = 0) -> pr.PwmInputRange:
        """Start the PWM-input frequency meter on the given range."""
        resolved = _resolve_pwm_input_range(rng)
        with self._lock:
            self._transport.write_packet(pr.build_pwm_input_config(resolved.psc_reg))
            self._measure_range = resolved
        return resolved

    def measure_read(self) -> pr.PulseMeasurement:
        """Read one measurement; values are zero until a full period was seen."""
        rng = self._measure_range
        if rng is None:
            raise DeviceError("call measure_start() before measure_read()")
        reply = self._request(pr.build_pwm_input_get_data(), pr.REPLY_SIZE, REPLY_TIMEOUT)
        period, width = pr.parse_pwm_input_reply(reply)
        return pr.pwm_input_measurement(period, width, rng)

    def measure_stop(self) -> None:
        """Stop the frequency meter (spec 9)."""
        with self._lock:
            self._transport.write_packet(pr.build_pwm_input_stop())
            self._measure_range = None


def _resolve_pwm_input_range(rng: pr.PwmInputRange | int | str) -> pr.PwmInputRange:
    if isinstance(rng, pr.PwmInputRange):
        return rng
    if isinstance(rng, int):
        try:
            return pr.PWM_INPUT_RANGES[rng]
        except IndexError:
            raise ValueError(
                f"range index {rng} out of range 0..{len(pr.PWM_INPUT_RANGES) - 1}"
            ) from None
    for candidate in pr.PWM_INPUT_RANGES:
        if candidate.name == rng:
            return candidate
    names = ", ".join(f"{i}={c.name!r}" for i, c in enumerate(pr.PWM_INPUT_RANGES))
    raise ValueError(f"unknown measurement range {rng!r}; available: {names}")


class StreamCapture:
    """An armed stream capture: iterate it to get decoded sample chunks.

    The device is stopped when iteration ends for any reason (target reached,
    ``close()``, ``KeyboardInterrupt``), and :attr:`summary` then holds the
    overflow flag and the valid packet count reported by the firmware.
    """

    def __init__(
        self,
        device: Device,
        *,
        config: bytes,
        channels: int,
        rate: float,
        requested_rate: float,
        sample_limit: int | None,
        packet_timeout: float,
        first_packet_timeout: float,
    ) -> None:
        self._device = device
        self._config = config
        self.channels = channels
        self.rate = rate
        self.requested_rate = requested_rate
        self.sample_limit = sample_limit
        self.packet_timeout = packet_timeout
        self.first_packet_timeout = first_packet_timeout
        self.unitsize = pr.bytes_per_sample(channels)
        self.packet_limit = (
            pr.stream_packets_for_samples(sample_limit, channels)
            if sample_limit
            else None
        )
        self.summary = StreamSummary(channels=channels, rate=rate)
        self._generator: Iterator[bytes] | None = None
        self._cancelled = False

    # -- iteration ----------------------------------------------------------

    def __iter__(self) -> Iterator[bytes]:
        if self._generator is None:
            self._generator = self._run()
        return self._generator

    def __enter__(self) -> "StreamCapture":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def cancel(self) -> None:
        """Ask the capture to stop after the packet currently being read."""
        self._cancelled = True

    def close(self) -> None:
        """Stop the capture and make sure the device is idle again."""
        if self._generator is not None:
            self._generator.close()
            self._generator = None

    def _run(self) -> Iterator[bytes]:
        device = self._device
        transport = device._transport
        clean = True
        packets = 0
        with device._lock:
            transport.write_packet(self._config)
            device._stream_active = True
            try:
                while self.packet_limit is None or packets < self.packet_limit:
                    if self._cancelled:
                        self.summary.cancelled = True
                        break
                    transport.write_packet(pr.build_get_samples())
                    timeout = self.first_packet_timeout if packets == 0 else self.packet_timeout
                    clean = False
                    try:
                        raw = transport.read_exact(pr.STREAM_PACKET_SIZE, timeout)
                    except TimeoutError:
                        self.summary.timed_out = True
                        log.warning(
                            "no stream packet within %.1f s; stopping the capture", timeout
                        )
                        break
                    clean = True
                    packets += 1
                    self.summary.packets_read = packets
                    self.summary.samples_read = (
                        packets * pr.STREAM_PACKET_SIZE // self.unitsize
                    )
                    yield pr.decode_stream_packet(raw, self.channels)
            except GeneratorExit:
                # Closing the generator after the target was reached is a normal
                # end; anything earlier means the caller stopped the capture.
                if self.packet_limit is None or packets < self.packet_limit:
                    self.summary.cancelled = True
                raise
            except KeyboardInterrupt:
                self.summary.cancelled = True
                raise
            finally:
                self._finish(clean)

    def _finish(self, clean: bool) -> None:
        """Send SAMPLE_STOP and collect the final report (spec 7.2)."""
        device = self._device
        transport = device._transport
        reply = b""
        try:
            transport.write_packet(pr.build_sample_stop())
            if clean:
                try:
                    reply = transport.read_exact(pr.REPLY_SIZE, REPLY_TIMEOUT)
                except TimeoutError:
                    log.warning("no SAMPLE_STOP reply within %.1f s", REPLY_TIMEOUT)
            else:
                # An unfinished stream packet may precede the stop reply (spec 7.3).
                pending = transport.drain(OPEN_DRAIN_TIMEOUT)
                if len(pending) >= pr.REPLY_SIZE:
                    reply = pending[-pr.REPLY_SIZE:]
            if reply:
                report = pr.parse_stop_reply(reply)
                self.summary.overflow = report.overflow
                self.summary.valid_packets = report.valid_packets
                self.summary.valid_samples = min(
                    self.summary.samples_read,
                    report.valid_samples(self.channels),
                )
            else:
                log.warning("no SAMPLE_STOP report received")
                self.summary.valid_packets = self.summary.packets_read
                self.summary.valid_samples = self.summary.samples_read
        finally:
            device._stream_active = False


def stream_to_writer(
    capture: StreamCapture,
    writer,
    *,
    progress: Callable[[int, int | None], None] | None = None,
) -> StreamSummary:
    """Run a stream capture into a writer and truncate to the valid samples.

    Ctrl+C stops the device cleanly and keeps everything captured so far; the
    summary then has ``cancelled`` set.
    """
    unitsize = capture.unitsize
    limit_bytes = capture.sample_limit * unitsize if capture.sample_limit else None
    written = 0
    try:
        with capture:
            for chunk in capture:
                if limit_bytes is not None and written + len(chunk) > limit_bytes:
                    chunk = chunk[: limit_bytes - written]
                writer.append(chunk)
                written += len(chunk)
                if progress is not None:
                    progress(written // unitsize, capture.sample_limit)
                if limit_bytes is not None and written >= limit_bytes:
                    break
    except KeyboardInterrupt:
        capture.summary.cancelled = True
    summary = capture.summary
    valid_bytes = written
    if summary.valid_packets or summary.overflow:
        valid_bytes = min(written, summary.valid_packets * pr.STREAM_PACKET_SIZE)
    if valid_bytes < written:
        writer.truncate(valid_bytes)
        summary.truncated = True
    summary.written_samples = valid_bytes // unitsize
    return summary
