"""
Test write_property() Property Monitors
---------------------------------------

Changes made to local objects by write_property(), the path taken by
WriteProperty and WritePropertyMultiple requests, should be passed along to
the property monitors the same way changes by attribute assignment are.
See issue #133.
"""

from __future__ import annotations

from typing import Any

import pytest

from bacpypes3.basetypes import BinaryPV, DailySchedule, DateRange, PropertyIdentifier
from bacpypes3.debugging import ModuleLogger
from bacpypes3.errors import PropertyError
from bacpypes3.local.analog import (
    AnalogInputObject,
    AnalogValueObject,
    AnalogValueObjectCmd,
)
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.schedule import ScheduleObject
from bacpypes3.primitivedata import Date, Real

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def add_monitor(obj: Any, attr: str) -> list[tuple[Any, Any]]:
    """Add a monitor to the object property, return the list of calls."""
    calls: list[tuple[Any, Any]] = []
    obj._property_monitors[attr].append(
        lambda old_value, new_value: calls.append((old_value, new_value))
    )
    return calls


async def test_present_value():
    """Non-commandable presentValue."""
    obj = AnalogValueObject(objectName="av", presentValue=1.0)
    calls = add_monitor(obj, "presentValue")

    await obj.write_property("presentValue", Real(2.0))
    assert obj.presentValue == 2.0
    assert calls == [(1.0, 2.0)]

    # same value again is not a change
    await obj.write_property("presentValue", Real(2.0))
    assert len(calls) == 1


async def test_property_identifier():
    """Property identifier as passed along by the service layer."""
    obj = BinaryValueObject(objectName="bv", presentValue="inactive")
    calls = add_monitor(obj, "presentValue")

    await obj.write_property(PropertyIdentifier.presentValue, "active")
    assert calls == [(BinaryPV.inactive, BinaryPV.active)]


async def test_out_of_service():
    """Not just presentValue."""
    obj = AnalogInputObject(objectName="ai", presentValue=1.0, outOfService=False)
    calls = add_monitor(obj, "outOfService")

    await obj.write_property("outOfService", True)
    assert calls == [(False, True)]


async def test_object_name():
    """Properties implemented with @property."""
    obj = AnalogValueObject(objectName="old-name", presentValue=1.0)
    calls = add_monitor(obj, "objectName")

    await obj.write_property("objectName", "new-name")
    assert obj.objectName == "new-name"
    assert calls == [("old-name", "new-name")]


async def test_commandable_once():
    """
    Commanding a presentValue already tells the monitors when the
    presentValue is recalculated, so do it exactly once.
    """
    obj = AnalogValueObjectCmd(objectName="av-cmd", presentValue=1.0)
    calls = add_monitor(obj, "presentValue")

    await obj.write_property("presentValue", Real(2.0), priority=8)
    assert obj.presentValue == 2.0
    assert calls == [(1.0, 2.0)]


async def test_write_failed():
    """No change, no monitors."""
    obj = AnalogValueObjectCmd(objectName="av-cmd", presentValue=1.0)
    calls = add_monitor(obj, "priorityArray")

    with pytest.raises(PropertyError):
        await obj.write_property("priorityArray", obj.priorityArray)
    assert calls == []


async def test_no_monitors():
    """No entries are added to the defaultdict for unmonitored properties."""
    obj = AnalogValueObject(objectName="av", presentValue=1.0)

    await obj.write_property("presentValue", Real(2.0))
    assert obj.presentValue == 2.0
    assert "presentValue" not in obj._property_monitors


async def test_array_element():
    """Array element writes change the array in place."""
    obj = ScheduleObject(
        objectName="sched",
        presentValue=Real(0.0),
        scheduleDefault=Real(0.0),
        effectivePeriod=DateRange(
            startDate=Date("2000-01-01"), endDate=Date("2099-12-31")
        ),
        weeklySchedule=[DailySchedule(daySchedule=[]) for _ in range(7)],
    )
    calls = add_monitor(obj, "weeklySchedule")

    tuesday = DailySchedule(
        daySchedule=[{"time": (8, 0, 0, 0), "value": Real(1.0)}],
    )
    await obj.write_property("weeklySchedule", tuesday, index=2)
    assert len(calls) == 1

    old_value, new_value = calls[0]
    assert old_value is not new_value
    assert old_value[1] == DailySchedule(daySchedule=[])
    assert new_value[1] == tuesday

    # same element again is not a change
    await obj.write_property("weeklySchedule", tuesday, index=2)
    assert len(calls) == 1
