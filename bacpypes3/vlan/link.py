"""
Link Layer Module

Classes in this module extend the BVLLServiceAccessPoint subclasses with
additional components necessary to send packets down to a virtual network.

The clients of instances of these object (next up the stack) is a NetworkAdapter
instance which references a NetworkServiceAccessPoint.
"""

from __future__ import annotations

from ..debugging import bacpypes_debugging, ModuleLogger

from ..comm import bind, Client, Server
from ..pdu import PDU, LocalStation
from ..vlan import VirtualNode

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   VirtualLinkLayer
#


@bacpypes_debugging
class VirtualLinkLayer(Client[PDU], Server[PDU]):
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

        # create a node
        self.node = VirtualNode(local_address, network_interface_name)

        # add it below this in the stack
        bind(self, self.node)

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            VirtualLinkLayer._debug("indication %r", pdu)

        # continue down the stack
        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            VirtualLinkLayer._debug("confirmation %r", pdu)

        # countinue up the stack
        await self.response(pdu)

    def close(self):
        if _debug:
            VirtualLinkLayer._debug("close")
