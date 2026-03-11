#!/usr/bin/env python3
"""
Mini Schedule + Calendar BACnet Device (BACpypes3)
=================================================

A minimal BACnet/IP server device for testing BACnet Schedule + Calendar objects
using BACpypes3.

What this device exposes
------------------------
1) Calendar Object:  calendar,1
   - Name: "Holiday-Calendar"
   - dateList: includes a single holiday date (Dec 25, 2025)
   - Purpose: used by the Schedule object's exceptionSchedule

2) Schedule Object:  schedule,1
   - Name: "Office-Hours-Schedule"
   - weeklySchedule: Mon–Fri 08:00 → 1, 17:00 → 0; Sat/Sun 00:00 → 0
   - exceptionSchedule: references calendar,1 (holiday), forces value 0 on holidays
   - presentValue: maintained by the BACnet Schedule object logic

3) Binary Value Object: binaryValue,1
   - Name: "occupied-bv"
   - Mirrors the Schedule presentValue (active when presentValue is non-zero)

Typical testing workflow
------------------------
- Read device objectName / objectList from the device.
- Read schedule,1 presentValue
- Read schedule,1 weeklySchedule
- Read calendar,1 dateList
- Observe occupied-bv track the schedule presentValue.

Usage
-----
    python mini-schedule-calendar-device.py --name BensScheduleServer --instance 123456 --debug

Arguments
---------
--name       BACnet device name (e.g., "BensScheduleServer")
--instance   BACnet device instance ID (e.g., 123456)
--address    Optional override for IP/port binding (BACpypes3 address string)
--debug      Enable verbose debug logging
"""

import asyncio
import sys
from datetime import datetime, time
from typing import Optional

from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

# Local objects
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.schedule import ScheduleObject
from bacpypes3.local.object import Object as LocalObject

# Standard BACnet objects / types
from bacpypes3.object import CalendarObject
from bacpypes3.basetypes import (
    DailySchedule,
    TimeValue,
    DateRange,
    CalendarEntry,
    SpecialEvent,
    SpecialEventPeriod,
)
from bacpypes3.primitivedata import Integer, Unsigned, Time, Date, ObjectIdentifier


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_debug = 0
_log = ModuleLogger(globals())


# ---------------------------------------------------------------------------
# Human-readable constants (make the schedule definition obvious)
# ---------------------------------------------------------------------------

# BACnet schedule ordering is 7 entries: Monday .. Sunday
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

WEEKDAYS = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY]
WEEKENDS = [SATURDAY, SUNDAY]

# Office hours
OFFICE_OPEN = time(8, 0)
OFFICE_CLOSE = time(17, 0)
START_OF_DAY = time(0, 0)

# Occupancy semantics (kept as Integer 0/1 since your JSON output is working)
OCCUPIED = Integer(1)
UNOCCUPIED = Integer(0)


# ---------------------------------------------------------------------------
# Custom Class: LocalCalendarObject
# ---------------------------------------------------------------------------

class LocalCalendarObject(CalendarObject, LocalObject):
    """
    A CalendarObject that can be added to a BACpypes3 Application as a local object.
    """
    notificationClass: Optional[Unsigned] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bacnet_date_tuple(year: int, month: int, day: int) -> tuple[int, int, int, int]:
    """
    Convert a normal date (YYYY, M, D) into the BACnet Date tuple format:
        (year_since_1900, month, day, day_of_week)

    BACnet day_of_week uses 1=Monday ... 7=Sunday.
    """
    dt = datetime(year, month, day)
    bacnet_dow = dt.weekday() + 1  # Monday=1 ... Sunday=7
    return (year - 1900, month, day, bacnet_dow)


def tv(t: time, value: Integer) -> TimeValue:
    """
    Build a TimeValue from a Python time() and a BACnet atomic value.
    """
    return TimeValue(time=Time((t.hour, t.minute, t.second, 0)), value=value)


def build_daily_schedule(entries: list[tuple[time, Integer]]) -> DailySchedule:
    """
    Build a DailySchedule from a list of (time, value) pairs.
    """
    return DailySchedule(daySchedule=[tv(t, v) for t, v in entries])


