"""
Simple example that sends a Read Property request and decodes the response.
"""

import asyncio
import re

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

from bacpypes3.constructeddata import AnyAtomic
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
            help="object identifier, like 'analog-input,1'",
        )
        parser.add_argument(
            "property_identifier",
            help="property identifier with optional array index, like 'present-value'",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        try:
            response = await app.read_property(
                args.device_address,
                args.object_identifier,
                args.property_identifier,
            )
            if _debug:
                _log.debug("    - response: %r", response)
        except ErrorRejectAbortNack as err:
            if _debug:
                _log.debug("    - exception: %r", err)
            response = err

        if isinstance(response, AnyAtomic):
            if _debug:
                _log.debug("    - schedule objects")
            response = response.get_value()

        print(str(response))

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
