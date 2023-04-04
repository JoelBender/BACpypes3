"""
Application Layer
"""

from __future__ import annotations

import asyncio

from typing import (
    Callable,
    List,
    Optional,
    Tuple,
)

from .debugging import ModuleLogger, DebugContents, bacpypes_debugging
from .comm import Client, ServiceAccessPoint
from .errors import CommuncationError

from .pdu import Address, PDU
from .basetypes import Segmentation
from .apdu import (
    encode_max_segments_accepted,
    decode_max_segments_accepted,
    encode_max_apdu_length_accepted,
    decode_max_apdu_length_accepted,
    APCISequence,
    APDU,
    AbortPDU,
    AbortReason,
    ComplexAckPDU,
    ConfirmedRequestPDU,
    Error,
    ErrorPDU,
    RejectPDU,
    SegmentAckPDU,
    SimpleAckPDU,
    UnconfirmedRequestPDU,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   SSM - Segmentation State Machine
#

# transaction states
IDLE = 0
SEGMENTED_REQUEST = 1
AWAIT_CONFIRMATION = 2
AWAIT_RESPONSE = 3
SEGMENTED_RESPONSE = 4
SEGMENTED_CONFIRMATION = 5
COMPLETED = 6
ABORTED = 7


@bacpypes_debugging
class SSM(DebugContents):
    transactionLabels = [
        "IDLE",
        "SEGMENTED_REQUEST",
        "AWAIT_CONFIRMATION",
        "AWAIT_RESPONSE",
        "SEGMENTED_RESPONSE",
        "SEGMENTED_CONFIRMATION",
        "COMPLETED",
        "ABORTED",
    ]

    _debug: Callable[..., None]
    _exception: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "ssmSAP",
        "device_object",
        "device_info",
        "invokeID",
        "state",
        "segmentAPDU",
        "segmentSize",
        "segmentCount",
        "maxSegmentsAccepted",
        "retryCount",
        "segmentRetryCount",
        "sentAllSegments",
        "lastSequenceNumber",
        "initialSequenceNumber",
        "actualWindowSize",
    )

    invokeID: Optional[int]
    _timer_handle: Optional[asyncio.Handle]

    segmentState: int
    segmentAPDU: Optional[APDU]
    segmentSize: Optional[int]
    segmentCount: Optional[int]

    retryCount: Optional[int]
    segmentRetryCount: Optional[int]
    sentAllSegments: Optional[bool]
    lastSequenceNumber: Optional[int]
    initialSequenceNumber: Optional[int]
    actualWindowSize: Optional[int]

    def __init__(
        self, sap: ApplicationServiceAccessPoint, pdu_address: Address
    ) -> None:
        """Common parts for client and server segmentation."""
        if _debug:
            SSM._debug("__init__ %r %r", sap, pdu_address)

        self.ssmSAP = sap  # service access point

        # save the address and get the device information
        self.pdu_address = pdu_address
        self.invokeID = None  # invoke ID
        self._timer_handle = None  # no timer scheduled

        self.state = IDLE  # initial state
        self.segmentAPDU = None  # refers to request or response
        self.segmentSize = None  # how big the pieces are
        self.segmentCount = None

        self.retryCount = None
        self.segmentRetryCount = None
        self.sentAllSegments = None
        self.lastSequenceNumber = None
        self.initialSequenceNumber = None
        self.actualWindowSize = None

        # local device object provides these or SAP provides defaults, make
        # copies here so they are consistent throughout the transaction but
        # they could change from one transaction to the next
        self.numberOfApduRetries = getattr(
            sap.device_object, "numberOfApduRetries", sap.numberOfApduRetries
        )
        self.apduTimeout = getattr(sap.device_object, "apduTimeout", sap.apduTimeout)

        self.segmentationSupported = getattr(
            sap.device_object, "segmentationSupported", sap.segmentationSupported
        )
        self.segmentTimeout = getattr(
            sap.device_object, "apduSegmentTimeout", sap.segmentTimeout
        )
        self.maxSegmentsAccepted = getattr(
            sap.device_object, "maxSegmentsAccepted", sap.maxSegmentsAccepted
        )
        self.maxApduLengthAccepted = getattr(
            sap.device_object, "maxApduLengthAccepted", sap.maxApduLengthAccepted
        )

    def start_timer(self, msecs: int) -> None:
        if _debug:
            SSM._debug("start_timer %r", msecs)

        # if this is set, cancel it
        if self._timer_handle:
            if _debug:
                SSM._debug("    - is scheduled")
            self._timer_handle.cancel()

        # schedule a call to self.timer_expired()
        loop = asyncio.get_event_loop()
        self._timer_handle = loop.call_later(msecs / 1000.0, self.timer_expired)
        if _debug:
            SSM._debug("    - timer handle: %r", self._timer_handle)

    def stop_timer(self) -> None:
        if _debug:
            SSM._debug("stop_timer")

        # if this is set, cancel it
        if self._timer_handle:
            if _debug:
                SSM._debug("    - is scheduled")
            self._timer_handle.cancel()
            self._timer_handle = None

    def restart_timer(self, msecs: int) -> None:
        if _debug:
            SSM._debug("restart_timer %r", msecs)

        # the current timer will be canceled if it is set
        self.start_timer(msecs)

    def timer_expired(self) -> None:
        """
        This function is called when the timer expires and must be overridden
        by a subclass.
        """
        raise NotImplementedError("timer_expired")

    def set_state(self, newState, msecs: int = 0) -> None:
        """
        This function is called when the derived class wants to change state
        and optionally start a timer.
        """
        if _debug:
            SSM._debug(
                "set_state %r (%s) msecs=%r",
                newState,
                SSM.transactionLabels[newState],
                msecs,
            )

        # make sure we have a correct transition
        if (self.state == COMPLETED) or (self.state == ABORTED):
            err = RuntimeError(
                "invalid state transition from %s to %s"
                % (SSM.transactionLabels[self.state], SSM.transactionLabels[newState])
            )
            SSM._exception(err)
            raise err

        # stop any current timer
        self.stop_timer()

        # make the change
        self.state = newState

        # if another timer should be started, start it
        if msecs:
            self.start_timer(msecs)

    def set_segmentation_context(self, apdu: APDU) -> None:
        """This function is called to set the segmentation context."""
        if _debug:
            SSM._debug("set_segmentation_context %s", repr(apdu))

        # set the context
        self.segmentAPDU = apdu

    def get_segment(self, indx: int) -> APDU:
        """
        This function returns an APDU coorisponding to a particular
        segment of a confirmed request or complex ack.  The segmentAPDU
        is the context.
        """
        if _debug:
            SSM._debug("get_segment %r", indx)

        # check for no context
        if not self.segmentAPDU:
            raise RuntimeError("no segmentation context established")
        assert self.segmentCount is not None

        # check for invalid segment number
        if indx >= self.segmentCount:
            raise RuntimeError(
                "invalid segment number {0}, APDU has {1} segments".format(
                    indx, self.segmentCount
                )
            )

        if self.segmentAPDU.apduType == ConfirmedRequestPDU.pduType:
            if _debug:
                SSM._debug("    - confirmed request context")
            assert self.invokeID is not None

            segAPDU = ConfirmedRequestPDU(
                self.segmentAPDU.apduService, self.segmentAPDU.apduInvokeID
            )

            segAPDU.apduMaxSegs = encode_max_segments_accepted(self.maxSegmentsAccepted)
            segAPDU.apduMaxResp = encode_max_apdu_length_accepted(
                self.maxApduLengthAccepted
            )
            segAPDU.apduInvokeID = self.invokeID

            # segmented response accepted?
            segAPDU.apduSA = self.segmentationSupported in (
                Segmentation.segmentedReceive,
                Segmentation.segmentedBoth,
            )
            if _debug:
                SSM._debug("    - segmented response accepted: %r", segAPDU.apduSA)

        elif self.segmentAPDU.apduType == ComplexAckPDU.pduType:
            if _debug:
                SSM._debug("    - complex ack context")

            segAPDU = ComplexAckPDU(
                self.segmentAPDU.apduService, self.segmentAPDU.apduInvokeID
            )
        else:
            raise RuntimeError("invalid APDU type for segmentation context")

        # maintain the the user data reference
        segAPDU.pduUserData = self.segmentAPDU.pduUserData

        # make sure the destination is set
        segAPDU.pduDestination = self.pdu_address

        # segmented message?
        if self.segmentCount != 1:
            segAPDU.apduSeg = True
            segAPDU.apduMor = indx < (self.segmentCount - 1)  # more follows
            segAPDU.apduSeq = indx % 256  # sequence number

            # first segment sends proposed window size, rest get actual
            if indx == 0:
                if _debug:
                    SSM._debug(
                        "    - proposedWindowSize: %r", self.ssmSAP.proposedWindowSize
                    )
                segAPDU.apduWin = self.ssmSAP.proposedWindowSize
            else:
                if _debug:
                    SSM._debug("    - actualWindowSize: %r", self.actualWindowSize)
                assert self.actualWindowSize is not None

                segAPDU.apduWin = self.actualWindowSize
        else:
            segAPDU.apduSeg = False
            segAPDU.apduMor = False

        # add the content
        assert self.segmentSize

        offset = indx * self.segmentSize
        segAPDU.put_data(self.segmentAPDU.pduData[offset : offset + self.segmentSize])

        # success
        return segAPDU

    def append_segment(self, apdu: APDU) -> None:
        """
        This function appends the apdu content to the end of the current
        APDU being built.  The segmentAPDU is the context.
        """
        if _debug:
            SSM._debug("append_segment %r", apdu)

        # check for no context
        if not self.segmentAPDU:
            raise RuntimeError("no segmentation context established")

        # append the data
        self.segmentAPDU.put_data(apdu.pduData)

    def in_window(self, seqA: int, seqB: int) -> bool:
        if _debug:
            SSM._debug("in_window %r %r", seqA, seqB)
        assert self.actualWindowSize

        rslt = ((seqA - seqB + 256) % 256) < self.actualWindowSize
        if _debug:
            SSM._debug("    - rslt: %r", rslt)

        return rslt

    async def fill_window(self, seqNum: int) -> None:
        """This function sends all of the packets necessary to fill
        out the segmentation window."""
        if _debug:
            SSM._debug("fill_window %r", seqNum)
        if _debug:
            SSM._debug("    - actualWindowSize: %r", self.actualWindowSize)
        assert self.actualWindowSize

        for ix in range(self.actualWindowSize):
            apdu = self.get_segment(seqNum + ix)

            # now continue downstream
            await self.ssmSAP.request(apdu)

            # check for no more follows
            if not apdu.apduMor:
                self.sentAllSegments = True
                break


