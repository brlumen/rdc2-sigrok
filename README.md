# OpenLA — RDC2-0064 on macOS and Linux

Open-source host software for the **ChipDip RDC2-0064** logic analyzer
(32 channels, 72 MHz, STM32F722, USB CDC-ACM). The vendor ships a
Windows-only application; this project makes the device usable natively on
macOS and Linux and integrates it with [sigrok](https://sigrok.org)
(sigrok-cli / PulseView).

Original device and vendor project: https://www.chipdip.ru/product/rdc2-0064-logic-analyzer
— firmware and application sources were released by ChipDip under the
Apache License 2.0; see [NOTICE](NOTICE).

## Layout

| Path | What |
|---|---|
| `docs/protocol.md` | Complete USB protocol description (commands, timing, data layout, firmware quirks) |
| `python/` | `rdc2la` — Python library and CLI: capture to `.sr`/`.bin`, PWM generator, frequency meter |
| `sigrok/` | libsigrok hardware driver `chipdip-rdc2-0064` (GPL-3.0-or-later) |
| `scripts/` | Build script for the sigrok stack with this driver on macOS |
| `third_party/chipdip/` | Vendor sources (Apache-2.0), kept for reference |

## Status

Verified on hardware (firmware 0.2, macOS 26, Apple silicon):

* `rdc2la` — buffer and stream capture, triggers, PWM generator, `.sr` output
  readable by sigrok-cli/PulseView.
* libsigrok driver — scan, buffer and stream capture, channel triggers,
  through sigrok-cli and PulseView built by `scripts/build-macos.sh`.

## Quick start

```sh
# Python tool
cd python && python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/rdc2la id
.venv/bin/rdc2la capture --mode stream --rate 100k --channels 8 --duration 10m -o capture.sr

# sigrok stack with the driver (installs into ~/.local/openla)
scripts/build-macos.sh
. scripts/env.sh
sigrok-cli --driver chipdip-rdc2-0064 --scan
sigrok-cli --driver chipdip-rdc2-0064 -c samplerate=100k --channels D0,D1,D2,D3,D4,D5,D6,D7 --samples 10000 -O srzip -o test.sr
pulseview
```

Notes for PulseView: start it as `pulseview -d chipdip-rdc2-0064` and the
device is connected automatically. While it is connected the serial port is
held exclusively, so "Scan for devices" in the *Connect to Device* dialog
reports nothing ("Resource busy" in the log) and removes the device from the
toolbar list — do not rescan; the device is already selected in the toolbar.
Closing the session tab does not release the port either: quit PulseView and
start it again if the device is gone from the list. In sigrok-cli use a comma-separated channel
list (`--channels D0,D1,D2`); ranges like `D0-D7` are not parsed for
non-numeric channel names.

## License

Apache-2.0, except `sigrok/` which is GPL-3.0-or-later. Details in
[NOTICE](NOTICE).
