"""
Test Segmented Response Timeout
-------------------------------

When a server sends the first segment of a segmented response and the client
never acknowledges it, the window size has not been negotiated yet.  The retry
must resend the first segment rather than calling fill_window(), which asserts
when actualWindowSize is None (see PR #149).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from bacpypes3.apdu import ComplexAckPDU
from bacpypes3.appservice import SEGMENTED_RESPONSE, ServerSSM
from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import Address

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def make_server_ssm(segment_count: int = 3) -> ServerSSM:
    """Build a server SSM in the SEGMENTED_RESPONSE state with the first segment
    already sent."""
    sap = MagicMock()
    sap.device_object = None
    sap.numberOfApduRetries = 3
    sap.apduTimeout = 3000
    sap.segmentationSupported = "segmentedBoth"
    sap.segmentTimeout = 1500
    sap.maxSegmentsAccepted = 16
    sap.maxApduLengthAccepted = 1024
    sap.proposedWindowSize = 2
    sap.request = AsyncMock()

    ssm = ServerSSM(sap, Address("1.2.3.4"))

    response = ComplexAckPDU(12, 7)
    response.put_data(b"\x00" * (10 * segment_count))
    ssm.segmentAPDU = response
    ssm.segmentSize = 10
    ssm.segmentCount = segment_count
    ssm.invokeID = 7

    ssm.state = SEGMENTED_RESPONSE
    ssm.segmentRetryCount = 0
    ssm.sentAllSegments = False
    ssm.initialSequenceNumber = 0
    ssm.actualWindowSize = None

    return ssm


async def test_resend_first_segment_before_window_negotiated():
    ssm = make_server_ssm()
    try:
        await ssm.segmented_response_timeout()

        # just the first segment went out again
        ssm.ssmSAP.request.assert_awaited_once()
        apdu = ssm.ssmSAP.request.await_args.args[0]
        assert apdu.apduSeg
        assert apdu.apduSeq == 0
        assert apdu.apduMor
        assert apdu.pduDestination == Address("1.2.3.4")
        assert ssm.segmentRetryCount == 1
    finally:
        ssm.stop_timer()


async def test_refill_window_after_negotiation():
    ssm = make_server_ssm()
    ssm.initialSequenceNumber = 1
    ssm.actualWindowSize = 2
    try:
        await ssm.segmented_response_timeout()

        # the rest of the window is sent again
        seqs = [call.args[0].apduSeq for call in ssm.ssmSAP.request.await_args_list]
        assert seqs == [1, 2]
        assert ssm.sentAllSegments
    finally:
        ssm.stop_timer()
