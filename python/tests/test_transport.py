# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Transport tests.

The serial transport is exercised against a stub ``serial.Serial`` object and
the USB transport against a stub ``usb`` package; no real port and no real USB
device is ever opened.
"""

from __future__ import annotations

import logging
import sys
import time
import types
from array import array

import pytest
import serial

from rdc2la import protocol as pr
from rdc2la.transport import (
    FakeTransport,
    LoggingTransport,
    SerialTransport,
    UsbTransport,
    find_usb_devices,
    is_usb_port,
    usb_selector,
)


class StubSerial:
    """Just enough of pyserial's Serial for the transport tests."""

    instances: list["StubSerial"] = []

    def __init__(self, port, **kwargs):
        if "exclusive" not in kwargs:
            raise AssertionError("SerialTransport must ask for an exclusive open")
        self.port = port
        self.kwargs = kwargs
        self.timeout = kwargs.get("timeout")
        self.writes: list[bytes] = []
        self.chunks: list[bytes] = []
        self.flushed = 0
        self.closed = False
        self.short_write = False
        StubSerial.instances.append(self)

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data) - 1 if self.short_write else len(data)

    def flush(self):
        self.flushed += 1

    def read(self, size):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        return chunk[:size]

    def close(self):
        self.closed = True


@pytest.fixture
def stub_serial(monkeypatch):
    StubSerial.instances.clear()
    monkeypatch.setattr(serial, "Serial", StubSerial)
    return StubSerial


