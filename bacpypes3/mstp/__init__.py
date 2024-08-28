"""
MSTP via Misty
"""

import asyncio

from typing import Any, Callable, Optional, List, cast

from ..debugging import ModuleLogger, bacpypes_debugging

from ..comm import Server
from ..pdu import MSTPAddress, PDU


# some debugging
_debug = 0
_log = ModuleLogger(globals())

# move this to settings sometime
BACPYPES_ENDPOINT_RETRY_INTERVAL = 1.0


@bacpypes_debugging
class MSTPDatagramProtocol(asyncio.DatagramProtocol):
    _debug: Callable[..., None]

    server: "MSTPLinkLayer"
    transport: asyncio.BaseTransport

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        if _debug:
            MSTPDatagramProtocol._debug("connection_made %r", transport)
        self.transport = transport

    def data_received(self, data: bytes) -> None:
        if _debug:
            MSTPDatagramProtocol._debug("data_received %r", data)

        pdu = PDU(data[1:], source=MSTPAddress(data[:1]))
        asyncio.ensure_future(self.server.confirmation(pdu))

    def error_received(self, exc: Exception) -> None:
        if _debug:
            MSTPDatagramProtocol._debug("error_received %r", exc)

    def eof_received(self) -> None:
        if _debug:
            MSTPDatagramProtocol._debug("eof_received")

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if _debug:
            MSTPDatagramProtocol._debug("connection_lost %r", exc)
        self.transport = None


@bacpypes_debugging
class MSTPLinkLayer(Server[PDU]):
    _debug: Callable[..., None]
    _exception: Callable[..., None]
    _transport_tasks: List[Any]

    path: str
    local_transport: Optional[asyncio.DatagramTransport]
    local_protocol: Optional[MSTPDatagramProtocol]

    def __init__(
        self,
        path: str,
    ) -> None:
        if _debug:
            MSTPLinkLayer._debug(
                "__init__ %r",
                path,
            )

        # grab the loop to create tasks and endpoints
        loop: asyncio.events.AbstractEventLoop = asyncio.get_running_loop()

        # save the path
        self.path = path
        if _debug:
            MSTPLinkLayer._debug("    - path: %r", self.path)

        # initialized in set_local_transport_protocol callback
        self.local_transport = None
        self.local_protocol = None

        # easy call to create a local endpoint
        local_endpoint_task = loop.create_task(
            self.retrying_create_unix_connection(loop, path)
        )
        if _debug:
            MSTPLinkLayer._debug("    - local_endpoint_task: %r", local_endpoint_task)
        local_endpoint_task.add_done_callback(self.set_local_transport_protocol)

        # keep a list of things that need to complete before sending stuff
        self._transport_tasks = [local_endpoint_task]

    async def retrying_create_unix_connection(
        self, loop: asyncio.events.AbstractEventLoop, path: str
    ):
        """
        Repeat attempts to create a unix connection, sometimes during boot
        the agent isn't ready.
        """
        while True:
            try:
                return await loop.create_unix_connection(
                    lambda: MSTPDatagramProtocol(), path=path
                )
            except OSError:
                if _debug:
                    MSTPLinkLayer._debug(
                        "    - Could not create datagram endpoint, retrying..."
                    )
                await asyncio.sleep(BACPYPES_ENDPOINT_RETRY_INTERVAL)

    def set_local_transport_protocol(self, task):
        if _debug:
            MSTPLinkLayer._debug("set_local_transport_protocol %r", task)

        # get the results of creating the datagram endpoint
        transport, protocol = task.result()
        if _debug:
            MSTPLinkLayer._debug(
                "    - transport, protocol: %r, %r", transport, protocol
            )

        # make these the correct type
        self.local_transport = cast(asyncio.DatagramTransport, transport)
        self.local_protocol = cast(MSTPDatagramProtocol, protocol)

        # link together
        self.local_protocol.server = self

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            MSTPLinkLayer._debug("indication %r", pdu)

        # wait for set_local_transport_protocol to have been called
        if self._transport_tasks:
            if _debug:
                MSTPLinkLayer._debug(
                    "    - waiting for tasks: %r", self._transport_tasks
                )
            await asyncio.gather(*self._transport_tasks)
            self._transport_tasks = []

        # downstream packets can have a specific or local broadcast address
        if pdu.pduDestination.is_localstation:
            pdu_destination = pdu.pduDestination.addrAddr
        elif pdu.pduDestination.is_localbroadcast:
            pdu_destination = b"\xFF"
        else:
            raise ValueError(f"invalid destination: {pdu.pduDestination}")
        if _debug:
            MSTPLinkLayer._debug("    - pdu_destination: %r", pdu_destination)

        # send it along
        self.local_transport.write(pdu_destination + pdu.pduData)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            MSTPLinkLayer._debug("confirmation %r", pdu)

        # up the stack it goes
        await self.response(pdu)

    def close(self) -> None:
        if _debug:
            MSTPLinkLayer._debug("close")

        # close the transport(s)
        if self.local_transport:
            self.local_transport.close()
