#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC BVLL
-------------------

Encode/decode round-trip tests for all BACnet/SC BVLC message types, plus
decode tests against the wire examples published in the standard (Addendum
135-2016bj Figures YY-5 and YY-6, equivalent to Annex AB in 135-2020/2024).
"""

import unittest
from uuid import UUID

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.pdu import PDU, VirtualAddress
from bacpypes3.basetypes import ErrorClass, ErrorCode
from bacpypes3.sc.bvll import (
    LPCI,
    LPDU,
    pdu_types,
    HeaderOption,
    SecurePathHeaderOption,
    ProprietaryHeaderOption,
    Result,
    EncapsulatedNPDU,
    AddressResolution,
    AddressResolutionACK,
    Advertisement,
    AdvertisementSolicitation,
    ConnectRequest,
    ConnectAccept,
    DisconnectRequest,
    DisconnectACK,
    HeartbeatRequest,
    HeartbeatACK,
    ProprietaryMessage,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def decode_lpdu(blob: str) -> LPDU:
    """Decode a hex string into an LPDU following the BVLLCodec two-step
    decode: first the link-layer header (LPCI), then the function-specific
    payload."""
    pdu = PDU(xtob(blob))
    lpci = LPCI.decode(pdu)
    lpdu = pdu_types[lpci.bvlcFunction].decode(pdu)
    LPCI.update(lpdu, lpci)
    return lpdu


def encode_hex(lpdu: LPDU) -> str:
    """Encode an LPDU and return the octets as an upper-case hex string."""
    from bacpypes3.debugging import btox

    return btox(lpdu.encode().pduData).upper()


@bacpypes_debugging
class TestHeaderOptions(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_secure_path_round_trip(self):
        option = SecurePathHeaderOption()
        assert option.option_type == 1
        assert option.must_understand is True

        pdu = option.encode()
        decoded = HeaderOption.decode(pdu)
        assert isinstance(decoded, SecurePathHeaderOption)
        assert decoded.option_type == 1
        assert decoded.must_understand is True
        assert decoded.header_data_flag is False

    def test_proprietary_round_trip(self):
        option = ProprietaryHeaderOption(
            xtob("C5ECC099"),
            vendor_identifier=0x022B,
            proprietary_option_type=0xBA,
        )
        pdu = option.encode()
        decoded = HeaderOption.decode(pdu)
        assert isinstance(decoded, ProprietaryHeaderOption)
        assert decoded.option_type == 31
        assert decoded.vendor_identifier == 0x022B
        assert decoded.proprietary_option_type == 0xBA
        assert decoded.pduData == xtob("C5ECC099")

    def test_proprietary_no_data(self):
        option = ProprietaryHeaderOption(
            b"",
            vendor_identifier=0x0309,
            proprietary_option_type=0x39,
        )
        pdu = option.encode()
        decoded = HeaderOption.decode(pdu)
        assert isinstance(decoded, ProprietaryHeaderOption)
        assert decoded.vendor_identifier == 0x0309
        assert decoded.proprietary_option_type == 0x39
        assert decoded.pduData == b""


@bacpypes_debugging
class TestResult(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_ack_round_trip(self):
        lpdu = Result(result_function=EncapsulatedNPDU.bvlcFunction, result_code=0x00)
        lpdu.bvlcMessageID = 0x1234

        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, Result)
        assert decoded.bvlcMessageID == 0x1234
        assert decoded.result_function == EncapsulatedNPDU.bvlcFunction
        assert decoded.result_code == 0x00

    def test_nak_round_trip(self):
        lpdu = Result(
            result_function=EncapsulatedNPDU.bvlcFunction,
            result_code=0x01,
            error_header_marker=0x00,
            error_class=ErrorClass.communication,
            error_code=ErrorCode.headerNotUnderstood,
            error_details="nope",
        )
        lpdu.bvlcMessageID = 0x1234

        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, Result)
        assert decoded.result_code == 0x01
        assert decoded.error_class == ErrorClass.communication
        assert decoded.error_code == ErrorCode.headerNotUnderstood
        assert decoded.error_details == "nope"


@bacpypes_debugging
class TestEncapsulatedNPDU(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_simple_round_trip(self):
        lpdu = EncapsulatedNPDU(xtob("0104deadbeef"))
        lpdu.bvlcMessageID = 0x0001
        lpdu.bvlcDestinationVirtualAddress = VirtualAddress(xtob("010203040506"))

        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, EncapsulatedNPDU)
        assert decoded.bvlcMessageID == 0x0001
        assert decoded.bvlcDestinationVirtualAddress.addrAddr == xtob("010203040506")
        assert decoded.bvlcOriginatingVirtualAddress is None
        assert decoded.pduData == xtob("0104deadbeef")

    def test_broadcast_round_trip(self):
        # broadcast VMAC is FF:FF:FF:FF:FF:FF
        lpdu = EncapsulatedNPDU(xtob("0120fffe"))
        lpdu.bvlcMessageID = 0x0002
        lpdu.bvlcDestinationVirtualAddress = VirtualAddress(xtob("FFFFFFFFFFFF"))

        decoded = decode_lpdu(encode_hex(lpdu))
        assert decoded.bvlcDestinationVirtualAddress.addrAddr == xtob("FFFFFFFFFFFF")

    def test_figure_yy5_decode(self):
        """Decode the Encapsulated-NPDU wire example from the standard
        (Addendum 135-2016bj Figure YY-5).  This message conveys a
        ReadProperty request being sent to the hub function for forwarding."""
        blob = (
            "01"  # BVLC function: Encapsulated-NPDU
            "07"  # control flags: dest vmac, dest options, data options
            "B5EC"  # message id
            "927BF71A96A2"  # destination virtual address
            # destination options
            "BF0007022BBAC5ECC099"  # proprietary option, vendor 555
            "3F0003030939"  # proprietary option, vendor 777
            # data options
            "01"  # secure path option
            # payload (npdu)
            "0104"
            "0000010C0C000000051955"
        )
        lpdu = decode_lpdu(blob)

        assert isinstance(lpdu, EncapsulatedNPDU)
        assert lpdu.bvlcMessageID == 0xB5EC
        assert lpdu.bvlcOriginatingVirtualAddress is None
        assert lpdu.bvlcDestinationVirtualAddress.addrAddr == xtob("927BF71A96A2")

        # two destination options, both proprietary
        assert len(lpdu.bvlcDestinationOptions) == 2
        opt0 = lpdu.bvlcDestinationOptions[0]
        assert isinstance(opt0, ProprietaryHeaderOption)
        assert opt0.vendor_identifier == 555
        assert opt0.proprietary_option_type == 0xBA
        assert opt0.pduData == xtob("C5ECC099")
        assert opt0.more_options is True

        opt1 = lpdu.bvlcDestinationOptions[1]
        assert isinstance(opt1, ProprietaryHeaderOption)
        assert opt1.vendor_identifier == 777
        assert opt1.proprietary_option_type == 0x39
        assert opt1.more_options is False

        # one data option: secure path
        assert len(lpdu.bvlcDataOptions) == 1
        assert isinstance(lpdu.bvlcDataOptions[0], SecurePathHeaderOption)

        # payload is the encapsulated npdu
        assert lpdu.pduData == xtob("01040000010C0C000000051955")


@bacpypes_debugging
class TestAddressResolution(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_address_resolution_round_trip(self):
        lpdu = AddressResolution()
        lpdu.bvlcMessageID = 0x0003
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, AddressResolution)
        assert decoded.bvlcMessageID == 0x0003

    def test_address_resolution_ack_round_trip(self):
        uris = "wss://host.example.org:47808/path wss://10.0.0.1/x"
        lpdu = AddressResolutionACK(uris)
        lpdu.bvlcMessageID = 0x0004
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, AddressResolutionACK)
        assert decoded.websocket_uris == uris

    def test_address_resolution_ack_empty(self):
        lpdu = AddressResolutionACK("")
        lpdu.bvlcMessageID = 0x0005
        decoded = decode_lpdu(encode_hex(lpdu))
        assert decoded.websocket_uris == ""


@bacpypes_debugging
class TestAdvertisement(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_advertisement_round_trip(self):
        lpdu = Advertisement(
            hub_connection_status=1,
            accept_direct_connections=0,
            maximum_bvlc_length=1497,
            maximum_npdu_length=1476,
        )
        lpdu.bvlcMessageID = 0x0006
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, Advertisement)
        assert decoded.hub_connection_status == 1
        assert decoded.accept_direct_connections == 0
        assert decoded.maximum_bvlc_length == 1497
        assert decoded.maximum_npdu_length == 1476

    def test_advertisement_solicitation_round_trip(self):
        lpdu = AdvertisementSolicitation()
        lpdu.bvlcMessageID = 0x0007
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, AdvertisementSolicitation)
        assert decoded.bvlcMessageID == 0x0007


@bacpypes_debugging
class TestConnect(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_connect_request_round_trip(self):
        vmac = VirtualAddress(xtob("020304050607"))
        uuid = UUID("f81d4fae-7dec-11d0-a765-00a0c91e6bf6")
        lpdu = ConnectRequest(
            vmac_address=vmac,
            device_uuid=uuid,
            maximum_bvlc_length=1497,
            maximum_npdu_length=1476,
        )
        lpdu.bvlcMessageID = 0x0008
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, ConnectRequest)
        assert decoded.vmac_address.addrAddr == xtob("020304050607")
        assert decoded.device_uuid == uuid
        assert decoded.maximum_bvlc_length == 1497
        assert decoded.maximum_npdu_length == 1476

    def test_connect_accept_round_trip(self):
        vmac = VirtualAddress(xtob("0A0B0C0D0E0F"))
        uuid = UUID("f81d4fae-7dec-11d0-a765-00a0c91e6bf6")
        lpdu = ConnectAccept(
            vmac_address=vmac,
            device_uuid=uuid,
            maximum_bvlc_length=61327,
            maximum_npdu_length=1497,
        )
        lpdu.bvlcMessageID = 0x0009
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, ConnectAccept)
        assert decoded.vmac_address.addrAddr == xtob("0A0B0C0D0E0F")
        assert decoded.device_uuid == uuid
        assert decoded.maximum_bvlc_length == 61327
        assert decoded.maximum_npdu_length == 1497


@bacpypes_debugging
class TestConnectionControl(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_disconnect_request_round_trip(self):
        lpdu = DisconnectRequest()
        lpdu.bvlcMessageID = 0x000A
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, DisconnectRequest)
        assert decoded.bvlcMessageID == 0x000A

    def test_disconnect_ack_round_trip(self):
        lpdu = DisconnectACK()
        lpdu.bvlcMessageID = 0x000B
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, DisconnectACK)

    def test_heartbeat_request_round_trip(self):
        lpdu = HeartbeatRequest()
        lpdu.bvlcMessageID = 0x000C
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, HeartbeatRequest)

    def test_heartbeat_ack_round_trip(self):
        lpdu = HeartbeatACK()
        lpdu.bvlcMessageID = 0x000D
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, HeartbeatACK)


@bacpypes_debugging
class TestProprietaryMessage(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_proprietary_message_round_trip(self):
        lpdu = ProprietaryMessage(555, 0x2A, xtob("cafe"))
        lpdu.bvlcMessageID = 0x000E
        decoded = decode_lpdu(encode_hex(lpdu))
        assert isinstance(decoded, ProprietaryMessage)
        assert decoded.vendor_identifier == 555
        assert decoded.proprietary_function == 0x2A
        assert decoded.pduData == xtob("cafe")


if __name__ == "__main__":
    unittest.main()
