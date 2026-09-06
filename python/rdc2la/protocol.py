# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Pure protocol layer of the ChipDip RDC2-0064 logic analyzer.

Everything here is I/O free: constants, packet builders, reply parsers,
sample-clock maths and sample-buffer rearrangement.  The byte layouts follow
``docs/protocol.md``; section numbers in the docstrings refer to that file.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from math import ceil
from typing import Iterable, Mapping, NamedTuple, Sequence

__all__ = [
    "USB_VID", "USB_PID", "CONTROLLER_ID",
    "CMD_PACKET_SIZE", "REPLY_SIZE", "BUFFER_SIZE", "STREAM_PACKET_SIZE",
    "SAMPLE_CLOCK_HZ", "PWM_CLOCK_HZ", "PWM_INPUT_CLOCK_HZ",
    "Module", "SysCmd", "LaCmd", "PwmInputCmd", "SamplingMode", "Trigger",
    "DeviceId", "DeviceStatus", "StopReport", "SampleClock", "PulseMeasurement",
    "PwmTimerSetup", "PwmInputRange",
    "build_packet", "build_get_id", "build_get_status", "build_get_samples",
    "build_sample_stop", "build_la_config", "build_pwm_packet",
    "build_pwm_off_packet", "build_pwm_input_config", "build_pwm_input_get_data",
    "build_pwm_input_stop",
    "parse_id_reply", "parse_status_reply", "parse_stop_reply",
    "parse_pwm_input_reply",
    "resolve_samplerate", "dma_stream_count", "check_capture_limits",
    "normalise_sample_count", "buffer_capacity", "bytes_per_sample",
    "deinterleave_buffer", "decode_stream_packet", "encode_triggers",
    "solve_pwm_frequency", "pwm_duty_to_ccr", "plan_pwm_timer",
    "pwm_input_measurement", "stream_packet_time", "stream_packets_for_samples",
]

# --------------------------------------------------------------------------
# USB identity and transport sizes (spec 1, 2)
# --------------------------------------------------------------------------

USB_VID = 0x0483
USB_PID = 0xA210
USB_PRODUCT = "RDC2-0064 in HS Mode"

CMD_PACKET_SIZE = 64
REPLY_SIZE = 512
BUFFER_SIZE = 240_640
STREAM_PACKET_SIZE = 16_384
STREAM_RING_SIZE = 229_376
STREAM_RING_PACKETS = STREAM_RING_SIZE // STREAM_PACKET_SIZE

CONTROLLER_ID = 5

# --------------------------------------------------------------------------
# Clocks and register widths
# --------------------------------------------------------------------------

SAMPLE_CLOCK_HZ = 216_000_000
PWM_CLOCK_HZ = 108_000_000
PWM_INPUT_CLOCK_HZ = 216_000_000

REG16_MAX = 0xFFFF
DIVIDER_MAX = REG16_MAX + 1  # register value + 1

CHANNEL_COUNTS = (8, 16, 32)


class Module(IntEnum):
    SYSTEM = 0
    LA = 1
    PWM = 2
    PWM_INPUT = 3


class SysCmd(IntEnum):
    GET_ID = 4
    GET_STATUS = 5


class LaCmd(IntEnum):
    CONFIG = 0
    GET_SAMPLES = 1
    SAMPLE_STOP = 2


class PwmInputCmd(IntEnum):
    CONFIG = 0
    GET_DATA = 1
    STOP = 2


class SamplingMode(IntEnum):
    BUFFER = 0
    STREAM = 1


class Trigger(IntEnum):
    """Trigger types, per channel and for the EDGE input (spec 5.4)."""

    NONE = 0
    LOW = 1
    HIGH = 2
    RISING = 3
    FALLING = 4
    ANY = 5


EDGE_TRIGGERS = (Trigger.RISING, Trigger.FALLING, Trigger.ANY)
#: Channels above this index support level triggers only (spec 5.4).
MAX_EDGE_TRIGGER_CHANNEL = 15

STATUS_TRIGGER_AWAIT = 1 << 0
STATUS_SAMPLING_CMP = 1 << 1

# --------------------------------------------------------------------------
# Packet offsets (spec 3, 5.1, 8, 9)
# --------------------------------------------------------------------------

OFF_MODULE = 0
OFF_CMD = 1
OFF_SUBCMD = 2
OFF_DATA = 3

