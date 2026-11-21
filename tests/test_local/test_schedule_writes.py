from __future__ import annotations

import asyncio
import gc
from typing import Any

from bacpypes3.basetypes import DailySchedule, DateRange, DeviceObjectPropertyReference
from bacpypes3.debugging import ModuleLogger
from bacpypes3.local.analog import AnalogValueObjectCmd
from bacpypes3.local.schedule import ScheduleObject
from bacpypes3.primitivedata import Date, ObjectIdentifier, Real

_debug = 0
_log = ModuleLogger(globals())


class StubApplication:
    device_object = None

    def __init__(self, *objs: Any) -> None:
        self.objects = {obj.objectIdentifier: obj for obj in objs}

    def get_object_id(self, objid: ObjectIdentifier) -> Any:
        return self.objects.get(objid)


def schedule_object(**kwargs: Any) -> ScheduleObject:
    sched = ScheduleObject(
        objectIdentifier="schedule,1",
        objectName="sched",
        presentValue=Real(0.0),
        scheduleDefault=Real(0.0),
        effectivePeriod=DateRange(
            startDate=Date("2000-01-01"), endDate=Date("2099-12-31")
        ),
        weeklySchedule=[DailySchedule(daySchedule=[]) for _ in range(7)],
        **kwargs,
    )
    if sched._interpret_schedule_handle:
        sched._interpret_schedule_handle.cancel()
    return sched


async def test_present_value_written_to_reference():
    target = AnalogValueObjectCmd(
        objectIdentifier="analog-value,1",
        objectName="av",
        presentValue=1.0,
    )
    sched = schedule_object(
        listOfObjectPropertyReferences=[
            DeviceObjectPropertyReference(
                objectIdentifier="analog-value,1",
                propertyIdentifier="present-value",
            )
        ],
        priorityForWriting=8,
    )
    sched._app = StubApplication(sched, target)

    sched.presentValue = Real(42.0)
    for _ in range(3):
        await asyncio.sleep(0)

    assert target.presentValue == 42.0
    assert target.priorityArray[7].real == 42.0


async def test_write_error_is_retrieved():
    target = AnalogValueObjectCmd(
        objectIdentifier="analog-value,1",
        objectName="av",
        presentValue=1.0,
    )
    sched = schedule_object(
        listOfObjectPropertyReferences=[
            DeviceObjectPropertyReference(
                objectIdentifier="analog-value,1",
                propertyIdentifier="priority-array",
            )
        ],
        priorityForWriting=8,
    )
    sched._app = StubApplication(sched, target)

    loop = asyncio.get_running_loop()
    unhandled: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda loop, context: unhandled.append(context))
    try:
        sched.presentValue = Real(42.0)
        for _ in range(3):
            await asyncio.sleep(0)
        gc.collect()
    finally:
        loop.set_exception_handler(None)

    assert unhandled == []
    assert target.presentValue == 1.0
