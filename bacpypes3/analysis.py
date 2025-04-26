#!/usr/bin/python

"""
Analysis - Decoding pcap files and packets
"""

import time
import socket
import struct
from dataclasses import dataclass
from typing import Optional

from .settings import settings
from .debugging import ModuleLogger, bacpypes_debugging, btox

from .pdu import PDU, Address
from .ipv4.bvll import (
    LPDU,
    pdu_types as bvll_pdu_types,
    DistributeBroadcastToNetwork,
    OriginalUnicastNPDU,
    OriginalBroadcastNPDU,
)
from .npdu import NPDU, npdu_types
from .apdu import (
    APDU,
    APCISequence,
    ConfirmedRequestPDU,
    UnconfirmedRequestPDU,
    ComplexAckPDU,
)

pylibpcap = None
try:
    import pylibpcap
except ImportError:
    pass

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# protocol map
_protocols = {
    socket.IPPROTO_TCP: "tcp",
    socket.IPPROTO_UDP: "udp",
    socket.IPPROTO_ICMP: "icmp",
}


def strftimestamp(ts):
    return time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(ts)) + (
        ".%06d" % ((ts - int(ts)) * 1000000,)
    )


@dataclass
class Ethernet:
    """Class for keeping track of an item in inventory."""

    destination_address: str
    source_address: str
    type: int
    data: bytes


@bacpypes_debugging
def decode_ethernet(s) -> Ethernet:
    """Decode the Ethernet header."""
    if _debug:
        decode_ethernet._debug("decode_ethernet %s...", btox(s[:14], "."))

    d = Ethernet(
        destination_address=btox(s[0:6], ":"),
        source_address=btox(s[6:12], ":"),
        type=struct.unpack("!H", s[12:14])[0],
        data=s[14:],
    )

    return d


@dataclass
class VLAN:
    priority: int
    cfi: int
    vlan: int
    type: int
    data: bytes


@bacpypes_debugging
def decode_vlan(s) -> VLAN:
    """Decode the VLAN header."""
    if _debug:
        decode_vlan._debug("decode_vlan %s...", btox(s[:4]))

    x = struct.unpack("!H", s[0:2])[0]
    d = VLAN(
        priority=(x >> 13) & 0x07,
        cfi=(x >> 12) & 0x01,
        vlan=x & 0x0FFF,
        type=struct.unpack("!H", s[2:4])[0],
        data=s[4:],
    )

    return d


@dataclass
class IPv4:
    version: int
    header_len: int
    tos: int
    total_len: int
    id: int
    flags: int
    fragment_offset: int
    ttl: int
    protocol: str
    checksum: int
    source_address: str
    destination_address: str
    options: bytes
    data: bytes


@bacpypes_debugging
def decode_ipv4(s) -> IPv4:
    """Decode the IPv4 header."""
    if _debug:
        decode_ipv4._debug("decode_ipv4 %r", btox(s[:20], "."))

    header_len = s[0] & 0x0F
    d = IPv4(
        version=(s[0] & 0xF0) >> 4,
        header_len=header_len,
        tos=s[1],
        total_len=struct.unpack("!H", s[2:4])[0],
        id=struct.unpack("!H", s[4:6])[0],
        flags=(s[6] & 0xE0) >> 5,
        fragment_offset=struct.unpack("!H", s[6:8])[0] & 0x1F,
        ttl=s[8],
        protocol=_protocols.get(s[9], "0x%.2x ?" % s[9]),
        checksum=struct.unpack("!H", s[10:12])[0],
        source_address=socket.inet_ntoa(s[12:16]),
        destination_address=socket.inet_ntoa(s[16:20]),
        options=s[20 : 4 * (header_len - 5)] if header_len > 5 else None,
        data=s[4 * header_len :],
    )

    return d


@dataclass
class UDP:
    source_port: int
    destination_port: int
    length: int
    checksum: int
    data: bytes


@bacpypes_debugging
def decode_udp(s):
    if _debug:
        decode_udp._debug("decode_udp %s...", btox(s[:8]))

    d = UDP(
        source_port=struct.unpack("!H", s[0:2])[0],
        destination_port=struct.unpack("!H", s[2:4])[0],
        length=struct.unpack("!H", s[4:6])[0],
        checksum=struct.unpack("!H", s[6:8])[0],
        data=s[8 : 8 + struct.unpack("!H", s[4:6])[0] - 8],
    )

    return d


