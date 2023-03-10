"""
Application Module
"""

from __future__ import annotations

import asyncio

from ..debugging import bacpypes_debugging, ModuleLogger

from ..comm import bind
from ..pdu import Address, IPv4Address
from ..object import DeviceObject

from ..appservice import ApplicationServiceAccessPoint
from ..netservice import NetworkServiceAccessPoint, NetworkServiceElement

from ..ipv4 import IPv4DatagramServer
from .bvll import BVLLCodec
from .service import BIPForeign, BIPBBMD, UDPMultiplexer
from .link import NormalLinkLayer

# application starting point
from ..app import Application

# basic services
from ..service.device import WhoIsIAmServices, WhoHasIHaveServices
from ..service.object import (
    ReadWritePropertyServices,
    ReadWritePropertyMultipleServices,
)

# bridge to mock a network port object
from ..local.networkport import NetworkPortObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   NormalApplication
#


@bacpypes_debugging
class NormalApplication(
    Application,
    WhoIsIAmServices,
    WhoHasIHaveServices,
    ReadWritePropertyServices,
    ReadWritePropertyMultipleServices,
):
    """
    Normal Application IPv4 Stack
    """

    def __init__(
        self, device_object, localAddress: Address, deviceInfoCache=None
    ) -> None:
        if _debug:
            NormalApplication._debug(
                "__init__ %r %r deviceInfoCache=%r",
                device_object,
                localAddress,
                deviceInfoCache,
            )
        Application.__init__(self, deviceInfoCache=deviceInfoCache)
        if not isinstance(localAddress, IPv4Address):
            raise TypeError(f"localAddress: {type(localAddress)}")
        if not isinstance(localAddress, DeviceObject):
            raise TypeError(f"device_object: {type(device_object)}")

        # add/bind the device object and a network port object
        self.add_object(device_object)
        self.add_object(
            NetworkPortObject(
                localAddress,
                objectName="NetworkPort1",
                objectIdentifier=("network-port", 1),
            )
        )

        # a application service access point will be needed
        self.asap = ApplicationServiceAccessPoint(
            self.device_object, self.deviceInfoCache
        )
        if _debug:
            NormalApplication._debug("    - asap: %r", self.asap)

        # a network service access point will be needed
        self.nsap = NetworkServiceAccessPoint()
        if _debug:
            NormalApplication._debug("    - nsap: %r", self.nsap)

        # give the NSAP a generic network layer service element
        self.nse = NetworkServiceElement()
        if _debug:
            NormalApplication._debug("    - nse: %r", self.nse)
        bind(self.nse, self.nsap)

        # bind the top layers
        bind(self, self.asap, self.nsap)

        # create a "normal" virtual link layer
        self.normal = NormalLinkLayer(localAddress)
        if _debug:
            NormalApplication._debug("    - asap: %r", self.asap)

        # bind the BIP stack to the network, no network number
        self.nsap.bind(self.normal, address=localAddress)

    def close(self):
        if _debug:
            NormalApplication._debug("close")
        self.normal.close()


#
#   ForeignApplication
#