OFF_LA_MODE = 3
OFF_LA_CHANNELS = 4
OFF_LA_SAMPLE_COUNT = 5
OFF_LA_CLOCK_SOURCE = 9
OFF_LA_PLL_RECONFIG = 10
OFF_LA_PLL_M = 11
OFF_LA_PLL_N = 12
OFF_LA_PLL_P = 14
OFF_LA_TIM_PSC = 15
OFF_LA_TIM_ARR = 17
OFF_LA_DMA_STREAMS = 19
OFF_LA_TRIG_ACTIVE = 20
OFF_LA_TRIG_TIM_PSC = 21
OFF_LA_TRIG_TIM_ARR = 23
OFF_LA_TRIGGERS = 25
OFF_LA_EDGE_TRIGGER = 57

OFF_PWM1_MASK = 3
OFF_PWM1_PSC = 4
OFF_PWM1_ARR = 6
OFF_PWM1_CCR = 8
OFF_PWM2_MASK = 14
OFF_PWM2_PSC = 15
OFF_PWM2_ARR = 17
OFF_PWM2_CCR = 19

OFF_PWM_INPUT_PSC = 3

# Reply offsets
OFF_ID_CONTROLLER = 3
OFF_ID_FIRMWARE = 4
OFF_ID_MEMORY = 8
OFF_ID_HARDWARE = 10
OFF_STATUS_BITS = 3
OFF_STATUS_NDTR = 4
OFF_STOP_OVERFLOW = 0
OFF_STOP_PACKETS = 1
OFF_PWM_INPUT_PERIOD = 0
OFF_PWM_INPUT_WIDTH = 2

# --------------------------------------------------------------------------
# Vendor tables (spec 5.2, 5.3)
# --------------------------------------------------------------------------

#: rate in Hz -> (timer divider = PSC register + 1, ARR1)
VENDOR_PRESETS: dict[int, tuple[int, int]] = {
    10_000: (10800, 2),
    20_000: (5400, 2),
    50_000: (2160, 2),
    100_000: (1080, 2),
    200_000: (540, 2),
    500_000: (216, 2),
    1_000_000: (108, 2),
    2_000_000: (54, 2),
    4_000_000: (27, 2),
    8_000_000: (9, 3),
    12_000_000: (9, 2),
    18_000_000: (6, 2),
    24_000_000: (3, 3),
    36_000_000: (3, 2),
    54_000_000: (2, 2),
    72_000_000: (1, 3),
    108_000_000: (2, 1),
}

VENDOR_BUFFER_SAMPLE_COUNTS = (
    1_000, 2_000, 5_000, 10_000, 20_000, 30_000, 60_000, 120_000, 160_000, 240_000,
)

MAX_SAMPLES_PER_DMA_STREAM = 65_000
DMA_STREAM_COUNT_MAX = 5

#: Buffer mode limits, spec 5.3.
BUFFER_MAX_RATE = {8: 72_000_000, 16: 72_000_000, 32: 24_000_000}
BUFFER_MAX_SAMPLES = {8: 240_000, 16: 120_000, 32: 60_000}
#: 8 channels may run at 108 MHz, but only for short captures.
BUFFER_MAX_RATE_8CH_BOOST = 108_000_000
BUFFER_MAX_SAMPLES_BOOST = 30_000

#: Stream mode limits, spec 5.3.
STREAM_MAX_RATE = {8: 18_000_000, 16: 8_000_000, 32: 4_000_000}

# PWM generator (spec 8)
PWM_MIN_FREQ = 0.03
PWM_MAX_FREQ = 27_000_000
PWM_TIMER_CHANNELS: dict[int, tuple[str, ...]] = {1: ("M15", "M16", "M17"), 2: ("M18", "M19")}
PWM_CHANNELS: dict[str, tuple[int, int]] = {
    name: (timer, index)
    for timer, names in PWM_TIMER_CHANNELS.items()
    for index, name in enumerate(names)
}


class ProtocolError(Exception):
    """Malformed or unexpected data from the device."""


# --------------------------------------------------------------------------
# Reply containers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceId:
    """Decoded ``SYS_CMD_GET_ID`` reply (spec 4.1)."""

    controller_id: int
    firmware: tuple[int, int, int, int]
    memory_size: int
    hardware: int

    @property
    def firmware_str(self) -> str:
        return f"{self.firmware[0]}.{self.firmware[1]}"

    @property
    def is_rdc2_0064(self) -> bool:
        return self.controller_id == CONTROLLER_ID


