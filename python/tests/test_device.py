# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""End-to-end capture flows against the emulated firmware (FakeTransport)."""

from __future__ import annotations

import struct

import pytest

from rdc2la import protocol as pr
from rdc2la.device import Device, DeviceError, StuckFirmwareError, stream_to_writer
from rdc2la.protocol import SamplingMode, Trigger
from rdc2la.transport import FakeTransport, pattern_sample


class ListWriter:
    """Minimal writer used to check the truncation logic."""

    def __init__(self, channels: int) -> None:
        self.unitsize = pr.bytes_per_sample(channels)
        self.data = bytearray()
        self.closed = False

    def append(self, data: bytes) -> None:
        self.data += data

    def truncate(self, size: int) -> None:
        del self.data[size:]

    def close(self) -> None:
        self.closed = True


def open_device(**kwargs) -> tuple[Device, FakeTransport]:
    fake = FakeTransport(**kwargs)
    device = Device.open(transport=fake)
    return device, fake


def commands(fake: FakeTransport) -> list[tuple[int, int]]:
    return [(packet[0], packet[1]) for packet in fake.written]


# --------------------------------------------------------------------------
# open sequence (spec 7.3)
# --------------------------------------------------------------------------


def test_open_sequence_stops_then_identifies():
    device, fake = open_device()
    assert commands(fake) == [
        (pr.Module.LA, pr.LaCmd.SAMPLE_STOP),
        (pr.Module.SYSTEM, pr.SysCmd.GET_ID),
    ]
    assert device.device_id is not None
    assert device.device_id.controller_id == 5
    assert device.device_id.firmware_str == "0.2"
    assert device.device_id.hardware == 1


def test_open_rejects_a_foreign_controller():
    with pytest.raises(DeviceError, match="controller id"):
        Device.open(transport=FakeTransport(controller_id=7))


def test_open_detects_a_stuck_firmware():
    fake = FakeTransport()
    fake.hung = True  # firmware spins in the main loop, answers nothing
    with pytest.raises(StuckFirmwareError, match="replug"):
        Device.open(transport=fake)


def test_open_discards_a_stale_stream_packet():
    fake = FakeTransport()
    fake.rx += b"\x5a" * pr.STREAM_PACKET_SIZE  # leftover from a previous run
    device = Device.open(transport=fake)
    assert device.device_id is not None


# --------------------------------------------------------------------------
# buffer capture (spec 7.1)
# --------------------------------------------------------------------------


def parse_config(packet: bytes) -> dict:
    return {
        "mode": packet[pr.OFF_LA_MODE],
        "channels": packet[pr.OFF_LA_CHANNELS],
        "samples": struct.unpack_from("<I", packet, pr.OFF_LA_SAMPLE_COUNT)[0],
        "psc": struct.unpack_from("<H", packet, pr.OFF_LA_TIM_PSC)[0],
        "arr1": struct.unpack_from("<H", packet, pr.OFF_LA_TIM_ARR)[0],
        "streams": packet[pr.OFF_LA_DMA_STREAMS],
    }


@pytest.mark.parametrize("channels", [8, 16, 32])
def test_buffer_capture_returns_ordered_samples(channels):
    device, fake = open_device(status_polls=3)
    progress: list[tuple[int, int]] = []
    result = device.capture_buffer(
        100_000, channels, 1_000,
        progress=lambda done, total: progress.append((done, total)),
        poll_interval=0,
    )
    assert result.sample_count == 1_000
    assert result.rate == 100_000
    assert result.channels == channels
    unit = pr.bytes_per_sample(channels)
    assert len(result.data) == 1_000 * unit
    for i in (0, 1, 2, 499, 999):
        value = int.from_bytes(result.data[i * unit:(i + 1) * unit], "little")
        assert value == pattern_sample(i, channels)
    assert progress and progress[-1] == (1_000, 1_000)
    assert commands(fake)[2:] == [
        (pr.Module.LA, pr.LaCmd.CONFIG),
        (pr.Module.SYSTEM, pr.SysCmd.GET_STATUS),
        (pr.Module.SYSTEM, pr.SysCmd.GET_STATUS),
        (pr.Module.SYSTEM, pr.SysCmd.GET_STATUS),
        (pr.Module.LA, pr.LaCmd.GET_SAMPLES),
    ]


