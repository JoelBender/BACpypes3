"""
Simple example that has a device object and an additional custom object.
"""

import asyncio

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.ipv4.app import Application

# this server has custom objects
import custom

# some debugging
_debug = 0
_log = ModuleLogger(globals())


async def main() -> None:
    try:
        app = None
        args = SimpleArgumentParser().parse_args()

        # make sure the vendor identifier is the custom one
        args.vendoridentifier = custom._vendor_id
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # create a custom object
        custom_object = custom.ProprietaryObject(
            objectIdentifier=("custom", 12),
            objectName="Wowzers!",
            custom=13,
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
