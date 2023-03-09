"""
PDU
"""

from __future__ import annotations

import sys
import re
import socket
import struct
import ipaddress

from copy import copy as _copy
from typing import Union, Any, List, TextIO, Tuple, Dict, Optional, Callable, cast

from .settings import settings
from .debugging import ModuleLogger, DebugContents, bacpypes_debugging, btox, xtob
from .errors import DecodingError

try:
    import ifaddr  # type: ignore[import]
except ImportError:
    ifaddr = None

try:
    import netifaces  # type: ignore[import]
except ImportError:
    netifaces = None

# pack/unpack constants
_short_mask = 0xFFFF
_long_mask = 0xFFFFFFFF

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   Address
#

_field_address = r"((?:\d+)|(?:0x(?:[0-9A-Fa-f][0-9A-Fa-f])+))"
field_address_re = re.compile("^" + _field_address + "$")

_ipv4_address_port = r"(\d+\.\d+\.\d+\.\d+)(?::(\d+))?"
_ipv4_address_mask_port = (
    r"(\d+\.\d+\.\d+\.\d+)(?:/(\d+(?:\.\d+\.\d+\.\d+)?))?(?::(\d+))?"
)
_net_ipv4_address_port = r"(\d+):" + _ipv4_address_port
_net_ipv4_address_mask_port = r"(\d+):" + _ipv4_address_mask_port
ipv4_address_port_re = re.compile("^" + _ipv4_address_port + "$")
ipv4_address_mask_port_re = re.compile("^" + _ipv4_address_mask_port + "$")
net_ipv4_address_port_re = re.compile("^" + _net_ipv4_address_port + "$")
net_ipv4_address_mask_port_re = re.compile("^" + _net_ipv4_address_mask_port + "$")

_ipv6_address = r"([.:0-9A-Fa-f]+(?:/\d+)?)"
_ipv6_address_port = r"(?:\[)([.:0-9A-Fa-f]+(?:/\d+)?)(?:\])(?::(\d+))?"
_net_ipv6_address_port = r"(\d+):" + _ipv6_address_port
ipv6_address_re = re.compile("^" + _ipv6_address + "$")
ipv6_address_port_re = re.compile("^" + _ipv6_address_port + "$")
net_ipv6_address_port_re = re.compile("^" + _net_ipv6_address_port + "$")

_ipv6_interface = r"(?:(?:[%])([\w]+))?"
_ipv6_address_interface = _ipv6_address + _ipv6_interface
_ipv6_address_port_interface = _ipv6_address_port + _ipv6_interface
ipv6_address_interface_re = re.compile("^" + _ipv6_address_interface + "$")
ipv6_address_port_interface_re = re.compile("^" + _ipv6_address_port_interface + "$")

_at_route = (
    "(?:[@](?:"
    + _field_address
    + "|"
    + _ipv4_address_port
    + "|"
    + _ipv6_address_port
    + "))?"
)

net_broadcast_route_re = re.compile("^([0-9])+:[*]" + _at_route + "$")
net_station_route_re = re.compile("^([0-9])+:" + _field_address + _at_route + "$")
net_ipv4_address_route_re = re.compile(
    "^([0-9])+:" + _ipv4_address_port + _at_route + "$"
)
net_ipv6_address_route_re = re.compile(
    "^([0-9])+:" + _ipv6_address_port + _at_route + "$"
)

combined_pattern = re.compile(
    "^(?:(?:([0-9]+)|([*])):)?(?:([*])|"
    + _field_address
    + "|"
    + _ipv4_address_mask_port
    + "|"
    + _ipv6_address_port
    + ")"
    + _at_route
    + "$"
)

ethernet_re = re.compile(r"^([0-9A-Fa-f][0-9A-Fa-f][:]){5}([0-9A-Fa-f][0-9A-Fa-f])$")
interface_port_re = re.compile(r"^(?:([\w]+))(?::(\d+))?$")
host_port_re = re.compile(r"^(?:([\w.]+))(?::(\d+))?$")

network_types: Dict[str, type]


