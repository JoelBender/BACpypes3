#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test APDU Services
------------------

Service requests, acknowledgements and errors from the CSML description of
Clause 21 (bacnet-data-types.xml) encode into APDUs and decode back into the
same classes.
"""

import pytest

from bacpypes3.apdu import (
    APDU,
    APCISequence,
    AuditLogQueryACK,
    AuditLogQueryRequest,
    ConfirmedAuditNotificationRequest,
    ConfirmedCOVNotificationMultipleRequest,
    DeviceCommunicationControlRequest,
    SubscribeCOVPropertyMultipleError,
    SubscribeCOVPropertyMultipleRequest,
    UnconfirmedAuditNotificationRequest,
    UnconfirmedCOVNotificationMultipleRequest,
    VTDataACK,
    WhoAmIRequest,
    WritePropertyRequest,
    YouAreRequest,
    error_types,
)
from bacpypes3.basetypes import (
    AuditLogQueryParameters,
    AuditLogQueryParametersBySource,
    COVMultipleSubscriptionList,
    COVMultipleSubscriptionListOfCOVReference,
    COVNotificationMultipleListOfCOVNotifications,
    COVNotificationMultipleListOfValues,
    ErrorType,
)
from bacpypes3.constructeddata import Any
from bacpypes3.debugging import ModuleLogger, xtob
from bacpypes3.pdu import PDU
from bacpypes3.primitivedata import ObjectIdentifier, Real

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def round_trip(sequence, invoke_id=None):
    """Encode a service sequence into octets and decode it back."""
    if invoke_id is not None:
        sequence.apduInvokeID = invoke_id
    apdu = sequence.encode()

    # header fields the application service access point normally provides
    for attr, value in (
        ("apduSeg", False),
        ("apduMor", False),
        ("apduSA", False),
        ("apduMaxSegs", 0),
        ("apduMaxResp", 5),
    ):
        if getattr(apdu, attr, None) is None:
            setattr(apdu, attr, value)

    octets = apdu.encode().pduData
    result = APCISequence.decode(APDU.decode(PDU(octets)))
    assert type(result) is type(sequence)
    return octets, result


def notifications():
    return [
        COVNotificationMultipleListOfCOVNotifications(
            monitoredObjectIdentifier=("analogValue", 1),
            listOfValues=[
                COVNotificationMultipleListOfValues(
                    propertyIdentifier="presentValue",
                    propertyValue=Any(Real(5.0)),
                )
            ],
        )
    ]


def test_who_am_i():
    octets, result = round_trip(
        WhoAmIRequest(vendorID=999, modelName="m", serialNumber="s")
    )
    assert octets == xtob("10 0d 2203e7 7200 6d 7200 73")
    assert (result.vendorID, result.modelName, result.serialNumber) == (999, "m", "s")


def test_you_are():
    octets, result = round_trip(
        YouAreRequest(
            vendorID=999,
            modelName="m",
            serialNumber="s",
            deviceIdentifier=("device", 5),
        )
    )
    assert octets == xtob("10 0e 2203e7 7200 6d 7200 73 c402000005")
    assert result.deviceIdentifier == ObjectIdentifier(("device", 5))
    assert result.deviceMACAddress is None


def test_unconfirmed_cov_notification_multiple():
    octets, result = round_trip(
        UnconfirmedCOVNotificationMultipleRequest(
            subscriberProcessIdentifier=1,
            initiatingDeviceIdentifier=("device", 5),
            timeRemaining=0,
            listOfCOVNotifications=notifications(),
        )
    )
    assert octets == xtob(
        "10 0b 0901 1c02000005 29004e 0c00800001 1e 0955 2e 4440a00000 2f 1f 4f"
    )
    values = result.listOfCOVNotifications[0].listOfValues
    assert values[0].propertyIdentifier == 85


def test_confirmed_cov_notification_multiple():
    octets, _ = round_trip(
        ConfirmedCOVNotificationMultipleRequest(
            subscriberProcessIdentifier=1,
            initiatingDeviceIdentifier=("device", 5),
            timeRemaining=0,
            listOfCOVNotifications=notifications(),
        ),
        invoke_id=1,
    )
    assert octets[:4] == xtob("00 05 01 1f")


def test_subscribe_cov_property_multiple():
    octets, _ = round_trip(
        SubscribeCOVPropertyMultipleRequest(
            subscriberProcessIdentifier=1,
            issueConfirmedNotifications=False,
            listOfCOVSubscriptionSpecifications=[
                COVMultipleSubscriptionList(
                    monitoredObjectIdentifier=("analogValue", 1),
                    listOfCOVReferences=[
                        COVMultipleSubscriptionListOfCOVReference(
                            monitoredProperty="presentValue",
                            timestamped=True,
                        )
                    ],
                )
            ],
        ),
        invoke_id=3,
    )
    assert octets == xtob("00 05 03 1e 0901 19004e 0c00800001 1e 0e 0955 0f 2901 1f 4f")


@pytest.mark.parametrize(
    "cls", [ConfirmedAuditNotificationRequest, UnconfirmedAuditNotificationRequest]
)
def test_audit_notification(cls):
    invoke_id = 4 if cls is ConfirmedAuditNotificationRequest else None
    octets, _ = round_trip(cls(notifications=[]), invoke_id=invoke_id)
    assert octets[-2:] == xtob("0e 0f")


def test_audit_log_query():
    octets, result = round_trip(
        AuditLogQueryRequest(
            auditLog=("auditLog", 1),
            queryParameters=AuditLogQueryParameters(
                bySource=AuditLogQueryParametersBySource(
                    sourceDeviceIdentifier=("device", 1),
                    successfulActionsOnly="failuresOnly",
                )
            ),
            requestedCount=10,
        ),
        invoke_id=2,
    )
    assert octets == xtob("00 05 02 21 0c0f400001 1e 1e 0c02000001 4902 1f 1f 390a")
    assert result.queryParameters.bySource.successfulActionsOnly == 2

    octets, result = round_trip(
        AuditLogQueryACK(auditLog=("auditLog", 1), records=[], noMoreItems=True),
        invoke_id=5,
    )
    assert octets == xtob("30 05 21 0c0f400001 1e 1f 2901")


def test_subscribe_cov_property_multiple_error():
    octets, result = round_trip(
        SubscribeCOVPropertyMultipleError(
            errorType=ErrorType(errorClass="object", errorCode="unknownObject")
        ),
        invoke_id=6,
    )
    assert octets == xtob("50 06 1e 0e 9101 911f 0f")
    assert result.firstFailedSubscription is None


@pytest.mark.parametrize("service_choice", [27, 28, 29, 31, 32])
def test_error_for_newer_services(service_choice):
    """These services return a plain Error, they used to fail to decode."""
    octets, _ = round_trip(
        error_types[service_choice](errorClass="property", errorCode="unknownProperty"),
        invoke_id=7,
    )
    assert octets == xtob("50 07") + bytes([service_choice]) + xtob("9102 9120")


def test_vt_data_ack_without_count():
    octets, result = round_trip(VTDataACK(allNewDataAccepted=True), invoke_id=8)
    assert octets == xtob("30 08 17 0901")
    assert result.acceptedOctetCount is None


def test_write_property_priority_is_unsigned():
    element = WritePropertyRequest._elements["priority"]
    assert element.__mro__[1].__name__ == "Unsigned"


def test_device_communication_control_enable_disable_required():
    assert not DeviceCommunicationControlRequest._elements["enableDisable"]._optional
