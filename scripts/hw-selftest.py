#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Hardware regression test for the RDC2-0064.

Drives the board's own PWM outputs into its logic inputs and checks that
every capture path (rdc2la buffer/stream/triggers, sigrok-cli, the EDGE
trigger input and the frequency meter) returns exactly the signal that was
generated. Needs loopback jumpers:

    M15 -> D0            always
    M16 -> D1            default, or M16 -> EDGE with --edge
    M17 -> M20           with --meter

Run it from the repository with the rdc2la virtualenv:

    python/.venv/bin/python scripts/hw-selftest.py [--edge] [--meter]
        [--sigrok | --no-sigrok] [--stream-rate 12M] [--port /dev/cu...|usb]

sigrok-cli is exercised when it is on PATH or in $RDC2_SIGROK_PREFIX/bin.
Exit status is 0 when every check passed.
"""

from __future__ import annotations

import argparse
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass

from rdc2la import protocol as pr
from rdc2la.cli import parse_frequency
from rdc2la.device import Device
from rdc2la.protocol import Trigger

PWM_HZ = 1000.0
DUTY = {"M15": 50.0, "M16": 25.0, "M17": 30.0}
CH8 = "D0,D1,D2,D3,D4,D5,D6,D7"


# --------------------------------------------------------------------------
# Sample analysis (pure Python, C-speed via bytes.translate / bytes.find)
# --------------------------------------------------------------------------


@dataclass
class ChannelStats:
    samples: int
    first: int
    high_ratio: float
    rising: int
    falling: int
    first_edge: int | None
    period_min: int
    period_max: int
    period_mean: float

    def freq(self, rate: float) -> float:
        return rate / self.period_mean if self.period_mean else 0.0


def channel_bits(data: bytes, unitsize: int, channel: int) -> bytes:
    """One byte (0/1) per sample for the given channel."""
    byte_off = channel // 8
    bit = channel % 8
    lane = data[byte_off::unitsize] if unitsize > 1 else data
    table = bytes((b >> bit) & 1 for b in range(256))
    return lane.translate(table)


def analyse(bits: bytes) -> ChannelStats:
    n = len(bits)
    edges: list[tuple[int, int]] = []  # (position, new level)
    pos = 0
    level = bits[0]
    while True:
        pos = bits.find(b"\x00" if level else b"\x01", pos)
        if pos < 0:
            break
        level ^= 1
        edges.append((pos, level))
    rising = [p for p, l in edges if l == 1]
    falling = [p for p, l in edges if l == 0]
    periods = [b - a for a, b in zip(rising, rising[1:])]
    # Duty cycle over whole periods only, so short captures are not skewed
    # by the partial period at either end.
    if len(rising) >= 2:
        window = bits[rising[0]:rising[-1]]
    else:
        window = bits
    return ChannelStats(
        samples=n,
        first=bits[0],
        high_ratio=window.count(1) / len(window),
        rising=len(rising),
        falling=len(falling),
        first_edge=edges[0][0] if edges else None,
        period_min=min(periods) if periods else 0,
        period_max=max(periods) if periods else 0,
        period_mean=sum(periods) / len(periods) if periods else 0.0,
    )


def describe(st: ChannelStats, rate: float) -> str:
    if st.rising < 2:
        return f"const/rare high={st.high_ratio:.3f} edges={st.rising}/{st.falling}"
    return (
        f"f={st.freq(rate):.2f}Hz duty={st.high_ratio * 100:.1f}% "
        f"period={st.period_min}..{st.period_max} edges={st.rising}/{st.falling}"
    )


# --------------------------------------------------------------------------
# Test harness
# --------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
        sys.stdout.flush()
        return ok

    def skip(self, name: str, why: str) -> None:
        print(f"SKIP  {name}  [{why}]")

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.results if not ok)


def expect_pwm(
    rep: Report,
    name: str,
    data: bytes,
    unitsize: int,
    rate: float,
    *,
    channel: int,
    duty: float,
    jitter: int = 0,
    duty_tol: float = 1.0,
    pwm_hz: float = PWM_HZ,
) -> ChannelStats:
    st = analyse(channel_bits(data, unitsize, channel))
    nominal = rate / pwm_hz
    ok = (
        st.rising >= 2
        and abs(st.freq(rate) - pwm_hz) <= pwm_hz * 0.002
        and abs(st.high_ratio * 100 - duty) <= duty_tol
        and st.period_min >= nominal - jitter
        and st.period_max <= nominal + jitter
    )
    rep.check(f"{name}: D{channel}", ok, describe(st, rate))
    return st


def expect_quiet(rep: Report, name: str, data: bytes, unitsize: int, channels: list[int]) -> None:
    noisy = [c for c in channels if channel_bits(data, unitsize, c).count(1)]
    rep.check(f"{name}: D{channels[0]}..D{channels[-1]} quiet", not noisy, f"noisy: {noisy}" if noisy else "")


def stream_capture(dev: Device, rate: float, channels: int, samples: int) -> tuple[bytes, object]:
    buf = bytearray()
    with dev.capture_stream(rate, channels, samples=samples) as cap:
        for chunk in cap:
            buf += chunk
            if len(buf) >= samples * pr.bytes_per_sample(channels):
                break
    unit = pr.bytes_per_sample(channels)
    return bytes(buf[: samples * unit]), cap.summary


# --------------------------------------------------------------------------
# Test groups
# --------------------------------------------------------------------------


def test_buffer(rep: Report, dev: Device, d1_wired: bool) -> None:
    cases = [
        # name, rate, channels, samples, PWM frequency, period jitter allowed
        ("buffer 8ch 100k 10k", 100e3, 8, 10_000, 1e3, 0),
        ("buffer 16ch 1M 100k", 1e6, 16, 100_000, 1e3, 0),
        ("buffer 32ch 24M 60k", 24e6, 32, 60_000, 10e3, 1),
        ("buffer 8ch 72M 240k", 72e6, 8, 240_000, 100e3, 1),
        # 16 channels at 72 MHz was flaky on the board this was written on
        # (spec 7.3); 54 MHz is the highest rate that was always clean.
        ("buffer 16ch 54M 120k", 54e6, 16, 120_000, 100e3, 1),
    ]
    for name, rate, channels, samples, pwm_hz, jitter in cases:
        dev.pwm_set(pwm_hz, DUTY)
        res = dev.capture_buffer(rate, channels, samples)
        rep.check(f"{name}: count", res.sample_count == samples, f"{res.sample_count}")
        expect_pwm(rep, name, res.data, res.unitsize, res.rate, channel=0, duty=DUTY["M15"],
                   jitter=jitter, pwm_hz=pwm_hz)
        if d1_wired:
            expect_pwm(rep, name, res.data, res.unitsize, res.rate, channel=1, duty=DUTY["M16"],
                       jitter=jitter, pwm_hz=pwm_hz)
        expect_quiet(rep, name, res.data, res.unitsize, list(range(2, channels)))
    dev.pwm_set(PWM_HZ, DUTY)


def test_stream(rep: Report, dev: Device, d1_wired: bool, fast_rate: float) -> None:
    cases = [
        ("stream 8ch 1M 3M", 1e6, 8, 3_000_000),
        ("stream 32ch 1M 1M", 1e6, 32, 1_000_000),
        (f"stream 8ch {fast_rate / 1e6:g}M 5M", fast_rate, 8, 5_000_000),
    ]
    for name, rate, channels, samples in cases:
        data, summary = stream_capture(dev, rate, channels, samples)
        unit = pr.bytes_per_sample(channels)
        rep.check(
            f"{name}: no overflow",
            not summary.overflow and len(data) == samples * unit,
            f"overflow={summary.overflow} valid={summary.valid_samples}",
        )
        if len(data) < unit * 10:
            continue
        expect_pwm(rep, name, data, unit, rate, channel=0, duty=DUTY["M15"], jitter=1)
        if d1_wired:
            expect_pwm(rep, name, data, unit, rate, channel=1, duty=DUTY["M16"], jitter=1)


def triggered_capture(rep: Report, dev: Device, name: str, rate: float, **kw):
    """Buffer capture that reports a never-firing trigger as a failure."""
    try:
        return dev.capture_buffer(rate, 8, 5000, timeout=10, **kw)
    except TimeoutError:
        dev.stop()
        rep.check(name, False, "trigger did not fire within 10 s")
        return None


def test_triggers(rep: Report, dev: Device, d1_wired: bool) -> None:
    rate = 1e6
    half = int(rate / PWM_HZ / 2)  # samples per half period of the 50 % signal
    cases = [
        # name, triggers, expected first level of D0, expected first edge of D0
        ("trigger D0=r", {0: Trigger.RISING}, 1, half),
        ("trigger D0=f", {0: Trigger.FALLING}, 0, half),
        ("trigger D0=e", {0: Trigger.ANY}, None, half),
    ]
    if d1_wired:
        # M15 and M16 rise together; M16 falls at 25 %.
        cases += [
            ("trigger D1=1", {1: Trigger.HIGH}, 1, None),
            ("trigger D1=0", {1: Trigger.LOW}, None, None),
            ("trigger D0=f,D1=0", {0: Trigger.FALLING, 1: Trigger.LOW}, 0, half),
        ]
    for name, trig, first, edge in cases:
        res = triggered_capture(rep, dev, name, rate, triggers=trig)
        if res is None:
            continue
        st = analyse(channel_bits(res.data, 1, 0))
        ok = st.rising >= 2
        if first is not None:
            ok = ok and st.first == first
        if edge is not None:
            ok = ok and st.first_edge is not None and abs(st.first_edge - edge) <= 2
        rep.check(name, ok, f"first={st.first} first_edge={st.first_edge} {describe(st, rate)}")


def test_edge(rep: Report, dev: Device) -> None:
    rate = 1e6
    half = int(rate / PWM_HZ / 2)
    for name, trig, first, edge in [
        ("EDGE r", Trigger.RISING, 1, half),
        ("EDGE f", Trigger.FALLING, 0, half),
        ("EDGE e", Trigger.ANY, None, half),
    ]:
        res = triggered_capture(rep, dev, name, rate, edge_trigger=trig)
        if res is None:
            continue
        st = analyse(channel_bits(res.data, 1, 0))
        ok = st.rising >= 2 and st.first_edge is not None and abs(st.first_edge - edge) <= 2
        if first is not None:
            ok = ok and st.first == first
        rep.check(name, ok, f"first={st.first} first_edge={st.first_edge} {describe(st, rate)}")
    # Gated by level: sampling runs only while EDGE (in phase with D0) is at
    # that level, so D0 is almost all ones or all zeros.
    for name, trig, want_high in [("EDGE level 1 (gated)", Trigger.HIGH, True),
                                  ("EDGE level 0 (gated)", Trigger.LOW, False)]:
        res = triggered_capture(rep, dev, name, rate, edge_trigger=trig)
        if res is None:
            continue
        bits = channel_bits(res.data, 1, 0)
        ratio = bits.count(1) / len(bits)
        rep.check(name, ratio > 0.99 if want_high else ratio < 0.01, f"D0 high {ratio * 100:.1f}%")


def test_meter(rep: Report, dev: Device) -> None:
    for rng in (1, 2):
        dev.measure_start(rng)
        try:
            time.sleep(0.5)
            m = dev.measure_read()
        finally:
            dev.measure_stop()
        ok = abs(m.frequency_hz - PWM_HZ) <= PWM_HZ * 0.005 and abs(m.duty_percent - DUTY["M17"]) <= 1.0
        rep.check(f"meter range {rng}", ok, f"f={m.frequency_hz:.2f}Hz duty={m.duty_percent:.2f}%")


def find_sigrok_cli() -> str | None:
    prefix = os.environ.get("RDC2_SIGROK_PREFIX", os.path.expanduser("~/.local/rdc2-sigrok"))
    cand = os.path.join(prefix, "bin", "sigrok-cli")
    if os.access(cand, os.X_OK):
        return cand
    return shutil.which("sigrok-cli")


def read_sr(path: str) -> tuple[bytes, int, float]:
    with zipfile.ZipFile(path) as z:
        meta = configparser.ConfigParser()
        meta.read_string(z.read("metadata").decode())
        dev = meta["device 1"]
        unitsize = int(dev["unitsize"])
        value, unit = dev["samplerate"].split()
        rate = float(value) * {"Hz": 1, "kHz": 1e3, "MHz": 1e6}[unit]
        names = [n for n in z.namelist() if n.startswith("logic-1")]
        names.sort(key=lambda n: int(n.rsplit("-", 1)[1]) if n.count("-") == 2 else 0)
        data = b"".join(z.read(n) for n in names)
    return data, unitsize, rate


def sigrok_conn(port: str) -> str:
    """rdc2la port name as the driver's conn= option.

    Serial ports are passed as they are; the libusb selector ``usb:<bus>.<address>``
    becomes the ``<bus>.<address>`` form that sr_usb_find() expects.
    """
    return port[4:] if port.lower().startswith("usb:") else port


def test_sigrok(rep: Report, cli: str, port: str, d1_wired: bool) -> None:
    dev_arg = f"chipdip-rdc2-0064:conn={sigrok_conn(port)}"
    tmp = tempfile.mkdtemp(prefix="hw-selftest-")
    cases = [
        ("sigrok buffer 100k 10k", ["-c", "samplerate=100k", "--channels", CH8, "--samples", "10000"], None),
        ("sigrok stream 1M 3M", ["-c", "samplerate=1m:data_source=Stream", "--channels", CH8, "--samples", "3000000"], None),
        ("sigrok buffer 72M 240k", ["-c", "samplerate=72m", "--channels", CH8, "--samples", "240000"], None),
        ("sigrok trigger D0=r", ["-c", "samplerate=1m", "--channels", "D0,D1", "--samples", "5000", "-t", "D0=r"], 1),
    ]
    for name, args, first in cases:
        out = os.path.join(tmp, "cap.sr")
        cmd = [cli, "-d", dev_arg, *args, "-O", "srzip", "-o", out]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not os.path.exists(out):
            rep.check(name, False, (proc.stderr or proc.stdout).strip().splitlines()[-1:] or "no output")
            continue
        data, unitsize, rate = read_sr(out)
        st = expect_pwm(rep, name, data, unitsize, rate, channel=0, duty=DUTY["M15"])
        if first is not None:
            rep.check(f"{name}: starts at edge", st.first == first and st.first_edge is not None
                      and abs(st.first_edge - int(rate / PWM_HZ / 2)) <= 2,
                      f"first={st.first} first_edge={st.first_edge}")
        if d1_wired:
            expect_pwm(rep, name, data, unitsize, rate, channel=1, duty=DUTY["M16"])
        os.remove(out)
    os.rmdir(tmp)


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port", help="serial port or usb[:bus.address]; autodetected when omitted")
    ap.add_argument("--edge", action="store_true", help="M16 is wired to EDGE instead of D1")
    ap.add_argument("--meter", action="store_true", help="M17 is wired to M20: test the frequency meter")
    ap.add_argument("--stream-rate", default="12M", help="fast stream rate to test (default 12M; vendor limit 18M)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sigrok", action="store_true", help="require sigrok-cli tests")
    g.add_argument("--no-sigrok", action="store_true", help="skip sigrok-cli tests")
    args = ap.parse_args(argv)

    fast_rate = parse_frequency(args.stream_rate)
    d1_wired = not args.edge
    rep = Report()

    cli = None if args.no_sigrok else find_sigrok_cli()
    if args.sigrok and not cli:
        print("sigrok-cli not found", file=sys.stderr)
        return 2

    with Device.open(args.port) as dev:
        port = dev.port
        ident = dev.get_id()
        rep.check("device", ident.is_rdc2_0064, f"{port} firmware {ident.firmware_str} hw {ident.hardware}")
        dev.pwm_set(PWM_HZ, DUTY)
        try:
            test_buffer(rep, dev, d1_wired)
            test_stream(rep, dev, d1_wired, fast_rate)
            test_triggers(rep, dev, d1_wired)
            if args.edge:
                test_edge(rep, dev)
            else:
                rep.skip("EDGE trigger", "wire M16 -> EDGE and pass --edge")
            if args.meter:
                test_meter(rep, dev)
            else:
                rep.skip("frequency meter", "wire M17 -> M20 and pass --meter")
        finally:
            dev.pwm_off()

    if cli:
        # sigrok-cli needs the port for itself; the device is closed above.
        with Device.open(port) as dev:
            dev.pwm_set(PWM_HZ, DUTY)
        try:
            test_sigrok(rep, cli, port, d1_wired)
        finally:
            with Device.open(port) as dev:
                dev.pwm_off()
    else:
        rep.skip("sigrok-cli", "not found; build the stack or use --no-sigrok")

    total = len(rep.results)
    print(f"\n{total - rep.failed}/{total} checks passed")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