def test_buffer_capture_config_packet():
    device, fake = open_device()
    device.capture_buffer(100_000, 8, 10_000, poll_interval=0)
    config = parse_config(fake.written[2])
    assert config == {
        "mode": SamplingMode.BUFFER,
        "channels": 8,
        "samples": 10_000,
        "psc": 1079,   # 216 MHz / 1080 / 2 = 100 kHz
        "arr1": 2,
        "streams": 1,
    }


def test_buffer_capture_uses_four_dma_streams_for_large_counts():
    device, fake = open_device()
    result = device.capture_buffer(1_000_000, 8, 240_000, poll_interval=0)
    config = parse_config(fake.written[2])
    assert config["streams"] == 4
    assert config["samples"] == 240_000
    assert result.n_streams == 4
    unit = 1
    for i in (0, 1, 3, 4, 239_999):
        value = int.from_bytes(result.data[i * unit:(i + 1) * unit], "little")
        assert value == pattern_sample(i, 8)


def test_buffer_capture_normalises_the_sample_count():
    device, fake = open_device()
    result = device.capture_buffer(1_000_000, 8, 100_001, poll_interval=0)
    # 100001 needs two DMA streams, which the firmware rounds up to four
    assert result.n_streams == 4
    assert result.sample_count == 100_000
    assert parse_config(fake.written[2])["samples"] == 100_000


def test_buffer_capture_with_triggers():
    device, fake = open_device()
    device.capture_buffer(
        100_000, 8, 1_000,
        triggers={3: Trigger.RISING, 0: Trigger.FALLING},
        edge_trigger=Trigger.ANY,
        poll_interval=0,
    )
    packet = fake.written[2]
    assert packet[pr.OFF_LA_TRIG_ACTIVE] == 1
    assert packet[pr.OFF_LA_TRIGGERS + 3] == Trigger.RISING
    assert packet[pr.OFF_LA_TRIGGERS + 0] == Trigger.FALLING
    assert packet[pr.OFF_LA_EDGE_TRIGGER] == Trigger.ANY


def test_buffer_capture_cancellation_stops_the_device():
    device, fake = open_device(status_polls=1000)

    def progress(done: int, total: int) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        device.capture_buffer(100_000, 8, 1_000, progress=progress, poll_interval=0)
    assert commands(fake)[-1] == (pr.Module.LA, pr.LaCmd.SAMPLE_STOP)


def test_buffer_capture_timeout_stops_the_device():
    device, fake = open_device(status_polls=10 ** 6)
    with pytest.raises(TimeoutError):
        device.capture_buffer(100_000, 8, 1_000, timeout=0.0, poll_interval=0)
    assert commands(fake)[-1] == (pr.Module.LA, pr.LaCmd.SAMPLE_STOP)


def test_buffer_capture_rejects_vendor_limit_violations():
    device, _ = open_device()
    with pytest.raises(ValueError, match="limited to"):
        device.capture_buffer(100_000, 32, 120_000, poll_interval=0)
    device.capture_buffer(100_000, 32, 60_000, unsafe=True, poll_interval=0)


# --------------------------------------------------------------------------
# stream capture (spec 7.2)
# --------------------------------------------------------------------------


def test_stream_capture_yields_decoded_packets():
    device, fake = open_device()
    capture = device.capture_stream(100_000, 8, samples=3 * pr.STREAM_PACKET_SIZE)
    chunks = list(capture)
    assert len(chunks) == 3
    assert all(len(chunk) == pr.STREAM_PACKET_SIZE for chunk in chunks)
    joined = b"".join(chunks)
    for i in (0, 1, 16_383, 16_384, 49_151):
        assert joined[i] == pattern_sample(i, 8)
    assert commands(fake)[2:] == [
        (pr.Module.LA, pr.LaCmd.CONFIG),
        (pr.Module.LA, pr.LaCmd.GET_SAMPLES),
        (pr.Module.LA, pr.LaCmd.GET_SAMPLES),
        (pr.Module.LA, pr.LaCmd.GET_SAMPLES),
        (pr.Module.LA, pr.LaCmd.SAMPLE_STOP),
    ]
    # GET_STATUS must never be sent while streaming (spec 7.2)
    assert (pr.Module.SYSTEM, pr.SysCmd.GET_STATUS) not in commands(fake)[2:]
    assert capture.summary.packets_read == 3
    assert capture.summary.valid_packets == 3
    assert not capture.summary.overflow
    assert not fake.hung


