#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis Capture File Reader
---------------------------------

Capture files are read directly so the packet timestamps keep the resolution
of the file, the pylibpcap file reader truncates them to whole seconds.
"""

import struct

import pytest

from bacpypes3 import analysis
from bacpypes3.analysis import (
    LINKTYPE_ETHERNET,
    LINKTYPE_LINUX_SLL,
    LINKTYPE_RAW,
    decode_file,
    read_pcap_file,
)

from .test_linktypes import RAW_ACK, pcapng_block


def pcap_file(endian, magic, linktype, records):
    """Build a classic pcap file from (ts_sec, ts_frac, data) records."""
    data = struct.pack(endian + "IHHiIII", magic, 2, 4, 0, 0, 65535, linktype)
    for ts_sec, ts_frac, packet in records:
        data += struct.pack(endian + "IIII", ts_sec, ts_frac, len(packet), len(packet))
        data += packet
    return data


def shb(endian):
    return pcapng_block(
        endian, 0x0A0D0D0A, struct.pack(endian + "IHHq", 0x1A2B3C4D, 1, 0, -1)
    )


def idb(endian, linktype, options=b"", snaplen=262144):
    if options:
        options += struct.pack(endian + "HH", 0, 0)
    return pcapng_block(
        endian, 1, struct.pack(endian + "HHI", linktype, 0, snaplen) + options
    )


def option(endian, code, value):
    return (
        struct.pack(endian + "HH", code, len(value))
        + value
        + b"\x00" * (-len(value) % 4)
    )


def epb(endian, interface_id, ticks, packet):
    return pcapng_block(
        endian,
        6,
        struct.pack(
            endian + "IIIII",
            interface_id,
            ticks >> 32,
            ticks & 0xFFFFFFFF,
            len(packet),
            len(packet),
        )
        + packet,
    )


def write(tmp_path, data, name="test.pcap"):
    fname = tmp_path / name
    fname.write_bytes(data)
    return str(fname)


#
#   classic pcap
#


@pytest.mark.parametrize("endian", ["<", ">"])
@pytest.mark.parametrize(
    "magic, ts_frac, expected",
    [
        (0xA1B2C3D4, 332479, 1793878125.332479),  # microseconds
        (0xA1B23C4D, 332479123, 1793878125.332479123),  # nanoseconds
    ],
)
def test_pcap_timestamp(tmp_path, endian, magic, ts_frac, expected):
    fname = write(
        tmp_path,
        pcap_file(endian, magic, LINKTYPE_RAW, [(1793878125, ts_frac, RAW_ACK)]),
    )
    ((timestamp, linktype, data),) = list(read_pcap_file(fname))
    assert timestamp == pytest.approx(expected, abs=1e-6)
    assert timestamp != int(timestamp)
    assert linktype == LINKTYPE_RAW
    assert data == RAW_ACK


def test_pcap_truncated_last_record(tmp_path):
    """A file still being written ends with a partial record."""
    data = pcap_file("<", 0xA1B2C3D4, LINKTYPE_RAW, [(1, 0, RAW_ACK), (2, 0, RAW_ACK)])
    fname = write(tmp_path, data[:-5])
    assert [ts for ts, _, _ in read_pcap_file(fname)] == [1.0]


def test_pcap_unsupported_linktype(tmp_path):
    fname = write(tmp_path, pcap_file("<", 0xA1B2C3D4, 147, []))
    with pytest.raises(ValueError, match="unsupported link type: 147"):
        list(read_pcap_file(fname))


def test_not_a_capture_file(tmp_path):
    fname = write(tmp_path, b"this is not a capture file at all")
    with pytest.raises(ValueError):
        list(read_pcap_file(fname))


#
#   pcapng
#


@pytest.mark.parametrize("endian", ["<", ">"])
def test_pcapng_default_resolution(tmp_path, endian):
    data = (
        shb(endian)
        + idb(endian, LINKTYPE_RAW)
        + epb(endian, 0, 1793878125332479, RAW_ACK)
    )
    fname = write(tmp_path, data, "test.pcapng")
    ((timestamp, linktype, packet),) = list(read_pcap_file(fname))
    assert timestamp == pytest.approx(1793878125.332479, abs=1e-6)
    assert linktype == LINKTYPE_RAW
    assert packet == RAW_ACK


@pytest.mark.parametrize(
    "tsresol, ticks, expected",
    [
        (9, 1793878125332479123, 1793878125.332479123),  # nanoseconds
        (3, 1793878125332, 1793878125.332),  # milliseconds
        (0x80 | 10, 1793878125 * 1024 + 512, 1793878125.5),  # 2**-10 seconds
    ],
)
def test_pcapng_tsresol(tmp_path, tsresol, ticks, expected):
    options = option("<", 9, bytes([tsresol]))
    data = shb("<") + idb("<", LINKTYPE_RAW, options) + epb("<", 0, ticks, RAW_ACK)
    fname = write(tmp_path, data, "test.pcapng")
    ((timestamp, _, _),) = list(read_pcap_file(fname))
    assert timestamp == pytest.approx(expected, abs=1e-6)


def test_pcapng_tsoffset(tmp_path):
    options = option("<", 14, struct.pack("<q", 1000))
    data = shb("<") + idb("<", LINKTYPE_RAW, options) + epb("<", 0, 2_500_000, RAW_ACK)
    fname = write(tmp_path, data, "test.pcapng")
    ((timestamp, _, _),) = list(read_pcap_file(fname))
    assert timestamp == pytest.approx(1002.5)


def test_pcapng_interfaces_with_different_linktypes(tmp_path):
    data = (
        shb("<")
        + idb("<", LINKTYPE_RAW)
        + idb("<", LINKTYPE_ETHERNET, option("<", 9, bytes([9])))
        + epb("<", 1, 2_000_000_000, b"eth")
        + epb("<", 0, 1_000_000, b"raw")
    )
    fname = write(tmp_path, data, "test.pcapng")
    assert list(read_pcap_file(fname)) == [
        (2.0, LINKTYPE_ETHERNET, b"eth"),
        (1.0, LINKTYPE_RAW, b"raw"),
    ]


def test_pcapng_simple_and_obsolete_packet_blocks(tmp_path):
    spb = pcapng_block("<", 3, struct.pack("<I", 10) + b"0123456789")
    pb = pcapng_block("<", 2, struct.pack("<HHIIII", 0, 0, 0, 3_000_000, 2, 2) + b"pb")
    data = shb("<") + idb("<", LINKTYPE_LINUX_SLL, snaplen=4) + spb + pb
    fname = write(tmp_path, data, "test.pcapng")
    assert list(read_pcap_file(fname)) == [
        (0.0, LINKTYPE_LINUX_SLL, b"0123"),  # no timestamp, cut to the snaplen
        (3.0, LINKTYPE_LINUX_SLL, b"pb"),
    ]


def test_pcapng_new_section_resets_interfaces(tmp_path):
    data = (
        shb("<")
        + idb("<", LINKTYPE_RAW)
        + idb("<", LINKTYPE_RAW)
        + shb(">")
        + idb(">", LINKTYPE_RAW)
        + epb(">", 1, 0, RAW_ACK)
    )
    fname = write(tmp_path, data, "test.pcapng")
    with pytest.raises(ValueError, match="undefined interface 1"):
        list(read_pcap_file(fname))


def test_pcapng_truncated_last_block(tmp_path):
    data = shb("<") + idb("<", LINKTYPE_RAW) + epb("<", 0, 1_000_000, RAW_ACK)
    fname = write(tmp_path, data + epb("<", 0, 2_000_000, RAW_ACK)[:-8], "test.pcapng")
    assert [ts for ts, _, _ in read_pcap_file(fname)] == [1.0]


#
#   decode_file
#


def test_decode_file_without_pylibpcap(tmp_path, monkeypatch):
    """Files are decoded with the full timestamp and pylibpcap isn't needed."""
    monkeypatch.setattr(analysis, "pylibpcap", None)
    records = [(1793878125, 0, b"not a bacnet packet"), (1793878125, 332479, RAW_ACK)]
    fname = write(tmp_path, pcap_file("<", 0xA1B2C3D4, LINKTYPE_RAW, records))
    (frame,) = list(decode_file(fname))
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"
    assert frame._number == 2
    assert frame._timestamp == pytest.approx(1793878125.332479, abs=1e-6)
