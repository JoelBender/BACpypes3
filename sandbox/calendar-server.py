"""
Simple example that has a device object
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.pdu import Address, LocalBroadcast, IPv4Address, PDU
from bacpypes3.comm import Client, bind

from bacpypes3.primitivedata import Null, Boolean, Integer, Unsigned, ObjectIdentifier
from bacpypes3.constructeddata import Array, ArrayOf
from bacpypes3.basetypes import (
    CalendarEntry,
    DailySchedule,
    DateRange,
    SpecialEvent,
    SpecialEventPeriod,
    TimeValue,
)
from bacpypes3.object import ScheduleObject

from bacpypes3.ipv4.app import NormalApplication
from bacpypes3.apdu import (
    ReadPropertyRequest,
    ReadPropertyACK,
    ErrorPDU,
    RejectPDU,
    AbortPDU,
)

from bacpypes3.local.device import DeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
this_application: NormalApplication = None


def main() -> None:
    global this_application

    try:
        loop = console = cmd = this_application = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="address",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # get the event loop
        loop = asyncio.get_event_loop()

        # evaluate the address
        ipv4_address = IPv4Address(args.address)
        if _debug:
            _log.debug("ipv4_address: %r", ipv4_address)

        # make a device object
        this_device = DeviceObject(
            objectIdentifier=("device", 1),
            objectName="test",
            vendorIdentifier=999,
        )
        if _debug:
            _log.debug("this_device: %r", this_device)

        # build the application
        this_application = NormalApplication(this_device, ipv4_address)

        #
        #   Simple daily schedule (actually a weekly schedule with every day
        #   being identical.
        #
        so = ScheduleObject(
            objectIdentifier=("schedule", 1),
            objectName="Schedule 1",
            presentValue=Integer(8),
            effectivePeriod=DateRange(
                startDate=(0, 1, 1, 1),
                endDate=(254, 12, 31, 2),
            ),
            weeklySchedule=[
                DailySchedule(
                    daySchedule=[
                        TimeValue(time=(8, 0, 0, 0), value=Integer(8)),
                        TimeValue(time=(14, 0, 0, 0), value=Null(())),
                        TimeValue(time=(17, 0, 0, 0), value=Integer(42)),
                        # TimeValue(time=(0,0,0,0), value=Null()),
                    ]
                ),
            ]
            * 7,
            scheduleDefault=Integer(0),
        )
        _log.debug("    - so: %r", so)
        this_application.add_object(so)

        # just keep running
        loop.run_forever()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if this_application:
            this_application.server.close()
        if loop:
            loop.close()


if __name__ == "__main__":
    main()
