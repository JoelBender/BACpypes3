#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis Link Types
------------------------

Captures from interfaces without an Ethernet header (tun, Linux "any",
loopback) must be decoded using the link-layer header type of the capture.
"""

import socket
import struct

import pytest

from bacpypes3.analysis import (
    LINKTYPE_ETHERNET,
    LINKTYPE_LINUX_SLL,
    LINKTYPE_LINUX_SLL2,
    LINKTYPE_NULL,
    LINKTYPE_RAW,
    decode_packet,
    pcap_file_linktype,
)
from bacpypes3.errors import DecodingError
from bacpypes3.pdu import IPv4Address, LocalBroadcast

# BVLL Original-Unicast-NPDU, NPDU, ReadProperty-ACK device,510 object-list
READ_PROPERTY_ACK = bytes.fromhex(
    "810a0017 0100 3001 0c 0c020001fe 194c 3e c4014004 4b 3f"
)

# BVLL Original-Broadcast-NPDU, NPDU, Who-Is
WHO_IS = bytes.fromhex("810b0008 0100 1008")


def ipv4_udp(src: str, dst: str, payload: bytes, protocol: int = 17) -> bytes:
    """Build an IPv4 header and a UDP header around a payload."""
    udp = struct.pack("!HHHH", 47808, 47808, 8 + len(payload), 0) + payload
    ip = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(udp),
        0,
        0x4000,
        64,
        protocol,
        0,
        socket.inet_aton(src),
        socket.inet_aton(dst),
    )
    return ip + udp


def ethernet(dst: str, payload: bytes, ethertype: int = 0x0800) -> bytes:
    return (
        bytes.fromhex(dst.replace(":", ""))
        + bytes.fromhex("020000000001")
        + struct.pack("!H", ethertype)
        + payload
    )


def linux_sll(payload: bytes, packet_type: int = 0) -> bytes:
    return struct.pack("!HHH8sH", packet_type, 1, 6, b"\x02" * 6, 0x0800) + payload


def linux_sll2(payload: bytes, packet_type: int = 0) -> bytes:
    return (
        struct.pack("!HHIHBB8s", 0x0800, 0, 2, 1, packet_type, 6, b"\x02" * 6) + payload
    )


# the packet that failed when Ethernet was assumed, the third octet of the
# source address landed where the NPDU version was expected
RAW_ACK = ipv4_udp("10.0.1.71", "128.253.109.12", READ_PROPERTY_ACK)


def assert_read_property_ack(frame, source="10.0.1.71"):
    assert frame is not None
    assert frame.ipv4.source_address == source
    assert frame.udp.destination_port == 47808
    assert frame.bvll is not None
    assert frame.npci.npduVersion == 1
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"
    assert frame.apdu.pduSource == IPv4Address(source)


def test_raw_ip():
    frame = decode_packet(RAW_ACK, LINKTYPE_RAW)
    assert frame.ethernet is None
    assert_read_property_ack(frame)


def test_raw_ip_as_ethernet_is_garbage():
    """Decoding raw IP as Ethernet must not produce a bogus NPCI."""
    frame = decode_packet(RAW_ACK, LINKTYPE_ETHERNET)
    assert frame.ipv4 is None
    assert frame.apdu is None


def test_ethernet_default():
    frame = decode_packet(ethernet("02:00:00:00:00:02", RAW_ACK))
    assert frame.ethernet is not None
    assert_read_property_ack(frame)


def test_ethernet_broadcast():
    data = ethernet("FF:FF:FF:FF:FF:FF", ipv4_udp("10.0.1.71", "10.0.1.255", WHO_IS))
    frame = decode_packet(data, LINKTYPE_ETHERNET)
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_raw_ip_limited_broadcast():
    frame = decode_packet(
        ipv4_udp("10.0.1.71", "255.255.255.255", WHO_IS), LINKTYPE_RAW
    )
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_raw_ip_directed_broadcast():
    """Without a MAC address a subnet broadcast looks like a unicast."""
    frame = decode_packet(ipv4_udp("10.0.1.71", "10.0.1.255", WHO_IS), LINKTYPE_RAW)
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert frame.apdu.pduDestination == IPv4Address("10.0.1.255")


def test_raw_ip_not_udp():
    frame = decode_packet(
        ipv4_udp("10.0.1.71", "128.253.109.12", READ_PROPERTY_ACK, protocol=6),
        LINKTYPE_RAW,
    )
    assert frame.ipv4.protocol == "tcp"
    assert frame.udp is None
    assert frame.npci is None


def test_raw_ipv6_is_skipped():
    frame = decode_packet(b"\x60" + b"\x00" * 47, LINKTYPE_RAW)
    assert frame.ipv4 is None
    assert frame.npci is None


@pytest.mark.parametrize("family", [b"\x02\x00\x00\x00", b"\x00\x00\x00\x02"])
def test_null(family):
    frame = decode_packet(family + RAW_ACK, LINKTYPE_NULL)
    assert_read_property_ack(frame)


def test_linux_sll():
    frame = decode_packet(linux_sll(RAW_ACK), LINKTYPE_LINUX_SLL)
    assert_read_property_ack(frame)
    assert not isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_linux_sll_broadcast():
    data = linux_sll(ipv4_udp("10.0.1.71", "10.0.1.255", WHO_IS), packet_type=1)
    frame = decode_packet(data, LINKTYPE_LINUX_SLL)
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_linux_sll2():
    frame = decode_packet(linux_sll2(RAW_ACK), LINKTYPE_LINUX_SLL2)
    assert_read_property_ack(frame)


def test_linux_sll2_broadcast():
    data = linux_sll2(ipv4_udp("10.0.1.71", "10.0.1.255", WHO_IS), packet_type=1)
    frame = decode_packet(data, LINKTYPE_LINUX_SLL2)
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_unsupported_linktype():
    with pytest.raises(DecodingError):
        decode_packet(RAW_ACK, 9999)


#
#   pcap_file_linktype
#


@pytest.mark.parametrize("endian", ["<", ">"])
@pytest.mark.parametrize("magic", [0xA1B2C3D4, 0xA1B23C4D])
def test_pcap_file_linktype(tmp_path, endian, magic):
    fname = tmp_path / "test.pcap"
    fname.write_bytes(struct.pack(endian + "IHHiIII", magic, 2, 4, 0, 0, 65535, 101))
    assert pcap_file_linktype(str(fname)) == LINKTYPE_RAW


def test_pcap_file_linktype_fcs_bits(tmp_path):
    """The upper bits of the link type field carry FCS information."""
    fname = tmp_path / "test.pcap"
    fname.write_bytes(
        struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 0x14000001)
    )
    assert pcap_file_linktype(str(fname)) == LINKTYPE_ETHERNET


def pcapng_block(endian: str, block_type: int, body: bytes) -> bytes:
    body += b"\x00" * (-len(body) % 4)
    length = 12 + len(body)
    return (
        struct.pack(endian + "II", block_type, length)
        + body
        + struct.pack(endian + "I", length)
    )


@pytest.mark.parametrize("endian", ["<", ">"])
def test_pcapng_file_linktype(tmp_path, endian):
    shb = pcapng_block(
        endian,
        0x0A0D0D0A,
        struct.pack(endian + "IHHq", 0x1A2B3C4D, 1, 0, -1)
        # a shb_userappl option so the IDB is not at a fixed offset
        + struct.pack(endian + "HH", 4, 7)
        + b"dumpcap\x00"
        + struct.pack(endian + "HH", 0, 0),
    )
    idb = pcapng_block(endian, 1, struct.pack(endian + "HHI", 113, 0, 262144))
    fname = tmp_path / "test.pcapng"
    fname.write_bytes(shb + idb)
    assert pcap_file_linktype(str(fname)) == LINKTYPE_LINUX_SLL


def test_not_a_capture_file(tmp_path):
    fname = tmp_path / "test.txt"
    fname.write_bytes(b"this is not a capture file at all")
    with pytest.raises(ValueError):
        pcap_file_linktype(str(fname))
