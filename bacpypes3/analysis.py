#!/usr/bin/python

"""
Analysis - Decoding pcap files and packets
"""

import time
import socket
import struct
import json
import warnings
import functools
import traceback

from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Tuple,
    Union,
)

from .settings import settings
from .debugging import ModuleLogger, bacpypes_debugging, btox

from .errors import DecodingError
from .pdu import PDU, Address, LocalBroadcast, IPv4Address, IPv6Address
from .ipv4.bvll import (
    LPCI,
    LPDU,
    pdu_types as bvll_pdu_types,
    DistributeBroadcastToNetwork,
    OriginalUnicastNPDU,
    OriginalBroadcastNPDU,
    ForwardedNPDU,
)
from .ipv6 import bvll as bvll6
from .npdu import NPCI, NPDU, npdu_types
from .apdu import (
    APDU,
    APCI,
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
    socket.IPPROTO_ICMPV6: "icmpv6",
}

# IPv6 extension headers that can come between the fixed header and the
# upper-layer protocol: hop-by-hop options, routing, fragment, destination
# options
_IPV6_FRAGMENT = 44
_ipv6_extension_headers = (0, 43, _IPV6_FRAGMENT, 60)
_ethernet_broadcast_address = Address("FF:FF:FF:FF:FF:FF")

# link-layer header types, https://www.tcpdump.org/linktypes.html
LINKTYPE_NULL = 0  # BSD loopback, 4-byte address family in host byte order
LINKTYPE_ETHERNET = 1
LINKTYPE_RAW = 101  # raw IPv4/IPv6, e.g. tun interfaces
LINKTYPE_LOOP = 108  # OpenBSD loopback, 4-byte address family in network order
LINKTYPE_LINUX_SLL = 113  # Linux "cooked" capture v1, e.g. the "any" interface
LINKTYPE_IPV4 = 228
LINKTYPE_IPV6 = 229
LINKTYPE_LINUX_SLL2 = 276  # Linux "cooked" capture v2

# DLT_RAW is 12 (14 on OpenBSD), older files carry those values
_raw_ip_linktypes = (LINKTYPE_RAW, LINKTYPE_IPV4, LINKTYPE_IPV6, 12, 14)

linktypes: Dict[str, int] = {
    "null": LINKTYPE_NULL,
    "ethernet": LINKTYPE_ETHERNET,
    "raw": LINKTYPE_RAW,
    "loop": LINKTYPE_LOOP,
    "linux-sll": LINKTYPE_LINUX_SLL,
    "ipv4": LINKTYPE_IPV4,
    "ipv6": LINKTYPE_IPV6,
    "linux-sll2": LINKTYPE_LINUX_SLL2,
}
_supported_linktypes = set(linktypes.values()) | set(_raw_ip_linktypes)

# AF_INET6 for the NULL/LOOP link types depends on the capturing OS: Linux,
# NetBSD/OpenBSD, FreeBSD, macOS
_null_af_inet6 = (10, 24, 28, 30)

# Linux packet types from the cooked header (<linux/if_packet.h>)
_PACKET_BROADCAST = 1

# Linux ARPHRD_* interface types to link-layer types
_arphrd_linktypes = {
    1: LINKTYPE_ETHERNET,  # ARPHRD_ETHER
    772: LINKTYPE_ETHERNET,  # ARPHRD_LOOPBACK, libpcap fakes Ethernet
    65534: LINKTYPE_RAW,  # ARPHRD_NONE, tun interfaces
}


