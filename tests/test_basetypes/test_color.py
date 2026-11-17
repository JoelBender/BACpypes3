#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Color and Color Temperature
--------------------------------

The Color (63) and Color Temperature (64) object types, their properties,
and the BACnetxyColor and BACnetColorCommand constructed types.
"""

import pytest

from bacpypes3.basetypes import (
    ChannelValue,
    ColorCommand,
    ColorOperation,
    ColorOperationInProgress,
    ColorTransition,
    ObjectTypesSupported,
    XYColor,
)
from bacpypes3.debugging import ModuleLogger
from bacpypes3.object import (
    ColorObject,
    ColorTemperatureObject,
    LightingOutputObject,
)
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import (
    ObjectType,
    PropertyIdentifier,
    TagList,
)
from bacpypes3.vendor import get_vendor_info

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def round_trip(cls, value, data_hex):
    data = bytes.fromhex(data_hex)
    assert value.encode().encode().pduData == data
    decoded = cls.decode(TagList.decode(PDUData(data)))
    assert decoded.encode().encode().pduData == data
    return decoded


def test_object_types():
    assert ObjectType("color") == 63
    assert ObjectType("colorTemperature") == 64
    assert ObjectType("color-temperature") == 64
    assert str(ObjectType(63)) == "color"
    assert str(ObjectType(64)) == "color-temperature"


@pytest.mark.parametrize(
    "name, value",
    [
        ("color-override", 4194328),
        ("color-reference", 4194329),
        ("default-color", 4194330),
        ("default-color-temperature", 4194331),
        ("override-color-reference", 4194332),
        ("color-command", 4194334),
    ],
)
def test_property_identifiers(name, value):
    assert PropertyIdentifier(name) == value
    assert str(PropertyIdentifier(value)) == name


def test_object_types_supported():
    # the bit names set the encoded length, which must cover the color bits
    assert ObjectTypesSupported._bitstring_names["color"] == 63
    assert ObjectTypesSupported._bitstring_names["color-temperature"] == 64
    assert ObjectTypesSupported._bitstring_length > 64


def test_enumerations():
    assert str(ColorOperation(2)) == "fade-to-cct"
    assert ColorOperation("step-down-cct") == 5
    assert str(ColorOperationInProgress(3)) == "not-controlled"
    assert str(ColorTransition(2)) == "ramp"


def test_xy_color():
    decoded = round_trip(
        XYColor,
        XYColor(xCoordinate=0.5, yCoordinate=0.25),
        "44 3f000000 44 3e800000",
    )
    assert decoded.xCoordinate == 0.5
    assert decoded.yCoordinate == 0.25


def test_color_command_fade_to_color():
    decoded = round_trip(
        ColorCommand,
        ColorCommand(
            operation=ColorOperation("fade-to-color"),
            targetColor=XYColor(xCoordinate=0.5, yCoordinate=0.25),
            fadeTime=1000,
        ),
        "09 01 1e 44 3f000000 44 3e800000 1f 3a 03e8",
    )
    assert decoded.operation == ColorOperation.fadeToColor
    assert decoded.targetColor.yCoordinate == 0.25
    assert decoded.targetColorTemperature is None
    assert decoded.fadeTime == 1000


def test_color_command_ramp_to_cct():
    decoded = round_trip(
        ColorCommand,
        ColorCommand(
            operation=ColorOperation("ramp-to-cct"),
            targetColorTemperature=2700,
            rampRate=10,
        ),
        "09 03 2a 0a8c 49 0a",
    )
    assert decoded.targetColor is None
    assert decoded.targetColorTemperature == 2700
    assert decoded.rampRate == 10


def test_channel_value_color():
    decoded = round_trip(
        ChannelValue,
        ChannelValue(xycolor=XYColor(xCoordinate=0.5, yCoordinate=0.25)),
        "1e 44 3f000000 44 3e800000 1f",
    )
    assert decoded.xycolor.xCoordinate == 0.5

    decoded = round_trip(
        ChannelValue,
        ChannelValue(colorCommand=ColorCommand(operation=ColorOperation("stop"))),
        "2e 09 06 2f",
    )
    assert decoded.colorCommand.operation == ColorOperation.stop


def test_object_classes():
    vendor_info = get_vendor_info(0)
    assert vendor_info.get_object_class(63) is ColorObject
    assert vendor_info.get_object_class(64) is ColorTemperatureObject

    assert ColorObject.get_property_type("presentValue") is XYColor
    assert ColorObject.get_property_type("colorCommand") is ColorCommand
    assert ColorObject.get_property_type("defaultColor") is XYColor
    assert ColorTemperatureObject.get_property_type("defaultColorTemperature")
    assert LightingOutputObject.get_property_type("colorReference")
    assert LightingOutputObject.get_property_type("overrideColorReference")
    assert LightingOutputObject.get_property_type("colorOverride")


def test_color_object():
    obj = ColorObject(
        objectIdentifier=("color", 1),
        objectName="Color 1",
        presentValue=XYColor(xCoordinate=0.3127, yCoordinate=0.329),
        inProgress="idle",
        defaultFadeTime=100,
    )
    assert obj.objectType == ObjectType.color
    assert obj.objectIdentifier == (ObjectType.color, 1)
    assert obj.inProgress == ColorOperationInProgress.idle