def test_serial_transport_writes_one_full_packet(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    packet = pr.build_get_id()
    transport.write_packet(packet)
    stub = stub_serial.instances[-1]
    assert stub.writes == [packet]  # exactly one write of 64 bytes
    assert stub.flushed == 1
    assert stub.kwargs["rtscts"] is False


def test_serial_transport_rejects_wrong_packet_sizes(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    with pytest.raises(ValueError, match="64 bytes"):
        transport.write_packet(b"\x00" * 63)


def test_serial_transport_detects_a_short_write(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    stub_serial.instances[-1].short_write = True
    with pytest.raises(OSError, match="short write"):
        transport.write_packet(pr.build_get_id())


def test_serial_transport_read_exact_assembles_chunks(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    stub = stub_serial.instances[-1]
    stub.chunks = [b"a" * 100, b"b" * 300, b"c" * 112]
    assert transport.read_exact(512, 1.0) == b"a" * 100 + b"b" * 300 + b"c" * 112


def test_serial_transport_read_exact_times_out(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    stub_serial.instances[-1].chunks = [b"x" * 10]
    with pytest.raises(TimeoutError, match="10 of 512 bytes"):
        transport.read_exact(512, 0.05)


def test_serial_transport_drain_returns_pending_bytes(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    stub_serial.instances[-1].chunks = [b"1" * 512, b"2" * 16]
    assert transport.drain(1.0, quiet=0.01) == b"1" * 512 + b"2" * 16


def test_serial_transport_drain_returns_nothing_when_silent(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    assert transport.drain(0.05, quiet=0.01) == b""


def test_serial_transport_close(stub_serial):
    transport = SerialTransport("/dev/null-not-opened")
    transport.close()
    assert stub_serial.instances[-1].closed


def test_serial_transport_falls_back_without_exclusive(monkeypatch):
    created = []

    class NoExclusive(StubSerial):
        def __init__(self, port, **kwargs):
            if "exclusive" in kwargs:
                raise TypeError("unexpected keyword argument 'exclusive'")
            kwargs["exclusive"] = None
            super().__init__(port, **kwargs)
            created.append(self)

    monkeypatch.setattr(serial, "Serial", NoExclusive)
    SerialTransport("/dev/null-not-opened")
    assert len(created) == 1


# --------------------------------------------------------------------------
# libusb transport (pyusb is stubbed, no device is ever opened)
# --------------------------------------------------------------------------


class StubUSBError(Exception):
    """Stand-in for ``usb.core.USBError``."""


class StubUSBTimeoutError(StubUSBError):
    """Stand-in for ``usb.core.USBTimeoutError``."""


class StubNoBackendError(ValueError):
    """Stand-in for ``usb.core.NoBackendError``."""


class StubUsbDevice:
    """Just enough of a ``usb.core.Device`` for the transport tests."""

    def __init__(self, bus: int = 1, address: int = 4, kernel_driver=False) -> None:
        self.bus = bus
        self.address = address
        self.kernel_driver = kernel_driver  # bool, or an exception class to raise
        self.chunks: list[bytes] = []
        self.writes: list[tuple[int, bytes, int]] = []
        self.reads: list[tuple[int, int, int]] = []
        self.short_write = False
        self.claimed: list[int] = []
        self.released: list[int] = []
        self.disposed = 0

    def is_kernel_driver_active(self, interface):
        if isinstance(self.kernel_driver, type):
            raise self.kernel_driver("stub")
        return self.kernel_driver

    def write(self, endpoint, data, timeout):
        self.writes.append((endpoint, bytes(data), timeout))
        return len(data) - 1 if self.short_write else len(data)

    def read(self, endpoint, size, timeout):
        self.reads.append((endpoint, size, timeout))
        if not self.chunks:
            time.sleep(timeout / 1000.0)  # libusb blocks for the whole timeout
            raise StubUSBTimeoutError("timed out")
        # A short packet (here: the zero-length one) ends the transfer early.
        return array("B", self.chunks.pop(0)[:size])


@pytest.fixture
def stub_usb(monkeypatch):
    """Install a fake ``usb`` package; works with and without pyusb installed."""
    core = types.ModuleType("usb.core")
    core.USBError = StubUSBError
    core.USBTimeoutError = StubUSBTimeoutError
    core.NoBackendError = StubNoBackendError
    core.devices = []
    core.find_calls = []
    core.backend_missing = False

    def find(*, find_all, idVendor, idProduct, backend):
        core.find_calls.append((idVendor, idProduct, backend))
        if core.backend_missing:
            raise StubNoBackendError("no backend available")
        return iter(core.devices)

    core.find = find

    util = types.ModuleType("usb.util")
    util.claim_interface = lambda device, intf: device.claimed.append(intf)
    util.release_interface = lambda device, intf: device.released.append(intf)

    def dispose_resources(device):
        device.disposed += 1

    util.dispose_resources = dispose_resources

    package = types.ModuleType("usb")
    package.core = core
    package.util = util
    for name, module in (("usb", package), ("usb.core", core), ("usb.util", util)):
        monkeypatch.setitem(sys.modules, name, module)
    # None in sys.modules makes the import fail: no libusb-package by default.
    monkeypatch.setitem(sys.modules, "libusb_package", None)
    return core


def test_usb_transport_claims_the_data_interface(stub_usb):
    device = StubUsbDevice(bus=2, address=7)
    transport = UsbTransport(device)
    assert transport.port == "usb:2.7"
    assert device.claimed == [1]  # CDC data interface, like the vendor app


def test_usb_transport_writes_one_full_packet(stub_usb):
    device = StubUsbDevice()
    transport = UsbTransport(device)
    packet = pr.build_get_id()
    transport.write_packet(packet)
    assert device.writes == [(0x01, packet, 2000)]  # bulk OUT, 2 s in ms


def test_usb_transport_rejects_wrong_packet_sizes(stub_usb):
    transport = UsbTransport(StubUsbDevice())
    with pytest.raises(ValueError, match="64 bytes"):
        transport.write_packet(b"\x00" * 63)


def test_usb_transport_detects_a_short_write(stub_usb):
    device = StubUsbDevice()
    transport = UsbTransport(device)
    device.short_write = True
    with pytest.raises(OSError, match="short write"):
        transport.write_packet(pr.build_get_id())


def test_usb_transport_read_exact_consumes_the_zero_length_packet(stub_usb):
    device = StubUsbDevice()
    device.chunks = [b"r" * pr.REPLY_SIZE]
    transport = UsbTransport(device)
    assert transport.read_exact(pr.REPLY_SIZE, 1.5) == b"r" * pr.REPLY_SIZE
    # size + 512 makes the ZLP part of the same transfer (spec 2.2).
    assert device.reads == [(0x81, pr.REPLY_SIZE + 512, 1500)]


def test_usb_transport_read_exact_reads_a_whole_buffer(stub_usb):
    device = StubUsbDevice()
    device.chunks = [b"\xa5" * pr.BUFFER_SIZE]
    transport = UsbTransport(device)
    assert len(transport.read_exact(pr.BUFFER_SIZE, 15.0)) == pr.BUFFER_SIZE
    assert device.reads == [(0x81, pr.BUFFER_SIZE + 512, 15000)]


def test_usb_transport_read_exact_rejects_short_data(stub_usb):
    device = StubUsbDevice()
    device.chunks = [b"x" * 10]
    transport = UsbTransport(device)
    with pytest.raises(TimeoutError, match="10 of 512 bytes"):
        transport.read_exact(pr.REPLY_SIZE, 0.05)


def test_usb_transport_read_exact_times_out(stub_usb):
    transport = UsbTransport(StubUsbDevice())
    with pytest.raises(TimeoutError, match="0 of 512 bytes"):
        transport.read_exact(pr.REPLY_SIZE, 0.01)


def test_usb_transport_drain_returns_pending_bytes(stub_usb):
    device = StubUsbDevice()
    device.chunks = [b"1" * 512, b"2" * 16]
    transport = UsbTransport(device)
    assert transport.drain(1.0, quiet=0.01) == b"1" * 512 + b"2" * 16
    # A stale stream packet plus its ZLP fits into one read.
    assert device.reads[0][1] == pr.STREAM_PACKET_SIZE + pr.REPLY_SIZE


def test_usb_transport_drain_returns_nothing_when_silent(stub_usb):
    transport = UsbTransport(StubUsbDevice())
    assert transport.drain(0.05, quiet=0.01) == b""


def test_usb_transport_close_is_idempotent(stub_usb):
    device = StubUsbDevice()
    transport = UsbTransport(device)
    transport.close()
    transport.close()
    assert device.released == [1]
    assert device.disposed == 1


def test_find_usb_devices_skips_devices_owned_by_a_kernel_driver(stub_usb):
    free = StubUsbDevice(bus=1, address=4)
    owned = StubUsbDevice(bus=1, address=5, kernel_driver=True)
    stub_usb.devices = [owned, free]
    assert find_usb_devices() == [free]
    assert free.disposed == 1  # the probe must not keep a handle open


def test_find_usb_devices_accepts_backends_without_the_query(stub_usb):
    # pyusb raises NotImplementedError on Windows; that is not a kernel driver.
    device = StubUsbDevice(kernel_driver=NotImplementedError)
    stub_usb.devices = [device]
    assert find_usb_devices() == [device]


def test_find_usb_devices_skips_unopenable_devices(stub_usb):
    stub_usb.devices = [StubUsbDevice(kernel_driver=StubUSBError)]
    assert find_usb_devices() == []


def test_find_usb_devices_sorts_and_filters_by_selector(stub_usb):
    far = StubUsbDevice(bus=1, address=9)
    near = StubUsbDevice(bus=1, address=2)
    stub_usb.devices = [far, near]
    assert find_usb_devices() == [near, far]
    assert find_usb_devices("usb") == [near, far]
    assert find_usb_devices("usb:1.9") == [far]
    assert find_usb_devices("USB:1.9 ") == [far]
    assert find_usb_devices("usb:3.1") == []


@pytest.mark.parametrize("selector", ["usb:", "usb:1", "usb:a.b", "COM3"])
def test_find_usb_devices_rejects_invalid_selectors(stub_usb, selector):
    with pytest.raises(ValueError, match="USB selector"):
        find_usb_devices(selector)


def test_find_usb_devices_uses_the_libusb_package_backend(stub_usb, monkeypatch):
    module = types.ModuleType("libusb_package")
    module.get_libusb1_backend = lambda: "libusb-1.0-backend"
    monkeypatch.setitem(sys.modules, "libusb_package", module)
    find_usb_devices()
    assert stub_usb.find_calls == [(pr.USB_VID, pr.USB_PID, "libusb-1.0-backend")]


def test_find_usb_devices_falls_back_to_the_default_backend(stub_usb):
    find_usb_devices()
    assert stub_usb.find_calls == [(pr.USB_VID, pr.USB_PID, None)]


def test_find_usb_devices_without_a_libusb_library(stub_usb, caplog):
    stub_usb.backend_missing = True
    with caplog.at_level(logging.WARNING, logger="rdc2la.transport"):
        assert find_usb_devices() == []
    assert "libusb" in caplog.text


def test_find_usb_devices_without_pyusb(monkeypatch):
    monkeypatch.setitem(sys.modules, "usb", None)
    monkeypatch.setitem(sys.modules, "usb.core", None)
    assert find_usb_devices() == []


def test_usb_selector_and_port_detection():
    assert usb_selector(StubUsbDevice(bus=3, address=11)) == "usb:3.11"
    assert is_usb_port("usb") and is_usb_port("usb:1.4") and is_usb_port("USB:1.4")
    assert not is_usb_port("COM3")
    assert not is_usb_port("/dev/cu.usbmodem1234")


# --------------------------------------------------------------------------
# logging wrapper and fake device
# --------------------------------------------------------------------------


def test_logging_transport_records_and_logs(caplog):
    fake = FakeTransport()
    transport = LoggingTransport(fake)
    with caplog.at_level(logging.DEBUG, logger="rdc2la.wire"):
        transport.write_packet(pr.build_get_id())
        reply = transport.read_exact(pr.REPLY_SIZE, 1.0)
    assert len(reply) == pr.REPLY_SIZE
    assert transport.history[0][0] == "tx"
    assert transport.history[1][0] == "rx"
    assert "tx 00 04 00" in caplog.text
    assert "(512 bytes)" in caplog.text
    transport.close()
    assert fake.closed


def test_fake_transport_rejects_wrong_packet_sizes():
    with pytest.raises(ValueError):
        FakeTransport().write_packet(b"\x00" * 10)


def test_fake_transport_times_out_without_data():
    fake = FakeTransport()
    with pytest.raises(TimeoutError):
        fake.read_exact(512, 0.01)


def test_fake_transport_buffer_has_the_full_size():
    fake = FakeTransport()
    fake.write_packet(
        pr.build_la_config(
            mode=pr.SamplingMode.BUFFER, channels=8, sample_count=1_000,
            psc_reg=1079, arr1=2, n_streams=1,
        )
    )
    fake.write_packet(pr.build_get_samples())
    raw = fake.read_exact(pr.BUFFER_SIZE, 1.0)
    assert len(raw) == pr.BUFFER_SIZE
    assert raw[1_000:1_010] == b"\xa5" * 10  # untouched area behind the samples


def test_fake_transport_emulates_the_get_samples_hang():
    fake = FakeTransport()
    fake.write_packet(
        pr.build_la_config(
            mode=pr.SamplingMode.STREAM, channels=8, sample_count=0,
            psc_reg=1079, arr1=2, n_streams=1,
        )
    )
    fake.write_packet(pr.build_sample_stop())
    fake.read_exact(pr.REPLY_SIZE, 1.0)
    fake.write_packet(pr.build_get_samples())  # no stream running any more
    assert fake.hung
    with pytest.raises(TimeoutError):
        fake.read_exact(1, 0.01)
