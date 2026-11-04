#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Base Type Constructors
---------------------------

PriorityValue picks its choice from the type of the value, PropertyReference
accepts another reference, and SecurityLevel values are distinct.
"""

import pytest

from bacpypes3.basetypes import (
    COVMultipleSubscriptionListOfCOVReference,
    DateTime,
    PriorityValue,
    PropertyReference,
    SecurityLevel,
)
from bacpypes3.debugging import ModuleLogger
from bacpypes3.primitivedata import (
    BitString,
    Boolean,
    CharacterString,
    Date,
    Double,
    Enumerated,
    Integer,
    Null,
    ObjectIdentifier,
    OctetString,
    Real,
    TagList,
    Time,
    Unsigned,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


PRIORITY_VALUES = [
    (Null(()), "null"),
    (Real(1.5), "real"),
    (Double(1.5), "double"),
    (Enumerated(3), "enumerated"),
    (Unsigned(3), "unsigned"),
    (Boolean(True), "boolean"),
    (Integer(-3), "integer"),
    (Time((1, 2, 3, 4)), "time"),
    (CharacterString("x"), "characterString"),
    (OctetString(b"\x01"), "octetString"),
    (BitString([1, 0]), "bitString"),
    (Date((124, 1, 2, 3)), "date"),
    (ObjectIdentifier(("device", 1)), "objectidentifier"),
    (DateTime(date=(124, 1, 2, 3), time=(1, 2, 3, 4)), "datetime"),
]


@pytest.mark.parametrize(
    "value, choice",
    PRIORITY_VALUES,
    ids=[choice for _, choice in PRIORITY_VALUES],
)
def test_priority_value_choice(value, choice):
    priority_value = PriorityValue(value)
    assert priority_value._choice == choice

    # round trip keeps the choice
    result = PriorityValue.decode(TagList(list(priority_value.encode())))
    assert result._choice == choice


def test_priority_value_double_keeps_precision():
    value = Double(0.1)
    result = PriorityValue.decode(TagList(list(PriorityValue(value).encode())))
    assert result.double == value


def test_security_level_values_are_distinct():
    assert SecurityLevel.signedEndToEnd == 4
    assert SecurityLevel.encryptedEndToEnd == 5
    assert SecurityLevel(4).attr == "signedEndToEnd"
    assert SecurityLevel(5).attr == "encryptedEndToEnd"


def test_property_reference_copy():
    original = PropertyReference("presentValue[3]")
    copy = PropertyReference(original)
    assert copy.propertyIdentifier == original.propertyIdentifier
    assert copy.propertyArrayIndex == 3

    copy = PropertyReference(PropertyReference("presentValue"))
    assert copy.propertyArrayIndex is None


def test_property_reference_element_accepts_instance():
    """A reference instance can be given for a context tagged element."""
    element = COVMultipleSubscriptionListOfCOVReference(
        monitoredProperty=PropertyReference("presentValue[3]"),
        timestamped=True,
    )
    assert element.monitoredProperty.propertyArrayIndex == 3

    result = COVMultipleSubscriptionListOfCOVReference.decode(
        TagList(list(element.encode()))
    )
    assert result.monitoredProperty.propertyIdentifier == 85
    assert result.monitoredProperty.propertyArrayIndex == 3


def test_property_reference_rejects_other_types():
    with pytest.raises(TypeError):
        PropertyReference.cast(1.5)