def test_stream_capture_config_packet():
    device, fake = open_device()
    list(device.capture_stream(1_000_000, 16, samples=8_192))
    config = parse_config(fake.written[2])
    assert config["mode"] == SamplingMode.STREAM
    assert config["channels"] == 16
    assert config["streams"] == 1
    assert config["psc"] == 107  # 216 MHz / 108 / 2 = 1 MHz
    assert config["arr1"] == 2


def test_stream_capture_32_channels_is_deinterleaved():
    device, _ = open_device()
    capture = device.capture_stream(1_000_000, 32, samples=4_096)
    chunk = next(iter(capture))
    capture.close()
    for i in (0, 1, 4_095):
        value = int.from_bytes(chunk[i * 4:(i + 1) * 4], "little")
        assert value == pattern_sample(i, 32)


def test_stream_capture_duration_is_converted_to_samples():
    device, _ = open_device()
    capture = device.capture_stream(100_000, 8, duration=2.0)
    assert capture.sample_limit == 200_000
    assert capture.packet_limit == 13  # ceil(200000 / 16384)
    capture.close()


def test_stream_timeout_is_derived_from_the_rate():
    device, _ = open_device()
    slow = device.capture_stream(10_000, 8, samples=16_384)
    # one packet takes 1.6384 s at 10 kHz, so the timeout must be well above it
    assert slow.packet_timeout > 2 * pr.stream_packet_time(10_000, 8)
    fast = device.capture_stream(1_000_000, 8, samples=16_384)
    assert fast.packet_timeout >= 2.0  # never below the minimum
    slow.close()
    fast.close()


def test_stream_to_writer_truncates_to_the_sample_limit():
    device, _ = open_device()
    writer = ListWriter(8)
    capture = device.capture_stream(100_000, 8, samples=20_000)
    summary = stream_to_writer(capture, writer)
    assert summary.packets_read == 2
    assert len(writer.data) == 20_000
    assert summary.written_samples == 20_000
    assert not summary.truncated


def test_stream_to_writer_truncates_to_the_valid_packet_count():
    device, fake = open_device(stream_valid_packets=2)
    writer = ListWriter(8)
    capture = device.capture_stream(100_000, 8, samples=4 * pr.STREAM_PACKET_SIZE)
    summary = stream_to_writer(capture, writer)
    assert summary.packets_read == 4
    assert summary.overflow
    assert summary.valid_packets == 2
    assert summary.truncated
    assert len(writer.data) == 2 * pr.STREAM_PACKET_SIZE
    assert summary.written_samples == 2 * pr.STREAM_PACKET_SIZE
    assert writer.data == b"".join(
        bytes(pattern_sample(i, 8) for i in range(p * 16_384, (p + 1) * 16_384))
        for p in range(2)
    )


def test_stream_cancellation_keeps_the_data_and_stops_the_device():
    device, fake = open_device()
    writer = ListWriter(8)
    capture = device.capture_stream(100_000, 8, samples=10 * pr.STREAM_PACKET_SIZE)
    original_append = writer.append
    state = {"count": 0}

    def append(data: bytes) -> None:
        original_append(data)
        state["count"] += 1
        if state["count"] == 2:
            raise KeyboardInterrupt

    writer.append = append  # type: ignore[method-assign]
    summary = stream_to_writer(capture, writer)
    assert summary.cancelled
    assert summary.packets_read == 2
    assert len(writer.data) == 2 * pr.STREAM_PACKET_SIZE
    assert commands(fake)[-1] == (pr.Module.LA, pr.LaCmd.SAMPLE_STOP)
    assert not device._stream_active


def test_stream_cancel_flag_stops_after_the_current_packet():
    device, fake = open_device()
    capture = device.capture_stream(100_000, 8, samples=10 * pr.STREAM_PACKET_SIZE)
    chunks = []
    for chunk in capture:
        chunks.append(chunk)
        capture.cancel()
    assert len(chunks) == 1
    assert capture.summary.cancelled
    assert commands(fake)[-1] == (pr.Module.LA, pr.LaCmd.SAMPLE_STOP)


def test_stream_timeout_ends_the_capture_cleanly():
    device, fake = open_device(stream_stall_after=1)
    capture = device.capture_stream(1_000_000, 8, samples=10 * pr.STREAM_PACKET_SIZE)
    capture.packet_timeout = 0.01
    capture.first_packet_timeout = 0.01
    chunks = list(capture)
    assert len(chunks) == 1
    assert capture.summary.timed_out
    assert capture.summary.valid_packets == 1
    assert commands(fake)[-1] == (pr.Module.LA, pr.LaCmd.SAMPLE_STOP)


