#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test EventParameter extended
----------------------------

The parameters of the extended choice of BACnetEventParameter are
application tagged, except for the reference which is context tagged 0,
see issue #155.
"""

import pytest

from bacpypes3.debugging import ModuleLogger

from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import (
    TagList,
    Null,
    Boolean,
    Unsigned,
    Integer,
    Real,
    Double,
    OctetString,
    CharacterString,
    BitString,
    Enumerated,
    Date,
    Time,
    ObjectIdentifier,
)
from bacpypes3.basetypes import (
    DeviceObjectPropertyReference,
    EventParameter,
    EventParameterExtended,
    EventParameterExtendedParameters,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def extended_event_parameter(**kwargs) -> EventParameter:
    return EventParameter(
        extended=EventParameterExtended(
            vendorId=4,
            extendedEventType=3,
            parameters=[EventParameterExtendedParameters(**kwargs)],
        )
    )


def encode(event_parameter: EventParameter) -> bytes:
    return event_parameter.encode().encode().pduData


def decode(data: bytes) -> EventParameter:
    return EventParameter.decode(TagList.decode(PDUData(data)))


# extended [9] { vendor-id [0] 4, extended-event-type [1] 3, parameters [2] {
HEADER = bytes.fromhex("9e 09 04 19 03 2e")
# } }
TRAILER = bytes.fromhex("2f 9f")


@pytest.mark.parametrize(
    "kwargs, parameter_hex",
    [
        ({"null": Null(())}, "00"),
        ({"real": Real(1.0)}, "44 3f800000"),
        ({"unsigned": Unsigned(5)}, "21 05"),
        ({"boolean": Boolean(False)}, "10"),
        ({"boolean": Boolean(True)}, "11"),
        ({"integer": Integer(-1)}, "31 ff"),
        ({"double": Double(1.0)}, "55 08 3ff0000000000000"),
        ({"octet": OctetString(b"\x01\x02")}, "62 0102"),
        ({"characterString": CharacterString("ab")}, "73 00 6162"),
        ({"bitstring": BitString([1, 0])}, "82 06 80"),
        ({"enum": Enumerated(2)}, "91 02"),
        ({"date": Date((121, 1, 2, 6))}, "a4 79010206"),
        ({"time": Time((1, 2, 3, 4))}, "b4 01020304"),
        ({"objectIdentifier": ObjectIdentifier("analog-value,1")}, "c4 00800001"),
        (
            {
                "reference": DeviceObjectPropertyReference(
                    objectIdentifier="analog-value,1",
                    propertyIdentifier="present-value",
                )
            },
            "0e 0c 00800001 19 55 0f",
        ),
    ],
)
def test_extended_parameters_endec(kwargs, parameter_hex) -> None:
    event_parameter = extended_event_parameter(**kwargs)
    data = HEADER + bytes.fromhex(parameter_hex) + TRAILER

    # the parameter is encoded with an application tag (or the reference
    # with context tag 0)
    assert encode(event_parameter) == data

    # decoding gets the same choice back
    event_parameter2 = decode(data)
    choice = event_parameter2.extended.parameters[0]
    ((attr, value),) = kwargs.items()
    assert getattr(choice, attr) == value
    assert encode(event_parameter2) == data
