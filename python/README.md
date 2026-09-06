# rdc2la

Python library and CLI for the **ChipDip RDC2-0064** logic analyzer
(32 channels, STM32F722, USB CDC-ACM) on macOS and Linux. No vendor driver
is needed: the device shows up as `/dev/cu.usbmodem*` / `/dev/ttyACM*`.

Captures are written as sigrok session files (`.sr`, readable by
sigrok-cli and PulseView) or as raw `.bin` sample dumps.
The protocol is documented in [`../docs/protocol.md`](../docs/protocol.md).

## Install

```sh
cd python
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'      # drop [dev] if you do not need pytest
.venv/bin/pytest -q                    # tests run against a fake device
```

Requires Python 3.11+ and pyserial 3.5+. The `rdc2la` command is installed
into the environment.

## Examples

```sh
# which devices are connected
rdc2la ports

# identify the device (controller id, firmware and hardware version)
rdc2la id

# 10 000 samples at 100 kHz on 8 channels into a sigrok session file
rdc2la capture --rate 100k --channels 8 --samples 10k -o test.sr

# same capture, started by a rising edge on D3 while D5 is high
rdc2la capture --rate 100k --samples 10k --trigger D3=r,D5=1 -o trig.sr

# 2 minute stream capture at 100 kHz, written while it runs (Ctrl+C keeps the data)
rdc2la capture --mode stream --rate 100k --channels 8 --duration 2m -o ot.sr --progress

# fast buffer capture on all 32 channels, raw output
rdc2la capture --rate 24M --channels 32 --samples 60k -o wide.bin

# 1 kHz / 50 % square wave on M15, and switching the generator off again
rdc2la pwm set --freq 1k --duty M15=50
rdc2la pwm off

# frequency meter on the PWM input (M20), 100 Hz - 4 kHz range
rdc2la measure --range 1

# stop a capture left running by a previous session, dump every USB packet
rdc2la -vv reset
```

Sample rates accept `100k`, `1M`, `72M`; sample counts accept `10k`, `1M`;
durations accept `30s`, `10m`, `1.5h`. `--unsafe` lifts the vendor rate and
sample-count limits (register limits still apply). If the requested rate is
not reachable exactly, the actual rate is printed and stored in the file.

## Library

```python
from rdc2la import Device

with Device.open() as device:                       # or Device.open("/dev/cu.usbmodem...")
    result = device.capture_buffer(100_000, 8, 10_000)
    print(result.sample_count, result.rate, len(result.data))

    with device.capture_stream(100_000, 8, duration=120) as capture:
        for chunk in capture:                       # decoded samples, 16 KiB each
            ...
    print(capture.summary.valid_samples, capture.summary.overflow)
```