def pcap_file_linktype(fname: str) -> int:
    """
    Return the link-layer header type of a pcap or pcapng file by reading its
    header.  The pylibpcap reader does not expose pcap_datalink().
    """
    with open(fname, "rb") as f:
        header = f.read(24)
        if len(header) < 24:
            raise ValueError(f"{fname}: not a pcap or pcapng file")

        # classic pcap, microsecond or nanosecond timestamps, either byte order
        magic = header[:4]
        if magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
            return struct.unpack("!I", header[20:24])[0] & 0xFFFF
        if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
            return struct.unpack("<I", header[20:24])[0] & 0xFFFF

        # pcapng starts with a Section Header Block with a byte order magic
        if magic != b"\x0a\x0d\x0d\x0a":
            raise ValueError(f"{fname}: not a pcap or pcapng file")
        if header[8:12] == b"\x1a\x2b\x3c\x4d":
            endian = "!"
        elif header[8:12] == b"\x4d\x3c\x2b\x1a":
            endian = "<"
        else:
            raise ValueError(f"{fname}: invalid pcapng byte order magic")

        # walk the blocks looking for the first Interface Description Block,
        # libpcap requires all interfaces in a file share the same link type
        f.seek(0)
        while True:
            block_header = f.read(12)
            if len(block_header) < 12:
                raise ValueError(f"{fname}: no pcapng interface description block")
            block_type, block_length = struct.unpack(endian + "II", block_header[:8])
            if block_type == 1:
                return struct.unpack(endian + "H", block_header[8:10])[0]
            if block_length < 12:
                raise ValueError(f"{fname}: invalid pcapng block length")
            f.seek(block_length - 12, 1)


def iface_linktype(iface: str) -> Optional[int]:
    """
    Return the link-layer header type libpcap will use for a live capture on
    an interface, or None if it cannot be determined (Linux only).
    """
    if iface == "any":
        return LINKTYPE_LINUX_SLL
    try:
        with open(f"/sys/class/net/{iface}/type") as f:
            return _arphrd_linktypes.get(int(f.read().strip()))
    except (OSError, ValueError):
        return None


def strftimestamp(ts):
    return time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(ts)) + (
        ".%06d" % ((ts - int(ts)) * 1000000,)
    )


class ExperimentalWarning(UserWarning):
    """Warning for experimental APIs."""

    pass


def experimental(func: Callable) -> Callable:
    """Decorator to mark a method as experimental."""

    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{func.__qualname__} is experimental and subject to change",
            ExperimentalWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)

    # Preserve function metadata
    return functools.update_wrapper(wrapper, func)


@dataclass
class Ethernet:
    """Class for keeping track of an item in inventory."""

    destination_address: str
    source_address: str
    type: int
    data: bytes

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        *,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
        include_data: Optional[bool] = True,
    ):
        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        use_dict.__setitem__("destination_address", self.destination_address)
        use_dict.__setitem__("source_address", self.source_address)
        use_dict.__setitem__("type", self.type)

        if include_data:
            use_dict.__setitem__("data", self.data)

        # return what we built/updated
        return use_dict


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

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        *,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
        include_data: Optional[bool] = True,
    ):
        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        use_dict.__setitem__("priority", self.priority)
        use_dict.__setitem__("cfi", self.cfi)
        use_dict.__setitem__("vlan", self.vlan)
        use_dict.__setitem__("type", self.type)

        if include_data:
            use_dict.__setitem__("data", self.data)

        # return what we built/updated
        return use_dict


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

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        *,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
        include_data: Optional[bool] = True,
    ):
        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        use_dict.__setitem__("version", self.version)
        use_dict.__setitem__("header_len", self.header_len)
        use_dict.__setitem__("tos", self.tos)
        use_dict.__setitem__("total_len", self.total_len)
        use_dict.__setitem__("id", self.id)
        use_dict.__setitem__("flags", self.flags)
        use_dict.__setitem__("fragment_offset", self.fragment_offset)
        use_dict.__setitem__("ttl", self.ttl)
        use_dict.__setitem__("protocol", self.protocol)
        use_dict.__setitem__("checksum", self.checksum)
        use_dict.__setitem__("source_address", self.source_address)
        use_dict.__setitem__("destination_address", self.destination_address)
        if self.options is not None:
            use_dict.__setitem__("options", self.options)

        if include_data:
            use_dict.__setitem__("data", self.data)

        # return what we built/updated
        return use_dict


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
        fragment_offset=struct.unpack("!H", s[6:8])[0] & 0x1FFF,
        ttl=s[8],
        protocol=_protocols.get(s[9], "0x%.2x ?" % s[9]),
        checksum=struct.unpack("!H", s[10:12])[0],
        source_address=socket.inet_ntoa(s[12:16]),
        destination_address=socket.inet_ntoa(s[16:20]),
        options=s[20 : 4 * header_len] if header_len > 5 else None,
        data=s[4 * header_len :],
    )

    return d


