#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis ARCNET and LLC
----------------------------

BACnet/ARCNET (Clause 8) and BACnet/Ethernet (Clause 7) carry the NPDU in
an 802.2 LLC UI frame, and APDUs that cannot be decoded keep their frame.
"""

import socket
import struct

from bacpypes3.analysis import (
    LINKTYPE_ARCNET_BSD,
    LINKTYPE_ARCNET_LINUX,
    LINKTYPE_ETHERNET,
    LINKTYPE_LINUX_SLL,
    LINKTYPE_RAW,
    decode_packet,
)
from bacpypes3.apdu import ComplexAckPDU
from bacpypes3.pdu import Address, ARCNETAddress, LocalBroadcast
from bacpypes3.primitivedata import CharacterString

LLC_BACNET = bytes.fromhex("828203")

# NPDU and Who-Is
NPDU_WHO_IS = bytes.fromhex("0100 1008")

# NPDU and ReadProperty-ACK device,510 object-list
NPDU_READ_PROPERTY_ACK = bytes.fromhex("0100 3001 0c 0c020001fe 194c 3e c4014004 4b 3f")


def npdu_long_read_property_ack(length: int = 260) -> bytes:
    """
    An NPDU with a ReadProperty-ACK of a long description, too big for a
    short ARCNET frame.
    """
    value = b"\x00" + b"x" * length
    return (
        bytes.fromhex("0100 3001 0c 0c02000001 191c 3e")
        + bytes([0x75, 0xFE])
        + struct.pack("!H", len(value))
        + value
        + b"\x3f"
    )


def arcnet_linux(src: int, dst: int, payload: bytes, sc: int = 0xCD) -> bytes:
    """Linux ARCNET header, the 2-byte field is the length after it."""
    return (
        bytes([src, dst]) + struct.pack("<H", 1 + len(payload)) + bytes([sc]) + payload
    )


def arcnet_bsd(src: int, dst: int, payload: bytes, sc: int = 0xCD) -> bytes:
    return bytes([src, dst, sc]) + payload


def ipv4_udp(payload: bytes) -> bytes:
    udp = struct.pack("!HHHH", 47808, 47808, 8 + len(payload), 0) + payload
    return (
        struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(udp),
            0,
            0x4000,
            64,
            17,
            0,
            socket.inet_aton("10.0.0.1"),
            socket.inet_aton("10.0.0.2"),
        )
        + udp
    )


#
#   ARCNET
#


def test_arcnet_linux_broadcast():
    frame = decode_packet(
        arcnet_linux(5, 0, LLC_BACNET + NPDU_WHO_IS), LINKTYPE_ARCNET_LINUX
    )
    assert frame.ethernet is None
    assert frame.arcnet.source_address == 5
    assert frame.arcnet.destination_address == 0
    assert frame.arcnet.system_code == 0xCD
    assert frame.arcnet.padding == b""
    assert (frame.llc.dsap, frame.llc.ssap, frame.llc.control) == (0x82, 0x82, 0x03)
    assert frame.npci.npduVersion == 1
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert frame.apdu.pduSource == ARCNETAddress(5)
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_arcnet_linux_unicast():
    frame = decode_packet(
        arcnet_linux(1, 9, LLC_BACNET + NPDU_READ_PROPERTY_ACK), LINKTYPE_ARCNET_LINUX
    )
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"
    assert frame.apdu.pduSource == ARCNETAddress(1)
    assert frame.apdu.pduDestination == ARCNETAddress(9)


def test_arcnet_bsd():
    frame = decode_packet(
        arcnet_bsd(7, 0, LLC_BACNET + NPDU_WHO_IS), LINKTYPE_ARCNET_BSD
    )
    assert frame.arcnet.source_address == 7
    assert frame.arcnet.system_code == 0xCD
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"


def test_arcnet_not_bacnet():
    """Other system codes (0xD4 is RFC 1201 IP) are not decoded further."""
    frame = decode_packet(
        arcnet_linux(5, 0, b"\x00\x00\x00" + NPDU_WHO_IS, sc=0xD4),
        LINKTYPE_ARCNET_LINUX,
    )
    assert frame.arcnet.system_code == 0xD4
    assert frame.llc is None
    assert frame.npci is None


def test_arcnet_not_bacnet_llc():
    frame = decode_packet(
        arcnet_linux(5, 0, bytes.fromhex("424203") + NPDU_WHO_IS),
        LINKTYPE_ARCNET_LINUX,
    )
    assert frame.llc.dsap == 0x42
    assert frame.npci is None


#
#   ARCNET long frame padding
#


def test_arcnet_long_frame():
    npdu = npdu_long_read_property_ack()
    frame = decode_packet(arcnet_linux(1, 6, LLC_BACNET + npdu), LINKTYPE_ARCNET_LINUX)
    assert len(frame.arcnet.data) > 253
    assert frame.arcnet.padding == b""
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"


def test_arcnet_long_frame_padding():
    """
    Three trailing octets on a long frame are removed when they break
    decoding the APDU.  Padding that decodes as stray tags (like 00 00 77,
    0x77 is decoded as a closing tag) is ignored by the decoder instead.
    """
    npdu = npdu_long_read_property_ack()
    data = arcnet_linux(6, 1, LLC_BACNET + npdu + b"\x00\x00\x05")
    frame = decode_packet(data, LINKTYPE_ARCNET_LINUX)
    assert frame.arcnet.padding == b"\x00\x00\x05"
    assert frame.apdu.__class__.__name__ == "ReadPropertyACK"
    assert frame.apdu.propertyValue.cast_out(CharacterString) == "x" * 260
    assert frame.apdu.pduSource == ARCNETAddress(6)


def test_arcnet_short_frame_is_not_trimmed():
    """Short frames are never trimmed, a bad APDU stays undecoded."""
    data = arcnet_linux(6, 1, LLC_BACNET + NPDU_READ_PROPERTY_ACK + b"\x00\x00\x05")
    frame = decode_packet(data, LINKTYPE_ARCNET_LINUX)
    assert frame.arcnet.padding == b""
    assert type(frame.apdu) is ComplexAckPDU


def test_arcnet_long_frame_undecodable():
    """If trimming does not help the original frame is kept."""
    npdu = bytes.fromhex("0100 3001 0c") + b"\xff" * 300
    frame = decode_packet(arcnet_linux(6, 1, LLC_BACNET + npdu), LINKTYPE_ARCNET_LINUX)
    assert frame.arcnet.padding == b""
    assert type(frame.apdu) is ComplexAckPDU
    assert len(frame.apdu.pduData) == 300


#
#   APDUs that cannot be decoded keep their frame
#


def test_segment_is_not_decoded():
    """A segment of a ComplexACK is part of a ReadRange-ACK, not one."""
    npdu = bytes.fromhex("0100 3c2a0001 1a 0c05000003 1983") + b"\x0e" * 40
    frame = decode_packet(
        ipv4_udp(bytes.fromhex("810a") + struct.pack("!H", 4 + len(npdu)) + npdu),
        LINKTYPE_RAW,
    )
    assert type(frame.apdu) is ComplexAckPDU
    assert frame.apdu.apduSeg
    assert frame.apdu.apduMor
    assert frame.apdu.apduSeq == 0


def test_bad_apdu_keeps_frame():
    npdu = bytes.fromhex("0100 3001 0c 0c020001fe 3f")
    frame = decode_packet(
        ipv4_udp(bytes.fromhex("810a") + struct.pack("!H", 4 + len(npdu)) + npdu),
        LINKTYPE_RAW,
    )
    assert frame.udp is not None
    assert type(frame.apdu) is ComplexAckPDU


#
#   BACnet/Ethernet, 802.3 with LLC
#


def test_ethernet_llc():
    payload = LLC_BACNET + NPDU_WHO_IS
    data = (
        bytes.fromhex("ffffffffffff 020000000001")
        + struct.pack("!H", len(payload))
        + payload
    )
    data += b"\x00" * (60 - len(data))  # minimum frame size padding
    frame = decode_packet(data, LINKTYPE_ETHERNET)
    assert frame.ethernet.type == len(payload)
    assert frame.llc.data == NPDU_WHO_IS
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert frame.apdu.pduSource == Address("02:00:00:00:00:01")
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_linux_sll_llc():
    data = (
        struct.pack("!HHH8sH", 1, 1, 6, bytes.fromhex("020000000001") + b"\0\0", 0x0004)
        + LLC_BACNET
        + NPDU_WHO_IS
    )
    frame = decode_packet(data, LINKTYPE_LINUX_SLL)
    assert frame.apdu.__class__.__name__ == "WhoIsRequest"
    assert frame.apdu.pduSource == Address("02:00:00:00:00:01")
    assert isinstance(frame.apdu.pduDestination, LocalBroadcast)


def test_ethernet_not_bacnet():
    """A payload that starts with 0x01 is not an NPDU without UDP or LLC."""
    data = bytes.fromhex("ffffffffffff 020000000001 88b5") + NPDU_WHO_IS
    frame = decode_packet(data, LINKTYPE_ETHERNET)
    assert frame.ethernet.type == 0x88B5
    assert frame.llc is None
    assert frame.npci is None
