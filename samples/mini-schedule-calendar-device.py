#!/usr/bin/env python3
"""
Mini Schedule / Calendar BACnet Device (Fixed)
==============================================
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional

from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

# --- IMPORTS FOR LOCAL OBJECTS ---
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.schedule import ScheduleObject
from bacpypes3.local.object import Object as LocalObject

# --- IMPORTS FOR STANDARD DEFINITIONS ---
from bacpypes3.object import CalendarObject
from bacpypes3.basetypes import (
    DailySchedule, 
    TimeValue, 
    DateRange, 
    CalendarEntry, 
    SpecialEvent, 
    SpecialEventPeriod
)
from bacpypes3.primitivedata import Integer, Unsigned, Time, Date, ObjectIdentifier
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

# Debug logging setup
_debug = 0
_log = ModuleLogger(globals())

# ---------------------------------------------------------------------------
# Custom Class: LocalCalendarObject
# ---------------------------------------------------------------------------
class LocalCalendarObject(CalendarObject, LocalObject):
    """
    A local Calendar Object that can be added to an Application.
    Includes notificationClass to satisfy LocalObject requirements.
    """
    notificationClass: Optional[Unsigned] = None

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def bacnet_date_tuple(year: int, month: int, day: int) -> tuple[int, int, int, int]:
    dt = datetime(year, month, day)
    bacnet_dow = dt.weekday() + 1
    return (year - 1900, month, day, bacnet_dow)

def make_time_value(time_tuple: tuple[int, int, int, int], value: Integer) -> TimeValue:
    return TimeValue(time=Time(time_tuple), value=value)

def build_weekly_schedule() -> list[DailySchedule]:
    weekday_schedule = DailySchedule(
        daySchedule=[
            make_time_value((8, 0, 0, 0), Integer(1)),   
            make_time_value((17, 0, 0, 0), Integer(0)), 
        ]
    )
    weekend_schedule = DailySchedule(
        daySchedule=[
            make_time_value((0, 0, 0, 0), Integer(0)), 
        ]
    )
    return [
        weekday_schedule, weekday_schedule, weekday_schedule, weekday_schedule, weekday_schedule,
        weekend_schedule, weekend_schedule
    ]

# ---------------------------------------------------------------------------
# BACnet application
# ---------------------------------------------------------------------------

@bacpypes_debugging
class ScheduleCalendarApplication:
    def __init__(self, args):
        if _debug:
            _log.debug("Initializing ScheduleCalendarApplication")

        self.app = Application.from_args(args)

        # 1. CREATE THE CALENDAR OBJECT
        # -----------------------------
        holiday_date = Date(bacnet_date_tuple(2025, 12, 25))
        
        self.holiday_calendar = LocalCalendarObject(
            objectIdentifier=("calendar", 1),
            objectName="Holiday-Calendar",
            description="Global Holiday List (Exceptions)",
            presentValue=False, 
            dateList=[
                CalendarEntry(date=holiday_date)
            ]
        )

        # 2. CREATE EXCEPTION SCHEDULE
        # ----------------------------
        # FIX: Passed tuple (("calendar", 1)) instead of two args
        exception_period = SpecialEventPeriod(
            calendarReference=ObjectIdentifier(("calendar", 1))
        )
        exception_values = [
            make_time_value((0, 0, 0, 0), Integer(0))
        ]
        special_event = SpecialEvent(
            period=exception_period,
            listOfTimeValues=exception_values,
            eventPriority=1
        )

        # 3. CREATE THE SCHEDULE OBJECT
        # -----------------------------
        self.schedule_obj = ScheduleObject(
            objectIdentifier=("schedule", 1),
            objectName="Office-Hours-Schedule",
            presentValue=Integer(0),
            effectivePeriod=DateRange(
                startDate=Date(bacnet_date_tuple(2024, 1, 1)),
                endDate=Date(bacnet_date_tuple(2030, 12, 31))
            ),
            weeklySchedule=build_weekly_schedule(),
            exceptionSchedule=[special_event],
            scheduleDefault=Integer(0),
            description="M-F 8-5, Closed on Holidays (Calendar 1)"
        )

        # 4. CREATE THE MIRROR BV
        # -----------------------
        self.occupied_bv = BinaryValueObject(
            objectIdentifier=("binaryValue", 1),
            objectName="occupied-bv",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="Mirrors Schedule Present Value"
        )

        # Register objects
        for obj in [self.holiday_calendar, self.schedule_obj, self.occupied_bv]:
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
                    _log.debug(f"Schedule: {pv}")
            except Exception:
                pass

    async def _mirror_schedule_to_bv_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            try:
                pv = self.schedule_obj.presentValue.get_value()
                is_active = bool(pv) if pv is not None else False
                new_bv = "active" if is_active else "inactive"
                
                if self.occupied_bv.presentValue != new_bv:
                    self.occupied_bv.presentValue = new_bv
                    if _debug:
                        _log.debug(f"Updated occupied-bv to {new_bv}")
            except Exception:
                continue

async def main() -> None:
    global _debug
    parser = SimpleArgumentParser()
    args = parser.parse_args()

    if args.debug:
        _debug = 1
        _log.set_level("DEBUG")

    ScheduleCalendarApplication(args)
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)