@dataclass
class IPv6:
    version: int
    traffic_class: int
    flow_label: int
    payload_len: int
    next_header: int
    hop_limit: int
    source_address: str
    destination_address: str
    extension_headers: List[int]
    protocol: str
    fragment_offset: int
    data: bytes

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        *,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
        include_data: Optional[bool] = True,
    ):
        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        use_dict.__setitem__("version", self.version)
        use_dict.__setitem__("traffic_class", self.traffic_class)
        use_dict.__setitem__("flow_label", self.flow_label)
        use_dict.__setitem__("payload_len", self.payload_len)
        use_dict.__setitem__("next_header", self.next_header)
        use_dict.__setitem__("hop_limit", self.hop_limit)
        use_dict.__setitem__("source_address", self.source_address)
        use_dict.__setitem__("destination_address", self.destination_address)
        if self.extension_headers:
            use_dict.__setitem__("extension_headers", self.extension_headers)
            use_dict.__setitem__("fragment_offset", self.fragment_offset)
        use_dict.__setitem__("protocol", self.protocol)

        if include_data:
            use_dict.__setitem__("data", self.data)

        # return what we built/updated
        return use_dict


@bacpypes_debugging
def decode_ipv6(s) -> IPv6:
    """
    Decode the IPv6 header and skip over any extension headers.  The protocol
    is the upper-layer protocol, the data is its payload.
    """
    if _debug:
        decode_ipv6._debug("decode_ipv6 %r", btox(s[:40], "."))

    x = struct.unpack("!I", s[0:4])[0]
    payload_len = struct.unpack("!H", s[4:6])[0]
    next_header = s[6]

    # a zero payload length is a jumbogram, the length is in an option
    data = s[40 : 40 + payload_len] if payload_len else s[40:]

    # walk the extension header chain
    extension_headers: List[int] = []
    fragment_offset = 0
    protocol = next_header
    while (protocol in _ipv6_extension_headers) and (len(data) >= 8):
        extension_headers.append(protocol)
        if protocol == _IPV6_FRAGMENT:
            fragment_offset = struct.unpack("!H", data[2:4])[0] >> 3
            header_len = 8
        else:
            header_len = (data[1] + 1) * 8
        protocol = data[0]
        data = data[header_len:]

        # a later fragment does not start with the upper-layer header
        if fragment_offset:
            break

    d = IPv6(
        version=x >> 28,
        traffic_class=(x >> 20) & 0xFF,
        flow_label=x & 0xFFFFF,
        payload_len=payload_len,
        next_header=next_header,
        hop_limit=s[7],
        source_address=socket.inet_ntop(socket.AF_INET6, s[8:24]),
        destination_address=socket.inet_ntop(socket.AF_INET6, s[24:40]),
        extension_headers=extension_headers,
        protocol=_protocols.get(protocol, "0x%.2x ?" % protocol),
        fragment_offset=fragment_offset,
        data=data,
    )

    return d


@dataclass
class UDP:
    source_port: int
    destination_port: int
    length: int
    checksum: int
    data: bytes

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        *,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
        include_data: Optional[bool] = True,
    ):
        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        use_dict.__setitem__("source_port", self.source_port)
        use_dict.__setitem__("destination_port", self.destination_port)
        use_dict.__setitem__("length", self.length)
        use_dict.__setitem__("checksum", self.checksum)

        if include_data:
            use_dict.__setitem__("data", self.data)

        # return what we built/updated
        return use_dict


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
    ipv6: Optional[IPv6] = None
    udp: Optional[UDP] = None
    bvlci: Optional[LPCI] = None
    bvll: Optional[LPDU] = None
    npci: Optional[NPCI] = None
    npdu: Optional[NPDU] = None
    apci: Optional[APCI] = None
    apdu: Optional[APDU] = None

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        *,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
        include_data: Optional[bool] = True,
    ):
        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        for attr in (
            "ethernet",
            "vlan",
            "ipv4",
            "ipv6",
            "udp",
            "bvlci",
            "bvll",
            "npci",
            "npdu",
            "apci",
            "apdu",
        ):
            v = getattr(self, attr)
            if v is not None:
                use_dict.__setitem__(
                    attr, v.dict_contents(as_class=as_class, include_data=include_data)
                )

        # return what we built/updated
        return use_dict