@bacpypes_debugging
class AddressMetaclass(type):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __new__(
        cls: Any,
        clsname: str,
        superclasses: Tuple[type, ...],
        attributedict: Dict[str, Any],
    ) -> "AddressMetaclass":
        if _debug:
            AddressMetaclass._debug(
                "__new__ %r %r %r", clsname, superclasses, attributedict
            )

        return cast(
            AddressMetaclass, type.__new__(cls, clsname, superclasses, attributedict)
        )

    def __call__(cls, *args: Any, **kwargs: Any) -> "Address":
        if _debug:
            AddressMetaclass._debug("__call__ %r %r %r", cls, args, kwargs)

        # already subclassed, nothing to see here
        if cls is not Address:
            return cast(Address, type.__call__(cls, *args, **kwargs))

        network_type = kwargs.get("network_type", None)

        # network type was provided
        if network_type:
            if network_type not in network_types:
                raise ValueError("invalid network type")

            return super(AddressMetaclass, network_types[network_type]).__call__(*args, **kwargs)  # type: ignore[misc, no-any-return]

        if not args:
            if _debug:
                AddressMetaclass._debug("    - null")
            return super(AddressMetaclass, NullAddress).__call__(*args, **kwargs)  # type: ignore[misc, no-any-return]

        # match the address
        addr = args[0]

        if isinstance(addr, int):
            if _debug:
                AddressMetaclass._debug("    - int")
            if addr < 0:
                raise ValueError("invalid address")
            if addr <= 255:
                return super(AddressMetaclass, ARCNETAddress).__call__(addr, **kwargs)  # type: ignore[misc, no-any-return]
            # if addr <= _long_mask:
            #     return super(AddressMetaclass, IPv4Address).__call__(addr, **kwargs)  # type: ignore[misc, no-any-return]

            # last chance
            # return super(AddressMetaclass, IPv6Address).__call__(addr, **kwargs)  # type: ignore[misc, no-any-return]
            raise ValueError("invalid address")

        if isinstance(addr, (bytes, bytearray)):
            if _debug:
                AddressMetaclass._debug("    - bytes or bytearray")
            if isinstance(addr, bytearray):
                addr_bytes = bytes(addr)
            else:
                addr_bytes = addr

            if len(addr_bytes) <= 0:
                raise ValueError("invalid address")

            if len(addr_bytes) == 1:
                return super(AddressMetaclass, ARCNETAddress).__call__(addr_bytes, **kwargs)  # type: ignore[misc, no-any-return]
            if len(addr_bytes) == 3:
                return super(AddressMetaclass, VirtualAddress).__call__(addr_bytes, **kwargs)  # type: ignore[misc, no-any-return]
            if len(addr_bytes) == 6:
                return super(AddressMetaclass, IPv4Address).__call__(addr_bytes, **kwargs)  # type: ignore[misc, no-any-return]
            if len(addr_bytes) == 18:
                return super(AddressMetaclass, IPv6Address).__call__(addr_bytes, **kwargs)  # type: ignore[misc, no-any-return]

            raise ValueError("invalid address")

        if isinstance(addr, str):
            if _debug:
                AddressMetaclass._debug("    - str")

            m = combined_pattern.match(addr)
            if m:
                if _debug:
                    Address._debug("    - combined pattern")

                (
                    net,
                    global_broadcast,
                    local_broadcast,
                    local_addr,
                    local_ipv4_addr,
                    local_ipv4_net,
                    local_ipv4_port,
                    local_ipv6_addr,
                    local_ipv6_port,
                    route_addr,
                    route_ipv4_addr,
                    route_ipv4_port,
                    route_ipv6_addr,
                    route_ipv6_port,
                ) = m.groups()

                net_addr = -1
                if net:
                    if _debug:
                        AddressMetaclass._debug(
                            "    - remote broadcast or remote station"
                        )
                    net_addr = int(net)
                    if net_addr >= 65535:
                        raise ValueError("network out of range")

                if global_broadcast and local_broadcast:
                    if _debug:
                        AddressMetaclass._debug("    - global broadcast")
                    address = super(AddressMetaclass, GlobalBroadcast).__call__(**kwargs)  # type: ignore[misc]

                elif net and local_broadcast:
                    if _debug:
                        AddressMetaclass._debug("    - remote broadcast: %r", net)
                    address = super(AddressMetaclass, RemoteBroadcast).__call__(net_addr, **kwargs)  # type: ignore[misc]

                elif local_broadcast:
                    if _debug:
                        AddressMetaclass._debug("    - local broadcast")
                    address = super(AddressMetaclass, LocalBroadcast).__call__(**kwargs)  # type: ignore[misc]

                if local_addr:
                    if _debug:
                        AddressMetaclass._debug("    - simple address")

                    if local_addr.startswith("0x"):
                        local_addr_bytes = xtob(local_addr[2:])
                    else:
                        local_addr_byte = int(local_addr)
                        if local_addr_byte >= 256:
                            raise ValueError("address out of range")

                        local_addr_bytes = struct.pack("B", local_addr_byte)

                    if net_addr > 0:
                        address = super(AddressMetaclass, RemoteStation).__call__(net_addr, local_addr_bytes, **kwargs)  # type: ignore[misc]
                    else:
                        address = super(AddressMetaclass, LocalStation).__call__(local_addr_bytes, **kwargs)  # type: ignore[misc]

                if local_ipv4_addr:
                    if _debug:
                        Address._debug("    - IPv4 address")
                    if not local_ipv4_net:
                        local_ipv4_net = "32"
                    if not local_ipv4_port:
                        local_ipv4_port = "47808"

                    address = super(AddressMetaclass, IPv4Address).__call__(f"{local_ipv4_addr}/{local_ipv4_net}", port=int(local_ipv4_port), **kwargs)  # type: ignore[misc]

                if local_ipv6_addr:
                    if _debug:
                        AddressMetaclass._debug("    - IPv6 address")
                    if not local_ipv6_port:
                        local_ipv6_port = "47808"

                    address = super(AddressMetaclass, IPv6Address).__call__(local_ipv6_addr, port=int(local_ipv6_port), **kwargs)  # type: ignore[misc]

                # if this is a remote address, add the network
                if net and (not global_broadcast) and (not local_broadcast):
                    if _debug:
                        AddressMetaclass._debug("    - adding network")
                    address.addrNet = net_addr

                # make sure we should be route aware
                if (not settings.route_aware) and (
                    route_addr or route_ipv4_addr or route_ipv6_addr
                ):
                    Address._warning("route provided but not route aware: %r", addr)

                # route address is a field address - go recursion
                if route_addr:
                    if _debug:
                        AddressMetaclass._debug("    - adding field route")
                    address.addrRoute = Address(route_addr)

                if route_ipv4_addr:
                    if _debug:
                        AddressMetaclass._debug("    - adding IPv4 route")
                    if not route_ipv4_port:
                        route_ipv4_port = "47808"
                    address.addrRoute = super(AddressMetaclass, IPv4Address).__call__((route_ipv4_addr, int(route_ipv4_port)))  # type: ignore[misc]

                if route_ipv6_addr:
                    if _debug:
                        AddressMetaclass._debug("    - adding IPv6 route")
                    if not route_ipv6_port:
                        route_ipv6_port = "47808"
                    address.addrRoute = super(AddressMetaclass, IPv6Address).__call__((route_ipv4_addr, int(route_ipv4_port)))  # type: ignore[misc]

                return address  # type: ignore[no-any-return]

            if ethernet_re.match(addr):
                return super(AddressMetaclass, EthernetAddress).__call__(*args, **kwargs)  # type: ignore[misc, no-any-return]

            if interface_port_re.match(addr):
                return super(AddressMetaclass, IPv4Address).__call__(*args, **kwargs)  # type: ignore[misc, no-any-return]

            raise ValueError("unrecognized format")

        if isinstance(addr, tuple):
            if _debug:
                AddressMetaclass._debug("    - tuple")
            addr, port = addr

            try:
                test_address = ipaddress.ip_address(addr)
                if _debug:
                    AddressMetaclass._debug("    - test_address: %r", test_address)

                if isinstance(test_address, ipaddress.IPv4Address):
                    if _debug:
                        AddressMetaclass._debug("    - ipv4")
                    return super(AddressMetaclass, IPv4Address).__call__(addr, port=port, **kwargs)  # type: ignore[misc, no-any-return]
                elif isinstance(test_address, ipaddress.IPv6Address):
                    if _debug:
                        AddressMetaclass._debug("    - ipv6")
                    return super(AddressMetaclass, IPv6Address).__call__(addr, port=port, **kwargs)  # type: ignore[misc, no-any-return]
            except Exception as err:
                if _debug:
                    AddressMetaclass._debug("    - err: %r", err)

        if isinstance(addr, ipaddress.IPv4Address):
            if _debug:
                AddressMetaclass._debug("    - ipv4")
            return super(AddressMetaclass, IPv4Address).__call__(addr, **kwargs)  # type: ignore[misc, no-any-return]

        if isinstance(addr, ipaddress.IPv6Address):
            if _debug:
                AddressMetaclass._debug("    - ipv6")
            return super(AddressMetaclass, IPv6Address).__call__(addr, **kwargs)  # type: ignore[misc, no-any-return]

        raise ValueError("invalid address")


#
#   Address
#


