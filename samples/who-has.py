"""
Simple example that sends a Who-Has request for an object identifier and prints
out the device instance number, object identifier and object name of the
responses.
"""

import asyncio

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.primitivedata import ObjectIdentifier
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
        parser.add_argument(
            "object_identifier",
            help="object identifier",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        object_identifier = ObjectIdentifier(args.object_identifier)
        if _debug:
            _log.debug("object_identifier: %r", object_identifier)

        # run the query
        i_haves = await app.who_has(
            args.low_limit,
            args.high_limit,
            object_identifier,
        )
        if _debug:
            _log.debug("    - i_haves: %r", i_haves)
        for i_have in i_haves:
            if _debug:
                _log.debug("    - i_have: %r", i_have)
            print(
                f"{i_have.deviceIdentifier[1]} {i_have.objectIdentifier} {i_have.objectName!r}"
            )

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
