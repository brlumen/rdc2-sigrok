# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Command line interface for the RDC2-0064 logic analyzer.

Run ``rdc2la --help`` for the list of subcommands.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from typing import Sequence

from . import protocol as pr
from .device import Device, DeviceError, StreamSummary, stream_to_writer
from .protocol import SamplingMode, Trigger
from .srfile import writer_for_path

__all__ = ["main", "build_parser", "parse_frequency", "parse_count",
           "parse_duration", "parse_triggers", "parse_trigger_type", "parse_duties"]

log = logging.getLogger("rdc2la.cli")

_SI = {"": 1.0, "k": 1e3, "m": 1e6, "g": 1e9}
_TIME_UNITS = {"ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
_TRIGGER_CHARS = {
    "0": Trigger.LOW,
    "1": Trigger.HIGH,
    "r": Trigger.RISING,
    "f": Trigger.FALLING,
    "e": Trigger.ANY,
}


class CliError(Exception):
    """A user-facing error; printed without a traceback."""


# --------------------------------------------------------------------------
# argument value parsers
# --------------------------------------------------------------------------


def parse_frequency(text: str) -> float:
    """``100k``, ``1M``, ``72MHz``, ``500`` -> Hz."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmMgG]?)\s*(?:[hH][zZ])?\s*", text)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid frequency {text!r}, expected e.g. 100k, 1M, 72MHz"
        )
    return float(match.group(1)) * _SI[match.group(2).lower()]


def parse_count(text: str) -> int:
    """``10k``, ``1M``, ``16G``, ``2500`` -> integer count."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmMgG]?)\s*", text)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid count {text!r}, expected e.g. 10k, 1M, 240000"
        )
    return int(float(match.group(1)) * _SI[match.group(2).lower()])


