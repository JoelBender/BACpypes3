#!/usr/bin/python

"""
Secure Connect
"""

import asyncio
from asyncio.tasks import Task
import traceback
import websockets

from typing import TYPE_CHECKING, Any, Callable, List, Optional, Set, Tuple, Union, cast

from ..debugging import ModuleLogger, bacpypes_debugging

from ..comm import Server, ServiceAccessPoint
from ..pdu import LocalBroadcast, IPv4Address, PDU


# some debugging
_debug = 0
_log = ModuleLogger(globals())


if TYPE_CHECKING:
    WebSocketQueue = asyncio.Queue[PDU]
else:
    WebSocketQueue = asyncio.Queue


@bacpypes_debugging
class WebSocketClient(Server[PDU]):
    """
    This generic WebSocket client attempts to establish and maintain a
    connection to a server.  It is subclassed for direct connect and hub
    connections.
    """

    _debug: Callable[..., None]
    _exception: Callable[..., None]

    uri: str
    kwargs: Any

    def __init__(self, switch: "SCNodeSwitch", uri: str, **kwargs: Any) -> None:
        if _debug:
            WebSocketClient._debug("__init__ %r %r %r", switch, uri, kwargs)

        self.switch = switch
        self.uri = uri
        self.kwargs = kwargs

        # EOF is set when processing is complete
        self.eof = asyncio.Event()

        # set the stop event to stop the task, wait for EOF to be done
        self.stop = asyncio.Event()
        self.stop.clear()

        # create a task for the connection
        # self.websocket_task = asyncio.create_task(self.websocket_loop())

        # create the task and save it so it can be canceled
        self.client_task = asyncio.ensure_future(self.websocket_loop())
        if _debug:
            SCNodeSwitch._debug("    - client_task: %r", self.client_task)

        # queue for outbound messages
        self.outgoing: WebSocketQueue = asyncio.Queue()

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            WebSocketClient._debug("indication %r", pdu)

        # transfer the PDU to the outgoing queue
        await self.outgoing.put(pdu.pduData)

    async def websocket_loop(self) -> None:
        """The websocket_loop runs as a task opening and maintaining a
        connection to the server.  It waits for incoming messages and sends
        them up the stack, for downstream messages and sends them to the server,
        or for the stop event to be set.
        """
        if _debug:
            WebSocketClient._debug("websocket_loop")

        # loop around making new connections if necessary
        while True:
            try:
                if _debug:
                    WebSocketClient._debug("    - connection attempt")

                async with websockets.connect(self.uri, **self.kwargs) as websocket:
                    if _debug:
                        WebSocketClient._debug("    - connected: %r", websocket)

                    # loop around sending and receiving PDUs (bytes)
                    while True:
                        incoming: asyncio.Future = asyncio.ensure_future(
                            websocket.recv()
                        )
                        outgoing: asyncio.Future = asyncio.ensure_future(
                            self.outgoing.get()
                        )

                        if _debug:
                            WebSocketClient._debug("    - waiting")
                        done, pending = await asyncio.wait(
                            [incoming, outgoing, self.stop.wait()],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        # cancel pending tasks to avoid leaking them
                        for task in pending:
                            task.cancel()

                        # send incoming messages up the stack
                        if incoming in done:
                            try:
                                pdu = incoming.result()
                                if _debug:
                                    WebSocketClient._debug("    - incoming: %r", pdu)
                            except websockets.ConnectionClosedOK:
                                if _debug:
                                    WebSocketClient._debug("    - connection closed")
                                break
                            else:
                                await self.switch.confirmation(PDU(pdu, source=self))

                        # send downsteam messages to the server, None means stop
                        if outgoing in done:
                            try:
                                pdu = outgoing.result()
                                if _debug:
                                    WebSocketClient._debug("    - outgoing: %r", pdu)
                                if pdu is None:
                                    self.stop.set()
                                else:
                                    await websocket.send(pdu)
                            except websockets.ConnectionClosedOK:
                                if _debug:
                                    WebSocketClient._debug("    - connection closed")
                                break

                        if self.stop.is_set():
                            if _debug:
                                WebSocketClient._debug("    - stopping")
                            break

            except asyncio.CancelledError:
                _log.warning("websocket_loop canceled")
                break
            except websockets.exceptions.ConnectionClosedOK:
                if _debug:
                    WebSocketClient._debug("    - connection closed")
                _log.warning("websocket_loop connection closed")
            except ConnectionRefusedError:
                _log.warning("websocket_loop connection refused")
                if None in self.outgoing._queue:  # type: ignore[attr-defined]
                    self.stop.set()
                else:
                    await asyncio.sleep(5.0)
            # except Exception as err:
            #     _log.warning("websocket_loop exception: {!r}".format(err))
            #     for filename, lineno, fn, _ in traceback.extract_stack()[:-1]:
            #         _log.warning("    %-20s  %s:%s", fn, filename.split('/')[-1], lineno)

            # if an EOF was received, do not try to reconnect
            if self.stop.is_set():
                break

        # we're all done
        self.eof.set()

    async def close(self):
        if _debug:
            WebSocketClient._debug("close")

        # tell the loop to stop, the connection is closed when the websocket
        # context exits
        self.stop.set()
        if _debug:
            WebSocketClient._debug("    - stop is set")

        # wait for the end-of-file event
        await self.eof.wait()
        if _debug:
            WebSocketClient._debug("   - eof: %r", self.eof)


@bacpypes_debugging
class SCDirectConnectClient(WebSocketClient):
    """
    This is the initiating side of a direct connection.
    """

    _debug: Callable[..., None]
    _exception: Callable[..., None]

    def __init__(self, switch: "SCNodeSwitch", uri: str, **kwargs: Any) -> None:
        if _debug:
            SCDirectConnectClient._debug("__init__")
        WebSocketClient.__init__(
            self,
            switch,
            uri,
            subprotocols=[websockets.Subprotocol("dc.bsc.bacnet.org")],
            **kwargs
        )


@bacpypes_debugging
class SCHubClient(WebSocketClient):
    """
    This is the initiating side of a hub connection.
    """

    _debug: Callable[..., None]
    _exception: Callable[..., None]

    def __init__(self, switch: "SCNodeSwitch", uri: str, **kwargs: Any) -> None:
        if _debug:
            SCHubClient._debug("__init__")
        WebSocketClient.__init__(
            self,
            switch,
            uri,
            subprotocols=[websockets.Subprotocol("hub.bsc.bacnet.org")],
            **kwargs
        )


@bacpypes_debugging
class WebSocketServer:

    _debug: Callable[..., None]
    _exception: Callable[..., None]

    def __init__(self, switch: "SCNodeSwitch", websocket, path) -> None:
        if _debug:
            WebSocketServer._debug("__init__ %r %r %r", switch, websocket, path)

        self.switch = switch
        self.websocket = websocket
        self.path = path

        # EOF is set when processing is complete
        self.eof = asyncio.Event()

        # set the stop event to stop the task, wait for EOF to be done
        self.stop = asyncio.Event()
        self.stop.clear()
        self.websocket_task = asyncio.create_task(self.websocket_loop())

        self.outgoing: WebSocketQueue = asyncio.Queue()

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            WebSocketServer._debug("indication %r", pdu)

        # transfer the PDU to the outgoing queue
        await self.outgoing.put(pdu.pduData)

    async def websocket_loop(self) -> None:
        """The websocket_loop runs as a task opening and maintaining a
        connection to the server.  It waits for incoming messages and sends
        them up the stack, for downstream messages and sends them to the server,
        or for the stop event to be set.
        """
        if _debug:
            WebSocketServer._debug("websocket_loop")

        # loop around sending and receiving PDUs (bytes)
        while True:
            try:
                incoming: asyncio.Future = asyncio.ensure_future(self.websocket.recv())
                outgoing: asyncio.Future = asyncio.ensure_future(self.outgoing.get())
                done, pending = await asyncio.wait(
                    [incoming, outgoing, self.stop.wait()],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # cancel pending tasks to avoid leaking them
                for task in pending:
                    task.cancel()

                # send incoming messages up the stack
                if incoming in done:
                    try:
                        pdu = incoming.result()
                        if _debug:
                            WebSocketServer._debug("    - incoming: %r", pdu)

                        await self.switch.confirmation(PDU(pdu, source=self))
                    except websockets.ConnectionClosedOK:
                        if _debug:
                            WebSocketServer._debug("    - connection closed")
                        break

                # send downsteam messages to the server, None means stop
                if outgoing in done:
                    try:
                        pdu = outgoing.result()
                        if _debug:
                            WebSocketServer._debug("    - outgoing: %r", pdu)
                        if pdu is None:
                            self.stop.set()
                        else:
                            await self.websocket.send(pdu)
                    except websockets.ConnectionClosedOK:
                        if _debug:
                            WebSocketServer._debug("    - connection closed")
                        break

                if self.stop.is_set():
                    if _debug:
                        WebSocketServer._debug("    - stopping")
                    break

            except asyncio.CancelledError:
                WebSocketServer._exception("websocket_loop canceled")
                break
            except websockets.exceptions.ConnectionClosedOK:
                if _debug:
                    WebSocketServer._debug("    - connection closed")
                WebSocketServer._exception("websocket_loop connection closed")
                break
            # except Exception as err:
            #     _log.warning("websocket_loop exception: {!r}".format(err))
            #     for filename, lineno, fn, _ in traceback.extract_stack()[:-1]:
            #         _log.warning("    %-20s  %s:%s", fn, filename.split('/')[-1], lineno)

            # if an EOF was received, do not try to reconnect
            if self.stop.is_set():
                break

        # normal close
        await self.websocket.close()
        if _debug:
            WebSocketServer._debug("    - loop finished")

        # we're all done
        self.eof.set()

    async def close(self):
        if _debug:
            WebSocketServer._debug("close")

        self.stop.set()
        if _debug:
            WebSocketServer._debug("    - stop is set")

        await self.eof.wait()
        if _debug:
            WebSocketServer._debug("   - eof: %r", self.eof)


@bacpypes_debugging
class SCDirectConnectServer(WebSocketServer):
    """
    This is the listening side of a direct connection for a specific client.
    """

    pass


@bacpypes_debugging
class SCHubServer(WebSocketServer):
    """
    This is the listening side of a hub connection for a specific client.
    """

    pass


@bacpypes_debugging
class SCServiceAccessPoint(ServiceAccessPoint):
    """
    This Service Access Point interface is shared with both the direct connect
    and hub service access points and provides the registration list for the
    connect peers and hub clients.
    """

    _debug: Callable[..., None]
    connected_servers: Set[WebSocketServer]

    def __init__(self) -> None:
        if _debug:
            SCServiceAccessPoint._debug("__init__")
        super().__init__()

        # no connected servers
        self.connected_servers = set()

    async def register(self, server: WebSocketServer) -> None:
        if _debug:
            SCServiceAccessPoint._debug("register %r", server)

        # add it to the set of connected servers
        self.connected_servers.add(server)

    async def unregister(self, server: WebSocketServer) -> None:
        if _debug:
            SCServiceAccessPoint._debug("unregister %r", server)

        # remove it from the set of connected servers
        self.connected_servers.remove(server)


@bacpypes_debugging
class SCDirectConnectServiceAccessPoint(SCServiceAccessPoint):
    pass


@bacpypes_debugging
class SCHubServiceAccessPoint(SCServiceAccessPoint):
    pass


@bacpypes_debugging
class SCNodeSwitch(Server[PDU]):

    _debug: Callable[..., None]
    _exception: Callable[..., None]

    host: str
    port: int
    server_task: Optional[asyncio.Future]

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        dc_support: bool = False,
        hub_support: bool = False,
    ) -> None:
        if _debug:
            SCNodeSwitch._debug("__init__")
        super().__init__()

        self.host = host
        self.port = port

        # create the service access points
        self.dc_sap = SCDirectConnectServiceAccessPoint()
        self.hub_sap = SCHubServiceAccessPoint()

        subprotocols: List[websockets.Subprotocol] = []
        if dc_support:  # will this support incoming direct connections
            subprotocols.append(websockets.Subprotocol("dc.bsc.bacnet.org"))
        if hub_support:  # will this support incoming hub connections
            subprotocols.append(websockets.Subprotocol("hub.bsc.bacnet.org"))

        if not subprotocols:
            self.server_task = None
        else:
            # this function will be turned into a task
            start_server = websockets.serve(
                self.dispatcher,
                host,
                port,
                subprotocols=subprotocols,
            )
            if _debug:
                SCNodeSwitch._debug("    - start_server: %r", start_server)

            # create the task and save it so it can be canceled
            self.server_task = asyncio.ensure_future(start_server)
            if _debug:
                SCNodeSwitch._debug("    - server_task: %r", self.server_task)

    async def dispatcher(self, websocket, path) -> None:
        if _debug:
            SCNodeSwitch._debug(
                "dispatcher %r %r %r", websocket, websocket.subprotocol, path
            )

        client_sap: SCServiceAccessPoint
        client_server: WebSocketServer

        if websocket.subprotocol == "dc.bsc.bacnet.org":
            client_sap = self.dc_sap
            client_server = SCDirectConnectServer(self, websocket, path)

        elif websocket.subprotocol == "hub.bsc.bacnet.org":
            client_sap = self.hub_sap
            client_server = SCHubServer(self, websocket, path)

        else:
            await websocket.close(code=1002)
            return

        # register the server to its service access point
        await client_sap.register(client_server)

        # wait for the server to do its thing
        await client_server.eof.wait()

        # unregister the server from its service access point
        await client_sap.unregister(client_server)

    async def indication(self, pdu: PDU) -> None:
        """
        Downstream messages from the network layer.
        """
        if _debug:
            SCNodeSwitch._debug("indication %r", pdu)
        assert isinstance(pdu.pduDestination, (WebSocketClient, WebSocketServer))

        # transfer the PDU to the client/server
        await pdu.pduDestination.indication(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        """
        Upstream messages from one of the clients or servers.
        """
        if _debug:
            SCNodeSwitch._debug("confirmation %r", pdu)

        # send the message upstream
        await self.response(pdu)

    def connect_to_device(self, uri: str) -> SCDirectConnectClient:
        """
        Initiate a connection to another device.
        """
        return SCDirectConnectClient(self, uri)

    def connect_to_hub(self, uri: str) -> SCHubClient:
        """
        Initiate a connection to a hub.
        """
        return SCHubClient(self, uri)

    async def close(self) -> None:
        """
        This should shutdown all of the clients and servers.
        """
        if _debug:
            SCNodeSwitch._debug("close")

        # cancel the server task
        if self.server_task:
            self.server_task.cancel()