@bacpypes_debugging
class Address(metaclass=AddressMetaclass):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _warning: Callable[..., None]

    nullAddr = 0
    localBroadcastAddr = 1
    localStationAddr = 2
    remoteBroadcastAddr = 3
    remoteStationAddr = 4
    globalBroadcastAddr = 5

    addrType: int
    addrNetworkType: Optional[str]
    addrNet: Optional[int]
    addrAddr: Optional[bytes]
    addrLen: Optional[int]
    addrRoute: Optional["Address"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if _debug:
            Address._debug("__init__ %r %r", args, kwargs)
        raise NotImplementedError

    @property
    def is_null(self) -> bool:
        return self.addrType == Address.nullAddr

    @property
    def is_localbroadcast(self) -> bool:
        return self.addrType == Address.localBroadcastAddr

    @property
    def is_localstation(self) -> bool:
        return self.addrType == Address.localStationAddr

    @property
    def is_remotebroadcast(self) -> bool:
        return self.addrType == Address.remoteBroadcastAddr

    @property
    def is_remotestation(self) -> bool:
        return self.addrType == Address.remoteStationAddr

    @property
    def is_globalbroadcast(self) -> bool:
        return self.addrType == Address.globalBroadcastAddr

    def __str__(self) -> str:
        return "?"

    def __repr__(self) -> str:
        return "<%s %s>" % (self.__class__.__name__, self.__str__())

    def _tuple(
        self,
    ) -> Tuple[int, Optional[int], Optional[bytes], Optional[Tuple[Any, ...]]]:
        if (not settings.route_aware) or (self.addrRoute is None):
            return (self.addrType, self.addrNet, self.addrAddr, None)
        else:
            return (self.addrType, self.addrNet, self.addrAddr, self.addrRoute._tuple())

    def __hash__(self) -> int:
        return hash(self._tuple())

    def __eq__(self, arg: object) -> bool:
        # try an coerce it into an address
        if not isinstance(arg, Address):
            arg = Address(arg)

        # basic components must match
        rslt = self.addrType == arg.addrType
        rslt = rslt and (self.addrNet == arg.addrNet)
        rslt = rslt and (self.addrAddr == arg.addrAddr)

        # if both have routes they must match
        if rslt and self.addrRoute and arg.addrRoute:
            rslt = rslt and (self.addrRoute == arg.addrRoute)

        return rslt

    def __ne__(self, arg: object) -> bool:
        return not self.__eq__(arg)

    #    def __lt__(self, arg: 'Address') -> bool:
    #        return self._tuple() < arg._tuple()

    def match(self, other: Address) -> bool:
        """
        Match this address as a source address with the 'other' as a destination,
        so a local station matches a local broadcast, etc.
        """
        if _debug:
            Address._debug("match %r %r", self, other)

        if other.addrType == Address.nullAddr:
            return self.addrType == Address.nullAddr

        elif other.addrType == Address.localBroadcastAddr:
            return self.addrType == Address.localStationAddr

        elif other.addrType == Address.localStationAddr:
            return (self.addrType == Address.localStationAddr) and (
                self.addrAddr == other.addrAddr
            )

        elif other.addrType == Address.remoteBroadcastAddr:
            return (self.addrType == Address.remoteStationAddr) and (
                self.addrNet == other.addrNet
            )

        elif other.addrType == Address.remoteStationAddr:
            return (
                (self.addrType == Address.remoteStationAddr)
                and (self.addrAddr == other.addrAddr)
                and (self.addrNet == other.addrNet)
            )

        elif other.addrType == Address.globalBroadcastAddr:
            return True

        else:
            raise ValueError("address pattern error")

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
    ) -> Dict[str, Any]:
        """Return the contents of an object as a dict."""
        if _debug:
            _log.debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the string version of the address
        use_dict.__setitem__("str", str(self))

        # return what we built/updated
        return use_dict


#
#   NullAddress
#


@bacpypes_debugging
class NullAddress(Address):
    """
    Amazing documentation here.
    """

    def __init__(self, network_type: str = "null") -> None:
        if _debug:
            NullAddress._debug("NullAddress.__init__ network_type=%r", network_type)

        if network_type != "null":
            raise ValueError("network type must be 'null'")

        self.addrType = Address.nullAddr
        self.addrNet = None
        self.addrLen = None
        self.addrAddr = None

    def __str__(self) -> str:
        return "Null"


#
#   LocalStation
#


@bacpypes_debugging
class LocalStation(Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self,
        addr: Union[int, bytes, bytearray],
        route: Optional[Address] = None,
        network_type: Optional[str] = None,
    ) -> None:
        if _debug:
            LocalStation._debug("__init__ %r network_type=%r", addr, network_type)

        if network_type and network_type not in network_types:
            raise ValueError("invalid network type")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = network_type
        self.addrNet = None
        self.addrRoute = route

        if isinstance(addr, int):
            if (addr < 0) or (addr >= 256):
                raise ValueError("address out of range")

            self.addrAddr = struct.pack("B", addr)
            self.addrLen = 1

        elif isinstance(addr, (bytes, bytearray)):
            if _debug:
                Address._debug("    - bytes or bytearray")

            self.addrAddr = bytes(addr)
            self.addrLen = len(addr)

        else:
            raise TypeError("integer, bytes or bytearray required")

    def __str__(self) -> str:
        assert self.addrAddr is not None

        if self.addrLen == 1:
            addrstr = str(self.addrAddr[0])
        else:
            addrstr = "0x" + btox(self.addrAddr)

        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return addrstr + suffix


#
#   LocalBroadcast
#


@bacpypes_debugging
class LocalBroadcast(Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self, route: Optional[Address] = None, network_type: Optional[str] = None
    ) -> None:
        if _debug:
            LocalBroadcast._debug("__init__ network_type=%r", network_type)

        if network_type and network_type not in network_types:
            raise ValueError("invalid network type")

        self.addrType = Address.localBroadcastAddr
        self.addrNetworkType = network_type
        self.addrNet = None
        self.addrAddr = None
        self.addrLen = None
        self.addrRoute = route

    def __str__(self) -> str:
        if _debug:
            LocalBroadcast._debug("__str__")

        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return "*" + suffix


#
#   RemoteStation
#


