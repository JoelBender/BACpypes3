"""
Simple example that has a device object and an additional custom object.
"""

import asyncio

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.ipv4.app import Application
from bacpypes3.basetypes import OptionalUnsigned

# this server has custom objects
import custom

# some debugging
_debug = 0
_log = ModuleLogger(globals())


async def main() -> None:
    try:
        app = None
        parser = SimpleArgumentParser()
        parser.add_argument(
            "-1",
            dest="option_1",
            action="store_true",
            help="omit the optional property",
        )
        parser.add_argument(
            "-2",
            dest="option_2",
            action="store_true",
            help="provide a Null optional property",
        )
        parser.add_argument(
            "-3",
            dest="option_3",
            type=int,
            # default=12345,
            help="provide an unsigned optional property",
        )
        args = parser.parse_args()

        # make sure the vendor identifier is the custom one
        args.vendoridentifier = custom._vendor_id
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # build an optional value, reference the device object
        if args.option_1:
            pass
        elif args.option_2:
            app.device_object.custom_optional_unsigned = OptionalUnsigned(null=())
        elif args.option_3 is not None:
            app.device_object.custom_optional_unsigned = OptionalUnsigned(
                unsigned=args.option_3
            )
        else:
            raise RuntimeError("please provide option 1, 2, or 3")

        # create a custom object
        custom_object = custom.ProprietaryObject(
            objectIdentifier=("custom_object", 12),
            objectName="Wowzers!",
            custom_integer=13,
        )
        if _debug:
            _log.debug("custom_object: %r", custom_object)

        app.add_object(custom_object)

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