@bacpypes_debugging
def decode_packet(data: bytes, linktype: int = LINKTYPE_ETHERNET) -> Optional[Frame]:
    """
    Decode the data, return a Frame object or None.  The linktype is the
    link-layer header type of the capture (see pcap_file_linktype()).
    """
    if _debug:
        decode_packet._debug("decode_packet %r linktype=%r", data, linktype)

    # empty strings are some other kind of pcap content
    if not data:
        return None

    # a place to stuff everything
    frame = Frame()

    # addresses are filled in from the link layer and/or IP/UDP headers
    pduSource: Optional[Address] = None
    pduDestination: Optional[Address] = None
    ethernet_type: Optional[int] = None

    if linktype == LINKTYPE_ETHERNET:
        ethernet = decode_ethernet(data)
        data = ethernet.data

        # basic source and destination
        pduSource = Address(ethernet.source_address)
        if ethernet.destination_address == "ff:ff:ff:ff:ff:ff":
            pduDestination = LocalBroadcast()
        else:
            pduDestination = Address(ethernet.destination_address)

        # save the header
        frame.ethernet = ethernet
        ethernet_type = ethernet.type

    elif linktype in _raw_ip_linktypes:
        # no link-layer header, the IP version is in the first nibble
        version = data[0] >> 4
        if version == 4:
            ethernet_type = 0x0800
        elif version == 6:
            ethernet_type = 0x86DD

    elif linktype in (LINKTYPE_NULL, LINKTYPE_LOOP):
        # the byte order depends on the type and (for NULL) the capturing
        # host, so accept either, AF_INET is 2 everywhere
        family = struct.unpack("<I", data[:4])[0]
        if family > 0xFFFF:
            family = struct.unpack("!I", data[:4])[0]
        if family == socket.AF_INET:
            ethernet_type = 0x0800
        elif family in _null_af_inet6:
            ethernet_type = 0x86DD
        data = data[4:]

    elif linktype == LINKTYPE_LINUX_SLL:
        packet_type = struct.unpack("!H", data[0:2])[0]
        ethernet_type = struct.unpack("!H", data[14:16])[0]
        if packet_type == _PACKET_BROADCAST:
            pduDestination = LocalBroadcast()
        data = data[16:]

    elif linktype == LINKTYPE_LINUX_SLL2:
        ethernet_type = struct.unpack("!H", data[0:2])[0]
        if data[10] == _PACKET_BROADCAST:
            pduDestination = LocalBroadcast()
        data = data[20:]

    else:
        raise DecodingError(f"unsupported link type: {linktype}")

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
    ip: Union[IPv4, IPv6, None] = None
    if ethernet_type == 0x0800:
        if _debug:
            decode_packet._debug("    - IPv4 found")

        ip = frame.ipv4 = decode_ipv4(data)
    elif ethernet_type == 0x86DD:
        if _debug:
            decode_packet._debug("    - IPv6 found")

        ip = frame.ipv6 = decode_ipv6(data)
    else:
        if _debug:
            decode_packet._debug("    - not an IP packet")

    if ip:
        data = ip.data

        # check for a UDP packet, later fragments do not have a UDP header
        if ip.protocol != "udp":
            if _debug:
                decode_packet._debug("    - not a UDP packet")
        elif ip.fragment_offset:
            if _debug:
                decode_packet._debug("    - not the first fragment")
        else:
            if _debug:
                decode_packet._debug("    - UDP found")

            udp = decode_udp(data)
            data = udp.data

            # update the source and destination
            if isinstance(ip, IPv4):
                pduSource = IPv4Address((ip.source_address, udp.source_port))

                # without a MAC address the limited broadcast address is the
                # only broadcast that is certain
                if (frame.ethernet is None) and (
                    ip.destination_address == "255.255.255.255"
                ):
                    pduDestination = LocalBroadcast()
                if not isinstance(pduDestination, LocalBroadcast):
                    pduDestination = IPv4Address(
                        (ip.destination_address, udp.destination_port)
                    )
            else:
                # BACnet/IPv6 broadcasts are multicasts, the BVLL function
                # says which it is
                pduSource = IPv6Address((ip.source_address, udp.source_port))
                pduDestination = IPv6Address(
                    (ip.destination_address, udp.destination_port)
                )

            # save the header
            frame.udp = udp

    # without Ethernet or UDP there are no addresses and no BACnet to decode
    if pduSource is None:
        if _debug:
            decode_packet._debug("    - no link layer or UDP addresses")
        return frame

    # check for empty
    if not data:
        if _debug:
            decode_packet._debug("    - empty packet")
        return frame

    # build a PDU, to be consumed by the decode functions
    pdu = PDU(data, source=pduSource, destination=pduDestination)
    if _debug:
        decode_packet._debug("    - pdu: %r", pdu)

    # check for a BVLL header, BACnet/IPv4 (Annex J) or BACnet/IPv6 (Annex U)
    bvll_type = pdu.pduData[0]
    if bvll_type in (0x81, 0x82):
        if _debug:
            decode_packet._debug("    - BVLL header found: %r", bvll_type)

        lpci_class = LPCI if bvll_type == 0x81 else bvll6.LPCI
        try:
            lpci = lpci_class.decode(pdu)
            frame.bvlci = lpci
        except Exception as err:
            if _debug:
                decode_packet._debug("    - BVLL PDU decoding error: %r", err)
            return frame

        # find the appropriate LPDU subclass
        try:
            if bvll_type == 0x81:
                lpdu_class = bvll_pdu_types[lpci.bvlciFunction]
            else:
                lpdu_class = bvll6.pdu_types[lpci.bvlciFunction]
        except KeyError:
            raise DecodingError(f"unrecognized BVLL function: {lpci.bvlciFunction}")
        if _debug:
            decode_packet._debug("    - lpdu_class: %r", lpdu_class)

        try:
            # ask the subclass to decode the rest of the pdu
            lpdu = lpdu_class.decode(pdu)
            frame.bvll = lpdu

            if bvll_type == 0x81:
                # no deeper decoding for some
                if not isinstance(
                    lpdu,
                    (
                        DistributeBroadcastToNetwork,
                        OriginalUnicastNPDU,
                        OriginalBroadcastNPDU,
                        ForwardedNPDU,
                    ),
                ):
                    return frame

                # update source address
                if isinstance(lpdu, ForwardedNPDU):
                    pduSource = lpdu.bvlciAddress

            else:
                # the BACnet/IPv6 MAC address is the virtual address (VMAC)
                if isinstance(lpdu, bvll6.OriginalUnicastNPDU):
                    pduSource = lpdu.bvlciSourceVirtualAddress
                    pduDestination = lpdu.bvlciDestinationVirtualAddress
                elif isinstance(
                    lpdu,
                    (
                        bvll6.OriginalBroadcastNPDU,
                        bvll6.ForwardedNPDU,
                        bvll6.DistributeBroadcastToNetwork,
                    ),
                ):
                    pduSource = lpdu.bvlciSourceVirtualAddress
                    pduDestination = LocalBroadcast()
                else:
                    # no deeper decoding for the rest
                    return frame

            # reference the rest of the packet
            pdu = PDU(lpdu.pduData, source=pduSource, destination=pduDestination)

        except Exception as err:
            if _debug:
                decode_packet._debug("    - %r decoding Error: %r", lpdu_class, err)
                traceback.print_stack()
            return frame

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

        # keep the 'null' out of the JSON encoding
        delattr(npci, "npduNetMessage")

        # decode it as an APDU
        try:
            apdu = APDU.decode(pdu)
            frame.apdu = apdu
            if _debug:
                decode_packet._debug("    - apdu: %r", apdu)
        except Exception as err:
            if _debug:
                decode_packet._debug("    - decoding Error: %r", err)
            return frame

        # scrape off the APCI data
        frame.apci = APCI()
        frame.apci.update(apdu)

        # update the source and destination
        if npci.npduSADR:
            apdu.pduSource = npci.npduSADR
        if npci.npduDADR:
            apdu.pduDestination = npci.npduDADR

        if not isinstance(
            apdu, (ConfirmedRequestPDU, ComplexAckPDU, UnconfirmedRequestPDU)
        ):
            return frame

        # continue decoding the apdu.pduData
        try:
            apdu = APCISequence.decode(apdu)
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