@dataclass(frozen=True)
class DeviceStatus:
    """Decoded ``SYS_CMD_GET_STATUS`` reply (spec 4.2)."""

    bits: int
    ndtr: int

    @property
    def sampling_complete(self) -> bool:
        return bool(self.bits & STATUS_SAMPLING_CMP)

    @property
    def trigger_await(self) -> bool:
        return bool(self.bits & STATUS_TRIGGER_AWAIT)


@dataclass(frozen=True)
class StopReport:
    """Decoded ``LA_CMD_SAMPLE_STOP`` reply (spec 5.5)."""

    overflow: bool
    valid_packets: int

    def valid_samples(self, channels: int) -> int:
        return self.valid_packets * STREAM_PACKET_SIZE // bytes_per_sample(channels)


class SampleClock(NamedTuple):
    """Sample-clock solution (spec 5.2)."""

    psc_reg: int
    arr1: int
    n_streams: int
    actual_rate: float

    @property
    def arr_reg(self) -> int:
        """Value the firmware programs into TIMx_ARR."""
        return self.arr1 * self.n_streams - 1


# --------------------------------------------------------------------------
# Low level packet helpers
# --------------------------------------------------------------------------


def _u16(value: int, name: str) -> bytes:
    if not 0 <= value <= REG16_MAX:
        raise ValueError(f"{name} must fit in 16 bits, got {value}")
    return struct.pack("<H", value)


def build_packet(module: int, cmd: int = 0, subcmd: int = 0, payload: bytes = b"") -> bytes:
    """Build a zero-padded 64-byte host to device command packet (spec 2, 3)."""
    if len(payload) > CMD_PACKET_SIZE - OFF_DATA:
        raise ValueError("payload does not fit into a 64-byte packet")
    packet = bytearray(CMD_PACKET_SIZE)
    packet[OFF_MODULE] = module
    packet[OFF_CMD] = cmd
    packet[OFF_SUBCMD] = subcmd
    packet[OFF_DATA:OFF_DATA + len(payload)] = payload
    return bytes(packet)


def build_get_id() -> bytes:
    return build_packet(Module.SYSTEM, SysCmd.GET_ID)


def build_get_status() -> bytes:
    return build_packet(Module.SYSTEM, SysCmd.GET_STATUS)


def build_get_samples() -> bytes:
    return build_packet(Module.LA, LaCmd.GET_SAMPLES)


def build_sample_stop() -> bytes:
    return build_packet(Module.LA, LaCmd.SAMPLE_STOP)


def bytes_per_sample(channels: int) -> int:
    """Host-side sample size: 1, 2 or 4 bytes (spec 6)."""
    _check_channels(channels)
    return channels // 8


def buffer_transfer_size(channels: int) -> int:
    """Bytes written per DMA transfer in buffer mode (spec 6.1)."""
    _check_channels(channels)
    return 1 if channels == 8 else 2


def buffer_capacity(channels: int) -> int:
    """Number of samples the on-device buffer can hold."""
    return BUFFER_SIZE // bytes_per_sample(channels)


def _check_channels(channels: int) -> None:
    if channels not in CHANNEL_COUNTS:
        raise ValueError(
            f"channel count must be one of {CHANNEL_COUNTS}, got {channels} "
            "(24 channels are broken in firmware v0.2, see spec 6.4)"
        )


# --------------------------------------------------------------------------
# Triggers (spec 5.4)
# --------------------------------------------------------------------------


def encode_triggers(
    triggers: Mapping[int, int] | Sequence[int] | None,
    channels: int = 32,
) -> bytes:
    """Encode the 32-byte per-channel trigger block.

    ``triggers`` is either a mapping ``{channel: Trigger}`` or a sequence of up
    to 32 trigger values.  Edge triggers are rejected on channels 16..31 and
    triggers outside the active channel range are rejected as well.
    """
    table = bytearray(32)
    if triggers is None:
        return bytes(table)

    items: Iterable[tuple[int, int]]
    if isinstance(triggers, Mapping):
        items = triggers.items()
    else:
        items = enumerate(triggers)

    for channel, value in items:
        if not 0 <= channel < 32:
            raise ValueError(f"trigger channel {channel} out of range 0..31")
        if channel >= channels:
            needed = 8 if channel < 8 else 16 if channel < 16 else 32
            raise ValueError(
                f"trigger on channel D{channel} needs at least "
                f"{needed} channels, capture uses {channels}"
            )
        value = int(value)
        if value not in tuple(Trigger):
            raise ValueError(f"invalid trigger type {value} for channel D{channel}")
        if value in EDGE_TRIGGERS and channel > MAX_EDGE_TRIGGER_CHANNEL:
            raise ValueError(
                f"channel D{channel} supports level triggers only; "
                "edge triggers exist on channels D0..D15 (spec 5.4)"
            )
        table[channel] = value
    return bytes(table)