#
#   ClientSSM - Client Segmentation State Machine
#


@bacpypes_debugging
class ClientSSM(SSM):
    _debug: Callable[..., None]

    def __init__(self, sap: ApplicationServiceAccessPoint, pdu_address) -> None:
        if _debug:
            ClientSSM._debug("__init__ %s %r", sap, pdu_address)
        SSM.__init__(self, sap, pdu_address)

        # initialize the retry count
        self.retryCount = 0

    def set_state(self, newState: int, timer: int = 0) -> None:
        """This function is called when the client wants to change state."""
        if _debug:
            ClientSSM._debug(
                "set_state %r (%s) timer=%r",
                newState,
                SSM.transactionLabels[newState],
                timer,
            )

        # do the regular state change
        SSM.set_state(self, newState, timer)

        # when completed or aborted, remove tracking
        if (newState == COMPLETED) or (newState == ABORTED):
            if _debug:
                ClientSSM._debug("    - remove from active transactions")
            self.ssmSAP.clientTransactions.remove(self)

    async def request(self, apdu: APDU) -> None:
        """This function is called by client transaction functions when it wants
        to send a message to the device."""
        if _debug:
            ClientSSM._debug("request %r", apdu)

        # make sure it has a good source and destination
        apdu.pduSource = None
        apdu.pduDestination = self.pdu_address

        # now continue downstream
        await self.ssmSAP.request(apdu)

    async def indication(self, apdu: APDU) -> None:
        """This function is called after the device has bound a new transaction
        and wants to start the process rolling."""
        if _debug:
            ClientSSM._debug("indication %r", apdu)

        # make sure we're getting confirmed requests
        if apdu.apduType != ConfirmedRequestPDU.pduType:
            raise RuntimeError("invalid APDU (1)")

        # save the request and set the segmentation context
        self.set_segmentation_context(apdu)

        # get information about the server we are going to talk to
        self.device_info = await self.ssmSAP.device_info_cache.get_device_info(
            self.pdu_address
        )
        if _debug:
            ClientSSM._debug("    - device_info: %r", self.device_info)

        # if the max apdu length of the server isn't known, assume that it
        # is the same size as our own and will be the segment size
        if (not self.device_info) or (
            self.device_info.max_apdu_length_accepted is None
        ):
            self.segmentSize = self.maxApduLengthAccepted

        # if the max npdu length of the server isn't known, assume that it
        # is the same as the max apdu length accepted
        elif self.device_info.max_npdu_length is None:
            self.segmentSize = self.device_info.max_apdu_length_accepted

        # the segment size is the minimum of the size of the largest packet
        # that can be delivered to the server and the largest it can accept
        else:
            self.segmentSize = min(
                self.device_info.max_npdu_length,
                self.device_info.max_apdu_length_accepted,
            )
        if _debug:
            ClientSSM._debug("    - segment size: %r", self.segmentSize)

        # save the invoke ID
        self.invokeID = apdu.apduInvokeID
        if _debug:
            ClientSSM._debug("    - invoke ID: %r", self.invokeID)

        # compute the segment count
        if not apdu.pduData:
            # always at least one segment
            self.segmentCount = 1
        else:
            # split into chunks, maybe need one more
            self.segmentCount, more = divmod(len(apdu.pduData), self.segmentSize)
            if more:
                self.segmentCount += 1
        if _debug:
            ClientSSM._debug("    - segment count: %r", self.segmentCount)

        # make sure we support segmented transmit if we need to
        if self.segmentCount > 1:
            if self.segmentationSupported not in (
                Segmentation.segmentedTransmit,
                Segmentation.segmentedBoth,
            ):
                if _debug:
                    ClientSSM._debug("    - local device can't send segmented requests")
                abort = self.abort(AbortReason.segmentationNotSupported)
                await self.response(abort)
                return

            if not self.device_info:
                if _debug:
                    ClientSSM._debug("    - no server info for segmentation support")

            elif self.device_info.segmentation_supported not in (
                Segmentation.segmentedReceive,
                Segmentation.segmentedBoth,
            ):
                if _debug:
                    ClientSSM._debug("    - server can't receive segmented requests")
                abort = self.abort(AbortReason.segmentationNotSupported)
                await self.response(abort)
                return

            # make sure we dont exceed the number of segments in our request
            # that the server said it was willing to accept
            if not self.device_info:
                if _debug:
                    ClientSSM._debug(
                        "    - no server info for maximum number of segments"
                    )

            elif not self.device_info.max_segments_accepted:
                if _debug:
                    ClientSSM._debug(
                        "    - server doesn't say maximum number of segments"
                    )

            elif self.segmentCount > self.device_info.max_segments_accepted:
                if _debug:
                    ClientSSM._debug("    - server can't receive enough segments")
                abort = self.abort(AbortReason.apduTooLong)
                await self.response(abort)
                return

        # send out the first segment (or the whole thing)
        if self.segmentCount == 1:
            # unsegmented
            self.sentAllSegments = True
            self.retryCount = 0
            self.set_state(AWAIT_CONFIRMATION, self.apduTimeout)
        else:
            # segmented
            self.sentAllSegments = False
            self.retryCount = 0
            self.segmentRetryCount = 0
            self.initialSequenceNumber = 0
            self.actualWindowSize = None  # segment ack will set value
            self.set_state(SEGMENTED_REQUEST, self.segmentTimeout)

        # deliver to the device
        try:
            await self.request(self.get_segment(0))
        except CommuncationError as err:
            if _debug:
                ClientSSM._debug("    - communication error: %r", err)

            # completed
            self.set_state(COMPLETED)

            # make this look like it came from the device
            error_pdu = Error(
                source=apdu.pduDestination,
                destination=None,
                service_choice=apdu.apduService,
                invoke_id=apdu.apduInvokeID,
                errorClass=err.errorClass,
                errorCode=err.errorCode,
            )
            if _debug:
                ClientSSM._debug("    - error_pdu: %r", error_pdu)

            # this has already been decoded, layer skipping :-(
            await ServiceAccessPoint.sap_response(self.ssmSAP, error_pdu)

    async def response(self, apdu):
        """This function is called by client transaction functions when they want
        to send a message to the application."""
        if _debug:
            ClientSSM._debug("response %r", apdu)

        # make sure it has a good source and destination
        apdu.pduSource = self.pdu_address
        apdu.pduDestination = None

        # send it to the application
        await self.ssmSAP.sap_response(apdu)

    async def confirmation(self, apdu):
        """This function is called by the device for all upstream messages related
        to the transaction."""
        if _debug:
            ClientSSM._debug("confirmation %r", apdu)

        if self.state == SEGMENTED_REQUEST:
            await self.segmented_request(apdu)
        elif self.state == AWAIT_CONFIRMATION:
            await self.await_confirmation(apdu)
        elif self.state == SEGMENTED_CONFIRMATION:
            await self.segmented_confirmation(apdu)
        else:
            raise RuntimeError("invalid state")

    def timer_expired(self):
        """
        This function is called when something has taken too long.
        """
        if _debug:
            ClientSSM._debug("timer_expired")

        fn: Callable[..., None] = None
        if self.state == SEGMENTED_REQUEST:
            fn = self.segmented_request_timeout
        elif self.state == AWAIT_CONFIRMATION:
            fn = self.await_confirmation_timeout
        elif self.state == SEGMENTED_CONFIRMATION:
            fn = self.segmented_confirmation_timeout
        elif self.state == COMPLETED:
            pass
        elif self.state == ABORTED:
            pass
        else:
            err = RuntimeError("invalid state")
            ClientSSM._exception("exception: %r", err)
            raise err

        if fn:
            asyncio.ensure_future(fn())

    def abort(self, reason):
        """This function is called when the transaction should be aborted."""
        if _debug:
            ClientSSM._debug("abort %r", reason)

        # change the state to aborted
        self.set_state(ABORTED)

        # build an abort PDU to return
        abort_pdu = AbortPDU(False, self.invokeID, reason)

        # return it
        return abort_pdu

    async def segmented_request(self, apdu):
        """This function is called when the client is sending a segmented request
        and receives an apdu."""
        if _debug:
            ClientSSM._debug("segmented_request %r", apdu)

        # server is ready for the next segment
        if apdu.apduType == SegmentAckPDU.pduType:
            if _debug:
                ClientSSM._debug("    - segment ack")

            # actual window size is provided by server
            self.actualWindowSize = apdu.apduWin

            # duplicate ack received?
            if not self.in_window(apdu.apduSeq, self.initialSequenceNumber):
                if _debug:
                    ClientSSM._debug("    - not in window")
                self.restart_timer(self.segmentTimeout)

            # final ack received?
            elif self.sentAllSegments:
                if _debug:
                    ClientSSM._debug("    - all done sending request")
                self.set_state(AWAIT_CONFIRMATION, self.apduTimeout)

            # more segments to send
            else:
                if _debug:
                    ClientSSM._debug("    - more segments to send")

                self.initialSequenceNumber = (apdu.apduSeq + 1) % 256
                self.segmentRetryCount = 0
                await self.fill_window(self.initialSequenceNumber)
                self.restart_timer(self.segmentTimeout)

        # simple ack
        elif apdu.apduType == SimpleAckPDU.pduType:
            if _debug:
                ClientSSM._debug("    - simple ack")

            if not self.sentAllSegments:
                abort = self.abort(AbortReason.invalidApduInThisState)
                await self.request(abort)  # send it to the device
                await self.response(abort)  # send it to the application
            else:
                self.set_state(COMPLETED)
                await self.response(apdu)

        elif apdu.apduType == ComplexAckPDU.pduType:
            if _debug:
                ClientSSM._debug("    - complex ack")

            if not self.sentAllSegments:
                abort = self.abort(AbortReason.invalidApduInThisState)
                await self.request(abort)  # send it to the device
                await self.response(abort)  # send it to the application

            elif not apdu.apduSeg:
                # ack is not segmented
                self.set_state(COMPLETED)
                await self.response(apdu)

            else:
                # set the segmented response context
                self.set_segmentation_context(apdu)

                # minimum of what the server is proposing and this client proposes
                self.actualWindowSize = min(
                    apdu.apduWin, self.ssmSAP.proposedWindowSize
                )
                self.lastSequenceNumber = 0
                self.initialSequenceNumber = 0
                self.set_state(SEGMENTED_CONFIRMATION, self.segmentTimeout)

        # some kind of problem
        elif (
            (apdu.apduType == ErrorPDU.pduType)
            or (apdu.apduType == RejectPDU.pduType)
            or (apdu.apduType == AbortPDU.pduType)
        ):
            if _debug:
                ClientSSM._debug("    - error/reject/abort")

            self.set_state(COMPLETED)
            await self.response(apdu)

        else:
            raise RuntimeError("invalid APDU (2)")

    async def segmented_request_timeout(self):
        if _debug:
            ClientSSM._debug("segmented_request_timeout")

        # try again
        if self.segmentRetryCount < self.numberOfApduRetries:
            if _debug:
                ClientSSM._debug("    - retry segmented request")

            self.segmentRetryCount += 1
            self.start_timer(self.segmentTimeout)

            if self.initialSequenceNumber == 0:
                await self.request(self.get_segment(0))
            else:
                await self.fill_window(self.initialSequenceNumber)
        else:
            if _debug:
                ClientSSM._debug("    - abort, no response from the device")

            abort = self.abort(AbortReason.noResponse)
            await self.response(abort)

    async def await_confirmation(self, apdu):
        if _debug:
            ClientSSM._debug("await_confirmation %r", apdu)

        if apdu.apduType == AbortPDU.pduType:
            if _debug:
                ClientSSM._debug("    - server aborted")

            self.set_state(ABORTED)
            await self.response(apdu)

        elif (
            (apdu.apduType == SimpleAckPDU.pduType)
            or (apdu.apduType == ErrorPDU.pduType)
            or (apdu.apduType == RejectPDU.pduType)
        ):
            if _debug:
                ClientSSM._debug("    - simple ack, error, or reject")

            self.set_state(COMPLETED)
            await self.response(apdu)

        elif apdu.apduType == ComplexAckPDU.pduType:
            if _debug:
                ClientSSM._debug("    - complex ack")

            # if the response is not segmented, we're done
            if not apdu.apduSeg:
                if _debug:
                    ClientSSM._debug("    - unsegmented")

                self.set_state(COMPLETED)
                await self.response(apdu)

            elif self.segmentationSupported not in (
                Segmentation.segmentedReceive,
                Segmentation.segmentedBoth,
            ):
                if _debug:
                    ClientSSM._debug(
                        "    - local device can't receive segmented messages"
                    )
                abort = self.abort(AbortReason.segmentationNotSupported)
                await self.response(abort)

            elif apdu.apduSeq == 0:
                if _debug:
                    ClientSSM._debug("    - segmented response")

                # set the segmented response context
                self.set_segmentation_context(apdu)

                self.actualWindowSize = apdu.apduWin
                self.lastSequenceNumber = 0
                self.initialSequenceNumber = 0
                self.set_state(SEGMENTED_CONFIRMATION, self.segmentTimeout)

                # send back a segment ack
                segack = SegmentAckPDU(
                    0,
                    0,
                    self.invokeID,
                    self.initialSequenceNumber,
                    self.actualWindowSize,
                )
                await self.request(segack)

            else:
                if _debug:
                    ClientSSM._debug("    - invalid APDU in this state")

                abort = self.abort(AbortReason.invalidApduInThisState)
                await self.request(abort)  # send it to the device
                await self.response(abort)  # send it to the application

        elif apdu.apduType == SegmentAckPDU.pduType:
            if _debug:
                ClientSSM._debug("    - segment ack(!?)")

            self.restart_timer(self.segmentTimeout)

        else:
            raise RuntimeError("invalid APDU (3)")

    async def await_confirmation_timeout(self):
        if _debug:
            ClientSSM._debug("await_confirmation_timeout")

        if self.retryCount < self.numberOfApduRetries:
            if _debug:
                ClientSSM._debug(
                    "    - no response, try again (%d < %d)",
                    self.retryCount,
                    self.numberOfApduRetries,
                )
            self.retryCount += 1

            # save the retry count, indication acts like the request is coming
            # from the application so the retryCount gets re-initialized.
            saveCount = self.retryCount
            await self.indication(self.segmentAPDU)
            self.retryCount = saveCount
        else:
            if _debug:
                ClientSSM._debug("    - retry count exceeded")
            abort = self.abort(AbortReason.noResponse)
            await self.response(abort)

    async def segmented_confirmation(self, apdu):
        if _debug:
            ClientSSM._debug("segmented_confirmation %r", apdu)

        # the only messages we should be getting are complex acks
        if apdu.apduType != ComplexAckPDU.pduType:
            if _debug:
                ClientSSM._debug("    - complex ack required")

            abort = self.abort(AbortReason.invalidApduInThisState)
            await self.request(abort)  # send it to the device
            await self.response(abort)  # send it to the application
            return

        # it must be segmented
        if not apdu.apduSeg:
            if _debug:
                ClientSSM._debug("    - must be segmented")

            abort = self.abort(AbortReason.invalidApduInThisState)
            await self.request(abort)  # send it to the device
            await self.response(abort)  # send it to the application
            return

        # proper segment number
        if apdu.apduSeq != (self.lastSequenceNumber + 1) % 256:
            if _debug:
                ClientSSM._debug(
                    "    - segment %s received out of order, should be %s",
                    apdu.apduSeq,
                    (self.lastSequenceNumber + 1) % 256,
                )

            # segment received out of order
            self.restart_timer(self.segmentTimeout)
            segack = SegmentAckPDU(
                1, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize
            )
            await self.request(segack)
            return

        # add the data
        self.append_segment(apdu)

        # update the sequence number
        self.lastSequenceNumber = (self.lastSequenceNumber + 1) % 256

        # last segment received
        if not apdu.apduMor:
            if _debug:
                ClientSSM._debug("    - no more follows")

            # send a final ack
            segack = SegmentAckPDU(
                0, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize
            )
            await self.request(segack)

            self.set_state(COMPLETED)
            await self.response(self.segmentAPDU)

        elif apdu.apduSeq == (
            (self.initialSequenceNumber + self.actualWindowSize) % 256
        ):
            if _debug:
                ClientSSM._debug("    - last segment in the group")

            self.initialSequenceNumber = self.lastSequenceNumber
            self.restart_timer(self.segmentTimeout)
            segack = SegmentAckPDU(
                0, 0, self.invokeID, self.lastSequenceNumber, self.actualWindowSize
            )
            await self.request(segack)

        else:
            # wait for more segments
            if _debug:
                ClientSSM._debug("    - wait for more segments")

            self.restart_timer(self.segmentTimeout)

    async def segmented_confirmation_timeout(self):
        if _debug:
            ClientSSM._debug("segmented_confirmation_timeout")

        abort = self.abort(AbortReason.noResponse)
        await self.response(abort)


