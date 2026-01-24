"""
Simple example that sends a Read Property request and decodes the response.
"""

import asyncio
from typing import Any as _Any
from typing import Callable, Optional, Tuple, Union

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.pdu import Address
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.basetypes import EventState, GetAlarmSummaryAlarmSummary
from bacpypes3.apdu import (
    GetAlarmSummaryRequest,
    GetAlarmSummaryACK,
    ErrorRejectAbortNack,
)

from bacpypes3.local.device import DeviceObject as _DeviceObject
from bacpypes3.local.networkport import NetworkPortObject as _NetworkPortObject
from bacpypes3.vendor import VendorInfo

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# this vendor identifier reference is used when registering custom classes
_vendor_id = 888


# create a VendorInfo object for this custom application before registering
# specialize object classes
custom_vendor_info = VendorInfo(_vendor_id)


class DeviceObject(_DeviceObject):
    pass


class NetworkPortObject(_NetworkPortObject):
    pass


@bacpypes_debugging
class GetAlarmSummaryService:
    _debug: Callable[..., None]

    async def do_GetAlarmSummaryRequest(self, apdu) -> None:
        """Respond to GetAlarmSummary request."""
        if _debug:
            GetAlarmSummaryService._debug("do_GetAlarmSummaryRequest %r", apdu)

        list_of_alarm_summaries = [
            GetAlarmSummaryAlarmSummary(
                objectIdentifier=self.device_object.objectIdentifier,
                alarmState=EventState.fault,
                acknowledgedTransitions=[],
            )
        ]
        # build a response
        resp = GetAlarmSummaryACK(
            listOfAlarmSummaries=list_of_alarm_summaries,
            context=apdu,
        )
        if _debug:
            GetAlarmSummaryService._debug("    - resp: %r", resp)

        # return the result
        await self.response(resp)


@bacpypes_debugging
class CustomApplication(Application, GetAlarmSummaryService):
    _debug: Callable[..., None]


async def main() -> None:
    app = None
    try:
        parser = SimpleArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = CustomApplication.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