def _decode_packets(
    gen: Iterator[Tuple[int, float, bytes]], linktype: int = LINKTYPE_ETHERNET
) -> Iterator[Frame]:
    """
    Helper function for decoding data from pylibpcap generators.
    """
    # loop through the packets
    for i, (len, timestamp, data) in enumerate(gen):
        try:
            frame = decode_packet(data, linktype)
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
def decode_file(fname):
    """
    Given the name of a pcap file, open it, decode the contents and yield each
    as a frame.
    """
    if _debug:
        decode_file._debug("decode_file %r", fname)

    if not pylibpcap:
        raise RuntimeError("failed to import pylibpcap")

    # the link-layer header type determines where the IP header starts
    linktype = pcap_file_linktype(fname)
    if _debug:
        decode_file._debug("    - linktype: %r", linktype)
    if linktype not in _supported_linktypes:
        raise ValueError(f"{fname}: unsupported link type: {linktype}")

    # generator function yields (len, timestamp, data) tuple
    gen_fn = pylibpcap.pcap.rpcap(fname)

    yield from _decode_packets(gen_fn, linktype)


@bacpypes_debugging
def decode_iface(
    iface: str,
    count: int = -1,
    promisc: int = 0,
    snaplen: int = 65535,
    filters: str = "udp port 47808",
    timeout: int = 500,
    linktype: Optional[int] = None,
):
    """
    Given the name of an interface, 'sniff' the packets and yield each as
    a frame.  If the linktype is not provided it is looked up from the
    interface type (Linux only) and defaults to Ethernet.
    """
    if _debug:
        decode_iface._debug("decode_iface %r linktype=%r", iface, linktype)

    if not pylibpcap:
        raise RuntimeError("failed to import pylibpcap")

    if linktype is None:
        linktype = iface_linktype(iface)
        if linktype is None:
            linktype = LINKTYPE_ETHERNET
        if _debug:
            decode_iface._debug("    - linktype: %r", linktype)
    if linktype not in _supported_linktypes:
        raise ValueError(f"{iface}: unsupported link type: {linktype}")

    # generator function yields (len, timestamp, data) tuple
    gen_fn = pylibpcap.sniff(
        iface,
        count=count,
        promisc=promisc,
        snaplen=snaplen,
        filters=filters,
        timeout=timeout,
    )

    yield from _decode_packets(gen_fn, linktype)


