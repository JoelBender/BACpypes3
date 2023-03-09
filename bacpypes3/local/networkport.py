"""
Network Port Object
"""

from __future__ import annotations

from typing import Callable, Optional

from ..debugging import bacpypes_debugging, ModuleLogger
from ..pdu import Address, IPv4Address, IPv6Address
from ..primitivedata import CharacterString, ObjectType

from ..basetypes import NetworkType, NetworkNumberQuality
from ..object import NetworkPortObject as _NetworkPortObject

from .object import Object as _Object

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# this is for sample applications
_vendor_id = 999


@bacpypes_debugging
class NetworkPortObject(_Object, _NetworkPortObject):
    """
    A local network port object.
    """

    _debug: Callable[..., None]

    objectType = ObjectType.networkPort

    def __init__(
        self, addr: Optional[Address, CharacterString] = None, *args, **kwargs
    ) -> None:
        if _debug:
            NetworkPortObject._debug("__init__ %r %r %r", addr, args, kwargs)

        if not addr:
            super().__init__(*args, **kwargs)
            return

        # make it an address of some kind
        if not isinstance(addr, Address):
            addr = Address(addr)

        # default values
        default_kwargs = {
            "statusFlags": [0, 0, 0, 0],
            "reliability": "no-fault-detected",
            "outOfService": False,
            "changesPending": False,
            "linkSpeed": 0.0,  # unknown
        }

        if isinstance(addr, IPv4Address):
            if _debug:
                NetworkPortObject._debug("    - IPv4")
            default_kwargs.update(
                {
                    "macAddress": addr.addrAddr,
                    "networkType": "ipv4",
                    "protocolLevel": "bacnet-application",
                    "bacnetIPMode": "normal",
                    "ipAddress": addr.addrAddr[:4],
                    "ipSubnetMask": addr.netmask.packed,
                    "bacnetIPUDPPort": addr.addrPort,
                    # ipDefaultGateway = netifaces.gateways()['default'][netifaces.AF_INET][0]
                    # ipDNSServer = [b"\x00" * 4]  # not available or not configured
                }
            )

        elif isinstance(addr, IPv6Address):
            if _debug:
                NetworkPortObject._debug("    - IPv6")
            default_kwargs.update(
                {
                    "macAddress": addr.addrAddr,
                    "networkType": "ipv6",
                    "protocolLevel": "bacnet-application",
                    "bacnetIPv6Mode": "normal",
                    "ipv6Address": addr.packed[:16],
                    "ipv6PrefixLength": addr._prefixlen,
                    "bacnetIPv6UDPPort": addr.addrPort,
                    # bacnetIPv6MulticastAddress = ? https://en.wikipedia.org/wiki/IPv6_address#Address_scopes
                    # ipv6DefaultGateway = ?
                    # ipv6DNSServer = [b"\x00" * 16]  # not available or not configured
                }
            )

        else:
            raise TypeError("addr: IPv4 or IPv6 address expected")

        if addr.addrNet is None:
            default_kwargs.update(
                {
                    "networkNumber": 0,
                    "networkNumberQuality": NetworkNumberQuality.unknown,
                }
            )
        else:
            default_kwargs.update(
                {
                    "networkNumber": addr.addrNet,
                    "networkNumberQuality": NetworkNumberQuality.configured,
                }
            )

        """
            mode == foreign
                fdBBMDAddress: HostNPort
                fdSubscriptionLifetime: Unsigned16
            mode == bbmd
                bbmdBroadcastDistributionTable: ListOf(BDTEntry)
                bbmdAcceptFDRegistrations: Boolean
                bbmdForeignDeviceTable: ListOf(FDTEntry)
        """

        # allow kwargs override defaults
        default_kwargs.update(kwargs)

        super().__init__(*args, **default_kwargs)

    @property
    def address(self) -> Address:
        """
        Interpret the contents returning an Address that has all the
        tuples necessary for sockets.
        """
        if _debug:
            NetworkPortObject._debug("address(getter)")

        if self.networkType == NetworkType.ipv4:
            if _debug:
                NetworkPortObject._debug("    - IPv4")

            addr = ".".join(str(x) for x in self.ipAddress[:4])
            mask = ".".join(str(x) for x in self.ipSubnetMask)
            port = str(self.bacnetIPUDPPort)

            return IPv4Address(addr + "/" + mask + ":" + port)

        elif self.networkType == NetworkType.ipv6:
            if _debug:
                NetworkPortObject._debug("    - IPv6")
            raise NotImplementedError("no IPv6 yet")

        return None
