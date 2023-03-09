"""
Link Layer Module

Classes in this module extend the BVLLServiceAccessPoint subclasses with
additional components necessary to send packets own to the physical network,
including a UDP multiplexer to distinguish between Annex-H and Annex-J traffic
anda IPv4DatagramServer instance to send and receive UDP packetes.

The clients of instances of these object (next up the stack) is a NetworkAdapter
instance which references a NetworkServiceAccessPoint.
"""

from __future__ import annotations

from ..debugging import bacpypes_debugging, ModuleLogger

from ..comm import bind
from ..pdu import IPv4Address

from ..ipv4 import IPv4DatagramServer
from .bvll import BVLLCodec
from .service import BIPNormal, BIPForeign, BIPBBMD, UDPMultiplexer

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   NormalLinkLayer
#


@bacpypes_debugging
class NormalLinkLayer(BIPNormal):
    """
    Create a link layer mini-stack starting with the "normal"
    BVLLServiceAccessPoint (parent class of BIPNormal) down to the datagram
    server.
    """

    codec: BVLLCodec
    multiplexer: UDPMultiplexer
    server: IPv4DatagramServer

    def __init__(self, local_address: IPv4Address, **kwargs) -> None:
        if _debug:
            NormalLinkLayer._debug(
                "__init__ %r %r",
                local_address,
                kwargs,
            )
        BIPNormal.__init__(self, **kwargs)

        # create a normal B/IP stack, bound to the Annex J server
        # on the UDP multiplexer
        self.codec = BVLLCodec()
        self.multiplexer = UDPMultiplexer()
        self.server = IPv4DatagramServer(local_address)

        bind(self, self.codec, self.multiplexer.annexJ)  # type: ignore[arg-type]
        bind(self.multiplexer, self.server)  # type: ignore[arg-type]

    def close(self):
        if _debug:
            NormalLinkLayer._debug("close")
        self.server.close()


#
#   ForeignLinkLayer
#


@bacpypes_debugging
class ForeignLinkLayer(BIPForeign):
    """
    Create a link layer mini-stack starting with the "foreign"
    BVLLServiceAccessPoint (parent class of BIPForeign) down to the datagram
    server.
    """

    codec: BVLLCodec
    multiplexer: UDPMultiplexer
    server: IPv4DatagramServer

    def __init__(self, local_address: IPv4Address, **kwargs) -> None:
        if _debug:
            ForeignLinkLayer._debug(
                "__init__ %r %r",
                local_address,
                kwargs,
            )
        BIPForeign.__init__(self, **kwargs)

        # create a foreign B/IP stack, bound to the Annex J server
        # on the UDP multiplexer
        self.codec = BVLLCodec()
        self.multiplexer = UDPMultiplexer()
        self.server = IPv4DatagramServer(local_address)

        bind(self, self.codec, self.multiplexer.annexJ)  # type: ignore[arg-type]
        bind(self.multiplexer, self.server)  # type: ignore[arg-type]

    def close(self):
        if _debug:
            ForeignLinkLayer._debug("close")
        self.server.close()


#
#   BBMDLinkLayer
#


@bacpypes_debugging
class BBMDLinkLayer(BIPBBMD):
    """
    Create a link layer mini-stack starting with the BBMD
    BVLLServiceAccessPoint (parent class of BIPBBMD) down to the datagram
    server.
    """

    codec: BVLLCodec
    multiplexer: UDPMultiplexer
    server: IPv4DatagramServer

    def __init__(self, local_address: IPv4Address, **kwargs) -> None:
        if _debug:
            BBMDLinkLayer._debug(
                "__init__ %r %r",
                local_address,
                kwargs,
            )
        BIPBBMD.__init__(self, local_address, **kwargs)

        # create a BBMD B/IP stack, bound to the Annex J server
        # on the UDP multiplexer
        self.codec = BVLLCodec()
        self.multiplexer = UDPMultiplexer()
        self.server = IPv4DatagramServer(local_address)

        bind(self, self.codec, self.multiplexer.annexJ)  # type: ignore[arg-type]
        bind(self.multiplexer, self.server)  # type: ignore[arg-type]

    def close(self):
        if _debug:
            BBMDLinkLayer._debug("close")
        self.server.close()