class TracerState(Enum):
    IDLE = 0
    BUSY = 1
    FINI = 2


TracerMethod = Callable[["Tracer", Union[Frame, None]], None]


@bacpypes_debugging
class Tracer:
    """
    A tracer is a state machine that is given packets from a stream one at a
    time and filters them for some pattern.  When a pattern matches the
    tracer transitions to its next state.
    """

    _state: TracerState
    _state_method: Optional[TracerMethod]

    @experimental
    def __init__(self) -> None:
        if _debug:
            Tracer._debug("__init__")

        # set the starting state
        self._state = TracerState.IDLE
        self._state_method = self.start

    def next(self, next_state: TracerMethod) -> None:
        if _debug:
            Tracer._debug("next %r", next_state)

        # set the state
        if next_state:
            self._state = TracerState.BUSY
            self._state_method = next_state
        else:
            self._state = TracerState.FINI

    def start(self, frame: Frame) -> None:
        """
        The starting state for a tracer.  When a frame is matched then
        the state machine transitions to another state or 'None' if it
        is exiting.
        """
        raise NotImplementedError("Tracer.start")

    def stop(self) -> None:
        """
        The stopping state for a tracer, can be called by the tracer when
        it's work is complete or by the `trace()` function when there are no
        more frames.
        """
        if _debug:
            Tracer._debug("stop")

        self._state = TracerState.FINI

    def __repr__(self):
        return f"<{self.__class__.__name__}({id(self)}) {self._state}>"