def build_weekly_schedule() -> list[DailySchedule]:
    """
    Build a 7-day BACnet weekly schedule (Mon..Sun).

    Weekdays:
        08:00 -> 1 (occupied)
        17:00 -> 0 (unoccupied)

    Weekends:
        00:00 -> 0 (unoccupied)
    """
    weekday = build_daily_schedule([
        (OFFICE_OPEN, OCCUPIED),
        (OFFICE_CLOSE, UNOCCUPIED),
    ])

    weekend = build_daily_schedule([
        (START_OF_DAY, UNOCCUPIED),
    ])

    schedule: list[DailySchedule] = [weekend] * 7
    for d in WEEKDAYS:
        schedule[d] = weekday

    return schedule


# ---------------------------------------------------------------------------
# BACnet application
# ---------------------------------------------------------------------------

@bacpypes_debugging
class ScheduleCalendarApplication:
    def __init__(self, args):
        if _debug:
            _log.debug("Initializing ScheduleCalendarApplication")

        self.app = Application.from_args(args)

        # 1) Calendar object (holiday list)
        holiday_date = Date(bacnet_date_tuple(2025, 12, 25))

        self.holiday_calendar = LocalCalendarObject(
            objectIdentifier=("calendar", 1),
            objectName="Holiday-Calendar",
            description="Global Holiday List (used for Schedule exceptions)",
            dateList=[CalendarEntry(date=holiday_date)],
        )

        # 2) Exception schedule: on holiday calendar -> force value 0 all day
        exception_period = SpecialEventPeriod(
            calendarReference=ObjectIdentifier(("calendar", 1))
        )

        special_event = SpecialEvent(
            period=exception_period,
            listOfTimeValues=[tv(START_OF_DAY, UNOCCUPIED)],
            eventPriority=1,
        )

        # 3) Schedule object
        self.schedule_obj = ScheduleObject(
            objectIdentifier=("schedule", 1),
            objectName="Office-Hours-Schedule",
            description="M-F 8-5; weekend closed; holidays closed via Calendar(1)",
            presentValue=Integer(0),
            effectivePeriod=DateRange(
                startDate=Date(bacnet_date_tuple(2024, 1, 1)),
                endDate=Date(bacnet_date_tuple(2030, 12, 31)),
            ),
            weeklySchedule=build_weekly_schedule(),
            exceptionSchedule=[special_event],
            scheduleDefault=UNOCCUPIED,
        )

        # 4) Mirror BV
        self.occupied_bv = BinaryValueObject(
            objectIdentifier=("binaryValue", 1),
            objectName="occupied-bv",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="Mirrors Schedule(1) presentValue (active when non-zero)",
        )

        for obj in (self.holiday_calendar, self.schedule_obj, self.occupied_bv):
            self.app.add_object(obj)

        _log.info("Objects initialized: Calendar(1), Schedule(1), BV(1)")

        asyncio.create_task(self._log_schedule_loop())
        asyncio.create_task(self._mirror_schedule_to_bv_loop())

    async def _log_schedule_loop(self) -> None:
        while True:
            await asyncio.sleep(30.0)
            try:
                pv = self.schedule_obj.presentValue.get_value()
                if _debug:
                    _log.debug(f"Schedule presentValue: {pv!r}")
            except Exception as e:
                if _debug:
                    _log.debug(f"Schedule log loop error: {e!r}")

    async def _mirror_schedule_to_bv_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            try:
                pv = self.schedule_obj.presentValue.get_value()

                # Treat None/0 as inactive, any non-zero as active
                is_active = bool(pv) if pv is not None else False
                new_bv = "active" if is_active else "inactive"

                if self.occupied_bv.presentValue != new_bv:
                    self.occupied_bv.presentValue = new_bv
                    if _debug:
                        _log.debug(f"Updated occupied-bv to {new_bv}")

            except Exception as e:
                if _debug:
                    _log.debug(f"Mirror loop error: {e!r}")


async def main() -> None:
    global _debug

    parser = SimpleArgumentParser()
    args = parser.parse_args()

    if getattr(args, "debug", False):
        _debug = 1
        _log.set_level("DEBUG")

    ScheduleCalendarApplication(args)
    await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
