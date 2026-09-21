# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""CLI argument parsing tests (no device access)."""

from __future__ import annotations

import argparse

import pytest

from rdc2la import cli
from rdc2la.protocol import SamplingMode, Trigger


@pytest.mark.parametrize(
    "text,expected",
    [
        ("100k", 100_000.0),
        ("1M", 1_000_000.0),
        ("72M", 72_000_000.0),
        ("72MHz", 72_000_000.0),
        ("100 kHz", 100_000.0),
        ("500", 500.0),
        ("1.5M", 1_500_000.0),
        ("0.5k", 500.0),
    ],
)
def test_parse_frequency(text, expected):
    assert cli.parse_frequency(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "10x", "1M2", "-5k"])
def test_parse_frequency_rejects_garbage(text):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_frequency(text)


@pytest.mark.parametrize(
    "text,expected",
    [("10k", 10_000), ("1M", 1_000_000), ("16G", 16_000_000_000), ("240000", 240_000)],
)
def test_parse_count(text, expected):
    assert cli.parse_count(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10m", 600.0),
        ("30s", 30.0),
        ("1.5h", 5_400.0),
        ("250ms", 0.25),
        ("45", 45.0),
        ("2M", 120.0),  # case insensitive: M is minutes here
        ("2x", None),
        ("", None),
    ],
)
def test_parse_duration(text, expected):
    if expected is None:
        with pytest.raises(argparse.ArgumentTypeError):
            cli.parse_duration(text)
    else:
        assert cli.parse_duration(text) == expected


def test_parse_trigger_type():
    assert cli.parse_trigger_type("0") is Trigger.LOW
    assert cli.parse_trigger_type("1") is Trigger.HIGH
    assert cli.parse_trigger_type("r") is Trigger.RISING
    assert cli.parse_trigger_type("F") is Trigger.FALLING
    assert cli.parse_trigger_type("e") is Trigger.ANY
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_trigger_type("x")


def test_parse_triggers():
    assert cli.parse_triggers("D3=r,D5=1,D0=f") == {
        3: Trigger.RISING,
        5: Trigger.HIGH,
        0: Trigger.FALLING,
    }
    assert cli.parse_triggers("31=0") == {31: Trigger.LOW}
    assert cli.parse_triggers(" d7 = e ") == {7: Trigger.ANY}


@pytest.mark.parametrize("text", ["D3", "D3=z", "X3=r", "D32=r", ""])
def test_parse_triggers_rejects_garbage(text):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_triggers(text)


def test_parse_duties():
    assert cli.parse_duties("M15=50,M16=25") == {"M15": 50.0, "M16": 25.0}
    assert cli.parse_duties("m18=12.5") == {"M18": 12.5}


@pytest.mark.parametrize("text", ["M15", "M20=50", "M15=200", "M15=x", ""])
def test_parse_duties_rejects_garbage(text):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_duties(text)


def parse(argv):
    return cli.build_parser().parse_args(argv)


def test_capture_arguments():
    args = parse(
        [
            "-p", "/dev/cu.usbmodemTEST1",
            "capture",
            "--rate", "100k",
            "--channels", "16",
            "--samples", "10k",
            "--trigger", "D3=r,D5=1",
            "--edge-trigger", "f",
            "-o", "out.sr",
            "--progress",
            "--unsafe",
        ]
    )
    assert args.port == "/dev/cu.usbmodemTEST1"
    assert args.rate == 100_000.0
    assert args.channels == 16
    assert args.samples == 10_000
    assert args.trigger == {3: Trigger.RISING, 5: Trigger.HIGH}
    assert args.edge_trigger is Trigger.FALLING
    assert args.output == "out.sr"
    assert args.progress is True
    assert args.unsafe is True
    assert args.mode == "auto"
    assert args.func is cli.cmd_capture


def test_capture_defaults():
    args = parse(["capture", "--rate", "1M"])
    assert args.channels == 8
    assert args.samples is None
    assert args.duration is None
    assert args.trigger is None
    assert args.edge_trigger is None
    assert args.verbose == 0


def test_capture_duration():
    args = parse(["capture", "--mode", "stream", "--rate", "100k", "--duration", "2m"])
    assert args.duration == 120.0
    assert args.mode == "stream"


