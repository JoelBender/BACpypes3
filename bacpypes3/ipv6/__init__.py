"""
IPv6
"""

import asyncio
import socket
import struct
import functools

from typing import Any, Callable, List, Tuple, Optional, cast

from ..debugging import ModuleLogger, bacpypes_debugging

from ..comm import Server
from ..pdu import LocalBroadcast, IPv6Address, IPv6LinkLocalMulticastAddress, PDU

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class IPv6DatagramProtocol(asyncio.DatagramProtocol):

    _debug: Callable[..., None]

    server: "IPv6DatagramServer"

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if _debug:
            IPv6DatagramProtocol._debug("connection_made %r", transport)

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        if _debug:
            IPv6DatagramProtocol._debug("datagram_received %r %r", data, addr)

        pdu = PDU(data, source=IPv6Address(addr))
        asyncio.ensure_future(self.server.confirmation(pdu))

    def error_received(self, exc: Exception) -> None:
        if _debug:
            IPv6DatagramProtocol._debug("error_received %r", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if _debug:
            IPv6DatagramProtocol._debug("connection_lost %r", exc)


@bacpypes_debugging
class IPv6DatagramServer(Server[PDU]):

    _debug: Callable[..., None]
    _exception: Callable[..., None]
    _transport_tasks: List[Any]

    interface_index: int
    local_address: Tuple[str, int, int, int]
    transport: asyncio.DatagramTransport
    protocol: IPv6DatagramProtocol

    def __init__(
        self,
        address: IPv6Address,
    ) -> None:
        if _debug:
            IPv6DatagramServer._debug("__init__ %r", address)

        # grab the loop to create tasks and endpoints
        loop: asyncio.events.AbstractEventLoop = asyncio.get_running_loop()

        # save the local address to check for reflections
        self.local_address = address.addrTuple
        if _debug:
            IPv6DatagramServer._debug("    - local_address: %r", self.local_address)

        # the address tuple contains the interface index as the last element,
        # like ('::', 47808, 0, 0) for any interface, or if attempting to bind
        # to a specific interface, the result of socket.if_nametoindex()
        self.interface_index = address.addrTuple[-1]
        if _debug:
            IPv6DatagramServer._debug("    - interface_index: %r", self.interface_index)

        # create a local socket
        local_socket = socket.socket(family=socket.AF_INET6, type=socket.SOCK_DGRAM)
        if _debug:
            IPv6DatagramServer._debug("    - local_socket: %r", local_socket)

        # join the IANA assigned link-local multicast group
        # TODO allow multiple/configurable multicast groups
        for group in ["ff02::bac0"]:
            local_socket.setsockopt(
                socket.IPPROTO_IPV6,
                socket.IPV6_JOIN_GROUP,
                struct.pack(
                    "16sI",
                    socket.inet_pton(socket.AF_INET6, group),
                    self.interface_index,
                ),
            )
        local_socket.bind(address.addrTuple)

        # easy call to create a local endpoint
        local_endpoint_task = loop.create_task(
            loop.create_datagram_endpoint(
                IPv6DatagramProtocol,
                sock=local_socket,
            )
        )
        if _debug:
            IPv6DatagramServer._debug(
                "    - local_endpoint_task: %r", local_endpoint_task
            )
        local_endpoint_task.add_done_callback(
            functools.partial(self.set_local_transport_protocol, address)
        )

        # keep a list of things that need to complete before sending stuff
        self._transport_tasks = [local_endpoint_task]

    def set_local_transport_protocol(self, address, task):
        if _debug:
            IPv6DatagramServer._debug(
                "set_local_transport_protocol %r, %r", address, task
            )

        # get the results of creating the datagram endpoint
        transport, protocol = task.result()
        if _debug:
            IPv6DatagramServer._debug(
                "    - transport, protocol: %r, %r", transport, protocol
            )

        # make these the correct type
        self.transport = cast(asyncio.DatagramTransport, transport)
        self.protocol = cast(IPv6DatagramProtocol, protocol)

        # tell the protocol instance created that it should talk back to us
        self.protocol.server = self

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            IPv6DatagramServer._debug("indication %r", pdu)

        # wait for set_local_transport_protocol to have been called
        if self._transport_tasks:
            if _debug:
                IPv6DatagramServer._debug(
                    "    - waiting for tasks: %r", self._transport_tasks
                )
            await asyncio.gather(*self._transport_tasks)
            self._transport_tasks = []

        # downstream packets can have a specific or local broadcast address
        if isinstance(pdu.pduDestination, LocalBroadcast):
            pdu_destination = IPv6LinkLocalMulticastAddress(
                port=self.local_address[1], interface=self.interface_index
            ).addrTuple
        elif isinstance(pdu.pduDestination, IPv6Address):
            pdu_destination = pdu.pduDestination.addrTuple
        else:
            raise ValueError("invalid destination: {pdu.pduDestination}")
        if _debug:
            IPv6DatagramServer._debug("    - pdu_destination: %r", pdu_destination)

        # send it along
        self.transport.sendto(pdu.pduData, pdu_destination)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            IPv6DatagramServer._debug("confirmation %r", pdu)

        assert isinstance(pdu.pduSource, IPv6Address)
        if pdu.pduSource.addrTuple[:2] == self.local_address[:2]:
            if _debug:
                IPv6DatagramServer._debug("    - broadcast/reflected?")

        # up the stack it goes
        await self.response(pdu)

    def close(self) -> None:
        if _debug:
            IPv6DatagramServer._debug("close")

        # close the transport
        self.transport.close()
