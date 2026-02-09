#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Invalid Tag Handling
-------------------------

Verifies that malformed BACnet PDUs raising InvalidTag, DecodingError, or other
exceptions during decode do not crash the event loop.  These tests exercise the
three call sites fixed in appservice.py and ipv4/__init__.py.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bacpypes3.debugging import ModuleLogger
from bacpypes3.errors import DecodingError, InvalidTag
from bacpypes3.pdu import PDU, PDUData, IPv4Address
from bacpypes3.primitivedata import Tag
from bacpypes3.apdu import (
    APDU,
    APCISequence,
    AbortPDU,
    AbortReason,
    UnconfirmedRequestPDU,
)
from bacpypes3.appservice import (
    ApplicationServiceAccessPoint,
    ServerSSM,
)
from bacpypes3.ipv4 import IPv4DatagramServer

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# ---------------------------------------------------------------------------
# Tag.decode() – improved error messages
# ---------------------------------------------------------------------------


class TestTagDecodeErrorMessages:
    """Tag.decode() should include the original DecodingError context."""

    def test_truncated_tag_includes_original_error(self):
        """A truncated tag should raise InvalidTag chained from DecodingError."""
        # Context tag, tag number 2, extended length (5 marker) then claims 20
        # bytes but buffer is empty after the length byte -> DecodingError
        pdu_data = PDUData(bytearray([0x2D, 0x14]))
        with pytest.raises(InvalidTag, match="invalid tag encoding"):
            Tag.decode(pdu_data)

    def test_empty_pdu_raises_invalid_tag(self):
        """An empty PDU should raise InvalidTag."""
        pdu_data = PDUData(bytearray())
        with pytest.raises(InvalidTag):
            Tag.decode(pdu_data)

    def test_error_chain_preserved(self):
        """The original DecodingError should be chained via __cause__."""
        pdu_data = PDUData(bytearray([0x2D, 0x14]))
        with pytest.raises(InvalidTag) as exc_info:
            Tag.decode(pdu_data)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, DecodingError)

    def test_valid_tag_still_decodes(self):
        """Ensure valid tags are unaffected by the error-handling changes."""
        # Boolean True tag: application class, tag number 1, LVT=1
        pdu_data = PDUData(bytearray([0x11]))
        tag = Tag.decode(pdu_data)
        assert tag.tag_number == 1  # boolean


# ---------------------------------------------------------------------------
# Bug 1 – UnconfirmedRequestPDU decode in confirmation()
# ---------------------------------------------------------------------------


def _make_asap():
    """Create a minimal ApplicationServiceAccessPoint for testing."""
    asap = ApplicationServiceAccessPoint.__new__(ApplicationServiceAccessPoint)
    asap.clientTransactions = []
    asap.serverTransactions = []
    asap.deviceInfoCache = None
    asap.dccEnableDisable = "enable"
    asap.sap_request = AsyncMock()
    return asap


def _make_unconfirmed_apdu():
    """Build a real UnconfirmedRequestPDU suitable for isinstance checks."""
    apdu = UnconfirmedRequestPDU()
    apdu.pduSource = MagicMock()
    apdu.pduDestination = MagicMock()
    return apdu


class TestUnconfirmedRequestDecodeHandling:
    """ApplicationServiceAccessPoint.confirmation() should catch all decode
    errors from UnconfirmedRequestPDU, not just AttributeError."""

    @pytest.mark.asyncio
    async def test_invalid_tag_is_caught(self):
        """InvalidTag during UnconfirmedRequestPDU decode should be caught."""
        asap = _make_asap()
        fake_apdu = _make_unconfirmed_apdu()

        with patch.object(
            APDU, "decode", return_value=fake_apdu
        ), patch.object(
            APCISequence, "decode", side_effect=InvalidTag("bad tag")
        ):
            await asap.confirmation(MagicMock())

        asap.sap_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_decoding_error_is_caught(self):
        """DecodingError during UnconfirmedRequestPDU decode should be caught."""
        asap = _make_asap()
        fake_apdu = _make_unconfirmed_apdu()

        with patch.object(
            APDU, "decode", return_value=fake_apdu
        ), patch.object(
            APCISequence, "decode",
            side_effect=DecodingError("no more packet data"),
        ):
            await asap.confirmation(MagicMock())

        asap.sap_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_value_error_is_caught(self):
        """ValueError during UnconfirmedRequestPDU decode should be caught."""
        asap = _make_asap()
        fake_apdu = _make_unconfirmed_apdu()

        with patch.object(
            APDU, "decode", return_value=fake_apdu
        ), patch.object(
            APCISequence, "decode", side_effect=ValueError("bad value")
        ):
            await asap.confirmation(MagicMock())

        asap.sap_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_attribute_error_still_caught(self):
        """AttributeError (original handler) should still be caught."""
        asap = _make_asap()
        fake_apdu = _make_unconfirmed_apdu()

        with patch.object(
            APDU, "decode", return_value=fake_apdu
        ), patch.object(
            APCISequence, "decode", side_effect=AttributeError("no attr")
        ):
            await asap.confirmation(MagicMock())

        asap.sap_request.assert_not_called()