def test_capture_rejects_unknown_channel_counts():
    with pytest.raises(SystemExit):
        parse(["capture", "--rate", "1M", "--channels", "24"])


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["capture", "--rate", "100k", "--samples", "10k"], SamplingMode.BUFFER),
        (["capture", "--rate", "100k", "--duration", "2m"], SamplingMode.STREAM),
        (["capture", "--rate", "100k", "--samples", "1M"], SamplingMode.STREAM),
        (["capture", "--rate", "108M", "--samples", "10k"], SamplingMode.STREAM),
        (["capture", "--mode", "buffer", "--rate", "100k", "--samples", "1k"], SamplingMode.BUFFER),
        (["capture", "--mode", "stream", "--rate", "100k", "--samples", "1k"], SamplingMode.STREAM),
    ],
)
def test_auto_mode_selection(argv, expected):
    assert cli._select_mode(parse(argv)) is expected


def test_auto_mode_needs_a_length():
    with pytest.raises(cli.CliError):
        cli._select_mode(parse(["capture", "--rate", "100k"]))


def test_pwm_arguments():
    args = parse(["pwm", "set", "--freq", "1k", "--duty", "M15=50,M16=25", "--freq2", "2k"])
    assert args.freq == 1_000.0
    assert args.freq2 == 2_000.0
    assert args.duty == {"M15": 50.0, "M16": 25.0}
    assert args.func is cli.cmd_pwm_set
    assert parse(["pwm", "off"]).func is cli.cmd_pwm_off


def test_simple_subcommands():
    assert parse(["ports"]).func is cli.cmd_ports
    assert parse(["id"]).func is cli.cmd_id
    assert parse(["status"]).func is cli.cmd_status
    assert parse(["reset"]).func is cli.cmd_reset
    assert parse(["measure", "--range", "1"]).range == "1"
    assert parse(["-vv", "id"]).verbose == 2


def test_missing_subcommand_exits():
    with pytest.raises(SystemExit):
        parse([])


def test_formatting_helpers():
    assert cli.format_hz(100_000) == "100 kHz"
    assert cli.format_hz(1_500_000) == "1.5 MHz"
    assert cli.format_hz(216) == "216 Hz"
    assert cli.format_seconds(0.25) == "250.00 ms"
    assert cli.format_seconds(90) == "1.50 min"
    assert cli.format_seconds(7_200) == "2.00 h"


# --------------------------------------------------------------------------
# whole-command runs against the emulated firmware
# --------------------------------------------------------------------------


def use_fake_device(monkeypatch, **kwargs) -> dict:
    """Make every CLI subcommand talk to a FakeTransport instead of a port."""
    from rdc2la.device import Device
    from rdc2la.transport import FakeTransport

    holder: dict = {}

    def fake_open(args):
        fake = FakeTransport(**kwargs)
        holder["fake"] = fake
        return Device.open(transport=fake)

    monkeypatch.setattr(cli, "_open_device", fake_open)
    return holder


def read_sr_metadata(path):
    import configparser
    import zipfile

    with zipfile.ZipFile(path) as archive:
        parser = configparser.ConfigParser()
        parser.read_string(archive.read("metadata").decode())
        chunks = [n for n in archive.namelist() if n.startswith("logic-1-")]
        size = sum(archive.getinfo(name).file_size for name in chunks)
    return parser, chunks, size


def test_cli_id_and_status(monkeypatch, capsys):
    use_fake_device(monkeypatch, status_polls=1)
    assert cli.main(["id"]) == 0
    out = capsys.readouterr().out
    assert "controller id:     5" in out
    assert "firmware version:  0.2" in out
    assert cli.main(["status"]) == 0
    assert "sampling complete" in capsys.readouterr().out


def test_cli_buffer_capture_writes_sr(tmp_path, monkeypatch, capsys):
    use_fake_device(monkeypatch, status_polls=1)
    out = tmp_path / "test.sr"
    rc = cli.main(
        ["capture", "--rate", "100k", "--channels", "8", "--samples", "10k", "-o", str(out)]
    )
    assert rc == 0
    metadata, chunks, size = read_sr_metadata(out)
    assert metadata["device 1"]["samplerate"] == "100000 Hz"
    assert metadata["device 1"]["unitsize"] == "1"
    assert chunks == ["logic-1-1"]
    assert size == 10_000
    printed = capsys.readouterr().out
    assert "10000 samples" in printed
    assert str(out) in printed


