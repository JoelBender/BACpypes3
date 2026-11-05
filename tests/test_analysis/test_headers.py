#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis Headers
---------------------

IPv4 header fields, UDP contents, and IPv6 / BACnet/IPv6 (Annex U) decoding.
"""

import json
import socket
import struct

import pytest

from bacpypes3.analysis import (
    LINKTYPE_ETHERNET,
    LINKTYPE_NULL,
    LINKTYPE_RAW,
    CustomJSONEncoder,
    decode_ipv4,
    decode_ipv6,
    decode_packet,
    decode_udp,
)
from bacpypes3.pdu import IPv4Address, IPv6Address, LocalBroadcast, VirtualAddress

# NPDU and ReadProperty-ACK device,510 object-list
NPDU_READ_PROPERTY_ACK = bytes.fromhex("0100 3001 0c 0c020001fe 194c 3e c4014004 4b 3f")

# NPDU and Who-Is
NPDU_WHO_IS = bytes.fromhex("0100 1008")

SRC_VMAC = bytes.fromhex("0a0b0c")
DST_VMAC = bytes.fromhex("010203")


def udp(payload: bytes, sport: int = 47808, dport: int = 47808) -> bytes:
    return struct.pack("!HHHH", sport, dport, 8 + len(payload), 0) + payload


def ipv4(
    src: str,
    dst: str,
    payload: bytes,
    protocol: int = 17,
    options: bytes = b"",
    flags_fragment: int = 0x4000,
) -> bytes:
    assert len(options) % 4 == 0
    header_len = 5 + len(options) // 4
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x40 | header_len,
        0,
        4 * header_len + len(payload),
        0x1234,
        flags_fragment,
        64,
        protocol,
        0,
        socket.inet_aton(src),
        socket.inet_aton(dst),
    )
    return header + options + payload


def ipv6(
    src: str,
    dst: str,
    payload: bytes,
    next_header: int = 17,
    extensions: bytes = b"",
) -> bytes:
    body = extensions + payload
    return (
        struct.pack("!IHBB", 0x60012345, len(body), next_header, 64)
        + socket.inet_pton(socket.AF_INET6, src)
        + socket.inet_pton(socket.AF_INET6, dst)
        + body
    )


def bvll6_unicast(npdu: bytes) -> bytes:
    return struct.pack("!BBH", 0x82, 0x01, 10 + len(npdu)) + SRC_VMAC + DST_VMAC + npdu


def bvll6_broadcast(npdu: bytes) -> bytes:
    return struct.pack("!BBH", 0x82, 0x02, 7 + len(npdu)) + SRC_VMAC + npdu


def bvll6_forwarded(npdu: bytes, src: str) -> bytes:
    return (
        struct.pack("!BBH", 0x82, 0x08, 25 + len(npdu))
        + SRC_VMAC
        + socket.inet_pton(socket.AF_INET6, src)
        + struct.pack("!H", 47808)
        + npdu
    )


def ethernet(payload: bytes, ethertype: int) -> bytes:
    # the IPv6 multicast MAC for ff02::bac0
    return (
        bytes.fromhex("33330000bac0")
        + bytes.fromhex("020000000001")
        + struct.pack("!H", ethertype)
        + payload
    )


#
#   IPv4 header fields
#


def test_ipv4_options():
    """Options are the bytes between the fixed header and the payload."""
    options = bytes.fromhex("94040000")  # router alert
    payload = udp(b"hello")
    ip = decode_ipv4(ipv4("10.0.0.1", "10.0.0.2", payload, options=options))
    assert ip.header_len == 6
    assert ip.options == options
    assert ip.data == payload


def test_ipv4_long_options():
    options = bytes.fromhex("010101010101010101010100")  # NOPs + EOL
    payload = udp(b"hello")
    ip = decode_ipv4(ipv4("10.0.0.1", "10.0.0.2", payload, options=options))
    assert ip.header_len == 8
    assert ip.options == options
    assert ip.data == payload


def test_ipv4_no_options():
    ip = decode_ipv4(ipv4("10.0.0.1", "10.0.0.2", udp(b"hello")))
    assert ip.options is None


def test_ipv4_fragment_offset():
    """The fragment offset is 13 bits, the flags are the upper 3."""
    ip = decode_ipv4(
        ipv4("10.0.0.1", "10.0.0.2", b"\x00" * 8, flags_fragment=0x2000 | 0x1ABC)
    )
    assert ip.flags == 1  # more fragments
    assert ip.fragment_offset == 0x1ABC


def test_ipv4_later_fragment_is_not_udp():
    """A non-first fragment has no UDP header, even if it looks like one."""
    payload = udp(bytes.fromhex("810a0008") + NPDU_WHO_IS)
    frame = decode_packet(
        ipv4("10.0.0.1", "10.0.0.2", payload, flags_fragment=0x0100), LINKTYPE_RAW
    )
    assert frame.ipv4.fragment_offset == 0x0100
    assert frame.udp is None
    assert frame.npci is None


#
#   UDP contents
#


def test_udp_dict_contents_data():
    u = decode_udp(udp(b"hello"))
    assert u.dict_contents()["data"] == b"hello"
    assert "type" not in u.dict_contents()
    assert "data" not in u.dict_contents(include_data=False)


#
#   IPv6
#


def test_ipv6_header():
    payload = udp(b"hello")
    ip = decode_ipv6(ipv6("fe80::1", "ff02::bac0", payload))
    assert ip.version == 6
    assert ip.traffic_class == 0x00
    assert ip.flow_label == 0x12345
    assert ip.payload_len == len(payload)
    assert ip.next_header == 17
    assert ip.hop_limit == 64
    assert ip.source_address == "fe80::1"
    assert ip.destination_address == "ff02::bac0"
    assert ip.extension_headers == []
    assert ip.protocol == "udp"
    assert ip.data == payload


def test_ipv6_trailing_padding():
    """Bytes past the payload length (Ethernet padding) are dropped."""
    payload = udp(b"hello")
    ip = decode_ipv6(ipv6("fe80::1", "fe80::2", payload) + b"\x00" * 6)
    assert ip.data == payload


def test_ipv6_extension_headers():
    payload = udp(b"hello")
    hop_by_hop = bytes([60, 0]) + b"\x01\x04\x00\x00\x00\x00"  # -> dest opts
    dest_opts = bytes([17, 1]) + b"\x01\x0c" + b"\x00" * 12  # 16 bytes -> UDP
    ip = decode_ipv6(
        ipv6(
            "fe80::1",
            "fe80::2",
            payload,
            next_header=0,
            extensions=hop_by_hop + dest_opts,
        )
    )
    assert ip.next_header == 0
    assert ip.extension_headers == [0, 60]
    assert ip.protocol == "udp"
    assert ip.data == payload


def test_ipv6_first_fragment():
    payload = udp(b"hello")
    fragment = struct.pack("!BBHI", 17, 0, 0x0001, 0xDEADBEEF)  # offset 0, M
    ip = decode_ipv6(
        ipv6("fe80::1", "fe80::2", payload, next_header=44, extensions=fragment)
    )
    assert ip.extension_headers == [44]
    assert ip.fragment_offset == 0
    assert ip.protocol == "udp"
    assert ip.data == payload


def test_ipv6_later_fragment_is_not_udp():
    payload = udp(bvll6_broadcast(NPDU_WHO_IS))
    fragment = struct.pack("!BBHI", 17, 0, 100 << 3, 0xDEADBEEF)
    frame = decode_packet(
        ipv6("fe80::1", "fe80::2", payload, next_header=44, extensions=fragment),
        LINKTYPE_RAW,
    )
    assert frame.ipv6.fragment_offset == 100
    assert frame.udp is None
    assert frame.npci is None


def test_ipv6_not_udp():
    frame = decode_packet(
        ipv6("fe80::1", "fe80::2", b"\x80\x00" + b"\x00" * 6, next_header=58),
        LINKTYPE_RAW,
    )
    assert frame.ipv6.protocol == "icmpv6"
    assert frame.udp is None
    assert frame.npci is None


#
#   BACnet/IPv6
#


def test_bacnet_ipv6_unicast():
    data = ipv6("fe80::1", "fe80::2", udp(bvll6_unicast(NPDU_READ_PROPERTY_ACK)))
    frame = decode_packet(data, LINKTYPE_RAW)
    assert frame.ethernet is None
    assert frame.ipv4 is None
    assert frame.ipv6.source_address == "fe80::1"
    assert frame.udp.source_port == 47808
    assert frame.bvlci.bvlciType == 0x82
    assert frame.bvll.__class__.__name__ == "OriginalUnicastNPDU"
    assert frame.npci.npduVersion == 1
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"

    # the BACnet/IPv6 MAC address is the VMAC
    assert frame.apdu.pduSource == VirtualAddress(SRC_VMAC)
    assert frame.apdu.pduDestination == VirtualAddress(DST_VMAC)


def test_bacnet_ipv6_broadcast_ethernet():
    data = ethernet(
        ipv6("fe80::1", "ff02::bac0", udp(bvll6_broadcast(NPDU_WHO_IS))), 0x86DD
    )
    frame = decode_packet(data, LINKTYPE_ETHERNET)
    assert frame.ethernet.type == 0x86DD
    assert frame.ipv6.destination_address == "ff02::bac0"
    assert frame.bvll.__class__.__name__ == "OriginalBroadcastNPDU"
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert frame.apdu.pduSource == VirtualAddress(SRC_VMAC)
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_bacnet_ipv6_forwarded():
    data = ipv6(
        "2001:db8::1", "ff05::bac0", udp(bvll6_forwarded(NPDU_WHO_IS, "2001:db8::99"))
    )
    frame = decode_packet(data, LINKTYPE_RAW)
    assert frame.bvll.__class__.__name__ == "ForwardedNPDU"
    assert frame.bvll.bvlciSourceIPv6Address == IPv6Address(("2001:db8::99", 47808))
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert frame.apdu.pduSource == VirtualAddress(SRC_VMAC)
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_bacnet_ipv6_no_npdu():
    """Address resolution has no NPDU to decode."""
    bvll = struct.pack("!BBH", 0x82, 0x03, 10) + SRC_VMAC + DST_VMAC
    frame = decode_packet(ipv6("fe80::1", "ff02::bac0", udp(bvll)), LINKTYPE_RAW)
    assert frame.bvll.__class__.__name__ == "AddressResolution"
    assert frame.npci is None


def test_bacnet_ipv4_unaffected():
    """The Annex J path still uses the IPv4 BVLL and the IPv4 address."""
    bvll = bytes.fromhex("810a") + struct.pack("!H", 4 + len(NPDU_WHO_IS))
    frame = decode_packet(
        ipv4("10.0.0.1", "10.0.0.2", udp(bvll + NPDU_WHO_IS)), LINKTYPE_RAW
    )
    assert frame.ipv6 is None
    assert frame.bvlci.bvlciType == 0x81
    assert frame.apdu.pduSource == IPv4Address("10.0.0.1")


@pytest.mark.parametrize("family", [10, 24, 28, 30])
@pytest.mark.parametrize("endian", ["<", ">"])
def test_null_ipv6(family, endian):
    data = struct.pack(endian + "I", family) + ipv6(
        "::1", "::1", udp(bvll6_unicast(NPDU_READ_PROPERTY_ACK))
    )
    frame = decode_packet(data, LINKTYPE_NULL)
    assert frame.ipv6 is not None
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"


def test_bacnet_ipv6_json():
    """The command line JSON dump works for IPv6 frames."""
    data = ipv6("fe80::1", "fe80::2", udp(bvll6_unicast(NPDU_READ_PROPERTY_ACK)))
    frame = decode_packet(data, LINKTYPE_RAW)
    contents = json.loads(json.dumps(frame.dict_contents(), cls=CustomJSONEncoder))
    assert contents["ipv6"]["source_address"] == "fe80::1"
    assert "extension_headers" not in contents["ipv6"]
    assert contents["bvlci"]["bvlciType"] == 0x82
    assert contents["apdu"]["function"] == "ReadPropertyACK"
