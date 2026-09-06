# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
"""Tests for the sigrok session (.sr) and raw (.bin) writers."""

from __future__ import annotations

import configparser
import shutil
import subprocess
import zipfile

import pytest

from rdc2la.srfile import BinWriter, SrWriter, build_metadata, writer_for_path


def read_sr(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        version = archive.read("version").decode()
        metadata = archive.read("metadata").decode()
        chunks = {
            name: archive.read(name)
            for name in names
            if name.startswith("logic-1-")
        }
    return names, version, metadata, chunks


def parse_metadata(text: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return parser


def test_metadata_keys_match_the_srzip_format():
    text = build_metadata(8, 100_000)
    config = parse_metadata(text)
    assert config["global"]["sigrok version"] == "0.5.2"
    device = config["device 1"]
    assert device["capturefile"] == "logic-1"
    assert device["total probes"] == "8"
    assert device["samplerate"] == "100000 Hz"
    assert device["total analog"] == "0"
    assert device["unitsize"] == "1"
    assert device["probe1"] == "D0"
    assert device["probe8"] == "D7"
    assert "probe9" not in device


@pytest.mark.parametrize("channels,unitsize", [(8, 1), (16, 2), (32, 4)])
def test_unitsize_follows_the_channel_count(tmp_path, channels, unitsize):
    path = tmp_path / "out.sr"
    with SrWriter(path, channels, 1_000_000) as writer:
        writer.append(b"\x00" * (unitsize * 10))
    _, _, metadata, chunks = read_sr(path)
    config = parse_metadata(metadata)
    assert config["device 1"]["unitsize"] == str(unitsize)
    assert config["device 1"]["total probes"] == str(channels)
    assert len(chunks["logic-1-1"]) == unitsize * 10


def test_sr_writer_layout(tmp_path):
    path = tmp_path / "capture.sr"
    payload = bytes(range(256)) * 4
    with SrWriter(path, 8, 100_000) as writer:
        writer.append(payload[:512])
        writer.append(payload[512:])
    assert zipfile.is_zipfile(path)
    names, version, metadata, chunks = read_sr(path)
    assert version == "2"
    assert names[:2] == ["version", "metadata"]
    assert list(chunks) == ["logic-1-1"]
    assert chunks["logic-1-1"] == payload
    assert parse_metadata(metadata)["device 1"]["samplerate"] == "100000 Hz"


def test_sr_writer_splits_data_into_chunks(tmp_path):
    path = tmp_path / "chunks.sr"
    payload = bytes((i * 7) & 0xFF for i in range(10_000))
    with SrWriter(path, 8, 1_000_000, chunk_size=4_096) as writer:
        for offset in range(0, len(payload), 1_000):
            writer.append(payload[offset:offset + 1_000])
    _, _, _, chunks = read_sr(path)
    assert list(chunks) == ["logic-1-1", "logic-1-2", "logic-1-3"]
    assert [len(chunk) for chunk in chunks.values()] == [4_096, 4_096, 1_808]
    assert b"".join(chunks.values()) == payload


def test_sr_writer_chunk_size_is_a_whole_number_of_samples(tmp_path):
    writer = SrWriter(tmp_path / "a.sr", 32, 1_000_000, chunk_size=4_002)
    assert writer.chunk_size % 4 == 0
    writer.close()


def test_sr_writer_truncate(tmp_path):
    path = tmp_path / "trunc.sr"
    with SrWriter(path, 8, 100_000) as writer:
        writer.append(b"\xaa" * 1_000)
        writer.append(b"\xbb" * 1_000)
        assert writer.bytes_written == 2_000
        writer.truncate(1_500)
        assert writer.bytes_written == 1_500
        assert writer.sample_count == 1_500
    _, _, _, chunks = read_sr(path)
    assert chunks["logic-1-1"] == b"\xaa" * 1_000 + b"\xbb" * 500


def test_sr_writer_drops_a_partial_sample(tmp_path):
    path = tmp_path / "partial.sr"
    with SrWriter(path, 16, 100_000) as writer:
        writer.append(b"\x01\x02\x03")  # one and a half samples
    _, _, _, chunks = read_sr(path)
    assert chunks["logic-1-1"] == b"\x01\x02"


def test_sr_writer_removes_its_spool_file(tmp_path):
    path = tmp_path / "spool.sr"
    with SrWriter(path, 8, 100_000) as writer:
        writer.append(b"\x00" * 100)
    assert [p.name for p in tmp_path.iterdir()] == ["spool.sr"]


def test_sr_writer_handles_an_empty_capture(tmp_path):
    path = tmp_path / "empty.sr"
    SrWriter(path, 8, 100_000).close()
    names, version, _, chunks = read_sr(path)
    assert version == "2"
    assert chunks == {}


def test_bin_writer(tmp_path):
    path = tmp_path / "out.bin"
    with BinWriter(path, 16) as writer:
        writer.append(b"\x01\x02")
        writer.append(b"\x03\x04")
        assert writer.sample_count == 2
        writer.truncate(2)
    assert path.read_bytes() == b"\x01\x02"


def test_writer_for_path(tmp_path):
    sr = writer_for_path(tmp_path / "a.SR", 8, 100_000)
    assert isinstance(sr, SrWriter)
    sr.close()
    binary = writer_for_path(tmp_path / "a.bin", 8, 100_000)
    assert isinstance(binary, BinWriter)
    binary.close()
    with pytest.raises(ValueError, match="unsupported output format"):
        writer_for_path(tmp_path / "a.txt", 8, 100_000)


@pytest.mark.skipif(shutil.which("sigrok-cli") is None, reason="sigrok-cli not installed")
def test_sigrok_cli_reads_the_session_file(tmp_path):
    path = tmp_path / "sigrok.sr"
    payload = bytes([0x00, 0x01, 0x03, 0x07, 0x0F, 0xFF, 0x00, 0xAA])
    with SrWriter(path, 8, 100_000) as writer:
        writer.append(payload)
    result = subprocess.run(
        ["sigrok-cli", "-i", str(path), "-O", "hex:width=8"],
        capture_output=True, text=True, check=True,
    )
    assert "D0:" in result.stdout
    result = subprocess.run(
        ["sigrok-cli", "-i", str(path), "--show"],
        capture_output=True, text=True, check=True,
    )
    assert "100 kHz" in result.stdout or "100000" in result.stdout
