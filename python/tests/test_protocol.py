# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Protocol layer tests: byte layouts, timer maths and sample rearrangement.

The expected values are taken from docs/protocol.md and, where the vendor
software is the reference, from third_party/chipdip/software-v0.2.
"""

from __future__ import annotations

import struct

import pytest

from rdc2la import protocol as pr
from rdc2la.protocol import SamplingMode, Trigger

# Vendor tables copied verbatim from LogicAnalyzer.xaml.cs so that the test is
# an independent cross-check of protocol.VENDOR_PRESETS.
VENDOR_RATES = (
    10_000, 20_000, 50_000, 100_000, 200_000, 500_000,
    1_000_000, 2_000_000, 4_000_000, 8_000_000, 12_000_000, 18_000_000,
    24_000_000, 36_000_000, 54_000_000, 72_000_000, 108_000_000,
)
VENDOR_TIMER_PSC = (
    10800, 5400, 2160, 1080, 540, 216,
    108, 54, 27, 9, 9, 6,
    3, 3, 2, 1, 2,
)
VENDOR_TIMER_ARR1 = (
    2, 2, 2, 2, 2, 2,
    2, 2, 2, 3, 2, 2,
    3, 2, 2, 3, 1,
)


# --------------------------------------------------------------------------
# packet layouts
# --------------------------------------------------------------------------


def test_command_packets_are_64_bytes():
    for packet in (
        pr.build_get_id(),
        pr.build_get_status(),
        pr.build_get_samples(),
        pr.build_sample_stop(),
        pr.build_pwm_off_packet(),
        pr.build_pwm_input_get_data(),
    ):
        assert len(packet) == 64


def test_system_command_headers():
    assert pr.build_get_id()[:3] == bytes([0, 4, 0])
    assert pr.build_get_status()[:3] == bytes([0, 5, 0])
    assert pr.build_get_id()[3:] == bytes(61)


def test_la_command_headers():
    assert pr.build_get_samples()[:3] == bytes([1, 1, 0])
    assert pr.build_sample_stop()[:3] == bytes([1, 2, 0])


def test_la_config_layout_matches_spec_offsets():
    packet = pr.build_la_config(
        mode=SamplingMode.BUFFER,
        channels=16,
        sample_count=120_000,
        psc_reg=1079,
        arr1=2,
        n_streams=4,
        triggers={3: Trigger.RISING, 15: Trigger.LOW, 8: Trigger.HIGH},
        edge_trigger=Trigger.FALLING,
    )
    assert len(packet) == 64
    assert packet[0] == pr.Module.LA
    assert packet[1] == pr.LaCmd.CONFIG
    assert packet[2] == 0
    assert packet[3] == SamplingMode.BUFFER
    assert packet[4] == 16
    assert struct.unpack_from("<I", packet, 5)[0] == 120_000
    assert packet[9] == 0  # internal timer
    assert packet[10:15] == bytes(5)  # PLL fields unused
    assert struct.unpack_from("<H", packet, 15)[0] == 1079
    assert struct.unpack_from("<H", packet, 17)[0] == 2
    assert packet[19] == 4
    assert packet[20] == 1  # channel triggers active
    assert packet[21:25] == bytes(4)  # trigger timer PSC/ARR unused
    assert packet[25 + 3] == Trigger.RISING
    assert packet[25 + 15] == Trigger.LOW
    assert packet[25 + 8] == Trigger.HIGH
    assert sum(packet[25:57]) == Trigger.RISING + Trigger.LOW + Trigger.HIGH
    assert packet[57] == Trigger.FALLING
    assert packet[58:] == bytes(6)  # padding


def test_la_config_without_triggers_clears_the_active_byte():
    packet = pr.build_la_config(
        mode=SamplingMode.STREAM,
        channels=8,
        sample_count=0,
        psc_reg=1079,
        arr1=2,
        n_streams=1,
    )
    assert packet[3] == SamplingMode.STREAM
    assert packet[20] == 0
    assert packet[25:57] == bytes(32)
    assert packet[57] == Trigger.NONE


def test_la_config_rejects_bad_arguments():
    common = dict(channels=8, psc_reg=0, arr1=2, n_streams=1)
    with pytest.raises(ValueError):  # not divisible by the DMA stream count
        pr.build_la_config(
            mode=SamplingMode.BUFFER, sample_count=1001,
            **{**common, "n_streams": 4},
        )
    with pytest.raises(ValueError):  # stream mode always uses one stream
        pr.build_la_config(
            mode=SamplingMode.STREAM, sample_count=0, **{**common, "n_streams": 4}
        )
    with pytest.raises(ValueError):  # 24 channels are broken (spec 6.4)
        pr.build_la_config(
            mode=SamplingMode.BUFFER, sample_count=1000,
            **{**common, "channels": 24},
        )
    with pytest.raises(ValueError):  # NDTR is 16 bit
        pr.build_la_config(
            mode=SamplingMode.BUFFER, sample_count=70_000, **common
        )
    with pytest.raises(ValueError):  # ARR is 16 bit
        pr.build_la_config(
            mode=SamplingMode.BUFFER, sample_count=1000,
            **{**common, "arr1": 20_000, "n_streams": 4},
        )


# --------------------------------------------------------------------------
# triggers
# --------------------------------------------------------------------------


def test_encode_triggers_accepts_mapping_and_sequence():
    from_map = pr.encode_triggers({0: Trigger.RISING, 31: Trigger.HIGH})
    from_seq = pr.encode_triggers([Trigger.RISING] + [0] * 30 + [Trigger.HIGH])
    assert from_map == from_seq
    assert len(from_map) == 32
    assert from_map[0] == Trigger.RISING
    assert from_map[31] == Trigger.HIGH


@pytest.mark.parametrize("trigger", [Trigger.RISING, Trigger.FALLING, Trigger.ANY])
def test_edge_triggers_rejected_above_channel_15(trigger):
    with pytest.raises(ValueError, match="level triggers only"):
        pr.encode_triggers({16: trigger})
    assert pr.encode_triggers({15: trigger})[15] == trigger


@pytest.mark.parametrize("level", [Trigger.LOW, Trigger.HIGH])
def test_level_triggers_allowed_everywhere(level):
    assert pr.encode_triggers({31: level})[31] == level


def test_trigger_outside_active_channels_is_rejected():
    with pytest.raises(ValueError, match="at least 16 channels"):
        pr.encode_triggers({8: Trigger.HIGH}, channels=8)


def test_invalid_trigger_value():
    with pytest.raises(ValueError, match="invalid trigger type"):
        pr.encode_triggers({0: 9})


# --------------------------------------------------------------------------
# sample clock
# --------------------------------------------------------------------------


@pytest.mark.parametrize("index", range(len(VENDOR_RATES)))
def test_vendor_presets_reproduce_vendor_registers(index):
    rate = VENDOR_RATES[index]
    clock = pr.resolve_samplerate(rate, SamplingMode.BUFFER, 8, 1000, unsafe=True)
    assert clock.psc_reg == VENDOR_TIMER_PSC[index] - 1
    assert clock.arr1 == VENDOR_TIMER_ARR1[index]
    assert clock.actual_rate == pytest.approx(rate)
    assert pr.SAMPLE_CLOCK_HZ / (clock.psc_reg + 1) / clock.arr1 == pytest.approx(rate)


@pytest.mark.parametrize("index", range(len(VENDOR_RATES)))
def test_vendor_presets_in_stream_mode_use_one_stream(index):
    rate = VENDOR_RATES[index]
    clock = pr.resolve_samplerate(rate, SamplingMode.STREAM, 8, unsafe=True)
    assert clock.n_streams == 1
    assert clock.psc_reg == VENDOR_TIMER_PSC[index] - 1
    assert clock.arr1 == VENDOR_TIMER_ARR1[index]


@pytest.mark.parametrize(
    "rate,sample_count,expected",
    [
        (10_000, 1_000, 1),
        (10_000, 65_000, 1),
        (10_000, 65_001, 4),      # 2 streams are bumped to 4
        (10_000, 195_001, 4),     # 3 -> 4 as well
        (10_000, 260_001, 5),
        (36_000_000, 1_000, 1),
        (54_000_000, 1_000, 4),
        (72_000_000, 1_000, 4),
        (108_000_000, 1_000, 5),
        (108_000_000, 240_000, 5),
    ],
)
def test_dma_stream_count_rule(rate, sample_count, expected):
    assert pr.dma_stream_count(rate, SamplingMode.BUFFER, sample_count) == expected


def test_dma_stream_count_is_one_in_stream_mode():
    assert pr.dma_stream_count(108_000_000, SamplingMode.STREAM, 10 ** 9) == 1


def test_arr_register_value():
    clock = pr.resolve_samplerate(108_000_000, SamplingMode.BUFFER, 8, 30_000)
    assert (clock.psc_reg, clock.arr1, clock.n_streams) == (1, 1, 5)
    assert clock.arr_reg == 4  # ARR1 * N - 1, spec 5.2


@pytest.mark.parametrize(
    "rate,channels,mode,sample_count",
    [
        (108_000_000, 8, SamplingMode.BUFFER, 60_000),   # too many samples at 108 MHz
        (108_000_000, 16, SamplingMode.BUFFER, 1_000),   # 16 ch stops at 72 MHz
        (36_000_000, 32, SamplingMode.BUFFER, 1_000),    # 32 ch stops at 24 MHz
        (24_000_000, 8, SamplingMode.STREAM, None),      # stream 8 ch stops at 18 MHz
        (12_000_000, 16, SamplingMode.STREAM, None),     # stream 16 ch stops at 8 MHz
        (8_000_000, 32, SamplingMode.STREAM, None),      # stream 32 ch stops at 4 MHz
        (1_000_000, 32, SamplingMode.BUFFER, 120_000),   # 32 ch buffer stops at 60k
    ],
)
def test_vendor_limits_raise(rate, channels, mode, sample_count):
    with pytest.raises(ValueError):
        pr.resolve_samplerate(rate, mode, channels, sample_count)
    # the same call is accepted with the documented escape hatch
    pr.resolve_samplerate(rate, mode, channels, sample_count, unsafe=True)


def test_unsafe_does_not_bypass_register_limits():
    # 216 MHz / 65536 / 65536 is the slowest possible rate; below that no
    # register combination exists, and unsafe must not pretend otherwise.
    with pytest.raises(ValueError, match="16-bit"):
        pr.resolve_samplerate(0.01, SamplingMode.STREAM, 8, unsafe=True)
    with pytest.raises(ValueError, match="above"):
        pr.resolve_samplerate(300_000_000, SamplingMode.STREAM, 8, unsafe=True)


def test_generic_solver_hits_exact_rates():
    for rate in (250, 3_000_000, 1, 1500):
        clock = pr.resolve_samplerate(rate, SamplingMode.STREAM, 8, unsafe=True)
        assert clock.actual_rate == pytest.approx(rate)
        assert 0 <= clock.psc_reg <= 0xFFFF
        assert 1 <= clock.arr1 <= 0xFFFF


def test_generic_solver_reports_the_closest_rate():
    clock = pr.resolve_samplerate(7_000_000, SamplingMode.BUFFER, 8, 1000)
    # 216 MHz / 31 is the closest reachable rate
    assert clock.actual_rate == pytest.approx(pr.SAMPLE_CLOCK_HZ / 31)
    assert (clock.psc_reg + 1) * clock.arr1 == 31


# --------------------------------------------------------------------------
# sample count normalisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_streams,expected", [(1, 1001), (4, 1000), (5, 1000)])
def test_normalise_sample_count_divisibility(n_streams, expected):
    assert pr.normalise_sample_count(1001, 8, n_streams) == expected


@pytest.mark.parametrize(
    "channels,capacity", [(8, 240_640), (16, 120_320), (32, 60_160)]
)
def test_buffer_capacity(channels, capacity):
    assert pr.buffer_capacity(channels) == capacity
    assert pr.normalise_sample_count(10 ** 9, channels, 1) == min(capacity, 0xFFFF)


def test_normalise_sample_count_respects_ndtr_width():
    # 8 channels, one stream: NDTR is 16 bit, so 65535 samples is the maximum
    assert pr.normalise_sample_count(240_000, 8, 1) == 65_535
    assert pr.normalise_sample_count(240_000, 8, 4) == 240_000


def test_normalise_sample_count_rejects_tiny_counts():
    with pytest.raises(ValueError):
        pr.normalise_sample_count(3, 8, 4)


# --------------------------------------------------------------------------
# buffer layout (spec 6.1)
# --------------------------------------------------------------------------


def _sample_value(index: int, channels: int) -> int:
    if channels == 8:
        return (index * 7 + 1) & 0xFF
    if channels == 16:
        return (index * 7 + 1) & 0xFFFF
    return ((index * 7 + 1) & 0xFFFF) | (((index * 13 + 5) & 0xFFFF) << 16)


def _make_raw_buffer(sample_count: int, channels: int, n_streams: int) -> bytes:
    """Lay out a synthetic capture exactly as the firmware DMA would."""
    bps = 1 if channels == 8 else 2
    per_part = sample_count // n_streams
    parts = []
    for k in range(n_streams):
        parts.append(
            b"".join(
                (_sample_value(i * n_streams + k, channels) & (0xFF if bps == 1 else 0xFFFF))
                .to_bytes(bps, "little")
                for i in range(per_part)
            )
        )
    if channels == 32:
        parts.append(
            b"".join(
                ((_sample_value(i * n_streams, channels) >> 16) & 0xFFFF).to_bytes(2, "little")
                for i in range(per_part)
            )
        )
    body = b"".join(parts)
    return body + b"\xa5" * (pr.BUFFER_SIZE - len(body))


@pytest.mark.parametrize("channels", [8, 16])
@pytest.mark.parametrize("n_streams", [1, 4, 5])
def test_deinterleave_buffer_restores_sample_order(channels, n_streams):
    sample_count = 200 * n_streams
    raw = _make_raw_buffer(sample_count, channels, n_streams)
    out = pr.deinterleave_buffer(raw, sample_count, channels, n_streams)
    unit = pr.bytes_per_sample(channels)
    assert len(out) == sample_count * unit
    for i in range(sample_count):
        value = int.from_bytes(out[i * unit:(i + 1) * unit], "little")
        assert value == _sample_value(i, channels)


def test_deinterleave_buffer_32_channels_merges_the_second_part():
    sample_count = 128
    raw = _make_raw_buffer(sample_count, 32, 1)
    out = pr.deinterleave_buffer(raw, sample_count, 32, 1)
    assert len(out) == sample_count * 4
    for i in range(sample_count):
        value = int.from_bytes(out[i * 4:(i + 1) * 4], "little")
        assert value == _sample_value(i, 32)
        assert value >> 16 == (_sample_value(i, 32) >> 16)  # channels 16..31


@pytest.mark.parametrize("n_streams", [4, 5])
def test_deinterleave_buffer_32_channels_multi_stream_layout(n_streams):
    # Firmware limits keep 32 channels at one stream, but the layout of spec 6.1
    # is defined for any N: N low-half samples followed by one high-half sample.
    sample_count = 40 * n_streams
    raw = _make_raw_buffer(sample_count, 32, n_streams)
    out = pr.deinterleave_buffer(raw, sample_count, 32, n_streams)
    group = n_streams * 2 + 2
    assert len(out) == (sample_count // n_streams) * group
    for i in range(sample_count // n_streams):
        for k in range(n_streams):
            offset = i * group + k * 2
            assert int.from_bytes(out[offset:offset + 2], "little") == (
                _sample_value(i * n_streams + k, 32) & 0xFFFF
            )
        offset = i * group + n_streams * 2
        assert int.from_bytes(out[offset:offset + 2], "little") == (
            _sample_value(i * n_streams, 32) >> 16
        )


def test_deinterleave_buffer_single_stream_is_a_passthrough():
    raw = bytes(range(256)) + b"\xa5" * (pr.BUFFER_SIZE - 256)
    assert pr.deinterleave_buffer(raw, 100, 8, 1) == bytes(range(100))


def test_deinterleave_buffer_validates_arguments():
    raw = b"\x00" * pr.BUFFER_SIZE
    with pytest.raises(ValueError, match="divisible"):
        pr.deinterleave_buffer(raw, 101, 8, 4)
    with pytest.raises(ValueError, match="need"):
        pr.deinterleave_buffer(b"\x00" * 10, 100, 8, 1)


# --------------------------------------------------------------------------
# stream layout (spec 6.2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("channels", [8, 16])
def test_decode_stream_packet_passthrough(channels):
    packet = bytes((i * 31 + channels) & 0xFF for i in range(pr.STREAM_PACKET_SIZE))
    assert pr.decode_stream_packet(packet, channels) == packet


def test_decode_stream_packet_32_channels():
    half = pr.STREAM_PACKET_SIZE // 2
    low = b"".join((i & 0xFFFF).to_bytes(2, "little") for i in range(half // 2))
    high = b"".join(((i ^ 0xBEEF) & 0xFFFF).to_bytes(2, "little") for i in range(half // 2))
    out = pr.decode_stream_packet(low + high, 32)
    assert len(out) == pr.STREAM_PACKET_SIZE
    for i in range(half // 2):
        value = int.from_bytes(out[i * 4:(i + 1) * 4], "little")
        assert value & 0xFFFF == i
        assert value >> 16 == (i ^ 0xBEEF) & 0xFFFF


def test_decode_stream_packet_rejects_wrong_size():
    with pytest.raises(ValueError):
        pr.decode_stream_packet(b"\x00" * 100, 8)


def test_stream_packet_time_and_packet_count():
    assert pr.stream_packet_time(10_000, 8) == pytest.approx(1.6384)
    assert pr.stream_packet_time(10_000, 32) == pytest.approx(0.4096)
    assert pr.stream_packets_for_samples(16_384, 8) == 1
    assert pr.stream_packets_for_samples(16_385, 8) == 2
    assert pr.stream_packets_for_samples(16_384, 16) == 2


# --------------------------------------------------------------------------
# reply parsers
# --------------------------------------------------------------------------


def test_parse_id_reply():
    reply = bytearray(512)
    reply[3] = 5
    reply[4:8] = bytes([0, 2, 0, 0])
    reply[8:10] = struct.pack("<H", 0)
    reply[10] = 1
    info = pr.parse_id_reply(bytes(reply))
    assert info.controller_id == 5
    assert info.firmware == (0, 2, 0, 0)
    assert info.firmware_str == "0.2"
    assert info.hardware == 1
    assert info.is_rdc2_0064


def test_parse_status_reply():
    reply = bytearray(512)
    reply[3] = pr.STATUS_SAMPLING_CMP
    reply[4:6] = struct.pack("<H", 1234)
    status = pr.parse_status_reply(bytes(reply))
    assert status.sampling_complete
    assert not status.trigger_await
    assert status.ndtr == 1234


def test_parse_stop_reply():
    reply = bytearray(512)
    reply[0] = 1
    reply[1:5] = struct.pack("<I", 4321)
    report = pr.parse_stop_reply(bytes(reply))
    assert report.overflow
    assert report.valid_packets == 4321
    assert report.valid_samples(8) == 4321 * 16_384
    assert report.valid_samples(32) == 4321 * 4_096


def test_short_replies_are_rejected():
    with pytest.raises(pr.ProtocolError):
        pr.parse_id_reply(b"\x00\x00")


# --------------------------------------------------------------------------
# PWM generator (spec 8)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("freq", [0.03, 1, 50, 1_000, 100_000, 1_000_000, 27_000_000])
def test_pwm_solver_is_exact_for_round_frequencies(freq):
    psc_reg, arr_reg, actual = pr.solve_pwm_frequency(freq)
    assert 0 <= psc_reg <= 0xFFFF
    assert 0 <= arr_reg <= 0xFFFF
    assert actual == pytest.approx(pr.PWM_CLOCK_HZ / ((psc_reg + 1) * (arr_reg + 1)))
    assert actual == pytest.approx(freq, rel=1e-6)


def test_pwm_solver_maximises_arr():
    # 108 MHz / 1 kHz = 108000 = 2 * 54000: the vendor picks PSC=2, ARR=54000
    psc_reg, arr_reg, actual = pr.solve_pwm_frequency(1_000)
    assert (psc_reg, arr_reg) == (1, 53_999)
    assert actual == pytest.approx(1_000)


def test_pwm_solver_range_check():
    with pytest.raises(ValueError):
        pr.solve_pwm_frequency(0.01)
    with pytest.raises(ValueError):
        pr.solve_pwm_frequency(30_000_000)


def test_pwm_duty_to_ccr():
    assert pr.pwm_duty_to_ccr(50, 53_999) == 27_000
    assert pr.pwm_duty_to_ccr(0, 53_999) == 0
    assert pr.pwm_duty_to_ccr(100, 999) == 1_000
    with pytest.raises(ValueError):
        pr.pwm_duty_to_ccr(101, 999)


def test_pwm_packet_layout():
    setup1 = pr.plan_pwm_timer(1, 1_000, {"M15": 50, "M17": 25})
    setup2 = pr.plan_pwm_timer(2, 2_000, {"M19": 10})
    packet = pr.build_pwm_packet(setup1, setup2)
    assert len(packet) == 64
    assert packet[0] == pr.Module.PWM
    assert packet[3] == 0b101  # M15 and M17
    assert struct.unpack_from("<H", packet, 4)[0] == 1
    assert struct.unpack_from("<H", packet, 6)[0] == 53_999
    assert struct.unpack_from("<H", packet, 8)[0] == 27_000   # M15
    assert struct.unpack_from("<H", packet, 10)[0] == 0       # M16
    assert struct.unpack_from("<H", packet, 12)[0] == 13_500  # M17
    assert packet[14] == 0b10  # M19
    assert struct.unpack_from("<H", packet, 15)[0] == setup2.psc_reg
    assert struct.unpack_from("<H", packet, 17)[0] == setup2.arr_reg
    assert struct.unpack_from("<H", packet, 19)[0] == 0       # M18
    assert struct.unpack_from("<H", packet, 21)[0] == pr.pwm_duty_to_ccr(10, setup2.arr_reg)


def test_pwm_off_packet_has_zero_masks():
    packet = pr.build_pwm_off_packet()
    assert packet[0] == pr.Module.PWM
    assert packet[3] == 0
    assert packet[14] == 0
    assert packet[3:] == bytes(61)


def test_plan_pwm_timer_rejects_foreign_channels():
    with pytest.raises(ValueError, match="does not belong"):
        pr.plan_pwm_timer(1, 1_000, {"M18": 50})


# --------------------------------------------------------------------------
# PWM input (spec 9)
# --------------------------------------------------------------------------


def test_pwm_input_ranges_match_vendor_table():
    # Measurements.xaml.cs: TimerPSC = {3600, 40, 1}, DetectDelayTicks = {1, 1, 2}
    assert [r.divider for r in pr.PWM_INPUT_RANGES] == [3600, 40, 1]
    assert [r.delay_ticks for r in pr.PWM_INPUT_RANGES] == [1, 1, 2]
    assert [r.psc_reg for r in pr.PWM_INPUT_RANGES] == [3599, 39, 0]
    assert pr.PWM_INPUT_RANGES[0].tick_hz == pytest.approx(216e6 / 3600)


def test_pwm_input_config_packet():
    packet = pr.build_pwm_input_config(3599)
    assert packet[0] == pr.Module.PWM_INPUT
    assert packet[1] == pr.PwmInputCmd.CONFIG
    assert struct.unpack_from("<H", packet, 3)[0] == 3599
    assert pr.build_pwm_input_stop()[:2] == bytes([3, 2])
    assert pr.build_pwm_input_get_data()[:2] == bytes([3, 1])


def test_pwm_input_measurement():
    reply = bytearray(512)
    reply[0:2] = struct.pack("<H", 600)
    reply[2:4] = struct.pack("<H", 300)
    period, width = pr.parse_pwm_input_reply(bytes(reply))
    assert (period, width) == (600, 300)
    rng = pr.PWM_INPUT_RANGES[0]  # 216 MHz / 3600 = 60 kHz ticks
    measurement = pr.pwm_input_measurement(period, width, rng)
    assert measurement.period_ticks == 601  # detection delay compensation
    assert measurement.width_ticks == 301
    assert measurement.period_s == pytest.approx(601 / 60_000)
    assert measurement.frequency_hz == pytest.approx(60_000 / 601)
    assert measurement.duty_percent == pytest.approx(100 * 301 / 601)
    assert measurement.valid


def test_pwm_input_measurement_without_signal():
    measurement = pr.pwm_input_measurement(0, 0, pr.PWM_INPUT_RANGES[2])
    assert not measurement.valid
    assert measurement.frequency_hz == 0.0
    assert measurement.duty_percent == 0.0
