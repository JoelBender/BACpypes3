"""
Simple example that has a very large octet string.
"""

import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.apdu import ReadPropertyRequest

from bacpypes3.object import (
    OctetStringValueObject as _OctetStringValueObject,
    VendorInfo,
)

from bacpypes3.local.object import Object as _Object
from bacpypes3.local.device import DeviceObject as _DeviceObject
from bacpypes3.local.networkport import NetworkPortObject as _NetworkPortObject

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


class OctetStringValueObject(_Object, _OctetStringValueObject):
    pass


@bacpypes_debugging
class CustomApplication(Application):
    _debug: Callable[..., None]

    async def do_ReadPropertyRequest(self, apdu: ReadPropertyRequest) -> None:
        """Return the value of some property of one of our objects."""
        if _debug:
            CustomApplication._debug("do_ReadPropertyRequest %r", apdu)

        # i_ams = await self.who_is(
        #     address=apdu.pduSource,
        # )
        # CustomApplication._debug("    - i_ams: %r", i_ams)
        # CustomApplication._debug("    - device_info_cache: %r", self.device_info_cache)

        return await super().do_ReadPropertyRequest(apdu)


async def main() -> None:
    try:
        app = None
        parser = SimpleArgumentParser()
        parser.add_argument(
            "--segmentation-supported",
            help="segmentation supported",
            action="store_true",
            default="no-segmentation",
        )
        parser.add_argument(
            "--max-apdu-length-accepted",
            help="max APDU length accepted",
            type=int,
            default=1024,
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # build an application
        app = CustomApplication.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # get a reference to the device object
        app.device_object.segmentationSupported = args.segmentation_supported
        app.device_object.maxApduLengthAccepted = args.max_apdu_length_accepted

        # make an octet string value object
        osvo = OctetStringValueObject(
            objectIdentifier=("octetstringValue", 1),
            objectName="test",
            presentValue=b"\0" * 600,
        )
        if _debug:
            _log.debug("osvo: %r", osvo)
        app.add_object(osvo)

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
