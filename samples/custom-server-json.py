"""
Simple example that gets its configuration from a JSON file and could include
custom objects.  Double check the JSON configuration that the vendor-identifier
matches the expect value in the `custom` module.
"""

import asyncio

from bacpypes3.settings import settings
from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import JSONArgumentParser
from bacpypes3.ipv4.app import Application

# this server has custom objects
import custom  # noqa: F401

# some debugging
_debug = 0
_log = ModuleLogger(globals())


async def main() -> None:
    try:
        app = None
        args = JSONArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_json(settings.json["application"])
        if _debug:
            _log.debug("app: %r", app)
            for obj_name, obj in app.objectIdentifier.items():
                _log.debug("    %s: %r (%s)", obj_name, obj, type(obj))

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
