"""
Mini BACnet Device Example
==========================

This script initializes a minimal BACnet server device using BACpypes3.
It is ideal for rapid prototyping and testing with BACnet client tools
or supervisory platforms. You can easily add or remove objects to fit your use case.

Included Objects:
-----------------
- 1 Read-Only Analog Value (AV)
- 1 Read-Only Binary Value (BV)
- 1 Commandable Analog Value (AV)
- 1 Commandable Binary Value (BV)
- 1 Schedule Object (weekly occupancy schedule)

Commandable Points:
-------------------
Commandable AV and BV points support writes via the BACnet priority array.
They emulate real-world control points, such as thermostat setpoints, damper commands, etc.

Schedule Object:
----------------
A ScheduleObject is configured with typical office hours:
- Weekdays (Mon thru Fri): Occupied from 8:00 AM to 5:00 PM
- Weekends (Sat thru Sun): Unoccupied all day

The .presentValue property reflects the current scheduled value,
which you can decode with .presentValue.get_value().

Usage:
------
Run the script with the device name, instance ID, and optional debug flag:

    python mini-device-revisited.py --name BensServerTest --instance 3456789 --debug

Arguments:
----------
- --name       : The BACnet device name (e.g., "BensServerTest")
- --instance   : The BACnet device instance ID (e.g., 3456789)
- --address    : Optional — override the automatically detected IP address and port.
                 Requires ifaddr package for auto-detection.
                 See: https://bacpypes3.readthedocs.io/en/latest/gettingstarted/addresses.html#bacpypes3-addresses
- --debug      : Enables verbose debug logging (built-in to BACpypes3)

Notes on Units:
---------------
See the EngineeringUnits class in bacpypes3/basetypes.py for a full list of valid units.

Notes on ScheduleObject:
------------------------
See:
- AnyAtomic.get_value() in bacpypes3/constructeddata.py for decoding schedule values.
- ScheduleObject implementation in bacpypes3/local/schedule.py for how weekly schedules are evaluated.
"""


import asyncio
import sys
from datetime import date

from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable
from bacpypes3.local.schedule import ScheduleObject
from bacpypes3.basetypes import DailySchedule, TimeValue, DateRange
from bacpypes3.primitivedata import Integer, Null, Time, Date
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

# Debug logging setup
_debug = 0
_log = ModuleLogger(globals())

# Interval for updating values
INTERVAL = 5.0

# ========== Weekly Schedule Config ==========
def make_time_value(t, v):
    return TimeValue(time=Time(t), value=v)

# Weekday: 8AM–5PM occupied
weekday_schedule = DailySchedule(
    daySchedule=[
        make_time_value((8, 0, 0, 0), Integer(1)),   # 8:00 AM ON
        make_time_value((17, 0, 0, 0), Integer(0)),  # 5:00 PM OFF
    ]
)

# Weekend: always off
weekend_schedule = DailySchedule(
    daySchedule=[
        make_time_value((0, 0, 0, 0), Integer(0)),   # Midnight OFF
    ]
)

# Weekly Schedule (Monday=0 ... Sunday=6)
weekly_schedule = [
    weekday_schedule,  # Monday
    weekday_schedule,  # Tuesday
    weekday_schedule,  # Wednesday
    weekday_schedule,  # Thursday
    weekday_schedule,  # Friday
    weekend_schedule,  # Saturday
    weekend_schedule,  # Sunday
]

# Effective period (2024-01-01 to 2030-12-31)
effective_period = DateRange(
    startDate=Date((2024 - 1900, 1, 1, 1)),   # Jan 1, 2024, Monday
    endDate=Date((2030 - 1900, 12, 31, 7)),   # Dec 31, 2030, Sunday
)
# =============================================


@bacpypes_debugging
class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """Commandable Analog Value Object"""


@bacpypes_debugging
class CommandableBinaryValueObject(Commandable, BinaryValueObject):
    """Commandable Binary Value Object"""


@bacpypes_debugging
class SampleApplication:
    def __init__(self, args):
        if _debug:
            _log.debug("Initializing SampleApplication")

        self.app = Application.from_args(args)

        self.read_only_av = AnalogValueObject(
            objectIdentifier=("analogValue", 1),
            objectName="read-only-av",
            presentValue=4.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            units="degreesFahrenheit",
            description="Simulated Read-Only Analog Value",
        )

        self.read_only_bv = BinaryValueObject(
            objectIdentifier=("binaryValue", 1),
            objectName="read-only-bv",
            presentValue="active",
            statusFlags=[0, 0, 0, 0],
            description="Simulated Read-Only Binary Value",
        )

        self.commandable_av = CommandableAnalogValueObject(
            objectIdentifier=("analogValue", 2),
            objectName="commandable-av",
            presentValue=0.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            units="degreesFahrenheit",
            description="Commandable Analog Value (Simulated)",
        )

        self.commandable_bv = CommandableBinaryValueObject(
            objectIdentifier=("binaryValue", 2),
            objectName="commandable-bv",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="Commandable Binary Value (Simulated)",
        )

        self.schedule_obj = ScheduleObject(
            objectIdentifier=("schedule", 1),
            objectName="Office-Hours-Schedule",
            presentValue=Integer(0),
            weeklySchedule=weekly_schedule,
            scheduleDefault=Integer(0),
            effectivePeriod=effective_period,
            description="Typical 5-day office hours schedule",
        )

        for obj in [
            self.read_only_av,
            self.read_only_bv,
            self.commandable_av,
            self.commandable_bv,
            self.schedule_obj,
        ]:
            self.app.add_object(obj)

        _log.info("BACnet Objects initialized.")
        asyncio.create_task(self.update_values())

    async def update_values(self):
        test_values = [
            ("active", 1.0),
            ("inactive", 2.0),
            ("active", 3.0),
            ("inactive", 4.0),
        ]

        while True:
            await asyncio.sleep(INTERVAL)
            next_value = test_values.pop(0)
            test_values.append(next_value)

            self.read_only_av.presentValue = next_value[1]
            self.read_only_bv.presentValue = next_value[0]

            if _debug:
                _log.debug(f"Read-Only AV: {self.read_only_av.presentValue}")
                _log.debug(f"Read-Only BV: {self.read_only_bv.presentValue}")
                _log.debug(f"Commandable AV: {self.commandable_av.presentValue}")
                _log.debug(f"Commandable BV: {self.commandable_bv.presentValue}")
                _log.debug(f"Schedule Present Value: {self.schedule_obj.presentValue.get_value()}")


async def main():
    global _debug

    parser = SimpleArgumentParser()
    args = parser.parse_args()

    if args.debug:
        _debug = 1
        _log.set_level("DEBUG")
        _log.debug("Debug mode enabled")

    if _debug:
        _log.debug(f"Parsed arguments: {args}")

    app = SampleApplication(args)
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log.info("Keyboard interrupt received, shutting down.")
        sys.exit(0)
