"""
Simple example that has a device object and an additional custom object.
"""

import asyncio

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.ipv4.app import Application

from bacpypes3.object import AnalogValueObject as _AnalogValueObject

from bacpypes3.local.object import Object as _Object
from bacpypes3.local.device import DeviceObject as _DeviceObject
from bacpypes3.local.networkport import NetworkPortObject as _NetworkPortObject
from bacpypes3.local.cov import COVIncrementCriteria
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
    """
    When running as an instance of this custom device, the DeviceObject is
    an extension of the one defined in bacpypes3.local.device (in this case
    doesn't add any proprietary properties).
    """

    vendorIdentifier = _vendor_id


class NetworkPortObject(_NetworkPortObject):
    """
    When running as an instance of this custom device, the NetworkPortObject is
    an extension of the one defined in bacpypes3.local.networkport (in this
    case doesn't add any proprietary properties).
    """

    pass


class AnalogValueObject(_Object, _AnalogValueObject):
    """
    This is an Analog Value Object that supports COV subscriptions.
    """

    _cov_criteria = COVIncrementCriteria


async def ramp(
    avo: AnalogValueObject, starting_value: float, step_count: int, step_size: float
) -> None:
    """
    Ramp the present value from the starting value up step_size increments
    step_count number of times, then back down again.
    """
    if _debug:
        _log.debug("ramp %r %r %r %r", avo, starting_value, step_count, step_size)

    try:
        while True:
            if _debug:
                _log.debug("- ramp up")
            for i in range(step_count):
                avo.presentValue = starting_value + i
                await asyncio.sleep(1.0)

            if _debug:
                _log.debug("- ramp down")
            for i in range(step_count):
                avo.presentValue = starting_value + step_count - i
                await asyncio.sleep(0.5)

    except KeyboardInterrupt:
        pass


async def main() -> None:
    try:
        app = None
        parser = SimpleArgumentParser()

        # make sure the vendor identifier is the custom one
        args = parser.parse_args()
        args.vendoridentifier = _vendor_id
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # create a custom object
        analog_value_object = AnalogValueObject(
            objectIdentifier=("analog-value", 1),
            objectName="Wowzers!",
            presentValue=75.0,
            covIncrement=1.0,
        )
        if _debug:
            _log.debug("analog_value_object: %r", analog_value_object)

        app.add_object(analog_value_object)

        # ramp up and down
        await ramp(analog_value_object, 75.0, 10, 1.0)

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
