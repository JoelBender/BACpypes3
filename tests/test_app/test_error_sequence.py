"""
Test Service-Specific Errors
----------------------------

Service-specific errors like WritePropertyMultipleError are ErrorSequence
APDUs, which derive from BaseException rather than Exception.  When a service
handler raises one, Application.indication() must send it back as the
response to the request rather than letting it escape (see PR #149).
"""

from __future__ import annotations

from typing import List

from bacpypes3.apdu import (
    APDU,
    ConfirmedServiceChoice,
    WritePropertyMultipleError,
    WritePropertyMultipleRequest,
)
from bacpypes3.app import Application
from bacpypes3.basetypes import ErrorCode, PropertyValue, WriteAccessSpecification
from bacpypes3.constructeddata import Any
from bacpypes3.debugging import ModuleLogger
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.device import DeviceObject
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, Real

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class ResponseApplication(Application):
    """Collect the responses rather than sending them downstream."""

    responses: List[APDU]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.responses = []

    async def response(self, apdu: APDU) -> None:  # type: ignore[override]
        self.responses.append(apdu)


async def test_write_property_multiple_error():
    app = ResponseApplication()
    app.add_object(
        DeviceObject(
            objectIdentifier=("device", 1),
            objectName="dev",
            vendorIdentifier=999,
        )
    )
    app.add_object(
        AnalogValueObject(
            objectIdentifier=("analog-value", 1),
            objectName="av",
            presentValue=1.0,
        )
    )

    # the first object exists, the second one does not
    request = WritePropertyMultipleRequest(
        listOfWriteAccessSpecifications=[
            WriteAccessSpecification(
                objectIdentifier=ObjectIdentifier("analog-value,1"),
                listOfProperties=[
                    PropertyValue(
                        propertyIdentifier="present-value", propertyValue=Any(Real(2.0))
                    )
                ],
            ),
            WriteAccessSpecification(
                objectIdentifier=ObjectIdentifier("analog-value,99"),
                listOfProperties=[
                    PropertyValue(
                        propertyIdentifier="present-value", propertyValue=Any(Real(3.0))
                    )
                ],
            ),
        ],
    )
    request.pduSource = Address("1.2.3.4")
    request.apduInvokeID = 42

    await app.indication(request)

    assert len(app.responses) == 1
    error = app.responses[0]
    assert isinstance(error, WritePropertyMultipleError)
    assert error.apduInvokeID == 42
    assert error.apduService == ConfirmedServiceChoice.writePropertyMultiple
    assert error.pduDestination == Address("1.2.3.4")
    assert error.errorType.errorCode == ErrorCode.unknownObject
    assert error.firstFailedWriteAttempt.objectIdentifier == ObjectIdentifier(
        "analog-value,99"
    )
    assert error.reason == ErrorCode.unknownObject

    app.close()