def parse_duration(text: str) -> float:
    """``30s``, ``10m``, ``1.5h``, ``250ms``, ``45`` -> seconds."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*", text, re.IGNORECASE)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid duration {text!r}, expected e.g. 30s, 10m, 1.5h, 250ms"
        )
    unit = (match.group(2) or "s").lower()
    return float(match.group(1)) * _TIME_UNITS[unit]


def parse_trigger_type(text: str) -> Trigger:
    """``0`` low, ``1`` high, ``r`` rising, ``f`` falling, ``e`` any edge."""
    key = text.strip().lower()
    if key not in _TRIGGER_CHARS:
        raise argparse.ArgumentTypeError(
            f"invalid trigger type {text!r}, expected one of "
            f"{', '.join(_TRIGGER_CHARS)}"
        )
    return _TRIGGER_CHARS[key]


def parse_triggers(text: str) -> dict[int, Trigger]:
    """``D3=r,D5=1,D0=f`` -> ``{3: RISING, 5: HIGH, 0: FALLING}``."""
    triggers: dict[int, Trigger] = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, value = item.partition("=")
        if not sep:
            raise argparse.ArgumentTypeError(
                f"invalid trigger {item!r}, expected CHANNEL=TYPE such as D3=r"
            )
        name = name.strip().lstrip("dD")
        if not name.isdigit():
            raise argparse.ArgumentTypeError(
                f"invalid trigger channel {name!r}, expected D0..D31"
            )
        channel = int(name)
        if not 0 <= channel <= 31:
            raise argparse.ArgumentTypeError(f"trigger channel D{channel} out of range")
        triggers[channel] = parse_trigger_type(value)
    if not triggers:
        raise argparse.ArgumentTypeError("no triggers given")
    return triggers


def parse_duties(text: str) -> dict[str, float]:
    """``M15=50,M16=25`` -> ``{'M15': 50.0, 'M16': 25.0}``."""
    duties: dict[str, float] = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, value = item.partition("=")
        name = name.strip().upper()
        if not sep or name not in pr.PWM_CHANNELS:
            raise argparse.ArgumentTypeError(
                f"invalid duty {item!r}, expected e.g. M15=50 "
                f"(outputs: {', '.join(pr.PWM_CHANNELS)})"
            )
        try:
            duty = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid duty cycle {value!r}") from None
        if not 0.0 <= duty <= 100.0:
            raise argparse.ArgumentTypeError(f"duty cycle {duty} outside 0..100 %")
        duties[name] = duty
    if not duties:
        raise argparse.ArgumentTypeError("no duty cycles given")
    return duties


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------


def format_hz(value: float) -> str:
    for unit, scale in (("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3)):
        if abs(value) >= scale:
            return f"{value / scale:g} {unit}"
    return f"{value:g} Hz"


def format_seconds(value: float) -> str:
    if value >= 3600:
        return f"{value / 3600:.2f} h"
    if value >= 60:
        return f"{value / 60:.2f} min"
    if value >= 1:
        return f"{value:.2f} s"
    return f"{value * 1e3:.2f} ms"


def _progress_printer(prefix: str):
    state = {"last": 0.0}

    def report(done: int, total: int | None) -> None:
        now = time.monotonic()
        finished = total is not None and done >= total
        if not finished and now - state["last"] < 0.2:
            return
        state["last"] = now
        if total:
            percent = 100.0 * done / total
            sys.stderr.write(f"\r{prefix}: {done}/{total} samples ({percent:5.1f} %)")
        else:
            sys.stderr.write(f"\r{prefix}: {done} samples")
        sys.stderr.flush()

    return report


def _progress_done() -> None:
    sys.stderr.write("\n")
    sys.stderr.flush()


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------


def _open_device(args) -> Device:
    return Device.open(args.port, log_packets=args.verbose >= 2)


def cmd_ports(args) -> int:
    ports = Device.find_ports()
    if not ports:
        print("no RDC2-0064 found "
              f"(USB {pr.USB_VID:04x}:{pr.USB_PID:04x})")
        return 1
    for port in ports:
        print(port)
    return 0


def cmd_id(args) -> int:
    with _open_device(args) as device:
        info = device.device_id or device.get_id()
        print(f"port:              {device.port}")
        print(f"controller id:     {info.controller_id}")
        print(f"firmware version:  {info.firmware_str}")
        print(f"hardware version:  {info.hardware}")
        print(f"memory size:       {info.memory_size}")
    return 0


def cmd_status(args) -> int:
    with _open_device(args) as device:
        status = device.get_status()
        print(f"status bits:       0x{status.bits:02x}")
        print(f"sampling complete: {status.sampling_complete}")
        print(f"trigger await:     {status.trigger_await} (never set by firmware v0.2)")
        print(f"DMA NDTR:          {status.ndtr}")
    return 0


def cmd_reset(args) -> int:
    with _open_device(args) as device:
        report = device.stop()
        device.pwm_off()
        print("device stopped")
        print(f"stream overflow:   {report.overflow}")
        print(f"valid packets:     {report.valid_packets}")
    return 0


def _select_mode(args) -> SamplingMode:
    if args.mode != "stream" and args.duration is not None and args.samples is not None:
        raise CliError("use either --samples or --duration, not both")
    if args.mode == "buffer":
        if args.duration is not None:
            raise CliError("--duration is a stream mode option, use --samples")
        return SamplingMode.BUFFER
    if args.mode == "stream":
        return SamplingMode.STREAM
    if args.duration is not None:
        return SamplingMode.STREAM
    if args.samples is None:
        raise CliError("--samples or --duration is required")
    fits = (
        args.samples <= pr.BUFFER_MAX_SAMPLES[args.channels]
        and args.rate <= pr.BUFFER_MAX_RATE[args.channels]
    )
    return SamplingMode.BUFFER if fits else SamplingMode.STREAM


def cmd_capture(args) -> int:
    mode = _select_mode(args)
    if mode is SamplingMode.BUFFER and args.samples is None:
        raise CliError("buffer mode needs --samples")
    if mode is SamplingMode.STREAM and args.samples is None and args.duration is None:
        print("no --samples/--duration given: streaming until Ctrl+C", file=sys.stderr)

    triggers = args.trigger
    edge = args.edge_trigger if args.edge_trigger is not None else Trigger.NONE
    with _open_device(args) as device:
        if mode is SamplingMode.BUFFER:
            return _run_buffer_capture(args, device, triggers, edge)
        return _run_stream_capture(args, device, triggers, edge)


def _report_rate(requested: float, actual: float) -> None:
    if abs(actual - requested) > 1e-6:
        print(
            f"note: requested {format_hz(requested)}, device runs at "
            f"{format_hz(actual)}",
            file=sys.stderr,
        )


def _run_buffer_capture(args, device: Device, triggers, edge) -> int:
    progress = _progress_printer("capturing") if args.progress else None
    try:
        result = device.capture_buffer(
            args.rate,
            args.channels,
            args.samples,
            triggers=triggers,
            edge_trigger=edge,
            progress=progress,
            unsafe=args.unsafe,
        )
    except KeyboardInterrupt:
        if progress:
            _progress_done()
        print("capture cancelled, device stopped; no data written", file=sys.stderr)
        return 130
    if progress:
        _progress_done()
    _report_rate(args.rate, result.rate)
    print(
        f"buffer capture: {result.sample_count} samples, {result.channels} channels, "
        f"{format_hz(result.rate)}, {format_seconds(result.duration)}, "
        f"{result.n_streams} DMA stream(s)"
    )
    if args.output:
        writer = writer_for_path(args.output, result.channels, result.rate)
        try:
            writer.append(result.data)
        finally:
            writer.close()
        print(f"wrote {args.output} ({len(result.data)} bytes)")
    return 0


def _run_stream_capture(args, device: Device, triggers, edge) -> int:
    capture = device.capture_stream(
        args.rate,
        args.channels,
        samples=args.samples,
        duration=args.duration,
        triggers=triggers,
        edge_trigger=edge,
        unsafe=args.unsafe,
    )
    _report_rate(args.rate, capture.rate)
    if capture.sample_limit:
        print(
            f"stream capture: {capture.sample_limit} samples "
            f"({format_seconds(capture.sample_limit / capture.rate)}), "
            f"{args.channels} channels, {format_hz(capture.rate)}"
        )
    if args.output:
        writer = writer_for_path(args.output, args.channels, capture.rate)
    else:
        writer = _NullWriter(args.channels)
    progress = _progress_printer("streaming") if args.progress else None
    try:
        summary = stream_to_writer(capture, writer, progress=progress)
    finally:
        writer.close()
        if progress:
            _progress_done()
    _print_stream_summary(summary, args.output)
    return 130 if summary.cancelled and not summary.written_samples else 0


class _NullWriter:
    """Drops the samples; used when no output file was requested."""

    def __init__(self, channels: int) -> None:
        self.unitsize = pr.bytes_per_sample(channels)
        self.bytes_written = 0

    def append(self, data: bytes) -> None:
        self.bytes_written += len(data)

    def truncate(self, size: int) -> None:
        self.bytes_written = min(self.bytes_written, size)

    def close(self) -> None:
        pass


def _print_stream_summary(summary: StreamSummary, output: str | None) -> None:
    if summary.cancelled:
        print("stopped by user; the device was stopped cleanly", file=sys.stderr)
    if summary.timed_out:
        print("no data from the device, capture stopped early", file=sys.stderr)
    if summary.overflow:
        print(
            "USB overflow reported: the tail of the capture was discarded",
            file=sys.stderr,
        )
    print(
        f"stream capture: {summary.packets_read} packets read, "
        f"{summary.samples_read} samples, {summary.valid_packets} valid packets"
    )
    if summary.truncated:
        print(f"truncated to {summary.written_samples} valid samples")
    if output:
        print(f"wrote {output} ({summary.written_samples} samples)")


def cmd_pwm_set(args) -> int:
    with _open_device(args) as device:
        setup1, setup2 = device.pwm_set(args.freq, args.duty, args.freq2)
        for timer, setup in ((1, setup1), (2, setup2)):
            if not setup.enabled:
                continue
            names = pr.PWM_TIMER_CHANNELS[timer]
            outputs = ", ".join(
                f"{name}={100.0 * setup.ccr[i] / (setup.arr_reg + 1):g} %"
                for i, name in enumerate(names)
                if setup.mask & (1 << i)
            )
            print(
                f"PWM{timer}: {format_hz(setup.actual_freq)} "
                f"(PSC={setup.psc_reg}, ARR={setup.arr_reg}) {outputs}"
            )
    return 0


def cmd_pwm_off(args) -> int:
    with _open_device(args) as device:
        device.pwm_off()
        print("PWM outputs off")
    return 0


def cmd_measure(args) -> int:
    with _open_device(args) as device:
        rng = device.measure_start(args.range)
        print(f"range {rng.name} (PSC={rng.psc_reg}, {format_hz(rng.tick_hz)} ticks)")
        try:
            count = 0
            while args.count == 0 or count < args.count:
                time.sleep(args.interval)
                measurement = device.measure_read()
                count += 1
                if not measurement.valid:
                    print("no signal")
                    continue
                print(
                    f"f={format_hz(measurement.frequency_hz)}  "
                    f"T={format_seconds(measurement.period_s)}  "
                    f"width={format_seconds(measurement.width_s)}  "
                    f"duty={measurement.duty_percent:.2f} %"
                )
        except KeyboardInterrupt:
            print()
        finally:
            device.measure_stop()
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rdc2la",
        description="Control the ChipDip RDC2-0064 logic analyzer.",
    )
    parser.add_argument("-p", "--port", help="serial port; autodetected when omitted")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v: progress logging, -vv: hex dump of every packet",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ports", help="list connected RDC2-0064 devices").set_defaults(
        func=cmd_ports
    )
    subparsers.add_parser("id", help="show controller/firmware identification").set_defaults(
        func=cmd_id
    )
    subparsers.add_parser("status", help="show the sampling status word").set_defaults(
        func=cmd_status
    )
    subparsers.add_parser(
        "reset", help="stop any running capture and switch the PWM outputs off"
    ).set_defaults(func=cmd_reset)

    capture = subparsers.add_parser("capture", help="capture logic samples")
    capture.add_argument(
        "--mode",
        choices=("buffer", "stream", "auto"),
        default="auto",
        help="capture mode (default: auto)",
    )
    capture.add_argument(
        "--rate", type=parse_frequency, required=True, help="sample rate, e.g. 100k or 1M"
    )
    capture.add_argument(
        "--channels", type=int, choices=(8, 16, 32), default=8, help="channel count"
    )
    capture.add_argument("--samples", type=parse_count, help="sample count, e.g. 10k")
    capture.add_argument(
        "--duration", type=parse_duration, help="stream capture length, e.g. 10m or 30s"
    )
    capture.add_argument(
        "--trigger",
        type=parse_triggers,
        help="channel triggers, e.g. D3=r,D5=1,D0=f (types: 0 low, 1 high, r, f, e)",
    )
    capture.add_argument(
        "--edge-trigger",
        type=parse_trigger_type,
        help="trigger on the external EDGE input (0, 1, r, f, e)",
    )
    capture.add_argument("-o", "--output", help="output file, .sr or .bin")
    capture.add_argument("--progress", action="store_true", help="show a progress line")
    capture.add_argument(
        "--unsafe",
        action="store_true",
        help="skip the vendor rate/sample limits (register limits still apply)",
    )
    capture.set_defaults(func=cmd_capture)

    pwm = subparsers.add_parser("pwm", help="PWM generator")
    pwm_sub = pwm.add_subparsers(dest="pwm_command", required=True)
    pwm_set = pwm_sub.add_parser("set", help="enable PWM outputs")
    pwm_set.add_argument(
        "--freq", type=parse_frequency, required=True, help="frequency of M15/M16/M17"
    )
    pwm_set.add_argument(
        "--duty",
        type=parse_duties,
        required=True,
        help="duty cycles in percent, e.g. M15=50,M16=25",
    )
    pwm_set.add_argument(
        "--freq2",
        type=parse_frequency,
        help="frequency of M18/M19 (defaults to --freq)",
    )
    pwm_set.set_defaults(func=cmd_pwm_set)
    pwm_sub.add_parser("off", help="switch all PWM outputs off").set_defaults(
        func=cmd_pwm_off
    )

    measure = subparsers.add_parser("measure", help="PWM input frequency meter")
    measure.add_argument(
        "--range",
        default=0,
        help="measurement range: index or name "
        + ", ".join(f"{i}={r.name!r}" for i, r in enumerate(pr.PWM_INPUT_RANGES)),
    )
    measure.add_argument(
        "--interval", type=float, default=0.3, help="seconds between readings"
    )
    measure.add_argument(
        "--count", type=int, default=0, help="number of readings (0 = until Ctrl+C)"
    )
    measure.set_defaults(func=cmd_measure)
    return parser


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    if args.command == "measure" and str(args.range).isdigit():
        args.range = int(args.range)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except (CliError, DeviceError, ValueError, TimeoutError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
