"""
Simple example that sends a Who-Is request for a device and when it responds
reads some interesting properties of the objects in the device.
"""

import sys
import asyncio

from typing import List, Optional

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application
from bacpypes3.vendor import get_vendor_info

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
show_warnings: bool = False


async def main() -> None:
    app = None
    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "device_identifier",
            type=int,
            help="device identifier",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # look for the device
        i_ams = await app.who_is(args.device_identifier, args.device_identifier)
        if not i_ams:
            return

        i_am = i_ams[0]
        if _debug:
            _log.debug("    - i_am: %r", i_am)

        device_address: Address = i_am.pduSource
        device_identifier: ObjectIdentifier = i_am.iAmDeviceIdentifier
        vendor_info = get_vendor_info(i_am.vendorID)
        if _debug:
            _log.debug("    - vendor_info: %r", vendor_info)

        # read the entire object list at once, or one element at a time if
        # it is too big and the device cannot segment the response
        object_list: List[ObjectIdentifier] = []
        try:
            object_list = await app.read_object_list(device_address, device_identifier)
        except ErrorRejectAbortNack as err:
            if show_warnings:
                sys.stderr.write(f"{device_identifier} object-list error: {err}\n")
        for object_identifier in object_list:
            object_class = vendor_info.get_object_class(object_identifier[0])
            if _debug:
                _log.debug("    - object_class: %r", object_class)
            if object_class is None:
                if show_warnings:
                    sys.stderr.write(f"unknown object type: {object_identifier}\n")
                continue

            print(f"    {object_identifier}:")

            # read the property list
            property_list: Optional[List[PropertyIdentifier]] = None
            try:
                property_list = await app.read_property(
                    device_address, object_identifier, "property-list"
                )
                if _debug:
                    _log.debug("    - property_list: %r", property_list)
            except ErrorRejectAbortNack as err:
                if show_warnings:
                    sys.stderr.write(
                        f"{object_identifier} property-list error: {err}\n"
                    )

            for property_name in (
                "object-name",
                "description",
                "present-value",
                "units",
            ):
                try:
                    # don't bother attempting to read the property if the object
                    # doesn't say it exists
                    property_identifier = PropertyIdentifier(property_name)
                    if property_list and property_identifier not in property_list:
                        continue

                    property_class = object_class.get_property_type(property_identifier)
                    if property_class is None:
                        if show_warnings:
                            sys.stderr.write(
                                f"{object_identifier} unknown property: {property_identifier}\n"
                            )
                        continue
                    if _debug:
                        _log.debug("    - property_class: %r", property_class)

                    property_value = await app.read_property(
                        device_address, object_identifier, property_identifier
                    )
                    print(f"        {property_name}: {property_value}")

                except ErrorRejectAbortNack as err:
                    if show_warnings:
                        sys.stderr.write(
                            f"{object_identifier} {property_name} error: {err}\n"
                        )
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