class RemoteStation(Address):
    """
    Amazing documentation here.
    """

    addrNet: int
    addrAddr: bytes
    addrLen: int

    def __init__(
        self,
        net: int,
        addr: Union[int, bytes, bytearray],
        route: Optional[Address] = None,
        network_type: Optional[str] = None,
    ) -> None:
        if not isinstance(net, int):
            raise TypeError("integer network required")
        if (net < 0) or (net >= 65535):
            raise ValueError("network out of range")

        if network_type and network_type not in network_types:
            raise ValueError("invalid network type")

        self.addrType = Address.remoteStationAddr
        self.addrNetworkType = network_type
        self.addrNet = net
        self.addrRoute = route

        if isinstance(addr, int):
            if (addr < 0) or (addr >= 256):
                raise ValueError("address out of range")

            self.addrAddr = struct.pack("B", addr)
            self.addrLen = 1

        elif isinstance(addr, (bytes, bytearray)):
            if _debug:
                Address._debug("    - bytes or bytearray")

            self.addrAddr = bytes(addr)
            self.addrLen = len(addr)

        else:
            raise TypeError("integer, bytes or bytearray required")

    def __str__(self) -> str:
        assert self.addrAddr is not None

        prefix = str(self.addrNet) + ":"
        if self.addrLen == 1:
            addrstr = str(self.addrAddr[0])
        elif self.addrLen == 6:
            port = struct.unpack(">H", self.addrAddr[-2:])[0]
            if 47808 <= port <= 47810:
                addrstr = socket.inet_ntoa(self.addrAddr[:4])
                if port != 47808:
                    addrstr += ":" + str(port)
            else:
                addrstr = "0x" + btox(self.addrAddr)
        else:
            addrstr = "0x" + btox(self.addrAddr)

        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return prefix + addrstr + suffix


#
#   RemoteBroadcast
#


class RemoteBroadcast(Address):
    """
    Amazing documentation here.
    """

    addrNet: int

    def __init__(
        self,
        net: int,
        route: Optional[Address] = None,
        network_type: Optional[str] = None,
    ) -> None:
        if not isinstance(net, int):
            raise TypeError("integer network required")
        if (net < 0) or (net >= 65535):
            raise ValueError("network out of range")

        if network_type and network_type not in network_types:
            raise ValueError("invalid network type")

        self.addrType = Address.remoteBroadcastAddr
        self.addrNetworkType = network_type

        self.addrNet = net
        self.addrAddr = None
        self.addrLen = None
        self.addrRoute = route

    def __str__(self) -> str:
        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return str(self.addrNet) + ":*" + suffix


#
#   GlobalBroadcast
#


class GlobalBroadcast(Address):
    """
    Amazing documentation here.
    """

    def __init__(self, route: Optional[Address] = None) -> None:
        self.addrType = Address.globalBroadcastAddr
        self.addrNet = None
        self.addrAddr = None
        self.addrLen = None
        self.addrRoute = route

    def __str__(self) -> str:
        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return "*:*" + suffix


#
#   ARCNETAddress
#


@bacpypes_debugging
class ARCNETAddress(Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self,
        addr: Union[int, bytes, bytearray, str],
        route: Optional[Address] = None,
        network_type: str = "arcnet",
    ) -> None:
        if _debug:
            ARCNETAddress._debug("__init__ %r network_type=%r", addr, network_type)

        if network_type != "arcnet":
            raise ValueError("network type must be 'arcnet'")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = "arcnet"
        self.addrNet = None
        self.addrRoute = route

        if _debug:
            ARCNETAddress._debug("    - %r", type(addr))

        if isinstance(addr, int):
            if _debug:
                ARCNETAddress._debug("    - int")
            self.addrAddr = struct.pack("B", addr)

        elif isinstance(addr, (bytes, bytearray)):
            if _debug:
                ARCNETAddress._debug("    - bytes, bytearray")
            self.addrAddr = bytes(addr)

        elif isinstance(addr, str):
            self.addrAddr = struct.pack("B", int(addr))

        else:
            raise ValueError("invalid address")

        self.addrLen = 1

    def __str__(self) -> str:
        assert self.addrAddr is not None

        prefix = str(self.addrNet) + ":" if self.addrNet else ""
        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return prefix + str(self.addrAddr[0]) + suffix


#
#   MSTPAddress
#


@bacpypes_debugging
class MSTPAddress(Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self,
        addr: Union[int, bytes, bytearray, str],
        route: Optional[Address] = None,
        network_type: str = "mstp",
    ) -> None:
        if _debug:
            MSTPAddress._debug("__init__ %r network_type=%r", addr, network_type)

        if network_type != "mstp":
            raise ValueError("network type must be 'mstp'")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = "arcnet"
        self.addrNet = None
        self.addrRoute = route

        if isinstance(addr, int):
            self.addrAddr = struct.pack("B", addr)

        elif isinstance(addr, (bytes, bytearray)):
            self.addrAddr = bytes(addr)

        elif isinstance(addr, str):
            self.addrAddr = struct.pack("B", int(addr))

        else:
            raise ValueError("invalid address")

        self.addrLen = 1

    def __str__(self) -> str:
        assert self.addrAddr is not None

        prefix = str(self.addrNet) + ":" if self.addrNet else ""
        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return prefix + str(self.addrAddr[0]) + suffix


#
#   EthernetAddress
#


@bacpypes_debugging
class EthernetAddress(Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self,
        addr: Union[str, bytes, bytearray],
        route: Optional[Address] = None,
        network_type: str = "ethernet",
    ) -> None:
        if _debug:
            EthernetAddress._debug("__init__ %r network_type=%r", addr, network_type)

        if network_type != "ethernet":
            raise ValueError("network type must be 'ethernet'")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = "ethernet"
        self.addrNet = None
        self.addrRoute = route

        if isinstance(addr, str) and ethernet_re.match(addr):
            self.addrAddr = xtob(addr, ":")
        elif isinstance(addr, (bytes, bytearray)):
            self.addrAddr = bytes(addr)

        self.addrLen = 6

    def __str__(self) -> str:
        assert self.addrAddr is not None

        suffix = ", net " + str(self.addrNet) if self.addrNet else ""
        suffix += "@" + str(self.addrRoute) if self.addrRoute else ""
        return btox(self.addrAddr, sep=":") + suffix


#
#   EthernetBroadcastAddress
#


@bacpypes_debugging
class EthernetBroadcastAddress(LocalBroadcast, EthernetAddress):
    """
    Amazing documentation here.
    """

    def __init__(self) -> None:
        if _debug:
            EthernetAddress._debug("__init__")
        LocalBroadcast.__init__(self, network_type="ethernet")
        EthernetAddress.__init__(self, "\xFF" * 6)

        # reset the address type
        self.addrType = Address.localBroadcastAddr


#
#   IPv4Address
#


