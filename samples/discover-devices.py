"""
Simple example that sends a Who-Is request and prints out the device identifier,
address, and description for the devices that respond.
"""

import sys
import asyncio

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application

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
            "low_limit",
            type=int,
            help="device instance range low limit",
        )
        parser.add_argument(
            "high_limit",
            type=int,
            help="device instance range high limit",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # run the query
        i_ams = await app.who_is(args.low_limit, args.high_limit)
        for i_am in i_ams:
            if _debug:
                _log.debug("    - i_am: %r", i_am)

            device_address: Address = i_am.pduSource
            device_identifier: ObjectIdentifier = i_am.iAmDeviceIdentifier
            print(f"{device_identifier} @ {device_address}")

            try:
                device_description: str = await app.read_property(
                    device_address, device_identifier, "description"
                )
                print(f"    description: {device_description}")

            except ErrorRejectAbortNack as err:
                if show_warnings:
                    sys.stderr.write(f"{device_identifier} description error: {err}\n")
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