def test_get_status_is_refused_during_a_stream():
    device, _ = open_device()
    capture = device.capture_stream(100_000, 8, samples=10 * pr.STREAM_PACKET_SIZE)
    iterator = iter(capture)
    next(iterator)
    with pytest.raises(DeviceError, match="7.2"):
        device.get_status()
    capture.close()


def test_get_samples_is_never_sent_without_a_running_stream():
    device, fake = open_device()
    list(device.capture_stream(100_000, 8, samples=pr.STREAM_PACKET_SIZE))
    # A GET_SAMPLES outside a running stream would hang the firmware (spec 7.3).
    assert not fake.hung
    assert not device._stream_active


def test_a_second_stream_capture_is_refused_while_one_runs():
    device, _ = open_device()
    capture = device.capture_stream(100_000, 8, samples=10 * pr.STREAM_PACKET_SIZE)
    next(iter(capture))
    with pytest.raises(DeviceError, match="already running"):
        device.capture_stream(100_000, 8, samples=pr.STREAM_PACKET_SIZE)
    with pytest.raises(DeviceError, match="still running"):
        device.capture_buffer(100_000, 8, 1_000, poll_interval=0)
    capture.close()


def test_stream_capture_rejects_vendor_limits():
    device, _ = open_device()
    with pytest.raises(ValueError, match="stream mode"):
        device.capture_stream(24_000_000, 8, samples=16_384)


# --------------------------------------------------------------------------
# stop, PWM and frequency meter
# --------------------------------------------------------------------------


def test_stop_reports_the_stream_state():
    device, fake = open_device()
    report = device.stop()
    assert report.overflow is False
    assert report.valid_packets == 0


def test_pwm_set_and_off():
    device, fake = open_device()
    setup1, setup2 = device.pwm_set(1_000, {"M15": 50})
    packet = fake.pwm_packets[-1]
    assert packet[0] == pr.Module.PWM
    assert packet[pr.OFF_PWM1_MASK] == 0b001
    assert struct.unpack_from("<H", packet, pr.OFF_PWM1_ARR)[0] == 53_999
    assert struct.unpack_from("<H", packet, pr.OFF_PWM1_CCR)[0] == 27_000
    assert packet[pr.OFF_PWM2_MASK] == 0
    assert setup1.actual_freq == pytest.approx(1_000)
    assert not setup2.enabled

    device.pwm_off()
    off = fake.pwm_packets[-1]
    assert off[pr.OFF_PWM1_MASK] == 0 and off[pr.OFF_PWM2_MASK] == 0


def test_pwm_set_uses_the_second_timer_frequency():
    device, fake = open_device()
    setup1, setup2 = device.pwm_set(1_000, {"M15": 50, "M18": 25}, freq2_hz=2_000)
    assert setup1.actual_freq == pytest.approx(1_000)
    assert setup2.actual_freq == pytest.approx(2_000)
    packet = fake.pwm_packets[-1]
    assert packet[pr.OFF_PWM2_MASK] == 0b01
    assert struct.unpack_from("<H", packet, pr.OFF_PWM2_CCR)[0] == pr.pwm_duty_to_ccr(
        25, setup2.arr_reg
    )


def test_pwm_set_rejects_unknown_outputs():
    device, _ = open_device()
    with pytest.raises(ValueError, match="unknown PWM outputs"):
        device.pwm_set(1_000, {"M20": 50})


def test_frequency_meter_roundtrip():
    device, fake = open_device(pwm_input_ticks=(600, 300))
    rng = device.measure_start(0)
    assert fake.pwm_input_psc == 3599
    assert fake.pwm_input_running
    measurement = device.measure_read()
    assert measurement.frequency_hz == pytest.approx(60_000 / 601)
    device.measure_stop()
    assert not fake.pwm_input_running


def test_frequency_meter_range_selection():
    device, fake = open_device()
    device.measure_start("> 4 kHz")
    assert fake.pwm_input_psc == 0
    with pytest.raises(ValueError, match="unknown measurement range"):
        device.measure_start("nonsense")
    with pytest.raises(DeviceError, match="measure_start"):
        device.measure_stop()
        device.measure_read()


def test_close_closes_the_transport():
    device, fake = open_device()
    device.close()
    assert fake.closed
