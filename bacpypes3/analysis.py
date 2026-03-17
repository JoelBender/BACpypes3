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
from .pdu import PDU, Address, LocalBroadcast, IPv4Address
from .ipv4.bvll import (
    LPCI,
    LPDU,
    pdu_types as bvll_pdu_types,
    DistributeBroadcastToNetwork,
    OriginalUnicastNPDU,
    OriginalBroadcastNPDU,
    ForwardedNPDU,
)
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
}
_ethernet_broadcast_address = Address("FF:FF:FF:FF:FF:FF")


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
            use_dict.__setitem__("type", self.data)

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
    data = ethernet.data

    # basic source and destination
    pduSource = Address(ethernet.source_address)
    if ethernet.destination_address == "FF:FF:FF:FF:FF:FF":
        pduDestination = LocalBroadcast()
    else:
        pduDestination = Address(ethernet.destination_address)

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
        data = ipv4.data

        # save the header
        frame.ipv4 = ipv4

        # check for a UDP packet
        if ipv4.protocol == "udp":
            if _debug:
                decode_packet._debug("    - UDP found")

            udp = decode_udp(data)
            data = udp.data

            # update the source and destination
            pduSource = IPv4Address((ipv4.source_address, udp.source_port))
            if not isinstance(pduDestination, LocalBroadcast):
                pduDestination = IPv4Address(
                    (ipv4.destination_address, udp.destination_port)
                )

            # save the header
            frame.udp = udp
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

    # build a PDU, to be consumed by the decode functions
    pdu = PDU(data, source=pduSource, destination=pduDestination)
    if _debug:
        decode_packet._debug("    - pdu: %r", pdu)

    # check for a BVLL header
    if pdu.pduData[0] == 0x81:
        if _debug:
            decode_packet._debug("    - BVLL header found")

        try:
            lpci = LPCI.decode(pdu)
            frame.bvlci = lpci
        except Exception as err:
            if _debug:
                decode_packet._debug("    - BVLL PDU decoding error: %r", err)
            return frame

        # find the appropriate LPDU subclass
        try:
            lpdu_class = bvll_pdu_types[lpci.bvlciFunction]
        except KeyError:
            raise DecodingError(f"unrecognized BVLL function: {lpci.bvlciFunction}")
        if _debug:
            decode_packet._debug("    - lpdu_class: %r", lpdu_class)

        try:
            # ask the subclass to decode the rest of the pdu
            lpdu = lpdu_class.decode(pdu)
            frame.bvll = lpdu

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


def _decode_packets(gen: Iterator[Tuple[int, float, bytes]]) -> Iterator[Frame]:
    """
    Helper function for decoding data from pylibpcap generators.
    """
    # loop through the packets
    for i, (len, timestamp, data) in enumerate(gen):
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
def decode_file(fname):
    """
    Given the name of a pcap file, open it, decode the contents and yield each
    as a frame.
    """
    if _debug:
        decode_file._debug("decode_file %r", fname)

    if not pylibpcap:
        raise RuntimeError("failed to import pylibpcap")

    # generator function yields (len, timestamp, data) tuple
    gen_fn = pylibpcap.pcap.rpcap(fname)

    yield from _decode_packets(gen_fn)


@bacpypes_debugging
def decode_iface(
    iface: str,
    count: int = -1,
    promisc: int = 0,
    snaplen: int = 65535,
    filters: str = "udp port 47808",
    timeout: int = 500,
):
    """
    Given the name of an interface, 'sniff' the packets and yield each as
    a frame.
    """
    if _debug:
        decode_file._debug("decode_iface %r", iface)

    if not pylibpcap:
        raise RuntimeError("failed to import pylibpcap")

    # generator function yields (len, timestamp, data) tuple
    gen_fn = pylibpcap.sniff(
        iface,
        count=count,
        promisc=promisc,
        snaplen=snaplen,
        filters=filters,
        timeout=timeout,
    )

    yield from _decode_packets(gen_fn)


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
