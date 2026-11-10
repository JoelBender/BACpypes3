#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC hub connector state machine
-------------------------------------------

Drives the initiating-peer connection state machine (Clause YY.6.2.2) directly
through its ``_fsm_*`` handlers with a fake WebSocket connection, so no live
TLS socket is required.
"""

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
from bacpypes3.sc.service import SCHubConnector, HubConnectorState

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


if __name__ == "__main__":
    unittest.main()