@bacpypes_debugging
class IPv4Address(Address, ipaddress.IPv4Interface):
    """
    Amazing documentation here.
    """

    addrPort: int
    addrTuple: Tuple[str, int]
    addrBroadcastTuple: Tuple[str, int]

    def __init__(
        self,
        addr: Union[
            LocalStation,
            RemoteStation,
            int,
            str,
            bytes,
            bytearray,
            Tuple[Union[str, int], int],
            ipaddress.IPv4Address,
        ],
        port: int = 47808,
        route: Optional[Address] = None,
        network_type: str = "ipv4",
    ) -> None:
        if _debug:
            IPv4Address._debug("__init__ %r network_type=%r", addr, network_type)
        if _debug:
            IPv4Address._debug("    - type(addr): %r", type(addr))

        if network_type != "ipv4":
            raise ValueError("network type must be 'ipv4'")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = "ipv4"
        self.addrNet = None
        self.addrRoute = route

        # if this is a remote station, suck out the network
        if isinstance(addr, RemoteStation):
            self.addrType = Address.remoteStationAddr
            self.addrNet = addr.addrNet

        # if this is some other kind of address, suck out the guts
        if isinstance(addr, (LocalStation, RemoteStation)):
            if addr.addrAddr is None:
                raise ValueError("invalid address")
            if len(addr.addrAddr) != 6:
                raise ValueError("invalid address length")

            ipaddress.IPv4Interface.__init__(self, addr.addrAddr[:4])

            # extract the port
            port = struct.unpack("!H", addr.addrAddr[4:6])[0]

        elif isinstance(addr, int):
            if _debug:
                IPv4Address._debug("    - int")
            ipaddress.IPv4Interface.__init__(self, addr)

        elif isinstance(addr, str):
            if _debug:
                IPv4Address._debug("    - str")

            while True:
                ipv4_match = ipv4_address_mask_port_re.match(addr)
                if ipv4_match:
                    addr, _mask, _port = ipv4_match.groups()
                    if _debug:
                        IPv4Address._debug(
                            "    - addr, _mask, _port: %r, %r, %r", addr, _mask, _port
                        )
                    if not _mask:
                        _mask = "32"
                    ipaddress.IPv4Interface.__init__(self, addr + "/" + _mask)

                    if _port:
                        port = int(_port)
                    break

                ipv4_match = net_ipv4_address_mask_port_re.match(addr)
                if ipv4_match:
                    _net, addr, _mask, _port = ipv4_match.groups()
                    if _debug:
                        IPv4Address._debug(
                            "    - _net, addr, _mask, _port: %r, %r, %r",
                            _net,
                            addr,
                            _mask,
                            _port,
                        )
                    if not _mask:
                        _mask = "32"

                    self.addrType = Address.remoteStationAddr
                    self.addrNet = int(_net)

                    ipaddress.IPv4Interface.__init__(self, addr + "/" + _mask)

                    if _port:
                        port = int(_port)
                    break

                interface_port_match = interface_port_re.match(addr)
                if interface_port_match:
                    interface, _port = interface_port_match.groups()
                    if _debug:
                        IPv4Address._debug(
                            "    - interface, _port: %r, %r", interface, _port
                        )

                    ipv4_address: str = ""
                    host_ipv4_address: str = ""
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                        try:
                            # doesn't even have to be reachable
                            s.connect(("10.255.255.255", 1))
                            host_ipv4_address = s.getsockname()[0]
                        except Exception:
                            raise ValueError("no IPv4 address for host interface")
                    if _debug:
                        IPv4Address._debug(
                            "    - host_ipv4_address: %r", host_ipv4_address
                        )

                    if interface == "host":
                        if not host_ipv4_address:
                            raise ValueError("no IPv4 address for host interface")

                        if ifaddr:
                            adapters = ifaddr.get_adapters()

                            ipv4_to_ip = {}
                            for adapter in adapters:
                                for ip in adapter.ips:
                                    if isinstance(ip.ip, str):
                                        ipv4_to_ip[ip.ip] = ip
                            if host_ipv4_address not in ipv4_to_ip:
                                raise ValueError(
                                    "no matching IPv4 address for host interface"
                                )
                            ip = ipv4_to_ip[host_ipv4_address]

                            # extract the address the network size
                            ipv4_address = (
                                host_ipv4_address + "/" + str(ip.network_prefix)
                            )
                            ipaddress.IPv4Interface.__init__(self, ipv4_address)

                        else:
                            ipaddress.IPv4Interface.__init__(self, host_ipv4_address)
                        if _port:
                            port = int(_port)
                        break

                    if ifaddr:
                        # get the list of adapters
                        adapters = ifaddr.get_adapters()

                        for adapter in adapters:
                            if adapter.name == interface:
                                break
                        else:
                            raise ValueError("no interface: %r" % (interface,))

                        # get a list of the IPv4 addresses, IPv6 are tuples
                        ipv4_addresses = [
                            ip for ip in adapter.ips if isinstance(ip.ip, str)
                        ]
                        if len(ipv4_addresses) == 0:
                            raise ValueError(
                                "no IPv4 addresses for interface: %r" % (interface,)
                            )
                        if len(ipv4_addresses) > 1:
                            raise ValueError(
                                "multiple IPv4 addresses for interface: %r"
                                % (interface,)
                            )

                        # extract the address and the network size
                        ipv4_address = (
                            ipv4_addresses[0].ip
                            + "/"
                            + str(ipv4_addresses[0].network_prefix)
                        )

                        ipaddress.IPv4Interface.__init__(self, ipv4_address)
                        if _port:
                            port = int(_port)
                        break

                    if netifaces:
                        ifaddresses = netifaces.ifaddresses(interface)
                        ipv4_addresses = ifaddresses.get(netifaces.AF_INET, None)
                        if not ipv4_addresses:
                            raise ValueError(
                                "no IPv4 address for interface: %r" % (interface,)
                            )
                        if len(ipv4_addresses) > 1:
                            raise ValueError(
                                "multiple IPv4 addresses for interface: %r"
                                % (interface,)
                            )

                        ipv4_address = ipv4_addresses[0]
                        if _debug:
                            IPv4Address._debug("    - ipv4_address: %r", ipv4_address)

                        ipaddress.IPv4Interface.__init__(
                            self, ipv4_address["addr"] + "/" + ipv4_address["netmask"]
                        )

                        if _port:
                            port = int(_port)
                        break

                    raise RuntimeError(
                        "install ifaddr or netifaces for interface name addresses"
                    )

                raise ValueError("invalid address")

        elif isinstance(addr, (bytes, bytearray)):
            if _debug:
                IPv4Address._debug("    - bytes: %r..%r", addr[:4], addr[4:6])
            ipaddress.IPv4Interface.__init__(self, bytes(addr[:4]))

            # extract the port
            port = struct.unpack("!H", addr[4:6])[0]

        elif isinstance(addr, tuple):
            if _debug:
                IPv4Address._debug("    - tuple")
            addr, port = addr

            if isinstance(addr, int):
                ipaddress.IPv4Interface.__init__(self, addr)
            elif isinstance(addr, str):
                ipaddress.IPv4Interface.__init__(self, addr)

        elif isinstance(addr, ipaddress.IPv4Address):
            ipaddress.IPv4Interface.__init__(self, addr)

        else:
            raise ValueError("invalid address")

        self.addrAddr = self.packed + struct.pack("!H", port & _short_mask)
        self.addrLen = 6

        self.addrPort = port
        self.addrTuple = (self.ip.compressed, port)
        self.addrBroadcastTuple = (self.network.broadcast_address.compressed, port)

    def __str__(self) -> str:
        prefix = str(self.addrNet) + ":" if self.addrNet else ""
        suffix = ":" + str(self.addrPort) if (self.addrPort != 47808) else ""
        suffix += "@" + str(self.addrRoute) if self.addrRoute else ""

        return prefix + self.ip.compressed + suffix


