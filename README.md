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

Work in progress. See the sections above for what already works.

## License

Apache-2.0, except `sigrok/` which is GPL-3.0-or-later. Details in
[NOTICE](NOTICE).
