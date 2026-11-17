#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Base Types Wire Encoding
-----------------------------

Encodings of the base types that were corrected to match the CSML
description of Clause 21 (bacnet-data-types.xml).  The expected octets are
computed by hand from the ASN.1 productions.
"""

from bacpypes3.basetypes import (
    AuditLogRecordLogDatum,
    ChannelValue,
    ColorCommand,
    DateTime,
    DeviceObjectPropertyReference,
    EventParameter,
    EventParameterAccessEvent,
    EventParameterExtended,
    EventParameterExtendedParameters,
    FaultParameter,
    FaultParametersFaultListed,
    GroupChannelValue,
    LockStatus,
    NameValue,
    NotificationParameters,
    NotificationParametersAccessEventType,
    NotificationParametersChangeOfStatusFlagsType,
    NotificationParametersChangeOfTimer,
    NotificationParametersExtended,
    NotificationParametersExtendedParametersType,
    ObjectTypesSupported,
    PropertyStates,
    PropertyValue,
    SCConnectionState,
    TimeStamp,
    XYColor,
)
from bacpypes3.constructeddata import Any
from bacpypes3.debugging import ModuleLogger, xtob
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import (
    Integer16,
    Real,
    TagList,
    Unsigned,
    Unsigned32,
    Unsigned64,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def encode(obj) -> bytes:
    """Encode an element into octets."""
    return obj.encode().encode().pduData


def decode(cls, data: bytes):
    """Decode octets into an element of the class, all octets consumed."""
    tag_list = TagList.decode(PDUData(data))
    obj = cls.decode(tag_list)
    assert len(tag_list) == 0
    return obj


def test_unsigned_64_bits():
    """Unsigned values are no longer limited to 32 bits."""
    obj = Unsigned64(2**40 + 5)
    assert encode(obj) == xtob("25 06 010000000005")
    assert decode(Unsigned64, encode(obj)) == obj

    assert encode(Unsigned(0)) == xtob("21 00")
    assert encode(Unsigned(255)) == xtob("21 ff")
    assert encode(Unsigned32(4294967295)) == xtob("24 ffffffff")


def test_sized_limits():
    for cls, value in ((Unsigned32, 2**32), (Integer16, 32768), (Integer16, -32769)):
        try:
            cls(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{cls.__name__}({value}) accepted")


def test_property_states_write_status():
    """write-status is context tag 37, not 370."""
    obj = PropertyStates(writeStatus="successful")
    assert encode(obj) == xtob("f9 25 02")
    assert decode(PropertyStates, encode(obj)).writeStatus == 2


def test_property_states_extended_value():
    """Tags above 254 travel as extended-value [63] = tag * 100000 + value."""
    obj = PropertyStates(scConnectionState=SCConnectionState("connected"))
    # 258 * 100000 + 1 = 25800001 = 0x189AD41
    assert encode(obj) == xtob("fc 3f 0189ad41")

    result = decode(PropertyStates, encode(obj))
    assert result._choice == "scConnectionState"
    assert result.scConnectionState == SCConnectionState.connected

    # an unknown extended value stays as it is
    result = decode(PropertyStates, encode(PropertyStates(extendedValue=12345)))
    assert result._choice == "extendedValue"
    assert result.extendedValue == 12345


def test_notification_parameters_complex_event_type():
    """complex-event-type [6] is a SEQUENCE OF BACnetPropertyValue."""
    obj = NotificationParameters(
        complexEventType=[
            PropertyValue(
                propertyIdentifier="presentValue", propertyValue=Any(Real(1.0))
            )
        ]
    )
    assert encode(obj) == xtob("6e 0955 2e 443f800000 2f 6f")
    result = decode(NotificationParameters, encode(obj))
    assert result.complexEventType[0].propertyIdentifier == 85  # present-value


def test_notification_parameters_extended():
    """extended parameters [2] is a SEQUENCE OF application tagged values."""
    obj = NotificationParameters(
        extended=NotificationParametersExtended(
            vendorId=999,
            extendedEventType=5,
            parameters=[
                NotificationParametersExtendedParametersType(real=2.5),
                NotificationParametersExtendedParametersType(unsigned=7),
                NotificationParametersExtendedParametersType(integer=-1),
                NotificationParametersExtendedParametersType(characterstring="hi"),
            ],
        )
    )
    assert encode(obj) == xtob("9e 0a03e7 1905 2e 4440200000 2107 31ff 7300 6869 2f 9f")
    result = decode(NotificationParameters, encode(obj))
    assert [p._choice for p in result.extended.parameters] == [
        "real",
        "unsigned",
        "integer",
        "characterstring",
    ]


def test_notification_parameters_access_event():
    """authentication-factor [5] is a BACnetAuthenticationFactor."""
    element = NotificationParametersAccessEventType._elements["authenticationFactor"]
    assert element.__mro__[1].__name__ == "AuthenticationFactor"
    assert element._context == 5
    assert element._optional


def test_notification_parameters_change_of_status_flags():
    """present-value [0] is ABSTRACT-SYNTAX.&Type OPTIONAL."""
    element = NotificationParametersChangeOfStatusFlagsType._elements["presentValue"]
    assert issubclass(element, Any)
    assert element._optional


def test_notification_parameters_change_of_timer():
    obj = NotificationParameters(
        changeOfTimer=NotificationParametersChangeOfTimer(
            newState="running",
            statusFlags=[0, 0, 0, 0],
            updateTime=DateTime(date=(124, 1, 2, 3), time=(1, 2, 3, 4)),
        )
    )
    assert encode(obj) == xtob(
        "fe 16"  # opening tag 22
        "0901"  # new-state [0] running
        "1a 0400"  # status-flags [1]
        "2e a47c010203 b401020304 2f"  # update-time [2]
        "ff 16"  # closing tag 22
    )
    assert decode(NotificationParameters, encode(obj))._choice == "changeOfTimer"


def test_event_parameter_extended():
    """extended parameters are application tagged except reference [0]."""
    obj = EventParameter(
        extended=EventParameterExtended(
            vendorId=999,
            extendedEventType=5,
            parameters=[
                EventParameterExtendedParameters(real=2.5),
                EventParameterExtendedParameters(
                    reference=DeviceObjectPropertyReference(
                        objectIdentifier=("analogValue", 1),
                        propertyIdentifier="presentValue",
                    )
                ),
            ],
        )
    )
    assert encode(obj) == xtob(
        "9e 0a03e7 1905 2e 4440200000 0e 0c00800001 1955 0f 2f 9f"
    )
    result = decode(EventParameter, encode(obj))
    assert [p._choice for p in result.extended.parameters] == ["real", "reference"]


def test_event_parameter_access_event():
    """access-event [13] holds the list and the time reference directly."""
    obj = EventParameter(
        accessEvent=EventParameterAccessEvent(
            listOfAccessEvents=["granted", "duress"],
            accessEventTimeReference=DeviceObjectPropertyReference(
                objectIdentifier=("accessPoint", 1),
                propertyIdentifier="accessEventTime",
            ),
        )
    )
    assert encode(obj) == xtob("de 0e 9101 9104 0f 1e 0c08400001 19fa 1f df")
    result = decode(EventParameter, encode(obj))
    assert list(result.accessEvent.listOfAccessEvents) == [1, 4]


def test_fault_parameter_fault_listed():
    """fault-list-reference [0] is one BACnetDeviceObjectPropertyReference."""
    obj = FaultParameter(
        faultListed=FaultParametersFaultListed(
            faultListReference=DeviceObjectPropertyReference(
                objectIdentifier=("binaryValue", 1),
                propertyIdentifier="presentValue",
            )
        )
    )
    assert encode(obj) == xtob("7e 0e 0c01400001 1955 0f 7f")
    result = decode(FaultParameter, encode(obj))
    assert result.faultListed.faultListReference.propertyIdentifier == 85


def test_audit_log_record_time_change():
    """time-change is context tag 2."""
    obj = AuditLogRecordLogDatum(timeChange=1.0)
    assert encode(obj) == xtob("2c 3f800000")
    assert decode(AuditLogRecordLogDatum, encode(obj))._choice == "timeChange"


def test_group_channel_value():
    """channel [0], value [1], overriding-priority [2] OPTIONAL."""
    obj = GroupChannelValue(
        channel=3, value=ChannelValue(real=50.0), overridingPriority=8
    )
    assert encode(obj) == xtob("0903 1e 4442480000 1f 2908")
    result = decode(GroupChannelValue, encode(obj))
    assert (result.channel, result.value.real, result.overridingPriority) == (
        3,
        50.0,
        8,
    )


def test_channel_value_color():
    xy = XYColor(xCoordinate=0.5, yCoordinate=0.25)
    obj = ChannelValue(xycolor=xy)
    assert encode(obj) == xtob("1e 443f000000 443e800000 1f")
    assert decode(ChannelValue, encode(obj))._choice == "xycolor"

    obj = ChannelValue(
        colorCommand=ColorCommand(
            operation="fadeToColor", targetColor=xy, fadeTime=1000
        )
    )
    assert encode(obj) == xtob("2e 0901 1e 443f000000 443e800000 1f 3a03e8 2f")
    assert decode(ChannelValue, encode(obj)).colorCommand.fadeTime == 1000


def test_name_value_optional_value():
    obj = NameValue(name="tag")
    assert encode(obj) == xtob("0c 00746167")
    result = decode(NameValue, encode(obj))
    assert result.name == "tag"
    assert result.value is None


def test_lock_status():
    assert LockStatus("unknown") == 4
    assert LockStatus("lock-fault") == 2
    assert LockStatus("unused") == 3


def test_object_types_supported():
    # dataRev 31 says length 65 but also defines bit 65 (directory)
    assert ObjectTypesSupported._bitstring_length == 66
    assert ObjectTypesSupported._bitstring_names["timer"] == 31
    assert ObjectTypesSupported._bitstring_names["color"] == 63
    assert ObjectTypesSupported._bitstring_names["color-temperature"] == 64
    assert ObjectTypesSupported._bitstring_names["directory"] == 65


def test_time_stamp_datetime():
    obj = TimeStamp(datetime=DateTime(date=(124, 1, 2, 3), time=(1, 2, 3, 4)))
    assert encode(obj) == xtob("2e a47c010203 b401020304 2f")
    assert decode(TimeStamp, encode(obj))._choice == "datetime"
