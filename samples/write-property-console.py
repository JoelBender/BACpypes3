"""
Simple example that sends Write Property requests.
"""

import asyncio
import re

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack

from bacpypes3.pdu import Address
from bacpypes3.comm import bind

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Simple example that sends Write Property requests.
    """

    _debug: Callable[..., None]

    async def do_write(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        value: str,
        priority: int = -1,
    ) -> None:
        """
        usage: write address objid prop[indx] value [ priority ]
        """
        if _debug:
            SampleCmd._debug(
                "do_write %r %r %r %r %r",
                address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return
        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        try:
            response = await this_application.write_property(
                address,
                object_identifier,
                property_identifier,
                value,
                property_array_index,
                priority,
            )
            if _debug:
                SampleCmd._debug("    - response: %r", response)
            assert response is None

        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            await self.response(str(err))


async def main() -> None:
    global this_application

    this_application = None
    try:
        parser = SimpleArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # build an application
        this_application = Application.from_args(args)
        if _debug:
            _log.debug("this_application: %r", this_application)

        print(f"{this_application = }")

        # wait until the user is done
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if this_application:
            this_application.close()


if __name__ == "__main__":
    asyncio.run(main())