def _check_edge_trigger(value: int) -> int:
    value = int(value)
    if value not in tuple(Trigger):
        raise ValueError(f"invalid EDGE-input trigger type {value}")
    return value


# --------------------------------------------------------------------------
# Sample clock (spec 5.2, 5.3)
# --------------------------------------------------------------------------


def dma_stream_count(
    rate_hz: float,
    mode: SamplingMode = SamplingMode.BUFFER,
    sample_count: int | None = None,
) -> int:
    """Number of DMA streams the firmware must use (spec 5.2)."""
    if SamplingMode(mode) is SamplingMode.STREAM:
        return 1
    if rate_hz <= 36_000_000:
        by_rate = 1
    elif rate_hz <= 72_000_000:
        by_rate = 4
    else:
        by_rate = 5
    by_count = 1
    if sample_count:
        by_count = min(
            ceil(sample_count / MAX_SAMPLES_PER_DMA_STREAM), DMA_STREAM_COUNT_MAX
        )
    n = max(by_rate, by_count)
    return 4 if n in (2, 3) else n


def check_capture_limits(
    rate_hz: float,
    mode: SamplingMode,
    channels: int,
    sample_count: int | None = None,
    *,
    unsafe: bool = False,
) -> None:
    """Enforce the vendor rate/sample limits of spec 5.3.

    ``unsafe=True`` skips these vendor limits only; register-width and buffer
    capacity limits are enforced elsewhere and are never bypassed.
    """
    _check_channels(channels)
    if rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    if unsafe:
        return

    mode = SamplingMode(mode)
    if mode is SamplingMode.STREAM:
        limit = STREAM_MAX_RATE[channels]
        if rate_hz > limit:
            raise ValueError(
                f"stream mode with {channels} channels is limited to "
                f"{limit / 1e6:g} MHz, requested {rate_hz / 1e6:g} MHz "
                "(use --unsafe to override)"
            )
        return

    max_rate = BUFFER_MAX_RATE[channels]
    max_samples = BUFFER_MAX_SAMPLES[channels]
    if channels == 8 and rate_hz > max_rate and rate_hz <= BUFFER_MAX_RATE_8CH_BOOST:
        max_rate = BUFFER_MAX_RATE_8CH_BOOST
        max_samples = BUFFER_MAX_SAMPLES_BOOST
    if rate_hz > max_rate:
        raise ValueError(
            f"buffer mode with {channels} channels is limited to "
            f"{max_rate / 1e6:g} MHz, requested {rate_hz / 1e6:g} MHz "
            "(use --unsafe to override)"
        )
    if sample_count is not None and sample_count > max_samples:
        raise ValueError(
            f"buffer mode with {channels} channels at {rate_hz / 1e6:g} MHz is "
            f"limited to {max_samples} samples, requested {sample_count} "
            "(use --unsafe to override)"
        )


def _solve_timer(rate_hz: float, arr1_max: int) -> tuple[int, int, float]:
    """Generic 216 MHz / divider / ARR1 solver, both registers 16 bit."""
    total = SAMPLE_CLOCK_HZ / rate_hz
    if total < 1:
        raise ValueError(
            f"sample rate {rate_hz:g} Hz is above the {SAMPLE_CLOCK_HZ / 1e6:g} MHz timer clock"
        )
    arr1_min = max(1, ceil(total / DIVIDER_MAX))
    if arr1_min > arr1_max:
        raise ValueError(
            f"sample rate {rate_hz:g} Hz cannot be reached: it needs ARR1 >= {arr1_min}, "
            f"but only {arr1_max} fits into the 16-bit ARR register"
        )
    best: tuple[int, int, float] | None = None
    best_err = float("inf")
    for arr1 in range(arr1_min, arr1_max + 1):
        divider = min(DIVIDER_MAX, max(1, round(total / arr1)))
        actual = SAMPLE_CLOCK_HZ / (divider * arr1)
        err = abs(actual - rate_hz)
        if err < best_err:
            best, best_err = (divider, arr1, actual), err
            if err == 0.0:
                break
    assert best is not None
    return best


