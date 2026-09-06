# RDC2-0064 USB protocol

Reverse-engineered from the vendor sources published by ChipDip under the
Apache License 2.0 (see `third_party/chipdip/`), cross-checked against
the device (firmware v0.2, hardware v0.1). Byte offsets below are absolute
offsets inside a packet unless stated otherwise. All multi-byte integers
are little-endian.

## 1. Hardware summary

| Item | Value |
|---|---|
| MCU | STM32F722 @ 216 MHz, external USB HS PHY (ULPI) |
| USB | 2.0 High Speed, VID `0x0483`, PID `0xA210`, product `RDC2-0064 in HS Mode`, manufacturer `ChipDip` |
| USB class | CDC-ACM (composite: iface 0 = CDC control, iface 1 = CDC data, bulk IN 512 / bulk OUT 64) — built on STM32Cube `CDC_Standalone` |
| Inputs | 32 logic channels, 2–5 V logic, ESD-protected |
| Channels 0–15 | GPIOE0..15, sampled by TIM1 + DMA2 |
| Channels 16–31 | GPIOD0..15, sampled by TIM8 + DMA2 |
| EDGE input | PA1 (TIM2_CH2): external gate/trigger for the whole capture |
| CLK input | PA0: not implemented in firmware v0.2 |
| PWM outputs | M15=PC8, M16=PC7, M17=PC6 (TIM3); M18=PB15, M19=PB14 (TIM12) |
| PWM input | M20=PA2 (TIM9_CH1), input-capture (period + high time) |
| LED | PA6: solid = idle; blinking = awaiting trigger / sampling |
| Sample memory | 240 640 bytes (`LA_DATA_BUF_SIZE` = 512 × 470) |

On macOS/Linux the device binds to the stock CDC-ACM driver and appears as
`/dev/cu.usbmodem<serial>1` / `/dev/ttyACM0`. No vendor driver is needed:
the Windows package merely swaps the CDC driver for libusb0 and talks to
the very same bulk endpoints. Line coding, DTR and RTS are ignored by the
firmware.

## 2. Transport rules

1. **Host → device packets are exactly 64 bytes** (`USB_Rx_LENGTH`). The
   firmware treats every received bulk OUT packet as one command and copies
   64 bytes out of it. Always write the full 64-byte, zero-padded packet in a
   single `write()`.
2. **Device → host replies are 512 bytes** (`USB_Tx_LENGTH`), except
   `LA_CMD_GET_SAMPLES` (240 640 bytes in buffer mode, 16 384 bytes in
   stream mode). Transfers that are a multiple of 512 are terminated with a
   zero-length packet; it is invisible through a tty and harmless via libusb.
3. **Strict request/response.** Never send a command while a reply is still
   in flight. `SYS_*` commands are answered from the USB interrupt handler,
   which spins until the previous transmit completes; issuing one in the
   middle of a large transfer deadlocks the firmware until power-cycle.
4. The firmware never sends unsolicited data.
5. Commands that produce **no reply**: `LA_CMD_CONFIG`, `MODULE_PWM`
   (any cmd), `PWM_INPUT_CMD_CONFIG`, `PWM_INPUT_CMD_STOP`.
6. Commands are handled by two different contexts:
   * `MODULE_SYSTEM` — inside the USB receive interrupt (always serviced,
     even while the main loop is busy).
   * `MODULE_LA` / `MODULE_PWM` / `MODULE_PWM_INPUT` — from the main loop,
     which is single-threaded and may be blocked (see §7).

## 3. Packet header

| Offset | Name | Meaning |
|---|---|---|
| 0 | `MODULE_ID` | 0 = SYSTEM, 1 = LA, 2 = PWM, 3 = PWM_INPUT |
| 1 | `CMD` | command inside the module |
| 2 | `SUBCMD` | unused, send 0 |
| 3.. | `DATA` | command-specific payload |

Replies to `SYS_*` commands echo bytes 0..2 and put data from offset 3.

