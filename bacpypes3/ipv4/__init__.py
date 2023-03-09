"""
IPv4
"""

import os
import asyncio
import functools

from typing import Any, Callable, Optional, List, Tuple, Union, cast

from ..debugging import ModuleLogger, bacpypes_debugging

from ..comm import Server
from ..pdu import LocalBroadcast, IPv4Address, PDU


# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class IPv4DatagramProtocol(asyncio.DatagramProtocol):

    _debug: Callable[..., None]

    server: "IPv4DatagramServer"
    destination: Union[IPv4Address, LocalBroadcast, None]

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if _debug:
            IPv4DatagramProtocol._debug("connection_made %r", transport)

        # get the 'name' of the socket when it was bound which is useful
        # for ephemeral sockets used by applications running as a foreign device
        socket = transport.get_extra_info("socket")
        if _debug:
            IPv4DatagramProtocol._debug("    - socket: %r", socket)
        if socket is not None:
            socket_name = socket.getsockname()
            if _debug:
                IPv4DatagramProtocol._debug("    - socket_name: %r", socket_name)
            self.destination = IPv4Address(socket_name)
        else:
            self.destination = None

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        if _debug:
            IPv4DatagramProtocol._debug("datagram_received %r %r", data, addr)

        pdu = PDU(data, source=IPv4Address(addr), destination=self.destination)
        asyncio.ensure_future(self.server.confirmation(pdu))

    def error_received(self, exc: Exception) -> None:
        if _debug:
            IPv4DatagramProtocol._debug("error_received %r", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if _debug:
            IPv4DatagramProtocol._debug("connection_lost %r", exc)


@bacpypes_debugging
class IPv4DatagramServer(Server[PDU]):

    _debug: Callable[..., None]
    _exception: Callable[..., None]
    _transport_tasks: List[Any]

    local_address: Tuple[str, int]
    local_transport: asyncio.DatagramTransport
    local_protocol: IPv4DatagramProtocol
    broadcast_address: Optional[Tuple[str, int]]
    broadcast_transport: Optional[asyncio.DatagramTransport]
    broadcast_protocol: Optional[IPv4DatagramProtocol]

    def __init__(
        self,
        address: IPv4Address,
        no_broadcast: bool = False,
    ) -> None:
        if _debug:
            IPv4DatagramServer._debug(
                "__init__ %r no_broadcast=%r", address, no_broadcast
            )

        # grab the loop to create tasks and endpoints
        loop: asyncio.events.AbstractEventLoop = asyncio.get_running_loop()

        # save the address
        self.local_address = address.addrTuple
        if _debug:
            IPv4DatagramServer._debug("    - local_address: %r", self.local_address)

        # no broadcast if this is an ephemeral port
        if self.local_address[1] == 0:
            no_broadcast = True

        # easy call to create a local endpoint
        local_endpoint_task = loop.create_task(
            loop.create_datagram_endpoint(
                IPv4DatagramProtocol,
                local_addr=address.addrTuple,
                allow_broadcast=True,
            )
        )
        if _debug:
            IPv4DatagramServer._debug(
                "    - local_endpoint_task: %r", local_endpoint_task
            )
        local_endpoint_task.add_done_callback(
            functools.partial(self.set_local_transport_protocol, address)
        )

        # keep a list of things that need to complete before sending stuff
        self._transport_tasks = [local_endpoint_task]

        # see if we need a broadcast listener
        if no_broadcast or (address.addrBroadcastTuple == address.addrTuple):
            self.broadcast_address = None
            self.broadcast_transport = None
            self.broadcast_protocol = None
        else:
            self.broadcast_address = address.addrBroadcastTuple
            if _debug:
                IPv4DatagramServer._debug(
                    "    - broadcast_address: %r", self.broadcast_address
                )

            # Windows takes care of the broadcast, but Linux needs a broadcast endpoint
            if "nt" not in os.name:
                broadcast_endpoint_task = loop.create_task(
                    loop.create_datagram_endpoint(
                        IPv4DatagramProtocol,
                        local_addr=address.addrBroadcastTuple,
                        allow_broadcast=True,
                    )
                )
                if _debug:
                    IPv4DatagramServer._debug(
                        "    - broadcast_endpoint_task: %r", broadcast_endpoint_task
                    )
                broadcast_endpoint_task.add_done_callback(
                    functools.partial(self.set_broadcast_transport_protocol, address)
                )
                self._transport_tasks.append(broadcast_endpoint_task)

    def set_local_transport_protocol(self, address, task):
        if _debug:
            IPv4DatagramServer._debug(
                "set_local_transport_protocol %r, %r", address, task
            )

        # get the results of creating the datagram endpoint
        transport, protocol = task.result()
        if _debug:
            IPv4DatagramServer._debug(
                "    - transport, protocol: %r, %r", transport, protocol
            )

        # make these the correct type
        self.local_transport = cast(asyncio.DatagramTransport, transport)
        self.local_protocol = cast(IPv4DatagramProtocol, protocol)

        # tell the protocol instance created that it should talk back to us
        self.local_protocol.server = self
        # self.local_protocol.destination = address

        # Windows will use the same transport and protocol for broadcasts
        if "nt" in os.name:
            # make these the correct type
            self.broadcast_transport = cast(asyncio.DatagramTransport, transport)
            self.broadcast_protocol = cast(IPv4DatagramProtocol, protocol)

            # tell the protocol instance created that it should talk back to us
            self.broadcast_protocol.server = self
            self.broadcast_protocol.destination = LocalBroadcast()

    def set_broadcast_transport_protocol(self, address, task):
        if _debug:
            IPv4DatagramServer._debug(
                "set_broadcast_transport_protocol %r, %r", address, task
            )

        # get the results of creating the datagram endpoint
        transport, protocol = task.result()
        if _debug:
            IPv4DatagramServer._debug(
                "    - transport, protocol: %r, %r", transport, protocol
            )

        # make these the correct type
        self.broadcast_transport = cast(asyncio.DatagramTransport, transport)
        self.broadcast_protocol = cast(IPv4DatagramProtocol, protocol)

        # tell the protocol instance created that it should talk back to us
        self.broadcast_protocol.server = self

        # incoming packets on this transport were sent as a local broadcast
        self.broadcast_protocol.destination = LocalBroadcast()

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            IPv4DatagramServer._debug("indication %r", pdu)

        # wait for set_local_transport_protocol to have been called
        if self._transport_tasks:
            if _debug:
                IPv4DatagramServer._debug(
                    "    - waiting for tasks: %r", self._transport_tasks
                )
            await asyncio.gather(*self._transport_tasks)
            self._transport_tasks = []

        # downstream packets can have a specific or local broadcast address
        if isinstance(pdu.pduDestination, LocalBroadcast):
            if not self.broadcast_address:
                raise RuntimeError("no broadcast")
            pdu_destination = self.broadcast_address
        elif isinstance(pdu.pduDestination, IPv4Address):
            pdu_destination = pdu.pduDestination.addrTuple
        else:
            raise ValueError("invalid destination: {pdu.pduDestination}")
        if _debug:
            IPv4DatagramServer._debug("    - pdu_destination: %r", pdu_destination)

        # send it along
        self.local_transport.sendto(pdu.pduData, pdu_destination)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            IPv4DatagramServer._debug("confirmation %r", pdu)

        assert isinstance(pdu.pduSource, IPv4Address)
        if pdu.pduSource.addrTuple == self.local_address:
            if _debug:
                IPv4DatagramServer._debug("    - broadcast/reflected")
            return

        # up the stack it goes
        await self.response(pdu)

    def close(self) -> None:
        if _debug:
            IPv4DatagramServer._debug("close")

        # close the transport(s)
        self.local_transport.close()
        if self.broadcast_transport:
            self.broadcast_transport.close()
