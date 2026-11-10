#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC hub connector state machine
-------------------------------------------

Drives the initiating-peer connection state machine (Clause YY.6.2.2) directly
through its ``_fsm_*`` handlers with a fake WebSocket connection, so no live
TLS socket is required.
"""

import asyncio
import time
import unittest
from uuid import UUID

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.comm import Client, bind
from bacpypes3.pdu import PDU, SecureConnectAddress, VirtualAddress
from bacpypes3.basetypes import ErrorClass, ErrorCode
from bacpypes3.sc.bvll import (
    ConnectRequest,
    ConnectAccept,
    DisconnectRequest,
    DisconnectACK,
    HeartbeatRequest,
    EncapsulatedNPDU,
    Result,
)
from bacpypes3.sc.service import (
    HUB_CONNECTOR_CONNECTED_FAILOVER,
    HUB_CONNECTOR_CONNECTED_PRIMARY,
    HUB_CONNECTOR_NO_CONNECTION,
    HubConnectorState,
    SCHubConnector,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

DEVICE_UUID = UUID("f81d4fae-7dec-11d0-a765-00a0c91e6bf6")
HUB_UUID = UUID("12345678-1234-5678-1234-567812345678")


class FakeConn:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, data):
        self.sent.append(bytes(data))

    async def close(self, *args, **kwargs):
        self.closed = True


class UpstreamCapture(Client):
    def __init__(self):
        super().__init__()
        self.received = []

    async def confirmation(self, pdu):
        self.received.append(pdu)


def decode(data):
    from bacpypes3.sc.bvll import LPCI, pdu_types

    pdu = PDU(data)
    lpci = LPCI.decode(pdu)
    lpdu = pdu_types[lpci.bvlcFunction].decode(pdu)
    LPCI.update(lpdu, lpci)
    return lpdu


def make_connector(**kwargs):
    connector = SCHubConnector(
        SecureConnectAddress(xtob("AABBCCDDEEFF")),
        DEVICE_UUID,
        "wss://hub.example.org/",
        **kwargs,
    )
    capture = UpstreamCapture()
    bind(capture, connector)
    return connector, capture


def connect_accept_bytes(message_id=0):
    lpdu = ConnectAccept(
        vmac_address=VirtualAddress(xtob("010203040506")),
        device_uuid=HUB_UUID,
        maximum_bvlc_length=1497,
        maximum_npdu_length=1476,
    )
    lpdu.bvlcMessageID = message_id
    return lpdu.encode().pduData


@bacpypes_debugging
class TestHubConnectorFSM(unittest.IsolatedAsyncioTestCase):
    _debug = None  # type: ignore[assignment]

    async def asyncTearDown(self):
        # cancel any pending timers created during the test
        if hasattr(self, "connector"):
            self.connector._cancel_all_timers()

    async def _established(self):
        connector, capture = make_connector()
        self.connector = connector
        connector._conn = FakeConn()
        connector._state = HubConnectorState.AWAITING_WEBSOCKET
        await connector._fsm_ws_established()
        return connector, capture

    async def test_connect_request_sent(self):
        connector, capture = await self._established()

        assert connector._state == HubConnectorState.AWAITING_ACCEPT
        assert len(connector._conn.sent) == 1
        lpdu = decode(connector._conn.sent[0])
        assert isinstance(lpdu, ConnectRequest)
        assert lpdu.vmac_address.addrAddr == xtob("AABBCCDDEEFF")
        assert lpdu.device_uuid == DEVICE_UUID

    async def test_connect_accept_establishes(self):
        connector, capture = await self._established()

        await connector._fsm_message(connect_accept_bytes())

        assert connector._state == HubConnectorState.CONNECTED
        assert connector.connected.is_set()
        assert connector.peer_vmac.addrAddr == xtob("010203040506")
        assert connector.peer_uuid == HUB_UUID

    async def test_connect_wait_timeout(self):
        connector, capture = await self._established()

        await connector._fsm_connect_wait_timeout()

        assert connector._state == HubConnectorState.IDLE
        assert connector._conn is None

    async def test_duplicate_vmac_regenerates(self):
        connector, capture = await self._established()
        original = connector.vmac.addrAddr

        nak = Result(
            result_function=ConnectRequest.bvlcFunction,
            result_code=0x01,
            error_class=ErrorClass.communication,
            error_code=ErrorCode.nodeDuplicateVmac,
        )
        nak.bvlcMessageID = 0
        await connector._fsm_message(nak.encode().pduData)

        assert connector._state == HubConnectorState.IDLE
        assert connector.vmac.addrAddr != original
        # Random-48: low nibble of first octet is 0x2
        assert (connector.vmac.addrAddr[0] & 0x0F) == 0x02

    async def test_vmac_change_callback(self):
        changes = []
        connector, capture = make_connector(on_vmac_change=changes.append)
        self.connector = connector
        connector._conn = FakeConn()
        connector._state = HubConnectorState.AWAITING_ACCEPT

        nak = Result(
            result_function=ConnectRequest.bvlcFunction,
            result_code=0x01,
            error_class=ErrorClass.communication,
            error_code=ErrorCode.nodeDuplicateVmac,
        )
        nak.bvlcMessageID = 0
        await connector._fsm_message(nak.encode().pduData)

        assert len(changes) == 1
        assert changes[0] is connector.vmac

    async def test_encapsulated_npdu_forwarded_up(self):
        connector, capture = await self._established()
        await connector._fsm_message(connect_accept_bytes())

        # a forwarded NPDU from the hub
        npdu = EncapsulatedNPDU(xtob("0104cafe"))
        npdu.bvlcMessageID = 1
        npdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        await connector._fsm_message(npdu.encode().pduData)

        assert len(capture.received) == 1
        # the raw BVLC bytes are passed up to the codec unchanged
        assert capture.received[0].pduData == npdu.encode().pduData

    async def test_disconnect_request_received(self):
        connector, capture = await self._established()
        await connector._fsm_message(connect_accept_bytes())

        conn = connector._conn
        conn.sent.clear()

        req = DisconnectRequest()
        req.bvlcMessageID = 7
        await connector._fsm_message(req.encode().pduData)

        # a Disconnect-ACK was returned and the connection closed to IDLE
        assert len(conn.sent) == 1
        ack = decode(conn.sent[0])
        assert isinstance(ack, DisconnectACK)
        assert ack.bvlcMessageID == 7
        assert conn.closed
        assert connector._state == HubConnectorState.IDLE

    async def test_heartbeat_sent_when_idle(self):
        connector, capture = await self._established()
        await connector._fsm_message(connect_accept_bytes())
        connector._conn.sent.clear()

        await connector._fsm_heartbeat()

        assert len(connector._conn.sent) == 1
        assert isinstance(decode(connector._conn.sent[0]), HeartbeatRequest)

    async def test_connector_state_reported(self):
        from bacpypes3.sc.service import (
            HUB_CONNECTOR_NO_CONNECTION,
            HUB_CONNECTOR_CONNECTED_PRIMARY,
        )

        states = []
        connector, capture = make_connector(on_connector_state_change=states.append)
        self.connector = connector
        connector._conn = FakeConn()
        connector._state = HubConnectorState.AWAITING_WEBSOCKET
        await connector._fsm_ws_established()

        # connecting on the primary hub reports connectedToPrimary
        await connector._fsm_message(connect_accept_bytes())
        assert states == [HUB_CONNECTOR_CONNECTED_PRIMARY]

        # closing reports back to noHubConnection
        await connector._close_connection()
        assert states[-1] == HUB_CONNECTOR_NO_CONNECTION

    async def test_indication_requires_connection(self):
        connector, capture = await self._established()

        # not connected yet: dropped
        await connector.indication(PDU(xtob("deadbeef")))
        assert len(connector._conn.sent) == 1  # only the Connect-Request

        # once connected it is sent
        await connector._fsm_message(connect_accept_bytes())
        connector._conn.sent.clear()
        await connector.indication(PDU(xtob("deadbeef")))
        assert connector._conn.sent == [xtob("deadbeef")]


class ScriptedConn(FakeConn):
    """A WebSocket connection to a hub that accepts the Connect-Request and
    (optionally) acknowledges a Disconnect-Request."""

    def __init__(self, ack_disconnect=True):
        super().__init__()
        self.ack_disconnect = ack_disconnect
        self.queue = asyncio.Queue()

    async def send(self, data):
        self.sent.append(bytes(data))
        lpdu = decode(data)
        if isinstance(lpdu, ConnectRequest):
            self.queue.put_nowait(connect_accept_bytes(lpdu.bvlcMessageID))
        elif isinstance(lpdu, DisconnectRequest) and self.ack_disconnect:
            ack = DisconnectACK()
            ack.bvlcMessageID = lpdu.bvlcMessageID
            self.queue.put_nowait(ack.encode().pduData)

    async def close(self, *args, **kwargs):
        self.closed = True
        self.queue.put_nowait(None)

    def lost(self):
        """The hub went away."""
        self.queue.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.queue.get()
        if message is None:
            raise StopAsyncIteration
        return message

    def sent_types(self):
        return [type(decode(data)) for data in self.sent]


class ScriptedConnector(SCHubConnector):
    """A connector whose _connect() follows a script, each URI has a list of
    outcomes, an exception is raised and a connection is returned."""

    def __init__(self, script, **kwargs):
        kwargs.setdefault("minimum_reconnect_time", 0.01)
        kwargs.setdefault("maximum_reconnect_time", 0.04)
        kwargs.setdefault("disconnect_wait_timeout", 0.05)
        super().__init__(
            SecureConnectAddress(xtob("AABBCCDDEEFF")),
            DEVICE_UUID,
            "wss://primary/",
            "wss://failover/" if "wss://failover/" in script else None,
            **kwargs,
        )
        self.script = script
        self.attempts = []
        self.states = []
        self.on_connector_state_change = self.states.append

    async def _connect(self, uri):
        self.attempts.append(uri)
        outcomes = self.script[uri]
        outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


async def wait_for(predicate, timeout=1.0):
    """Wait for the predicate to become true."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timeout")
        await asyncio.sleep(0.005)


