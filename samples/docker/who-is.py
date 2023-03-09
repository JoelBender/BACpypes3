"""
Simple example that sends a Who-Is request and prints out the device identifier
and address for the devices that respond.
"""

import asyncio

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())


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
                _log._debug("    - i_am: %r", i_am)
            print(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