def test_cli_stream_capture_writes_sr(tmp_path, monkeypatch, capsys):
    use_fake_device(monkeypatch)
    out = tmp_path / "ot.sr"
    rc = cli.main(
        [
            "capture", "--mode", "stream", "--rate", "100k", "--channels", "8",
            "--duration", "2s", "-o", str(out),
        ]
    )
    assert rc == 0
    _, _, size = read_sr_metadata(out)
    assert size == 200_000  # exactly the requested 2 s at 100 kHz
    captured = capsys.readouterr()
    assert "13 packets read" in captured.out
    assert "stopped by user" not in captured.err  # the target was reached


def test_cli_stream_capture_truncates_after_an_overflow(tmp_path, monkeypatch, capsys):
    use_fake_device(monkeypatch, stream_valid_packets=2)
    out = tmp_path / "overflow.bin"
    rc = cli.main(
        [
            "capture", "--mode", "stream", "--rate", "100k", "--samples", "65536",
            "-o", str(out),
        ]
    )
    assert rc == 0
    assert out.stat().st_size == 2 * 16_384
    captured = capsys.readouterr()
    assert "overflow" in captured.err
    assert "truncated" in captured.out


def test_cli_reports_a_different_actual_rate(monkeypatch, capsys):
    use_fake_device(monkeypatch, status_polls=1)
    assert cli.main(["capture", "--rate", "7M", "--samples", "1k"]) == 0
    assert "device runs at" in capsys.readouterr().err


def test_cli_rejects_vendor_limits_and_accepts_unsafe(monkeypatch, capsys):
    use_fake_device(monkeypatch, status_polls=1)
    assert cli.main(["capture", "--rate", "36M", "--channels", "32", "--samples", "1k"]) == 1
    assert "error:" in capsys.readouterr().err
    assert cli.main(
        ["capture", "--rate", "36M", "--channels", "32", "--samples", "1k", "--unsafe"]
    ) == 0


def test_cli_pwm_and_measure(monkeypatch, capsys):
    holder = use_fake_device(monkeypatch, pwm_input_ticks=(600, 300))
    assert cli.main(["pwm", "set", "--freq", "1k", "--duty", "M15=50,M16=25"]) == 0
    out = capsys.readouterr().out
    assert "PWM1: 1 kHz" in out and "M15=50 %" in out and "M16=25 %" in out
    assert holder["fake"].pwm_packets[-1][3] == 0b011
    assert cli.main(["pwm", "off"]) == 0
    assert holder["fake"].pwm_packets[-1][3] == 0
    assert cli.main(["measure", "--range", "0", "--count", "2", "--interval", "0"]) == 0
    assert "duty=50.08 %" in capsys.readouterr().out


def test_cli_reset(monkeypatch, capsys):
    use_fake_device(monkeypatch)
    assert cli.main(["reset"]) == 0
    assert "device stopped" in capsys.readouterr().out


def test_cli_ports_lists_both_transports(monkeypatch, capsys):
    from rdc2la.device import Device

    monkeypatch.setattr(Device, "find_ports", staticmethod(lambda: ["COM7"]))
    monkeypatch.setattr(Device, "find_usb", staticmethod(lambda: ["usb:1.4"]))
    assert cli.main(["ports"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "COM7  (serial)",
        "usb:1.4  (libusb)",
    ]


def test_cli_ports_without_a_device(monkeypatch, capsys):
    from rdc2la.device import Device

    monkeypatch.setattr(Device, "find_ports", staticmethod(lambda: []))
    monkeypatch.setattr(Device, "find_usb", staticmethod(lambda: []))
    assert cli.main(["ports"]) == 1
    assert "serial port or via libusb" in capsys.readouterr().out


def test_cli_port_option_takes_a_usb_selector():
    assert parse(["-p", "usb:1.4", "id"]).port == "usb:1.4"
    assert "usb[:bus.address]" in cli.build_parser().format_help()