def resolve_samplerate(
    rate_hz: float,
    mode: SamplingMode = SamplingMode.BUFFER,
    channels: int = 8,
    sample_count: int | None = None,
    *,
    unsafe: bool = False,
) -> SampleClock:
    """Resolve a requested sample rate into timer registers (spec 5.2).

    Vendor presets are used verbatim where they exist; every other rate goes
    through a generic solver.  Returns ``(psc_reg, arr1, n_streams, actual_rate)``.
    """
    mode = SamplingMode(mode)
    check_capture_limits(rate_hz, mode, channels, sample_count, unsafe=unsafe)
    n_streams = dma_stream_count(rate_hz, mode, sample_count)
    arr1_max = DIVIDER_MAX // n_streams

    preset = None
    if float(rate_hz).is_integer():
        preset = VENDOR_PRESETS.get(int(rate_hz))
    if preset is not None:
        divider, arr1 = preset
    else:
        divider, arr1, _ = _solve_timer(rate_hz, arr1_max)

    if not 1 <= divider <= DIVIDER_MAX:
        raise ValueError(f"timer divider {divider} does not fit into 16 bits")
    if not 1 <= arr1 <= arr1_max:
        raise ValueError(
            f"ARR1 {arr1} with {n_streams} DMA streams does not fit into the "
            "16-bit ARR register"
        )
    actual = SAMPLE_CLOCK_HZ / (divider * arr1)
    return SampleClock(divider - 1, arr1, n_streams, actual)


def normalise_sample_count(sample_count: int, channels: int, n_streams: int) -> int:
    """Round a buffer-mode sample count down to something the device accepts.

    The count must be divisible by the DMA stream count, must fit the on-device
    buffer and must keep the per-stream transfer count inside the 16-bit NDTR
    register.  These are hardware limits and are never bypassed.
    """
    _check_channels(channels)
    if n_streams < 1:
        raise ValueError("DMA stream count must be >= 1")
    if sample_count < n_streams:
        raise ValueError(f"sample count must be at least {n_streams} (one per DMA stream)")
    capacity = buffer_capacity(channels)
    limit = min(capacity, REG16_MAX * n_streams)
    count = min(int(sample_count), limit)
    count -= count % n_streams
    if count < n_streams:
        raise ValueError("sample count too small after normalisation")
    return count


def stream_packet_time(rate_hz: float, channels: int) -> float:
    """Seconds the device needs to fill one 16 KiB stream packet (spec 5.5)."""
    return STREAM_PACKET_SIZE / (rate_hz * bytes_per_sample(channels))


def stream_packets_for_samples(sample_count: int, channels: int) -> int:
    """Number of stream packets needed to cover ``sample_count`` samples."""
    per_packet = STREAM_PACKET_SIZE // bytes_per_sample(channels)
    return ceil(sample_count / per_packet)


# --------------------------------------------------------------------------
# LA_CMD_CONFIG (spec 5.1)
# --------------------------------------------------------------------------