@bacpypes_debugging
class TestHubConnectorRun(unittest.IsolatedAsyncioTestCase):
    """The run loop with scripted hub connections (Clauses AB.5.2, AB.6)."""

    _debug = None  # type: ignore[assignment]

    async def asyncTearDown(self):
        if hasattr(self, "connector"):
            await self.connector.close()

    async def test_primary(self):
        conn = ScriptedConn()
        self.connector = connector = ScriptedConnector({"wss://primary/": [conn]})
        connector.start()
        await wait_for(lambda: connector.connected.is_set())

        assert connector.attempts == ["wss://primary/"]
        assert connector.states == [HUB_CONNECTOR_CONNECTED_PRIMARY]

    async def test_close_waits_for_disconnect_ack(self):
        conn = ScriptedConn()
        connector = ScriptedConnector({"wss://primary/": [conn]})
        connector.start()
        await wait_for(lambda: connector.connected.is_set())

        await connector.close()

        assert conn.sent_types() == [ConnectRequest, DisconnectRequest]
        assert conn.closed
        assert connector.states[-1] == HUB_CONNECTOR_NO_CONNECTION

    async def test_close_disconnect_wait_timeout(self):
        conn = ScriptedConn(ack_disconnect=False)
        connector = ScriptedConnector(
            {"wss://primary/": [conn]}, disconnect_wait_timeout=0.05
        )
        connector.start()
        await wait_for(lambda: connector.connected.is_set())

        start = time.monotonic()
        await connector.close()
        elapsed = time.monotonic() - start

        # waited for the Disconnect-ACK that never came, then closed
        assert elapsed >= 0.04
        assert conn.sent_types() == [ConnectRequest, DisconnectRequest]
        assert conn.closed

    async def test_failover_when_primary_down(self):
        conn = ScriptedConn()
        self.connector = connector = ScriptedConnector(
            {
                "wss://primary/": [OSError("primary down")],
                "wss://failover/": [conn],
            }
        )
        connector.start()
        await wait_for(lambda: connector.connected.is_set())

        # the failover hub is tried right after the primary fails
        assert connector.attempts[:2] == ["wss://primary/", "wss://failover/"]
        assert connector.states == [HUB_CONNECTOR_CONNECTED_FAILOVER]

    async def test_primary_restored(self):
        failover_conn = ScriptedConn()
        primary_conn = ScriptedConn()
        self.connector = connector = ScriptedConnector(
            {
                "wss://primary/": [
                    OSError("primary down"),
                    OSError("still down"),
                    primary_conn,
                ],
                "wss://failover/": [failover_conn],
            }
        )
        connector.start()

        # on the failover hub, the primary keeps being retried and when it
        # comes back the failover connection is terminated
        await wait_for(
            lambda: connector.states[-1:] == [HUB_CONNECTOR_CONNECTED_PRIMARY]
        )
        assert connector.states == [
            HUB_CONNECTOR_CONNECTED_FAILOVER,
            HUB_CONNECTOR_NO_CONNECTION,
            HUB_CONNECTOR_CONNECTED_PRIMARY,
        ]
        assert failover_conn.sent_types() == [ConnectRequest, DisconnectRequest]
        assert failover_conn.closed
        assert primary_conn.sent_types() == [ConnectRequest]
        assert connector._conn is primary_conn

    async def test_lost_connection_retries_primary_first(self):
        first_conn = ScriptedConn()
        second_conn = ScriptedConn()
        failover_conn = ScriptedConn()
        self.connector = connector = ScriptedConnector(
            {
                "wss://primary/": [first_conn, second_conn],
                "wss://failover/": [failover_conn],
            }
        )
        connector.start()
        await wait_for(lambda: connector.connected.is_set())

        # the primary hub goes away
        first_conn.lost()
        await wait_for(
            lambda: connector._conn is second_conn and connector.connected.is_set()
        )

        assert connector.attempts == ["wss://primary/", "wss://primary/"]
        assert failover_conn.sent == []


if __name__ == "__main__":
    unittest.main()