@dataclass
class Frame:
    ethernet: Optional[Ethernet] = None
    vlan: Optional[VLAN] = None
    ipv4: Optional[IPv4] = None
    udp: Optional[UDP] = None
    bvlci: Optional[LPDU] = None
    npci: Optional[NPDU] = None
    npdu: Optional[NPDU] = None
    apci: Optional[APDU] = None
    apdu: Optional[APDU] = None


@bacpypes_debugging
def decode_packet(data: bytes) -> Optional[Frame]:
    """Decode the data, return a Frame object or None."""
    if _debug:
        decode_packet._debug("decode_packet %r", data)

    # empty strings are some other kind of pcap content
    if not data:
        return None

    # a place to stuff everything
    frame = Frame()

    # assume it is ethernet for now
    ethernet = decode_ethernet(data)
    pduSource = Address(ethernet.source_address)
    pduDestination = Address(ethernet.destination_address)
    data = ethernet.data

    # save the header
    frame.ethernet = ethernet

    ethernet_type: int = ethernet.type

    # there could be a VLAN header
    if ethernet_type == 0x8100:
        if _debug:
            decode_packet._debug("    - vlan found")

        vlan = decode_vlan(data)
        data = vlan.data

        # save the header
        frame.vlan = vlan

        ethernet_type = vlan.type

    # look for IP packets
    if ethernet_type == 0x0800:
        if _debug:
            decode_packet._debug("    - IP found")

        ipv4 = decode_ipv4(data)
        pduSource, pduDestination = (
            ipv4.source_address,
            ipv4.destination_address,
        )
        data = ipv4.data

        # save the header
        frame.ipv4 = ipv4

        # check for a UDP packet
        if ipv4.protocol == "udp":
            if _debug:
                decode_packet._debug("    - UDP found")

            udp = decode_udp(data)
            data = udp.data

            # save the header
            frame.udp = udp

            pduSource = Address((pduSource, udp.source_port))
            pduDestination = Address((pduDestination, udp.destination_port))
            if _debug:
                decode_packet._debug("    - pduSource: %r", pduSource)
                decode_packet._debug("    - pduDestination: %r", pduDestination)
        else:
            if _debug:
                decode_packet._debug("    - not a UDP packet")
    else:
        if _debug:
            decode_packet._debug("    - not an IP packet")

    # check for empty
    if not data:
        if _debug:
            decode_packet._debug("    - empty packet")
        return frame

    # build a PDU, consumed by the decode functions
    pdu = PDU(data)  # , source=pduSource, destination=pduDestination

    # check for a BVLL header
    if pdu.pduData[0] == 0x81:
        if _debug:
            decode_packet._debug("    - BVLL header found")

        try:
            bvlci = LPDU.decode(pdu)
            frame.bvlci = bvlci
        except Exception as err:
            if _debug:
                decode_packet._debug("    - BVLL PDU decoding error: %r", err)
            return frame

        # make a more focused interpretation
        atype = bvll_pdu_types.get(bvlci.bvlciFunction, None)
        if not atype:
            if _debug:
                decode_packet._debug("    - unknown BVLL type: %r", bvlci.bvlciFunction)
            return frame

        # decode it as one of the basic types
        try:
            bvll = atype.decode(bvlci)
            frame.bvll = bvll

            # no deeper decoding for some
            if atype not in (
                DistributeBroadcastToNetwork,
                OriginalUnicastNPDU,
                OriginalBroadcastNPDU,
            ):
                return frame
        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding Error: %r", err)
            return pdu

    # check for version number
    if pdu.pduData[0] != 0x01:
        if _debug:
            decode_packet._debug(
                "    - not a version 1 packet: %s...", btox(pdu.pduData[:30], ".")
            )
        return frame

    # it's an NPDU
    try:
        npci = NPDU.decode(pdu)
        frame.npci = npci
    except Exception as err:
        if _debug:
            decode_packet._debug("    - NPDU decoding Error: %r", err)
        return frame
    if _debug:
        decode_packet._debug("    - npci: %r", npci)

    # application or network layer message
    if npci.npduNetMessage is None:
        if _debug:
            decode_packet._debug("    - not a network layer message, try as an APDU")

        # decode as a generic APDU
        try:
            apci = APDU.decode(npci)
            frame.apci = apci
        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding Error: %r", err)
            return frame

        if not isinstance(
            apci, (ConfirmedRequestPDU, ComplexAckPDU, UnconfirmedRequestPDU)
        ):
            return frame

        try:
            apdu = APCISequence.decode(apci)
            frame.apdu = apdu
            if _debug:
                decode_packet._debug("    - apdu: %r", apdu)
        except AttributeError as err:
            if _debug:
                decode_packet._debug("    - decoding error: %r", err)

        # success
        return frame

    else:
        # make a more focused interpretation
        ntype = npdu_types.get(npci.npduNetMessage, None)
        if not ntype:
            if _debug:
                decode_packet._debug(
                    "    - no network layer decoder: %r", npci.npduNetMessage
                )
            return frame
        if _debug:
            decode_packet._debug("    - ntype: %r", ntype)

        # deeper decoding
        try:
            npdu = ntype.decode(npci)
            frame.npdu = npdu
        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding error: %r", err)

        # success
        return frame