@bacpypes_debugging
class ForeignApplication(
    Application,
    WhoIsIAmServices,
    WhoHasIHaveServices,
    ReadWritePropertyServices,
    ReadWritePropertyMultipleServices,
):
    def __init__(
        self, device_object, localAddress: Address, deviceInfoCache=None
    ) -> None:
        if _debug:
            ForeignApplication._debug(
                "__init__ %r %r deviceInfoCache=%r",
                device_object,
                localAddress,
                deviceInfoCache,
            )
        Application.__init__(self, deviceInfoCache=deviceInfoCache)
        if not isinstance(localAddress, IPv4Address):
            raise TypeError(f"localAddress: {type(localAddress)}")
        if not isinstance(device_object, DeviceObject):
            raise TypeError(f"device_object: {type(device_object)}")

        # add/bind the device object and a network port object
        self.add_object(device_object)
        self.add_object(NetworkPortObject(localAddress))

        # get the event loop
        self.loop = asyncio.get_event_loop()

        # a application service access point will be needed
        self.asap = ApplicationServiceAccessPoint(
            self.device_object, self.deviceInfoCache
        )

        # a network service access point will be needed
        self.nsap = NetworkServiceAccessPoint()

        # give the NSAP a generic network layer service element
        self.nse = NetworkServiceElement()
        bind(self.nse, self.nsap)

        # bind the top layers
        bind(self, self.asap, self.nsap)

        # create a B/IP stack as a foreign device, bound to the Annex J server
        # on the UDP multiplexer without a broadcast listener
        self.foreign = BIPForeign()
        self.codec = BVLLCodec()
        self.multiplexer = UDPMultiplexer()
        self.server = IPv4DatagramServer(self.loop, localAddress, no_broadcast=True)

        bind(self.foreign, self.codec, self.multiplexer.annexJ)  # type: ignore[arg-type]
        bind(self.multiplexer, self.server)  # type: ignore[arg-type]

        # bind the BIP stack to the network, no network number
        self.nsap.bind(self.foreign, address=localAddress)

    def register(self, addr: IPv4Address, ttl: int) -> None:
        """Facade for foreign device API."""
        self.foreign.register(addr, ttl)

    def unregister(self):
        """Facade for foreign device API."""
        self.foreign.unregister()

    def close(self):
        self.server.close()


#
#   BBMDApplication
#


@bacpypes_debugging
class BBMDApplication(
    Application,
    WhoIsIAmServices,
    WhoHasIHaveServices,
    ReadWritePropertyServices,
    ReadWritePropertyMultipleServices,
):
    def __init__(
        self, device_object, localAddress: Address, deviceInfoCache=None
    ) -> None:
        if _debug:
            BBMDApplication._debug(
                "__init__ %r %r deviceInfoCache=%r",
                device_object,
                localAddress,
                deviceInfoCache,
            )
        Application.__init__(self, deviceInfoCache=deviceInfoCache)
        if not isinstance(localAddress, IPv4Address):
            raise TypeError(f"localAddress: {type(localAddress)}")
        if not isinstance(device_object, DeviceObject):
            raise TypeError(f"device_object: {type(device_object)}")

        # add/bind the device object and a network port object
        self.add_object(device_object)
        self.add_object(NetworkPortObject(localAddress))

        # get the event loop
        self.loop = asyncio.get_event_loop()

        # a application service access point will be needed
        self.asap = ApplicationServiceAccessPoint(
            self.device_object, self.deviceInfoCache
        )

        # a network service access point will be needed
        self.nsap = NetworkServiceAccessPoint()

        # give the NSAP a generic network layer service element
        self.nse = NetworkServiceElement()
        bind(self.nse, self.nsap)

        # bind the top layers
        bind(self, self.asap, self.nsap)

        # create a B/IP stack as a BBMD, bound to the Annex J server
        self.bbmd = BIPBBMD()
        self.codec = BVLLCodec()
        self.multiplexer = UDPMultiplexer()
        self.server = IPv4DatagramServer(self.loop, localAddress)

        bind(self.foreign, self.codec, self.multiplexer.annexJ)  # type: ignore[arg-type]
        bind(self.multiplexer, self.server)  # type: ignore[arg-type]

        # bind the BIP stack to the network, no network number
        self.nsap.bind(self.foreign, address=localAddress)

    def register_foreign_device(self, addr: IPv4Address, ttl: int) -> int:
        """Facade for BBMD API."""
        return self.bbmd.register_foreign_device(addr, ttl)

    def delete_foreign_device_table_entry(self, addr: IPv4Address) -> int:
        """Facade for BBMD API."""
        return self.bbmd.delete_foreign_device_table_entry(addr)

    def add_peer(self, addr: IPv4Address) -> None:
        """Facade for BBMD API."""
        self.bbmd.add_peer(addr)

    def delete_peer(self, addr: IPv4Address) -> None:
        """Facade for BBMD API."""
        self.bbmd.delete_peer(addr)

    def close(self):
        self.server.close()
