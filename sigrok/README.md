# libsigrok driver `chipdip-rdc2-0064`

Hardware driver for the ChipDip RDC2-0064 logic analyzer (32 channels, up to
72 MHz, USB CDC-ACM). GPL-3.0-or-later, see `LICENSE`. The protocol is
documented in `../docs/protocol.md`.

## Apply to a libsigrok checkout

```sh
git clone https://github.com/sigrokproject/libsigrok.git
./apply.sh /path/to/libsigrok        # copies the driver, patches the build
cd /path/to/libsigrok
./autogen.sh && ./configure --enable-chipdip-rdc2-0064
make && sudo make install
```

`apply.sh` copies `chipdip-rdc2-0064/` into `src/hardware/` and registers the
driver in `Makefile.am` and `configure.ac` (via `libsigrok-build.patch`, or by
anchor insertion when that patch does not apply). Re-running it is safe.
`UPSTREAM.txt` records the libsigrok commit the driver was built against.

The driver needs libserialport and read/write access to the device node
(`/dev/ttyACM*` on Linux, `/dev/cu.usbmodem*` on macOS). No udev rule or
firmware upload is required.