## 4. MODULE_SYSTEM (0)

### 4.1 `SYS_CMD_GET_ID` (cmd = 4) → 512-byte reply

| Offset | Meaning |
|---|---|
| 3 | controller id, always **5** (`RDC2_0064_ID`) |
| 4..7 | firmware version bytes (v0.2 → `00 02 00 00`) |
| 8..9 | memory size (0 in firmware v0.2) |
| 10 | hardware version (1) |

Side effect: LED switches to solid on. Use id == 5 to identify the device.

### 4.2 `SYS_CMD_GET_STATUS` (cmd = 5) → 512-byte reply

| Offset | Meaning |
|---|---|
| 3 | status bits: bit0 `LA_TRIGGER_AWAIT` (never set by fw 0.2), bit1 `LA_SAMPLING_CMP` (buffer capture finished) |
| 4..5 | `NDTR` of the update-DMA stream = remaining transfers (progress indicator while sampling) |

`LA_SAMPLING_CMP` is cleared by `LA_CMD_CONFIG` and set by the DMA
transfer-complete interrupt in buffer mode. It is only meaningful in buffer
mode. See §7 for when it is safe to poll.

## 5. MODULE_LA (1)

| cmd | Name | Reply |
|---|---|---|
| 0 | `LA_CMD_CONFIG` | none — configures and immediately starts sampling (or arms the trigger) |
| 1 | `LA_CMD_GET_SAMPLES` | buffer mode: the whole 240 640-byte buffer; stream mode: one 16 384-byte packet (blocks until ready) |
| 2 | `LA_CMD_SAMPLE_STOP` | 512 bytes: `[0]` = stream overflow flag, `[1..4]` = number of valid 16 384-byte stream packets (u32) |

### 5.1 `LA_CMD_CONFIG` payload (64-byte packet)

| Offset | Size | Field | Notes |
|---|---|---|---|
| 3 | 1 | sampling mode | 0 = buffer, 1 = stream |
| 4 | 1 | channel count | 8, 16 or 32 (24 exists but is broken, see §6.4) |
| 5 | 4 | sample count | buffer mode: total samples, must be divisible by the DMA stream count; ignored in stream mode |
| 9 | 1 | sample clock source | 0 = internal timer. Values for EDGE/CLK clocking are reserved and unused by fw 0.2 |
| 10 | 1 | PLL reconfigure flag | unused by fw 0.2, send 0 |
| 11 | 1 | PLL M | unused, 0 |
| 12 | 2 | PLL N | unused, 0 |
| 14 | 1 | PLL P | unused, 0 |
| 15 | 2 | `TIM_PSC` | timer prescaler **register** value (= divider − 1) |
| 17 | 2 | `ARR1` | timer period per DMA stream (see §5.2) |
| 19 | 1 | DMA stream count | 1, 4 or 5 (see §5.2) |
| 20 | 1 | channel triggers active | 0 / 1 |
| 21 | 2 | trigger timer PSC | unused by fw 0.2 |
| 23 | 2 | trigger timer ARR | unused by fw 0.2 |
| 25 | 32 | per-channel trigger | one byte per channel 0..31, values from §5.4 |
| 57 | 1 | EDGE-input trigger | values from §5.4, applies to the external EDGE pin |
| 58..63 | 6 | padding | 0 |

### 5.2 Sample clock

TIM1 (channels 0–15) and TIM8 (16–31) are clocked at **216 MHz**.
With `N` DMA streams the firmware programs

    PSC_reg = TIM_PSC                     (divider = PSC_reg + 1)
    ARR_reg = ARR1 * N - 1
    CCRk    = ARR1 * k        for k = 1 .. N-1   (extra DMA requests)

so every timer period generates `N` DMA requests and the effective sample
rate is

    f_sample = 216 000 000 / (PSC_reg + 1) / ARR1

