#!/usr/bin/python

"""
Simple console example that echos the input converted to uppercase.  This is a
derivative of the console.py sample that looks for a BACpypes.json settings
file, or the JSON file specified with the --json option.
"""

import sys
import asyncio
import re

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import JSONArgumentParser
from bacpypes3.console import Console
from bacpypes3.comm import bind
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# 'property[index]' matching
property_index_re = re.compile(r"^([0-9A-Za-z-]+)(?:\[([0-9]+)\])?$")

# globals
app: Application


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_read(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
    ) -> None:
        """
        usage: read address objid prop[indx]
        """
        if _debug:
            SampleCmd._debug(
                "do_read %r %r %r", address, object_identifier, property_identifier
            )
        print(f"{app = }")

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return

        property_identifier, property_array_index = property_index_match.groups()
        if property_identifier.isdigit():
            property_identifier = int(property_identifier)
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        try:
            property_value = await app.read_property(
                address, object_identifier, property_identifier, property_array_index
            )
            if _debug:
                SampleCmd._debug("    - property_value: %r", property_value)
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            property_value = err

        if isinstance(property_value, AnyAtomic):
            if _debug:
                SampleCmd._debug("    - schedule objects")
            property_value = property_value.get_value()

        await self.response(str(property_value))


async def main() -> None:
    global app

    try:
        console = None
        parser = JSONArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # build an application
        app = Application.from_json(settings.json["application"])
        if _debug:
            _log.debug("app: %r", app)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
