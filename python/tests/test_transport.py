# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Transport tests.

The serial transport is exercised against a stub ``serial.Serial`` object; no
real port is ever opened.
"""

from __future__ import annotations

import logging

import pytest
import serial

from rdc2la import protocol as pr
from rdc2la.transport import FakeTransport, LoggingTransport, SerialTransport


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