# ---------------------------------------------------------------------------
# Bug 2 – ServerSSM.request() unprotected decode
# ---------------------------------------------------------------------------


def _make_server_ssm():
    """Create a minimal ServerSSM for testing."""
    ssm = ServerSSM.__new__(ServerSSM)
    ssm.pdu_address = MagicMock()
    ssm.ssmSAP = MagicMock()
    ssm.ssmSAP.sap_request = AsyncMock()
    return ssm


class TestServerSSMRequestDecodeHandling:
    """ServerSSM.request() should catch decode errors and send an AbortPDU."""

    @pytest.mark.asyncio
    async def test_invalid_tag_sends_abort(self):
        """InvalidTag during request decode should send an AbortPDU."""
        ssm = _make_server_ssm()
        apdu = MagicMock(spec=[])  # not an AbortPDU instance

        with patch.object(
            APCISequence, "decode", side_effect=InvalidTag("bad tag")
        ):
            await ssm.request(apdu)

        ssm.ssmSAP.sap_request.assert_called_once()
        abort_call = ssm.ssmSAP.sap_request.call_args[0][0]
        assert isinstance(abort_call, AbortPDU)

    @pytest.mark.asyncio
    async def test_decoding_error_sends_abort(self):
        """DecodingError during request decode should send an AbortPDU."""
        ssm = _make_server_ssm()
        apdu = MagicMock(spec=[])

        with patch.object(
            APCISequence, "decode",
            side_effect=DecodingError("no more packet data"),
        ):
            await ssm.request(apdu)

        ssm.ssmSAP.sap_request.assert_called_once()
        abort_call = ssm.ssmSAP.sap_request.call_args[0][0]
        assert isinstance(abort_call, AbortPDU)

    @pytest.mark.asyncio
    async def test_abort_pdu_passes_through(self):
        """An AbortPDU should not be decoded, just forwarded."""
        ssm = _make_server_ssm()
        apdu = AbortPDU(reason=AbortReason.other)
        apdu.pduSource = None
        apdu.pduDestination = None

        with patch.object(APCISequence, "decode") as mock_decode:
            await ssm.request(apdu)

        # decode should NOT have been called for an AbortPDU
        mock_decode.assert_not_called()
        ssm.ssmSAP.sap_request.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 3 – IPv4DatagramServer.confirmation() top-level handler
# ---------------------------------------------------------------------------


def _make_ipv4_server():
    """Create a minimal IPv4DatagramServer for testing."""
    server = IPv4DatagramServer.__new__(IPv4DatagramServer)
    server.local_address = ("10.18.2.16", 47808)
    server.response = AsyncMock()
    return server


class TestIPv4DatagramServerConfirmation:
    """IPv4DatagramServer.confirmation() should catch exceptions from the
    processing stack and not let them escape as unhandled task exceptions."""

    @pytest.mark.asyncio
    async def test_exception_in_response_is_caught(self):
        """An exception from self.response() should be caught, not propagated."""
        server = _make_ipv4_server()
        server.response = AsyncMock(
            side_effect=InvalidTag("bad tag in PDU")
        )

        pdu = PDU(b"\x00\x01\x02")
        pdu.pduSource = IPv4Address(("10.18.2.100", 47808))

        await server.confirmation(pdu)

    @pytest.mark.asyncio
    async def test_runtime_error_in_response_is_caught(self):
        """A RuntimeError from processing should be caught."""
        server = _make_ipv4_server()
        server.response = AsyncMock(
            side_effect=RuntimeError("segmentation fault in decode")
        )

        pdu = PDU(b"\x00\x01\x02")
        pdu.pduSource = IPv4Address(("10.18.2.100", 47808))

        await server.confirmation(pdu)

    @pytest.mark.asyncio
    async def test_normal_pdu_still_processed(self):
        """A normal PDU should still be forwarded via response()."""
        server = _make_ipv4_server()

        pdu = PDU(b"\x00\x01\x02")
        pdu.pduSource = IPv4Address(("10.18.2.100", 47808))

        await server.confirmation(pdu)

        server.response.assert_called_once_with(pdu)

    @pytest.mark.asyncio
    async def test_reflected_broadcast_still_filtered(self):
        """Reflected broadcasts (source == local) should still be filtered."""
        server = _make_ipv4_server()

        pdu = PDU(b"\x00\x01\x02")
        pdu.pduSource = IPv4Address(("10.18.2.16", 47808))

        await server.confirmation(pdu)

        server.response.assert_not_called()
