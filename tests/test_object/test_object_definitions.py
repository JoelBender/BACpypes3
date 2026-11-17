#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Object Definitions
-----------------------

The object type classes in bacpypes3.object agree with the CSML description
of the object types (bacnet-object-types.xml).
"""

import inspect

import pytest

from bacpypes3 import object as bacpypes_object
from bacpypes3.basetypes import ColorCommand, XYColor
from bacpypes3.debugging import ModuleLogger
from bacpypes3.primitivedata import ObjectType, Unsigned
from bacpypes3.vendor import get_vendor_info

# some debugging
_debug = 0
_log = ModuleLogger(globals())

OBJECT_CLASSES = [
    cls
    for cls in vars(bacpypes_object).values()
    if inspect.isclass(cls)
    and issubclass(cls, bacpypes_object.Object)
    and "objectType" in cls.__dict__
]


def required(cls):
    names = set()
    for c in cls.__mro__:
        names |= set(c.__dict__.get("_required", ()))
    return names


@pytest.mark.parametrize("cls", OBJECT_CLASSES, ids=lambda cls: cls.__name__)
def test_required_properties_exist(cls):
    """Every name in _required is a property of the object type."""
    assert required(cls) <= set(cls._elements)


@pytest.mark.parametrize(
    "cls_name, object_type",
    [("ColorObject", "color"), ("ColorTemperatureObject", "color-temperature")],
)
def test_color_objects(cls_name, object_type):
    cls = getattr(bacpypes_object, cls_name)
    assert cls.objectType == ObjectType(object_type)
    assert get_vendor_info(0).get_object_class(ObjectType(object_type)) is cls
    assert {"presentValue", "colorCommand", "inProgress", "defaultFadeTime"} <= (
        required(cls)
    )
    assert issubclass(cls._elements["colorCommand"], ColorCommand)


def test_color_present_values():
    assert issubclass(bacpypes_object.ColorObject._elements["presentValue"], XYColor)
    assert issubclass(
        bacpypes_object.ColorTemperatureObject._elements["presentValue"], Unsigned
    )


@pytest.mark.parametrize(
    "cls_name, attr, is_required",
    [
        ("StructuredViewObject", "nodeType", True),
        ("StructuredViewObject", "nodeSubtype", False),
        ("TrendLogObject", "eventState", True),
        ("TrendLogObject", "reliability", False),
        ("NotificationClassObject", "notificationClass", False),
        ("NetworkPortObject", "linkSpeed", False),
        ("AccessPointObject", "authorizationMode", True),
        ("IntegerValueObject", "units", True),
        ("AuditReporterObject", "auditLevel", True),
        ("AuditLogObject", "statusFlags", True),
        ("AuditLogObject", "eventState", True),
        ("LifeSafetyZoneObject", "zoneMembers", True),
    ],
)
def test_required_or_optional(cls_name, attr, is_required):
    cls = getattr(bacpypes_object, cls_name)
    assert attr in cls._elements
    assert (attr in required(cls)) is is_required


def test_notification_class_priority_length():
    element = bacpypes_object.NotificationClassObject._elements["priority"]
    assert element._length == 3


def test_lift_has_no_tracking_value():
    assert "trackingValue" not in bacpypes_object.LiftObject._elements


@pytest.mark.parametrize(
    "cls_name, attr",
    [
        ("DeviceObject", "deployedProfileLocation"),
        ("ScheduleObject", "writeEveryScheduledAction"),
        ("LightingOutputObject", "eventState"),
        ("LightingOutputObject", "highEndTrim"),
        ("LightingOutputObject", "colorOverride"),
        ("BinaryLightingOutputObject", "colorReference"),
        ("NetworkPortObject", "scPrimaryHubConnectionStatus"),
        ("NetworkPortObject", "currentHealth"),
        ("NetworkPortObject", "issuerCertificateFiles"),
    ],
)
def test_added_properties(cls_name, attr):
    assert attr in getattr(bacpypes_object, cls_name)._elements


def test_directory_object():
    cls = bacpypes_object.DirectoryObject
    assert cls.objectType == ObjectType("directory")
    assert get_vendor_info(0).get_object_class(ObjectType("directory")) is cls
    assert {"discoveryStatus", "directoryRevision", "enable", "eventState"} <= (
        required(cls)
    )


@pytest.mark.parametrize(
    "cls_name, attr, is_required",
    [
        ("LightingOutputObject", "lastOnValue", True),
        ("LightingOutputObject", "defaultOnValue", True),
        ("DeviceObject", "authorizationServer", False),
        ("DeviceObject", "authorizationCache", False),
        ("DeviceObject", "deviceAddressProxyTable", False),
        ("DeviceObject", "maxProxiedIAmsPerSecond", False),
        ("NetworkPortObject", "deviceAddressProxyEnable", False),
        ("NetworkPortObject", "deviceAddressProxyTimeout", False),
    ],
)
def test_rev31_properties(cls_name, attr, is_required):
    cls = getattr(bacpypes_object, cls_name)
    assert attr in cls._elements
    assert (attr in required(cls)) is is_required