Multiple DMA streams exist because a single stream cannot sustain more than
~36 MHz; each stream writes its own contiguous region (see §6.1). The vendor
software chooses `N` as follows (buffer mode only; stream mode always uses
`N = 1`):

    streams_by_count = ceil(sample_count / 65000)   (NDTR is 16-bit)
    streams_by_rate  = 1 if f <= 36 MHz, 4 if f <= 72 MHz, 5 for 108 MHz
    N = max(streams_by_count, streams_by_rate); if N in (2, 3): N = 4

Vendor presets (`SampleTimerPSC` is the divider, i.e. register value + 1):

| Rate | divider | ARR1 | Rate | divider | ARR1 | Rate | divider | ARR1 |
|---|---|---|---|---|---|---|---|---|
| 10 kHz | 10800 | 2 | 1 MHz | 108 | 2 | 24 MHz | 3 | 3 |
| 20 kHz | 5400 | 2 | 2 MHz | 54 | 2 | 36 MHz | 3 | 2 |
| 50 kHz | 2160 | 2 | 4 MHz | 27 | 2 | 54 MHz | 2 | 2 |
| 100 kHz | 1080 | 2 | 8 MHz | 9 | 3 | 72 MHz | 1 | 3 |
| 200 kHz | 540 | 2 | 12 MHz | 9 | 2 | 108 MHz | 2 | 1 (N = 5) |
| 500 kHz | 216 | 2 | 18 MHz | 6 | 2 | | | |

Any other rate that satisfies the formula (with `ARR1 >= 1`, 16-bit
registers) should work as well; only the presets are vendor-tested.

### 5.3 Limits enforced by the vendor software

Buffer mode:

| Channels | Max rate | Max samples | Notes |
|---|---|---|---|
| 8 | 72 MHz (108 MHz*) | 240 000 (30 000 at 108 MHz) | 1 byte/sample |
| 16 | 72 MHz | 120 000 | 2 bytes/sample |
| 32 | 24 MHz | 60 000 | 4 bytes/sample |

Stream mode (sample count is a host-side limit, up to 16 × 10⁹):

| Channels | Max rate |
|---|---|
| 8 | 18 MHz |
| 16 | 8 MHz |
| 32 | 4 MHz |

Vendor note: in practice the USB link sustains ~24 MB/s without loss only
on an otherwise idle bus; above that the overflow flag (§5.5) is set.
Vendor sample-count presets: buffer 1k, 2k, 5k, 10k, 20k, 30k, 60k, 120k,
160k, 240k; stream 1M … 16G.

### 5.4 Triggers

Trigger type values (per channel and for the EDGE input):

| Value | Name |
|---|---|
| 0 | none |
| 1 | low level |
| 2 | high level |
| 3 | rising edge |
| 4 | falling edge |
| 5 | any edge |

Per-channel triggers (offset 25, enabled by byte 20):

* Channels 0–15 support all types (edges via EXTI lines 0–15).
* Channels 16–31 support **level only**; edge values are silently ignored.
* The capture starts when **all** configured edge channels have seen their
  edge (EXTI pending flags accumulate, so the edges need not be simultaneous)
  **and** all level conditions are true at that moment.
* If only level triggers are configured, the firmware busy-waits in its main
  loop polling the GPIOs until the condition is met (see §7).
* There is no pre-trigger data: sampling starts at the trigger.

EDGE-input trigger (offset 57): controls TIM2, which is master to TIM1/TIM8.

* rising / falling / any edge — sampling starts on that edge of the EDGE pin.
* low / high level — **gated** sampling: samples are taken only while the
  EDGE pin is at that level (timer runs in gated slave mode).

Both trigger kinds may be combined. With 24/32 channels TIM2 is also used
(without a trigger) to start TIM1 and TIM8 synchronously.

### 5.5 Stream mode internals

