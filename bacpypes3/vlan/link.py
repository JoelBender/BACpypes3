"""
Link Layer Module

Classes in this module extend the BVLLServiceAccessPoint subclasses with
additional components necessary to send packets down to a virtual network.

The clients of instances of these object (next up the stack) is a NetworkAdapter
instance which references a NetworkServiceAccessPoint.
"""

from __future__ import annotations

from ..debugging import bacpypes_debugging, ModuleLogger

from ..comm import bind, Server
from ..pdu import PDU, LocalStation

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   VirtualLinkLayer
#


@bacpypes_debugging
class VirtualLinkLayer(Server[PDU]):
    """
    Create a link layer mini-stack ...
    """

    def __init__(
        self, local_address: LocalStation, network_interface_name: str, **kwargs
    ) -> None:
        if _debug:
            VirtualLinkLayer._debug(
                "__init__ %r %r %r",
                local_address,
                network_interface_name,
                kwargs,
            )

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            VirtualLinkLayer._debug("indication %r", pdu)

    def close(self):
        if _debug:
            VirtualLinkLayer._debug("close")