#
#   ServerSSM - Server Segmentation State Machine
#


@bacpypes_debugging
class ServerSSM(SSM):
    _debug: Callable[..., None]

    def __init__(self, sap, pdu_address):
        if _debug:
            ServerSSM._debug("__init__ %s %r", sap, pdu_address)
        SSM.__init__(self, sap, pdu_address)

    def set_state(self, newState, timer=0):
        """This function is called when the client wants to change state."""
        if _debug:
            ServerSSM._debug(
                "set_state %r (%s) timer=%r",
                newState,
                SSM.transactionLabels[newState],
                timer,
            )

        # do the regular state change
        SSM.set_state(self, newState, timer)

        # when completed or aborted, remove tracking
        if (newState == COMPLETED) or (newState == ABORTED):
            if _debug:
                ServerSSM._debug("    - remove from active transactions")
            self.ssmSAP.serverTransactions.remove(self)

    async def request(self, apdu):
        """This function is called by transaction functions to send
        to the application."""
        if _debug:
            ServerSSM._debug("request %r", apdu)

        # if this is an abort, no more decoding
        if isinstance(apdu, AbortPDU):
            pass
        else:
            # decode this now, the APDU is complete
            apdu = APCISequence.decode(apdu)
            if _debug:
                ServerSSM._debug("    - apdu: %r", apdu)

        # make sure it has a good source and destination
        apdu.pduSource = self.pdu_address
        apdu.pduDestination = None

        # send it via the device
        await self.ssmSAP.sap_request(apdu)

    async def indication(self, apdu):
        """This function is called for each downstream packet related to
        the transaction."""
        if _debug:
            ServerSSM._debug("indication %r", apdu)

        if self.state == IDLE:
            await self.idle(apdu)
        elif self.state == SEGMENTED_REQUEST:
            await self.segmented_request(apdu)
        elif self.state == AWAIT_RESPONSE:
            await self.await_response(apdu)
        elif self.state == SEGMENTED_RESPONSE:
            await self.segmented_response(apdu)
        else:
            if _debug:
                ServerSSM._debug("    - invalid state")

    async def response(self, apdu):
        """This function is called by transaction functions when they want
        to send a message to the device."""
        if _debug:
            ServerSSM._debug("response %r", apdu)

        # make sure it has a good source and destination
        apdu.pduSource = None
        apdu.pduDestination = self.pdu_address

        # now continue downstream
        await self.ssmSAP.request(apdu)

    async def confirmation(self, apdu):
        """This function is called when the application has provided a response
        and needs it to be sent to the client."""
        if _debug:
            ServerSSM._debug("confirmation %r", apdu)

        # check to see we are in the correct state
        if self.state != AWAIT_RESPONSE:
            if _debug:
                ServerSSM._debug("    - warning: not expecting a response")

        # abort response
        if apdu.apduType == AbortPDU.pduType:
            if _debug:
                ServerSSM._debug("    - abort")

            self.set_state(ABORTED)

            # send the response to the device
            await self.response(apdu)
            return

        # simple response
        if (
            (apdu.apduType == SimpleAckPDU.pduType)
            or (apdu.apduType == ErrorPDU.pduType)
            or (apdu.apduType == RejectPDU.pduType)
        ):
            if _debug:
                ServerSSM._debug("    - simple ack, error, or reject")

            # transaction completed
            self.set_state(COMPLETED)

            # send the response to the device
            await self.response(apdu)
            return

        # complex ack
        if apdu.apduType == ComplexAckPDU.pduType:
            if _debug:
                ServerSSM._debug("    - complex ack")

            # save the response and set the segmentation context
            self.set_segmentation_context(apdu)

            # the segment size is the minimum of the size of the largest packet
            # that can be delivered to the client and the largest it can accept
            if (not self.device_info) or (self.device_info.max_npdu_length is None):
                self.segmentSize = self.maxApduLengthAccepted
            else:
                self.segmentSize = min(
                    self.device_info.max_npdu_length, self.maxApduLengthAccepted
                )
            if _debug:
                ServerSSM._debug("    - segment size: %r", self.segmentSize)

            # compute the segment count
            if not apdu.pduData:
                # always at least one segment
                self.segmentCount = 1
            else:
                # split into chunks, maybe need one more
                self.segmentCount, more = divmod(len(apdu.pduData), self.segmentSize)
                if more:
                    self.segmentCount += 1
            if _debug:
                ServerSSM._debug("    - segment count: %r", self.segmentCount)

            # make sure we support segmented transmit if we need to
            if self.segmentCount > 1:
                if _debug:
                    ServerSSM._debug(
                        "    - segmentation required, %d segments", self.segmentCount
                    )

                # make sure we support segmented transmit
                if self.segmentationSupported not in (
                    Segmentation.segmentedTransmit,
                    Segmentation.segmentedBoth,
                ):
                    if _debug:
                        ServerSSM._debug("    - server can't send segmented responses")
                    abort = self.abort(AbortReason.segmentationNotSupported)
                    await self.response(abort)
                    return

                # make sure client supports segmented receive
                if not self.segmented_response_accepted:
                    if _debug:
                        ServerSSM._debug(
                            "    - client can't receive segmented responses"
                        )
                    abort = self.abort(AbortReason.segmentationNotSupported)
                    await self.response(abort)
                    return

                # make sure we dont exceed the number of segments in our response
                # that the client said it was willing to accept in the request
                if (self.maxSegmentsAccepted is not None) and (
                    self.segmentCount > self.maxSegmentsAccepted
                ):
                    if _debug:
                        ServerSSM._debug("    - client can't receive enough segments")
                    abort = self.abort(AbortReason.apduTooLong)
                    await self.response(abort)
                    return

            # initialize the state
            self.segmentRetryCount = 0
            self.initialSequenceNumber = 0
            self.actualWindowSize = None

            # send out the first segment (or the whole thing)
            if self.segmentCount == 1:
                apdu.apduSeg = False
                apdu.apduMor = False

                await self.response(apdu)
                self.set_state(COMPLETED)
            else:
                await self.response(self.get_segment(0))
                self.set_state(SEGMENTED_RESPONSE, self.segmentTimeout)

        else:
            raise RuntimeError("invalid APDU (4)")

    def timer_expired(self):
        """
        This function is called when the client has failed to send all of the
        segments of a segmented request, the application has taken too long to
        complete the request, or the client failed to ack the segments of a
        segmented response.
        """
        if _debug:
            ServerSSM._debug("timer_expired")

        fn: Callable[..., None] = None
        if self.state == SEGMENTED_REQUEST:
            fn = self.segmented_request_timeout
        elif self.state == AWAIT_RESPONSE:
            fn = self.await_response_timeout
        elif self.state == SEGMENTED_RESPONSE:
            fn = self.segmented_response_timeout
        elif self.state == COMPLETED:
            pass
        elif self.state == ABORTED:
            pass
        else:
            if _debug:
                ServerSSM._debug("invalid state")
            raise RuntimeError("invalid state")

        if fn:
            asyncio.ensure_future(fn())

    def abort(self, reason):
        """This function is called when the application would like to abort the
        transaction.  There is no notification back to the application."""
        if _debug:
            ServerSSM._debug("abort %r", reason)

        # change the state to aborted
        self.set_state(ABORTED)

        # return an abort APDU
        return AbortPDU(True, self.invokeID, reason)

    async def idle(self, apdu):
        if _debug:
            ServerSSM._debug("idle %r", apdu)

        # make sure we're getting confirmed requests
        if not isinstance(apdu, ConfirmedRequestPDU):
            raise RuntimeError("invalid APDU (5)")

        # save the invoke ID
        self.invokeID = apdu.apduInvokeID
        if _debug:
            ServerSSM._debug("    - invoke ID: %r", self.invokeID)

        # get the info about the client
        self.device_info = await self.ssmSAP.device_info_cache.get_device_info(
            self.pdu_address
        )
        if _debug:
            ServerSSM._debug("    - device_info: %r", self.device_info)

        # remember if the client accepts segmented responses
        self.segmented_response_accepted = apdu.apduSA

        # if there is a cache record, check to see if it needs to be updated
        if apdu.apduSA and self.device_info:
            if self.device_info.segmentation_supported == Segmentation.noSegmentation:
                if _debug:
                    ServerSSM._debug("    - client actually supports segmented receive")
                self.device_info.segmentation_supported = Segmentation.segmentedReceive

                if _debug:
                    ServerSSM._debug("    - tell the cache the info has been updated")
                self.ssmSAP.device_info_cache.update_device_info(self.device_info)

            elif (
                self.device_info.segmentation_supported == Segmentation.segmentedTransmit
            ):
                if _debug:
                    ServerSSM._debug(
                        "    - client actually supports both segmented transmit and receive"
                    )
                self.device_info.segmentation_supported = Segmentation.segmentedBoth

                if _debug:
                    ServerSSM._debug("    - tell the cache the info has been updated")
                self.ssmSAP.device_info_cache.update_device_info(self.device_info)

            elif (
                self.device_info.segmentation_supported == Segmentation.segmentedReceive
            ):
                pass

            elif self.device_info.segmentation_supported == Segmentation.segmentedBoth:
                pass

            else:
                raise RuntimeError("invalid segmentation supported in device info")

        # decode the maximum that the client can receive in one APDU, and if
        # there is a value in the device information then use that one because
        # it came from reading device object property value or from an I-Am
        # message that was received
        self.maxApduLengthAccepted = decode_max_apdu_length_accepted(apdu.apduMaxResp)
        if self.device_info and self.device_info.max_apdu_length_accepted is not None:
            if self.device_info.max_apdu_length_accepted < self.maxApduLengthAccepted:
                if _debug:
                    ServerSSM._debug("    - apduMaxResp encoding error")
            else:
                self.maxApduLengthAccepted = self.device_info.max_apdu_length_accepted
        if _debug:
            ServerSSM._debug(
                "    - maxApduLengthAccepted: %r", self.maxApduLengthAccepted
            )

        # save the number of segments the client is willing to accept in the ack,
        # if this is None then the value is unknown or more than 64
        self.maxSegmentsAccepted = decode_max_segments_accepted(apdu.apduMaxSegs)

        # unsegmented request
        if not apdu.apduSeg:
            self.set_state(AWAIT_RESPONSE, self.ssmSAP.applicationTimeout)
            await self.request(apdu)
            return

        # make sure we support segmented requests
        if self.segmentationSupported not in (
            Segmentation.segmentedReceive,
            Segmentation.segmentedBoth,
        ):
            abort = self.abort(AbortReason.segmentationNotSupported)
            await self.response(abort)
            return

        # save the request and set the segmentation context
        self.set_segmentation_context(apdu)

        # the window size is the minimum of what I would propose and what the
        # device has proposed
        self.actualWindowSize = min(apdu.apduWin, self.ssmSAP.proposedWindowSize)
        if _debug:
            ServerSSM._debug(
                "    - actualWindowSize? min(%r, %r) -> %r",
                apdu.apduWin,
                self.ssmSAP.proposedWindowSize,
                self.actualWindowSize,
            )

        # initialize the state
        self.lastSequenceNumber = 0
        self.initialSequenceNumber = 0
        self.set_state(SEGMENTED_REQUEST, self.segmentTimeout)

        # send back a segment ack
        segack = SegmentAckPDU(
            0, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize
        )
        if _debug:
            ServerSSM._debug("    - segAck: %r", segack)

        await self.response(segack)

    async def segmented_request(self, apdu):
        if _debug:
            ServerSSM._debug("segmented_request %r", apdu)

        # some kind of problem
        if apdu.apduType == AbortPDU.pduType:
            self.set_state(COMPLETED)
            await self.response(apdu)
            return

        # the only messages we should be getting are confirmed requests
        elif apdu.apduType != ConfirmedRequestPDU.pduType:
            abort = self.abort(AbortReason.invalidApduInThisState)
            await self.request(abort)  # send it to the device
            await self.response(abort)  # send it to the application
            return

        # it must be segmented
        elif not apdu.apduSeg:
            abort = self.abort(AbortReason.invalidApduInThisState)
            await self.request(abort)  # send it to the application
            await self.response(abort)  # send it to the device
            return

        # proper segment number
        if apdu.apduSeq != (self.lastSequenceNumber + 1) % 256:
            if _debug:
                ServerSSM._debug(
                    "    - segment %d received out of order, should be %d",
                    apdu.apduSeq,
                    (self.lastSequenceNumber + 1) % 256,
                )

            # segment received out of order
            self.restart_timer(self.segmentTimeout)

            # send back a segment ack
            segack = SegmentAckPDU(
                1, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize
            )

            await self.response(segack)
            return

        # add the data
        self.append_segment(apdu)

        # update the sequence number
        self.lastSequenceNumber = (self.lastSequenceNumber + 1) % 256

        # last segment?
        if not apdu.apduMor:
            if _debug:
                ServerSSM._debug("    - no more follows")

            # send back a final segment ack
            segack = SegmentAckPDU(
                0, 1, self.invokeID, self.lastSequenceNumber, self.actualWindowSize
            )
            await self.response(segack)

            # forward the whole thing to the application
            self.set_state(AWAIT_RESPONSE, self.ssmSAP.applicationTimeout)
            await self.request(self.segmentAPDU)

        elif apdu.apduSeq == (
            (self.initialSequenceNumber + self.actualWindowSize) % 256
        ):
            if _debug:
                ServerSSM._debug("    - last segment in the group")

            self.initialSequenceNumber = self.lastSequenceNumber
            self.restart_timer(self.segmentTimeout)

            # send back a segment ack
            segack = SegmentAckPDU(
                0, 1, self.invokeID, self.initialSequenceNumber, self.actualWindowSize
            )
            await self.response(segack)

        else:
            # wait for more segments
            if _debug:
                ServerSSM._debug("    - wait for more segments")

            self.restart_timer(self.segmentTimeout)

    async def segmented_request_timeout(self):
        if _debug:
            ServerSSM._debug("segmented_request_timeout")

        # give up
        self.set_state(ABORTED)

    async def await_response(self, apdu):
        if _debug:
            ServerSSM._debug("await_response %r", apdu)

        if isinstance(apdu, ConfirmedRequestPDU):
            if _debug:
                ServerSSM._debug("    - client is trying this request again")

        elif isinstance(apdu, AbortPDU):
            if _debug:
                ServerSSM._debug("    - client aborting this request")

            # forward abort to the application
            self.set_state(ABORTED)
            await self.request(apdu)

        else:
            raise RuntimeError("invalid APDU (6)")

    async def await_response_timeout(self):
        """This function is called when the application has taken too long
        to respond to a clients request.  The client has probably long since
        given up."""
        if _debug:
            ServerSSM._debug("await_response_timeout")

        abort = self.abort(AbortReason.serverTimeout)
        await self.request(abort)

    async def segmented_response(self, apdu):
        if _debug:
            ServerSSM._debug("segmented_response %r", apdu)

        # client is ready for the next segment
        if apdu.apduType == SegmentAckPDU.pduType:
            if _debug:
                ServerSSM._debug("    - segment ack")

            # actual window size is provided by client
            self.actualWindowSize = apdu.apduWin

            # duplicate ack received?
            if not self.in_window(apdu.apduSeq, self.initialSequenceNumber):
                if _debug:
                    ServerSSM._debug("    - not in window")
                self.restart_timer(self.segmentTimeout)

            # final ack received?
            elif self.sentAllSegments:
                if _debug:
                    ServerSSM._debug("    - all done sending response")
                self.set_state(COMPLETED)

            else:
                if _debug:
                    ServerSSM._debug("    - more segments to send")

                self.initialSequenceNumber = (apdu.apduSeq + 1) % 256
                self.actualWindowSize = apdu.apduWin
                self.segmentRetryCount = 0
                await self.fill_window(self.initialSequenceNumber)
                self.restart_timer(self.segmentTimeout)

        # some kind of problem
        elif apdu.apduType == AbortPDU.pduType:
            self.set_state(COMPLETED)
            await self.response(apdu)

        else:
            raise RuntimeError("invalid APDU (7)")

    async def segmented_response_timeout(self):
        if _debug:
            ServerSSM._debug("segmented_response_timeout")

        # try again
        if self.segmentRetryCount < self.numberOfApduRetries:
            self.segmentRetryCount += 1
            self.start_timer(self.segmentTimeout)
            await self.fill_window(self.initialSequenceNumber)
        else:
            # give up
            self.set_state(ABORTED)