The DMA runs in double-buffer mode over a 229 376-byte ring (14 packets of
16 384 bytes). Each completed 16 384-byte half raises `StreamPackReady`.
`LA_CMD_GET_SAMPLES` blocks in the main loop until a packet is ready, then
transmits it and advances the read pointer by one packet. If the write
pointer catches up with the read pointer the overflow flag is set and the
valid-packet counter stops incrementing; everything read after that point is
unreliable. `LA_CMD_SAMPLE_STOP` stops the timers/DMA and reports
`[0]` = overflow flag, `[1..4]` = valid packet count.

Per-packet time is `16384 / (f_sample × bytes_per_sample)` seconds — at
10 kHz with 8 channels a packet takes 1.64 s, so read timeouts must be
computed from the configured rate.

## 6. Sample data layout

Bit `n` of a sample word is channel `n`; sample words are little-endian.
Sample size is 1 byte (8 channels), 2 bytes (16) or 4 bytes (32). This is
exactly the sigrok logic format with `unitsize` 1/2/4.

### 6.1 Buffer mode

`LA_CMD_GET_SAMPLES` always returns the entire 240 640-byte buffer
regardless of the requested sample count. The buffer is organised in
**parts**:

    bps       = 1 (8 ch) or 2 (16/32 ch)      # bytes written per DMA transfer
    part_size = (sample_count / N) * bps       # bytes
    part k (k = 0..N-1)  at offset k * part_size : channels 0-15, samples k, k+N, k+2N, ...
    part N (32 ch only)  at offset N * part_size : channels 16-31, 2 bytes/sample, N is 1 here

