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
| `scripts/` | Build script for the sigrok stack on macOS, PulseView app bundle, hardware self-test |
| `third_party/chipdip/` | Vendor sources (Apache-2.0), kept for reference |

## Status

Verified on hardware (firmware 0.2, macOS 26, Apple silicon) with the
board's own PWM outputs looped back into its inputs:

* `rdc2la` — buffer and stream capture on 8/16/32 channels, channel
  triggers (level, edge, combined), the EDGE trigger input, PWM generator,
  frequency meter on M20, `.sr` output readable by sigrok-cli/PulseView.
* libsigrok driver — scan, buffer and stream capture, channel and EDGE
  triggers, through sigrok-cli and PulseView built by `scripts/build-macos.sh`.
* PulseView — capture, stop, repeated runs, closing releases the port
  (with the two patches from `scripts/patches/`).

`scripts/hw-selftest.py` reruns this verification in a few minutes.

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

# PulseView as a macOS app (/Applications/PulseView.app, launcher only)
scripts/install-app.sh
```

## Device limits

The driver and `rdc2la` enforce the limits of the vendor software:

| Channels | Buffer: max rate | Buffer: max samples | Stream: max rate |
|---|---|---|---|
| 8 | 72 MHz (108 MHz, see below) | 240 000 (30 000 at 108 MHz) | 18 MHz |
| 16 | 72 MHz | 120 000 | 8 MHz |
| 32 | 24 MHz | 60 000 | 4 MHz |

Anything the sample memory cannot hold is streamed over USB. With the
*Auto* data source the driver picks the mode itself: at or below the
stream rate limit any sample count works, above it the capture is a
buffer capture and the count is capped at the memory size. PulseView and
sigrok-cli read these limits from the driver (`limit_samples` range and
the samplerate list), so a rate or count that cannot work is not offered.
PulseView refreshes both lists when the samplerate or count changes, not
when channels are toggled — reselect the samplerate after changing the
channel set.

Things to know:

* **108 MHz is experimental**, as the vendor says; both tools warn. On the
  board used for testing the DMA occasionally lost a request at that preset
  and also with 16 channels at 72 MHz, corrupting the rest of the capture,
  while 8 channels at 72 MHz, 16 at 54 MHz and 32 at 24 MHz were always
  clean. This may be specific to that unit; see `docs/protocol.md` 7.3.
* **Stream throughput depends on the USB path.** Through a USB 2.0 hub shared
  with other devices this board sustained about 12 MB/s (8 channels at
  12 MHz) before the firmware reported an overflow; the vendor limits assume
  an otherwise idle bus. The overflow is reported and the capture truncated
  to the valid part.
* For long continuous captures with sigrok-cli use `-O binary`; the srzip
  writer rewrites the archive on every chunk and falls behind the device.
* In sigrok-cli use a comma-separated channel list (`--channels D0,D1,D2`);
  ranges like `D0-D7` are not parsed for non-numeric channel names.

## Hardware self-test

```sh
python/.venv/bin/python scripts/hw-selftest.py [--edge] [--meter]
```

Needs jumpers M15 → D0 and M16 → D1 (or M16 → EDGE with `--edge`) and,
for the frequency meter, M17 → M20 with `--meter`. Exercises buffer and
stream captures at several rates and channel counts, all trigger types,
the EDGE input, the meter and sigrok-cli, and checks that each capture
contains exactly the generated PWM signal.

## License

Apache-2.0, except `sigrok/` which is GPL-3.0-or-later. Details in
[NOTICE](NOTICE).