#
#   IPv6Address
#


@bacpypes_debugging
class IPv6Address(Address, ipaddress.IPv6Interface):
    """
    Amazing documentation here.
    """

    addrPort: int
    addrTuple: Tuple[str, int, int, int]

    def __init__(
        self,
        addr: Union[
            LocalStation,
            RemoteStation,
            int,
            str,
            bytes,
            bytearray,
            Tuple[Union[str, int], int],
            ipaddress.IPv6Address,
        ],
        port: int = 47808,
        interface: Union[None, int, str] = None,
        route: Optional[Address] = None,
        network_type: str = "ipv6",
    ) -> None:
        if _debug:
            IPv6Address._debug("__init__ %r network_type=%r", addr, network_type)

        if network_type != "ipv6":
            raise ValueError("network type must be 'ipv6'")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = "ipv6"
        self.addrNet = None
        self.addrRoute = route

        # if this is a remote station, suck out the network
        if isinstance(addr, RemoteStation):
            self.addrType = Address.remoteStationAddr
            self.addrNet = addr.addrNet

        # if this is some other kind of address, suck out the guts
        if isinstance(addr, (LocalStation, RemoteStation)):
            if addr.addrAddr is None:
                raise ValueError("invalid address")
            addr = bytearray(addr.addrAddr)
            if len(addr) != 18:
                raise ValueError("invalid address length")

        if interface is None:
            interface_index = 0
        elif isinstance(interface, int):
            interface_index = interface
        elif isinstance(interface, str):
            interface_index = socket.if_nametoindex(interface)
        else:
            raise ValueError("invalid interface")
        if _debug:
            IPv6Address._debug("    - interface_index: %r", interface_index)

        if isinstance(addr, int):
            if _debug:
                IPv6Address._debug("    - int")
            ipaddress.IPv6Interface.__init__(self, addr)

        elif isinstance(addr, str):
            if _debug:
                IPv6Address._debug("    - str")

            while True:
                # matching the "raw" format like fe80::67a9/64%eno1
                ipv6_match = ipv6_address_interface_re.match(addr)
                if ipv6_match:
                    addr, _interface = ipv6_match.groups()
                    if _debug:
                        IPv6Address._debug(
                            "    - addr, _interface: %r, %r", addr, _interface
                        )

                    if (_interface and interface is not None) and (
                        _interface != interface
                    ):
                        raise ValueError("interface mismatch")
                        interface = _interface

                    if _interface:
                        interface_index = socket.if_nametoindex(_interface)
                        if _debug:
                            IPv6Address._debug(
                                "    - interface_index: %r", interface_index
                            )

                    ipaddress.IPv6Interface.__init__(self, addr)
                    break

                # matching the extended format with optional port
                # [fe80::67a9/64]:47809%eno1
                ipv6_match = ipv6_address_port_interface_re.match(addr)
                if ipv6_match:
                    addr, _port, _interface = ipv6_match.groups()
                    if _debug:
                        IPv6Address._debug(
                            "    - addr, _port, _interface: %r, %r, %r",
                            addr,
                            _port,
                            _interface,
                        )

                    if (_interface and interface is not None) and (
                        _interface != interface
                    ):
                        raise ValueError("interface mismatch")
                        interface = _interface

                    if _interface:
                        interface_index = socket.if_nametoindex(_interface)
                        if _debug:
                            IPv6Address._debug(
                                "    - interface_index: %r", interface_index
                            )

                    ipaddress.IPv6Interface.__init__(self, addr)

                    if _port:
                        port = int(_port)
                    break

                # matching the extended format with network and optional port
                # 99:[fe80::67a9/64]:47809
                ipv6_match = net_ipv6_address_port_re.match(addr)
                if ipv6_match:
                    _net, addr, _port = ipv6_match.groups()
                    if _debug:
                        IPv6Address._debug(
                            "    - _net, addr, _port: %r, %r, %r", _net, addr, _port
                        )

                    if _net:
                        self.addrType = Address.remoteStationAddr
                        self.addrNet = int(_net)

                    ipaddress.IPv6Interface.__init__(self, addr)

                    if _port:
                        port = int(_port)
                    break

                # matching an interface name with an optional port eno1:47809
                interface_port_match = interface_port_re.match(addr)
                if interface_port_match:
                    if not netifaces:
                        raise RuntimeError(
                            "install netifaces for interface name addresses"
                        )

                    _interface, _port = interface_port_match.groups()
                    if _debug:
                        IPv6Address._debug(
                            "    - _interface, _port: %r, %r", _interface, _port
                        )

                    if (_interface and interface is not None) and (
                        _interface != interface
                    ):
                        raise ValueError("interface mismatch")
                        interface = _interface

                    if _port:
                        port = int(_port)

                    ifaddresses = netifaces.ifaddresses(_interface)
                    ipv6_addresses = ifaddresses.get(netifaces.AF_INET6, None)
                    if not ipv6_addresses:
                        ValueError("no IPv6 address for interface: %r" % (interface,))
                    if len(ipv6_addresses) > 1:
                        ValueError(
                            "multiple IPv6 addresses for interface: %r" % (interface,)
                        )

                    ipv6_address = ipv6_addresses[0]
                    if _debug:
                        IPv6Address._debug("    - ipv6_address: %r", ipv6_address)

                    # get the address
                    addr_str = ipv6_address["addr"]
                    if _debug:
                        IPv6Address._debug("    - addr_str: %r", addr_str)

                    # find the interface name (a.k.a. scope identifier)
                    if "%" in addr_str:
                        addr_str, _interface = addr_str.split("%")
                        if (interface is not None) and (_interface != interface):
                            raise ValueError("interface mismatch")

                        interface_index = socket.if_nametoindex(_interface)
                        if _debug:
                            IPv6Address._debug(
                                "    - interface_index: %r", interface_index
                            )

                    # if the prefix length is in the address, leave it, otherwise
                    # convert the netmask to a prefix length
                    if "/" not in addr_str:
                        netmask_bytes = xtob(ipv6_address["netmask"].replace(":", ""))
                        prefix_len = sum(bin(x).count("1") for x in netmask_bytes)
                        addr_str += "/" + str(prefix_len)

                    ipaddress.IPv6Interface.__init__(self, addr_str)
                    break

                # raw, perhaps compressed, address
                if re.match("^[.:0-9A-Fa-f]+$", addr):
                    if _debug:
                        IPv6Address._debug("    - just an address")
                    ipaddress.IPv6Interface.__init__(self, addr)
                    break

                raise ValueError("invalid address")

        elif isinstance(addr, (bytes, bytearray)):
            if _debug:
                IPv6Address._debug("    - bytes")
            if len(addr) != 18:
                raise ValueError("IPv6 requires 18 bytes")

            ipaddress.IPv6Interface.__init__(self, bytes(addr[:16]))

            # extract the port
            port = struct.unpack("!H", addr[16:18])[0]

        elif isinstance(addr, tuple):
            if _debug:
                IPv6Address._debug("    - tuple")
            addr, port = addr[:2]

            if isinstance(addr, (int, str)):
                ipaddress.IPv6Interface.__init__(self, addr)

        elif isinstance(addr, ipaddress.IPv6Address):
            ipaddress.IPv6Interface.__init__(self, addr)

        else:
            raise ValueError("invalid address")

        self.addrAddr = self.packed + struct.pack("!H", port & _short_mask)
        self.addrLen = len(self.addrAddr)

        self.addrPort = port
        self.addrTuple = (self.ip.compressed, port, 0, interface_index)

    def __str__(self) -> str:
        prefix = str(self.addrNet) + ":[" if self.addrNet else "["
        suffix = "]:" + str(self.addrPort) if (self.addrPort != 47808) else "]"
        suffix += "@" + str(self.addrRoute) if self.addrRoute else ""

        return prefix + self.ip.compressed + suffix


