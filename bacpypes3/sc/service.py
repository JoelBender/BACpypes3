#!/usr/bin/python

"""
Secure Connect
"""

import asyncio
from asyncio.tasks import Task
import enum
import traceback
import uuid
import websockets

from typing import TYPE_CHECKING, Any, Callable, List, Optional, Set, Tuple, Union, cast

from ..debugging import ModuleLogger, bacpypes_debugging

from ..comm import Client, Server, ServiceAccessPoint
from ..pdu import (
    Address,
    LocalBroadcast,
    IPv4Address,
    PDU,
    SecureConnectAddress,
    VirtualAddress,
)
from ..basetypes import ErrorClass, ErrorCode

from .bvll import (
    LPCI,
    LPDU,
    pdu_types,
    ConnectRequest,
    ConnectAccept,
    DisconnectRequest,
    DisconnectACK,
    HeartbeatRequest,
    HeartbeatACK,
    Result,
    EncapsulatedNPDU,
)
from .tls import require_wss


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
            **kwargs,
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
            **kwargs,
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


@bacpypes_debugging
class SCBVLLServiceAccessPoint(Client[LPDU], Server[PDU], ServiceAccessPoint):
    """
    BACnet/SC Virtual Link Layer entity (BVLL entity, see Annex AB / Clause
    YY.1.1.1).

    This is the SC equivalent of the IPv4 BIPNormal service access point.  It
    is stacked on a BVLLCodec: as a server (top) it exchanges NPDUs with the
    network layer using BACnet addresses; as a client (bottom) it exchanges
    LPDUs with the codec, wrapping outgoing NPDUs in Encapsulated-NPDU BVLC
    messages and mapping BACnet addresses to 6-octet VMAC addresses.

    The node is identified in the BACnet/SC network by its VMAC.  Control BVLC
    messages (Connect, Heartbeat, ...) are handled below the codec by the hub
    connector and do not reach this layer.
    """

    _debug: Callable[..., None]
    _warning: Callable[..., None]

    local_vmac: SecureConnectAddress

    def __init__(
        self,
        local_vmac: SecureConnectAddress,
        *,
        sapID: Optional[str] = None,
        cid: Optional[str] = None,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            SCBVLLServiceAccessPoint._debug("__init__ %r", local_vmac)
        Client.__init__(self, cid=cid)
        Server.__init__(self, sid=sid)
        ServiceAccessPoint.__init__(self, sapID=sapID)

        self.local_vmac = local_vmac
        self._message_id = 0

    def _next_message_id(self) -> int:
        message_id = self._message_id
        self._message_id = (self._message_id + 1) & 0xFFFF
        return message_id

    async def indication(self, pdu: PDU) -> None:
        """Downstream from the network layer: wrap the NPDU in an
        Encapsulated-NPDU BVLC message addressed by VMAC."""
        if _debug:
            SCBVLLServiceAccessPoint._debug("indication %r", pdu)

        destination = pdu.pduDestination

        # determine the destination VMAC
        if destination is None or destination.addrType == Address.localBroadcastAddr:
            dest_vmac = SecureConnectAddress(SecureConnectAddress.local_broadcast)
        elif destination.addrType == Address.localStationAddr:
            if not destination.addrAddr or len(destination.addrAddr) != 6:
                SCBVLLServiceAccessPoint._warning(
                    "invalid VMAC address: %r", destination
                )
                return
            dest_vmac = SecureConnectAddress(destination.addrAddr)
        else:
            SCBVLLServiceAccessPoint._warning(
                "invalid destination address: %r", destination
            )
            return

        # wrap the NPDU
        lpdu = EncapsulatedNPDU(pdu.pduData)
        lpdu.bvlcMessageID = self._next_message_id()
        lpdu.bvlcDestinationVirtualAddress = dest_vmac
        # the node is the originator, so the originating VMAC is absent; the
        # hub function inserts it when forwarding (Clause YY.5.4)
        lpdu.bvlcOriginatingVirtualAddress = None
        lpdu.pduUserData = pdu.pduUserData
        if _debug:
            SCBVLLServiceAccessPoint._debug("    - lpdu: %r", lpdu)

        # send it downstream
        await self.request(lpdu)

    async def confirmation(self, lpdu: LPDU) -> None:
        """Upstream from the codec: unwrap Encapsulated-NPDU BVLC messages and
        present the NPDU to the network layer."""
        if _debug:
            SCBVLLServiceAccessPoint._debug("confirmation %r", lpdu)

        # only NPDU-bearing messages are presented to the network layer; any
        # control message reaching this layer is unexpected and ignored
        if not isinstance(lpdu, EncapsulatedNPDU):
            if _debug:
                SCBVLLServiceAccessPoint._debug("    - not an NPDU, ignored")
            return

        # the source is the originating VMAC (inserted by the hub) or, absent
        # that, the connection peer as tagged by the transport
        origin = lpdu.bvlcOriginatingVirtualAddress
        if origin is not None:
            source: Optional[Address] = SecureConnectAddress(origin.addrAddr)
        else:
            source = lpdu.pduSource

        # a broadcast destination maps to a local broadcast, otherwise the
        # message was addressed to this node
        dest_vmac = lpdu.bvlcDestinationVirtualAddress
        destination: Optional[Address]
        if (
            dest_vmac is not None
            and dest_vmac.addrAddr == SecureConnectAddress.local_broadcast
        ):
            destination = LocalBroadcast()
        else:
            destination = self.local_vmac

        pdu = PDU(
            lpdu.pduData,
            source=source,
            destination=destination,
            user_data=lpdu.pduUserData,
        )
        if _debug:
            SCBVLLServiceAccessPoint._debug("    - pdu: %r", pdu)

        # send it upstream
        await self.response(pdu)

    async def sap_indication(self, lpdu: LPDU) -> None:
        if _debug:
            SCBVLLServiceAccessPoint._debug("sap_indication %r", lpdu)

        # a request initiated by an application service element, send downstream
        await self.request(lpdu)

    async def sap_confirmation(self, lpdu: LPDU) -> None:
        if _debug:
            SCBVLLServiceAccessPoint._debug("sap_confirmation %r", lpdu)

        # a response from an application service element, send downstream
        await self.request(lpdu)


class HubConnectorState(enum.Enum):
    IDLE = "idle"
    AWAITING_WEBSOCKET = "awaiting-websocket"
    AWAITING_ACCEPT = "awaiting-accept"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"


# WebSocket subprotocol names, see Clause YY.7.1
HUB_SUBPROTOCOL = "hub.bsc.bacnet.org"
DIRECT_CONNECT_SUBPROTOCOL = "dc.bsc.bacnet.org"

# hub connector states, matching the BACnetSCHubConnectorState enumeration
HUB_CONNECTOR_NO_CONNECTION = 0
HUB_CONNECTOR_CONNECTED_PRIMARY = 1
HUB_CONNECTOR_CONNECTED_FAILOVER = 2


@bacpypes_debugging
class SCHubConnector(Server[PDU]):
    """
    BACnet/SC hub connector (see Annex AB / Clause YY.1.1.2 and YY.5).

    Maintains a single hub connection at a time, preferring the primary hub
    and falling back to the failover hub.  Runs the initiating-peer BACnet/SC
    connection state machine (Clause YY.6.2.2), keeps the connection alive with
    heartbeats (Clause YY.6.3), and forwards Encapsulated-NPDU BVLC messages
    to and from the codec above it.  Control BVLC messages are consumed here
    and are not passed up the stack.

    This class deals in encoded BVLC bytes.  The real WebSocket transport is
    provided by ``_connect``; the state machine is driven by the ``_fsm_*``
    handlers which can be exercised directly in tests without a live socket.
    """

    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _exception: Callable[..., None]

    def __init__(
        self,
        vmac: SecureConnectAddress,
        device_uuid: uuid.UUID,
        primary_hub_uri: str,
        failover_hub_uri: Optional[str] = None,
        *,
        ssl_context: Any = None,
        maximum_bvlc_length: int = 1497,
        maximum_npdu_length: int = 1476,
        connect_wait_timeout: float = 10.0,
        heartbeat_timeout: float = 30.0,
        disconnect_wait_timeout: float = 10.0,
        minimum_reconnect_time: float = 10.0,
        maximum_reconnect_time: float = 600.0,
        on_vmac_change: Optional[Callable[[SecureConnectAddress], None]] = None,
        on_connector_state_change: Optional[Callable[[int], None]] = None,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            SCHubConnector._debug(
                "__init__ %r %r %r", vmac, primary_hub_uri, failover_hub_uri
            )
        Server.__init__(self, sid)

        self.vmac = vmac
        self.device_uuid = device_uuid
        self.on_vmac_change = on_vmac_change
        self.on_connector_state_change = on_connector_state_change

        # hub URIs, primary first
        self._uris = [primary_hub_uri]
        if failover_hub_uri:
            self._uris.append(failover_hub_uri)
        self._uri_index = 0

        self.ssl_context = ssl_context
        self.maximum_bvlc_length = maximum_bvlc_length
        self.maximum_npdu_length = maximum_npdu_length
        self.connect_wait_timeout = connect_wait_timeout
        self.heartbeat_timeout = heartbeat_timeout
        self.disconnect_wait_timeout = disconnect_wait_timeout
        self.minimum_reconnect_time = minimum_reconnect_time
        self.maximum_reconnect_time = maximum_reconnect_time

        # connection state
        self._state = HubConnectorState.IDLE
        self._connector_state_code = HUB_CONNECTOR_NO_CONNECTION
        self._conn: Any = None
        self._message_id = 0
        self._timers: Dict[str, Task] = {}

        # information learned from the hub in the Connect-Accept
        self.peer_vmac: Optional[SecureConnectAddress] = None
        self.peer_uuid: Optional[uuid.UUID] = None

        # set while a hub connection is fully established
        self.connected = asyncio.Event()

        # lifecycle
        self._closing = False
        self._run_task: Optional[Task] = None

    #
    #   message id and encoding helpers
    #

    def _next_message_id(self) -> int:
        message_id = self._message_id
        self._message_id = (self._message_id + 1) & 0xFFFF
        return message_id

    async def _send(self, lpdu: LPDU) -> None:
        """Encode and send a BVLC message on the active connection."""
        conn = self._conn
        if conn is None:
            if _debug:
                SCHubConnector._debug("    - no connection, dropping %r", lpdu)
            return
        data = lpdu.encode().pduData
        await conn.send(bytes(data))

    @staticmethod
    def _decode(data: bytes) -> LPDU:
        pdu = PDU(data)
        lpci = LPCI.decode(pdu)
        lpdu = pdu_types[lpci.bvlcFunction].decode(pdu)
        LPCI.update(lpdu, lpci)
        return lpdu

    #
    #   timers
    #

    def _start_timer(self, name: str, delay: float, callback: Callable) -> None:
        self._cancel_timer(name)

        async def _timer() -> None:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            await callback()

        self._timers[name] = asyncio.ensure_future(_timer())

    def _cancel_timer(self, name: str) -> None:
        task = self._timers.pop(name, None)
        if task is not None:
            task.cancel()

    def _cancel_all_timers(self) -> None:
        for name in list(self._timers):
            self._cancel_timer(name)

    #
    #   downstream (from the codec / SAP)
    #

    async def indication(self, pdu: PDU) -> None:
        """A BVLC message (Encapsulated-NPDU) from the SAP, send it to the
        hub if the connection is established."""
        if _debug:
            SCHubConnector._debug("indication %r", pdu)

        if self._state != HubConnectorState.CONNECTED:
            if _debug:
                SCHubConnector._debug("    - not connected, dropping")
            return

        conn = self._conn
        if conn is not None:
            await conn.send(bytes(pdu.pduData))

    #
    #   connection state machine (Clause YY.6.2.2, initiating peer)
    #

    async def _fsm_ws_established(self) -> None:
        """A WebSocket connection was established: send a Connect-Request and
        wait for the Connect-Accept."""
        if _debug:
            SCHubConnector._debug("_fsm_ws_established")

        request = ConnectRequest(
            vmac_address=VirtualAddress(self.vmac.addrAddr),
            device_uuid=self.device_uuid,
            maximum_bvlc_length=self.maximum_bvlc_length,
            maximum_npdu_length=self.maximum_npdu_length,
        )
        request.bvlcMessageID = self._next_message_id()
        await self._send(request)

        self._state = HubConnectorState.AWAITING_ACCEPT
        self._start_timer(
            "connect_wait", self.connect_wait_timeout, self._fsm_connect_wait_timeout
        )

    async def _fsm_connect_wait_timeout(self) -> None:
        if _debug:
            SCHubConnector._debug("_fsm_connect_wait_timeout")
        await self._close_connection()

    async def _fsm_message(self, data: bytes) -> None:
        """A BVLC message was received from the hub."""
        if not data:
            return

        # any received message counts as connection liveness
        self._restart_heartbeat()

        function = data[0]

        # NPDU-bearing messages go straight up to the codec/SAP
        if function == LPCI.encapsulatedNPDU:
            await self.response(PDU(bytes(data)))
            return

        try:
            lpdu = self._decode(data)
        except Exception as err:
            SCHubConnector._warning("failed to decode BVLC message: %r", err)
            return
        if _debug:
            SCHubConnector._debug("_fsm_message %r", lpdu)

        if isinstance(lpdu, ConnectAccept):
            await self._handle_connect_accept(lpdu)
        elif isinstance(lpdu, Result):
            await self._handle_result(lpdu)
        elif isinstance(lpdu, HeartbeatRequest):
            await self._handle_heartbeat_request(lpdu)
        elif isinstance(lpdu, HeartbeatACK):
            pass  # liveness already recorded
        elif isinstance(lpdu, DisconnectRequest):
            await self._handle_disconnect_request(lpdu)
        elif isinstance(lpdu, DisconnectACK):
            await self._handle_disconnect_ack(lpdu)
        else:
            if _debug:
                SCHubConnector._debug("    - unhandled: %r", lpdu)

    async def _handle_connect_accept(self, lpdu: ConnectAccept) -> None:
        if self._state != HubConnectorState.AWAITING_ACCEPT:
            return
        if _debug:
            SCHubConnector._debug("_handle_connect_accept %r", lpdu)

        self._cancel_timer("connect_wait")

        # remember the hub's identity (informational, Clause YY.6)
        self.peer_vmac = SecureConnectAddress(lpdu.vmac_address.addrAddr)
        self.peer_uuid = lpdu.device_uuid

        self._state = HubConnectorState.CONNECTED
        self.connected.set()
        self._restart_heartbeat()

        # report whether we are on the primary or failover hub
        self._set_connector_state(
            HUB_CONNECTOR_CONNECTED_PRIMARY
            if self._uri_index == 0
            else HUB_CONNECTOR_CONNECTED_FAILOVER
        )

    async def _handle_result(self, lpdu: Result) -> None:
        if _debug:
            SCHubConnector._debug("_handle_result %r", lpdu)

        if lpdu.result_code == 0x00:
            return

        # a duplicate VMAC was detected: choose a new Random-48 VMAC and
        # reconnect (Clause YY.6.2.2)
        if lpdu.error_code == ErrorCode.nodeDuplicateVmac:
            self.vmac = SecureConnectAddress.random()
            SCHubConnector._warning("duplicate VMAC, regenerated %r", self.vmac)
            if self.on_vmac_change is not None:
                self.on_vmac_change(self.vmac)

        await self._close_connection()

    async def _handle_heartbeat_request(self, lpdu: HeartbeatRequest) -> None:
        # the node is the initiating peer and normally sends heartbeats, but
        # respond to a request defensively
        ack = HeartbeatACK()
        ack.bvlcMessageID = lpdu.bvlcMessageID
        await self._send(ack)

    async def _handle_disconnect_request(self, lpdu: DisconnectRequest) -> None:
        if _debug:
            SCHubConnector._debug("_handle_disconnect_request")
        ack = DisconnectACK()
        ack.bvlcMessageID = lpdu.bvlcMessageID
        await self._send(ack)
        await self._close_connection()

    async def _handle_disconnect_ack(self, lpdu: DisconnectACK) -> None:
        if self._state == HubConnectorState.DISCONNECTING:
            await self._close_connection()

    #
    #   heartbeats (Clause YY.6.3)
    #

    def _restart_heartbeat(self) -> None:
        if self._state != HubConnectorState.CONNECTED:
            return
        self._start_timer("heartbeat", self.heartbeat_timeout, self._fsm_heartbeat)

    async def _fsm_heartbeat(self) -> None:
        if self._state != HubConnectorState.CONNECTED:
            return
        if _debug:
            SCHubConnector._debug("_fsm_heartbeat")
        request = HeartbeatRequest()
        request.bvlcMessageID = self._next_message_id()
        await self._send(request)
        self._start_timer("heartbeat", self.heartbeat_timeout, self._fsm_heartbeat)

    #
    #   connection teardown
    #

    def _set_connector_state(self, code: int) -> None:
        """Report the hub connector state (BACnetSCHubConnectorState) to an
        observer, e.g. the Network Port object, when it changes."""
        if code == self._connector_state_code:
            return
        self._connector_state_code = code
        if self.on_connector_state_change is not None:
            try:
                self.on_connector_state_change(code)
            except Exception as err:
                SCHubConnector._warning("connector state callback failed: %r", err)

    async def _close_connection(self) -> None:
        """Close the active WebSocket connection (if any) and return to IDLE."""
        if _debug:
            SCHubConnector._debug("_close_connection")

        self._cancel_all_timers()
        self._state = HubConnectorState.IDLE
        self.connected.clear()
        self.peer_vmac = None
        self.peer_uuid = None
        self._set_connector_state(HUB_CONNECTOR_NO_CONNECTION)

        conn = self._conn
        self._conn = None
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

    #
    #   WebSocket transport
    #

    async def _connect(self, uri: str) -> Any:
        """Open a secure WebSocket connection to the hub.  Overridable for
        testing."""
        if _debug:
            SCHubConnector._debug("_connect %r", uri)

        # BACnet/SC only permits TLS-secured connections
        require_wss(uri)

        return await websockets.connect(
            uri,
            subprotocols=[websockets.Subprotocol(HUB_SUBPROTOCOL)],
            ssl=self.ssl_context,
        )

    def _current_uri(self) -> str:
        return self._uris[self._uri_index % len(self._uris)]

    def _advance_uri(self) -> None:
        self._uri_index = (self._uri_index + 1) % len(self._uris)

    def start(self) -> None:
        """Start maintaining the hub connection."""
        if _debug:
            SCHubConnector._debug("start")
        if self._run_task is None:
            self._closing = False
            self._run_task = asyncio.ensure_future(self._run())

    async def _run(self) -> None:
        backoff = self.minimum_reconnect_time
        while not self._closing:
            uri = self._current_uri()
            self._state = HubConnectorState.AWAITING_WEBSOCKET
            try:
                conn = await self._connect(uri)
            except Exception as err:
                SCHubConnector._warning("connect to %s failed: %r", uri, err)
                self._state = HubConnectorState.IDLE
                self._advance_uri()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.maximum_reconnect_time)
                continue

            self._conn = conn
            backoff = self.minimum_reconnect_time
            try:
                await self._fsm_ws_established()
                async for message in conn:
                    if isinstance(message, str):
                        message = message.encode()
                    await self._fsm_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if _debug:
                    SCHubConnector._debug("    - connection ended: %r", err)
            finally:
                await self._close_connection()

            if not self._closing:
                await asyncio.sleep(backoff)

    async def close(self) -> None:
        """Gracefully disconnect and stop maintaining the connection."""
        if _debug:
            SCHubConnector._debug("close")

        self._closing = True

        # attempt a graceful disconnect
        if self._state == HubConnectorState.CONNECTED and self._conn is not None:
            request = DisconnectRequest()
            request.bvlcMessageID = self._next_message_id()
            try:
                await self._send(request)
            except Exception:
                pass

        await self._close_connection()

        if self._run_task is not None:
            self._run_task.cancel()
            self._run_task = None
