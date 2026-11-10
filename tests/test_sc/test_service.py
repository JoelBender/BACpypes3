#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC BVLL Service Access Point
----------------------------------------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.comm import Client, Server, bind
from bacpypes3.pdu import PDU, Address, LocalBroadcast, SecureConnectAddress
from bacpypes3.basetypes import ErrorClass, ErrorCode
from bacpypes3.sc.bvll import (
    LPCI,
    BVLLCodec,
    EncapsulatedNPDU,
    HeaderOption,
    Result,
    pdu_types,
)
from bacpypes3.sc.service import SCBVLLServiceAccessPoint

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def decode_lpdu(data: bytes):
    pdu = PDU(data)
    lpci = LPCI.decode(pdu)
    lpdu = pdu_types[lpci.bvlcFunction].decode(pdu)
    LPCI.update(lpdu, lpci)
    return lpdu


class UpstreamCapture(Client):
    """Captures PDUs delivered upstream by the SAP."""

    def __init__(self):
        super().__init__()
        self.received = []

    async def confirmation(self, pdu):
        self.received.append(pdu)


class DownstreamStub(Server):
    """Captures encoded PDUs sent downstream and can inject received PDUs."""

    def __init__(self):
        super().__init__()
        self.sent = []

    async def indication(self, pdu):
        self.sent.append(pdu)

    async def inject(self, pdu):
        await self.response(pdu)


@bacpypes_debugging
class TestSCBVLLServiceAccessPoint(unittest.IsolatedAsyncioTestCase):
    _debug = None  # type: ignore[assignment]

    def build_stack(self):
        local_vmac = SecureConnectAddress(xtob("AABBCCDDEEFF"))
        capture = UpstreamCapture()
        sap = SCBVLLServiceAccessPoint(local_vmac)
        codec = BVLLCodec()
        stub = DownstreamStub()
        bind(capture, sap, codec, stub)
        return capture, sap, codec, stub

    async def test_unicast_downstream(self):
        capture, sap, codec, stub = self.build_stack()

        dest = SecureConnectAddress(xtob("010203040506"))
        await capture.request(PDU(xtob("0104deadbeef"), destination=dest))

        assert len(stub.sent) == 1
        lpdu = decode_lpdu(stub.sent[0].pduData)
        assert isinstance(lpdu, EncapsulatedNPDU)
        assert lpdu.bvlcDestinationVirtualAddress.addrAddr == xtob("010203040506")
        assert lpdu.bvlcOriginatingVirtualAddress is None
        assert lpdu.pduData == xtob("0104deadbeef")

    async def test_broadcast_downstream(self):
        capture, sap, codec, stub = self.build_stack()

        await capture.request(PDU(xtob("0120"), destination=LocalBroadcast()))

        assert len(stub.sent) == 1
        lpdu = decode_lpdu(stub.sent[0].pduData)
        assert lpdu.bvlcDestinationVirtualAddress.addrAddr == xtob("FFFFFFFFFFFF")

    async def test_unicast_upstream(self):
        capture, sap, codec, stub = self.build_stack()

        # a message forwarded by the hub: originating VMAC present, no
        # destination VMAC (we are the connection peer / final destination)
        lpdu = EncapsulatedNPDU(xtob("0104cafe"))
        lpdu.bvlcMessageID = 0x0001
        lpdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        await stub.inject(PDU(lpdu.encode().pduData))

        assert len(capture.received) == 1
        pdu = capture.received[0]
        assert pdu.pduSource.addrAddr == xtob("010203040506")
        assert pdu.pduData == xtob("0104cafe")
        # addressed to this node
        assert pdu.pduDestination.addrType == Address.localStationAddr

    async def test_broadcast_upstream(self):
        capture, sap, codec, stub = self.build_stack()

        # a broadcast forwarded by the hub keeps the broadcast destination VMAC
        lpdu = EncapsulatedNPDU(xtob("0120"))
        lpdu.bvlcMessageID = 0x0002
        lpdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        lpdu.bvlcDestinationVirtualAddress = SecureConnectAddress(
            SecureConnectAddress.local_broadcast
        )
        await stub.inject(PDU(lpdu.encode().pduData))

        assert len(capture.received) == 1
        pdu = capture.received[0]
        assert pdu.pduSource.addrAddr == xtob("010203040506")
        assert pdu.pduDestination.addrType == Address.localBroadcastAddr

    async def test_unicast_with_destination_dropped(self):
        capture, sap, codec, stub = self.build_stack()

        # a unicast message for this node from the hub has no destination,
        # one with a (non-broadcast) destination is dropped (Clause AB.5.4)
        lpdu = EncapsulatedNPDU(xtob("0104cafe"))
        lpdu.bvlcMessageID = 0x0003
        lpdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        lpdu.bvlcDestinationVirtualAddress = SecureConnectAddress(xtob("AABBCCDDEEFF"))
        await stub.inject(PDU(lpdu.encode().pduData))

        assert capture.received == []
        assert stub.sent == []

    async def test_must_understand_unicast_nak(self):
        capture, sap, codec, stub = self.build_stack()

        # an unsupported destination option that must be understood
        lpdu = EncapsulatedNPDU(xtob("0104cafe"))
        lpdu.bvlcMessageID = 0x1234
        lpdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        lpdu.bvlcDestinationOptions = [
            HeaderOption(option_type=5, must_understand=True)
        ]
        await stub.inject(PDU(lpdu.encode().pduData))

        # not delivered, a NAK goes back to the originating node
        assert capture.received == []
        assert len(stub.sent) == 1
        nak = decode_lpdu(stub.sent[0].pduData)
        assert isinstance(nak, Result)
        assert nak.result_function == EncapsulatedNPDU.bvlcFunction
        assert nak.result_code == 0x01
        assert nak.error_header_marker == 0x45
        assert nak.error_class == ErrorClass.communication
        assert nak.error_code == ErrorCode.headerNotUnderstood
        assert nak.bvlcMessageID == 0x1234
        assert nak.bvlcDestinationVirtualAddress.addrAddr == xtob("010203040506")
        assert nak.bvlcOriginatingVirtualAddress is None

    async def test_must_understand_broadcast_ignored(self):
        capture, sap, codec, stub = self.build_stack()

        lpdu = EncapsulatedNPDU(xtob("0120"))
        lpdu.bvlcMessageID = 0x0004
        lpdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        lpdu.bvlcDestinationVirtualAddress = SecureConnectAddress(
            SecureConnectAddress.local_broadcast
        )
        lpdu.bvlcDestinationOptions = [
            HeaderOption(option_type=5, must_understand=True)
        ]
        await stub.inject(PDU(lpdu.encode().pduData))

        # ignored, no NAK for a broadcast
        assert capture.received == []
        assert stub.sent == []

    async def test_optional_destination_option_ignored(self):
        capture, sap, codec, stub = self.build_stack()

        # a destination option that need not be understood is skipped
        lpdu = EncapsulatedNPDU(xtob("0104cafe"))
        lpdu.bvlcMessageID = 0x0005
        lpdu.bvlcOriginatingVirtualAddress = SecureConnectAddress(xtob("010203040506"))
        lpdu.bvlcDestinationOptions = [HeaderOption(option_type=5)]
        await stub.inject(PDU(lpdu.encode().pduData))

        assert len(capture.received) == 1
        assert stub.sent == []


if __name__ == "__main__":
    unittest.main()
