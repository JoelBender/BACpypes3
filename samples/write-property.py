"""
Simple example that sends a Write Property request.
"""

import asyncio
import re

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# 'property[index]' matching
property_index_re = re.compile(r"^([0-9A-Za-z-]+)(?:\[([0-9]+)\])?$")


async def main() -> None:
    app = None
    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "device_address",
            help="address of the server (B-device)",
        )
        parser.add_argument(
            "object_identifier",
            help="object identifier",
        )
        parser.add_argument(
            "property_identifier",
            help="property identifier with optional array index",
        )
        parser.add_argument(
            "value",
            help="value to write",
        )
        parser.add_argument(
            "priority",
            nargs="?",
            help="optional priority",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # interpret the address
        device_address = Address(args.device_address)
        if _debug:
            _log.debug("device_address: %r", device_address)

        # interpret the object identifier
        object_identifier = ObjectIdentifier(args.object_identifier)
        if _debug:
            _log.debug("object_identifier: %r", object_identifier)

        # split the property identifier and its index
        property_index_match = property_index_re.match(args.property_identifier)
        if not property_index_match:
            raise ValueError("property specification incorrect")
        property_identifier, property_array_index = property_index_match.groups()
        if property_identifier.isdigit():
            property_identifier = int(property_identifier)
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        # check the priority
        priority = None
        if args.priority:
            priority = int(args.priority)
            if (priority < 1) or (priority > 16):
                raise ValueError(f"priority: {priority}")
        if _debug:
            _log.debug("priority: %r", priority)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        try:
            response = await app.write_property(
                device_address,
                object_identifier,
                property_identifier,
                args.value,
                property_array_index,
                priority,
            )
            if _debug:
                _log.debug("response: %r", response)
        except ErrorRejectAbortNack as err:
            print(str(err))

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
