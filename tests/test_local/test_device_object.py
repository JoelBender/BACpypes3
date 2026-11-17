"""
Test Local Device Object
------------------------

Protocol_Object_Types_Supported has a bit for each type of object in the
application, and the bit string was always empty before.
"""

from __future__ import annotations

from types import SimpleNamespace

from bacpypes3.app import Application
from bacpypes3.basetypes import ObjectTypesSupported
from bacpypes3.debugging import ModuleLogger
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.device import DeviceObject
from bacpypes3.primitivedata import ObjectIdentifier

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def set_bits(bits: ObjectTypesSupported) -> list[int]:
    """Return the indexes of the bits that are set."""
    return [i for i, bit in enumerate(bits) if bit]


async def test_object_types_no_application():
    device_object = DeviceObject(objectIdentifier=("device", 999), objectName="dev")

    # not bound to an application, just the device type
    object_types = device_object.protocolObjectTypesSupported
    assert isinstance(object_types, ObjectTypesSupported)
    assert set_bits(object_types) == [ObjectTypesSupported.device]


async def test_object_types_from_application():
    app = Application()
    device_object = DeviceObject(
        objectIdentifier=("device", 999), objectName="dev", vendorIdentifier=999
    )
    app.add_object(device_object)
    app.add_object(
        AnalogValueObject(objectIdentifier=("analog-value", 1), objectName="av1")
    )
    app.add_object(
        AnalogValueObject(objectIdentifier=("analog-value", 2), objectName="av2")
    )

    # one bit per object type, even when there are several of a type
    object_types = device_object.protocolObjectTypesSupported
    assert set_bits(object_types) == [
        ObjectTypesSupported.analogValue,
        ObjectTypesSupported.device,
    ]


async def test_object_types_skip_proprietary():
    device_object = DeviceObject(objectIdentifier=("device", 999), objectName="dev")

    # proprietary object types (128 and up) do not have a bit
    device_object._app = SimpleNamespace(
        objectIdentifier={
            ObjectIdentifier("device,999"): device_object,
            ObjectIdentifier((128, 1)): None,
        }
    )
    object_types = device_object.protocolObjectTypesSupported
    assert set_bits(object_types) == [ObjectTypesSupported.device]
    assert len(object_types) == len(ObjectTypesSupported([]))
