"""
Application Layer Protocol Data Units
"""

from __future__ import annotations

from typing import Callable, Tuple, cast

from .errors import DecodingError, TooManyArguments
from .debugging import ModuleLogger, DebugContents, bacpypes_debugging

from .pdu import PCI, PDUData, PDU
from .primitivedata import (
    Boolean,
    CharacterString,
    Enumerated,
    Integer,
    ObjectIdentifier,
    OctetString,
    Real,
    TagList,
    Unsigned,
)
from .constructeddata import (
    Any,
    Sequence,
    SequenceOf,
    SequenceOfAny,
)
from .basetypes import (
    AtomicReadFileACKAccessMethodChoice,
    AtomicReadFileRequestAccessMethodChoice,
    AtomicWriteFileRequestAccessMethodChoice,
    ConfirmedTextMessageRequestMessageClass,
    ConfirmedTextMessageRequestMessagePriority,
    CreateObjectRequestObjectSpecifier,
    DateTime,
    DeviceAddress,
    DeviceCommunicationControlRequestEnableDisable,
    ErrorClass,
    ErrorCode,
    ErrorType,
    EventState,
    EventType,
    GetAlarmSummaryAlarmSummary,
    GetEnrollmentSummaryEnrollmentSummary,
    GetEnrollmentSummaryRequestAcknowledgmentFilterType,
    GetEnrollmentSummaryRequestEventStateFilterType,
    GetEnrollmentSummaryRequestPriorityFilterType,
    GetEventInformationEventSummary,
    GroupChannelValue,
    LifeSafetyOperation,
    NotificationParameters,
    NotifyType,
    ObjectPropertyReference,
    PropertyIdentifier,
    PropertyReference,
    PropertyValue,
    Range,
    ReadAccessResult,
    ReadAccessSpecification,
    RecipientProcess,
    ReinitializeDeviceRequestReinitializedStateOfDevice,
    ResultFlags,
    Segmentation,
    TimeStamp,
    UnconfirmedTextMessageRequestMessageClass,
    UnconfirmedTextMessageRequestMessagePriority,
    VTClass,
    WhoHasLimits,
    WhoHasObject,
    WriteAccessSpecification,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# a dictionary of message type values and classes
apdu_types = {}


def register_apdu_type(class_):
    apdu_types[class_.pduType] = class_
    return class_


# a dictionary of confirmed request choices and classes
confirmed_request_types = {}


def register_confirmed_request_type(class_):
    confirmed_request_types[class_.service_choice] = class_
    return class_


# a dictionary of complex ack choices and classes
complex_ack_types = {}


def register_complex_ack_type(class_):
    complex_ack_types[class_.service_choice] = class_
    return class_


# a dictionary of unconfirmed request choices and classes
unconfirmed_request_types = {}


def register_unconfirmed_request_type(class_):
    unconfirmed_request_types[class_.service_choice] = class_
    return class_


# a dictionary of unconfirmed request choices and classes
error_types = {}


def register_error_type(class_):
    error_types[class_.service_choice] = class_
    return class_


class AbortReason(Enumerated):
    _vendor_range = (64, 255)
    other = 0
    bufferOverflow = 1
    invalidApduInThisState = 2
    preemptedByHigherPriorityTask = 3
    segmentationNotSupported = 4
    securityError = 5
    insufficientSecurity = 6
    windowSizeOutOfRange = 7
    applicationExceededReplyTime = 8
    outOfResources = 9
    tsmTimeout = 10
    apduTooLong = 11
    serverTimeout = 64
    noResponse = 65


class RejectReason(Enumerated):
    _vendor_range = (64, 255)
    other = 0
    bufferOverflow = 1
    inconsistentParameters = 2
    invalidParameterDatatype = 3
    invalidTag = 4
    missingRequiredParameter = 5
    parameterOutOfRange = 6
    tooManyArguments = 7
    undefinedEnumeration = 8
    unrecognizedService = 9


#
#   encode_max_segments_accepted/decode_max_segments_accepted
#

_max_segments_accepted_encoding = [
    None,
    2,
    4,
    8,
    16,
    32,
    64,
    None,
]


def encode_max_segments_accepted(arg):
    """Encode the maximum number of segments the device will accept, Section
    20.1.2.4, and if the device says it can only accept one segment it shouldn't
    say that it supports segmentation!"""
    # unspecified
    if not arg:
        return 0

    if arg > 64:
        return 7

    # the largest number not greater than the arg
    for i in range(6, 0, -1):
        if _max_segments_accepted_encoding[i] <= arg:
            return i

    raise ValueError("invalid max max segments accepted: {0}".format(arg))


def decode_max_segments_accepted(arg):
    """Decode the maximum number of segments the device will accept, Section
    20.1.2.4"""
    return _max_segments_accepted_encoding[arg]


#
#   encode_max_apdu_length_accepted/decode_max_apdu_length_accepted
#

_max_apdu_length_encoding = [
    50,
    128,
    206,
    480,
    1024,
    1476,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
]


def encode_max_apdu_length_accepted(arg):
    """Return the encoding of the highest encodable value less than the
    value of the arg."""
    for i in range(5, -1, -1):
        if arg >= _max_apdu_length_encoding[i]:
            return i

    raise ValueError("invalid max APDU length accepted: {0}".format(arg))


def decode_max_apdu_length_accepted(arg):
    v = _max_apdu_length_encoding[arg]
    if not v:
        raise ValueError("invalid max APDU length accepted: {0}".format(arg))

    return v


#
#   APCI
#


@bacpypes_debugging
class APCI(PCI):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "apduType",
        "apduSeg",
        "apduMor",
        "apduSA",
        "apduSrv",
        "apduNak",
        "apduSeq",
        "apduWin",
        "apduMaxSegs",
        "apduMaxResp",
        "apduService",
        "apduInvokeID",
        "apduAbortRejectReason",
    )
    apduType: int
    apduSeg: int  # segmented
    apduMor: int  # more follows
    apduSA: int  # segmented response accepted
    apduSrv: int  # sent by server
    apduNak: int  # negative acknowledgement
    apduSeq: int  # sequence number
    apduWin: int  # actual/proposed window size
    apduMaxSegs: int  # maximum segments accepted (decoded)
    apduMaxResp: int  # max response accepted (decoded)
    apduService: int  # service choice
    apduInvokeID: int  # invoke identifier
    apduAbortRejectReason: int  # abort/reject reason code

    def __init__(self, *args, **kwargs):
        if _debug:
            APCI._debug("__init__ %r %r", args, kwargs)
        PCI.__init__(self, *args, **kwargs)

    def update(self, apci: APCI) -> None:  # type: ignore[override]
        if _debug:
            APCI._debug("update %r", apci)

        PCI.update(self, apci)

        # skip over fields that aren't set
        for k in APCI._debug_contents:
            if hasattr(apci, k):
                setattr(self, k, getattr(apci, k))

    def __repr__(self) -> str:
        """Return a string representation of the PDU."""
        # start with the class name
        sname = self.__module__ + "." + self.__class__.__name__

        # expand the type if possible
        stype = apdu_types.get(self.apduType, None)
        if stype:
            stype = stype.__name__
        else:
            stype = "?"

        # add the invoke ID if it has one
        if hasattr(self, "apduInvokeID"):
            stype += "," + str(self.apduInvokeID)

        # put it together
        return "<{0}({1}) instance at {2}>".format(sname, stype, hex(id(self)))

    def encode(self) -> PDU:
        """encode the contents of the APCI into a PDU."""
        if _debug:
            APCI._debug("encode")

        # create a PDU and save the PCI contents
        pdu = PDU()
        PCI.update(pdu, self)

        # branch on the APDU type
        if self.apduType == ConfirmedRequestPDU.pduType:
            # PDU type
            buff = self.apduType << 4
            if self.apduSeg:
                buff += 0x08
            if self.apduMor:
                buff += 0x04
            if self.apduSA:
                buff += 0x02
            pdu.put(buff)
            pdu.put((self.apduMaxSegs << 4) + self.apduMaxResp)
            pdu.put(self.apduInvokeID)
            if self.apduSeg:
                pdu.put(self.apduSeq)
                pdu.put(self.apduWin)
            pdu.put(self.apduService)

        elif self.apduType == UnconfirmedRequestPDU.pduType:
            pdu.put(self.apduType << 4)
            pdu.put(self.apduService)

        elif self.apduType == SimpleAckPDU.pduType:
            pdu.put(self.apduType << 4)
            pdu.put(self.apduInvokeID)
            pdu.put(self.apduService)

        elif self.apduType == ComplexAckPDU.pduType:
            # PDU type
            buff = self.apduType << 4
            if self.apduSeg:
                buff += 0x08
            if self.apduMor:
                buff += 0x04
            pdu.put(buff)
            pdu.put(self.apduInvokeID)
            if self.apduSeg:
                pdu.put(self.apduSeq)
                pdu.put(self.apduWin)
            pdu.put(self.apduService)

        elif self.apduType == SegmentAckPDU.pduType:
            # PDU type
            buff = self.apduType << 4
            if self.apduNak:
                buff += 0x02
            if self.apduSrv:
                buff += 0x01
            pdu.put(buff)
            pdu.put(self.apduInvokeID)
            pdu.put(self.apduSeq)
            pdu.put(self.apduWin)

        elif self.apduType == ErrorPDU.pduType:
            pdu.put(self.apduType << 4)
            pdu.put(self.apduInvokeID)
            pdu.put(self.apduService)

        elif self.apduType == RejectPDU.pduType:
            pdu.put(self.apduType << 4)
            pdu.put(self.apduInvokeID)
            pdu.put(self.apduAbortRejectReason)

        elif self.apduType == AbortPDU.pduType:
            # PDU type
            buff = self.apduType << 4
            if self.apduSrv:
                buff += 0x01
            pdu.put(buff)
            pdu.put(self.apduInvokeID)
            pdu.put(self.apduAbortRejectReason)

        else:
            raise ValueError("invalid APCI.apduType")
        if _debug:
            APCI._debug("    - pdu: %r", pdu)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> APCI:
        """decode the contents of the PDU and return an APCI."""
        if _debug:
            APCI._debug("decode %r", pdu)

        apci = APCI()
        PCI.update(apci, pdu)

        # decode the first octet
        buff = pdu.get()

        # decode the APCI type
        apci.apduType = (buff >> 4) & 0x0F

        if apci.apduType == ConfirmedRequestPDU.pduType:
            apci.apduSeg = (buff & 0x08) != 0
            apci.apduMor = (buff & 0x04) != 0
            apci.apduSA = (buff & 0x02) != 0
            buff = pdu.get()
            apci.apduMaxSegs = (buff >> 4) & 0x07
            apci.apduMaxResp = buff & 0x0F
            apci.apduInvokeID = pdu.get()
            if apci.apduSeg:
                apci.apduSeq = pdu.get()
                apci.apduWin = pdu.get()
            apci.apduService = pdu.get()

        elif apci.apduType == UnconfirmedRequestPDU.pduType:
            apci.apduService = pdu.get()

        elif apci.apduType == SimpleAckPDU.pduType:
            apci.apduInvokeID = pdu.get()
            apci.apduService = pdu.get()

        elif apci.apduType == ComplexAckPDU.pduType:
            apci.apduSeg = (buff & 0x08) != 0
            apci.apduMor = (buff & 0x04) != 0
            apci.apduInvokeID = pdu.get()
            if apci.apduSeg:
                apci.apduSeq = pdu.get()
                apci.apduWin = pdu.get()
            apci.apduService = pdu.get()

        elif apci.apduType == SegmentAckPDU.pduType:
            apci.apduNak = (buff & 0x02) != 0
            apci.apduSrv = (buff & 0x01) != 0
            apci.apduInvokeID = pdu.get()
            apci.apduSeq = pdu.get()
            apci.apduWin = pdu.get()

        elif apci.apduType == ErrorPDU.pduType:
            apci.apduInvokeID = pdu.get()
            apci.apduService = pdu.get()

        elif apci.apduType == RejectPDU.pduType:
            apci.apduInvokeID = pdu.get()
            apci.apduAbortRejectReason = RejectReason(pdu.get())

        elif apci.apduType == AbortPDU.pduType:
            apci.apduSrv = (buff & 0x01) != 0
            apci.apduInvokeID = pdu.get()
            apci.apduAbortRejectReason = AbortReason(pdu.get())

        else:
            raise DecodingError("invalid APDU type")

        return apci

    def apci_contents(self, use_dict=None, as_class=dict) -> dict:
        """Return the contents of an object as a dict."""
        if _debug:
            APCI._debug("apci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # fill in the PCI contents
        PCI.pci_contents(self, use_dict=use_dict, as_class=as_class)

        # loop through the elements
        for attr in APCI._debug_contents:
            value = getattr(self, attr, None)
            if value is None:
                continue

            if attr == "apduType":
                mapped_value = apdu_types[self.apduType].__name__
            elif attr == "apduService":
                if self.apduType in (
                    ConfirmedRequestPDU.pduType,
                    SimpleAckPDU.pduType,
                    ComplexAckPDU.pduType,
                ):
                    mapped_value = confirmed_request_types[self.apduService].__name__
                elif self.apduType == UnconfirmedRequestPDU.pduType:
                    mapped_value = unconfirmed_request_types[self.apduService].__name__
                elif self.apduType == ErrorPDU.pduType:
                    mapped_value = error_types[self.apduService].__name__
            else:
                mapped_value = value

            # save the mapped value
            use_dict.__setitem__(attr, mapped_value)

        # return what we built/updated
        return use_dict


#
#   APDU
#


@bacpypes_debugging
class APDU(APCI, PDUData):
    def __init__(self, *args, **kwargs):
        if _debug:
            APDU._debug("__init__ %r %r", args, kwargs)
        APCI.__init__(self, **kwargs)
        PDUData.__init__(self, *args)

    def set_context(self, context):
        """
        This function is called to set the PCI fields to be the response (simple
        ack, complex ack, error, or reject) of a confirmed service request.
        """
        if _debug:
            APDU._debug("set_context %r", context)

        self.pduUserData = context.pduUserData
        self.pduDestination = context.pduSource
        self.pduExpectingReply = False
        self.pduNetworkPriority = context.pduNetworkPriority
        self.apduInvokeID = context.apduInvokeID

    def encode(self) -> PDU:
        if _debug:
            APDU._debug("encode")

        # encode the header
        pdu = APCI.encode(self)
        PCI.update(pdu, self)
        pdu.put_data(self.pduData)
        if _debug:
            APDU._debug("    - pdu: %r", pdu)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> APDU:
        if _debug:
            APDU._debug("decode %r %r", class_, pdu)

        # decode the header
        apci = APCI.decode(pdu)
        if _debug:
            APDU._debug("    - apci: %r", apci)

        # find the appropriate APDU subclass
        try:
            apdu_class = apdu_types[apci.apduType]
        except KeyError:
            raise RuntimeError(f"unrecognized APDU type: {apci.apduType}")
        if _debug:
            APDU._debug("    - apdu_class: %r", apdu_class)

        # create an APDU
        apdu = apdu_class()
        APCI.update(apdu, apci)
        apdu.put_data(pdu.pduData)

        return apdu

    def apdu_contents(self, use_dict=None, as_class=dict) -> dict:
        return PDUData.pdudata_contents(self, use_dict=use_dict, as_class=as_class)

    def dict_contents(self, use_dict=None, as_class=dict) -> dict:
        """Return the contents of an object as a dict."""
        if _debug:
            APDU._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the parent classes
        self.apci_contents(use_dict=use_dict, as_class=as_class)
        self.apdu_contents(use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict

    debug_contents = DebugContents.debug_contents  # type: ignore[assignment]


#
#   ConfirmedRequestPDU
#


class ConfirmedServiceChoice(Enumerated):
    acknowledgeAlarm = 0
    addListElement = 8
    atomicReadFile = 6
    atomicWriteFile = 7
    auditLogQuery = 33
    authenticate = 24  ###TODO
    confirmedAuditNotification = 32
    confirmedCOVNotification = 1
    confirmedCOVNotificationMultiple = 31  ###TODO
    confirmedEventNotification = 2
    confirmedPrivateTransfer = 18
    confirmedTextMessage = 19
    createObject = 10
    deleteObject = 11
    deviceCommunicationControl = 17
    getAlarmSummary = 3
    getEnrollmentSummary = 4
    getEventInformation = 29  ###TODO
    lifeSafetyOperation = 27  ###TODO
    readProperty = 12
    readPropertyMultiple = 14
    readPropertyConditional = 13  ###TODO
    readRange = 26  ###TODO
    reinitializeDevice = 20
    removeListElement = 9
    requestKey = 25  ###TODO
    subscribeCOV = 5
    subscribeCOVProperty = 28
    subscribeCOVPropertyMultiple = 30  ###TODO
    vtClose = 22
    vtData = 23
    vtOpen = 21
    writeProperty = 15
    writePropertyMultiple = 16


@bacpypes_debugging
@register_apdu_type
class ConfirmedRequestPDU(APDU):
    pduType = 0

    def __init__(self, service_choice=None, invoke_id=None, *args, **kwargs):
        if _debug:
            ConfirmedRequestPDU._debug(
                "__init__ %r %r %r", service_choice, args, kwargs
            )
        APDU.__init__(self, *args, **kwargs)

        self.pduExpectingReply = True

        self.apduType = ConfirmedRequestPDU.pduType
        self.apduService = service_choice
        self.apduInvokeID = invoke_id


#
#   UnconfirmedRequestPDU
#


class UnconfirmedServiceChoice(Enumerated):
    iAm = 0
    iHave = 1
    unconfirmedCOVNotification = 2
    unconfirmedEventNotification = 3
    unconfirmedPrivateTransfer = 4
    unconfirmedTextMessage = 5
    timeSynchronization = 6
    whoHas = 7
    whoIs = 8
    utcTimeSynchronization = 9
    writeGroup = 10
    unconfirmedCOVNotificationMultiple = 11  ###TODO
    unconfirmedAuditNotification = 12  ###TODO
    whoIAm = 13  ###TODO
    youAre = 14  ###TODO


@bacpypes_debugging
@register_apdu_type
class UnconfirmedRequestPDU(APDU):
    pduType = 1

    def __init__(self, service_choice=None, *args, **kwargs):
        if _debug:
            UnconfirmedRequestPDU._debug(
                "__init__ %r %r %r", service_choice, args, kwargs
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = UnconfirmedRequestPDU.pduType
        self.apduService = service_choice


#
#   SimpleAckPDU
#


@bacpypes_debugging
@register_apdu_type
class SimpleAckPDU(APDU):
    pduType = 2

    def __init__(
        self, service_choice=None, invoke_id=None, context=None, *args, **kwargs
    ):
        if _debug:
            SimpleAckPDU._debug(
                "__init__ %r %r %r %r %r",
                service_choice,
                invoke_id,
                context,
                args,
                kwargs,
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = SimpleAckPDU.pduType
        self.apduService = service_choice
        self.apduInvokeID = invoke_id

        # use the context to fill in most of the fields
        if context is not None:
            self.apduService = context.apduService
            self.set_context(context)


#
#   ComplexAckPDU
#


@bacpypes_debugging
@register_apdu_type
class ComplexAckPDU(APDU):
    pduType = 3

    def __init__(
        self, service_choice=None, invoke_id=None, context=None, *args, **kwargs
    ):
        if _debug:
            ComplexAckPDU._debug(
                "__init__ %r %r %r %r %r",
                service_choice,
                invoke_id,
                context,
                args,
                kwargs,
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = ComplexAckPDU.pduType
        self.apduService = service_choice
        self.apduInvokeID = invoke_id

        # use the context to fill in most of the fields
        if context is not None:
            self.apduService = context.apduService
            self.set_context(context)


#
#   SegmentAckPDU
#


@bacpypes_debugging
@register_apdu_type
class SegmentAckPDU(APDU):
    pduType = 4

    def __init__(
        self,
        nak=None,
        srv=None,
        invoke_id=None,
        sequenceNumber=None,
        windowSize=None,
        *args,
        **kwargs,
    ):
        if _debug:
            SegmentAckPDU._debug(
                "__init__ %r %r %r %r %r %r %r",
                nak,
                srv,
                invoke_id,
                sequenceNumber,
                windowSize,
                args,
                kwargs,
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = SegmentAckPDU.pduType
        self.apduNak = nak
        self.apduSrv = srv
        self.apduInvokeID = invoke_id
        self.apduSeq = sequenceNumber
        self.apduWin = windowSize


#
#   ErrorRejectAbortNack
#


class ErrorRejectAbortNack(BaseException):
    """This is a pure virtual class inherited by ErrorPDU, RejectPDU, and
    AbortPDU to make it easier for application layer services to treat them
    all the same.
    """

    @property
    def reason(self) -> int:
        if isinstance(self, ErrorPDU):
            return self.errorCode  # type: ignore[attr-defined]
        elif isinstance(self, (RejectPDU, AbortPDU)):
            return self.apduAbortRejectReason
        else:
            raise TypeError("must be an ErrorPDU, RejectPDU or AbortPDU")

    def __str__(self) -> str:
        return str(self.reason)


#
#   ErrorPDU
#


@bacpypes_debugging
@register_apdu_type
class ErrorPDU(APDU, ErrorRejectAbortNack):
    pduType = 5

    def __init__(
        self, service_choice=None, invoke_id=None, context=None, *args, **kwargs
    ):
        if _debug:
            ErrorPDU._debug(
                "__init__ %r %r %r %r %r",
                service_choice,
                invoke_id,
                context,
                args,
                kwargs,
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = ErrorPDU.pduType
        self.apduService = service_choice
        self.apduInvokeID = invoke_id

        # use the context to fill in most of the fields
        if context is not None:
            self.apduService = context.apduService
            self.set_context(context)


#
#   RejectPDU
#


@bacpypes_debugging
@register_apdu_type
class RejectPDU(APDU, ErrorRejectAbortNack):
    pduType = 6

    def __init__(self, invoke_id=None, reason=None, context=None, *args, **kwargs):
        if _debug:
            RejectPDU._debug(
                "__init__ %r %r %r %r %r", invoke_id, reason, context, args, kwargs
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = RejectPDU.pduType
        self.apduInvokeID = invoke_id
        if isinstance(reason, (int, str)):
            reason = RejectReason(reason)
        self.apduAbortRejectReason = reason

        # use the context to fill in most of the fields
        if context is not None:
            self.set_context(context)


#
#   AbortPDU
#


@bacpypes_debugging
@register_apdu_type
class AbortPDU(APDU, ErrorRejectAbortNack):
    pduType = 7

    def __init__(
        self, srv=None, invoke_id=None, reason=None, context=None, *args, **kwargs
    ):
        if _debug:
            AbortPDU._debug(
                "__init__ %r %r %r %r %r %r",
                srv,
                invoke_id,
                reason,
                context,
                args,
                kwargs,
            )
        APDU.__init__(self, *args, **kwargs)

        self.apduType = AbortPDU.pduType
        self.apduSrv = srv
        self.apduInvokeID = invoke_id
        if isinstance(reason, (int, str)):
            reason = AbortReason(reason)
        self.apduAbortRejectReason = reason

        # use the context to fill in most of the fields
        if context is not None:
            self.set_context(context)


#
#   APCISequence
#


@bacpypes_debugging
class APCISequence(APCI, Sequence):
    def __init__(self, **kwargs) -> None:
        if _debug:
            APCISequence._debug("__init__ %r", kwargs)

        # note that the APCI.__init__() has already been called
        # pass the rest of the kwargs to the sequence
        Sequence.__init__(self, **kwargs)

    def encode(self) -> APDU:  # type: ignore[override]
        if _debug:
            APCISequence._debug("encode")

        # create a tag list
        tag_list: TagList = Sequence.encode(self)
        if _debug:
            APCISequence._debug("    - tag_list: %r", tag_list)
            for i, t in enumerate(tag_list):
                APCISequence._debug("        [%r]: %r", i, t)

        # encode the tag list
        pdu_data = tag_list.encode()
        if _debug:
            APCISequence._debug("    - pdu_data: %r", pdu_data)

        # create an APDU, copy the header fields
        apdu: APDU
        if isinstance(self, ConfirmedRequestPDU):
            apdu = ConfirmedRequestPDU()
        elif isinstance(self, ComplexAckPDU):
            apdu = ComplexAckPDU()
        elif isinstance(self, UnconfirmedRequestPDU):
            apdu = UnconfirmedRequestPDU()
        elif isinstance(self, ErrorPDU):
            apdu = ErrorPDU()

        apdu.update(self)
        apdu.put_data(pdu_data.pduData)
        if _debug:
            APCISequence._debug("    - apdu: %r, %r", apdu, apdu.pduData)

        return apdu

    @classmethod
    def decode(class_, apdu) -> APCISequence:  # type: ignore[override]
        if _debug:
            APCISequence._debug("decode %r", apdu)

        try:
            if apdu.apduType == ConfirmedRequestPDU.pduType:
                apci_sequence_subclass = confirmed_request_types[apdu.apduService]
            elif apdu.apduType == ComplexAckPDU.pduType:
                apci_sequence_subclass = complex_ack_types[apdu.apduService]
            elif apdu.apduType == UnconfirmedRequestPDU.pduType:
                apci_sequence_subclass = unconfirmed_request_types[apdu.apduService]
            elif apdu.apduType == ErrorPDU.pduType:
                apci_sequence_subclass = error_types[apdu.apduService]
            else:
                raise TypeError(f"invalid APDU type: {apdu.apduType}")
        except KeyError:
            raise RuntimeError(f"unrecognized service choice: {apdu.apduService}")
        if _debug:
            APCISequence._debug(
                "    - apci_sequence_subclass: %r, %r",
                apci_sequence_subclass,
                apci_sequence_subclass.decode,
            )

        # decode the APDU data as a TagList
        tag_list = TagList.decode(apdu)
        if _debug:
            APCISequence._debug("    - tag_list: %r len=%d", tag_list, len(tag_list))
            tag_list.debug_contents(indent=2)

        # pass the taglist to the Sequence for additional decoding, overriding
        # the classmethod cls parameter with our known subclass.  It would have
        # been nicer to have some way of calling apci_sequence_subclass.decode()
        # without it falling back to this function
        apci_sequence = Sequence.decode(tag_list, class_=apci_sequence_subclass)

        # check for trailing unmatched tags
        if len(tag_list) != 0:
            if _debug:
                APCISequence._debug("    - trailing unmatched tags: %r", tag_list)
                tag_list.debug_contents(indent=2)
            raise TooManyArguments()

        # copy the header fields
        apci_sequence.update(apdu)

        return cast(APCISequence, apci_sequence)

    def apdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug:
            APCISequence._debug(
                "apdu_contents use_dict=%r as_class=%r", use_dict, as_class
            )

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # set the function based on the class name
        use_dict.__setitem__("function", self.__class__.__name__)

        # fill in from the sequence contents
        Sequence.dict_contents(self, use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict


#
#   ConfirmedRequestSequence
#


@bacpypes_debugging
class ConfirmedRequestSequence(APCISequence, ConfirmedRequestPDU):  # type: ignore[misc]

    service_choice: int

    def __init__(self, *args, **kwargs):
        if _debug:
            ConfirmedRequestSequence._debug("__init__ %r %r", args, kwargs)

        # filter out the PCI kwargs
        pci_kwargs = {}
        for kwarg in (
            "source",
            "destination",
            "expectingReply",
            "networkPriority",
            "user_data",
        ):
            if kwarg in kwargs:
                pci_kwargs[kwarg] = kwargs.pop(kwarg)

        ConfirmedRequestPDU.__init__(
            self, service_choice=self.service_choice, **pci_kwargs
        )
        APCISequence.__init__(self, *args, **kwargs)


#
#   ComplexAckSequence
#


@bacpypes_debugging
class ComplexAckSequence(APCISequence, ComplexAckPDU):  # type: ignore[misc]

    service_choice: int

    def __init__(self, *args, **kwargs):
        if _debug:
            ComplexAckSequence._debug("__init__ %r %r", args, kwargs)

        # filter out the APDU kwargs, including the PCI kwargs
        pdu_kwargs = {}
        for kwarg in (
            "source",
            "destination",
            "expectingReply",
            "networkPriority",
            "user_data",
            "invoke_id",
            "context",
        ):
            if kwarg in kwargs:
                pdu_kwargs[kwarg] = kwargs.pop(kwarg)

        ComplexAckPDU.__init__(self, service_choice=self.service_choice, **pdu_kwargs)
        APCISequence.__init__(self, *args, **kwargs)


#
#   UnconfirmedRequestSequence
#


@bacpypes_debugging
class UnconfirmedRequestSequence(APCISequence, UnconfirmedRequestPDU):  # type: ignore[misc]

    service_choice: int

    def __init__(self, *args, **kwargs):
        if _debug:
            UnconfirmedRequestSequence._debug("__init__ %r %r", args, kwargs)

        # filter out the APDU kwargs, including the PCI kwargs
        pdu_kwargs = {}
        for kwarg in (
            "source",
            "destination",
            "expectingReply",
            "networkPriority",
            "user_data",
        ):
            if kwarg in kwargs:
                pdu_kwargs[kwarg] = kwargs.pop(kwarg)

        UnconfirmedRequestPDU.__init__(
            self, service_choice=self.service_choice, **pdu_kwargs
        )
        APCISequence.__init__(self, *args, **kwargs)


#
#   ErrorSequence
#


@bacpypes_debugging
class ErrorSequence(APCISequence, ErrorPDU):  # type: ignore[misc]

    service_choice: int

    def __init__(self, *args, **kwargs):
        if _debug:
            ErrorSequence._debug("__init__ %r %r", args, kwargs)

        # filter out the APDU kwargs, including the PCI kwargs
        pdu_kwargs = {}
        for kwarg in (
            "source",
            "destination",
            "expectingReply",
            "networkPriority",
            "user_data",
            "invoke_id",
            "context",
        ):
            if kwarg in kwargs:
                pdu_kwargs[kwarg] = kwargs.pop(kwarg)

        # service choice could be a keyword argument
        if "service_choice" in kwargs:
            service_choice = kwargs.pop("service_choice")
        else:
            service_choice = self.service_choice

        ErrorPDU.__init__(self, service_choice=service_choice, **pdu_kwargs)
        APCISequence.__init__(self, *args, **kwargs)


#
#
#


@register_confirmed_request_type
class AcknowledgeAlarmRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.acknowledgeAlarm
    _order = (
        "acknowledgingProcessIdentifier",
        "eventObjectIdentifier",
        "eventStateAcknowledged",
        "timeStamp",
        "acknowledgmentSource",
        "timeOfAcknowledgment",
    )
    acknowledgingProcessIdentifier = Unsigned(_context=0)
    eventObjectIdentifier = ObjectIdentifier(_context=1)
    eventStateAcknowledged = EventState(_context=2)
    timeStamp = TimeStamp(_context=3)
    acknowledgmentSource = CharacterString(_context=4)
    timeOfAcknowledgment = TimeStamp(_context=5)


@register_confirmed_request_type
class AddListElementRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.addListElement
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "listOfElements",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    listOfElements = Any(_context=3)


@register_confirmed_request_type
class AtomicReadFileRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.atomicReadFile
    _order = ("fileIdentifier", "accessMethod")
    fileIdentifier = ObjectIdentifier()
    accessMethod = AtomicReadFileRequestAccessMethodChoice()


@register_confirmed_request_type
class AtomicWriteFileRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.atomicWriteFile
    _order = ("fileIdentifier", "accessMethod")
    fileIdentifier = ObjectIdentifier()
    accessMethod = AtomicWriteFileRequestAccessMethodChoice()


@register_confirmed_request_type
class AuthenticateRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.authenticate
    _order = (
        "pseudoRandomNumber",
        "expectedInvokeID",
        "operatorName",
        "operatorPassword",
        "startEncipheredSession",
    )
    pseudoRandomNumber = Unsigned(_context=0)
    expectedInvokeID = Unsigned(_context=1)
    operatorName = CharacterString(_context=2)
    operatorPassword = CharacterString(_context=3)
    startEncipheredSession = Boolean(_context=4)


@register_confirmed_request_type
class ConfirmedCOVNotificationRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.confirmedCOVNotification
    _order = (
        "subscriberProcessIdentifier",
        "initiatingDeviceIdentifier",
        "monitoredObjectIdentifier",
        "timeRemaining",
        "listOfValues",
    )
    subscriberProcessIdentifier = Unsigned(_context=0)
    initiatingDeviceIdentifier = ObjectIdentifier(_context=1)
    monitoredObjectIdentifier = ObjectIdentifier(_context=2)
    timeRemaining = Unsigned(_context=3)
    listOfValues = SequenceOf(PropertyValue, _context=4)


@register_confirmed_request_type
class ConfirmedEventNotificationRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.confirmedEventNotification
    _order = (
        "processIdentifier",
        "initiatingDeviceIdentifier",
        "eventObjectIdentifier",
        "timeStamp",
        "notificationClass",
        "priority",
        "eventType",
        "messageText",
        "notifyType",
        "ackRequired",
        "fromState",
        "toState",
        "eventValues",
    )
    processIdentifier = Unsigned(_context=0)
    initiatingDeviceIdentifier = ObjectIdentifier(_context=1)
    eventObjectIdentifier = ObjectIdentifier(_context=2)
    timeStamp = TimeStamp(_context=3)
    notificationClass = Unsigned(_context=4)
    priority = Unsigned(_context=5)
    eventType = EventType(_context=6)
    messageText = CharacterString(_context=7, _optional=True)
    notifyType = NotifyType(_context=8)
    ackRequired = Boolean(_context=9, _optional=True)
    fromState = EventState(_context=10, _optional=True)
    toState = EventState(_context=11)
    eventValues = NotificationParameters(_context=12, _optional=True)


@register_confirmed_request_type
class ConfirmedPrivateTransferRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.confirmedPrivateTransfer
    _order = ("vendorID", "serviceNumber", "serviceParameters")
    vendorID = Unsigned(_context=0)
    serviceNumber = Unsigned(_context=1)
    serviceParameters = Any(_context=2, _optional=True)


@register_confirmed_request_type
class ConfirmedTextMessageRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.confirmedTextMessage
    _order = ("textMessageSourceDevice", "messageClass", "messagePriority", "message")
    textMessageSourceDevice = ObjectIdentifier(_context=0)
    messageClass = ConfirmedTextMessageRequestMessageClass(_context=1, _optional=True)
    messagePriority = ConfirmedTextMessageRequestMessagePriority(_context=2)
    message = CharacterString(_context=3)


@register_confirmed_request_type
class CreateObjectRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.createObject
    _order = ("objectSpecifier", "listOfInitialValues")
    objectSpecifier = CreateObjectRequestObjectSpecifier(_context=0)
    listOfInitialValues = SequenceOf(PropertyValue, _context=1, _optional=True)


@register_confirmed_request_type
class DeleteObjectRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.deleteObject
    _order = ("objectIdentifier",)
    objectIdentifier = ObjectIdentifier()


@register_confirmed_request_type
class DeviceCommunicationControlRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.deviceCommunicationControl
    _order = ("timeDuration", "enableDisable", "password")
    timeDuration = Unsigned(_context=0, _optional=True)
    enableDisable = DeviceCommunicationControlRequestEnableDisable(
        _context=1, _optional=True
    )
    password = CharacterString(_context=2, _optional=True)


@register_confirmed_request_type
class GetAlarmSummaryRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.getAlarmSummary
    _order = ()


@register_confirmed_request_type
class GetEnrollmentSummaryRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.getEnrollmentSummary
    _order = (
        "acknowledgmentFilter",
        "enrollmentFilter",
        "eventStateFilter",
        "eventTypeFilter",
        "priorityFilter",
        "notificationClassFilter",
    )
    acknowledgmentFilter = GetEnrollmentSummaryRequestAcknowledgmentFilterType(
        _context=0
    )
    enrollmentFilter = RecipientProcess(_context=1, _optional=True)
    eventStateFilter = GetEnrollmentSummaryRequestEventStateFilterType(
        _context=2, _optional=True
    )
    eventTypeFilter = EventType(_context=3, _optional=True)
    priorityFilter = GetEnrollmentSummaryRequestPriorityFilterType(
        _context=4, _optional=True
    )
    notificationClassFilter = Unsigned(_context=5, _optional=True)


@register_confirmed_request_type
class GetEventInformationRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.getEventInformation
    _order = ("lastReceivedObjectIdentifier",)
    lastReceivedObjectIdentifier = ObjectIdentifier(_context=0, _optional=True)


@register_confirmed_request_type
class LifeSafetyOperationRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.lifeSafetyOperation
    _order = (
        "requestingProcessIdentifier",
        "requestingSource",
        "request",
        "objectIdentifier",
    )
    requestingProcessIdentifier = Unsigned(_context=0)
    requestingSource = CharacterString(_context=1)
    request = LifeSafetyOperation(_context=2)
    objectIdentifier = ObjectIdentifier(_context=3, _optional=True)


@register_confirmed_request_type
class ReadPropertyMultipleRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.readPropertyMultiple
    _order = ("listOfReadAccessSpecs",)
    listOfReadAccessSpecs = SequenceOf(ReadAccessSpecification)


@register_confirmed_request_type
class ReadPropertyRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.readProperty
    _order = ("objectIdentifier", "propertyIdentifier", "propertyArrayIndex")
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)


@register_confirmed_request_type
class ReadRangeRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.readRange
    _order = ("objectIdentifier", "propertyIdentifier", "propertyArrayIndex", "range")
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    range = Range(_optional=True)


@register_confirmed_request_type
class ReinitializeDeviceRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.reinitializeDevice
    _order = ("reinitializedStateOfDevice", "password")
    reinitializedStateOfDevice = ReinitializeDeviceRequestReinitializedStateOfDevice(
        _context=0
    )
    password = CharacterString(_context=1, _optional=True)


@register_confirmed_request_type
class RemoveListElementRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.removeListElement
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "listOfElements",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    listOfElements = Any(_context=3)


@register_confirmed_request_type
class RequestKeyRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.requestKey
    _order = (
        "requestingDeviceIdentifier",
        "requestingDeviceAddress",
        "remoteDeviceIdentifier",
        "remoteDeviceAddress",
    )
    requestingDeviceIdentifier = ObjectIdentifier()
    requestingDeviceAddress = DeviceAddress()
    remoteDeviceIdentifier = ObjectIdentifier()
    remoteDeviceAddress = DeviceAddress()


@register_confirmed_request_type
class SubscribeCOVPropertyRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.subscribeCOVProperty
    _order = (
        "subscriberProcessIdentifier",
        "monitoredObjectIdentifier",
        "issueConfirmedNotifications",
        "lifetime",
        "monitoredPropertyIdentifier",
        "covIncrement",
    )
    subscriberProcessIdentifier = Unsigned(_context=0)
    monitoredObjectIdentifier = ObjectIdentifier(_context=1)
    issueConfirmedNotifications = Boolean(_context=2, _optional=True)
    lifetime = Unsigned(_context=3, _optional=True)
    monitoredPropertyIdentifier = PropertyReference(_context=4)
    covIncrement = Real(_context=5, _optional=True)


@register_confirmed_request_type
class SubscribeCOVRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.subscribeCOV
    _order = (
        "subscriberProcessIdentifier",
        "monitoredObjectIdentifier",
        "issueConfirmedNotifications",
        "lifetime",
    )
    subscriberProcessIdentifier = Unsigned(_context=0)
    monitoredObjectIdentifier = ObjectIdentifier(_context=1)
    issueConfirmedNotifications = Boolean(_context=2, _optional=True)
    lifetime = Unsigned(_context=3, _optional=True)


@register_confirmed_request_type
class VTCloseRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.vtClose
    _order = ("listOfRemoteVTSessionIdentifiers",)
    listOfRemoteVTSessionIdentifiers = SequenceOf(Unsigned)


@register_confirmed_request_type
class VTDataRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.vtData
    _order = ("vtSessionIdentifier", "vtNewData", "vtDataFlag")
    vtSessionIdentifier = Unsigned()
    vtNewData = OctetString()
    vtDataFlag = Unsigned()


@register_confirmed_request_type
class VTOpenRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.vtOpen
    _order = ("vtClass", "localVTSessionIdentifier")
    vtClass = VTClass()
    localVTSessionIdentifier = Unsigned()


@register_confirmed_request_type
class WritePropertyMultipleRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.writePropertyMultiple
    _order = ("listOfWriteAccessSpecs",)
    listOfWriteAccessSpecs = SequenceOf(WriteAccessSpecification)


@register_confirmed_request_type
class WritePropertyRequest(ConfirmedRequestSequence):
    service_choice = ConfirmedServiceChoice.writeProperty
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "propertyValue",
        "priority",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    propertyValue = Any(_context=3)
    priority = Integer(_context=4, _optional=True)


@register_unconfirmed_request_type
class IAmRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.iAm
    _order = (
        "iAmDeviceIdentifier",
        "maxAPDULengthAccepted",
        "segmentationSupported",
        "vendorID",
    )
    iAmDeviceIdentifier = ObjectIdentifier()
    maxAPDULengthAccepted = Unsigned()
    segmentationSupported = Segmentation()
    vendorID = Unsigned()


@register_unconfirmed_request_type
class IHaveRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.iHave
    _order = ("deviceIdentifier", "objectIdentifier", "objectName")
    deviceIdentifier = ObjectIdentifier()
    objectIdentifier = ObjectIdentifier()
    objectName = CharacterString()


@register_unconfirmed_request_type
class TimeSynchronizationRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.timeSynchronization
    _order = ("time",)
    time = DateTime()


@register_unconfirmed_request_type
class UTCTimeSynchronizationRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.utcTimeSynchronization
    _order = ("time",)
    time = DateTime()


@register_unconfirmed_request_type
class UnconfirmedCOVNotificationRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.unconfirmedCOVNotification
    _order = (
        "subscriberProcessIdentifier",
        "initiatingDeviceIdentifier",
        "monitoredObjectIdentifier",
        "timeRemaining",
        "listOfValues",
    )
    subscriberProcessIdentifier = Unsigned(_context=0)
    initiatingDeviceIdentifier = ObjectIdentifier(_context=1)
    monitoredObjectIdentifier = ObjectIdentifier(_context=2)
    timeRemaining = Unsigned(_context=3)
    listOfValues = SequenceOf(PropertyValue, _context=4)


@register_unconfirmed_request_type
class UnconfirmedEventNotificationRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.unconfirmedEventNotification
    _order = (
        "processIdentifier",
        "initiatingDeviceIdentifier",
        "eventObjectIdentifier",
        "timeStamp",
        "notificationClass",
        "priority",
        "eventType",
        "messageText",
        "notifyType",
        "ackRequired",
        "fromState",
        "toState",
        "eventValues",
    )
    processIdentifier = Unsigned(_context=0)
    initiatingDeviceIdentifier = ObjectIdentifier(_context=1)
    eventObjectIdentifier = ObjectIdentifier(_context=2)
    timeStamp = TimeStamp(_context=3)
    notificationClass = Unsigned(_context=4)
    priority = Unsigned(_context=5)
    eventType = EventType(_context=6)
    messageText = CharacterString(_context=7, _optional=True)
    notifyType = NotifyType(_context=8)
    ackRequired = Boolean(_context=9, _optional=True)
    fromState = EventState(_context=10, _optional=True)
    toState = EventState(_context=11)
    eventValues = NotificationParameters(_context=12, _optional=True)


@register_unconfirmed_request_type
class UnconfirmedPrivateTransferRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.unconfirmedPrivateTransfer
    _order = ("vendorID", "serviceNumber", "serviceParameters")
    vendorID = Unsigned(_context=0)
    serviceNumber = Unsigned(_context=1)
    serviceParameters = Any(_context=2, _optional=True)


@register_unconfirmed_request_type
class UnconfirmedTextMessageRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.unconfirmedTextMessage
    _order = ("textMessageSourceDevice", "messageClass", "messagePriority", "message")
    textMessageSourceDevice = ObjectIdentifier(_context=0)
    messageClass = UnconfirmedTextMessageRequestMessageClass(_context=1, _optional=True)
    messagePriority = UnconfirmedTextMessageRequestMessagePriority(_context=2)
    message = CharacterString(_context=3)


@register_unconfirmed_request_type
class WhoHasRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.whoHas
    _order = ("limits", "object")
    limits = WhoHasLimits(_optional=True)
    object = WhoHasObject()


@register_unconfirmed_request_type
class WhoIsRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.whoIs
    _order = ("deviceInstanceRangeLowLimit", "deviceInstanceRangeHighLimit")
    deviceInstanceRangeLowLimit = Unsigned(_context=0, _optional=True)
    deviceInstanceRangeHighLimit = Unsigned(_context=1, _optional=True)


@register_unconfirmed_request_type
class WriteGroupRequest(UnconfirmedRequestSequence):
    service_choice = UnconfirmedServiceChoice.writeGroup
    _order = ("groupNumber", "writePriority", "changeList", "inhibitDelay")
    groupNumber = Unsigned(_context=0)
    writePriority = Unsigned(_context=1)
    changeList = SequenceOf(GroupChannelValue, _context=2)
    inhibitDelay = Boolean(_context=3, _optional=True)


@register_complex_ack_type
class AtomicReadFileACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.atomicReadFile
    _order = ("endOfFile", "accessMethod")
    endOfFile = Boolean()
    accessMethod = AtomicReadFileACKAccessMethodChoice()


@register_complex_ack_type
class AtomicWriteFileACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.atomicWriteFile
    _order = ("fileStartPosition", "fileStartRecord")
    fileStartPosition = Integer(_context=0, _optional=True)
    fileStartRecord = Integer(_context=1, _optional=True)


@register_complex_ack_type
class AuthenticateACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.authenticate
    _order = ("modifiedRandomNumber",)
    modifiedRandomNumber = Unsigned()


@register_complex_ack_type
class ConfirmedPrivateTransferACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.confirmedPrivateTransfer
    _order = ("vendorID", "serviceNumber", "resultBlock")
    vendorID = Unsigned(_context=0)
    serviceNumber = Unsigned(_context=1)
    resultBlock = Any(_context=2, _optional=True)


@register_complex_ack_type
class CreateObjectACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.createObject
    _order = ("objectIdentifier",)
    objectIdentifier = ObjectIdentifier()


@register_complex_ack_type
class GetAlarmSummaryACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.getAlarmSummary
    _order = ("listOfAlarmSummaries",)
    listOfAlarmSummaries = SequenceOf(GetAlarmSummaryAlarmSummary)


@register_complex_ack_type
class GetEnrollmentSummaryACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.getEnrollmentSummary
    _order = ("listOfEnrollmentSummaries",)
    listOfEnrollmentSummaries = SequenceOf(GetEnrollmentSummaryEnrollmentSummary)


@register_complex_ack_type
class GetEventInformationACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.getEventInformation
    _order = ("listOfEventSummaries", "moreEvents")
    listOfEventSummaries = SequenceOf(GetEventInformationEventSummary, _context=0)
    moreEvents = Boolean(_context=1)


@register_complex_ack_type
class ReadPropertyACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.readProperty
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "propertyValue",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    propertyValue = Any(_context=3)


@register_complex_ack_type
class ReadPropertyMultipleACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.readPropertyMultiple
    _order = ("listOfReadAccessResults",)
    listOfReadAccessResults = SequenceOf(ReadAccessResult)


@register_complex_ack_type
class ReadRangeACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.readRange
    _order = (
        "objectIdentifier",
        "propertyIdentifier",
        "propertyArrayIndex",
        "resultFlags",
        "itemCount",
        "itemData",
        "firstSequenceNumber",
    )
    objectIdentifier = ObjectIdentifier(_context=0)
    propertyIdentifier = PropertyIdentifier(_context=1)
    propertyArrayIndex = Unsigned(_context=2, _optional=True)
    resultFlags = ResultFlags(_context=3)
    itemCount = Unsigned(_context=4)
    itemData = SequenceOfAny(_context=5)
    firstSequenceNumber = Unsigned(_context=6, _optional=True)


@register_complex_ack_type
class VTDataACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.vtData
    _order = ("allNewDataAccepted", "acceptedOctetCount")
    allNewDataAccepted = Boolean(_context=0)
    acceptedOctetCount = Unsigned(_context=1)


@register_complex_ack_type
class VTOpenACK(ComplexAckSequence):
    service_choice = ConfirmedServiceChoice.vtOpen
    _order = ("remoteVTSessionIdentifier",)
    remoteVTSessionIdentifier = Unsigned()


#
#   Errors
#


class Error(ErrorSequence):
    _order = ("errorClass", "errorCode")
    errorClass = ErrorClass()
    errorCode = ErrorCode()

    def __str__(self):
        return str(self.errorClass) + ": " + str(self.errorCode)


# see BACnet-Error
for service_choice in {
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    11,
    12,
    14,
    26,
    15,
    33,
    17,
    19,
    20,
    21,
    23,
}:
    error_types[service_choice] = type(
        f"Error({ConfirmedServiceChoice(service_choice)})",
        (Error,),
        {"service_choice": service_choice},
    )


class ChangeListError(ErrorSequence):
    _order = ("errorType", "firstFailedElementNumber")
    errorType = ErrorType(_context=0)
    firstFailedElementNumber = Unsigned(_context=1)


error_types[8] = ChangeListError
error_types[9] = ChangeListError


@register_error_type
class ConfirmedPrivateTransferError(ErrorSequence):
    service_choice = ConfirmedServiceChoice.confirmedPrivateTransfer
    _order = ("errorType", "vendorID", "serviceNumber", "errorParameters")
    errorType = ErrorType(_context=0)
    vendorID = Unsigned(_context=1)
    serviceNumber = Unsigned(_context=2)
    errorParameters = Any(_context=3, _optional=True)


error_types[18] = ConfirmedPrivateTransferError


@register_error_type
class CreateObjectError(ErrorSequence):
    service_choice = ConfirmedServiceChoice.createObject
    _order = ("errorType", "firstFailedElementNumber")
    errorType = ErrorType(_context=0)
    firstFailedElementNumber = Unsigned(_context=1)


error_types[10] = CreateObjectError


@register_error_type
class VTCloseError(ErrorSequence):
    service_choice = ConfirmedServiceChoice.vtClose
    _order = ("errorType", "listOfVTSessionIdentifiers")
    errorType = ErrorType(_context=0)
    listOfVTSessionIdentifiers = SequenceOf(Unsigned, _context=1, _optional=True)


error_types[22] = VTCloseError


@register_error_type
class WritePropertyMultipleError(ErrorSequence):
    service_choice = ConfirmedServiceChoice.writePropertyMultiple
    _order = ("errorType", "firstFailedWriteAttempt")
    errorType = ErrorType(_context=0)
    firstFailedWriteAttempt = ObjectPropertyReference(_context=1)


error_types[16] = WritePropertyMultipleError
