#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Analysis Addresses
-----------------------

Each header has only what its own fields say: the npci has "_source" and
"_destination" from SNET/SADR and DNET/DADR, and the apci has no addresses.  The
content of the NPDU, an APDU or a network layer message, has the end-to-end
source and destination: SADR and DADR when the header has them, otherwise
the link-level addresses.
"""

import json
import socket
import struct

import pytest

from bacpypes3.analysis import LINKTYPE_RAW, CustomJSONEncoder, decode_packet
from bacpypes3.pdu import GlobalBroadcast, IPv4Address, RemoteBroadcast, RemoteStation

from .test_linktypes import ipv4_udp

# I-Am device,1, max APDU 480, segmentation both, vendor 15
I_AM = bytes.fromhex("1000c4020000012201e09100210f")


def original_broadcast(npdu: bytes) -> bytes:
    return bytes.fromhex("810b") + struct.pack("!H", 4 + len(npdu)) + npdu


def forwarded(source: str, npdu: bytes) -> bytes:
    return (
        bytes.fromhex("8104")
        + struct.pack("!H", 10 + len(npdu))
        + socket.inet_aton(source)
        + struct.pack("!H", 47808)
        + npdu
    )


def decode(bvll: bytes, source: str = "10.0.1.1"):
    frame = decode_packet(ipv4_udp(source, "255.255.255.255", bvll), LINKTYPE_RAW)
    contents = json.loads(json.dumps(frame.dict_contents(), cls=CustomJSONEncoder))
    return frame, contents


def test_routed_apdu():
    """A Forwarded-NPDU with SNET 11651, SADR 02 and DNET 65535."""
    npdu = bytes.fromhex("0128ffff002d830102fe") + I_AM
    frame, contents = decode(forwarded("128.253.140.59", npdu))

    # the link-level source is the original source of the forwarded message
    assert frame.npci.pduSource == IPv4Address("128.253.140.59")

    npci = contents["npci"]
    assert (npci["_destination"], npci["_source"]) == ("*:*", "11651:2")
    assert list(npci).index("_destination") == list(npci).index("dadr") + 1
    assert list(npci).index("_source") == list(npci).index("sadr") + 1

    assert "source" not in contents["apci"]
    assert "destination" not in contents["apci"]

    apdu = contents["apdu"]
    assert list(apdu)[:2] == ["_source", "_destination"]
    assert apdu["_source"] == "11651:2"
    assert apdu["_destination"] == "*:*"
    assert apdu["function"] == "IAmRequest"


def test_local_apdu():
    frame, contents = decode(original_broadcast(bytes.fromhex("0100") + I_AM))
    assert "_source" not in contents["npci"]
    assert "_destination" not in contents["npci"]
    assert contents["apdu"]["_source"] == "10.0.1.1"
    assert contents["apdu"]["_destination"] == "*"


@pytest.mark.parametrize(
    "dnet_dlen_dadr, address_class, dnet, dlen, dadr, destination",
    [
        # DLEN 0 and a DNET other than 65535 is a remote broadcast
        ("2904 00", RemoteBroadcast, 10500, 0, "", "10500:*"),
        # DLEN 0 and DNET 65535 is a global broadcast
        ("ffff 00", GlobalBroadcast, 65535, 0, "", "*:*"),
        # a DLEN other than 0 is a remote station
        ("2904 01 07", RemoteStation, 10500, 1, "07", "10500:7"),
        (
            "0005 06 80fd6ddbbac0",
            RemoteStation,
            5,
            6,
            "80:fd:6d:db:ba:c0",
            "5:128.253.109.219",
        ),
    ],
)
def test_destination(dnet_dlen_dadr, address_class, dnet, dlen, dadr, destination):
    """The DNET/DLEN/DADR of a header without SNET/SADR, hop count 255."""
    npdu = bytes.fromhex("0120" + dnet_dlen_dadr.replace(" ", "") + "ff") + I_AM
    frame, contents = decode(original_broadcast(npdu))
    assert type(frame.npci.npduDADR) is address_class

    npci = contents["npci"]
    assert (npci["dnet"], npci["dlen"], npci["dadr"]) == (dnet, dlen, dadr)
    assert npci["_destination"] == destination
    assert list(npci).index("_destination") == list(npci).index("dadr") + 1
    assert "_source" not in npci
    assert npci["hop_count"] == 255

    # the end-to-end destination is the DADR, the source is the link-level
    # source because there is no SADR
    apdu = contents["apdu"]
    assert apdu["_destination"] == destination
    assert apdu["_source"] == "10.0.1.1"


def test_network_message_to_remote_station():
    """A Reject-Message-To-Network sent back to a remote station."""
    # version, control (DNET present), DNET 10500, DLEN 1, DADR 07, hop count,
    # Reject-Message-To-Network, reason 1, DNET 10500
    npdu = bytes.fromhex("01 a0 2904 01 07 ff 03 01 2904")
    frame, contents = decode(original_broadcast(npdu), source="10.0.1.20")
    assert frame.npdu.rmtnRejectionReason == 1
    assert frame.npdu.rmtnDNET == 10500
    assert frame.npdu.pduDestination == RemoteStation(10500, b"\x07")
    assert frame.npci.pduSource == IPv4Address("10.0.1.20")

    assert contents["npci"]["_destination"] == "10500:7"
    npdu_contents = contents["npdu"]
    assert npdu_contents["_destination"] == "10500:7"
    assert npdu_contents["_source"] == "10.0.1.20"

    # the routing header is only in the npci
    for key in ("dnet", "dlen", "dadr", "hop_count"):
        assert key not in npdu_contents


def test_i_am_router_to_network():
    """The router is the link-level source, there is no SADR."""
    npdu = bytes.fromhex("01800127252726")
    frame, contents = decode(original_broadcast(npdu), source="10.0.1.20")
    assert frame.npdu.iartnNetworkList == [10021, 10022]
    assert frame.npdu.pduSource == IPv4Address("10.0.1.20")
    assert frame.npdu.npduControl == 0x80

    npdu_contents = contents["npdu"]
    assert npdu_contents["_source"] == "10.0.1.20"
    assert npdu_contents["function"] == "IAmRouterToNetwork"
    assert npdu_contents["network_list"] == [10021, 10022]


def test_forwarded_who_is_router_to_network():
    """A request forwarded by a router has the originator in SNET/SADR."""
    npdu = (
        bytes.fromhex("0188000506")
        + socket.inet_aton("10.0.5.9")
        + bytes.fromhex("bac0002825")
    )
    frame, contents = decode(original_broadcast(npdu), source="10.0.1.20")
    assert frame.npdu.wirtnNetwork == 10277
    assert str(frame.npdu.pduSource) == "5:10.0.5.9"
    assert frame.npci.pduSource == IPv4Address("10.0.1.20")

    assert contents["npci"]["_source"] == "5:10.0.5.9"
    npdu_contents = contents["npdu"]
    assert npdu_contents["_source"] == "5:10.0.5.9"

    # the routing header is only in the npci
    assert "snet" not in npdu_contents
    assert "sadr" not in npdu_contents