def build_la_config(
    *,
    mode: SamplingMode,
    channels: int,
    sample_count: int,
    psc_reg: int,
    arr1: int,
    n_streams: int,
    triggers: Mapping[int, int] | Sequence[int] | None = None,
    edge_trigger: int = Trigger.NONE,
    clock_source: int = 0,
) -> bytes:
    """Build the 64-byte ``LA_CMD_CONFIG`` packet (spec 5.1)."""
    mode = SamplingMode(mode)
    _check_channels(channels)
    if n_streams not in (1, 4, 5):
        raise ValueError(f"DMA stream count must be 1, 4 or 5, got {n_streams}")
    if mode is SamplingMode.STREAM and n_streams != 1:
        raise ValueError("stream mode always uses a single DMA stream (spec 5.2)")
    if not 0 <= sample_count <= 0xFFFFFFFF:
        raise ValueError("sample count does not fit into 32 bits")
    if mode is SamplingMode.BUFFER:
        if sample_count % n_streams:
            raise ValueError(
                f"sample count {sample_count} is not divisible by the DMA stream "
                f"count {n_streams}"
            )
        if sample_count // n_streams > REG16_MAX:
            raise ValueError("per-stream transfer count does not fit into 16-bit NDTR")
    if arr1 < 1:
        raise ValueError("ARR1 must be >= 1")
    if arr1 * n_streams - 1 > REG16_MAX:
        raise ValueError("ARR1 * streams - 1 does not fit into the 16-bit ARR register")

    trigger_table = encode_triggers(triggers, channels)
    edge = _check_edge_trigger(edge_trigger)

    packet = bytearray(CMD_PACKET_SIZE)
    packet[OFF_MODULE] = Module.LA
    packet[OFF_CMD] = LaCmd.CONFIG
    packet[OFF_LA_MODE] = int(mode)
    packet[OFF_LA_CHANNELS] = channels
    packet[OFF_LA_SAMPLE_COUNT:OFF_LA_SAMPLE_COUNT + 4] = struct.pack("<I", sample_count)
    packet[OFF_LA_CLOCK_SOURCE] = clock_source
    packet[OFF_LA_TIM_PSC:OFF_LA_TIM_PSC + 2] = _u16(psc_reg, "TIM_PSC")
    packet[OFF_LA_TIM_ARR:OFF_LA_TIM_ARR + 2] = _u16(arr1, "ARR1")
    packet[OFF_LA_DMA_STREAMS] = n_streams
    packet[OFF_LA_TRIG_ACTIVE] = 1 if any(trigger_table) else 0
    packet[OFF_LA_TRIGGERS:OFF_LA_TRIGGERS + 32] = trigger_table
    packet[OFF_LA_EDGE_TRIGGER] = edge
    return bytes(packet)


# --------------------------------------------------------------------------
# Reply parsers (spec 4, 5)
# --------------------------------------------------------------------------


def _check_reply(data: bytes, size: int, what: str) -> None:
    if len(data) < size:
        raise ProtocolError(f"{what} reply too short: {len(data)} of {size} bytes")


def parse_id_reply(data: bytes) -> DeviceId:
    _check_reply(data, OFF_ID_HARDWARE + 1, "GET_ID")
    firmware = tuple(data[OFF_ID_FIRMWARE:OFF_ID_FIRMWARE + 4])
    return DeviceId(
        controller_id=data[OFF_ID_CONTROLLER],
        firmware=firmware,  # type: ignore[arg-type]
        memory_size=struct.unpack_from("<H", data, OFF_ID_MEMORY)[0],
        hardware=data[OFF_ID_HARDWARE],
    )


def parse_status_reply(data: bytes) -> DeviceStatus:
    _check_reply(data, OFF_STATUS_NDTR + 2, "GET_STATUS")
    return DeviceStatus(
        bits=data[OFF_STATUS_BITS],
        ndtr=struct.unpack_from("<H", data, OFF_STATUS_NDTR)[0],
    )


def parse_stop_reply(data: bytes) -> StopReport:
    _check_reply(data, OFF_STOP_PACKETS + 4, "SAMPLE_STOP")
    return StopReport(
        overflow=bool(data[OFF_STOP_OVERFLOW]),
        valid_packets=struct.unpack_from("<I", data, OFF_STOP_PACKETS)[0],
    )


# --------------------------------------------------------------------------
# Sample data layout (spec 6)
# --------------------------------------------------------------------------


def deinterleave_buffer(
    raw: bytes, sample_count: int, channels: int, n_streams: int
) -> bytes:
    """Rearrange a raw buffer-mode transfer into contiguous samples (spec 6.1).

    Uses strided slice assignment only, so no per-byte Python loop runs.
    """
    _check_channels(channels)
    if n_streams < 1:
        raise ValueError("DMA stream count must be >= 1")
    if sample_count % n_streams:
        raise ValueError(
            f"sample count {sample_count} is not divisible by the DMA stream count {n_streams}"
        )
    bps = buffer_transfer_size(channels)
    per_part = sample_count // n_streams
    part_size = per_part * bps
    n_parts = n_streams + (1 if channels == 32 else 0)
    if len(raw) < n_parts * part_size:
        raise ValueError(
            f"raw buffer holds {len(raw)} bytes, need {n_parts * part_size}"
        )

    if channels != 32 and n_streams == 1:
        return bytes(raw[: sample_count * bps])

    group = n_streams * bps + (2 if channels == 32 else 0)
    out = bytearray(per_part * group)
    view = memoryview(raw)
    for k in range(n_parts):
        part = bytes(view[k * part_size:(k + 1) * part_size])
        base = k * bps
        if bps == 1:
            out[base::group] = part
        else:
            out[base::group] = part[0::2]
            out[base + 1::group] = part[1::2]
    return bytes(out)