@experimental
@bacpypes_debugging
def trace(gen_fns: List[Generator[Frame, None, None]], tracers):
    """
    Given a list of generator functions like `decode_file("sample.pcap")` pass
    the frames to instances of the tracer classes.  If the current state of the
    tracer is `start` then it is assumed to be idle.
    """
    if _debug:
        trace._debug("trace %r %r", gen_fns, tracers)

    # make a set of tracers for each class
    current_tracers = set(tracer_cls() for tracer_cls in tracers)

    # pass the frame to each tracer
    for gen_fn in gen_fns:
        for frame in gen_fn:
            # skip decoding errors
            if frame is None:
                continue

            idle_tracers = set()
            for tracer in current_tracers:
                # give the frame to the tracer
                tracer._state_method(frame)

                # tracer may be finished
                if tracer._state is TracerState.FINI:
                    idle_tracers.add(tracer)

            # remove the idle tracers
            if idle_tracers:
                current_tracers.difference_update(idle_tracers)

            # make a set of those that have an idle instance
            idle_tracer_cls = set(
                tracer.__class__
                for tracer in current_tracers
                if tracer._state is TracerState.IDLE
            )

            # make a new tracer for classes that do not have an idle instance
            for tracer_cls in tracers:
                if tracer_cls not in idle_tracer_cls:
                    current_tracers.add(tracer_cls())

    # tell all the active tracers to shut down
    for tracer in current_tracers:
        tracer.stop()


@bacpypes_debugging
class CustomJSONEncoder(json.JSONEncoder):
    """
    JSON encoder that can handle special datatypes.  If object being encoded
    has a `dict_contents()` method then somehow a nested object was missed.
    Eventually this will be an assert.
    """

    def default(self, obj):
        if hasattr(obj, "dict_contents"):
            if _debug:
                CustomJSONEncoder._debug("trap obj: %r", obj)
            return obj.dict_contents()
        if isinstance(obj, (bytes, bytearray)):
            return ":".join(f"{b:02x}" for b in obj)
        if isinstance(obj, datetime):
            return obj.isoformat()

        # Let the base class handle other types or raise a TypeError
        try:
            return super().default(obj)
        except TypeError as err:
            return f"err: {err}"


if __name__ == "__main__":
    try:
        from bacpypes3.argparse import ArgumentParser

        parser = ArgumentParser()

        # pcap file decoding
        parser.add_argument(
            "filenames",
            nargs="*",
            help="the names of the pcaps file to decode",
        )

        # interface decoding
        parser.add_argument(
            "-i",
            "--interface",
            type=str,
            help="interface name",
        )
        parser.add_argument(
            "-f",
            "--filter",
            type=str,
            default="udp port 47808",
            help="capture filter",
        )
        parser.add_argument(
            "-c",
            "--count",
            type=int,
            default=-1,
            help="packet count",
        )
        parser.add_argument(
            "-p",
            "--no-promiscous",
            action="store_false",
            help="promiscous mode",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=500,
            help="timeout",
        )
        parser.add_argument(
            "--linktype",
            type=lambda v: linktypes[v] if v in linktypes else int(v),
            default=None,
            help="interface link-layer type, a number or one of: "
            + ", ".join(linktypes)
            + " (default: from the interface type, or ethernet)",
        )

        # data options
        parser.add_argument(
            "--data",
            action="store_true",
            help="include the data hex strings",
        )
        args = parser.parse_args()
        _log.debug("args: %r", args)
        _log.debug("settings: %r", settings)

        # stream from files
        gen_fns = [decode_file(fname) for fname in args.filenames]

        # stream from an interface
        if args.interface:
            gen_fns.append(
                decode_iface(
                    args.interface,
                    filters=args.filter,
                    count=args.count,
                    promisc=int(args.no_promiscous),
                    timeout=args.timeout,
                    linktype=args.linktype,
                )
            )

        # create a dict from each frame
        for gen_fn in gen_fns:
            for frame in gen_fn:
                # dump it as a string
                json_string = json.dumps(
                    frame.dict_contents(include_data=args.data),
                    cls=CustomJSONEncoder,
                    indent=4,
                )
                print(strftimestamp(frame._timestamp), json_string)

    except KeyboardInterrupt:
        pass
    except Exception as err:
        _log.exception("an error has occurred: %s", err)
    finally:
        _log.debug("finally")