#
#   IPv6MulticastAddress
#


@bacpypes_debugging
class IPv6MulticastAddress(LocalBroadcast, ipaddress.IPv6Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self,
        addr: str,
        port: int = 47808,
        interface: Union[None, int, str] = None,
        route: Optional[Address] = None,
    ) -> None:
        if _debug:
            IPv6MulticastAddress._debug("__init__ %r", addr)

        LocalBroadcast.__init__(self, network_type="ipv6")

        if isinstance(addr, str) and re.match("^[.:0-9A-Fa-f]+$", addr):
            if _debug:
                IPv6MulticastAddress._debug("    - str")
            ipaddress.IPv6Address.__init__(self, addr)
        else:
            raise ValueError("invalid address")

        # a little error checking
        if not self.is_multicast:
            raise ValueError("not a multicast address: %r" % (addr,))

        if interface is None:
            interface_index = 0
        elif isinstance(interface, int):
            interface_index = interface
        elif isinstance(interface, str):
            interface_index = socket.if_nametoindex(interface)
        else:
            raise ValueError("invalid interface")
        if _debug:
            IPv6MulticastAddress._debug("    - interface_index: %r", interface_index)

        self.addrPort = port
        self.addrTuple = (self.compressed, port, 0, interface_index)
        self.addrRoute = route

    def __str__(self) -> str:
        if _debug:
            IPv6MulticastAddress._debug("__str__")
        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return ipaddress.IPv6Address.__str__(self) + suffix


#
#   IPv6InterfaceLocalMulticastAddress
#


@bacpypes_debugging
class IPv6InterfaceLocalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6InterfaceLocalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff01::bac0", port=port, interface=interface
        )


#
#   IPv6LinkLocalMulticastAddress
#


@bacpypes_debugging
class IPv6LinkLocalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6LinkLocalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff02::bac0", port=port, interface=interface
        )


#
#   IPv6RealmLocalMulticastAddress
#


@bacpypes_debugging
class IPv6RealmLocalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6RealmLocalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff03::bac0", port=port, interface=interface
        )


#
#   IPv6AdminLocalMulticastAddress
#


@bacpypes_debugging
class IPv6AdminLocalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6AdminLocalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff04::bac0", port=port, interface=interface
        )


#
#   IPv6SiteLocalMulticastAddress
#


@bacpypes_debugging
class IPv6SiteLocalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6SiteLocalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff05::bac0", port=port, interface=interface
        )


#
#   IPv6OrganizationLocalMulticastAddress
#


@bacpypes_debugging
class IPv6OrganizationLocalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6OrganizationLocalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff08::bac0", port=port, interface=interface
        )


#
#   IPv6GlobalMulticastAddress
#


@bacpypes_debugging
class IPv6GlobalMulticastAddress(IPv6MulticastAddress):
    """
    Amazing documentation here.
    """

    def __init__(
        self, port: int = 47808, interface: Union[None, int, str] = None
    ) -> None:
        if _debug:
            IPv6GlobalMulticastAddress._debug("__init__")
        IPv6MulticastAddress.__init__(
            self, "ff0e::bac0", port=port, interface=interface
        )


#
#   VirtualAddress
#


@bacpypes_debugging
class VirtualAddress(Address):
    """
    Amazing documentation here.
    """

    def __init__(
        self,
        addr: Union[int, bytes, bytearray, str],
        route: Optional[Address] = None,
        network_type: str = "virtual",
    ) -> None:
        if _debug:
            VirtualAddress._debug("__init__ %r network_type=%r", addr, network_type)

        if network_type != "virtual":
            raise ValueError("network type must be 'virtual'")

        self.addrType = Address.localStationAddr
        self.addrNetworkType = "virtual"
        self.addrNet = None
        self.addrRoute = route

        if _debug:
            VirtualAddress._debug("    - %r", type(addr))

        if isinstance(addr, (bytes, bytearray)):
            if _debug:
                VirtualAddress._debug("    - bytes, bytearray")
            self.addrAddr = bytes(addr)

        elif isinstance(addr, str):
            if not addr.startswith("0x"):
                raise ValueError("invalid address")

            self.addrAddr = xtob(addr[2:])

        else:
            raise ValueError("invalid address")

        self.addrLen = len(self.addrAddr)

    def __str__(self) -> str:
        assert self.addrAddr is not None

        prefix = str(self.addrNet) + ":" if self.addrNet else ""
        suffix = "@" + str(self.addrRoute) if self.addrRoute else ""
        return prefix + "0x" + btox(self.addrAddr) + suffix


#
#   Network Types
#

network_types = {
    "null": NullAddress,  # not a standard type
    "ethernet": EthernetAddress,
    "arcnet": ARCNETAddress,
    "mstp": MSTPAddress,
    #   'ptp': PTPAddress,
    #   'lontalk': LonTalkAddress,
    "ipv4": IPv4Address,
    #   'zigbee': ZigbeeAddress,
    "virtual": VirtualAddress,
    "ipv6": IPv6Address,
    #   'serial': SerialAddress,
    #   'secureConnect': SecureConnectAddress,
    #   'websocket': WebSocketAddress,
}


#
#   PCI
#


