#!/usr/bin/python

"""
Analysis - Decoding pcap files and packets
"""

import time
import socket
import struct

from .settings import settings
from .debugging import ModuleLogger, bacpypes_debugging, btox

from .pdu import PDU, Address
from .ipv4.bvll import (
    LPDU,
    pdu_types as bvll_pdu_types,
    ForwardedNPDU,
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


@bacpypes_debugging
def decode_ethernet(s):
    if _debug:
        decode_ethernet._debug("decode_ethernet %s...", btox(s[:14], "."))

    d = {}
    d["destination_address"] = btox(s[0:6], ":")
    d["source_address"] = btox(s[6:12], ":")
    d["type"] = struct.unpack("!H", s[12:14])[0]
    d["data"] = s[14:]

    return d


@bacpypes_debugging
def decode_vlan(s):
    if _debug:
        decode_vlan._debug("decode_vlan %s...", btox(s[:4]))

    d = {}
    x = struct.unpack("!H", s[0:2])[0]
    d["priority"] = (x >> 13) & 0x07
    d["cfi"] = (x >> 12) & 0x01
    d["vlan"] = x & 0x0FFF
    d["type"] = struct.unpack("!H", s[2:4])[0]
    d["data"] = s[4:]

    return d


@bacpypes_debugging
def decode_ip(s):
    if _debug:
        decode_ip._debug("decode_ip %r", btox(s[:20], "."))

    d = {}
    d["version"] = (s[0] & 0xF0) >> 4
    d["header_len"] = s[0] & 0x0F
    d["tos"] = s[1]
    d["total_len"] = struct.unpack("!H", s[2:4])[0]
    d["id"] = struct.unpack("!H", s[4:6])[0]
    d["flags"] = (s[6] & 0xE0) >> 5
    d["fragment_offset"] = struct.unpack("!H", s[6:8])[0] & 0x1F
    d["ttl"] = s[8]
    d["protocol"] = _protocols.get(s[9], "0x%.2x ?" % s[9])
    d["checksum"] = struct.unpack("!H", s[10:12])[0]
    d["source_address"] = socket.inet_ntoa(s[12:16])
    d["destination_address"] = socket.inet_ntoa(s[16:20])
    if d["header_len"] > 5:
        d["options"] = s[20 : 4 * (d["header_len"] - 5)]
    else:
        d["options"] = None
    d["data"] = s[4 * d["header_len"] :]

    return d


@bacpypes_debugging
def decode_udp(s):
    if _debug:
        decode_udp._debug("decode_udp %s...", btox(s[:8]))

    d = {}
    d["source_port"] = struct.unpack("!H", s[0:2])[0]
    d["destination_port"] = struct.unpack("!H", s[2:4])[0]
    d["length"] = struct.unpack("!H", s[4:6])[0]
    d["checksum"] = struct.unpack("!H", s[6:8])[0]
    d["data"] = s[8 : 8 + d["length"] - 8]

    return d


@bacpypes_debugging
def decode_packet(data):
    """decode the data, return some kind of PDU."""
    if _debug:
        decode_packet._debug("decode_packet %r", data)

    # empty strings are some other kind of pcap content
    if not data:
        return None

    # assume it is ethernet for now
    d = decode_ethernet(data)
    pduSource = Address(d["source_address"])
    pduDestination = Address(d["destination_address"])
    data = d["data"]

    # there could be a VLAN header
    if d["type"] == 0x8100:
        if _debug:
            decode_packet._debug("    - vlan found")

        d = decode_vlan(data)
        data = d["data"]

    # look for IP packets
    if d["type"] == 0x0800:
        if _debug:
            decode_packet._debug("    - IP found")

        d = decode_ip(data)
        pduSource, pduDestination = d["source_address"], d["destination_address"]
        data = d["data"]

        if d["protocol"] == "udp":
            if _debug:
                decode_packet._debug("    - UDP found")

            d = decode_udp(data)
            data = d["data"]

            pduSource = Address((pduSource, d["source_port"]))
            pduDestination = Address((pduDestination, d["destination_port"]))
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
        return None

    # build a PDU
    pdu = PDU(data, source=pduSource, destination=pduDestination)

    # check for a BVLL header
    if pdu.pduData[0] == 0x81:
        if _debug:
            decode_packet._debug("    - BVLL header found")

        try:
            pdu = LPDU.decode(pdu)
        except Exception as err:
            if _debug:
                decode_packet._debug("    - BVLL PDU decoding error: %r", err)
            return pdu

        # make a more focused interpretation
        atype = bvll_pdu_types.get(pdu.bvlciFunction)
        if not atype:
            if _debug:
                decode_packet._debug("    - unknown BVLL type: %r", pdu.bvlciFunction)
            return pdu

        # decode it as one of the basic types
        try:
            xpdu = pdu
            bpdu = atype()
            pdu = atype.decode(pdu)
            if _debug:
                decode_packet._debug("    - bpdu: %r", bpdu)

            # lift the address for forwarded NPDU's
            if atype is ForwardedNPDU:
                old_pdu_source = pdu.pduSource
                pdu.pduSource = bpdu.bvlciAddress
                if settings.route_aware:
                    pdu.pduSource.addrRoute = old_pdu_source
            # no deeper decoding for some
            elif atype not in (
                DistributeBroadcastToNetwork,
                OriginalUnicastNPDU,
                OriginalBroadcastNPDU,
            ):
                return pdu

        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding Error: %r", err)
            return xpdu

    # check for version number
    if pdu.pduData[0] != 0x01:
        if _debug:
            decode_packet._debug(
                "    - not a version 1 packet: %s...", btox(pdu.pduData[:30], ".")
            )
        return None

    # it's an NPDU
    try:
        npdu = NPDU.decode(pdu)
    except Exception as err:
        if _debug:
            decode_packet._debug("    - NPDU decoding Error: %r", err)
        return None
    if _debug:
        decode_packet._debug("    - npdu: %r", npdu)

    # application or network layer message
    if npdu.npduNetMessage is None:
        if _debug:
            decode_packet._debug("    - not a network layer message, try as an APDU")

        # decode as a generic APDU
        try:
            apdu = APDU.decode(npdu)
        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding Error: %r", err)
            return npdu

        # "lift" the source and destination address
        if npdu.npduSADR:
            apdu.pduSource = npdu.npduSADR
            if settings.route_aware:
                apdu.pduSource.addrRoute = npdu.pduSource
        else:
            apdu.pduSource = npdu.pduSource
        if npdu.npduDADR:
            apdu.pduDestination = npdu.npduDADR
        else:
            apdu.pduDestination = npdu.pduDestination

        if isinstance(
            apdu, (ConfirmedRequestPDU, ComplexAckPDU, UnconfirmedRequestPDU)
        ):
            try:
                apdu = APCISequence.decode(apdu)
                if _debug:
                    decode_packet._debug("    - apdu: %r", apdu)
            except AttributeError as err:
                if _debug:
                    decode_packet._debug("    - decoding error: %r", err)

        # success
        return apdu

    else:
        # make a more focused interpretation
        ntype = npdu_types.get(npdu.npduNetMessage)
        if not ntype:
            if _debug:
                decode_packet._debug(
                    "    - no network layer decoder: %r", npdu.npduNetMessage
                )
            return npdu
        if _debug:
            decode_packet._debug("    - ntype: %r", ntype)

        # deeper decoding
        try:
            npdu = ntype.decode(npdu)
        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding error: %r", err)

        # success
        return npdu


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
            pkt = decode_packet(data)
            if not pkt:
                continue
        except Exception as err:
            if _debug:
                decode_file._debug("    - exception decoding packet %d: %r", i + 1, err)
            continue

        # save the packet number (as viewed in Wireshark) and timestamp
        pkt._number = i + 1
        pkt._timestamp = timestamp

        yield pkt


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
            for pkt in decode_file(fname):
                print(strftimestamp(pkt._timestamp), pkt.__class__.__name__)
                pkt.debug_contents()
                print("")

    except KeyboardInterrupt:
        pass
    except Exception as err:
        _log.exception("an error has occurred: %s", err)
    finally:
        _log.debug("finally")
