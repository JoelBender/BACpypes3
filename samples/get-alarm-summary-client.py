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
from bacpypes3.apdu import (
    GetAlarmSummaryRequest,
    GetAlarmSummaryACK,
    ErrorRejectAbortNack,
)
from bacpypes3.json import sequence_to_json

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

    async def get_alarm_summary(
        self,
        address: Union[Address, str],
    ) -> _Any:
        """
        Send a GetAlarmSummary Request to an address and decode the response.
        """
        if _debug:
            GetAlarmSummaryService._debug("get_alarm_summary %r", address)

        # parse the address if needed
        if isinstance(address, str):
            address = Address(address)
        elif not isinstance(address, Address):
            raise TypeError("address")

        # create a request
        get_alarm_summary_request = GetAlarmSummaryRequest(
            destination=address,
        )
        if _debug:
            GetAlarmSummaryService._debug(
                "    - read_property_request: %r", get_alarm_summary_request
            )

        # send the request, wait for the response
        response = await self.request(get_alarm_summary_request)
        if _debug:
            GetAlarmSummaryService._debug("    - response: %r", response)
        if isinstance(response, ErrorRejectAbortNack):
            if _debug:
                GetAlarmSummaryService._debug("    - error/reject/abort: %r", response)
            return response
        if not isinstance(response, GetAlarmSummaryACK):
            if _debug:
                GetAlarmSummaryService._debug("    - invalid response: %r", response)
            return None

        return response.listOfAlarmSummaries


@bacpypes_debugging
class CustomApplication(Application, GetAlarmSummaryService):
    _debug: Callable[..., None]


async def main() -> None:
    app: CustomApplication | None = None
    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "device_address",
            help="address of the client (A-device)",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = CustomApplication.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        try:
            response = await app.get_alarm_summary(
                args.device_address,
            )
            if _debug:
                _log.debug("    - response: %r", response)
        except ErrorRejectAbortNack as err:
            if _debug:
                _log.debug("    - exception: %r", err)
            response = err

        for i, alarm_summary in enumerate(response):
            print(f"[{i}] {sequence_to_json(alarm_summary)}")

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