def decode_stream_packet(packet: bytes, channels: int) -> bytes:
    """Convert one 16 KiB stream packet into contiguous samples (spec 6.2)."""
    _check_channels(channels)
    if len(packet) != STREAM_PACKET_SIZE:
        raise ValueError(
            f"stream packet must be {STREAM_PACKET_SIZE} bytes, got {len(packet)}"
        )
    if channels != 32:
        return bytes(packet)
    half = STREAM_PACKET_SIZE // 2
    low = bytes(packet[:half])
    high = bytes(packet[half:])
    out = bytearray(STREAM_PACKET_SIZE)
    out[0::4] = low[0::2]
    out[1::4] = low[1::2]
    out[2::4] = high[0::2]
    out[3::4] = high[1::2]
    return bytes(out)


# --------------------------------------------------------------------------
# PWM generator (spec 8)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PwmTimerSetup:
    """Register set for one PWM timer plus the resulting frequency."""

    psc_reg: int
    arr_reg: int
    ccr: tuple[int, ...]
    mask: int
    actual_freq: float

    @property
    def enabled(self) -> bool:
        return self.mask != 0


def solve_pwm_frequency(freq_hz: float) -> tuple[int, int, float]:
    """Solve the 108 MHz PWM timer for ``freq_hz``.

    Returns ``(psc_reg, arr_reg, actual_freq)``.  ARR is maximised so the duty
    cycle keeps as much resolution as possible.
    """
    if not PWM_MIN_FREQ <= freq_hz <= PWM_MAX_FREQ:
        raise ValueError(
            f"PWM frequency must be between {PWM_MIN_FREQ} Hz and "
            f"{PWM_MAX_FREQ / 1e6:g} MHz, got {freq_hz:g} Hz"
        )
    total = round(PWM_CLOCK_HZ / freq_hz)
    total = max(1, min(total, DIVIDER_MAX * DIVIDER_MAX))
    psc_min = max(1, ceil(total / DIVIDER_MAX))
    # Exact factorisation with the largest possible ARR.
    for psc in range(psc_min, DIVIDER_MAX + 1):
        if total % psc == 0 and total // psc <= DIVIDER_MAX:
            arr = total // psc
            return psc - 1, arr - 1, PWM_CLOCK_HZ / (psc * arr)
    # No exact split: take the closest frequency, preferring a large ARR.
    best = None
    best_err = float("inf")
    for psc in range(psc_min, DIVIDER_MAX + 1):
        arr = min(DIVIDER_MAX, max(1, round(total / psc)))
        actual = PWM_CLOCK_HZ / (psc * arr)
        err = abs(actual - freq_hz)
        if err < best_err:
            best, best_err = (psc - 1, arr - 1, actual), err
    assert best is not None
    return best


def pwm_duty_to_ccr(duty_percent: float, arr_reg: int) -> int:
    """Convert a duty cycle in percent into a CCR register value (spec 8)."""
    if not 0.0 <= duty_percent <= 100.0:
        raise ValueError(f"duty cycle must be 0..100 %, got {duty_percent}")
    ccr = int(duty_percent * (arr_reg + 1) / 100.0)
    return min(ccr, REG16_MAX)


def plan_pwm_timer(timer: int, freq_hz: float, duties: Mapping[str, float]) -> PwmTimerSetup:
    """Build the register set for one PWM timer from per-output duty cycles."""
    if timer not in PWM_TIMER_CHANNELS:
        raise ValueError(f"PWM timer must be 1 or 2, got {timer}")
    names = PWM_TIMER_CHANNELS[timer]
    for name in duties:
        if name not in names:
            raise ValueError(f"output {name} does not belong to PWM timer {timer}")
    if not duties:
        return PwmTimerSetup(0, 0, (0,) * len(names), 0, 0.0)
    psc_reg, arr_reg, actual = solve_pwm_frequency(freq_hz)
    ccr = []
    mask = 0
    for index, name in enumerate(names):
        if name in duties:
            ccr.append(pwm_duty_to_ccr(duties[name], arr_reg))
            mask |= 1 << index
        else:
            ccr.append(0)
    return PwmTimerSetup(psc_reg, arr_reg, tuple(ccr), mask, actual)