#
#   ApplicationServiceAccessPoint
#


@bacpypes_debugging
class ApplicationServiceAccessPoint(Client[PDU], ServiceAccessPoint):
    _debug: Callable[..., None]

    clientTransactions: List[ClientSSM]
    serverTransactions: List[ServerSSM]

    def __init__(
        self, device_object=None, device_info_cache=None, sap=None, cid=None
    ) -> None:
        if _debug:
            ApplicationServiceAccessPoint._debug(
                "__init__ device_object=%r device_info_cache=%r sap=%r cid=%r",
                device_object,
                device_info_cache,
                sap,
                cid,
            )

        # basic initialization
        Client.__init__(self, cid)
        ServiceAccessPoint.__init__(self, sap)

        # save a reference to the device object for segmentation settings
        # and the device information cache for peer settings
        self.device_object = device_object
        self.device_info_cache = device_info_cache

        # running state machines
        self.clientTransactions = []
        self.serverTransactions = []

        # confirmed request defaults
        self.numberOfApduRetries = 3
        self.apduTimeout = 3000
        self.maxApduLengthAccepted = 1024

        # segmentation defaults
        self.segmentationSupported = Segmentation.noSegmentation
        self.segmentTimeout = 1500
        self.maxSegmentsAccepted = 2
        self.proposedWindowSize = 2

        # device communication control
        self.dccEnableDisable = "enable"

        # how long the state machine is willing to wait for the application
        # layer to form a response and send it
        self.applicationTimeout = 3000

    async def request(self, apdu: APDU) -> None:
        """
        Packets going down the stack are APDUs but to be delivered to the
        network layer they need to be encoded as generic PDUs first.
        """
        if _debug:
            ApplicationServiceAccessPoint._debug("request %r", apdu)

        # APDU needs to be encoded first
        pdu: PDU = apdu.encode()
        if _debug:
            ApplicationServiceAccessPoint._debug("    - pdu: %r", pdu)

        # now it can go
        await Client.request(self, pdu)

    async def confirmation(self, pdu: PDU) -> None:
        """
        Packets coming up the stack are PDUs.  First decode them as one
        of the generic APDUs.  If it is an unconfirmed request deliver it
        directly to the application, otherwise it may associated with an
        existing client or server segmentation state machine, or if it is
        a new incoming request, make a new ServerSSM to track it.
        """
        if _debug:
            ApplicationServiceAccessPoint._debug("confirmation %r", pdu)

        # decode it as an APDU
        apdu = APDU.decode(pdu)
        if _debug:
            ApplicationServiceAccessPoint._debug("    - apdu: %r", apdu)

        # check device communication control
        if self.dccEnableDisable == "enable":
            if _debug:
                ApplicationServiceAccessPoint._debug("    - communications enabled")
        elif self.dccEnableDisable == "disable":
            if (pdu.apduType == 0) and (pdu.apduService == 17):
                if _debug:
                    ApplicationServiceAccessPoint._debug(
                        "    - continue with DCC request"
                    )
            elif (pdu.apduType == 0) and (pdu.apduService == 20):
                if _debug:
                    ApplicationServiceAccessPoint._debug(
                        "    - continue with reinitialize device"
                    )
            elif (pdu.apduType == 1) and (pdu.apduService == 8):
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - continue with Who-Is")
            else:
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - not a Who-Is, dropped")
                return
        elif self.dccEnableDisable == "disableInitiation":
            if _debug:
                ApplicationServiceAccessPoint._debug("    - initiation disabled")

        # confirmed requests need a ServerSSM
        if isinstance(apdu, ConfirmedRequestPDU):
            # find duplicates of this request
            for tr in self.serverTransactions:
                if (apdu.apduInvokeID == tr.invokeID) and (
                    apdu.pduSource == tr.pdu_address
                ):
                    break
            else:
                # build a server transaction
                tr = ServerSSM(self, apdu.pduSource)

                # add it to our transactions to track it
                self.serverTransactions.append(tr)

            # let it run with the apdu
            await tr.indication(apdu)

        elif isinstance(apdu, UnconfirmedRequestPDU):
            # decode this now, the APDU is complete
            try:
                apdu = APCISequence.decode(apdu)
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - apdu: %r", apdu)
            except AttributeError as err:
                if _debug:
                    ApplicationServiceAccessPoint._debug(
                        "    - decoding error: %r", err
                    )
                return

            # deliver directly to the application
            await self.sap_request(apdu)

        elif (
            isinstance(apdu, SimpleAckPDU)
            or isinstance(apdu, ComplexAckPDU)
            or isinstance(apdu, ErrorPDU)
            or isinstance(apdu, RejectPDU)
        ):
            # find the client transaction this is acking
            for tr in self.clientTransactions:
                if (apdu.apduInvokeID == tr.invokeID) and (
                    apdu.pduSource == tr.pdu_address
                ):
                    break
            else:
                return

            # send the packet on to the transaction
            await tr.confirmation(apdu)

        elif isinstance(apdu, AbortPDU):
            # find the transaction being aborted
            if apdu.apduSrv:
                for tr in self.clientTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (
                        apdu.pduSource == tr.pdu_address
                    ):
                        break
                else:
                    return

                # send the packet on to the transaction
                await tr.confirmation(apdu)
            else:
                for tr in self.serverTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (
                        apdu.pduSource == tr.pdu_address
                    ):
                        break
                else:
                    return

                # send the packet on to the transaction
                await tr.indication(apdu)

        elif isinstance(apdu, SegmentAckPDU):
            # find the transaction being aborted
            if apdu.apduSrv:
                for tr in self.clientTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (
                        apdu.pduSource == tr.pdu_address
                    ):
                        break
                else:
                    return

                # send the packet on to the transaction
                await tr.confirmation(apdu)
            else:
                for tr in self.serverTransactions:
                    if (apdu.apduInvokeID == tr.invokeID) and (
                        apdu.pduSource == tr.pdu_address
                    ):
                        break
                else:
                    return

                # send the packet on to the transaction
                await tr.indication(apdu)

        else:
            raise RuntimeError("invalid APDU (8): {type(apdu)}")

    async def sap_indication(self, apdu: APDU) -> None:
        """
        This function is called when the application is requesting a new
        transaction as a client.
        """
        if _debug:
            ApplicationServiceAccessPoint._debug("sap_indication %r", apdu)

        # check device communication control
        if self.dccEnableDisable == "enable":
            if _debug:
                ApplicationServiceAccessPoint._debug("    - communications enabled")

        elif self.dccEnableDisable == "disable":
            if _debug:
                ApplicationServiceAccessPoint._debug("    - communications disabled")
            return

        elif self.dccEnableDisable == "disableInitiation":
            if _debug:
                ApplicationServiceAccessPoint._debug("    - initiation disabled")

            if (apdu.apduType == 1) and (apdu.apduService == 0):
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - continue with I-Am")
            else:
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - not an I-Am")
                return

        # if this is a complex message, encode it as a generic
        # version before passing it to the ClientSSM
        if isinstance(apdu, APCISequence):
            apdu = apdu.encode()
            if _debug:
                ApplicationServiceAccessPoint._debug("    - encoded apdu: %r", apdu)

        if isinstance(apdu, UnconfirmedRequestPDU):
            # no need for a state machine, deliver to the device
            try:
                await self.request(apdu)
            except CommuncationError as err:
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - error ignored: %r", err)

        elif isinstance(apdu, ConfirmedRequestPDU):
            # warning for bogus requests
            if (apdu.pduDestination.addrType != Address.localStationAddr) and (
                apdu.pduDestination.addrType != Address.remoteStationAddr
            ):
                ApplicationServiceAccessPoint._warning(
                    "%s is not a local or remote station", apdu.pduDestination
                )

            # create a client transaction state machine
            tr = ClientSSM(self, apdu.pduDestination)
            if _debug:
                ApplicationServiceAccessPoint._debug(
                    "    - client segmentation state machine: %r", tr
                )

            # add it to our transactions to track it
            self.clientTransactions.append(tr)

            # let it run
            await tr.indication(apdu)

        else:
            raise RuntimeError("invalid APDU (9): {type(apdu)}")

    async def sap_response(self, apdu: APDU) -> None:
        """
        This function is called when the state machine has finished with
        a transaction and is sending the results back to the client.
        """
        if _debug:
            ApplicationServiceAccessPoint._debug("sap_response %r", apdu)

        if isinstance(apdu, SimpleAckPDU):
            xpdu = apdu

        elif isinstance(
            apdu, (UnconfirmedRequestPDU, ConfirmedRequestPDU, ComplexAckPDU, ErrorPDU)
        ):
            # if this is a complex type, decode it first
            try:
                xpdu = APCISequence.decode(apdu)
            except Exception as err:
                # might be lots of other decoding errors
                if _debug:
                    ApplicationServiceAccessPoint._debug(
                        "    - decoding error: %r", err
                    )

                # drop requests that aren't encoded correctly
                if isinstance(apdu, UnconfirmedRequestPDU):
                    return
                ###TODO there should be an error going back to the client
                if isinstance(apdu, ConfirmedRequestPDU):
                    return

                xpdu = Error(
                    service_choice=apdu.service_choice,
                    errorClass="communication",
                    errorCode="invalid-tag",
                )

        elif isinstance(apdu, (RejectPDU, AbortPDU)):
            xpdu = apdu

        else:
            raise RuntimeError(f"invalid APDU (10): {type(apdu)}")

        # continue along
        await ServiceAccessPoint.sap_response(self, xpdu)

    async def sap_confirmation(self, apdu: APDU) -> None:
        """
        This function is called when the application is responding to a request,
        the apdu may be a simple ack, complex ack, error, reject or abort.
        """
        if _debug:
            ApplicationServiceAccessPoint._debug("sap_confirmation %r", apdu)

        if isinstance(
            apdu, (SimpleAckPDU, ComplexAckPDU, ErrorPDU, RejectPDU, AbortPDU)
        ):
            # if this is a complex message, encode it as a generic
            # version before passing it to the ServerSSM
            if isinstance(apdu, APCISequence):
                apdu = apdu.encode()
                if _debug:
                    ApplicationServiceAccessPoint._debug("    - encoded apdu: %r", apdu)

            # find the appropriate server transaction
            for tr in self.serverTransactions:
                if (apdu.apduInvokeID == tr.invokeID) and (
                    apdu.pduDestination == tr.pdu_address
                ):
                    break
            else:
                return

            # pass control to the transaction
            await tr.confirmation(apdu)

        else:
            raise RuntimeError("invalid APDU (11): {type(apdu)}")