De-interleaving (equivalent to the vendor `RearrangeSamples`):

    for i in range(sample_count // N):
        for k in range(N):            out += part[k][i*bps : (i+1)*bps]
        if channels == 32:            out += part[N][i*2 : (i+1)*2]

With `N == 1` and ≤ 16 channels the data is already contiguous.

### 6.2 Stream mode

Every packet is 16 384 bytes:

| Channels | Content |
|---|---|
| 8 | 16 384 samples, 1 byte each |
| 16 | 8 192 samples, u16 each |
| 32 | bytes 0..8191: 4 096 × u16 for channels 0–15; bytes 8192..16383: 4 096 × u16 for channels 16–31 — interleave into 4 096 × u32 |

Total valid samples after stop = `valid_packets × 16384 / bytes_per_sample`.

### 6.3 Progress

`SYS_CMD_GET_STATUS` bytes 4..5 hold the remaining transfer count of the
last DMA stream (`sample_count / N` counting down to 0).

### 6.4 24-channel mode

With channel count 24 the firmware programs both DMAs for 8-bit transfers:
channels 0–7 land in part 0 and channels 16–23 in part 1, and the vendor
software does not rearrange them. Treat 24 as unsupported and use 32.

## 7. Capture sequences and firmware quirks

### 7.1 Buffer capture

    CONFIG(mode=0, ...)                 # no reply; LED starts blinking
    repeat every ~100 ms:
        GET_STATUS  -> if bit1 set: break; else bytes 4..5 = progress
    GET_SAMPLES -> read 240 640 bytes
    de-interleave (§6.1), keep sample_count samples

Cancelling: `SAMPLE_STOP` → read the 512-byte reply → the device is idle.
The 5 bytes at the start of the sample buffer are overwritten by the reply.

### 7.2 Stream capture

    CONFIG(mode=1, ...)                 # no reply
    loop:
        GET_SAMPLES -> read 16 384 bytes (timeout >= packet time + margin)
        stop when enough samples were collected or on user request
    SAMPLE_STOP -> read 512 bytes: overflow flag, valid packet count

Do **not** poll `GET_STATUS` during a stream capture: a reply may be in
flight and rule §2.3 applies.

### 7.3 Known firmware behaviour to design around

* `GET_SAMPLES` in stream mode when no stream is running blocks the main
  loop forever (`while (StreamPackReady == 0)`); only a power-cycle recovers.
  Never send it unless a stream capture is active.
* The USB receive interrupt copies every command into a **single slot**
  (`USBDataBuf`) that the main loop picks up later; there is no queue. A
  command that arrives before the previous one was consumed overwrites it.
  In practice this bites `CONFIG` followed immediately by `GET_SAMPLES` in
  stream mode: `CONFIG` is lost, `GET_SAMPLES` runs in the previous mode and
  the firmware ends up stuck as in the first bullet. Wait ≥ 10 ms after
  `CONFIG` (or until the write has physically drained, e.g. `tcdrain`)
  before sending the next command.
* With level-only channel triggers the main loop busy-waits, so
  `SAMPLE_STOP` is not processed until the trigger fires. `GET_STATUS` still
  works. Edge triggers do not have this problem.
* Sending `CONFIG` while a capture is running is undefined; always stop
  first.
* Recommended open sequence: send `SAMPLE_STOP`, then read whatever arrives
  within ~2 s and discard it (an unfinished stream packet of 16 384 bytes may
  precede the 512-byte reply), then `GET_ID`. If nothing arrives the firmware
  is stuck (see the first bullet) — ask the user to replug the device.
* The vendor application sends a 1-byte read after every reply to consume
  the zero-length packet; unnecessary over a tty.
* `LA_TRIGGER_AWAIT` in the status word is never set; the vendor software
  detects "waiting for trigger" only through the progress counter not moving.

## 8. MODULE_PWM (2) — generator

Any `CMD` value. Both timers are reconfigured by one packet; a zero channel
mask stops that timer (outputs low). Timer clock is **108 MHz**.

| Offset | Size | Field |
|---|---|---|
| 3 | 1 | PWM1 (TIM3) enable mask, 0 = off |
| 4 | 2 | PWM1 `PSC` register |
| 6 | 2 | PWM1 `ARR` register |
| 8 | 2 | CCR for M15 |
| 10 | 2 | CCR for M16 |
| 12 | 2 | CCR for M17 |
| 14 | 1 | PWM2 (TIM12) enable mask, 0 = off |
| 15 | 2 | PWM2 `PSC` register |
| 17 | 2 | PWM2 `ARR` register |
| 19 | 2 | CCR for M18 |
| 21 | 2 | CCR for M19 |

    f_pwm = 108e6 / (PSC + 1) / (ARR + 1);   duty = CCR / (ARR + 1)

Vendor range 0.03 Hz … 27 MHz; all three (two) outputs of a timer share the
frequency and differ only in duty cycle. No reply.

## 9. MODULE_PWM_INPUT (3) — frequency / duty meter

| cmd | Name | Payload / reply |
|---|---|---|
| 0 | `CONFIG` | offset 3..4 = `PSC` register of the capture timer (base clock and ranges: see `third_party/chipdip/software-v0.2/Measurements.xaml.cs`); no reply |
| 1 | `GET_DATA` | 512-byte reply: `[0..1]` period in timer ticks, `[2..3]` high time in ticks; both 0 until the first full period was captured |
| 2 | `STOP` | no reply |

The timer runs in PWM-input mode with `ARR = 0xFFFF` (reset on each rising
edge); periods longer than 65 535 ticks overflow — pick `PSC` accordingly.

## 10. References

* `third_party/chipdip/firmware-v0.2/Inc/USBPtorocol.h` — vendor protocol header (the file name typo is the vendor's).
* `third_party/chipdip/firmware-v0.2/Src/LogicAnalyzer.c`, `LogicAnalyzerTriggers.c`, `USBPort.c` — firmware behaviour.
* `third_party/chipdip/software-v0.2/USBDriver.cs`, `LogicAnalyzer.xaml.cs` — host-side sequences, rate tables, limits, `RearrangeSamples`.
* Vendor thread with the source drops and answers: https://forum.chipstudio.ru/index.php?threads/rdc2-0064-logicheskij-analizator-32-kanala-max-72-mgc-max.149/