def build_pwm_packet(
    timer1: PwmTimerSetup | None = None, timer2: PwmTimerSetup | None = None
) -> bytes:
    """Build the 64-byte PWM packet; a disabled timer stops its outputs (spec 8)."""
    packet = bytearray(CMD_PACKET_SIZE)
    packet[OFF_MODULE] = Module.PWM
    for setup, off_mask, off_psc, off_arr, off_ccr, count in (
        (timer1, OFF_PWM1_MASK, OFF_PWM1_PSC, OFF_PWM1_ARR, OFF_PWM1_CCR, 3),
        (timer2, OFF_PWM2_MASK, OFF_PWM2_PSC, OFF_PWM2_ARR, OFF_PWM2_CCR, 2),
    ):
        if setup is None or not setup.enabled:
            continue
        if len(setup.ccr) != count:
            raise ValueError(f"expected {count} CCR values, got {len(setup.ccr)}")
        packet[off_mask] = setup.mask
        packet[off_psc:off_psc + 2] = _u16(setup.psc_reg, "PWM PSC")
        packet[off_arr:off_arr + 2] = _u16(setup.arr_reg, "PWM ARR")
        for index, value in enumerate(setup.ccr):
            offset = off_ccr + 2 * index
            packet[offset:offset + 2] = _u16(value, "PWM CCR")
    return bytes(packet)


def build_pwm_off_packet() -> bytes:
    """Both enable masks zero: every PWM output goes low (spec 8)."""
    return build_packet(Module.PWM)


# --------------------------------------------------------------------------
# PWM input / frequency meter (spec 9)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PwmInputRange:
    """Capture-timer range as offered by the vendor software."""

    name: str
    divider: int
    delay_ticks: int

    @property
    def psc_reg(self) -> int:
        return self.divider - 1

    @property
    def tick_hz(self) -> float:
        return PWM_INPUT_CLOCK_HZ / self.divider


#: Ranges and detection-delay compensation from Measurements.xaml.cs.
PWM_INPUT_RANGES: tuple[PwmInputRange, ...] = (
    PwmInputRange("1 - 100 Hz", 3600, 1),
    PwmInputRange("100 Hz - 4 kHz", 40, 1),
    PwmInputRange("> 4 kHz", 1, 2),
)


@dataclass(frozen=True)
class PulseMeasurement:
    """One frequency-meter reading."""

    period_ticks: int
    width_ticks: int
    period_s: float
    width_s: float
    frequency_hz: float
    duty_percent: float

    @property
    def valid(self) -> bool:
        return self.period_ticks != 0


def build_pwm_input_config(psc_reg: int) -> bytes:
    return build_packet(
        Module.PWM_INPUT, PwmInputCmd.CONFIG, payload=_u16(psc_reg, "PWM input PSC")
    )


def build_pwm_input_get_data() -> bytes:
    return build_packet(Module.PWM_INPUT, PwmInputCmd.GET_DATA)


def build_pwm_input_stop() -> bytes:
    return build_packet(Module.PWM_INPUT, PwmInputCmd.STOP)


def parse_pwm_input_reply(data: bytes) -> tuple[int, int]:
    """Return ``(period_ticks, high_time_ticks)`` from a GET_DATA reply."""
    _check_reply(data, OFF_PWM_INPUT_WIDTH + 2, "PWM_INPUT GET_DATA")
    period = struct.unpack_from("<H", data, OFF_PWM_INPUT_PERIOD)[0]
    width = struct.unpack_from("<H", data, OFF_PWM_INPUT_WIDTH)[0]
    return period, width


def pwm_input_measurement(
    period_ticks: int, width_ticks: int, rng: PwmInputRange
) -> PulseMeasurement:
    """Convert raw capture-timer ticks into time, frequency and duty cycle."""
    if period_ticks and width_ticks:
        period_ticks += rng.delay_ticks
        width_ticks += rng.delay_ticks
    tick_hz = rng.tick_hz
    period_s = period_ticks / tick_hz
    width_s = width_ticks / tick_hz
    frequency = 1.0 / period_s if period_s else 0.0
    duty = 100.0 * width_ticks / period_ticks if period_ticks else 0.0
    return PulseMeasurement(period_ticks, width_ticks, period_s, width_s, frequency, duty)
