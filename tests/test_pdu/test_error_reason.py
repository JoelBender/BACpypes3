#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test ErrorRejectAbortNack.reason
--------------------------------

Error PDUs that wrap the error class and code in an errorType (for example
WritePropertyMultipleError) must still provide a reason and be printable,
see issue #123.
"""

from bacpypes3.debugging import ModuleLogger

from bacpypes3.pdu import Address
from bacpypes3.basetypes import ErrorCode, ErrorType, ObjectPropertyReference
from bacpypes3.apdu import (
    APDU,
    APCISequence,
    ChangeListError,
    CreateObjectError,
    RejectPDU,
    WritePropertyMultipleError,
    error_types,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def round_trip(apdu: APCISequence) -> APCISequence:
    """Encode the APDU and decode it again, like it would be received."""
    apdu.pduDestination = Address("1.2.3.4")
    apdu.apduInvokeID = 1
    pdu = apdu.encode().encode()
    return APCISequence.decode(APDU.decode(pdu))


def test_error_reason() -> None:
    """Plain Error keeps using errorCode."""
    error = error_types[12](errorClass="object", errorCode="unknownObject")
    assert error.reason == ErrorCode("unknownObject")
    assert str(error) == "object: unknown-object"


def test_write_property_multiple_error_reason() -> None:
    error = WritePropertyMultipleError(
        errorType=ErrorType(errorClass="property", errorCode="writeAccessDenied"),
        firstFailedWriteAttempt=ObjectPropertyReference(
            objectIdentifier="analog-value,1",
            propertyIdentifier="present-value",
        ),
    )
    assert error.reason == ErrorCode("writeAccessDenied")
    assert str(error) == "write-access-denied"

    # same thing after going through the wire format
    decoded = round_trip(error)
    assert isinstance(decoded, WritePropertyMultipleError)
    assert decoded.reason == ErrorCode("writeAccessDenied")
    assert str(decoded) == "write-access-denied"


def test_other_error_type_errors_reason() -> None:
    error_type = ErrorType(errorClass="object", errorCode="unknownObject")

    for error in (
        ChangeListError(
            errorType=error_type, firstFailedElementNumber=1, service_choice=8
        ),
        CreateObjectError(errorType=error_type, firstFailedElementNumber=1),
    ):
        assert error.reason == ErrorCode("unknownObject")
        assert str(error) == "unknown-object"


def test_reject_reason() -> None:
    reject = RejectPDU(reason="unrecognizedService")
    assert str(reject) == "unrecognized-service"