@bacpypes_debugging
def decode_file(fname):
    """Given the name of a pcap file, open it, decode the contents and yield each packet."""
    if _debug:
        decode_file._debug("decode_file %r", fname)

    if not pylibpcap:
        raise RuntimeError("failed to import pylibpcap")

    p = pylibpcap.pcap.rpcap(fname)

    # loop through the packets
    for i, (len, timestamp, data) in enumerate(p):
        try:
            frame = decode_packet(data)
            if not frame:
                continue
        except Exception as err:
            if _debug:
                decode_file._debug("    - exception decoding packet %d: %r", i + 1, err)
            continue

        # save the packet number (as viewed in Wireshark) and timestamp
        frame._number = i + 1
        frame._timestamp = timestamp

        yield frame


@bacpypes_debugging
class Tracer:

    def __init__(self, initial_state=None):
        if _debug:
            Tracer._debug("__init__ initial_state=%r", initial_state)

        # set the current state to the initial state
        self.next(initial_state or self.start)

    def next(self, fn):
        if _debug:
            Tracer._debug("next %r", fn)

        # set the state
        self.current_state = fn

    def start(self, pkt):
        if _debug:
            Tracer._debug("start %r", pkt)


@bacpypes_debugging
def trace(fname, tracers):
    if _debug:
        trace._debug("trace %r %r", fname, tracers)

    # make a list of tracers
    current_tracers = [traceClass() for traceClass in tracers]

    # decode the file
    for pkt in decode_file(fname):
        for i, tracer in enumerate(current_tracers):
            # give the packet to the tracer
            tracer.current_state(pkt)

            # if there is no current state, make a new one
            if not tracer.current_state:
                current_tracers[i] = tracers[i]()


if __name__ == "__main__":
    try:
        from bacpypes3.argparse import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument(
            "filename",
            nargs="+",
            help="the names of the pcaps file to decode",
        )
        args = parser.parse_args()
        _log.debug("args: %r", args)
        _log.debug("settings: %r", settings)

        for fname in args.filename:
            _log.debug("decode_file %r", fname)
            for frame in decode_file(fname):
                print(strftimestamp(frame._timestamp))
                if frame.ethernet:
                    print("  Ethernet: %s" % frame.ethernet)
                if frame.vlan:
                    print("  VLAN: %s" % frame.vlan)
                if frame.ipv4:
                    print("  IPv4: %s" % frame.ipv4)
                if frame.udp:
                    print("  UDP: %s" % frame.udp)
                if frame.bvlci:
                    print("  BVLCI: %s" % frame.bvlci)
                    frame.bvlci.debug_contents()
                if frame.bvll:
                    print("  BVLL: %s" % frame.bvll)
                    frame.bvll.debug_contents()
                if frame.npci:
                    print("  NPDU: %s" % frame.npci)
                    frame.npci.debug_contents()
                if frame.npdu:
                    print("  NPDU: %s" % frame.npdu)
                    frame.npdu.debug_contents()
                if frame.apci:
                    print("  APCI: %s" % frame.apci)
                    frame.apci.debug_contents()
                if frame.apdu:
                    print("  APDU: %s" % frame.apdu)
                    frame.apdu.debug_contents()

    except KeyboardInterrupt:
        pass
    except Exception as err:
        _log.exception("an error has occurred: %s", err)
    finally:
        _log.debug("finally")