@bacpypes_debugging
class PCI(DebugContents):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "pduSource",
        "pduDestination",
        "pduExpectingReply",
        "pduNetworkPriority",
        "pduUserData+",
    )

    pduSource: Optional[Any]
    pduDestination: Optional[Any]
    pduExpectingReply: bool
    pduNetworkPriority: int
    pduUserData: Optional[bytes]

    def __init__(
        self,
        *,
        source: Optional[Any] = None,
        destination: Optional[Any] = None,
        expectingReply: bool = False,
        networkPriority: int = 0,
        user_data: Optional[bytes] = None,
    ) -> None:
        if _debug:
            PCI._debug("__init__")

        # this call will fail if there are args or kwargs, but not if there
        # is another class in the __mro__ of this thing being constructed
        # super(PCI, self).__init__(*args, **kwargs)

        # save the values
        self.pduSource = source
        self.pduDestination = destination
        self.pduExpectingReply = expectingReply
        self.pduNetworkPriority = networkPriority
        self.pduUserData = user_data

    def update(self, pci: PCI) -> None:
        """Copy the PCI fields."""
        if _debug:
            PCI._debug("update %r", pci)

        self.pduUserData = pci.pduUserData
        self.pduSource = pci.pduSource
        self.pduDestination = pci.pduDestination
        self.pduExpectingReply = pci.pduExpectingReply
        self.pduNetworkPriority = pci.pduNetworkPriority
        self.pduUserData = pci.pduUserData

    def pci_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
    ) -> Dict[str, Any]:
        """Return the PCI contents as a dictionary or some other kind of mapping class."""
        if _debug:
            PCI._debug("pci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the values
        for k, v in (
            ("source", self.pduSource),
            ("destination", self.pduDestination),
            ("expectingReply", self.pduExpectingReply),
            ("networkPriority", self.pduNetworkPriority),
            ("user_data", self.pduUserData),
        ):
            if _debug:
                PCI._debug("    - %r: %r", k, v)
            if v is None:
                continue

            if hasattr(v, "dict_contents"):
                v = v.dict_contents(as_class=as_class)  # type: ignore[union-attr]
            use_dict.__setitem__(k, v)

        # return what we built/updated
        return use_dict

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
    ) -> Dict[str, Any]:
        """Return the PCI contents as a dictionary or some other kind of mapping class."""
        if _debug:
            PCI._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        return self.pci_contents(use_dict=use_dict, as_class=as_class)


#
#   PDUData
#


@bacpypes_debugging
class PDUData:
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    pduData: bytearray

    def __init__(self, data: Union[bytes, bytearray, "PDUData", None] = None):
        if _debug:
            PDUData._debug("__init__ %r", data)

        # this call will fail if there are args or kwargs, but not if there
        # is another class in the __mro__ of this thing being constructed
        # super(PDUData, self).__init__(*args, **kwargs)

        # function acts like a copy constructor
        if data is None:
            self.pduData = bytearray()
        elif isinstance(data, (bytes, bytearray)):
            self.pduData = bytearray(data)
        elif isinstance(data, PDUData):
            self.pduData = _copy(data.pduData)
        else:
            raise TypeError("bytes or bytearray expected")

    def get(self) -> int:
        if len(self.pduData) == 0:
            raise DecodingError("no more packet data")

        octet = self.pduData[0]
        del self.pduData[0]

        return octet

    def get_data(self, dlen: int) -> bytearray:
        if len(self.pduData) < dlen:
            raise DecodingError("no more packet data")

        data = self.pduData[:dlen]
        del self.pduData[:dlen]

        return data

    def get_short(self) -> int:
        return struct.unpack(">H", self.get_data(2))[0]  # type: ignore[no-any-return]

    def get_long(self) -> int:
        return struct.unpack(">L", self.get_data(4))[0]  # type: ignore[no-any-return]

    def put(self, n: int) -> None:
        # pduData is a bytearray
        self.pduData += bytes([n])

    def put_data(self, data: Union[bytes, bytearray, List[int]]) -> None:
        if isinstance(data, bytes):
            pass
        elif isinstance(data, bytearray):
            pass
        elif isinstance(data, list):
            data = bytes(data)
        else:
            raise TypeError("data must be bytes, bytearray, or a list")

        # regular append works
        self.pduData += data

    def put_short(self, n: int) -> None:
        self.pduData += struct.pack(">H", n & _short_mask)

    def put_long(self, n: int) -> None:
        self.pduData += struct.pack(">L", n & _long_mask)

    def debug_contents(
        self,
        indent: int = 1,
        file: TextIO = sys.stderr,
        _ids: Optional[List[Any]] = None,
    ) -> None:
        if isinstance(self.pduData, bytearray):
            if len(self.pduData) > 20:
                hexed = btox(self.pduData[:20], ".") + "..."
            else:
                hexed = btox(self.pduData, ".")
            file.write("%spduData = x'%s'\n" % ("    " * indent, hexed))
        else:
            file.write("%spduData = %r\n" % ("    " * indent, self.pduData))

    def pdudata_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
    ) -> Dict[str, Any]:
        """Return the PCI contents as a dictionary or some other kind of mapping class."""
        if _debug:
            PDUData._debug(
                "pdudata_contents use_dict=%r as_class=%r", use_dict, as_class
            )

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # add the data if it is not None
        v = self.pduData
        if v is not None:
            if isinstance(v, bytearray):
                use_dict.__setitem__("data", btox(v))
            elif hasattr(v, "dict_contents"):
                v = v.dict_contents(as_class=as_class)

        # return what we built/updated
        return use_dict

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
    ) -> Dict[str, Any]:
        """Return the PCI contents as a dictionary or some other kind of mapping class."""
        if _debug:
            PDUData._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        return self.pdudata_contents(use_dict=use_dict, as_class=as_class)


#
#   PDU
#


@bacpypes_debugging
class PDU(PCI, PDUData):
    """
    Amazing documentation here.
    """

    _debug: Callable[..., None]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if _debug:
            PDU._debug("__init__ %r %r", args, kwargs)
        PCI.__init__(self, **kwargs)
        PDUData.__init__(self, *args)

    def __str__(self) -> str:
        return "<%s %s -> %s : %s>" % (
            self.__class__.__name__,
            self.pduSource,
            self.pduDestination,
            btox(self.pduData, "."),
        )

    def dict_contents(
        self,
        use_dict: Optional[Dict[str, Any]] = None,
        as_class: Union[Callable[[], Dict[str, Any]]] = dict,
    ) -> Dict[str, Any]:
        """Return the PCI contents as a dictionary or some other kind of mapping class."""
        if _debug:
            PDUData._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call into the two base classes
        self.pci_contents(use_dict=use_dict, as_class=as_class)
        self.pdudata_contents(use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict
